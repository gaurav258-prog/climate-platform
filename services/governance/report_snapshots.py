"""Freeze an ESRS/CSRD filing as an immutable, versioned snapshot.

A filed disclosure must be reproducible: the same figures, on the same reporting basis, from the same
golden-source state — even after the live engine has moved on. This service computes the report at the
org's current basis and writes it once into `report_snapshots` (append-only: no update, no delete path).
A correction is a new version, so the history is complete and auditable.

Honesty carries through unchanged: the frozen payload is exactly what the assembler produced — a euro is
a firm figure only where the hazard→yield/asset chain is validated; otherwise exposure is mapped and the €
withheld. Freezing never launders an unvalidated number into a firm one.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.reporting_settings import get_settings


def _canonical(obj) -> str:
    """Deterministic JSON for content-hashing — stable key order + compact separators.
    MUST match the back-fill in migration snapshot_worm_20260731."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(obj) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _git_sha() -> str | None:
    """Short code version, best-effort (None if git is unavailable)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=".", stderr=subprocess.DEVNULL, timeout=3
        ).decode().strip() or None
    except Exception:  # noqa: BLE001
        return None


def _engine_versions(session: Session, org_id: str | None = None) -> dict:
    """The model/data/code versions in force at freeze — so the exact computation is identifiable.
    Includes the org's resolved INTERPRETATION settings (which regulatory interpretation produced the filing),
    so a regulator can see, on the frozen record, e.g. that the PML used a 1-in-200 return period."""
    from services.data.feeds import FEEDS, basis_freshness_at
    from services.intelligence.supply_cogs import IMPACT_VERSION, RANGED_PUBLISH_FLOOR
    fit_versions = sorted(v for v in session.execute(
        text("SELECT DISTINCT fit_version FROM sc_commodity_fit WHERE fit_version IS NOT NULL")
    ).scalars().all())
    versions = {
        "impact_version": IMPACT_VERSION,
        "ranged_floor": RANGED_PUBLISH_FLOOR,
        "ranged_gate_metric": "r2_oos",          # gate is out-of-sample r² (audit F2)
        "fit_versions": fit_versions,
        "feed_maturity": {f["key"]: f.get("maturity") for f in FEEDS},
        "feed_freshness_at_freeze": basis_freshness_at(session),   # audit T4: how current the golden source was
        "code_version": _git_sha(),
    }
    if org_id is not None:
        from services.calc_settings import get_calc_settings
        versions["interpretation_settings"] = get_calc_settings(session, org_id)
    return versions

# report_type -> (human label, builder, applicable org-type sectors). The builder takes
# (session, org_id, scenario, horizon, material); FIN builders ignore the extra basis args.
# builder args are (session, org_id, scenario, horizon, material, entity_ids, value_weights, translation). entity_ids /
# value_weights scope + consolidation-weight the book — supported by the located FIN books (bank/reit/insurer);
# the others (CSRD/ESRS entity-level, SFDR fund-aggregated) ignore them and report whole-org.
_BUILDERS = {
    "csrd_e1": ("CSRD · ESRS E1 physical-risk report",
                lambda s, o, sc, hz, m, ei, vw, tr: _csrd_e1(s, o, sc, hz, m), ("manufacturer",)),
    "esrs_pack": ("ESRS Climate & Nature pack (E1 · E3 · E4)",
                  lambda s, o, sc, hz, m, ei, vw, tr: _esrs_pack(s, o, sc, hz, m), ("manufacturer",)),
    # ── financial-institution filings (frozen through the same WORM/hash/version machinery) ──
    "bank_tcfd": ("TCFD · EU-Taxonomy disclosure (loan book)",
                  lambda s, o, sc, hz, m, ei, vw, tr: _bank_tcfd(s, o, sc, hz, ei, vw, tr), ("bank",)),
    "bank_p3esg": ("Pillar 3 ESG risk disclosures (EBA)",
                   lambda s, o, sc, hz, m, ei, vw, tr: _bank_tcfd(s, o, sc, hz, ei, vw, tr), ("bank",)),
    "sfdr_pai": ("SFDR Principal Adverse Impacts statement (Annex I)",
                 lambda s, o, sc, hz, m, ei, vw, tr: _sfdr_pai(s, o), ("asset_manager",)),
    "assetmgmt_tcfd": ("TCFD · physical-risk & concentration disclosure (holdings book)",
                       lambda s, o, sc, hz, m, ei, vw, tr: _assetmgmt_tcfd(s, o, sc, hz, ei, vw, tr), ("asset_manager",)),
    "reit_tcfd": ("TCFD · EU-Taxonomy disclosure (property book)",
                  lambda s, o, sc, hz, m, ei, vw, tr: _reit_tcfd(s, o, sc, hz, ei, vw, tr), ("reit",)),
    "insurer_climate": ("Climate / NatCat exposure disclosure (underwriting book)",
                        lambda s, o, sc, hz, m, ei, vw, tr: _insurer_climate(s, o, sc, hz, ei, vw, tr), ("insurer",)),
    "reit_taxonomy": ("EU Taxonomy Article 8 KPIs (property book)",
                      lambda s, o, sc, hz, m, ei, vw, tr: _reit_taxonomy(s, o, sc, hz, ei, vw, tr), ("reit",)),
    "insurer_solvency": ("Solvency II · Nat-Cat SCR (S.26.01)",
                         lambda s, o, sc, hz, m, ei, vw, tr: _insurer_solvency(s, o, sc, hz, ei, vw, tr), ("insurer",)),
}


def _csrd_e1(session, org_id, scenario, horizon, material):
    from services.intelligence.csrd_e1 import build_e1_report
    return build_e1_report(session, org_id, scenario=scenario, horizon=horizon, material_threshold=material)


def _esrs_pack(session, org_id, scenario, horizon, material):
    from services.intelligence.esrs_nature import build_esrs_pack
    return build_esrs_pack(session, org_id, scenario=scenario, horizon=horizon, material=material)


def _bank_tcfd(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None):
    from api.routers.bank import build_disclosure_snapshot
    return build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation)


def _sfdr_pai(session, org_id):
    from ml.regulatory.sfdr_pai import entity_pai_statement
    return entity_pai_statement(session, org_id)


def _assetmgmt_tcfd(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None):
    from api.routers.assetmgmt import build_disclosure_snapshot
    return build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation)


def _reit_tcfd(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None):
    from api.routers.realestate import build_disclosure_snapshot
    return build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation)


def _insurer_climate(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None):
    from api.routers.insurance import build_disclosure_snapshot
    return build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation)


def _reit_taxonomy(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None):
    """EU Taxonomy Article 8 KPIs for the REIT property book (on top of the same frozen disclosure snapshot).

    Carries the full `properties` + `by_hazard` alongside `rollup`/`art8` (fixed 2026-09-23 — an independent
    architecture review found this framework couldn't be traced back to source: build_disclosure_snapshot()
    computes the full per-property {h3_cell, hazards[]} list right here, in `snap`, and this used to discard
    it, keeping only the rollup aggregate. That made the earlier "documented workaround" — trace the sibling
    reit_tcfd filing instead — not just inconvenient but sometimes impossible: an org that only ever files
    reit_taxonomy (never reit_tcfd) had no sibling to trace at all, and a snapshot that depends on a SEPARATE
    filing to be reproducible isn't really self-contained. Carrying the same data this framework already
    computes is the actual fix, not a workaround. Duplicating it against reit_tcfd's own frozen snapshot for
    the same period is no different in kind from the duplication every WORM version-to-version freeze already
    accepts; see filing_lineage._LIST_CFG."""
    from api.routers.realestate import build_disclosure_snapshot
    from services.governance.reit_taxonomy import art8_kpis
    snap = build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation)
    return {"rollup": snap.get("rollup"), "properties": snap.get("properties"), "by_hazard": snap.get("by_hazard"),
            "art8": art8_kpis(snap.get("properties") or [], currency=translation.presentation if translation else "EUR")}


def _insurer_solvency(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None):
    """Solvency II S.26.01.01 NatCat SCR, mapped from the insurer disclosure snapshot (no re-run).

    Carries the full `policies` + `by_hazard` alongside `rollup`/`s2601` — same fix and same reasoning as
    _reit_taxonomy() above.

    value_weights is set by generate_filing() only when scoping to a parent/group with more than itself in
    its subtree — the exact same condition entities.filing_role_for() calls 'consolidated'. That's the
    signal s2601_natcat() needs to know whether to disclose the C3 group-method gap (see its docstring)."""
    from api.routers.insurance import build_disclosure_snapshot
    from services.governance.insurer_solvency import s2601_natcat
    snap = build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation)
    return {"rollup": snap.get("rollup"), "policies": snap.get("policies"), "by_hazard": snap.get("by_hazard"),
            "s2601": s2601_natcat(snap, group_scope=value_weights is not None)}


def _fx_record(session: Session, org_id: str, translation) -> dict:
    if translation is None:
        return {"presentation_currency": "EUR", "note": "This report is built from the euro book and presents in EUR."}
    from services.governance.translation import summary
    names = {r[0]: r[1] for r in session.execute(text(
        "SELECT entity_id::text, name FROM reporting_entities WHERE org_id = :o"), {"o": org_id}).all()}
    return summary(translation, names)


def _spec_record(session: Session, report_type: str, period_end) -> dict | None:
    """The governing template specification for a filing, or None when the framework has none yet."""
    import services.regspec as R
    from services.regspec.signoff import status as signoff_status
    if report_type not in R.frameworks():
        return None
    spec = R.governing(report_type, period_end=period_end)
    if spec is None:
        return {"version": None, "note": "no adopted specification applies to this period"}
    st = signoff_status(session, report_type, spec["version"])
    return {"framework": report_type, "version": spec["version"], "sha256": spec["_sha256"], "celex": spec["act"].get("celex"),
            "act": spec["act"].get("short") or spec["act"]["title"], "basis": spec["applies"]["basis"],
            "approved": st["approved"], "one_person": st["one_person"], "needs": st["needs"]}


def report_types(sectors: tuple[str, ...] | list[str] | None = None) -> list[dict]:
    """Registered report types, optionally filtered to those applicable to the given org-type sectors."""
    out = []
    for k, v in _BUILDERS.items():
        applies = v[2] if len(v) > 2 else None
        if sectors is None or applies is None or any(s in applies for s in sectors):
            out.append({"report_type": k, "label": v[0]})
    return out


def create_snapshot(session: Session, org_id: str, report_type: str, actor_user_id: str,
                    note: str | None = None, entity_ids: list | None = None,
                    value_weights: dict | None = None, translation=None, view: str = "joint",
                    figure_sources: dict | None = None) -> dict:
    """Compute the report at the org's current basis and freeze it as the next version. Immutable once written.
    entity_ids scopes the located book to a reporting entity or a group's whole subtree (None = whole org);
    value_weights applies proportional/equity consolidation weighting. Only the located FIN books honour them.
    translation (services.governance.translation.plan) presents the money in the filing's currency and eliminates
    group-internal exposures; its record — currency, every rate used, per-entity translation, eliminations — is frozen
    in the payload as `_fx` (hash-verified). Books that don't take one (CSRD/ESRS, SFDR) present in EUR, and say so."""
    if report_type not in _BUILDERS:
        raise ValueError(f"unknown report_type '{report_type}'")
    s = get_settings(session, org_id)
    basis = {"scenario": s["scenario"], "horizon": s["horizon"],
             "materiality_threshold": s["materiality_threshold"], "reporting_period_end": s["reporting_period_end"]}
    # intake phase 5: the engine reads the chosen view of the book (joint / client / tellumen), and the run's input
    # manifest is read in the same view, so the output checks compare like with like
    from services.governance import engine_runs
    from services.intake.views import in_view

    def compute():
        out = _BUILDERS[report_type][1](session, org_id, s["scenario"], s["horizon"], s["materiality_threshold"],
                                        entity_ids, value_weights, translation)
        return out, engine_runs.inputs(session, org_id, report_type, entity_ids)
    (payload, observed), view_record = in_view(session, org_id, view, compute)
    payload["_view"] = view_record
    payload["_fx"] = _fx_record(session, org_id, translation)
    basis["presentation_currency"] = payload["_fx"]["presentation_currency"]
    basis["view"] = view
    # Lane 2 (customer/vendor provided values, attested under 4-eyes) is baked into the frozen payload here,
    # not joined live at read time — fixed 2026-09-24 (platform E2E audit finding #6). This used to be
    # computed live inside filings.form_view()/get_filing() on EVERY read, so the "Provided & attested"
    # section of an already-accepted/attested filing could silently change if a new value was attested
    # afterward for the same framework — a real break in the immutability guarantee every OTHER section of
    # a frozen filing has (sha256-verified, WORM-enforced). Baking it in here makes it hash-verified and
    # genuinely frozen like the rest of the snapshot.
    from datetime import date as _d

    from services.governance.provided_data import attested_values
    payload["_provided_attested"] = attested_values(session, org_id, report_type,
                                                    s["reporting_period_end"] or _d(_d.today().year - 1, 12, 31))
    # per reported figure: the client's attested number or ours, where both exist (phase 5) — frozen with the rest
    from services.governance.figure_views import resolve as resolve_figures
    payload["_figures"] = resolve_figures(report_type, payload, figure_sources)
    # CRCS version pinning: the regulation version this filing is prepared under, and whether it still governs the
    # period — live from the EU register, frozen with the rest (hash-verified)
    from datetime import date as _date

    from services.governance.reg_versions import version_for
    period_end = s["reporting_period_end"] or _date(_date.today().year - 1, 12, 31)
    # the template specification governing this filing (change route): its version and the file's sha256, and
    # whether that exact file is signed off — frozen, so the form is always rendered to the spec it was prepared under
    payload["_spec"] = _spec_record(session, report_type, period_end)
    on = _date.today() if (payload["_spec"] or {}).get("basis") == "disclosure_date" else None
    payload["_regulation"] = version_for(session, report_type, period_end, on=on)
    basis["regulation_status"] = (payload["_regulation"] or {}).get("status")
    versions = _engine_versions(session, org_id)
    digest = _sha256(payload)
    # intake phase 4: what this run read and whether its output holds — an integrity failure refuses the freeze
    run = engine_runs.record(session, org_id, report_type, actor_user_id, basis=basis, payload=payload,
                             entity_ids=entity_ids, value_weights=value_weights, translation=translation, view=view,
                             observed=observed)

    version = (session.execute(text(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM report_snapshots WHERE org_id = :o AND report_type = :t"),
        {"o": org_id, "t": report_type}).scalar())
    row = session.execute(text("""
        INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload, note, created_by,
                                      payload_sha256, engine_versions, run_id)
        VALUES (:o, :t, :v, CAST(:b AS jsonb), CAST(:p AS jsonb), :n, :u, :h, CAST(:ev AS jsonb), CAST(:run AS uuid))
        RETURNING snapshot_id, version, created_at
    """), {"o": org_id, "t": report_type, "v": version,
           "b": json.dumps(basis, default=str), "p": json.dumps(payload, default=str),
           "n": note, "u": actor_user_id, "h": digest, "ev": json.dumps(versions, default=str),
           "run": run["run_id"]}).mappings().first()
    return {"snapshot_id": str(row["snapshot_id"]), "report_type": report_type,
            "label": _BUILDERS[report_type][0], "version": row["version"],
            "reporting_basis": basis, "created_at": row["created_at"].isoformat(), "note": note,
            "payload_sha256": digest, "engine_versions": versions, "run_id": run["run_id"], "run_status": run["status"],
            "run_checks": run["checks"]}


def list_snapshots(session: Session, org_id: str, report_type: str | None = None) -> list[dict]:
    """Frozen filings for the org — metadata only (not the full payload), newest first."""
    q = """
        SELECT rs.snapshot_id, rs.report_type, rs.version, rs.reporting_basis, rs.note,
               rs.created_at, u.full_name created_by_name
        FROM report_snapshots rs
        LEFT JOIN users u ON u.user_id = rs.created_by
        WHERE rs.org_id = :o {filt}
        ORDER BY rs.created_at DESC
    """.format(filt="AND rs.report_type = :t" if report_type else "")
    params = {"o": org_id}
    if report_type:
        params["t"] = report_type
    rows = session.execute(text(q), params).mappings().all()
    labels = {k: v[0] for k, v in _BUILDERS.items()}
    return [{"snapshot_id": str(r["snapshot_id"]), "report_type": r["report_type"],
             "label": labels.get(r["report_type"], r["report_type"]), "version": r["version"],
             "reporting_basis": r["reporting_basis"], "note": r["note"],
             "created_at": r["created_at"].isoformat(), "created_by": r["created_by_name"]} for r in rows]


def get_snapshot(session: Session, org_id: str, snapshot_id: str) -> dict | None:
    """One frozen filing, with its full payload — the exact bytes as filed."""
    r = session.execute(text("""
        SELECT rs.snapshot_id, rs.report_type, rs.version, rs.reporting_basis, rs.payload,
               rs.note, rs.created_at, rs.payload_sha256, rs.engine_versions, u.full_name created_by_name
        FROM report_snapshots rs
        LEFT JOIN users u ON u.user_id = rs.created_by
        WHERE rs.org_id = :o AND rs.snapshot_id = :s
    """), {"o": org_id, "s": snapshot_id}).mappings().first()
    if not r:
        return None
    labels = {k: v[0] for k, v in _BUILDERS.items()}
    # re-verify the content hash: the stored payload must still hash to what was signed off
    recomputed = _sha256(r["payload"])
    return {"snapshot_id": str(r["snapshot_id"]), "report_type": r["report_type"],
            "label": labels.get(r["report_type"], r["report_type"]), "version": r["version"],
            "reporting_basis": r["reporting_basis"], "payload": r["payload"], "note": r["note"],
            "created_at": r["created_at"].isoformat(), "created_by": r["created_by_name"],
            "payload_sha256": r["payload_sha256"], "engine_versions": r["engine_versions"],
            "hash_verified": (r["payload_sha256"] is not None and r["payload_sha256"] == recomputed)}
