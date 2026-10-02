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


# Hazards never used as a built asset's HEADLINE: nowcast signals and the scales that do not apply to buildings
# (crop-frost, soil water, land degradation …). ONE definition — core.hazard_relevance — read here and mirrored in
# the hazard_relevance table for the SQL paths.
from core.hazard_relevance import headline_exclude as _headline_exclude  # noqa: E402
from core.hazard_relevance import is_headline_eligible as _eligible  # noqa: E402
from core.hazard_relevance import reason as _why_not  # noqa: E402

DEFAULT_HEADLINE_EXCLUDE: tuple = _headline_exclude("buildings")


def _relevant(hazard: str, model_version, exclude_headline_hazards: tuple) -> bool:
    """The registry decides per row (hazard × model version); an explicit caller-supplied exclusion list is honoured on top."""
    if exclude_headline_hazards is not DEFAULT_HEADLINE_EXCLUDE and hazard in exclude_headline_hazards:
        return False
    return _eligible(hazard, "buildings", model_version)


_EXT_WITH_MONEY_SOURCE = {"ext_banking"}          # extension tables whose amounts record where they came from


def fetch_entities_with_risk(
    session, org_id: str, vertical: str, scenario: str, horizon: str, *, method,
    ext_table: Optional[str] = None, ext_columns: Optional[list] = None,
    extra_calc: Optional[Callable] = None,
    exclude_headline_hazards: tuple = DEFAULT_HEADLINE_EXCLUDE,
    valuation_kwargs: Optional[Callable] = None,
    entity_ids: Optional[list] = None,
    value_weights: Optional[dict] = None,
    source: str = "own",
    subject_org_id: Optional[str] = None,
    translation=None,
) -> list:
    """All of an org's entities for one vertical (metadata + extension fields)
    + their per-hazard projected risk + shared valuation block. exclude_headline_hazards
    keeps heat_acute (today's live ERA5 reading) out of the STANDING headline/valuation
    calc everywhere except where a caller explicitly needs the full hazard list
    (e.g. insurance's parametric triggers, which read `hazards` directly, not headline).
    valuation_kwargs(row) -> dict lets one vertical (banking) pass extra valuation_block
    kwargs (outstanding_balance_eur, for LTV) without every vertical needing that concept.
    translation (services.governance.translation.Translation, filings only) presents every amount in the filing's
    currency and removes group-internal exposures; None = the stored EUR figures (live views).
    method (services.money.params.Method): the institution's stated method for the financial year the figures are for —
    the valuation haircut is read from it (a gap when not stated), never from a default."""
    ext_select = (", " + ", ".join(ext_columns)) if ext_columns else ""
    if ext_table in _EXT_WITH_MONEY_SOURCE:
        ext_select += ", x.money_source AS ext_money_source"
    ext_join = f"LEFT JOIN {ext_table} x ON x.entity_id = e.entity_id" if ext_table else ""
    # entity_ids scopes the book to a set of reporting entities (a legal entity, or a group's whole subtree)
    # for per-entity / consolidated reporting; None = the whole org (the implicit top scope).
    scope = "AND e.reporting_entity_id = ANY(:eids)" if entity_ids else ""
    params = {"o": org_id, "v": vertical, "src": source}
    if entity_ids:
        params["eids"] = list(entity_ids)
    # source='own' (default) = the org's own book; 'supervisor_shadow' = a regulator's rebuild of a supervised
    # entity's book from granular supervisory data, scoped to that subject — never mixed with anyone's own rows.
    subject = ""
    if subject_org_id:
        params["subj"] = subject_org_id
        subject = "AND e.subject_org_id = CAST(:subj AS uuid)"
    entities = session.execute(text(f"""
        SELECT e.entity_id::text AS entity_id, e.entity_name, e.entity_type, e.sector, e.nace_code,
               CAST(e.latitude AS FLOAT) AS lat, CAST(e.longitude AS FLOAT) AS lon, e.h3_cell,
               e.country, e.region, CAST(e.primary_value_eur AS FLOAT) AS primary_value_eur,
               e.construction_type, e.year_built, e.number_of_stories,
               e.borrower_entity_id, e.minimum_safeguards_status,
               e.reporting_entity_id::text AS reporting_entity_id, e.location_precision, e.external_ref,
               e.intragroup_entity_id::text AS intragroup_entity_id, e.money_source
               {ext_select}
        FROM portfolio_entities e
        {ext_join}
        WHERE e.org_id = :o AND e.vertical = :v AND e.source = :src {subject} {scope}
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

    from services.governance.translation import (
        OWN_STAKE,
        elimination_share,
        record_elimination,
        translate_row,
    )
    out = []
    for e in entities:
        hz = sorted(by_entity.get(e["entity_id"], []), key=lambda x: -x["score"])
        for h in hz:
            h["relevant"] = _relevant(h["hazard"], h.get("model_version"), exclude_headline_hazards)
            if not h["relevant"]:
                h["why_not"] = _why_not(h["hazard"], "buildings", h.get("model_version"))
        priceable = [h for h in hz if h["relevant"]]
        headline = priceable[0] if priceable else None
        bucket = headline["bucket"] if headline else None
        hazard = headline["hazard"] if headline else None

        # consolidation weighting: a proportional/equity line contributes only its owned share of VALUE
        # (physical risk SCORES are per-asset and unchanged; scaling the value flows through to every
        # value-based aggregate — value-at-risk, financed emissions, taxonomy €). Full lines weight 1.0.
        #
        # outstanding_loan_balance_eur (the bank vertical's PCAF exposure input) gets the SAME weight — fixed
        # 2026-09-23 (C4, independent consolidation-scope review): it used to stay unweighted while
        # primary_value_eur (used for value-at-risk/taxonomy € on the SAME snapshot) was correctly weighted,
        # so a proportionally/equity-consolidated bank's financed emissions silently overstated its owned
        # share — internally inconsistent numbers in one frozen filing. counterparty_evic_eur is NEVER
        # weighted: EVIC is the counterparty's own total enterprise value, not ours to scale by our stake —
        # it's the PCAF attribution factor's denominator, and scaling it would understate the attribution.
        #
        # Multi-currency phase 3 (2026-09-26): in a filing, every amount is first presented in the filing's currency
        # (translation.translate_row), then group-internal exposures are removed (elimination), then the stake weight
        # applies — to EVERY own-stake amount (translation.OWN_STAKE: values, balances, sums insured, rent, NOI; NOI and
        # rent used to stay unweighted), never to the counterparty's own figures (EVIC, its revenue).
        ev = dict(e)
        ms, ext_ms = ev.pop("money_source", None), ev.pop("ext_money_source", None)
        cp_ms = ev.pop("counterparty_money_source", None)     # a banking counterparty's own figures (bank_counterparties)
        if translation is not None:
            merged = {"fields": {**((cp_ms or {}).get("fields") or {}), **((ext_ms or {}).get("fields") or {}),
                                 **((ms or {}).get("fields") or {})}}
            translate_row(session, translation, ev, merged)
            share = elimination_share(translation, ev)
            if share > 0:
                record_elimination(translation, ev, share, ev.get("primary_value_eur"))
                if share >= 1.0:
                    continue                           # wholly group-internal: not part of the consolidated book
                for c in OWN_STAKE:
                    if ev.get(c) is not None:
                        ev[c] = float(ev[c]) * (1.0 - share)
        w = value_weights.get(e["reporting_entity_id"], 1.0) if value_weights else 1.0
        if w != 1.0:
            for c in OWN_STAKE:
                if ev.get(c) is not None:
                    ev[c] = float(ev[c]) * w

        extra_val_kwargs = valuation_kwargs(ev) if valuation_kwargs else {}
        row = {
            **ev,
            "hazards": hz,
            "headline_score": headline["score"] if headline else None,
            "headline_bucket": bucket,
            "headline_hazard": hazard,
            "valuation": valuation_block(method, bucket, ev["primary_value_eur"], val_by_entity.get(ev["entity_id"]),
                                          hazard=hazard, score=(headline["score"] if headline else None),
                                          **extra_val_kwargs),
        }
        if extra_calc:
            row.update(extra_calc(row, headline, hz))
        out.append(row)
    return out


def get_entity_with_risk(session, entity_id: str, scenario: str, horizon: str, *, method,
                          ext_table: Optional[str] = None, ext_columns: Optional[list] = None,
                          extra_calc: Optional[Callable] = None,
                          exclude_headline_hazards: tuple = DEFAULT_HEADLINE_EXCLUDE,
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
                "model_version": r["model_version"], "scored_at": r["scored_at"],
                "relevant": _relevant(r["hazard_type"], r["model_version"], exclude_headline_hazards)} for r in scoped]
    priceable = [h for h in hz_norm if h["relevant"]]
    headline = sorted(priceable, key=lambda h: -h["score"])[0] if priceable else None
    bucket = headline["bucket"] if headline else None
    hazard = headline["hazard"] if headline else None

    val_row = get_valuation_row(session, entity_id)
    extra_val_kwargs = valuation_kwargs(e) if valuation_kwargs else {}
    row = {
        **{k: e[k] for k in e.keys()},
        "risks": [dict(r) for r in risks],
        "headline_score": headline["score"] if headline else None,
        "headline_bucket": bucket,
        "headline_hazard": hazard,
        "valuation": valuation_block(method, bucket, e["primary_value_eur"], val_row,
                                      hazard=hazard, score=(headline["score"] if headline else None),
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


def exposure_by_hazard(entities: list, value_key: str, method) -> dict:
    """Per hazard: the value of the book at or above the institution's stated at-risk level (method.at_risk_level) on that
    hazard — None when the level is not stated (a gap) — with the number of entities, the highest score and the model.
    A hazard that cannot head an entity's risk (the relevance registry) is not counted as exposure. 'peril_class' is the
    Pillar 3 Template 5 class of the hazard (acute / chronic; None for a non-climate peril)."""
    from services.governance.pillar3_templates import ACUTE_HAZARDS, CHRONIC_HAZARDS
    from services.money.params import at_risk
    hazards: dict = {}
    for e in entities:
        for hz in e["hazards"]:
            k = hz["hazard"]
            h = hazards.setdefault(k, {"exposed_value_eur": 0.0, "n_exposed": 0, "max_score": 0.0,
                                       "model_version": hz["model_version"], "scored_at": hz["scored_at"],
                                       "peril_class": "acute" if k in ACUTE_HAZARDS else "chronic" if k in CHRONIC_HAZARDS else None})
            flag = at_risk(method, hz["score"]) if hz.get("relevant", True) else False
            if flag is None:
                h["exposed_value_eur"] = h["n_exposed"] = None
            elif flag and h["exposed_value_eur"] is not None:
                h["exposed_value_eur"] += e[value_key] or 0
                h["n_exposed"] += 1
            h["max_score"] = max(h["max_score"], hz["score"])
    for h in hazards.values():
        h["exposed_value_eur"] = None if h["exposed_value_eur"] is None else round(h["exposed_value_eur"])
        h["max_score"] = round(h["max_score"], 1)
    return hazards


def value_at_risk(entities: list, value_key: str, method) -> dict:
    """{value_at_risk_eur, pct_value_at_risk, n_at_risk, at_risk_level, at_risk_by_peril_class}: the value whose headline
    score is at or above the stated at-risk level, and the value at or above it on an acute / on a chronic peril (the
    Pillar 3 Template 5 split; an entity can be both) — all None when the level is not stated."""
    level = method.get("method.at_risk_level")
    if level is None:
        return {"value_at_risk_eur": None, "pct_value_at_risk": None, "n_at_risk": None, "at_risk_level": None,
                "at_risk_by_peril_class": None}
    from services.governance.pillar3_templates import _asset_hits
    total = sum(e[value_key] or 0 for e in entities)
    flags = [e["headline_score"] is not None and e["headline_score"] >= level for e in entities]
    var = sum(e[value_key] or 0 for e, f in zip(entities, flags) if f)
    hits = [_asset_hits(e, level) for e in entities]
    return {"value_at_risk_eur": round(var), "pct_value_at_risk": round(100 * var / total, 1) if total else 0,
            "n_at_risk": sum(flags), "at_risk_level": level,
            "at_risk_by_peril_class": {"acute_eur": round(sum(e[value_key] or 0 for e, (_, a) in zip(entities, hits) if a)),
                                       "chronic_eur": round(sum(e[value_key] or 0 for e, (c, _) in zip(entities, hits) if c))}}


def climate_adjusted_total(entities: list, value_key: str) -> dict:
    """The climate-adjusted value of the SCORED entities (an unscored one is not assessed — never counted undiscounted):
    a gap while any scored entity's discount is not stated."""
    scored = [e for e in entities if e["headline_score"] is not None]
    disc = [e["valuation"]["discounted_value_eur"] for e in scored]
    return {"total_discounted_value_eur": None if None in disc else round(sum(disc)),
            "scored_value_eur": round(sum(e[value_key] or 0 for e in scored))}


def at_risk_by(entities: list, value_key: str, group_key: str, method) -> dict | None:
    """{group: {value_eur, n}} of the entities at or above the stated at-risk level, by a field (e.g. region) — None when
    the level is not stated (a gap)."""
    from services.money.params import at_risk
    out: dict = {}
    for e in entities:
        flag = at_risk(method, e["headline_score"])
        if flag is None:
            return None
        if flag:
            g = out.setdefault(e.get(group_key) or "Unspecified", {"value_eur": 0.0, "n": 0})
            g["value_eur"] += e[value_key] or 0
            g["n"] += 1
    return {k: {"value_eur": round(v["value_eur"]), "n": v["n"]} for k, v in out.items()}
