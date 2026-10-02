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
# builder args are (session, org_id, scenario, horizon, entity_ids, value_weights, translation, period_end) —
# period_end is the filing's reporting period (the figures are for the financial year ending on it). entity_ids /
# value_weights scope + consolidation-weight the book — supported by the located FIN books (bank/reit/insurer);
# the others (CSRD/ESRS entity-level, SFDR fund-aggregated) ignore them and report whole-org.
_BUILDERS = {
    "csrd_e1": ("CSRD · ESRS E1 physical-risk report",
                lambda *a: _retired("csrd_e1"), ("manufacturer",)),
    "esrs_pack": ("ESRS sustainability statement — E1, E3, E4",
                  lambda s, o, sc, hz, ei, vw, tr, pe: _esrs_statement(s, o, ei, pe), ("manufacturer",)),
    # ── financial-institution filings (frozen through the same WORM/hash/version machinery) ──
    "bank_tcfd": ("EU Taxonomy Art. 8 — credit institutions (loan book)",
                  lambda s, o, sc, hz, ei, vw, tr, pe: _bank_taxonomy(s, o, sc, hz, ei, vw, tr, pe), ("bank",)),
    "bank_p3esg": ("Pillar 3 ESG risk disclosures (EBA)",
                   lambda s, o, sc, hz, ei, vw, tr, pe: _bank_pillar3(s, o, sc, hz, ei, vw, tr, pe), ("bank",)),
    "sfdr_pai": ("SFDR Principal Adverse Impacts statement (Annex I)",
                 lambda s, o, sc, hz, ei, vw, tr, pe: _sfdr_pai(s, o), ("asset_manager",)),
    # retired (services.governance.filings.FRAMEWORKS[..]["retired"]): their frozen snapshots stay readable; nothing new
    "assetmgmt_tcfd": ("TCFD · physical-risk & concentration disclosure (holdings book)",
                       lambda *a: _retired("assetmgmt_tcfd"), ("asset_manager",)),
    "reit_tcfd": ("TCFD · EU-Taxonomy disclosure (property book)", lambda *a: _retired("reit_tcfd"), ("reit",)),
    "insurer_climate": ("Climate / NatCat exposure disclosure (underwriting book)",
                        lambda *a: _retired("insurer_climate"), ("insurer",)),
    "reit_taxonomy": ("EU Taxonomy Article 8 KPIs (property book)",
                      lambda s, o, sc, hz, ei, vw, tr, pe: _reit_taxonomy(s, o, sc, hz, ei, vw, tr, pe), ("reit",)),
    "insurer_orsa_climate": ("ORSA — climate change scenario analysis (Art. 45a)",
                             lambda s, o, sc, hz, ei, vw, tr, pe: _insurer_document(s, o, "insurer_orsa_climate", ei, vw, tr, pe), ("insurer",)),
    "insurer_recovery_stress": ("Pre-emptive recovery plan — nat-cat stress and capital indicators",
                                lambda s, o, sc, hz, ei, vw, tr, pe: _insurer_document(s, o, "insurer_recovery_stress", ei, vw, tr, pe),
                                ("insurer",)),
    "insurer_solvency": ("Solvency II · natural catastrophe risk (S.27.01.01)",
                         lambda s, o, sc, hz, ei, vw, tr, pe: _insurer_solvency(s, o, sc, hz, ei, vw, tr, pe), ("insurer",)),
    # ── per financial product (the fund is the filing's subject): frozen by services.governance.sfdr_product.freeze ──
    # frozen from its shipment (movement_id): services.eudr.statement + services.eudr.checks
    "eudr_dds": ("EUDR due diligence statement", "eudr_movement", ("manufacturer",)),
    "sfdr_precontractual": ("SFDR pre-contractual disclosure (RTS 2022/1288 Annex II / III)", None, ("asset_manager",)),
    "sfdr_periodic": ("SFDR periodic disclosure (RTS 2022/1288 Annex IV / V)", None, ("asset_manager",)),
}


def _retired(report_type: str):
    """A retired report freezes nothing new (create_snapshot refuses it first, with the reason of its declaration —
    services.governance.filings.retirement_refusal); its frozen snapshots stay readable. Its engine is gone (csrd_e1 read
    a v0 business-interruption curve and a fixed 'material' line of the platform's own, E69; the TCFD-style reports, E87)."""
    from services.governance.filings import retirement_refusal
    raise ValueError(retirement_refusal(report_type) or f"{report_type} is retired")


# a report type whose provided values are stated under a family shared by every report that prints them
_PROVIDED_UNDER = {"esrs_pack": "esrs"}


