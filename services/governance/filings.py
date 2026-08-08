"""Regulatory filing lifecycle — the reporting cockpit's engine.

A filing is one regulatory submission (a framework, for a reference period, for an entity). It moves
through a controlled lifecycle, each step logged append-only:

    generate → draft
    submit_for_review → in_review     (raises a 4-eyes approval request)
    approve  → approved               (a *different* user clears the approval; wired via approvals router)
    return   → returned / reject → rejected
    attest   → attested               (a named accountable person certifies the frozen numbers)
    submit   → submitted              (transmitted to the regulator, with a reference)
    accept   → accepted               (regulator acknowledgement)
    supersede→ superseded             (a restatement replaces it)

The frozen numbers behind a filing are a `report_snapshots` row (immutable, hashed, versioned) — this
service never re-implements freezing; it wraps `report_snapshots.create_snapshot`. Honesty carries through
untouched: a euro is firm only where the chain is validated, "—" otherwise, and freezing launders nothing.

Obligations are the filing calendar: what is due, for which entity, by when. They are derived live from the
frameworks that apply to the org's sector, so the calendar is never stale.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.report_snapshots import create_snapshot, get_snapshot, _BUILDERS

# framework (== report_snapshots report_type) -> filing metadata.
# `due` is (month, day) in the year AFTER period_end — the statutory filing deadline.
FRAMEWORKS = {
    "bank_tcfd": {"label": "TCFD · EU-Taxonomy disclosure", "sectors": ("bank",),
                  "frequency": "annual", "due": (4, 30),
                  "regulator": "National competent authority / EBA", "basis": "CSRD Art. 8 · TCFD"},
    "bank_p3esg": {"label": "Pillar 3 ESG risk disclosures", "sectors": ("bank",),
                   "frequency": "annual", "due": (3, 31),
                   "regulator": "National competent authority / EBA", "basis": "CRR Art. 449a · ITS (EU) 2022/2453"},
    "sfdr_pai": {"label": "SFDR Principal Adverse Impacts statement", "sectors": ("asset_manager",),
                 "frequency": "annual", "due": (6, 30),
                 "regulator": "National competent authority (SFDR)", "basis": "SFDR RTS 2022/1288 Annex I"},
    # ── agriculture (manufacturer) frameworks — builders already registered in report_snapshots._BUILDERS ──
    "csrd_e1": {"label": "CSRD · ESRS E1 physical-risk report", "sectors": ("manufacturer",),
                "frequency": "annual", "due": (3, 31),
                "regulator": "National competent authority (CSRD)", "basis": "ESRS E1"},
    "esrs_pack": {"label": "ESRS Climate & Nature pack (E1 · E3 · E4)", "sectors": ("manufacturer",),
                  "frequency": "annual", "due": (3, 31),
                  "regulator": "National competent authority (CSRD)", "basis": "ESRS E1 · E3 · E4"},
    "reit_tcfd": {"label": "TCFD · EU-Taxonomy disclosure (property book)", "sectors": ("reit",),
                  "frequency": "annual", "due": (4, 30),
                  "regulator": "National competent authority / EBA", "basis": "CSRD Art. 8 · TCFD"},
    "insurer_climate": {"label": "Climate / NatCat exposure disclosure", "sectors": ("insurer",),
                        "frequency": "annual", "due": (4, 30),
                        "regulator": "National competent authority / EIOPA", "basis": "Solvency II · IFRS S2"},
}

# machine-readable export formats available per framework (rendered from the FROZEN snapshot — see
# services/governance/filing_export.py). json is the universal record; xlsx/xbrl where a renderer exists.
EXPORT_FORMATS = {
    "bank_tcfd": ("json", "xlsx", "xbrl"),
    "bank_p3esg": ("json", "xlsx"),
    "sfdr_pai":  ("json", "xlsx", "xbrl"),
    "reit_tcfd": ("json", "xlsx"),
    "insurer_climate": ("json", "xlsx"),
    "csrd_e1":   ("json",),
    "esrs_pack": ("json",),
}

# lifecycle: action -> (allowed from-states, resulting to-state)
_TRANSITIONS = {
    "submit_for_review": ({"draft", "returned"}, "in_review"),
    "approve":           ({"in_review"},         "approved"),
    "return":            ({"in_review"},         "returned"),
    "reject":            ({"in_review"},         "rejected"),
    "attest":            ({"approved"},          "attested"),
    "submit":            ({"attested"},          "submitted"),
    "accept":            ({"submitted"},         "accepted"),
    "supersede":         ({"submitted", "accepted", "rejected"}, "superseded"),
}


class FilingError(ValueError):
    """A lifecycle rule was violated (bad transition, missing filing, duplicate slot)."""


# ── framework catalog ──────────────────────────────────────────────────

# Frameworks whose builder genuinely HONOURS entity scope — the located FIN books, where each asset carries a
# clear reporting-entity + value, so a group consolidates correctly (ownership-weighted). The others do NOT:
# SFDR consolidates fund-side (the funds workspace — per-fund statements + the entity-level across-all-funds
# aggregate), and agri CSRD/ESRS flows through an org/product COGS engine with no per-legal-entity attribution.
# Offering a per-entity scope for those would silently mislabel a whole-org number, so generate_filing refuses it.
_ENTITY_SCOPED = {"bank_tcfd", "bank_p3esg", "reit_tcfd", "insurer_climate"}


def available_frameworks(org_type: str) -> list[dict]:
    """Frameworks that apply to this org-type sector, each with its cadence and statutory deadline shape."""
    out = []
    for key, f in FRAMEWORKS.items():
        if org_type in f["sectors"] and key in _BUILDERS:
            out.append({"framework": key, "label": f["label"], "frequency": f["frequency"],
                        "regulator": f["regulator"], "basis": f["basis"],
                        "entity_scoped": key in _ENTITY_SCOPED})
    return out


_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def form_view(session: Session, org_id: str, filing_id: str) -> dict | None:
    """The final form for a filing — the frozen snapshot flattened into labelled datapoints (see
    filing_form.build_form), each with a stable key so a manual override can target it."""
    from services.governance.filing_form import build_form
    from services.governance.reg_reference import reference
    r = session.execute(text("""
        SELECT rf.framework, rf.status, rf.period_label, s.payload, s.version
        FROM regulatory_filing rf
        LEFT JOIN report_snapshots s ON s.snapshot_id = rf.snapshot_id
        WHERE rf.org_id = :o AND rf.filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        return None
    groups = build_form(r["framework"], r["payload"] or {})
    # merge the audited manual-override layer over the immutable snapshot: an APPROVED override replaces the
    # cell (flagged manual, original preserved); a PENDING one is surfaced awaiting 4-eyes.
    from services.governance.filing_overrides import overrides_for_filing
    ov = overrides_for_filing(session, org_id, filing_id)
    n_manual = n_pending = 0
    for g in groups:
        for d in g["datapoints"]:
            o = ov.get(d["key"])
            if not o:
                continue
            if o["status"] == "approved":
                d["value"] = o["proposed_value"]
                d["manual"] = True
                d["original_value"] = o["original_value"]
                d["override"] = {"reason": o["reason"], "by": o["proposed_by"], "at": o["proposed_at"],
                                 "approved_by": o["decided_by"], "approved_at": o["decided_at"]}
                n_manual += 1
            elif o["status"] == "pending":
                d["pending"] = {"value": o["proposed_value"], "reason": o["reason"], "by": o["proposed_by"]}
                n_pending += 1
    # the official regulator-form layout (SFDR Annex I Table 1, Taxonomy Art.8 GAR, ESRS E1 …) built from the
    # SAME merged datapoints, so the official form and the datapoint list stay in lock-step (overrides included).
    from services.governance.filing_annex import build_annex
    dps_by_key = {d["key"]: d for g in groups for d in g["datapoints"]}
    # the raw frozen payload is passed too — some official templates (e.g. EBA Pillar 3 Template 5) are
    # structured GRIDS computed from the per-asset book, not flat datapoints, and are rebuilt at read time.
    annex = build_annex(r["framework"], dps_by_key, groups, payload=r["payload"] or {})
    return {"framework": r["framework"], "label": FRAMEWORKS.get(r["framework"], {}).get("label", r["framework"]),
            "period_label": r["period_label"], "status": r["status"], "snapshot_version": r["version"],
            "official_form_url": (reference(r["framework"]) or {}).get("form_url"),
            "n_manual": n_manual, "n_pending": n_pending, "groups": groups, "annex": annex}


