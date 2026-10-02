"""The parameters a monetary figure depends on — read only here, from data/reference/money/parameters.json.

A method or parameter the institution chooses (its materiality level, its damage curve, its event frequencies, its
premium loadings …) is its own statement: a provided value of the family 'method' for the financial year, attested by
a second person (services.governance.provided_data). The platform supplies no default. An engine asks for what it
needs through `Method` and gets either the stated value or None; every None is recorded as a named gap, so the figure
it would have produced is reported as that gap — never computed from a guess.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

_REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "money" / "parameters.json"
FAMILY = "method"


@lru_cache(maxsize=1)
def register() -> dict:
    return json.loads(_REF.read_text())


def parameters() -> dict[str, dict]:
    return register()["parameters"]


def members(breakdown: str) -> list[str]:
    """The closed list of members of a breakdown ('band', 'peril_band')."""
    from core.hazard_taxonomy import EU_TAXONOMY, EXTRA_CHANNELS
    from core.types import RiskBucket
    bands = [b.value for b in RiskBucket]
    perils = [*sorted({c.value for h in (*EU_TAXONOMY, *EXTRA_CHANNELS) for c in h.internal}), "any"]
    if breakdown == "band":
        return bands
    if breakdown == "peril":
        return perils
    if breakdown == "peril_band":
        return [f"{p}/{b}" for p in perils for b in bands]
    if breakdown == "nace_division":
        return list(_divisions())
    if breakdown == "epc_grade":
        from ml.scoring.epc_stranding import EPC_ORDER
        return list(EPC_ORDER)
    from core.types import SCENARIO_VALUES, TIME_HORIZON_VALUES
    sh = [f"{s}/{h}" for s in SCENARIO_VALUES for h in TIME_HORIZON_VALUES]
    if breakdown == "scenario_horizon":
        return sh
    if breakdown == "division_scenario_horizon":
        return [f"{d}@{x}" for d in (*_divisions(), "any") for x in sh]
    raise KeyError(breakdown)


@lru_cache(maxsize=1)
def _divisions() -> tuple[str, ...]:
    import csv
    with (_REF.parents[1] / "nace_rev2.csv").open() as f:
        return tuple(r["code"] for r in csv.DictReader(f) if r["level"] == "division")


class Method:
    """The institution's stated methods and parameters for one financial year, read once. `gaps` collects what was
    asked for and is not stated (parameter key, member) — a figure that needed it is a gap naming it."""

    def __init__(self, session, org_id: str, period_end: date):
        from services.governance.provided_data import attested_values
        self.period_end = period_end
        self._values = {(v["concept"], v.get("member")): v for v in attested_values(session, org_id, FAMILY, period_end)}
        self.gaps: set[tuple[str, str | None]] = set()
        self.used: set[tuple[str, str | None]] = set()

    def get(self, key: str, member: str | None = None) -> float | None:
        if key not in parameters():
            raise KeyError(f"{key} is not a registered parameter (data/reference/money/parameters.json)")
        v = self._values.get((key, member))
        if v is None or v.get("value") is None:
            self.gaps.add((key, member))
            return None
        self.used.add((key, member))
        return float(v["value"])

    @classmethod
    def of(cls, values: dict, period_end: date) -> "Method":
        """A method from given values {(key, member | None): number} — a what-if, or a test; never a filing's."""
        m = cls.__new__(cls)
        m.period_end = period_end
        m._values = {k: {"value": v} for k, v in values.items()}
        m.gaps, m.used = set(), set()
        return m

    def per_peril(self, key: str, peril: str | None, band: str | None = None) -> float | None:
        """A value stated by peril (and band): the peril's own, else the institution's 'any' value — a gap names the
        peril's member when neither is stated."""
        if peril is None:
            return None
        own, fallback = (f"{peril}/{band}", f"any/{band}") if band is not None else (peril, "any")
        for m in (own, fallback):
            v = self._values.get((key, m))
            if v is not None and v.get("value") is not None:
                self.used.add((key, m))
                return float(v["value"])
        return self.get(key, own)

    def per_division(self, key: str, division: str | None, scenario: str, horizon: str) -> float | None:
        """A value stated per NACE division under a scenario and horizon: the division's own, else the institution's
        'any' value for that scenario and horizon."""
        if division is None:
            return self.per_peril(key, None)
        for m in (f"{division}@{scenario}/{horizon}", f"any@{scenario}/{horizon}"):
            v = self._values.get((key, m))
            if v is not None and v.get("value") is not None:
                self.used.add((key, m))
                return float(v["value"])
        return self.get(key, f"{division}@{scenario}/{horizon}")

    def provenance(self, key: str, member: str | None = None) -> dict | None:
        v = self._values.get((key, member))
        return None if v is None else {"key": key, "member": member, "value": v["value"], "attested_by": v.get("attested_by"),
                                       "attested_at": v.get("attested_at")}

    def record(self) -> dict:
        """What the figures read: the stated values used (with who attested them) and what was missing — frozen with a
        filing so its every money figure traces to the method it was computed on."""
        return {"period_end": self.period_end.isoformat(),
                "used": [self.provenance(k, m) for k, m in sorted(self.used, key=lambda x: (x[0], x[1] or ""))],
                "gaps": [{"key": k, "member": m} for k, m in sorted(self.gaps, key=lambda x: (x[0], x[1] or ""))]}

    def gap_text(self) -> str | None:
        """'not stated: method.damage_ratio (flood/H), method.at_risk_level' — or None when nothing is missing."""
        if not self.gaps:
            return None
        return "not stated: " + ", ".join(sorted(k + (f" ({m})" if m else "") for k, m in self.gaps))


def for_org(session, org_id: str, period_end: date | None = None) -> Method:
    """The organisation's method for the reporting period (its configured period end unless one is given)."""
    if period_end is None:
        from services.governance.filings import reporting_period_end
        period_end = reporting_period_end(session, org_id)
    return Method(session, org_id, period_end)


def at_risk(method: Method, score: float | None) -> bool | None:
    """At material physical risk: the score at or above the institution's stated level (method.at_risk_level); None when
    the level is not stated (a gap), False when unscored."""
    if score is None:
        return False
    level = method.get("method.at_risk_level")
    return None if level is None else float(score) >= level