def _esrs_statement(session, org_id, entity_ids, period_end):
    """The ESRS statement of the undertaking the filing is for (services.governance.esrs_document.freeze)."""
    from services.governance.esrs_document import freeze
    return freeze(session, org_id, entity_ids=entity_ids, period_end=period_end)


def _bank_taxonomy(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None, period_end=None):
    """The loan book the EU Taxonomy Art. 8 templates read (services.governance.bank_taxonomy_report, E95)."""
    from services.governance.bank_taxonomy_report import freeze
    return freeze(session, org_id, scenario, horizon, entity_ids, value_weights, translation, period_end)


def _bank_pillar3(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None, period_end=None):
    """The banking book the Pillar 3 ESG templates read (services.governance.pillar3_report, E97)."""
    from services.governance.pillar3_report import freeze
    return freeze(session, org_id, scenario, horizon, entity_ids, value_weights, translation, period_end)


def _sfdr_pai(session, org_id):
    from ml.regulatory.sfdr_pai import entity_pai_statement
    return entity_pai_statement(session, org_id)


def _reit_taxonomy(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None, period_end=None):
    """EU Taxonomy Article 8 KPIs for the REIT property book (on top of the same frozen disclosure snapshot).

    Carries the full `properties` + `by_hazard` alongside `rollup` (fixed 2026-09-23 — an independent
    architecture review found this framework couldn't be traced back to source: build_disclosure_snapshot()
    computes the full per-property {h3_cell, hazards[]} list right here, in `snap`, and this used to discard
    it, keeping only the rollup aggregate, so it could be traced only through a sibling filing of another report
    type (now retired). A snapshot that depends on a SEPARATE filing to be reproducible isn't self-contained;
    carrying the data this framework already computes is the fix. See filing_lineage._LIST_CFG."""
    from api.routers.realestate import build_disclosure_snapshot
    snap = build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation, period_end=period_end)
    # the EU Taxonomy Art. 8 figures are built from `properties` against the governing specification when the form is
    # rendered (services.governance.taxonomy_nonfin) — the book is what is frozen
    return {"rollup": snap.get("rollup"), "properties": snap.get("properties"), "by_hazard": snap.get("by_hazard"),
            "method": snap.get("method")}


def _insurer_solvency(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None, period_end=None):
    """Solvency II S.27.01.01 natural-catastrophe risk, mapped from the insurer disclosure snapshot (no re-run).

    Carries the full `policies` + `by_hazard` alongside `rollup` and the nat-cat block — same fix and same reasoning
    as _reit_taxonomy() above.

    value_weights is set by generate_filing() only when scoping to a parent/group with more than itself in
    its subtree — the exact same condition entities.filing_role_for() calls 'consolidated'. That's the
    signal s2701_natcat() needs to know whether to disclose the C3 group-method gap (see its docstring)."""
    from api.routers.insurance import build_disclosure_snapshot
    from services.governance.insurer_solvency import KEY, s2701_natcat
    snap = build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                                     translation=translation, period_end=period_end)
    return {"rollup": snap.get("rollup"), "policies": snap.get("policies"), "by_hazard": snap.get("by_hazard"),
            KEY: s2701_natcat(snap, group_scope=value_weights is not None), "method": snap.get("method")}


def _insurer_document(session, org_id, report_type, entity_ids=None, value_weights=None, translation=None, period_end=None):
    """An insurer document report (services.governance.insurer_documents): the computed part — every scenario run on the
    same book, the attested capital of the undertaking or group it is for — and the undertaking's answers, frozen; with
    today's book (rollup, policies) for the run record and lineage."""
    from api.routers.insurance import build_disclosure_snapshot
    from services.governance.entities import root_of
    from services.governance.insurer_documents import freeze
    doc = freeze(session, org_id, report_type, entity_ids=entity_ids, value_weights=value_weights, translation=translation,
                 period_end=period_end)
    today = build_disclosure_snapshot(session, org_id, "baseline", "current", entity_ids=entity_ids, value_weights=value_weights,
                                      translation=translation, reporting_entity_id=root_of(session, org_id, entity_ids),
                                      period_end=period_end)
    return {"document_report": doc, "rollup": today.get("rollup"), "policies": today.get("policies"),
            "by_hazard": today.get("by_hazard"), "method": today.get("method")}


def _fx_record(session: Session, org_id: str, translation) -> dict:
    if translation is None:
        return {"presentation_currency": "EUR", "note": "This report is built from the euro book and presents in EUR."}
    from services.governance.translation import summary
    names = {r[0]: r[1] for r in session.execute(text(
        "SELECT entity_id::text, name FROM reporting_entities WHERE org_id = :o"), {"o": org_id}).all()}
    return summary(translation, names)