def reporting_requirements(session: Session, org_id: str, org_type: str) -> list[dict]:
    """Every mandatory reporting obligation for the org: what the regulation is (name, authority, summary,
    official link + form), how often + to which regulator + by when, what data to supply, when it was last
    filed, and the full list of prior filings (for access to previously submitted reports)."""
    from services.governance.reg_reference import reference
    from services.governance.filing_coverage import coverage as _coverage
    out = []
    for f in available_frameworks(org_type):
        fk = f["framework"]
        ref = reference(fk) or {}
        spec = FRAMEWORKS[fk]
        due_m, due_d = spec.get("due", (0, 0))
        rows = session.execute(text("""
            SELECT rf.filing_id::text AS filing_id, rf.period_label, rf.status, rf.submission_ref,
                   rf.created_at, rf.updated_at, s.version AS snapshot_version,
                   rf.entity_id::text AS entity_id, re.name AS entity_name
            FROM regulatory_filing rf
            LEFT JOIN report_snapshots s ON s.snapshot_id = rf.snapshot_id
            LEFT JOIN reporting_entities re ON re.entity_id = rf.entity_id
            WHERE rf.org_id = :o AND rf.framework = :fk
            ORDER BY rf.period_end DESC, rf.created_at DESC
        """), {"o": org_id, "fk": fk}).mappings().all()
        filings = [{"filing_id": r["filing_id"], "period_label": r["period_label"], "status": r["status"],
                    "submission_ref": r["submission_ref"], "snapshot_version": r["snapshot_version"],
                    "entity_name": r["entity_name"], "filed_at": r["updated_at"].isoformat() if r["updated_at"] else None}
                   for r in rows]
        # "last filed" = the most-recent filing that actually reached the regulator — it carries a submission
        # ref (or is accepted), even if later superseded by a restatement.
        last = next((x for x in filings if x["submission_ref"] or x["status"] in ("submitted", "accepted")), None)
        out.append({
            **f, **ref,
            "due_label": f"{spec['frequency']} · by {due_d} {_MONTHS[due_m]}" if due_m else spec["frequency"],
            "n_filings": len(filings), "last_filed": last, "filings": filings,
            "coverage": _coverage(fk),
        })
    return out


