"""The record of every engine run that produces a filing: what it read, and whether its output holds (intake phase 4).

Inputs (the manifest)
  the book in scope, read the way the engine reads it — per book: how many assets, their total value, and a SHA-256 of
  every fact of every asset (the fingerprint of exactly this input); the last data batch that landed and the last
  fact statement recorded (phase 3); the vintage of the hazard scores those assets sit on; how many differences between
  the client's values and ours were still undecided.

Output checks
  integrity (a failure refuses the freeze — the output cannot be trusted):
    finite        no NaN / infinite number anywhere in the output
    identity      every asset in scope is in the output or was eliminated as group-internal; nothing else is
    totals        the listed values add up to the reported total
    input tie     the reported total equals the input total — where no currency translation, consolidation weight or
                  elimination stands in between (otherwise the per-entity translation table is the tie, and says so)
  attention (a warning is kept on the run and shown with the filing):
    scored        assets not yet scored
    differences   undecided differences between the client's values and ours, in scope
    feeds         a hazard feed the basis depends on is overdue or failed
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class RunCheckError(ValueError):
    """An integrity check failed: the output does not hold and is not frozen."""
    def __init__(self, checks: list[dict]):
        self.checks = checks
        failed = [c for c in checks if c["status"] == "fail"]
        super().__init__("The engine's output did not pass its checks, so nothing was frozen: " +
                         "; ".join(f"{c['label']} — {c['detail']}" for c in failed))


# report type → (vertical, list key, id key, value key, count key, total key, scored key) of the located books (the retired
# reit_tcfd / insurer_climate / assetmgmt_tcfd stay so their filings' runs and revisions remain readable)
LOCATED = {
    "bank_tcfd": ("banking", "assets", "asset_id", "value_eur", "n_assets", "total_value_eur", "n_scored"),
    "bank_p3esg": ("banking", "assets", "asset_id", "value_eur", "n_assets", "total_value_eur", "n_scored"),
    "reit_tcfd": ("realestate", "properties", "property_id", "property_value_eur", "n_properties", "total_value_eur", "n_scored"),
    "reit_taxonomy": ("realestate", "properties", "property_id", "property_value_eur", "n_properties", "total_value_eur", "n_scored"),
    "insurer_climate": ("insurance", "policies", "policy_id", "sum_insured_eur", "n_policies", "total_sum_insured_eur", "n_priced"),
    "insurer_solvency": ("insurance", "policies", "policy_id", "sum_insured_eur", "n_policies", "total_sum_insured_eur", "n_priced"),
    "insurer_orsa_climate": ("insurance", "policies", "policy_id", "sum_insured_eur", "n_policies", "total_sum_insured_eur", "n_priced"),
    "insurer_recovery_stress": ("insurance", "policies", "policy_id", "sum_insured_eur", "n_policies", "total_sum_insured_eur", "n_priced"),
    "assetmgmt_tcfd": ("assetmgmt", "holdings", "holding_id", "position_value_eur", "n_holdings", "total_portfolio_value_eur", "n_scored"),
}
_VERTICAL_BOOK = {"banking": "bank_assets", "insurance": "insurance_policies", "realestate": "realestate_properties",
                  "assetmgmt": "assetmgmt_holdings"}
_AGRI_BOOKS = ("company_sites", "supply_plots")


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha(obj) -> str:
    return hashlib.sha256(_canonical(obj).encode()).hexdigest()


# ───────────────────────────── inputs ─────────────────────────────

def _book_rows(session: Session, org_id: str, book_key: str, entity_ids: Optional[list]) -> tuple[list[dict], str]:
    from services.intake.observations import books, norm
    book = next(b for b in books() if b.key == book_key)
    rows = book.load(session, org_id)
    if entity_ids:
        scope = {str(e) for e in entity_ids}
        rows = [r for r in rows if r.get("reporting_entity_id") in scope]
    clean = sorted(({k: norm(v) for k, v in r.items()} for r in rows), key=lambda r: r["entity_id"])
    return clean, book.table


def _value_of(row: dict) -> float:
    for k in ("primary_value_eur", "annual_value_eur", "annual_spend_eur"):
        if row.get(k) is not None:
            return float(row[k])
    return 0.0


def inputs(session: Session, org_id: str, report_type: str, entity_ids: Optional[list] = None,
           fund_id: Optional[str] = None, as_of_dates: Optional[list] = None,
           asset_ids: Optional[list] = None) -> tuple[dict, dict]:
    """(manifest, the in-scope rows by book) — the manifest is stored, the rows feed the identity / tie checks.
    fund_id: a per-product report reads that fund's (and its sub-funds') positions on the position dates it froze
    (as_of_dates); their value is the average over those dates, as the document computes it.
    asset_ids: a report that decides its own scope (the ESRS statement: held at the year end, in the undertaking's
    consolidation) names the assets it read."""
    if report_type in LOCATED:
        keys = (_VERTICAL_BOOK[LOCATED[report_type][0]],)
    elif report_type == "csrd_e1":
        keys = _AGRI_BOOKS
    elif report_type == "esrs_pack":                    # the ESRS statement reads the undertaking's own sites
        keys = ("company_sites",)
    else:
        keys = ()
    books, rows_by_book, ids, cells, tables = [], {}, [], set(), set()
    for k in keys:
        rows, table = _book_rows(session, org_id, k, entity_ids if report_type in LOCATED else None)
        if asset_ids is not None:
            keep = {str(a) for a in asset_ids}
            rows = [r for r in rows if r["entity_id"] in keep]
        rows_by_book[k] = rows
        tables.add(table)
        ids += [r["entity_id"] for r in rows]
        books.append({"book": k, "n_assets": len(rows), "total_value_eur": round(sum(_value_of(r) for r in rows), 2),
                      "facts_sha256": _sha(rows)})
    if report_type == "sfdr_pai" or fund_id is not None:
        from services.asset_manager_engine import fund_descendant_ids
        pos = [dict(r) for r in session.execute(text("""
            SELECT p.position_id::text, p.fund_id::text, p.security_id::text, CAST(p.market_value_eur AS FLOAT) AS market_value_eur,
                   p.as_of_date::text AS as_of_date
            FROM fund_positions p JOIN funds f ON f.fund_id = p.fund_id WHERE f.org_id = CAST(:o AS uuid)
              AND (CAST(:ids AS uuid[]) IS NULL OR p.fund_id = ANY(CAST(:ids AS uuid[])))
              AND (CAST(:d AS date[]) IS NULL OR p.as_of_date = ANY(CAST(:d AS date[])))
            ORDER BY p.position_id
        """), {"o": org_id, "ids": fund_descendant_ids(session, fund_id) if fund_id else None,
               "d": list(as_of_dates) if fund_id and as_of_dates is not None else None}).mappings().all()]
        n_dates = len({p["as_of_date"] for p in pos}) or 1
        total = sum(p["market_value_eur"] or 0 for p in pos) / (n_dates if fund_id else 1)
        books.append({"book": "fund_positions", "n_assets": len({p["security_id"] for p in pos}) if fund_id else len(pos),
                      "total_value_eur": round(total, 2), "facts_sha256": _sha(pos),
                      **({"position_dates": n_dates} if fund_id else {})})
    for rows in rows_by_book.values():
        cells |= {r["h3_cell"] for r in rows if r.get("h3_cell")}
    sc = session.execute(text("""
        SELECT count(DISTINCT h3_cell), max(scored_at) FROM canonical_scores
        WHERE h3_cell = ANY(:c) AND valid_to IS NULL AND score_lane = 'standing'
    """), {"c": list(cells)}).first() if cells else (0, None)
    batch = session.execute(text("""
        SELECT batch_id::text, template, imported_at FROM ingest_batches
        WHERE org_id = CAST(:o AS uuid) AND state = 'imported' ORDER BY imported_at DESC NULLS LAST LIMIT 1
    """), {"o": org_id}).mappings().first()
    last_obs = session.execute(text("SELECT max(observation_id) FROM asset_observations WHERE org_id = CAST(:o AS uuid)"),
                               {"o": org_id}).scalar()
    open_c = session.execute(text("""
        SELECT count(*) FROM asset_conflicts WHERE org_id = CAST(:o AS uuid) AND status <> 'resolved'
          AND asset_table = ANY(:t) AND asset_id = ANY(CAST(:i AS uuid[]))
    """), {"o": org_id, "t": list(tables), "i": ids}).scalar() if ids else 0
    manifest = {"books": books,
                "scores": {"n_cells": int(sc[0] or 0), "latest_scored_at": sc[1].isoformat() if sc[1] else None},
                "last_batch": ({**dict(batch), "imported_at": batch["imported_at"].isoformat() if batch["imported_at"] else None}
                               if batch else None),
                "last_observation_id": last_obs, "open_differences": int(open_c)}
    return manifest, rows_by_book


# ───────────────────────────── checks ─────────────────────────────

def _check(key: str, label: str, ok: bool, detail: str, severity: str = "fail") -> dict:
    return {"key": key, "label": label, "status": "pass" if ok else severity, "detail": detail}


def _non_finite(obj, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(obj, float) and not math.isfinite(obj):
        out.append(path or "(root)")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out += _non_finite(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _non_finite(v, f"{path}[{i}]")
    return out


def checks(session: Session, report_type: str, payload: dict, manifest: dict, rows_by_book: dict,
           translation=None, value_weights: Optional[dict] = None) -> tuple[list[dict], dict]:
    """(checks, output figures)."""
    out: list[dict] = []
    bad = _non_finite(payload)
    out.append(_check("finite", "Every number is finite", not bad,
                      "no NaN or infinite values" if not bad else f"{len(bad)} non-finite value(s), e.g. {', '.join(bad[:3])}"))
    figures: dict = {}
    if report_type in LOCATED:
        vertical, lk, idk, vk, nk, tk, sk = LOCATED[report_type]
        items = payload.get(lk) or []
        roll = payload.get("rollup") or {}
        rows = rows_by_book[_VERTICAL_BOOK[vertical]]
        in_ids = {r["entity_id"] for r in rows}
        out_ids = {str(i.get(idk)) for i in items}
        elims = ((payload.get("_fx") or {}).get("eliminations") or [])
        gone = {str(e["asset_id"]) for e in elims if (e.get("share_eliminated") or 0) >= 1}
        missing, stranger = in_ids - out_ids - gone, out_ids - in_ids
        out.append(_check("identity", "Every asset in scope is in the output", not missing and not stranger,
                          f"{len(out_ids)} in the output, {len(gone)} eliminated as group-internal, of {len(in_ids)} in scope"
                          + (f"; {len(missing)} missing" if missing else "") + (f"; {len(stranger)} not in the book" if stranger else "")))
        listed = sum(float(i.get(vk) or 0) for i in items)
        total = float(roll.get(tk) or 0)
        tol = max(1.0, 0.5 * len(items))                      # each listed value is rounded to the unit
        out.append(_check("totals", "The listed values add up to the total", abs(listed - total) <= tol,
                          f"listed {listed:,.0f} vs reported total {total:,.0f}"))
        plain = (translation is None or translation.identity()) and not value_weights and not elims
        if plain:
            given = sum(_value_of(r) for r in rows)
            out.append(_check("input_tie", "The total equals the input", abs(given - total) <= max(1.0, 0.5 * len(rows)),
                              f"input {given:,.0f} EUR vs output {total:,.0f} EUR"))
        else:
            out.append({"key": "input_tie", "label": "The total equals the input", "status": "pass",
                        "detail": "translated / consolidated / eliminated: the per-entity translation table (with the "
                                  "eliminations) is the tie from the input to this total"})
        n, scored = int(roll.get(nk) or len(items)), int(roll.get(sk) or 0)
        out.append(_check("scored", "Every asset is scored", scored >= n, f"{scored} of {n} scored", "warn"))
        figures = {"n_assets": n, "n_scored": scored, "total": total,
                   "currency": (payload.get("_fx") or {}).get("presentation_currency", "EUR")}
    reg = payload.get("_regulation")
    if reg:
        if reg["status"] == "current":
            out.append(_check("regulation", "Prepared under the version in force", True, f"{reg['label']}"
                              + (f", as amended ({len(reg['amended_by'])} amending act(s))" if reg["amended_by"] else "")))
        else:
            rep = "; ".join(f"{r['title']} ({r['celex']}, in force {r['since']})" for r in reg["replaced_by"][:2])
            detail = (f"the act ended before this period; a later version governs it — {rep or 'see the register'}"
                      if reg["status"] == "superseded" else
                      f"an act that repeals it in whole or in part is in force for this period — {rep}; review which provisions apply")
            out.append(_check("regulation", "Prepared under the version in force", False, detail, "warn"))
    # every specification governing the filing (a filing frozen before _specs existed has its one _spec)
    for spec in ((payload.get("_specs") or {}).values() if payload.get("_specs") else [payload.get("_spec")]):
        if not spec:
            continue
        if not spec.get("version"):
            out.append(_check("specification", "Built to a signed-off template specification", False, spec.get("note", ""), "warn"))
        else:
            who = " and ".join(spec.get("needs") or [])
            out.append(_check("specification", "Built to a signed-off template specification", bool(spec.get("approved")),
                              f"{spec['act']} — specification {spec['version']}"
                              + ("" if not spec.get("approved") else
                                 "; signed off by one person (declared sole reviewer), not a four-eyes review"
                                 if spec.get("one_person") else "; signed off by two people")
                              + ("" if spec.get("approved") else f"; still needs the {who} sign-off"), "warn"))
    nd = manifest.get("open_differences") or 0
    out.append(_check("differences", "Your values and ours agree, or were decided", nd == 0,
                      f"{nd} difference(s) between your values and ours not yet decided (Your data → Your value vs ours)"
                      if nd else "none open", "warn"))
    from services.data.feeds import basis_freshness_at
    stale = sorted(k for k, v in basis_freshness_at(session).items() if v in ("overdue", "failed"))
    out.append(_check("feeds", "The hazard feeds are current", not stale,
                      f"overdue or failed: {', '.join(stale)}" if stale else "all current or not tracked", "warn"))
    return out, figures


# ───────────────────────────── the run ─────────────────────────────

def record(session: Session, org_id: str, report_type: str, actor_user_id: Optional[str], *, basis: dict, payload: dict,
           entity_ids: Optional[list] = None, value_weights: Optional[dict] = None, translation=None,
           purpose: str = "filing_freeze", view: str = "joint", observed: Optional[tuple] = None) -> dict:
    """Check the output against its input; refuse (RunCheckError) on an integrity failure, else record the run.
    observed = (manifest, rows) read in the same view as the output (views.in_view) — else read now, from the book."""
    manifest, rows = observed or inputs(session, org_id, report_type, entity_ids)
    cks, figures = checks(session, report_type, payload, manifest, rows, translation, value_weights)
    if any(c["status"] == "fail" for c in cks):
        raise RunCheckError(cks)
    status = "warn" if any(c["status"] == "warn" for c in cks) else "pass"
    row = session.execute(text("""
        INSERT INTO engine_runs (org_id, report_type, purpose, entity_ids, view, basis, inputs, inputs_sha256, outputs,
                                 checks, status, created_by)
        VALUES (CAST(:o AS uuid), :t, :p, CAST(:e AS jsonb), :v, CAST(:b AS jsonb), CAST(:i AS jsonb), :h,
                CAST(:out AS jsonb), CAST(:c AS jsonb), :s, CAST(:u AS uuid))
        RETURNING run_id::text, created_at
    """), {"o": org_id, "t": report_type, "p": purpose, "e": json.dumps(entity_ids), "v": view,
           "b": _canonical(basis), "i": _canonical(manifest), "h": _sha(manifest), "out": _canonical(figures),
           "c": _canonical(cks), "s": status, "u": actor_user_id}).mappings().first()
    return {"run_id": row["run_id"], "created_at": row["created_at"].isoformat(), "status": status, "checks": cks,
            "inputs": manifest, "inputs_sha256": _sha(manifest), "outputs": figures, "view": view}


def get_run(session: Session, org_id: str, run_id: str) -> Optional[dict]:
    r = session.execute(text("""
        SELECT run_id::text, report_type, purpose, entity_ids, view, basis, inputs, inputs_sha256, outputs, checks, status,
               created_at FROM engine_runs WHERE run_id = CAST(:r AS uuid) AND org_id = CAST(:o AS uuid)
    """), {"r": run_id, "o": org_id}).mappings().first()
    return {**dict(r), "created_at": r["created_at"].isoformat()} if r else None
