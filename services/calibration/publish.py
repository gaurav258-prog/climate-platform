"""Publishing calibration runs — reviewed, never automatic (E162; 'calibration.publish', the platform's Approvers
policy: one approver stated → the platform's system account proposes and one person decides).

  pending_changes   the recorded runs whose figures or upside verdict differ from what their recipe has published
  propose           one approval request for a batch of runs (the difference summarised); the runs → proposed
  apply_decision    approved → each run publishes: sc_commodity_fit takes its figures and names its recipe, yield series
                    and cycle rule; the origin's calibration row follows the published fit of ITS driver (season, box,
                    baseline years — never a value kept from an older fit); the recipe's previous run → superseded.
                    Rejected / returned → the runs close unpublished.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.calibration.gates import downside_pass
from services.calibration.runner import spec as get_spec

REQUEST_TYPE = "calibration.publish"
_FIGURES = ("n_years", "baseline_from", "baseline_to", "slope", "intercept", "r2", "r2_oos", "rmse", "score_mean",
            "score_sxx", "band_cov68", "downside_pass", "upside_pass")


class PublishError(ValueError):
    pass


def _run(session: Session, run_id: str) -> dict:
    r = session.execute(text(f"""
        SELECT run_id::text, spec_id::text, status, outcome, upside, {", ".join(f"CAST({c} AS FLOAT) AS {c}"
               if c not in ("n_years", "baseline_from", "baseline_to", "downside_pass", "upside_pass") else c
               for c in _FIGURES)}
        FROM crop_calibration_runs WHERE run_id = CAST(:r AS uuid)"""), {"r": run_id}).mappings().first()
    if r is None:
        raise PublishError(f"calibration run {run_id} not found")
    return dict(r)


def _published(session: Session, spec_id: str) -> dict | None:
    rid = session.execute(text("""SELECT run_id::text FROM crop_calibration_runs
                                  WHERE spec_id = CAST(:s AS uuid) AND status = 'published'"""), {"s": spec_id}).scalar()
    return _run(session, rid) if rid else None


def changes(session: Session, run_id: str) -> dict | None:
    """What publishing this run would change against its recipe's published run (None: nothing — or not fitted)."""
    run = _run(session, run_id)
    if run["outcome"] != "fitted" or run["status"] != "recorded":
        return None
    pub = _published(session, run["spec_id"])
    if pub is None:
        return {"run_id": run_id, "first": True}
    diff = {c: [pub[c], run[c]] for c in _FIGURES if pub[c] != run[c]}
    if (pub["upside"] or {}).get("capped") != (run["upside"] or {}).get("capped"):
        diff["upside_capped"] = [(pub["upside"] or {}).get("capped"), (run["upside"] or {}).get("capped")]
    return {"run_id": run_id, "first": False, "diff": diff} if diff else None


