"""User-selectable projection horizons — resolve any target year onto the engine's modelled anchor nodes.

The physical-risk engine is MODELLED only at discrete anchor years (≈2025 'now', 2030, 2050, 2100 — the
CMIP6/AR6 nodes we ingest). Bankers, though, decide on near-term / maturity-matched horizons, so the
operational surfaces let the user pick any year. This module maps a requested horizon token to a fetch plan:

  • an anchor label ('current' / '2030' / '2050' / '2100')  → exact, read that node
  • a year that lands on an anchor                            → exact
  • a year BETWEEN two anchors                               → interpolate, linearly, between the bracketing
                                                               nodes (flagged interpolated=True so the UI /
                                                               audit trail can label it — we never present an
                                                               interpolated year as an independently modelled one)

Near-term is honest by construction: over a few years the warming signal is tiny, so an interpolated +3y sits
very close to 'now' — which is the truth about near-term physical-climate change. The far anchors stay exact
where the disclosure regimes cite them (Pillar 3 IEA NZE2050, TCFD long-term).
"""
from __future__ import annotations

# (year, canonical time_horizon label in v_portfolio_entity_physical_risk). NOW is 2025.
ANCHORS: list[tuple[int, str]] = [(2025, "current"), (2030, "2030"), (2050, "2050"), (2100, "2100")]
ANCHOR_LABELS = {lbl for _, lbl in ANCHORS}
NOW_YEAR = ANCHORS[0][0]
_LABEL_YEAR = {lbl: yr for yr, lbl in ANCHORS}


def label_year(label: str) -> int:
    """The calendar year an anchor label represents (2025 for 'current')."""
    return _LABEL_YEAR.get(label, NOW_YEAR)


def resolve(horizon: str | int | None) -> dict:
    """Map a requested horizon to a fetch plan.

    Returns either
      {'kind': 'exact',  'label': <anchor label>, 'year': int, 'interpolated': False}
    or
      {'kind': 'interp', 'lo': <label>, 'hi': <label>, 'w': float, 'year': int, 'interpolated': True}
    where the interpolated value = lo + (hi - lo) * w. Unknown / empty input falls back to 'current'.
    """
    if horizon in ANCHOR_LABELS:
        return {"kind": "exact", "label": horizon, "year": label_year(horizon), "interpolated": False}
    try:
        y = int(horizon)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return {"kind": "exact", "label": "current", "year": NOW_YEAR, "interpolated": False}

    lo_year, hi_year = ANCHORS[0][0], ANCHORS[-1][0]
    if y <= lo_year:
        return {"kind": "exact", "label": "current", "year": NOW_YEAR, "interpolated": False}
    if y >= hi_year:
        return {"kind": "exact", "label": ANCHORS[-1][1], "year": hi_year, "interpolated": False}
    for (ly, ll), (uy, ul) in zip(ANCHORS, ANCHORS[1:]):
        if ly <= y <= uy:
            if y == ly:
                return {"kind": "exact", "label": ll, "year": ly, "interpolated": False}
            if y == uy:
                return {"kind": "exact", "label": ul, "year": uy, "interpolated": False}
            return {"kind": "interp", "lo": ll, "hi": ul, "w": (y - ly) / (uy - ly), "year": y, "interpolated": True}
    return {"kind": "exact", "label": "current", "year": NOW_YEAR, "interpolated": False}


def lerp(a: float | None, b: float | None, w: float) -> float | None:
    """Linear blend a→b by weight w∈[0,1]; tolerant of a missing endpoint (returns the other)."""
    if a is None:
        return b
    if b is None:
        return a
    return a + (b - a) * w


def labels_needed(plan: dict) -> list[str]:
    """The anchor label(s) a plan must read from the risk view."""
    return [plan["label"]] if plan["kind"] == "exact" else [plan["lo"], plan["hi"]]
