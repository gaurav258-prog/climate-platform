"""A mortgaged building's energy use for the governed intake (template bank_building_energy; PCAF Part A, 3rd ed., §5.5).

One row per loan and energy source, the loan named by its asset ID from the loan tape — what PCAF's equation sums over
(energy consumed × the emission factor of each source, p. 84):

  energy source     a fuel burned in the building (scope 1) or bought electricity, heating or cooling (scope 2);
                    biomass is refused with its reason (§6.1 reports its biogenic CO2 apart, not carried yet)
  energy basis      where the figure comes from — it sets the data quality score (Table 5.5-1): metered; per m² from the
                    official energy label; per m² or per building from statistics for the building's type and place
  the figure        a year's kWh (metered; per building, with the number of buildings), or kWh per m² a year (label,
                    statistics per m²: multiplied by the loan's floor area)
  emission factor   kg CO2e per kWh, the supplier's own or the average for the area (with where it comes from)
  year              the year the figure describes: a building's emissions read its most recent year's rows (§6.1: the
                    most recent data available), so a source of an earlier year that a later year does not state is
                    not summed into it

A row is refused with a message the bank can act on; nothing is guessed (services/scoring/pcaf_mortgages.py computes).
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.sector_contract import RowIssue, Sector, _f, _i, _s, _vocab, field_name

_FIELDS = ("energy_source", "energy_basis", "annual_kwh", "kwh_per_m2", "buildings", "emission_factor_kg_per_kwh",
           "emission_factor_type", "emission_factor_source", "energy_year")
_LOAN = """(SELECT e.entity_id FROM portfolio_entities e WHERE e.org_id = CAST(:org_id AS uuid) AND e.vertical = 'banking'
             AND e.source = 'own' AND e.external_ref = :loan_ref)"""


def _prepare(session: Session, org_id: str) -> dict:
    loans = {r[0] for r in session.execute(text("""
        SELECT external_ref FROM portfolio_entities
        WHERE org_id = CAST(:o AS uuid) AND vertical = 'banking' AND source = 'own' AND external_ref IS NOT NULL
    """), {"o": org_id}).all()}
    return {"loans": loans}


def _build(ctx: dict, row: dict) -> dict:
    from services.scoring.pcaf_mortgages import reference
    spec = reference()["mortgages"]
    ref = _s(row, "loan_ref")
    if not ref or (ref not in ctx["loans"] and ref not in ctx.get("in_file", {}).get("loans", ())):
        raise RowIssue(f"loan '{ref}' is not in your loan book — use its asset ID as on your loan tape")
    source, basis = _vocab(row, "energy_source", "energy_source"), _vocab(row, "energy_basis", "energy_basis")
    if source is None or basis is None:
        raise RowIssue(f"{field_name('energy_source')} and {field_name('energy_basis').lower()} are required")
    if source in spec["energy_sources"]["not_built"]:
        raise RowIssue("wood or other biomass: its biogenic CO2 is reported apart from the scopes, which is not supported "
                       "yet — leave this source out")
    kwh, per_m2, n = _f(row, "annual_kwh"), _f(row, "kwh_per_m2"), _i(row, "buildings")
    for k, v in (("annual_kwh", kwh), ("kwh_per_m2", per_m2)):
        if v is not None and v < 0:
            raise RowIssue(f"{field_name(k)} cannot be negative")
    need = spec["energy_bases"][basis]
    given = {"annual_kwh": kwh, "kwh_per_m2": per_m2}
    if given[need["value"]] is None:
        raise RowIssue(f"{field_name(need['value'])} is required for this energy figure")
    other = "kwh_per_m2" if need["value"] == "annual_kwh" else "annual_kwh"
    if given[other] is not None:
        raise RowIssue(f"give {field_name(need['value'])} only: {field_name(other)} is for another kind of energy figure")
    if need.get("times") == "buildings":
        if n is None or n < 1:
            raise RowIssue(f"{field_name('buildings')} is required (1 or more) for an energy figure per building")
    elif n is not None:
        raise RowIssue(f"{field_name('buildings')} is only for an energy figure per building")
    ef, ef_type = _f(row, "emission_factor_kg_per_kwh"), _vocab(row, "emission_factor_type", "emission_factor_type")
    if ef is not None and ef < 0:
        raise RowIssue(f"{field_name('emission_factor_kg_per_kwh')} cannot be negative")
    if ef is not None and ef_type is None:
        raise RowIssue(f"say the {field_name('emission_factor_type').lower()}: the supplier's own or the average for the area")
    if ef is None and ef_type is not None:
        raise RowIssue(f"{field_name('emission_factor_type')} is given without the {field_name('emission_factor_kg_per_kwh')}")
    year = _i(row, "energy_year")
    if year is None:
        raise RowIssue(f"{field_name('energy_year')} is required")
    return {"external_ref": f"{ref}|{source}", "loan_ref": ref, "energy_source": source, "energy_basis": basis,
            "annual_kwh": kwh, "kwh_per_m2": per_m2, "buildings": n, "emission_factor_kg_per_kwh": ef,
            "emission_factor_type": ef_type, "emission_factor_source": _s(row, "emission_factor_source"),
            "energy_year": year, "latitude": None, "longitude": None}


def _existing(session: Session, org_id: str) -> list[dict]:
    return [{**dict(r), "external_ref": f"{r['loan_ref']}|{r['energy_source']}", "latitude": None, "longitude": None}
            for r in session.execute(text("""
        SELECT b.energy_id::text AS entity_id, e.external_ref AS loan_ref, b.energy_source, b.energy_basis,
               CAST(b.annual_kwh AS FLOAT) AS annual_kwh, CAST(b.kwh_per_m2 AS FLOAT) AS kwh_per_m2, b.buildings,
               CAST(b.emission_factor_kg_per_kwh AS FLOAT) AS emission_factor_kg_per_kwh, b.emission_factor_type,
               b.emission_factor_source, b.energy_year
        FROM bank_building_energy b JOIN portfolio_entities e ON e.entity_id = b.entity_id
        WHERE b.org_id = CAST(:o AS uuid)"""), {"o": org_id}).mappings().all()]


def _insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r.setdefault("entity_id", str(uuid.uuid4()))
        r["org_id"] = org_id
    session.execute(text(f"""
        INSERT INTO bank_building_energy (energy_id, org_id, entity_id, {", ".join(_FIELDS)})
        SELECT CAST(:entity_id AS uuid), CAST(:org_id AS uuid), {_LOAN}, :energy_source, :energy_basis, :annual_kwh,
               :kwh_per_m2, :buildings, :emission_factor_kg_per_kwh, :emission_factor_type, :emission_factor_source,
               :energy_year"""), recs)


def _update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r["org_id"] = org_id
    session.execute(text(f"""
        UPDATE bank_building_energy SET {", ".join(f"{k} = :{k}" for k in _FIELDS[1:])}, updated_at = now()
        WHERE energy_id = CAST(:entity_id AS uuid) AND org_id = CAST(:org_id AS uuid)"""), recs)


BUILDING_ENERGY = Sector("bank_building_energy", "loan_ref", "_no_value", _FIELDS[1:],
                         _prepare, _build, _existing, _insert, _update,
                         table="bank_building_energy", id_column="energy_id", asset_book=False)
