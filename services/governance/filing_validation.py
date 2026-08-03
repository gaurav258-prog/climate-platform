"""Pre-submission validation — the checks that gate a filing before a human ever reviews it.

A regulatory filing shouldn't reach a reviewer (let alone the regulator) with a blocking defect. This runs
a framework-specific rule set over the *frozen snapshot* behind a filing and returns a full checklist —
every rule, passed or failed — split into three severities:

  blocking — the filing cannot be submitted for approval while this fails (e.g. nothing scored, no manager LEI)
  warning  — file-able but the reviewer must see it (e.g. partial coverage, thin emissions data)
  info     — context, never gates

Rules fall in three families, mirroring how a filing goes wrong:
  completeness — is every in-scope item scored, or explicitly flagged? are mandatory identities present?
  plausibility — are the numbers in sane ranges (non-negative, shares in 0–100, exposure ≤ book)?
  tie_out      — do the figures reconcile internally (severity buckets sum to the book; VaR = High+ buckets)?

Honesty carries through: a rule never invents a value — it reads what the assembler produced and flags a gap
as a gap. Because it reads the frozen snapshot, a filing's validation result is stable and reproducible.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.governance.filings import get_filing


def _f(rule: str, category: str, severity: str, passed: bool, message: str, ref: str | None = None) -> dict:
    return {"rule": rule, "category": category, "severity": severity, "passed": passed,
            "message": message, "ref": ref}


def _eur(n) -> str:
    try:
        return f"€{float(n):,.0f}"
    except (TypeError, ValueError):
        return "€—"


# ── framework rule sets ─────────────────────────────────────────────────

def _validate_bank_tcfd(payload: dict) -> list[dict]:
    out: list[dict] = []
    rollup = payload.get("rollup") or {}
    n_assets = rollup.get("n_assets", 0)
    n_scored = rollup.get("n_scored", 0)
    total = rollup.get("total_value_eur", 0) or 0

    # completeness
    out.append(_f("has_assets", "completeness", "blocking", n_assets > 0,
                  f"{n_assets} assets in scope" if n_assets > 0 else "No assets in scope — nothing to file"))
    out.append(_f("some_scored", "completeness", "blocking", n_scored > 0,
                  f"{n_scored} assets scored on the golden source" if n_scored > 0
                  else "No assets scored — the disclosure would be empty"))
    cov = round(100 * n_scored / n_assets, 1) if n_assets else 0
    out.append(_f("full_coverage", "completeness", "warning", n_assets > 0 and n_scored == n_assets,
                  f"All {n_assets} assets scored ({cov}%)" if n_scored == n_assets
                  else f"{n_scored}/{n_assets} scored ({cov}%) — {n_assets - n_scored} unscored are excluded from exposure"))

    # plausibility
    out.append(_f("total_value_positive", "plausibility", "blocking", total > 0,
                  f"Total book value {_eur(total)}" if total > 0 else "Total book value is zero"))
    pct = rollup.get("pct_value_at_risk", 0)
    out.append(_f("share_in_range", "plausibility", "warning", 0 <= pct <= 100,
                  f"Share of book at High+ risk: {pct}%" if 0 <= pct <= 100
                  else f"Share at risk out of range: {pct}%"))
    em = payload.get("financed_emissions_tco2e") or {}
    neg = [k for k, v in em.items() if (v or 0) < 0]
    out.append(_f("emissions_non_negative", "plausibility", "warning", not neg,
                  "Financed emissions are non-negative" if not neg else f"Negative financed emissions: {neg}"))
    for hz, b in (payload.get("by_hazard") or {}).items():
        ev = b.get("exposed_value_eur", 0) or 0
        ok = ev <= total * 1.0001 or total == 0
        out.append(_f(f"hazard_within_book:{hz}", "plausibility", "warning", ok,
                      f"{hz.replace('_', ' ')}: {_eur(ev)} exposed (≤ book)" if ok
                      else f"{hz.replace('_', ' ')}: exposed {_eur(ev)} exceeds book {_eur(total)}"))

    # tie-out (internal reconciliation)
    buckets = rollup.get("by_bucket") or {}
    bucket_sum = sum((b.get("value_eur", 0) or 0) for b in buckets.values())
    tol = max(1.0, 0.005 * total)
    out.append(_f("buckets_reconcile", "tie_out", "blocking", abs(bucket_sum - total) <= tol,
                  f"Severity buckets reconcile to the book total ({_eur(bucket_sum)})"
                  if abs(bucket_sum - total) <= tol
                  else f"Severity buckets {_eur(bucket_sum)} ≠ book total {_eur(total)}"))
    var = rollup.get("value_at_risk_eur", 0) or 0
    hv = sum((buckets.get(b, {}).get("value_eur", 0) or 0) for b in ("H", "VH"))
    out.append(_f("var_ties_to_buckets", "tie_out", "warning", abs(var - hv) <= tol,
                  "Value-at-risk ties to the High + Very-high buckets" if abs(var - hv) <= tol
                  else f"Value-at-risk {_eur(var)} ≠ High+VH buckets {_eur(hv)}"))
    return out


def _validate_sfdr_pai(payload: dict) -> list[dict]:
    out: list[dict] = []
    if payload.get("error"):
        return [_f("statement_builds", "completeness", "blocking", False,
                   f"Statement could not be assembled: {payload['error']}")]
    entity = payload.get("entity") or {}
    positions = entity.get("positions", 0) or 0
    total = entity.get("total_value_eur", 0) or 0

    out.append(_f("has_positions", "completeness", "blocking", positions > 0,
                  f"{positions} positions in scope" if positions > 0 else "No positions to report on"))
    out.append(_f("total_value_positive", "plausibility", "blocking", total > 0,
                  f"Total NAV in scope {_eur(total)}" if total > 0 else "Total value in scope is zero"))

    # SFDR is not filable without the manager's reporting identity (LEI, legal name, contact) + required narratives
    fr = payload.get("filing_readiness") or {}
    missing = fr.get("missing") or []
    out.append(_f("filing_identity", "completeness", "blocking", bool(fr.get("ready_to_file")),
                  "Reporting-entity identity & narratives complete" if fr.get("ready_to_file")
                  else f"Not submittable — missing: {', '.join(missing)}"))

    cs = payload.get("coverage_summary") or {}
    mand = cs.get("mandatory_indicators", 0) or 0
    comp = cs.get("computed", 0) or 0
    out.append(_f("mandatory_indicators", "completeness", "warning", mand > 0 and comp == mand,
                  f"All {mand} mandatory PAI indicators computed" if mand > 0 and comp == mand
                  else f"{comp}/{mand} mandatory PAI indicators computed — the rest await issuer input"))
    emis = cs.get("emissions_coverage_pct")
    if emis is not None:
        out.append(_f("emissions_coverage", "completeness", "warning", emis >= 50,
                      f"Emissions coverage {emis}% of NAV" if emis >= 50
                      else f"Emissions coverage only {emis}% of NAV — PAI 1–3 rest on a thin base"))
    nm = (payload.get("narratives") or {}).get("missing") or []
    out.append(_f("narratives_present", "completeness", "warning", not nm,
                  "All required narratives present" if not nm else f"{len(nm)} required narrative(s) missing"))

    # per-fund thin coverage — surfaced, never averaged away (info)
    thin = [f["fund_name"] for f in (payload.get("per_fund") or [])
            if (f.get("emissions_coverage_pct") or 0) < 30]
    out.append(_f("per_fund_coverage", "completeness", "info", not thin,
                  "Every fund has ≥30% emissions coverage" if not thin
                  else f"Thinly-covered fund(s) inside the entity total: {', '.join(thin)}"))
    return out


_RULESETS = {"bank_tcfd": _validate_bank_tcfd, "sfdr_pai": _validate_sfdr_pai}


# ── entry point ─────────────────────────────────────────────────────────

def validate_filing(session: Session, org_id: str, filing_id: str) -> dict:
    """Run the checklist over a filing's frozen snapshot. Returns findings + counts; `passed` is True
    only when no blocking rule fails."""
    filing = get_filing(session, org_id, filing_id, with_payload=True)
    if not filing:
        raise ValueError("filing not found")
    findings: list[dict] = []

    snap = filing.get("snapshot")
    # generic: the frozen bytes must still verify against their hash
    findings.append(_f("snapshot_frozen", "integrity", "blocking", bool(snap),
                       "Report is frozen as an immutable snapshot" if snap
                       else "No frozen snapshot behind this filing"))
    if snap:
        findings.append(_f("hash_verified", "integrity", "blocking", bool(snap.get("hash_verified")),
                           "Frozen payload matches its content hash" if snap.get("hash_verified")
                           else "Frozen payload does NOT match its content hash — tampered or drifted"))
        ruleset = _RULESETS.get(filing["framework"])
        if ruleset:
            findings.extend(ruleset(snap.get("payload") or {}))
        # cross-report reconciliation vs sibling filings (warning/info only — never blocks a real change)
        from services.governance.filing_crosscheck import cross_report_findings
        findings.extend(cross_report_findings(session, org_id, filing))

    blocking = sum(1 for f in findings if f["severity"] == "blocking" and not f["passed"])
    warnings = sum(1 for f in findings if f["severity"] == "warning" and not f["passed"])
    passed = blocking == 0
    return {"filing_id": filing_id, "framework": filing["framework"], "status": filing["status"],
            "findings": findings, "blocking": blocking, "warnings": warnings,
            "checks": len(findings), "passed": passed}


def blocking_messages(result: dict) -> list[str]:
    return [f["message"] for f in result["findings"] if f["severity"] == "blocking" and not f["passed"]]
