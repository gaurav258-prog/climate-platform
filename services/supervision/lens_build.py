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


def rebuilt_cells(session, regulator_org_id: str, subject_org_id: str, scenario: str, horizon: str,
                  level: float) -> tuple[dict, list[dict]]:
    pts = org_asset_points(session, regulator_org_id, scenario, horizon, source="supervisor_shadow", subject_org_id=subject_org_id)
    return rebuild_cells(pts, _geo, _sector, level), pts


def build_lens(session, regulator_org_id: str, subject_org_id: str, submission: dict, reg_scenario: str, reg_horizon: str,
               precision_label: str) -> dict:
    """submission = supervisor_submissions row (basis + cells). Rebuild at the regulator's basis (its scenario, horizon
    and stated at-risk level) and, where the bank's differs, at the bank's too — that is what separates the 'basis'
    term. Without the regulator's own level there is no rebuilt figure: {"available": False, "gap": …}."""
    from services.supervision.levels import GAP_AUTHORITY, GAP_ENTITY, authority_level, entity_level
    reg_level = authority_level(session, regulator_org_id)
    if reg_level is None:
        return {"available": False, "gap": GAP_AUTHORITY}
    ent_level, ent_level_from = entity_level(session, subject_org_id, submission)
    reg_cells, pts = rebuilt_cells(session, regulator_org_id, subject_org_id, reg_scenario, reg_horizon, reg_level)
    basis = submission.get("basis") or {}
    bank_sc, bank_hz = basis.get("scenario") or reg_scenario, basis.get("horizon") or reg_horizon
    bank_level = ent_level if ent_level is not None else reg_level
    bank_cells = (rebuilt_cells(session, regulator_org_id, subject_org_id, bank_sc, bank_hz, bank_level)[0]
                  if (bank_sc, bank_hz, bank_level) != (reg_scenario, reg_horizon, reg_level) else None)
    n_loc = sum(1 for p in pts if p.get("lat") is not None)
    prec = {p.get("location_precision") or "unlocated": 0 for p in pts}
    for p in pts:
        prec[p.get("location_precision") or "unlocated"] += 1
    # The basis term is separable only when the shadow book actually carries forward anchors (scenario × horizon
    # rows). Without them the engine carries today's value forward and a "0" would be a lie; with them a 0 is a
    # real finding (e.g. cells already at the top bucket under both bases). Coverage decides, not the result.
    from services.supervision.projection import projection_coverage, shadow_cells
    cov = projection_coverage(session, shadow_cells(session, regulator_org_id, subject_org_id))
    separable = bank_cells is None or bool(cov.get("complete"))
    out = compare(submission["cells"], reg_cells, bank_cells if separable else None, precision=precision_label,
                  basis_separable=separable)
    out["available"] = True
    out["at_risk_level"] = {"regulator": reg_level, "entity": ent_level, "entity_from": ent_level_from,
                            **({"gap": GAP_ENTITY + " — the scoring term may include a difference of definition"}
                               if ent_level is None else {})}
    out["projection_coverage"] = cov
    out.update({"period_label": submission["period_label"], "regulator_basis": {"scenario": reg_scenario, "horizon": reg_horizon},
                "bank_basis": {"scenario": bank_sc, "horizon": bank_hz, "stated": bool(basis.get("scenario") or basis.get("horizon")),
                               "method_note": basis.get("method_note"),
                               "separable": (bank_cells is None) or separable,
                               "note": (None if separable else
                                        f"scenario projections cover {cov.get('cells_complete', 0)} of {cov.get('cells', 0)} locations — run the projections "
                                        "on the intake screen; until then the basis effect cannot be separated from scoring")},
                "shadow_book": {"n_rows": len(pts), "n_located": n_loc, "n_scored": sum(1 for p in pts if p.get("score") is not None),
                                "location_precision": prec},
                "tier": 2})
    return out
