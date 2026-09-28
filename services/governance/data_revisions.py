"""New data since a filing was frozen — the restatement flag (intake phase 6).

Principle 4 (agreed 2026-09-25): data that arrives after a filing is frozen never touches the filing; the filing is
flagged that a restatement may be needed. The filing is pinned to the engine run it was frozen from (report_snapshots.
run_id → engine_runs), whose manifest fingerprints exactly what it read. Comparing that with the book now, in the same
scope and the same view, says whether anything the filing rests on has moved — and the fact history (phase 3) says what:

  book        the fingerprint of every fact the run read vs now (per book; assets added / removed / changed)
  facts       each statement recorded since the run on an asset in scope — which fact, from which source and path
  batches     data batches imported since the run that landed on assets in scope
  decisions   differences between the client's values and ours decided since (they change the joint view)
  scores      hazard scores for the scope's cells updated since the run
A filing frozen before runs were recorded has no pin: it says so rather than guessing.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance import engine_runs as R


def _pin(session: Session, org_id: str, filing_id: str) -> Optional[dict]:
    r = session.execute(text("""
        SELECT rf.framework, rf.status, rf.view, rf.entity_id::text AS entity_id, rs.run_id::text AS run_id
        FROM regulatory_filing rf LEFT JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        WHERE rf.filing_id = CAST(:f AS uuid) AND rf.org_id = CAST(:o AS uuid)
    """), {"f": filing_id, "o": org_id}).mappings().first()
    return dict(r) if r else None


def revisions(session: Session, org_id: str, filing_id: str) -> dict:
    pin = _pin(session, org_id, filing_id)
    if pin is None:
        raise ValueError("filing not found")
    if not pin["run_id"]:
        return {"pinned": False, "changed": None,
                "message": "This filing was frozen before engine runs were recorded, so there is no fingerprint to compare "
                           "the book with. Refresh (draft) or restate it to pin it to a run."}
    run = R.get_run(session, org_id, pin["run_id"])
    then = run["inputs"]
    entity_ids = run.get("entity_ids")
    from services.intake.views import in_view
    (now, rows), _ = in_view(session, org_id, run["view"], lambda: R.inputs(session, org_id, run["report_type"], entity_ids))
    books = []
    for b in then["books"]:
        n = next((x for x in now["books"] if x["book"] == b["book"]), None)
        books.append({"book": b["book"], "changed": n is None or n["facts_sha256"] != b["facts_sha256"],
                      "then": {"n_assets": b["n_assets"], "total_value_eur": b["total_value_eur"]},
                      "now": {"n_assets": n["n_assets"], "total_value_eur": n["total_value_eur"]} if n else None})
    ids = [r["entity_id"] for rs in rows.values() for r in rs]
    since_obs = then.get("last_observation_id") or 0
    facts = session.execute(text("""
        SELECT o.field, o.source, o.method, o.origin FROM asset_observations o
        WHERE o.org_id = CAST(:o AS uuid) AND o.observation_id > :since AND o.asset_id = ANY(CAST(:ids AS uuid[]))
    """), {"o": org_id, "since": since_obs, "ids": ids}).mappings().all() if ids else []
    batches = session.execute(text("""
        SELECT b.batch_id::text, b.template, b.imported_at, count(DISTINCT o.asset_id) AS n_assets
        FROM ingest_batches b JOIN asset_observations o ON o.origin = 'batch:' || b.batch_id::text
        WHERE b.org_id = CAST(:o AS uuid) AND b.state = 'imported' AND b.imported_at > CAST(:at AS timestamptz)
          AND o.asset_id = ANY(CAST(:ids AS uuid[]))
        GROUP BY b.batch_id, b.template, b.imported_at ORDER BY b.imported_at DESC
    """), {"o": org_id, "at": run["created_at"], "ids": ids}).mappings().all() if ids else []
    decided = session.execute(text("""
        SELECT count(*) FROM asset_conflicts WHERE org_id = CAST(:o AS uuid) AND status = 'resolved'
          AND resolved_at > CAST(:at AS timestamptz) AND asset_id = ANY(CAST(:ids AS uuid[]))
    """), {"o": org_id, "at": run["created_at"], "ids": ids}).scalar() if ids else 0
    scores_then, scores_now = then.get("scores") or {}, now.get("scores") or {}
    newer_scores = bool(scores_now.get("latest_scored_at") and (scores_now.get("latest_scored_at") or "") > (scores_then.get("latest_scored_at") or ""))
    book_changed = any(b["changed"] for b in books)
    changed = book_changed or newer_scores
    reasons = []
    if book_changed:
        reasons.append("the book it was computed from has changed")
    if newer_scores:
        reasons.append("hazard scores for its assets were updated")
    return {"pinned": True, "run_id": pin["run_id"], "view": run["view"], "frozen_at": run["created_at"],
            "changed": changed, "books": books,
            "facts": {"n": len(facts), "by_field": dict(Counter(f["field"] for f in facts).most_common(12)),
                      "by_path": dict(Counter(f["method"] for f in facts if f["source"] == "client"))},
            "batches": [{**dict(b), "imported_at": b["imported_at"].isoformat()} for b in batches],
            "decisions": int(decided or 0),
            "scores": {"then": scores_then.get("latest_scored_at"), "now": scores_now.get("latest_scored_at"), "newer": newer_scores},
            "message": (("New data since this filing was frozen — " + " and ".join(reasons) + ". The filing is unchanged; "
                         "restate it (or refresh a draft) to bring the new data in.") if changed else
                        "Nothing it was computed from has changed since it was frozen.")}


def flagged_filings(session: Session, org_id: str) -> list[dict]:
    """Live frozen filings with new client facts, or newly decided differences, on assets in their scope since their run
    — the cheap sweep behind the task feed (the filing page shows the full comparison, revisions())."""
    runs = session.execute(text("""
        SELECT rf.filing_id::text, rf.framework, rf.period_label, rf.status, er.run_id::text, er.report_type, er.entity_ids,
               er.created_at, (er.inputs->>'last_observation_id')::bigint AS since
        FROM regulatory_filing rf JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        JOIN engine_runs er ON er.run_id = rs.run_id
        WHERE rf.org_id = CAST(:o AS uuid) AND rf.status <> 'superseded'
    """), {"o": org_id}).mappings().all()
    out = []
    for r in runs:
        tables = _tables_for(r["report_type"])
        if not tables:
            continue
        scope = ""
        params = {"o": org_id, "since": r["since"] or 0, "t": tables, "at": r["created_at"]}
        if r["entity_ids"] and r["report_type"] in R.LOCATED:
            scope = ("AND EXISTS (SELECT 1 FROM portfolio_entities e WHERE e.entity_id = x.asset_id "
                     "AND e.reporting_entity_id = ANY(CAST(:eids AS uuid[])))")
            params["eids"] = [str(e) for e in r["entity_ids"]]
        if r["report_type"] in R.LOCATED:
            scope += (" AND EXISTS (SELECT 1 FROM portfolio_entities v WHERE v.entity_id = x.asset_id AND v.vertical = :vert)")
            params["vert"] = R.LOCATED[r["report_type"]][0]
        hit = session.execute(text(f"""
            SELECT (SELECT count(*) FROM asset_observations x WHERE x.org_id = CAST(:o AS uuid) AND x.observation_id > :since
                      AND x.source = 'client' AND x.asset_table = ANY(:t) {scope}) AS facts,
                   (SELECT count(*) FROM asset_conflicts x WHERE x.org_id = CAST(:o AS uuid) AND x.status = 'resolved'
                      AND x.resolution <> 'agreed' AND x.resolved_at > :at AND x.asset_table = ANY(:t) {scope}) AS decisions
        """), params).mappings().first()
        if hit["facts"] or hit["decisions"]:
            out.append({"filing_id": r["filing_id"], "framework": r["framework"], "period_label": r["period_label"],
                        "status": r["status"], "new_facts": int(hit["facts"]), "decisions": int(hit["decisions"])})
    return out


def _tables_for(report_type: str) -> list[str]:
    if report_type in R.LOCATED:
        return ["portfolio_entities"]
    if report_type in ("csrd_e1", "esrs_pack"):
        return ["sc_company_sites", "sc_sourcing_plots"]
    return []