def _due_date(framework: str, period_end: date) -> date:
    m, d = FRAMEWORKS[framework]["due"]
    return date(period_end.year + 1, m, d)


def _period_label(period_end: date) -> str:
    return f"FY{period_end.year}"


# ── obligations calendar (derived live, upserted so history persists) ───

def ensure_obligations(session: Session, org_id: str, org_type: str) -> None:
    """Make sure an obligation row exists for every framework applicable to this org, for the current
    reference period (last completed year-end). Idempotent — safe to call on every calendar read."""
    period_end = date(date.today().year - 1, 12, 31)
    for f in available_frameworks(org_type):
        fk = f["framework"]
        # entity_id is NULL for org-level obligations; a UNIQUE(...) treats NULLs as distinct, so we can't
        # rely on ON CONFLICT here — check existence explicitly (org-level obligation, entity_id IS NULL).
        exists = session.execute(text("""
            SELECT 1 FROM regulatory_obligation
            WHERE org_id = :o AND framework = :fk AND period_end = :pe AND entity_id IS NULL
        """), {"o": org_id, "fk": fk, "pe": period_end}).first()
        if exists:
            continue
        session.execute(text("""
            INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency)
            VALUES (:o, :fk, :pe, :pl, :due, :freq)
        """), {"o": org_id, "fk": fk, "pe": period_end, "pl": _period_label(period_end),
               "due": _due_date(fk, period_end), "freq": FRAMEWORKS[fk]["frequency"]})


def list_obligations(session: Session, org_id: str, org_type: str) -> list[dict]:
    """The filing calendar — each obligation with the live filing that satisfies it (if any) and its status."""
    ensure_obligations(session, org_id, org_type)
    rows = session.execute(text("""
        SELECT ob.obligation_id, ob.framework, ob.period_end, ob.period_label, ob.due_date, ob.frequency,
               f.filing_id, f.status AS filing_status
        FROM regulatory_obligation ob
        LEFT JOIN LATERAL (
            SELECT filing_id, status FROM regulatory_filing rf
            WHERE rf.org_id = ob.org_id AND rf.framework = ob.framework
              AND rf.period_end = ob.period_end AND rf.status <> 'superseded'
            ORDER BY rf.created_at DESC LIMIT 1
        ) f ON TRUE
        WHERE ob.org_id = :o
        ORDER BY ob.due_date
    """), {"o": org_id}).mappings().all()
    today = date.today()
    out = []
    for r in rows:
        status = r["filing_status"] or "not_started"
        done = status in ("submitted", "accepted")
        days_left = (r["due_date"] - today).days
        out.append({
            "obligation_id": str(r["obligation_id"]), "framework": r["framework"],
            "label": FRAMEWORKS.get(r["framework"], {}).get("label", r["framework"]),
            "period_end": r["period_end"].isoformat(), "period_label": r["period_label"],
            "due_date": r["due_date"].isoformat(), "frequency": r["frequency"],
            "filing_id": str(r["filing_id"]) if r["filing_id"] else None,
            "filing_status": status, "days_to_due": days_left,
            "overdue": (not done and days_left < 0),
        })
    return out


