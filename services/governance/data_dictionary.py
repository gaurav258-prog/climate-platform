"""Data dictionary — the single model behind every report, on screen.

The platform sources data once into one canonical model and reuses it across every reporting area. This lists that
model's fields: each hazard (the scored field), the source feed(s) it derives from with their live maturity and
freshness, how current the scores are (latest data vintage), and which of the organisation's own filings froze it —
read from the feed registry, the scores and the frozen filings, so nothing is typed in here. Then the reporting
datapoints of each live report, by where the data comes from and how it enters the platform (the datapoint catalogue).

Every word a screen shows is the catalogue's (core/messages.py): the hazard's name (names.hazard), the summary and the
legend (intake.dictionary.*).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.messages import name, names, render

# where a reporting datapoint's data comes from, and how it enters the platform (the catalogue's words for each)
SOURCE_CATEGORIES = ("tellumen", "egov", "evendor", "customer", "none")
LANES = ("compute", "granular", "provided", "report", "none")

# the frozen-filing lists whose items carry the hazards that filing read
_HAZARD_LISTS = ("assets", "properties", "policies", "holdings", "sites")


def _consumers(session: Session, org_id: str) -> dict[str, list[str]]:
    """hazard → the report types of the organisation's live filings whose frozen snapshot holds a figure for it."""
    rows = session.execute(text("""
        WITH live AS (
            SELECT rf.framework, rs.payload FROM regulatory_filing rf JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
            WHERE rf.org_id = CAST(:o AS uuid) AND rf.status NOT IN ('superseded', 'withdrawn'))
        SELECT DISTINCT framework, h.key AS hazard FROM live,
            LATERAL jsonb_object_keys(CASE WHEN jsonb_typeof(payload->'by_hazard') = 'object' THEN payload->'by_hazard'
                                           ELSE '{}'::jsonb END) AS h(key)
        UNION
        SELECT DISTINCT framework, hz->>'hazard' FROM live,
            LATERAL (SELECT value FROM jsonb_each(payload) WHERE key = ANY(:lists) AND jsonb_typeof(value) = 'array') l,
            LATERAL jsonb_array_elements(l.value) a,
            LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(a->'hazards') = 'array' THEN a->'hazards' ELSE '[]'::jsonb END) hz
        UNION
        SELECT DISTINCT framework, mh->>'hazard' FROM live,
            LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(payload->'topics') = 'array' THEN payload->'topics' ELSE '[]'::jsonb END) t,
            LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(t->'material_hazards') = 'array' THEN t->'material_hazards'
                                              ELSE '[]'::jsonb END) mh
    """), {"o": org_id, "lists": list(_HAZARD_LISTS)}).all()
    out: dict[str, set] = {}
    for fw, hz in rows:
        if hz:
            out.setdefault(hz, set()).add(fw)
    return {h: sorted(v) for h, v in out.items()}


def _feed(f: dict) -> dict:
    """A source feed with its freshness and how it reaches the platform, in customer words (names.intake.feed_*)."""
    states, kinds = names().get("intake.feed_state", {}), names().get("intake.feed_maturity", {})
    return {"name": f["name"], "maturity": f["maturity"], "status": f["status"], "last_refresh": f.get("last_refresh"),
            "state_label": states.get(f["status"] or "untracked") or states["untracked"],
            "maturity_label": kinds.get(f["maturity"] or "") or None}


def _report(framework: str) -> str:
    """A report's name as the filings show it (services/governance/filings.FRAMEWORKS)."""
    from services.governance.filings import FRAMEWORKS
    return (FRAMEWORKS.get(framework) or {}).get("label") or "Another report"


def data_dictionary(session: Session, org_id: str) -> dict:
    from core.types import HazardType
    from services.data.feeds import HAZARD_FEEDS, feeds_for_hazard

    # latest scored vintage per hazard (how current the data behind each field is)
    vintages = {r[0]: r[1] for r in session.execute(text("""
        SELECT hazard_type, MAX(data_vintage) FROM canonical_scores
        WHERE valid_to IS NULL AND score_lane = 'standing' GROUP BY hazard_type
    """)).all()}
    used = _consumers(session, org_id)

    fields = []
    for hz in HazardType:
        h = hz.value
        v = vintages.get(h)
        fields.append({
            "field": h, "label": name("hazard", h), "category": "hazard",
            "source_feeds": [_feed(f) for f in feeds_for_hazard(session, h)],
            "data_vintage": v.isoformat() if v else None,
            "mapped": bool(HAZARD_FEEDS.get(h)),
            "consumed_by": [{"framework": fw, "label": _report(fw)} for fw in used.get(h, [])],
        })

    # reporting datapoints by live report — each classified by where the data comes from (source category) and how it
    # enters the platform (lane), read from the canonical datapoint catalogue
    from services.governance.datapoint_catalog import CATALOG, coverage_source
    from services.governance.filings import retirement
    frameworks = []
    for fw, dps in CATALOG.items():
        if retirement(fw):                            # a retired report takes no data; its filings keep their own
            continue
        frameworks.append({
            "framework": fw, "label": _report(fw),
            "datapoints": [{"label": d["label"], "source_category": d["source_category"], "lane": d["lane"],
                            "provider": d["provider"], "note": d["note"], "coverage": coverage_source(d["lane"])}
                           for d in dps],
        })

    n_mapped = sum(1 for f in fields if f["mapped"])
    return {
        "fields": fields,
        "summary": {"hazard_fields": len(fields), "mapped_to_source": n_mapped,
                    "msg": render("intake.dictionary.summary", n=len(fields), mapped=n_mapped)},
        "frameworks": frameworks,
        "legend": {"source_category": {k: render(f"intake.dictionary.source.{k}") for k in SOURCE_CATEGORIES},
                   "lane": {k: render(f"intake.dictionary.lane.{k}") for k in LANES}},
    }
