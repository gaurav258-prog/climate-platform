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
    """A submission's stated basis as it enters: the at-risk level, when given, is a headline score in [0, 100] — checked
    here, never guessed later. Raises ValueError naming the problem."""
    b = {k: v for k, v in dict(basis or {}).items() if v not in (None, "")}
    if "at_risk_level" in b:
        try:
            lvl = float(str(b["at_risk_level"]).strip())
        except ValueError:
            raise ValueError("at_risk_level must be a number (a headline score 0–100)") from None
        if not 0 <= lvl <= 100:
            raise ValueError("at_risk_level must be between 0 and 100")
        b["at_risk_level"] = lvl
    return b


GAP_AUTHORITY = "not stated: method.at_risk_level (your own at-risk level — the yardstick of your population views)"
GAP_ENTITY = ("the entity's at-risk level for this template is not stated (in its submission basis, or its method on the "
              "platform) — its sensitive share cannot be read on the definition it used")