# ── filing register ────────────────────────────────────────────────────

def _row_to_summary(r) -> dict:
    return {
        "filing_id": str(r["filing_id"]), "framework": r["framework"],
        "label": FRAMEWORKS.get(r["framework"], {}).get("label", r["framework"]),
        "period_end": r["period_end"].isoformat(), "period_label": r["period_label"],
        "status": r["status"], "snapshot_id": str(r["snapshot_id"]) if r["snapshot_id"] else None,
        "snapshot_version": r.get("snapshot_version"),
        "submission_ref": r["submission_ref"],
        "superseded_by": str(r["superseded_by"]) if r["superseded_by"] else None,
        "note": r["note"], "created_by": r.get("created_by_name"),
        "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat(),
        # reporting scope: NULL entity = whole org; a group kind = a consolidated filing
        "entity_id": str(r["entity_id"]) if r.get("entity_id") else None,
        "entity_name": r.get("entity_name"),
        "scope": ("consolidated" if r.get("entity_kind") == "group" else "entity") if r.get("entity_id") else "organisation",
    }


def list_filings(session: Session, org_id: str) -> list[dict]:
    """Every filing for the org — the register, newest first."""
    rows = session.execute(text("""
        SELECT rf.filing_id, rf.framework, rf.period_end, rf.period_label, rf.status, rf.snapshot_id,
               rf.submission_ref, rf.superseded_by, rf.note, rf.created_at, rf.updated_at,
               rs.version AS snapshot_version, u.full_name AS created_by_name,
               rf.entity_id, re.name AS entity_name, re.kind AS entity_kind
        FROM regulatory_filing rf
        LEFT JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        LEFT JOIN users u ON u.user_id = rf.created_by
        LEFT JOIN reporting_entities re ON re.entity_id = rf.entity_id
        WHERE rf.org_id = :o
        ORDER BY rf.created_at DESC
    """), {"o": org_id}).mappings().all()
    return [_row_to_summary(r) for r in rows]


