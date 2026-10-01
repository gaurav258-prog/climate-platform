"""The hazard → money core: the ONE place a hazard score becomes a share of value (E69).

A hazard score is validated as a RANKING of places (core/hazard_taxonomy.py CALIBRATED_VALIDATION: 'not a loss or
damage anchor'); every loss-anchored validation run failed its gate. So no money figure is derived from the score
by a schedule of the platform's own. The shares below are the INSTITUTION'S stated method (services.money.params —
provided values of the family 'method', per financial year, attested by a second person), read by peril and by the
band of the platform's score (core.types.score_to_bucket), with the institution's 'any' value for a peril it does not
state separately. Not stated → None, recorded as a named gap on the Method; the caller reports that gap.

  valuation_haircut        share of an asset's value the institution discounts for physical risk
  damage_ratio             share of value lost if a damaging event occurs
  annual_event_probability probability of a damaging event in a year
"""
from __future__ import annotations

from typing import Optional

from core.types import score_to_bucket

DAMAGE_FUNCTION_VERSION = "df-v3.0-stated"     # every share is the institution's stated method, by peril and band


def band(score: Optional[float]) -> Optional[str]:
    return None if score is None else score_to_bucket(float(score)).value


def _stated(method, key: str, hazard: Optional[str], score: Optional[float]) -> Optional[float]:
    b = band(score)
    return None if b is None or hazard is None else method.per_peril(key, hazard, b)


def valuation_haircut(method, hazard: Optional[str], score: Optional[float]) -> Optional[float]:
    return _stated(method, "method.valuation_haircut", hazard, score)


def damage_ratio(method, hazard: Optional[str], score: Optional[float]) -> Optional[float]:
    return _stated(method, "method.damage_ratio", hazard, score)


def event_probability(method, hazard: Optional[str], score: Optional[float]) -> Optional[float]:
    return _stated(method, "method.annual_event_probability", hazard, score)
