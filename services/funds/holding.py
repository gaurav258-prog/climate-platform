"""A holding by ISIN and the issuer data a manager may state with it — the shape every door shares (moved from
api/routers/funds.py, 2026-10-23, so the API and the asset manager's standard file read one definition).

  Holding / HoldingsUpload   one line of a fund's book, and the book as the API receives it
  financials_eur(...)        the issuer's revenue, EVIC and physical asset value in EUR, with where each came from
  apply_enrichment(...)      the issuer data a holding states, written where each figure is kept
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from core.errors import UserError
from ml.regulatory.voluntary_pai import CATALOG as _VOLUNTARY_CATALOG
from services.reference.emissions_estimation import estimate_emissions


class Holding(BaseModel):
    isin: str
    # Supply EITHER market_value_eur (already in EUR) OR market_value + currency
    # (native, converted to EUR at the book's as-of date). Exactly one is required.
    market_value_eur: Optional[float] = Field(None, gt=0)  # value in EUR
    market_value: Optional[float] = Field(None, gt=0)      # value in the position's native currency
    weight_pct: Optional[float] = None                  # if omitted, derived from value share
    asset_class: Optional[str] = None                   # equity / corporate_bond / sovereign_bond / … (None → default equity on first resolve)
    currency: Optional[str] = None                      # ISO 4217 of market_value — required with it, never assumed

    @model_validator(mode="after")
    def _one_value(self) -> "Holding":
        # A row the file cannot hold is refused in the catalogue's words, naming the row's ISIN (a UserError is not a
        # ValueError, so it passes through pydantic to the API's handler as {error, message, detail}, status 422).
        isin = (self.isin or "").strip() or "—"
        if self.market_value_eur is None and self.market_value is None:
            raise UserError("filings.holding.no_value", isin=isin)
        native = (self.revenue, self.evic, self.physical_asset_value)
        if any(n is not None and e is not None for n, e in zip(native, (self.revenue_eur, self.evic_eur,
                                                                       self.physical_asset_value_eur))):
            raise UserError("filings.holding.financials_twice", isin=isin)
        if any(n is not None for n in native) and not (self.financials_currency or "").strip():
            raise UserError("filings.holding.financials_currency", isin=isin)
        if any(n is not None for n in native) and self.financials_date is None and self.reporting_year is None:
            raise UserError("filings.holding.financials_date", isin=isin)
        for basis, aligned, gas, nuc in (
                ("turnover", self.taxonomy_aligned_pct, self.taxonomy_fossil_gas_aligned_pct, self.taxonomy_nuclear_aligned_pct),
                ("CapEx", self.taxonomy_aligned_capex_pct, self.taxonomy_fossil_gas_aligned_capex_pct,
                 self.taxonomy_nuclear_aligned_capex_pct)):
            if (gas is not None or nuc is not None) and aligned is None:
                raise UserError("filings.holding.taxonomy_parts_alone", isin=isin, basis=basis)
            if aligned is not None and (gas or 0) + (nuc or 0) > aligned + 1e-9:
                raise UserError("filings.holding.taxonomy_parts_exceed", isin=isin, basis=basis,
                                parts=f"{(gas or 0) + (nuc or 0):g}", aligned=f"{aligned:g}")
        return self
    # ── Optional issuer data the client already holds (fills SFDR gaps) ──
    nace_code: Optional[str] = None                     # issuer industry → EU Taxonomy + fossil-fuel PAI
    sector: Optional[str] = None
    revenue_eur: Optional[float] = Field(None, gt=0)    # denominator for carbon intensity / WACI — already in EUR
    revenue: Optional[float] = Field(None, gt=0)        # …or the issuer's revenue in `financials_currency` (a yearly flow)
    scope1_tco2e: Optional[float] = Field(None, ge=0)
    scope2_tco2e: Optional[float] = Field(None, ge=0)
    scope3_tco2e: Optional[float] = Field(None, ge=0)
    evic_eur: Optional[float] = Field(None, gt=0)       # enterprise value incl. cash → PCAF attribution (PAI 1/2), in EUR
    evic: Optional[float] = Field(None, gt=0)           # …or EVIC in `financials_currency` (a balance)
    # the issuer's physical asset value — buildings, plant, machinery and contents, land excluded: what the share of value
    # a site loses is a share of (the holdings look-through, decided 2026-10-22) — in EUR, or in `financials_currency`
    physical_asset_value_eur: Optional[float] = Field(None, gt=0)
    physical_asset_value: Optional[float] = Field(None, gt=0)
    financials_currency: Optional[str] = None           # ISO 4217 of revenue / evic — required with them, never assumed
    financials_date: Optional[date] = None              # the date the financials describe (default: 31 Dec of reporting_year):
                                                        # revenue at the average of the 12 months to it, EVIC at its rate
    reporting_year: Optional[int] = None
    # ── Non-carbon ESG facts (SFDR PAI 5-14), from the manager's ESG feed ──
    non_renewable_energy_pct: Optional[float] = Field(None, ge=0, le=100)       # PAI 5 as one combined share
    non_renewable_consumption_pct: Optional[float] = Field(None, ge=0, le=100)  # PAI 5 — consumption share (EET 30420)
    non_renewable_production_pct: Optional[float] = Field(None, ge=0, le=100)   # PAI 5 — production share, producers (EET 30460)
    energy_consumption_gwh: Optional[float] = Field(None, ge=0)                 # company energy use — PAI 6 with revenue
    energy_intensity_gwh_per_meur: Optional[float] = Field(None, ge=0)          # PAI 6 as reported (GWh per €M revenue)
    biodiversity_sensitive_ops: Optional[bool] = None   # PAI 7
    emissions_to_water_tonnes: Optional[float] = None    # PAI 8
    hazardous_waste_tonnes: Optional[float] = None       # PAI 9
    ungc_oecd_violation: Optional[bool] = None           # PAI 10
    ungc_oecd_no_monitoring: Optional[bool] = None       # PAI 11
    gender_pay_gap_pct: Optional[float] = None           # PAI 12
    board_female_pct: Optional[float] = None             # PAI 13
    controversial_weapons: Optional[bool] = None         # PAI 14
    # EU Taxonomy — the issuer's own Article-8 reported figures. taxonomy_aligned_pct
    # is the TURNOVER-based KPI (% of revenue); taxonomy_aligned_capex_pct is the
    # CapEx-based KPI (% of capital expenditure) — Annex III/IV require both, shown
    # side by side, never blended into one figure.
    taxonomy_eligible_pct: Optional[float] = Field(None, ge=0, le=100)
    taxonomy_aligned_pct: Optional[float] = Field(None, ge=0, le=100)          # turnover-based
    taxonomy_aligned_capex_pct: Optional[float] = Field(None, ge=0, le=100)    # CapEx-based
    # the fossil gas and nuclear parts of the aligned shares (Delegated Regulation (EU) 2022/1214, Annex XII Template
    # 1-2): what the SFDR product templates ask whether the product invested in (2022/1288 Annex IV / V)
    taxonomy_fossil_gas_aligned_pct: Optional[float] = Field(None, ge=0, le=100)        # turnover-based
    taxonomy_nuclear_aligned_pct: Optional[float] = Field(None, ge=0, le=100)           # turnover-based
    taxonomy_fossil_gas_aligned_capex_pct: Optional[float] = Field(None, ge=0, le=100)  # CapEx-based
    taxonomy_nuclear_aligned_capex_pct: Optional[float] = Field(None, ge=0, le=100)     # CapEx-based
    # DNSH / minimum-safeguards attestation. NULL = not separately assessed (take
    # reported aligned as-is); False = known to fail → that issuer's aligned excluded.
    taxonomy_dnsh_ok: Optional[bool] = None
    taxonomy_min_safeguards_ok: Optional[bool] = None
    # Voluntary (additional) PAI values, keyed by catalog indicator_key → number or bool.
    voluntary_pai: Optional[dict] = None


class HoldingsUpload(BaseModel):
    as_of_date: Optional[date] = None
    holdings: list[Holding]
    # the file states the fund's COMPLETE book on as_of_date: a position held on that date and not in it (sold) is
    # removed — refused unless every line was positioned (E145). Without it a file adds to / updates the date's book.
    complete_book: bool = False


def financials_eur(session, h: "Holding", org_id: str | None = None) -> dict:
    """The issuer's revenue, EVIC and physical asset value in EUR: as given in EUR, or converted from financials_currency
    at the financials date — revenue (a yearly flow) at the average of the 12 months to it, EVIC and the physical asset
    value (balances) at its closing rate. The amounts as sent and the rates are kept (money_source). Raises MoneyError."""
    from services.intake.money import convert_amount, source_record
    given = {"revenue_eur": h.revenue_eur, "evic_eur": h.evic_eur, "physical_asset_value_eur": h.physical_asset_value_eur}
    if h.revenue is None and h.evic is None and h.physical_asset_value is None:
        return {**given, "money_source": None}
    d = h.financials_date or date(h.reporting_year, 12, 31)
    ccy = h.financials_currency.strip().upper()
    conv = {}
    if h.revenue is not None:
        conv["revenue_eur"] = convert_amount(session, h.revenue, ccy, d, flow=True, label="issuer revenue", org_id=org_id)
    if h.evic is not None:
        conv["evic_eur"] = convert_amount(session, h.evic, ccy, d, label="issuer EVIC", org_id=org_id)
    if h.physical_asset_value is not None:
        conv["physical_asset_value_eur"] = convert_amount(session, h.physical_asset_value, ccy, d,
                                                          label="issuer physical asset value", org_id=org_id)
    return {**{k: conv[k]["eur"] if k in conv else v for k, v in given.items()},
            "money_source": source_record(ccy, d, conv, origin="fund_holdings")}


def apply_enrichment(session, issuer_id: str, org_id: str, h: "Holding") -> dict:
    """Persist the issuer data a client supplied on a holding. Returns which
    fields were written. NACE/sector is a shared fact (enrich only when unknown,
    never clobber); emissions/revenue are the client's PRIVATE disclosure,
    org-scoped and marked source='client' — never a fabricated value."""
    wrote = {"sector": False, "emissions": False, "estimated": False, "esg": False, "voluntary": False}

    if h.nace_code or h.sector:
        session.execute(text("""
            UPDATE issuers
               SET nace_code = COALESCE(nace_code, :nace),
                   sector    = COALESCE(sector, :sector),
                   updated_at = now()
             WHERE issuer_id = :i
        """), {"i": issuer_id, "nace": h.nace_code, "sector": h.sector})
        wrote["sector"] = True

    from services.intake.money import MoneyError
    try:
        fin = financials_eur(session, h, org_id)
    except MoneyError as e:
        wrote["financials_error"] = str(e)
        fin = {"revenue_eur": None, "evic_eur": None, "physical_asset_value_eur": None, "money_source": None}
    rev_eur, evic_eur, pav_eur = fin["revenue_eur"], fin["evic_eur"], fin["physical_asset_value_eur"]
    if rev_eur is not None or h.scope1_tco2e is not None or evic_eur is not None or pav_eur is not None:
        session.execute(text("""
            INSERT INTO issuer_emissions
                (issuer_id, org_id, reporting_year, scope1_tco2e, scope2_tco2e, scope3_tco2e,
                 revenue_eur, evic_eur, physical_asset_value_eur, source, data_vintage, money_source)
            VALUES (:i, :org, :yr, :s1, :s2, :s3, :rev, :evic, :pav, 'client', now(), CAST(:ms AS jsonb))
            ON CONFLICT (issuer_id, reporting_year, source, org_id) WHERE org_id IS NOT NULL
            -- COALESCE so a partial follow-up (e.g. EVIC only) fills gaps without
            -- erasing figures supplied earlier.
            DO UPDATE SET scope1_tco2e = COALESCE(EXCLUDED.scope1_tco2e, issuer_emissions.scope1_tco2e),
                          scope2_tco2e = COALESCE(EXCLUDED.scope2_tco2e, issuer_emissions.scope2_tco2e),
                          scope3_tco2e = COALESCE(EXCLUDED.scope3_tco2e, issuer_emissions.scope3_tco2e),
                          revenue_eur  = COALESCE(EXCLUDED.revenue_eur, issuer_emissions.revenue_eur),
                          evic_eur     = COALESCE(EXCLUDED.evic_eur, issuer_emissions.evic_eur),
                          physical_asset_value_eur = COALESCE(EXCLUDED.physical_asset_value_eur,
                                                              issuer_emissions.physical_asset_value_eur),
                          data_vintage = EXCLUDED.data_vintage,
                          money_source = jsonb_build_object('fields',
                              COALESCE(issuer_emissions.money_source->'fields', '{}'::jsonb) ||
                              COALESCE(EXCLUDED.money_source->'fields', '{}'::jsonb))
        """), {"i": issuer_id, "org": org_id, "yr": h.reporting_year or date.today().year,
               "s1": h.scope1_tco2e, "s2": h.scope2_tco2e, "s3": h.scope3_tco2e,
               "rev": rev_eur, "evic": evic_eur, "pav": pav_eur, "ms": json.dumps(fin["money_source"], default=str) if fin["money_source"] else None})
        wrote["emissions"] = True

    # Estimation gap-fill: revenue + sector but no disclosed scope → estimate
    # scope 1+2 (sector intensity × revenue), stored source='estimated', method
    # disclosed. Never overrides a real scope the client gave.
    if h.scope1_tco2e is None and rev_eur:
        nace = h.nace_code or session.execute(
            text("SELECT nace_code FROM issuers WHERE issuer_id = :i"), {"i": issuer_id}).scalar()
        est = estimate_emissions(nace, rev_eur)
        if est:
            session.execute(text("""
                INSERT INTO issuer_emissions
                    (issuer_id, org_id, reporting_year, scope1_tco2e, revenue_eur,
                     source, estimation_method, data_vintage)
                VALUES (:i, :org, :yr, :s12, :rev, 'estimated', :method, now())
                ON CONFLICT (issuer_id, reporting_year, source, org_id) WHERE org_id IS NOT NULL
                DO UPDATE SET scope1_tco2e = EXCLUDED.scope1_tco2e, revenue_eur = EXCLUDED.revenue_eur,
                              estimation_method = EXCLUDED.estimation_method, data_vintage = EXCLUDED.data_vintage
            """), {"i": issuer_id, "org": org_id, "yr": h.reporting_year or date.today().year,
                   "s12": est["scope1_2_tco2e"], "rev": rev_eur, "method": est["method"]})
            wrote["estimated"] = True

    # Non-carbon ESG facts (PAI 5-14) — org-scoped private disclosure.
    esg_fields = {
        "non_renewable_energy_pct": h.non_renewable_energy_pct,
        "non_renewable_consumption_pct": h.non_renewable_consumption_pct,
        "non_renewable_production_pct": h.non_renewable_production_pct,
        "energy_consumption_gwh": h.energy_consumption_gwh,
        "energy_intensity_gwh_per_meur": h.energy_intensity_gwh_per_meur,
        "biodiversity_sensitive_ops": h.biodiversity_sensitive_ops,
        "emissions_to_water_tonnes": h.emissions_to_water_tonnes,
        "hazardous_waste_tonnes": h.hazardous_waste_tonnes,
        "ungc_oecd_violation": h.ungc_oecd_violation,
        "ungc_oecd_no_monitoring": h.ungc_oecd_no_monitoring,
        "gender_pay_gap_pct": h.gender_pay_gap_pct,
        "board_female_pct": h.board_female_pct,
        "controversial_weapons": h.controversial_weapons,
        "dnsh_ok": h.taxonomy_dnsh_ok,
        "min_safeguards_ok": h.taxonomy_min_safeguards_ok,
    }
    if any(v is not None for v in esg_fields.values()):
        cols = ", ".join(esg_fields)
        placeholders = ", ".join(f":{k}" for k in esg_fields)
        updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in esg_fields)
        session.execute(text(f"""
            INSERT INTO issuer_esg_metrics (issuer_id, org_id, reporting_year, {cols}, source, data_vintage)
            VALUES (:i, :org, :yr, {placeholders}, 'client', now())
            ON CONFLICT (issuer_id, reporting_year, org_id) WHERE org_id IS NOT NULL
            DO UPDATE SET {updates}, data_vintage = now()
        """), {"i": issuer_id, "org": org_id, "yr": h.reporting_year or date.today().year, **esg_fields})
        wrote["esg"] = True
    # the issuer's own Taxonomy KPIs — to the one store of them (services.issuer_taxonomy)
    from services.issuer_taxonomy import write_stated
    stated = {"taxonomy_eligible_pct": h.taxonomy_eligible_pct, "taxonomy_aligned_pct": h.taxonomy_aligned_pct,
              "taxonomy_aligned_capex_pct": h.taxonomy_aligned_capex_pct,
              "taxonomy_fossil_gas_aligned_pct": h.taxonomy_fossil_gas_aligned_pct,
              "taxonomy_nuclear_aligned_pct": h.taxonomy_nuclear_aligned_pct,
              "taxonomy_fossil_gas_aligned_capex_pct": h.taxonomy_fossil_gas_aligned_capex_pct,
              "taxonomy_nuclear_aligned_capex_pct": h.taxonomy_nuclear_aligned_capex_pct}
    if any(v is not None for v in stated.values()):
        write_stated(session, issuer_id, org_id, h.reporting_year or date.today().year, stated)
        wrote["taxonomy"] = True

    # Voluntary (additional) PAI values — org-scoped. Each must be an adoptable indicator of the governing spec with a
    # value of the kind its metric needs (yes/no for a share, a number otherwise); anything else is refused and reported
    # back to the uploader, never silently dropped (error log E24).
    if h.voluntary_pai:
        yr = h.reporting_year or date.today().year
        for key, val in h.voluntary_pai.items():
            entry = _VOLUNTARY_CATALOG.get(key)
            if entry is None:
                wrote.setdefault("voluntary_rejected", []).append({"key": key, "reason": "not an adoptable indicator",
                                                                   "code": "disclose.fund.onboard.indicator_unknown"})
                continue
            wants_flag = entry["agg"] == "share"
            if wants_flag != isinstance(val, bool) or (not wants_flag and not isinstance(val, (int, float))):
                wrote.setdefault("voluntary_rejected", []).append(
                    {"key": key, "reason": "needs yes/no (true/false)" if wants_flag else "needs a number",
                     "code": "disclose.fund.onboard.indicator_flag" if wants_flag else "disclose.fund.onboard.indicator_number"})
                continue
            num = val if not wants_flag else None
            flag = val if wants_flag else None
            session.execute(text("""
                INSERT INTO issuer_voluntary_pai (issuer_id, org_id, indicator_key, reporting_year, value_num, value_bool, source)
                VALUES (:i, :org, :k, :yr, :num, :flag, 'client')
                ON CONFLICT (issuer_id, org_id, indicator_key, reporting_year)
                DO UPDATE SET value_num = EXCLUDED.value_num, value_bool = EXCLUDED.value_bool, data_vintage = now()
            """), {"i": issuer_id, "org": org_id, "k": key, "yr": yr, "num": num, "flag": flag})
        wrote["voluntary"] = True

    return wrote