def get_filing(session: Session, org_id: str, filing_id: str, with_payload: bool = True) -> dict | None:
    """One filing with its full lifecycle history and (optionally) the frozen report payload."""
    r = session.execute(text("""
        SELECT rf.filing_id, rf.framework, rf.period_end, rf.period_label, rf.status, rf.snapshot_id,
               rf.approval_request_id, rf.submission_ref, rf.superseded_by, rf.note,
               rf.created_at, rf.updated_at, rs.version AS snapshot_version, u.full_name AS created_by_name,
               rf.entity_id, re.name AS entity_name, re.kind AS entity_kind
        FROM regulatory_filing rf
        LEFT JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        LEFT JOIN users u ON u.user_id = rf.created_by
        LEFT JOIN reporting_entities re ON re.entity_id = rf.entity_id
        WHERE rf.org_id = :o AND rf.filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        return None
    out = _row_to_summary(r)
    out["approval_request_id"] = str(r["approval_request_id"]) if r["approval_request_id"] else None
    out["regulator"] = FRAMEWORKS.get(r["framework"], {}).get("regulator")
    out["basis"] = FRAMEWORKS.get(r["framework"], {}).get("basis")

    events = session.execute(text("""
        SELECT e.from_status, e.to_status, e.action, e.detail, e.created_at, u.full_name AS actor_name, u.email AS actor_email
        FROM regulatory_filing_event e
        LEFT JOIN users u ON u.user_id = e.actor_user_id
        WHERE e.filing_id = :f
        ORDER BY e.created_at, e.event_id
    """), {"f": filing_id}).mappings().all()
    out["events"] = [{"from": e["from_status"], "to": e["to_status"], "action": e["action"],
                      "detail": e["detail"], "at": e["created_at"].isoformat(),
                      "actor": e["actor_name"], "actor_email": e["actor_email"]} for e in events]

    # machine-readable exports are only meaningful once the report is frozen
    out["export_formats"] = list(EXPORT_FORMATS.get(r["framework"], ("json",))) if r["snapshot_id"] else []

    if with_payload and r["snapshot_id"]:
        snap = get_snapshot(session, org_id, str(r["snapshot_id"]))
        if snap:
            out["snapshot"] = {"version": snap["version"], "reporting_basis": snap["reporting_basis"],
                               "payload": snap["payload"], "payload_sha256": snap["payload_sha256"],
                               "hash_verified": snap["hash_verified"], "engine_versions": snap["engine_versions"],
                               "created_at": snap["created_at"]}
    return out


def _log_event(session: Session, filing_id: str, from_status: str | None, to_status: str,
               action: str, actor_user_id: str | None, detail: dict | None = None) -> None:
    session.execute(text("""
        INSERT INTO regulatory_filing_event (filing_id, from_status, to_status, action, actor_user_id, detail)
        VALUES (:f, :fs, :ts, :a, :u, CAST(:d AS jsonb))
    """), {"f": filing_id, "fs": from_status, "ts": to_status, "a": action,
           "u": actor_user_id, "d": json.dumps(detail or {}, default=str)})


# ── lifecycle operations ────────────────────────────────────────────────

def preflight(session: Session, org_id: str, org_type: str, framework: str) -> dict:
    """The confirm-data step before freezing: shows the basis, the data coverage, the headline figures and
    any gaps, so a preparer confirms 'this is my data' before a filing is frozen. Computes but freezes nothing."""
    if framework not in FRAMEWORKS or framework not in _BUILDERS:
        raise FilingError(f"unknown framework '{framework}'")
    if org_type not in FRAMEWORKS[framework]["sectors"]:
        raise FilingError(f"framework '{framework}' does not apply to a {org_type}")
    period_end = date(date.today().year - 1, 12, 31)
    existing = session.execute(text("""
        SELECT status FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end = :pe AND status <> 'superseded'
    """), {"o": org_id, "fk": framework, "pe": period_end}).scalar()
    from services.governance.reporting_settings import get_settings
    basis = get_settings(session, org_id)
    summary = _preflight_summary(session, org_id, framework, basis)
    return {"framework": framework, "label": FRAMEWORKS[framework]["label"],
            "period_label": _period_label(period_end), "basis": basis,
            "can_generate": existing is None, "existing_status": existing,
            "entity_scoped": framework in _ENTITY_SCOPED, **summary}


def _preflight_summary(session: Session, org_id: str, framework: str, basis: dict) -> dict:
    """Live coverage + headline for the confirm-data step. Honest gaps, no freeze."""
    gaps: list[str] = []
    if framework in ("bank_tcfd", "bank_p3esg"):
        from api.routers.bank import build_disclosure_snapshot
        snap = build_disclosure_snapshot(session, org_id, basis["scenario"], basis["horizon"])
        r = snap["rollup"]
        n_total, n_done = r.get("n_assets", 0), r.get("n_scored", 0)
        if n_total and n_done < n_total:
            gaps.append(f"{n_total - n_done} of {n_total} assets not yet scored — they'd be excluded from exposure")
        return {"coverage": {"label": "assets scored", "done": n_done, "total": n_total,
                             "pct": round(100 * n_done / n_total, 1) if n_total else 0},
                "total_value_eur": r.get("total_value_eur"), "value_at_risk_eur": r.get("value_at_risk_eur"),
                "noun": "assets", "gaps": gaps}
    if framework == "sfdr_pai":
        from ml.regulatory.sfdr_pai import entity_pai_statement
        st = entity_pai_statement(session, org_id)
        if st.get("error"):
            return {"coverage": {"label": "positions", "done": 0, "total": 0, "pct": 0},
                    "total_value_eur": None, "noun": "positions", "gaps": [st["error"]]}
        cs, ent, fr = st["coverage_summary"], st["entity"], st.get("filing_readiness", {})
        if not fr.get("ready_to_file"):
            gaps.append("Manager identity/narratives incomplete: " + ", ".join(fr.get("missing", [])))
        mand, done = cs.get("mandatory_indicators", 0), cs.get("computed", 0)
        if mand and done < mand:
            gaps.append(f"{done}/{mand} mandatory PAI indicators computed — the rest await issuer input")
        return {"coverage": {"label": "PAI indicators computed", "done": done, "total": mand,
                             "pct": round(100 * done / mand, 1) if mand else 0},
                "total_value_eur": ent.get("total_value_eur"), "value_at_risk_eur": None,
                "noun": "positions", "positions": ent.get("positions"), "gaps": gaps}
    if framework == "reit_tcfd":
        from api.routers.realestate import build_disclosure_snapshot
        r = build_disclosure_snapshot(session, org_id, basis["scenario"], basis["horizon"])["rollup"]
        n_total, n_done = r.get("n_properties", 0), r.get("n_scored", 0)
        if n_total and n_done < n_total:
            gaps.append(f"{n_total - n_done} of {n_total} properties not yet scored — excluded from exposure")
        return {"coverage": {"label": "properties scored", "done": n_done, "total": n_total,
                             "pct": round(100 * n_done / n_total, 1) if n_total else 0},
                "total_value_eur": r.get("total_value_eur"), "value_at_risk_eur": None,
                "noun": "properties", "gaps": gaps}
    if framework == "insurer_climate":
        from api.routers.insurance import build_disclosure_snapshot
        r = build_disclosure_snapshot(session, org_id, basis["scenario"], basis["horizon"])["rollup"]
        n_total, n_done = r.get("n_policies", 0), r.get("n_priced", 0)
        if n_total and n_done < n_total:
            gaps.append(f"{n_total - n_done} of {n_total} policies not yet priced")
        return {"coverage": {"label": "policies priced", "done": n_done, "total": n_total,
                             "pct": round(100 * n_done / n_total, 1) if n_total else 0},
                "total_value_eur": r.get("total_sum_insured_eur"), "value_at_risk_eur": None,
                "noun": "policies", "gaps": gaps}
    # agri (csrd_e1 / esrs_pack) & any other framework — the report assembles from the org's own footprint;
    # no single coverage ratio, so present it cleanly (basis + confirm) rather than a fake 0%.
    return {"coverage": None, "total_value_eur": None, "noun": "sites & sourcing plots", "gaps": []}


def generate_filing(session: Session, org_id: str, org_type: str, framework: str,
                    actor_user_id: str, note: str | None = None, confirmed: bool = False,
                    entity_id: str | None = None) -> dict:
    """Freeze the report at the org's current basis and open a DRAFT filing over it. One live filing per
    (framework, period, entity) — regenerating while one is live is refused (supersede it first).
    entity_id scopes the book: NULL = the whole org; a leaf entity = its own book (100%); a parent/group =
    its whole subtree CONSOLIDATED (proportional/equity lines value-weighted by ownership)."""
    if framework not in FRAMEWORKS or framework not in _BUILDERS:
        raise FilingError(f"unknown framework '{framework}'")
    if org_type not in FRAMEWORKS[framework]["sectors"]:
        raise FilingError(f"framework '{framework}' does not apply to a {org_type}")
    # the confirm-data step is mandatory — a filing is never frozen without an explicit human confirmation
    if not confirmed:
        raise FilingError("data must be confirmed (via the pre-filing check) before a filing is frozen")

    # resolve the reporting scope — refuse a per-entity/consolidated scope for a framework that can't honour it
    # (would mislabel a whole-org number). SFDR consolidates by fund; agri CSRD has no per-legal-entity split.
    if entity_id is not None and framework not in _ENTITY_SCOPED:
        raise FilingError(f"{FRAMEWORKS[framework]['label']} files at whole-organisation level — a per-entity or "
                          f"consolidated scope isn't available for it (SFDR consolidates by fund in the Funds "
                          f"workspace; agri CSRD/ESRS has no per-legal-entity COGS attribution).")
    entity_ids = value_weights = None
    if entity_id is not None:
        from services.governance import entities as _E
        ent = _E.get_entity(session, org_id, entity_id)
        if not ent:
            raise FilingError("reporting entity not found")
        entity_ids = _E.subtree_ids(session, org_id, entity_id)
        if len(entity_ids) > 1:   # a parent/group — consolidate the subtree, ownership-weighted
            value_weights = _E.ownership_weights(session, org_id)

    period_end = date(date.today().year - 1, 12, 31)
    existing = session.execute(text("""
        SELECT filing_id, status FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end = :pe AND status <> 'superseded'
              AND entity_id IS NOT DISTINCT FROM :ent
    """), {"o": org_id, "fk": framework, "pe": period_end, "ent": entity_id}).mappings().first()
    if existing:
        raise FilingError(f"a live {framework} filing for {_period_label(period_end)} already exists "
                          f"(status {existing['status']}); supersede it to restate.")

    snap = create_snapshot(session, org_id, framework, actor_user_id, note=note,
                           entity_ids=entity_ids, value_weights=value_weights)
    row = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, note, created_by, entity_id)
        VALUES (:o, :fk, :pe, :pl, 'draft', :snap, :note, :u, :ent)
        RETURNING filing_id
    """), {"o": org_id, "fk": framework, "pe": period_end, "pl": _period_label(period_end),
           "snap": snap["snapshot_id"], "note": note, "u": actor_user_id, "ent": entity_id}).mappings().first()
    fid = str(row["filing_id"])
    _log_event(session, fid, None, "draft", "generate", actor_user_id,
               {"snapshot_id": snap["snapshot_id"], "version": snap["version"],
                "payload_sha256": snap["payload_sha256"], "data_confirmed": bool(confirmed)})
    return get_filing(session, org_id, fid, with_payload=False)