def propose(session: Session, run_ids: list[str], reason: str, maker_user_id: str | None = None) -> dict | None:
    """One approval request for the runs that would change a publication. None when nothing would change."""
    from services.governance.platform_policy import PLATFORM_ORG, SYSTEM_USER, human_approvers
    pending = [c for c in (changes(session, r) for r in run_ids) if c]
    if not pending:
        return None
    if human_approvers(session, REQUEST_TYPE) == 1:
        maker_user_id = SYSTEM_USER
    if maker_user_id is None:
        raise PublishError("a person proposes when the policy states two approvers")
    ids = [c["run_id"] for c in pending]
    summary = summarise(session, ids)
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), :t, :title, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id::text"""),
        {"o": PLATFORM_ORG, "t": REQUEST_TYPE,
         "title": f"Publish {len(ids)} crop calibration run{'s' if len(ids) != 1 else ''}",
         "p": json.dumps({"run_ids": ids, "review": reason, "summary": summary}, default=str),
         "m": maker_user_id}).scalar()
    session.execute(text("""UPDATE crop_calibration_runs SET status = 'proposed', approval_request_id = CAST(:a AS uuid)
                            WHERE run_id = ANY(CAST(:ids AS uuid[]))"""), {"a": rid, "ids": ids})
    return {"approval_request_id": rid, "runs": len(ids), "summary": summary}


def summarise(session: Session, run_ids: list[str]) -> dict:
    """The facts a reviewer decides on: per run its slot, figures, gates and what changes against the published fit."""
    rows = []
    for rid in run_ids:
        run, ch = _run(session, rid), changes(session, rid) or {}
        sp = get_spec(session, run["spec_id"])
        old = session.execute(text("""
            SELECT CAST(f.r2_oos AS FLOAT) AS r2_oos FROM sc_commodity_fit f JOIN sc_commodities c USING (commodity_id)
            WHERE c.name = :c AND f.origin = :o AND f.hazard_driver = :d"""),
            {"c": sp["commodity"], "o": sp["origin"], "d": sp["driver"]}).mappings().first()
        rows.append({"run_id": rid, "commodity": sp["commodity"], "origin": sp["origin"], "driver": sp["driver"],
                     "recipe": sp["weather_kind"], "r2_oos": run["r2_oos"],
                     "published_r2_oos": old["r2_oos"] if old else None, "downside_pass": run["downside_pass"],
                     "upside_pass": run["upside_pass"], "upside_failed": (run["upside"] or {}).get("failed"),
                     "first_run": ch.get("first", False)})
    return {"runs": rows,
            "downside_passes": sum(r["downside_pass"] for r in rows), "upside_passes": sum(r["upside_pass"] for r in rows),
            "gate_flips": [f"{r['commodity']}/{r['origin']} {r['driver']}" for r in rows
                           if r["published_r2_oos"] is not None
                           and downside_pass(r["published_r2_oos"]) != bool(r["downside_pass"])]}


def _publish(session: Session, run_id: str, checker: str, reason: str | None) -> None:
    run = _run(session, run_id)
    sp = get_spec(session, run["spec_id"])
    cid = session.execute(text("SELECT commodity_id FROM sc_commodities WHERE name = :n"), {"n": sp["commodity"]}).scalar()
    if cid is None:
        raise PublishError(f"'{sp['commodity']}' is not a modelled commodity (sc_commodities)")
    months = list(sp["season_months"])
    note = (f"{sp['protocol']} run {run_id}: OLS of the climate anomaly on the {sp['driver']} score, {sp['weather_kind']} "
            f"'{sp['weather_key']}', months {months}" + (f" (+ previous-year {list(sp['season_prev_months'])})"
                                                          if sp["season_prev_months"] else "")
            + f", {sp['yield_source']}{' ' + sp['yield_region'] if sp['yield_region'] else ''}, {run['n_years']} years. "
            + ("Publishes as a range." if run["downside_pass"] else "Below the publish floor — tested, the number withheld."))
    session.execute(text("""
        INSERT INTO sc_commodity_fit (commodity_id, origin, hazard_driver, region_key, season_months, spei_scale, n_years,
               slope, intercept, r2, rmse, score_mean, score_sxx, r2_oos, band_cov68, baseline_from, baseline_to,
               fit_version, source_note, yield_source, yield_region, allow_cycle, spec_id, run_id)
        SELECT :cid, :o, :d, :key, :months, :scale, n_years, slope, intercept, r2, rmse, score_mean, score_sxx, r2_oos,
               band_cov68, baseline_from, baseline_to, :proto, :note, :src, :reg, :cyc, spec_id, run_id
        FROM crop_calibration_runs WHERE run_id = CAST(:run AS uuid)
        ON CONFLICT (commodity_id, origin, hazard_driver) DO UPDATE SET
            region_key = EXCLUDED.region_key, season_months = EXCLUDED.season_months, spei_scale = EXCLUDED.spei_scale,
            n_years = EXCLUDED.n_years, slope = EXCLUDED.slope, intercept = EXCLUDED.intercept, r2 = EXCLUDED.r2,
            rmse = EXCLUDED.rmse, score_mean = EXCLUDED.score_mean, score_sxx = EXCLUDED.score_sxx,
            r2_oos = EXCLUDED.r2_oos, band_cov68 = EXCLUDED.band_cov68, baseline_from = EXCLUDED.baseline_from,
            baseline_to = EXCLUDED.baseline_to, fit_version = EXCLUDED.fit_version, source_note = EXCLUDED.source_note,
            yield_source = EXCLUDED.yield_source, yield_region = EXCLUDED.yield_region,
            allow_cycle = EXCLUDED.allow_cycle, spec_id = EXCLUDED.spec_id, run_id = EXCLUDED.run_id, created_at = now()"""),
        {"cid": cid, "o": sp["origin"], "d": sp["driver"], "key": sp["weather_key"], "months": months,
         "scale": sp["spei_scale"], "proto": sp["protocol"], "note": note, "src": sp["yield_source"],
         "reg": sp["yield_region"], "cyc": sp["allow_cycle"], "run": run_id})
    # the origin's calibration row follows the published fit of its own driver — never a season or box kept from an
    # older fit; a new origin takes this driver; an origin calibrated on another driver keeps it (its own governed fact)
    session.execute(text("""
        INSERT INTO sc_commodity_calibration (commodity_id, origin, hazard_driver, region_key, season_months,
               impact_version, baseline_from, baseline_to)
        VALUES (:cid, :o, :d, :key, :months, :proto, :bf, :bt)
        ON CONFLICT (commodity_id, origin) DO UPDATE SET region_key = EXCLUDED.region_key,
            season_months = EXCLUDED.season_months, baseline_from = EXCLUDED.baseline_from,
            baseline_to = EXCLUDED.baseline_to
        WHERE sc_commodity_calibration.hazard_driver = EXCLUDED.hazard_driver"""),
        {"cid": cid, "o": sp["origin"], "d": sp["driver"], "key": sp["weather_key"], "months": months,
         "proto": sp["protocol"], "bf": run["baseline_from"], "bt": run["baseline_to"]})
    session.execute(text("""UPDATE crop_calibration_runs SET status = 'superseded', decided_by = CAST(:u AS uuid),
                            decided_at = now(), decision_reason = 'a later run of the recipe was published'
                            WHERE spec_id = CAST(:s AS uuid) AND status = 'published'"""),
                    {"s": run["spec_id"], "u": checker})
    session.execute(text("""UPDATE crop_calibration_runs SET status = 'published', decided_by = CAST(:u AS uuid),
                            decided_at = now(), decision_reason = :w WHERE run_id = CAST(:r AS uuid)"""),
                    {"u": checker, "w": reason, "r": run_id})


def apply_decision(session: Session, payload: dict, decision: str, checker_user_id: str, reason: str | None) -> dict:
    """The approvals path's handler for 'calibration.publish'."""
    ids = list((payload or {}).get("run_ids") or [])
    for rid in ids:
        if _run(session, rid)["status"] != "proposed":
            raise PublishError(f"run {rid} is not awaiting a decision")
    if decision != "approved":
        session.execute(text("""UPDATE crop_calibration_runs SET status = 'rejected', decided_by = CAST(:u AS uuid),
                                decided_at = now(), decision_reason = :w WHERE run_id = ANY(CAST(:ids AS uuid[]))"""),
                        {"u": checker_user_id, "w": reason or f"{decision} by the reviewer", "ids": ids})
        return {"status": "rejected", "runs": len(ids)}
    for rid in ids:
        _publish(session, rid, checker_user_id, reason)
    return {"status": "published", "runs": len(ids)}
