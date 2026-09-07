"""Glue for the independent lens: submitted cells (intake) vs cells rebuilt from the shadow book (engine)."""
from __future__ import annotations

from typing import Optional

from services.geo.org_assets import org_asset_points
from services.governance.pillar3_templates import _section
from services.supervision.lens import compare, rebuild_cells


def _geo(p: dict) -> Optional[str]:
    return (p.get("country") or "").upper() or None


def _sector(p: dict) -> Optional[str]:
    s = _section(p.get("nace_code") or p.get("sector"))
    return s if s and s != "?" else None


def rebuilt_cells(session, regulator_org_id: str, subject_org_id: str, scenario: str, horizon: str) -> tuple[dict, list[dict]]:
    pts = org_asset_points(session, regulator_org_id, scenario, horizon, source="supervisor_shadow", subject_org_id=subject_org_id)
    return rebuild_cells(pts, _geo, _sector), pts


def build_lens(session, regulator_org_id: str, subject_org_id: str, submission: dict, reg_scenario: str, reg_horizon: str,
               precision_label: str) -> dict:
    """submission = supervisor_submissions row (basis + cells). Rebuild at the regulator's basis and, if the bank
    states a different one in its narrative, at the bank's too — that is what separates the 'basis' term."""
    reg_cells, pts = rebuilt_cells(session, regulator_org_id, subject_org_id, reg_scenario, reg_horizon)
    basis = submission.get("basis") or {}
    bank_sc, bank_hz = basis.get("scenario") or reg_scenario, basis.get("horizon") or reg_horizon
    bank_cells = rebuilt_cells(session, regulator_org_id, subject_org_id, bank_sc, bank_hz)[0] if (bank_sc, bank_hz) != (reg_scenario, reg_horizon) else None
    n_loc = sum(1 for p in pts if p.get("lat") is not None)
    prec = {p.get("location_precision") or "unlocated": 0 for p in pts}
    for p in pts:
        prec[p.get("location_precision") or "unlocated"] += 1
    # If the shadow book has no scenario-specific projections yet, the bank-basis rebuild equals the regulator's
    # (the engine carries baseline forward) — then the basis term is NOT separable and we say so, never a silent 0.
    separable = bank_cells is not None and any(
        (bank_cells.get(k, {}).get("sensitive_physical_eur") != v.get("sensitive_physical_eur")) for k, v in reg_cells.items())
    out = compare(submission["cells"], reg_cells, bank_cells if separable else None, precision=precision_label,
                  basis_separable=(bank_cells is None) or separable)
    out.update({"period_label": submission["period_label"], "regulator_basis": {"scenario": reg_scenario, "horizon": reg_horizon},
                "bank_basis": {"scenario": bank_sc, "horizon": bank_hz, "stated": bool(basis.get("scenario") or basis.get("horizon")),
                               "method_note": basis.get("method_note"),
                               "separable": (bank_cells is None) or separable,
                               "note": (None if bank_cells is None or separable else
                                        "the shadow book has no scenario projections yet, so the basis effect cannot be separated from scoring")},
                "shadow_book": {"n_rows": len(pts), "n_located": n_loc, "n_scored": sum(1 for p in pts if p.get("score") is not None),
                                "location_precision": prec},
                "tier": 2})
    return out