def _load(session: Session, org_id: str, filing_id: str) -> dict:
    r = session.execute(text("""
        SELECT filing_id, status, framework, period_label, snapshot_id, approval_request_id
        FROM regulatory_filing WHERE org_id = :o AND filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        raise FilingError("filing not found")
    return dict(r)


def _apply_transition(session: Session, org_id: str, filing_id: str, action: str,
                     actor_user_id: str, detail: dict | None = None,
                     extra_sets: dict | None = None) -> dict:
    allowed_from, to_status = _TRANSITIONS[action]
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in allowed_from:
        raise FilingError(f"cannot {action} a filing that is '{cur['status']}' "
                          f"(needs one of {sorted(allowed_from)})")
    sets = {"status": to_status}
    if extra_sets:
        sets.update(extra_sets)
    set_sql = ", ".join(f"{k} = :{k}" for k in sets)
    params = {**sets, "f": filing_id}
    session.execute(text(f"UPDATE regulatory_filing SET {set_sql} WHERE filing_id = :f"), params)
    _log_event(session, filing_id, cur["status"], to_status, action, actor_user_id, detail)
    return get_filing(session, org_id, filing_id, with_payload=False)


def submit_for_review(session: Session, org_id: str, filing_id: str, actor_user_id: str) -> dict:
    """Move a draft into review and raise a 4-eyes approval request. A *different* user must approve it.
    Refuses if the filing has an open BLOCKING validation issue — a broken filing never reaches a reviewer."""
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in ("draft", "returned"):
        raise FilingError(f"cannot submit a filing that is '{cur['status']}' for review")
    from services.governance.filing_validation import validate_filing, blocking_messages
    vr = validate_filing(session, org_id, filing_id)
    if not vr["passed"]:
        raise FilingError("cannot submit for approval — resolve the blocking validation issue(s): "
                          + "; ".join(blocking_messages(vr)))
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o, 'filing.approve', :ti, CAST(:p AS jsonb), :m)
        RETURNING request_id
    """), {"o": org_id, "ti": f"Approve {FRAMEWORKS[cur['framework']]['label']} · {cur['period_label']}",
           "p": json.dumps({"filing_id": filing_id, "framework": cur["framework"]}),
           "m": actor_user_id}).scalar()
    return _apply_transition(session, org_id, filing_id, "submit_for_review", actor_user_id,
                             detail={"approval_request_id": str(rid),
                                     "validation": {"blocking": vr["blocking"], "warnings": vr["warnings"],
                                                    "checks": vr["checks"]}},
                             extra_sets={"approval_request_id": rid})


