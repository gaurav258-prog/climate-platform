"""
Shared portfolio engine — ONE implementation of "fetch this org's entities,
join today's physical-risk score, pick a headline hazard/bucket, apply the
org's calc-settings triggers, compute a valuation/discount block, support a
human override" — replacing 4 near-identical hand-duplicated implementations
across banking/insurance/real-estate/asset-management (see the
b9c0d1e2f3a4 migration's docstring for why that duplication existed and what
bugs it caused: the heat_acute contamination bug and every calc-settings
trigger/override endpoint had to be written 4 times instead of once).

Each vertical supplies, via fetch_entities_with_risk():
  - vertical: 'banking' | 'insurance' | 'realestate' | 'assetmgmt'
  - ext_table / ext_columns: the extension table + raw SQL select fragments
    for the fields unique to that vertical -- e.g. "CAST(x.annual_revenue_eur
    AS FLOAT) AS annual_revenue_eur" (the caller owns the alias AND any cast,
    since NUMERIC columns arrive as Decimal otherwise and break arithmetic
    against the base table's already-float primary_value_eur). Omit both for
    asset management, which needs no extension table at all.
  - extra_calc: optional hook (row, headline, hazards) -> dict for a
    vertical-specific calculation layered on the shared valuation block
    (real estate's NOI impact + taxonomy status, insurance's premium
    pricing). The returned dict is MERGED into the row as top-level keys
    (not nested) -- e.g. real estate's hook returns {"noi_impact":...,
    "taxonomy_status":...} and both land as row["noi_impact"]/
    row["taxonomy_status"], matching the exact field names each vertical's
    API response has always had.

Rollup math stays per-vertical (banking's LTV, insurance's premium totals,
real estate's NOI, asset-management's climate-VaR% are genuinely different
questions) — only the fetch/join/headline/valuation/override layer is shared.

Agriculture (sc_sourcing_plots) does not use this engine — see the migration
docstring for why forcing a bill-of-materials graph into this shape would be
the wrong kind of uniformity.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import text

from ml.scoring.valuation_discount import valuation_block

VERTICALS = ("banking", "insurance", "realestate", "assetmgmt")


def fetch_entities_with_risk(
    session, org_id: str, vertical: str, scenario: str, horizon: str,
    severity_model: str = "universal",
    ext_table: Optional[str] = None, ext_columns: Optional[list] = None,
    extra_calc: Optional[Callable] = None,
    exclude_headline_hazards: tuple = ("heat_acute",),
    valuation_kwargs: Optional[Callable] = None,
    entity_ids: Optional[list] = None,
    value_weights: Optional[dict] = None,
) -> list:
    """All of an org's entities for one vertical (metadata + extension fields)
    + their per-hazard projected risk + shared valuation block. exclude_headline_hazards
    keeps heat_acute (today's live ERA5 reading) out of the STANDING headline/valuation
    calc everywhere except where a caller explicitly needs the full hazard list
    (e.g. insurance's parametric triggers, which read `hazards` directly, not headline).
    valuation_kwargs(row) -> dict lets one vertical (banking) pass extra valuation_block
    kwargs (outstanding_balance_eur, for LTV) without every vertical needing that concept."""
    ext_select = (", " + ", ".join(ext_columns)) if ext_columns else ""
    ext_join = f"LEFT JOIN {ext_table} x ON x.entity_id = e.entity_id" if ext_table else ""
    # entity_ids scopes the book to a set of reporting entities (a legal entity, or a group's whole subtree)
    # for per-entity / consolidated reporting; None = the whole org (the implicit top scope).
    scope = "AND e.reporting_entity_id = ANY(:eids)" if entity_ids else ""
    params = {"o": org_id, "v": vertical}
    if entity_ids:
        params["eids"] = list(entity_ids)
    entities = session.execute(text(f"""
        SELECT e.entity_id::text AS entity_id, e.entity_name, e.entity_type, e.sector, e.nace_code,
               CAST(e.latitude AS FLOAT) AS lat, CAST(e.longitude AS FLOAT) AS lon, e.h3_cell,
               e.country, e.region, CAST(e.primary_value_eur AS FLOAT) AS primary_value_eur,
               e.construction_type, e.year_built, e.number_of_stories,
               e.borrower_entity_id, e.minimum_safeguards_status,
               e.reporting_entity_id::text AS reporting_entity_id
               {ext_select}
        FROM portfolio_entities e
        {ext_join}
        WHERE e.org_id = :o AND e.vertical = :v {scope}
        ORDER BY e.primary_value_eur DESC
    """), params).mappings().all()

    # Horizon can be a modelled anchor ('current'/'2030'/'2050'/'2100') OR any user-picked year — an
    # intermediate year is blended between the two bracketing anchor nodes ALONG THE WARMING CURVE for this
    # scenario (global-warming-level weighting, not calendar-linear — see intelligence.horizon / intelligence.gwl).
    from core.types import score_to_bucket
    from services.intelligence.horizon import labels_needed, lerp
    from services.intelligence.horizon import resolve as _resolve_horizon
    plan = _resolve_horizon(horizon, scenario)
    risks = session.execute(text("""
        SELECT entity_id::text AS entity_id, hazard_type, time_horizon,
               physical_risk_score AS score, risk_bucket, model_version, scored_at,
               physical_risk_ci_lower AS ci_lo, physical_risk_ci_upper AS ci_hi
        FROM v_portfolio_entity_physical_risk
        WHERE org_id = :o AND vertical = :v AND scenario = :s AND time_horizon = ANY(:hs)
    """), {"o": org_id, "v": vertical, "s": scenario, "hs": labels_needed(plan)}).mappings().all()

    by_entity = defaultdict(list)
    if plan["kind"] == "exact":
        for r in risks:
            by_entity[r["entity_id"]].append({
                "hazard": r["hazard_type"], "score": round(r["score"], 1),
                "bucket": r["risk_bucket"], "model_version": r["model_version"],
                "scored_at": r["scored_at"],
                "ci_lo": round(r["ci_lo"], 1) if r["ci_lo"] is not None else None,
                "ci_hi": round(r["ci_hi"], 1) if r["ci_hi"] is not None else None,
            })
    else:
        # interpolate each (entity, hazard) linearly between the low and high anchor nodes
        w = plan["w"]
        pair: dict = defaultdict(dict)   # (entity, hazard) -> {label: row}
        for r in risks:
            pair[(r["entity_id"], r["hazard_type"])][r["time_horizon"]] = r
        for (eid, hazard), bylbl in pair.items():
            lo, hi = bylbl.get(plan["lo"]), bylbl.get(plan["hi"])
            # A forward horizon shows a (entity, hazard) only if it is modelled at BOTH bracketing anchors —
            # the same coverage rule an exact anchor applies (it needs its own node). Carrying an asset that
            # has only the lower node into an interpolated future would fabricate coverage and can invert the
            # trajectory (a near-term hump above both 'now' and the next anchor). Require both; then interpolate.
            if lo is None or hi is None:
                continue
            sc = lerp(lo["score"], hi["score"], w)
            by_entity[eid].append({
                "hazard": hazard, "score": round(sc, 1),
                "bucket": score_to_bucket(sc).value, "model_version": hi["model_version"],
                "scored_at": hi["scored_at"],
                "ci_lo": round(lerp(lo["ci_lo"], hi["ci_lo"], w), 1)
                         if lo["ci_lo"] is not None and hi["ci_lo"] is not None else None,
                "ci_hi": round(lerp(lo["ci_hi"], hi["ci_hi"], w), 1)
                         if lo["ci_hi"] is not None and hi["ci_hi"] is not None else None,
            })

    # Scenario-flat fallback. Susceptibility/state hazards that do not vary by scenario (subsidence, permafrost,
    # severe-convective environment, the erosion/degradation/marine layers, …) are stored only at
    # baseline/current. A forward-scenario report must still surface them — carried flat — otherwise a real
    # physical hazard silently vanishes at 2050. Carry a hazard's baseline value forward ONLY where it has NO
    # row under the requested scenario at ANY horizon, so scenario-VARYING hazards (and the interpolation
    # coverage rule above) are never touched and nothing is double-counted.
    if scenario != "baseline":
        scen_pairs = {(r["entity_id"], r["hazard_type"]) for r in session.execute(text("""
            SELECT DISTINCT entity_id::text AS entity_id, hazard_type
            FROM v_portfolio_entity_physical_risk WHERE org_id = :o AND vertical = :v AND scenario = :s
        """), {"o": org_id, "v": vertical, "s": scenario}).mappings().all()}
        for r in session.execute(text("""
            SELECT entity_id::text AS entity_id, hazard_type,
                   physical_risk_score AS score, risk_bucket, model_version, scored_at,
                   physical_risk_ci_lower AS ci_lo, physical_risk_ci_upper AS ci_hi
            FROM v_portfolio_entity_physical_risk
            WHERE org_id = :o AND vertical = :v AND scenario = 'baseline' AND time_horizon = 'current'
        """), {"o": org_id, "v": vertical}).mappings().all():
            if (r["entity_id"], r["hazard_type"]) in scen_pairs:
                continue                              # varies by scenario — its own rows already handled it
            by_entity[r["entity_id"]].append({
                "hazard": r["hazard_type"], "score": round(r["score"], 1),
                "bucket": r["risk_bucket"], "model_version": r["model_version"], "scored_at": r["scored_at"],
                "ci_lo": round(r["ci_lo"], 1) if r["ci_lo"] is not None else None,
                "ci_hi": round(r["ci_hi"], 1) if r["ci_hi"] is not None else None,
            })

    valuations = session.execute(text("""
        SELECT entity_id::text AS entity_id, CAST(override_discount_pct AS FLOAT) AS override_discount_pct,
               overridden_by::text AS overridden_by, overridden_at, reason
        FROM portfolio_entity_valuations WHERE entity_id IN (
            SELECT entity_id FROM portfolio_entities WHERE org_id = :o AND vertical = :v
        )
    """), {"o": org_id, "v": vertical}).mappings().all()
    val_by_entity = {v["entity_id"]: dict(v) for v in valuations}

    out = []
    for e in entities:
        hz = sorted(by_entity.get(e["entity_id"], []), key=lambda x: -x["score"])
        priceable = [h for h in hz if h["hazard"] not in exclude_headline_hazards]
        headline = priceable[0] if priceable else None
        bucket = headline["bucket"] if headline else None
        hazard = headline["hazard"] if headline else None

        # consolidation weighting: a proportional/equity line contributes only its owned share of VALUE
        # (physical risk SCORES are per-asset and unchanged; scaling the value flows through to every
        # value-based aggregate — value-at-risk, financed emissions, taxonomy €). Full lines weight 1.0.
        ev = dict(e)
        w = value_weights.get(e["reporting_entity_id"], 1.0) if value_weights else 1.0
        if w != 1.0 and ev["primary_value_eur"] is not None:
            ev["primary_value_eur"] = ev["primary_value_eur"] * w

        extra_val_kwargs = valuation_kwargs(ev) if valuation_kwargs else {}
        attrs = {"construction_type": ev["construction_type"], "year_built": ev["year_built"],
                 "number_of_stories": ev["number_of_stories"]}
        row = {
            **ev,
            "hazards": hz,
            "headline_score": headline["score"] if headline else None,
            "headline_bucket": bucket,
            "headline_hazard": hazard,
            "valuation": valuation_block(bucket, ev["primary_value_eur"], val_by_entity.get(ev["entity_id"]),
                                          hazard=hazard, severity_model=severity_model,
                                          score=(headline["score"] if headline else None), attrs=attrs,
                                          **extra_val_kwargs),
        }
        if extra_calc:
            row.update(extra_calc(row, headline, hz))
        out.append(row)
    return out


def get_entity_with_risk(session, entity_id: str, scenario: str, horizon: str,
                          severity_model: str = "universal",
                          ext_table: Optional[str] = None, ext_columns: Optional[list] = None,
                          extra_calc: Optional[Callable] = None,
                          exclude_headline_hazards: tuple = ("heat_acute",),
                          valuation_kwargs: Optional[Callable] = None,
                          scope_headline_to_query: bool = True):
    """One entity, any scenario/horizon it's been scored for -- the '/asset/{id}'-
    style detail endpoint every vertical has its own copy of today.
    scope_headline_to_query=False reproduces banking's pre-existing asset_detail
    behavior: this endpoint takes no scenario/horizon params, so its headline is
    picked across EVERY scenario/horizon this entity has ever been scored under
    -- a real, pre-existing quirk (it can disagree with the portfolio list's
    scenario-scoped headline for the same asset), preserved here rather than
    silently "fixed" mid-refactor."""
    ext_select = (", " + ", ".join(ext_columns)) if ext_columns else ""
    ext_join = f"LEFT JOIN {ext_table} x ON x.entity_id = e.entity_id" if ext_table else ""
    e = session.execute(text(f"""
        SELECT e.entity_id::text AS entity_id, e.org_id::text AS org_id, e.entity_name, e.entity_type,
               e.sector, e.nace_code, CAST(e.latitude AS FLOAT) AS lat, CAST(e.longitude AS FLOAT) AS lon,
               e.h3_cell, e.country, e.region, CAST(e.primary_value_eur AS FLOAT) AS primary_value_eur,
               e.construction_type, e.year_built, e.number_of_stories,
               e.borrower_entity_id, e.minimum_safeguards_status
               {ext_select}
        FROM portfolio_entities e
        {ext_join}
        WHERE e.entity_id = :i
    """), {"i": entity_id}).mappings().first()
    if not e:
        return None

    risks = session.execute(text("""
        SELECT hazard_type, scenario, time_horizon,
               physical_risk_score AS score, risk_bucket, model_version, scored_at,
               physical_risk_ci_lower AS ci_lo, physical_risk_ci_upper AS ci_hi
        FROM v_portfolio_entity_physical_risk WHERE entity_id = :i
        ORDER BY hazard_type, scenario, time_horizon
    """), {"i": entity_id}).mappings().all()

    scoped = ([r for r in risks if r["scenario"] == scenario and r["time_horizon"] == horizon]
              if scope_headline_to_query else risks)
    # Normalize to the SAME {hazard, score, bucket, ...} shape fetch_entities_with_risk's
    # by_entity list uses (as opposed to scoped's raw hazard_type/risk_bucket SQL-row keys) --
    # extra_calc hooks are documented as one contract shared by both entry points, and
    # insurance's hook reads headline["hazard"]/hz-item["hazard"] directly (see
    # api/routers/insurance.py's _insurance_extra), which silently KeyErrored against the
    # raw shape before this normalization existed.
    hz_norm = [{"hazard": r["hazard_type"], "score": round(r["score"], 1), "bucket": r["risk_bucket"],
                "model_version": r["model_version"], "scored_at": r["scored_at"]} for r in scoped]
    priceable = [h for h in hz_norm if h["hazard"] not in exclude_headline_hazards]
    headline = sorted(priceable, key=lambda h: -h["score"])[0] if priceable else None
    bucket = headline["bucket"] if headline else None
    hazard = headline["hazard"] if headline else None

    val_row = get_valuation_row(session, entity_id)
    extra_val_kwargs = valuation_kwargs(e) if valuation_kwargs else {}
    attrs = {"construction_type": e["construction_type"], "year_built": e["year_built"],
             "number_of_stories": e["number_of_stories"]}
    row = {
        **{k: e[k] for k in e.keys()},
        "risks": [dict(r) for r in risks],
        "headline_score": headline["score"] if headline else None,
        "headline_bucket": bucket,
        "headline_hazard": hazard,
        "valuation": valuation_block(bucket, e["primary_value_eur"], val_row,
                                      hazard=hazard, severity_model=severity_model,
                                      score=(headline["score"] if headline else None), attrs=attrs,
                                      **extra_val_kwargs),
    }
    if extra_calc:
        row.update(extra_calc(row, headline, hz_norm))
    return row


def get_valuation_row(session, entity_id: str) -> Optional[dict]:
    return session.execute(text("""
        SELECT CAST(override_discount_pct AS FLOAT) AS override_discount_pct,
               overridden_by::text AS overridden_by, overridden_at, reason
        FROM portfolio_entity_valuations WHERE entity_id = :e
    """), {"e": entity_id}).mappings().first()


def get_entity_org(session, entity_id: str) -> Optional[str]:
    return session.execute(text("SELECT org_id::text FROM portfolio_entities WHERE entity_id = :e"),
                            {"e": entity_id}).scalar()


def apply_valuation_override(session, entity_id: str, discount_pct: float, user_id: str,
                              reason: Optional[str]) -> dict:
    prior = get_valuation_row(session, entity_id)
    from_pct = prior["override_discount_pct"] if prior else None
    now = datetime.now(timezone.utc)
    session.execute(text("""
        INSERT INTO portfolio_entity_valuations (entity_id, override_discount_pct, overridden_by, overridden_at, reason)
        VALUES (:e, :pct, :u, :now, :reason)
        ON CONFLICT (entity_id) DO UPDATE
            SET override_discount_pct = EXCLUDED.override_discount_pct,
                overridden_by = EXCLUDED.overridden_by,
                overridden_at = EXCLUDED.overridden_at,
                reason = EXCLUDED.reason
    """), {"e": entity_id, "pct": discount_pct, "u": user_id, "now": now, "reason": reason})
    return {"from_pct": from_pct, "to_pct": discount_pct, "overridden_at": now}


def clear_valuation_override(session, entity_id: str) -> Optional[dict]:
    prior = get_valuation_row(session, entity_id)
    if not prior:
        return None
    session.execute(text("DELETE FROM portfolio_entity_valuations WHERE entity_id = :e"), {"e": entity_id})
    return prior
