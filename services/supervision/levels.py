"""Whose at-risk level a supervisory figure is read at (E69) — the platform supplies none.

  the entity's   — the level its submitted template was computed on: stated with the submission (its basis), frozen
                   there at submission when the entity states its method on the platform. The lens rebuild and the
                   plausibility band read a template at this level, so they compare like with like.
  the authority's — its own stated method.at_risk_level: the one yardstick of its population views (peer benchmark,
                   analytics, the regulator's side of the lens), so entities are compared on the same definition.
Not stated → None, and the figure that needs it is a named gap.
"""
from __future__ import annotations

from typing import Optional

LEVEL_KEY = "method.at_risk_level"


def authority_level(session, regulator_org_id: str) -> Optional[float]:
    from services.money.params import for_org
    return for_org(session, regulator_org_id).get(LEVEL_KEY)


def entity_level(session, subject_org_id: str, submission: Optional[dict]) -> tuple[Optional[float], Optional[str]]:
    """(level, where it came from): the submission's basis, else the entity's own stated method on the platform."""
    b = (submission or {}).get("basis") or {}
    if b.get("at_risk_level") is not None:
        return float(b["at_risk_level"]), "submission"
    from services.money.params import for_org
    lvl = for_org(session, subject_org_id).get(LEVEL_KEY)
    return (lvl, "entity_method") if lvl is not None else (None, None)


def with_entity_level(session, subject_org_id: str, basis: Optional[dict]) -> dict:
    """The basis a submission is frozen with: the level the entity states in it, else its stated method's for the period."""
    b = clean_basis(basis)
    if b.get("at_risk_level") is None:
        lvl, _ = entity_level(session, subject_org_id, None)
        if lvl is not None:
            b["at_risk_level"] = lvl
    return b


def clean_basis(basis: Optional[dict]) -> dict:
    """A submission's stated basis as it enters, checked here, never guessed later: the at-risk level, when given, is a
    headline score in [0, 100]; the scenario and horizon, when given, are ones the lens can rebuild at (the projection
    anchors). Raises ValueError naming the problem in the reader's words."""
    from services.supervision.projection import HORIZONS, SCENARIOS
    b = {k: v for k, v in dict(basis or {}).items() if v not in (None, "")}
    if "at_risk_level" in b:
        try:
            lvl = float(str(b["at_risk_level"]).strip())
        except ValueError:
            raise ValueError("The at-risk level must be a number from 0 to 100.") from None
        if not 0 <= lvl <= 100:
            raise ValueError("The at-risk level must be a number from 0 to 100.")
        b["at_risk_level"] = lvl
    if "scenario" in b and b["scenario"] not in SCENARIOS:
        raise ValueError("The stated scenario is not one of the platform's scenarios.")
    if "horizon" in b and str(b["horizon"]) not in HORIZONS:
        raise ValueError("The stated year must be today, 2030, 2050 or 2100.")
    return b


GAP_AUTHORITY = "not stated: method.at_risk_level (your own at-risk level — the yardstick of your population views)"
GAP_ENTITY = ("the entity's at-risk level for this template is not stated (in its submission basis, or its method on the "
              "platform) — its sensitive share cannot be read on the definition it used")