def mark_approved(session: Session, org_id: str, filing_id: str, checker_user_id: str,
                  reason: str | None = None) -> dict:
    """Called by the approvals router when a filing.approve request is approved (checker ≠ maker enforced there)."""
    return _apply_transition(session, org_id, filing_id, "approve", checker_user_id,
                             detail={"reason": reason})


def mark_returned(session: Session, org_id: str, filing_id: str, checker_user_id: str,
                  reason: str | None = None, rejected: bool = False) -> dict:
    """Approval sent back (returned→draft) or rejected outright. Both re-open the draft for the preparer
    unless explicitly rejected (terminal-ish; a new filing supersedes)."""
    action = "reject" if rejected else "return"
    return _apply_transition(session, org_id, filing_id, action, checker_user_id, detail={"reason": reason})


def attest(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           attestor_name: str, statement: str) -> dict:
    """A named accountable person certifies the frozen numbers. Distinct from the 4-eyes approval:
    approval is process control; attestation is personal accountability for the filing."""
    if not attestor_name or not statement:
        raise FilingError("attestation needs the accountable person's name and a certification statement")
    return _apply_transition(session, org_id, filing_id, "attest", actor_user_id,
                             detail={"attestor_name": attestor_name, "statement": statement})


def submit(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           submission_ref: str | None = None) -> dict:
    """Transmit to the regulator. Records the submission reference; the record freezes here (guard trigger)."""
    return _apply_transition(session, org_id, filing_id, "submit", actor_user_id,
                             detail={"submission_ref": submission_ref},
                             extra_sets={"submission_ref": submission_ref})


