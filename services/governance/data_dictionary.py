"""Data dictionary — the single golden model, on screen.

The platform sources data once into one canonical model and reuses it across every reporting area. This
lists that model's fields: each hazard (the scored field), the source feed(s) it derives from with their
live maturity/freshness, how current the golden source is (latest data vintage), and which reports consume
it. It's the "source once" story made browsable — read straight from the feed registry and the golden source,
so nothing is invented.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# which frameworks consume a physical-risk hazard field (all physical-risk reports read the same golden layer)
_HAZARD_CONSUMERS = ["TCFD", "SFDR", "CSRD/ESRS", "EUDR"]


def data_dictionary(session: Session) -> dict:
    from services.data.feeds import HAZARD_FEEDS, feeds_for_hazard
    from core.types import HazardType

    # latest golden-source vintage per hazard (how current the data behind each field is)
    vintages = {r[0]: r[1] for r in session.execute(text("""
        SELECT hazard_type, MAX(data_vintage) FROM canonical_scores
        WHERE valid_to IS NULL AND score_lane = 'standing' GROUP BY hazard_type
    """)).all()}

    fields = []
    for hz in HazardType:
        h = hz.value
        feeds = feeds_for_hazard(session, h)
        v = vintages.get(h)
        fields.append({
            "field": h, "category": "hazard", "type": "score 0–100",
            "source_feeds": [{"name": f["name"], "maturity": f["maturity"], "status": f["status"]} for f in feeds],
            "data_vintage": v.isoformat() if v else None,
            "mapped": bool(HAZARD_FEEDS.get(h)),
            "consumed_by": _HAZARD_CONSUMERS,
        })

    # reference-data fields (identity + estimated emissions), for completeness
    reference = [
        {"field": "issuer_lei", "category": "reference", "type": "LEI (ISO 17442)",
         "source_feeds": [{"name": "GLEIF (LEI)", "maturity": "live", "status": None}],
         "data_vintage": None, "mapped": True, "consumed_by": ["SFDR", "TCFD"]},
        {"field": "financed_emissions", "category": "reference", "type": "tCO₂e (PCAF)",
         "source_feeds": [{"name": "Sector-intensity estimates (NACE)", "maturity": "estimated", "status": None}],
         "data_vintage": None, "mapped": True, "consumed_by": ["SFDR", "TCFD"]},
    ]

    # reporting datapoints by framework — each classified by where the data comes from (source category)
    # and how it enters Tellumen (ingestion lane), read from the canonical datapoint catalog.
    from services.governance.datapoint_catalog import CATALOG, coverage_source
    from services.governance.reg_reference import reference as _ref
    frameworks = []
    for fw, dps in CATALOG.items():
        ref = _ref(fw) or {}
        frameworks.append({
            "framework": fw,
            "label": ref.get("official_name", fw),
            "datapoints": [{"label": d["label"], "source_category": d["source_category"], "lane": d["lane"],
                            "provider": d["provider"], "note": d["note"], "coverage": coverage_source(d["lane"])}
                           for d in dps],
        })

    return {
        "fields": fields + reference,
        "summary": {
            "hazard_fields": len(fields),
            "mapped_to_source": sum(1 for f in fields if f["mapped"]),
            "note": "One golden model, sourced once on the H3 cell and reused across every reporting area.",
        },
        "frameworks": frameworks,
        "legend": {
            "source_category": {
                "tellumen": "Our engine + authoritative feeds (the physical & nature moat)",
                "egov": "Free government / agency dataset we integrate",
                "evendor": "Commercial 3rd-party dataset you license",
                "customer": "Your proprietary data / judgement / narrative",
                "none": "Not produced by this platform",
            },
            "lane": {
                "compute": "Tellumen computes it (no input step)",
                "granular": "You upload raw data; we process it",
                "provided": "You / your vendor pre-calculate; we reconcile it",
                "report": "Final input captured on the filing form",
                "none": "Out of scope",
            },
        },
    }