def _financial_year_start(period_end):
    """The first day of the twelve-month financial year ending on period_end — one rule (services.regspec.fy_start)."""
    from services.regspec import fy_start
    return fy_start(period_end)


def _spec_record(session: Session, family: str, period_end, elections: dict | None = None,
                 disclosure_date=None) -> dict | None:
    """The governing version of one specification family for a filing (with the organisation's elections, e.g. the
    Art. 4 option of Delegated Regulation 2026/73 — see regspec.governing), or None when the family has no specs yet."""
    from datetime import date as _date

    import services.regspec as R
    from services.regspec.signoff import status as signoff_status
    if family not in R.frameworks():
        return None
    pe = _date.fromisoformat(str(period_end)[:10])
    spec = R.governing(family, period_end=pe, disclosure_date=disclosure_date, elections=elections,
                       financial_year_start=_financial_year_start(pe))
    if spec is None:
        return {"framework": family, "version": None, "note": "no adopted specification applies to this period"}
    st = signoff_status(session, family, spec["version"])
    return {"framework": family, "version": spec["version"], "sha256": spec["_sha256"], "celex": spec["act"].get("celex"),
            "act": spec["act"].get("short") or spec["act"]["title"], "basis": spec["applies"]["basis"],
            "approved": st["approved"], "one_person": st["one_person"], "needs": st["needs"],
            "disclosed_on": (disclosure_date or _date.today()).isoformat()}   # the disclosure the version was chosen for


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
                    figure_sources: dict | None = None, previous_period: dict | None = None,
                    fund_id: str | None = None, disclosure_date=None, *, period_end, movement_id: str | None = None) -> dict:
    """Compute the report at the org's current basis and freeze it as the next version. Immutable once written.
    entity_ids scopes the located book to a reporting entity or a group's whole subtree (None = whole org);
    value_weights applies proportional/equity consolidation weighting. Only the located FIN books honour them.
    translation (services.governance.translation.plan) presents the money in the filing's currency and eliminates
    group-internal exposures; its record — currency, every rate used, per-entity translation, eliminations — is frozen
    in the payload as `_fx` (hash-verified). Books that don't take one (CSRD/ESRS, SFDR) present in EUR, and say so.
    fund_id: the financial product a per-product report (sfdr_precontractual / sfdr_periodic) is about."""
    if report_type not in _BUILDERS:
        raise ValueError(f"unknown report_type '{report_type}'")
    from services.governance.filings import retirement_refusal
    if retirement_refusal(report_type):                  # a retired report freezes nothing new — the one reason
        raise ValueError(retirement_refusal(report_type))
    s = get_settings(session, org_id)
    from datetime import date as _pd
    period_end = _pd.fromisoformat(str(period_end)[:10])            # the filing's period — never the org's setting
    # 'material' is the undertaking's stated at-risk level for the period — frozen with the figures in payload['method']
    # (services.money.params), never a reporting setting of its own (E69)
    basis = {"scenario": s["scenario"], "horizon": s["horizon"], "reporting_period_end": period_end.isoformat()}
    # intake phase 5: the engine reads the chosen view of the book (joint / client / tellumen), and the run's input
    # manifest is read in the same view, so the output checks compare like with like
    from services.governance import engine_runs
    from services.intake.views import in_view

    def compute():
        if _BUILDERS[report_type][1] == "eudr_movement":  # an EUDR statement: its shipment, as it stands, and its checks
            from services.eudr.checks import checks
            from services.eudr.statement import compute as statement
            if movement_id is None:
                raise ValueError("an EUDR due diligence statement is prepared from its shipment — a movement is required")
            st = statement(session, org_id, movement_id)
            return {"statement": st, "checks": checks(st)}, engine_runs.inputs(session, org_id, report_type)
        if _BUILDERS[report_type][1] is None:            # a per-product report: the fund's own book and answers
            from services.governance import product_filings, sfdr_product
            if fund_id is None:
                raise ValueError(f"{report_type} is disclosed per financial product — a fund is required")
            out = sfdr_product.freeze(session, org_id, fund_id, product_filings.PRODUCT_SCOPED[report_type]["document"],
                                      period_end)
            return out, engine_runs.inputs(session, org_id, report_type, None, fund_id=fund_id,
                                           as_of_dates=out["position_dates"])
        out = _BUILDERS[report_type][1](session, org_id, s["scenario"], s["horizon"],
                                        entity_ids, value_weights, translation, period_end)
        if report_type == "esrs_pack":
            return out, engine_runs.inputs(session, org_id, report_type, asset_ids=[
                x["site_id"] for x in out["document_report"]["statement"]["sites"]])
        return out, engine_runs.inputs(session, org_id, report_type, entity_ids)
    (payload, observed), view_record = in_view(session, org_id, view, compute)
    payload["_view"] = view_record
    payload["_fx"] = _fx_record(session, org_id, translation)
    if value_weights:                         # a group filing: the consolidation rule it was weighted on, frozen with it
        from services.governance.entities import consolidation_record
        payload["_consolidation"] = consolidation_record(report_type)
    basis["presentation_currency"] = payload["_fx"]["presentation_currency"]
    basis["view"] = view
    # Lane 2 (customer/vendor provided values, attested under 4-eyes) is baked into the frozen payload here,
    # not joined live at read time — fixed 2026-09-24 (platform E2E audit finding #6). This used to be
    # computed live inside filings.form_view()/get_filing() on EVERY read, so the "Provided & attested"
    # section of an already-accepted/attested filing could silently change if a new value was attested
    # afterward for the same framework — a real break in the immutability guarantee every OTHER section of
    # a frozen filing has (sha256-verified, WORM-enforced). Baking it in here makes it hash-verified and
    # genuinely frozen like the rest of the snapshot.

    from services.governance.entities import root_of
    from services.governance.provided_data import attested_values
    payload["_scope"] = {"reporting_entity_id": root_of(session, org_id, entity_ids)}   # whose own figures (None = the organisation)
    payload["_provided_attested"] = attested_values(session, org_id, _PROVIDED_UNDER.get(report_type, report_type), period_end,
                                                    reporting_entity_id=payload["_scope"]["reporting_entity_id"])
    # per reported figure: the client's attested number or ours, where both exist (phase 5) — frozen with the rest
    from services.governance.figure_views import resolve as resolve_figures
    payload["_figures"] = resolve_figures(report_type, payload, figure_sources)
    # the previous period's frozen book for the same scope, when the templates print T-1 (filings._previous_period_book)
    if previous_period:
        payload["_previous_period"] = previous_period
    # CRCS version pinning: the regulation version this filing is prepared under, and whether it still governs the
    # period — live from the EU register, frozen with the rest (hash-verified)
    from datetime import date as _date

    # the template specification governing this filing (change route): its version and the file's sha256, and
    # whether that exact file is signed off — frozen, so the form is always rendered to the spec it was prepared under
    # every family that governs this report type (regspec_usage.json), with the organisation's elections applied;
    # _spec keeps the primary family's record for readers of a single specification
    from services.calc_settings import get_calc_settings
    from services.governance.reg_versions import version_for
    from services.regspec import families_for
    _elections = get_calc_settings(session, org_id)
    payload["_specs"] = {f: _spec_record(session, f, period_end, _elections, disclosure_date) for f in families_for(report_type)}
    payload["_spec"] = next(iter(payload["_specs"].values()), None)
    on = (disclosure_date or _date.today()) if (payload["_spec"] or {}).get("basis") == "disclosure_date" else None
    payload["_regulation"] = version_for(session, report_type, period_end, on=on)
    basis["regulation_status"] = (payload["_regulation"] or {}).get("status")
    if _BUILDERS[report_type][1] == "eudr_movement":
        # a shipment's statement: no scenario, horizon, view or money — it is the shipment on its date, under the version.
        # The date keeps the key report_snapshots scopes its versions by (period_end is generated from it); displays name
        # it 'shipment date' where the basis is a shipment's.
        basis = {"shipment": payload["statement"]["movement"]["external_ref"], "reporting_period_end": period_end.isoformat(),
                 "regulation_status": basis["regulation_status"]}
    versions = _engine_versions(session, org_id)
    digest = _sha256(payload)
    # intake phase 4: what this run read and whether its output holds — an integrity failure refuses the freeze
    run = engine_runs.record(session, org_id, report_type, actor_user_id, basis=basis, payload=payload,
                             entity_ids=entity_ids, value_weights=value_weights, translation=translation, view=view,
                             observed=observed)

    # versions are counted per report type, period and undertaking (the scope columns read the frozen record)
    version = (session.execute(text("""
        SELECT COALESCE(MAX(version), 0) + 1 FROM report_snapshots
        WHERE org_id = :o AND report_type = :t AND period_end IS NOT DISTINCT FROM iso_date_or_null(:pe)
          AND reporting_entity_id IS NOT DISTINCT FROM uuid_or_null(:e)"""),
        {"o": org_id, "t": report_type, "pe": period_end.isoformat(),
         "e": payload["_scope"]["reporting_entity_id"]}).scalar())
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