def accept(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           ack_ref: str | None = None) -> dict:
    """Record the regulator's acknowledgement — the filing is accepted."""
    return _apply_transition(session, org_id, filing_id, "accept", actor_user_id,
                             detail={"ack_ref": ack_ref})


def restate_filing(session: Session, org_id: str, filing_id: str, actor_user_id: str, reason: str) -> dict:
    """Restate a filed (submitted/accepted) filing: freeze a fresh snapshot at the current basis into a NEW
    draft, and supersede the old one pointing at the new. Both are preserved — the correction is a new
    version that runs the full lifecycle again, never an edit of the filed record."""
    if not reason:
        raise FilingError("a restatement needs a reason")
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in ("submitted", "accepted"):
        raise FilingError(f"only a filed (submitted/accepted) filing can be restated — this is '{cur['status']}'")

    # period_end of the filing being restated (restatement keeps the same reference period)
    period = session.execute(text(
        "SELECT period_end, period_label FROM regulatory_filing WHERE filing_id = :f"),
        {"f": filing_id}).mappings().first()
    snap = create_snapshot(session, org_id, cur["framework"], actor_user_id,
                           note=f"Restatement of {period['period_label']}: {reason}")
    # supersede the old FIRST so the single-live-slot frees up before the restatement is inserted
    _apply_transition(session, org_id, filing_id, "supersede", actor_user_id, detail={"reason": reason})
    new_fid = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, note, created_by)
        VALUES (:o, :fk, :pe, :pl, 'draft', :snap, :note, :u)
        RETURNING filing_id
    """), {"o": org_id, "fk": cur["framework"], "pe": period["period_end"], "pl": period["period_label"],
           "snap": snap["snapshot_id"], "note": f"Restates {period['period_label']}: {reason}",
           "u": actor_user_id}).scalar()
    _log_event(session, str(new_fid), None, "draft", "generate", actor_user_id,
               {"restates": filing_id, "reason": reason, "snapshot_id": snap["snapshot_id"]})
    # link the superseded old → the restatement (allowed: a superseded row is no longer guard-frozen)
    session.execute(text("UPDATE regulatory_filing SET superseded_by = :n WHERE filing_id = :f"),
                    {"n": new_fid, "f": filing_id})
    return get_filing(session, org_id, str(new_fid), with_payload=False)


def prior_filing_id(session: Session, org_id: str, filing_id: str) -> str | None:
    """The filing this one restates (i.e. the one it superseded), if any — for a variance comparison."""
    r = session.execute(text(
        "SELECT filing_id::text FROM regulatory_filing WHERE org_id = :o AND superseded_by = :f"),
        {"o": org_id, "f": filing_id}).scalar()
    if r:
        return r
    # else: the most recent accepted/submitted filing for the same framework with an EARLIER period
    cur = session.execute(text(
        "SELECT framework, period_end FROM regulatory_filing WHERE filing_id = :f"), {"f": filing_id}).mappings().first()
    if not cur:
        return None
    return session.execute(text("""
        SELECT filing_id::text FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end < :pe AND status IN ('submitted','accepted','superseded')
        ORDER BY period_end DESC, created_at DESC LIMIT 1
    """), {"o": org_id, "fk": cur["framework"], "pe": cur["period_end"]}).scalar()
