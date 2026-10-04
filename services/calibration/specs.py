"""Calibration recipes (E162): where each one comes from.

  legacy     a fit published before the pipeline: its recipe is what it was fitted with (box, season, SPEI scale,
             driver) and the production series the audit ledger records for it — never re-chosen. The bearing cycle is
             removed by the current rule (the crop registry's life_cycle), so a fit made under an older rule is
             re-run under today's and any difference goes to review.
  registry   a crop × origin the registry and the protocol generate (services.calibration.registry_specs)
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.features.crop_registry import is_alternate_bearing
from services.calibration.gates import protocol

_SOURCE = re.compile(r"Production source '([^']+)'")


class SpecError(ValueError):
    pass


def ledger_source(session: Session, commodity: str, origin: str, driver: str) -> tuple[str, str]:
    """(production source, ledger run id) the audit ledger last recorded for a published fit — refused when none."""
    r = session.execute(text("""
        SELECT run_id::text, notes FROM validation_run
        WHERE method = 'loo_cv' AND scope = :scope AND hazard_type = :hz AND notes LIKE '%Production source%'
        ORDER BY created_at DESC LIMIT 1"""), {"scope": f"{commodity}/{origin}", "hz": f"crop_{driver}"}).mappings().first()
    m = _SOURCE.search(r["notes"]) if r else None
    if not m:
        raise SpecError(f"{commodity}/{origin} {driver}: the audit ledger records no production source — a recipe "
                        "is never built on a guessed series")
    return m.group(1), r["run_id"]


def create(session: Session, **sp) -> str:
    """Record a recipe; one active recipe per slot (crop × origin × yield region × driver)."""
    return session.execute(text("""
        INSERT INTO crop_calibration_specs (commodity, origin, yield_source, yield_region, driver, weather_kind,
               weather_key, season_months, season_prev_months, spei_scale, allow_cycle, basis, protocol)
        VALUES (:commodity, :origin, :yield_source, :yield_region, :driver, :weather_kind, :weather_key, :season_months,
                :season_prev_months, :spei_scale, :allow_cycle, :basis, :protocol)
        RETURNING spec_id::text"""), {"yield_region": "", "season_prev_months": [], "spei_scale": 6, **sp}).scalar()


def legacy(session: Session) -> list[dict]:
    """A recipe for every published fit whose slot has none yet. Returns the recipes created."""
    out = []
    for f in session.execute(text("""
            SELECT c.name, f.origin, f.hazard_driver, f.region_key, f.season_months, f.spei_scale, f.fit_version,
                   f.created_at
            FROM sc_commodity_fit f JOIN sc_commodities c ON c.commodity_id = f.commodity_id
            WHERE NOT EXISTS (SELECT 1 FROM crop_calibration_specs s WHERE s.retired_at IS NULL AND s.commodity = c.name
                              AND s.origin = f.origin AND s.yield_region = '' AND s.driver = f.hazard_driver)
            ORDER BY c.name, f.origin, f.hazard_driver""")).mappings():
        if not f["region_key"] or not f["season_months"]:
            raise SpecError(f"{f['name']}/{f['origin']} {f['hazard_driver']}: the published fit records no box or season")
        source, ledger_run = ledger_source(session, f["name"], f["origin"], f["hazard_driver"])
        sp = {"commodity": f["name"], "origin": f["origin"], "yield_source": source, "driver": f["hazard_driver"],
              "weather_kind": "box", "weather_key": f["region_key"], "season_months": list(f["season_months"]),
              "spei_scale": f["spei_scale"] or 6, "allow_cycle": is_alternate_bearing(f["name"]),
              "basis": (f"published fit before the pipeline ({f['fit_version']}, {f['created_at']:%Y-%m-%d}); production "
                        f"source as the audit ledger records it (validation run {ledger_run})"),
              "protocol": protocol()["protocol"]}
        out.append({**sp, "spec_id": create(session, **sp)})
    return out
