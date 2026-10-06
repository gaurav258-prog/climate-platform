"""Published damage curves (E169): one file per curve family under data/reference/vulnerability/, transcribed from
the publisher's own table with the page and table quoted, and the source file's checksum. A curve is never fitted
here; the institution adopts a family per peril as its stated method, and an asset's occupancy and region select the
curve within it.

A family file:
  family, peril, metric, unit           e.g. "huizinga_2017", "flood", "water_depth", "m" — the metric and unit of an
                                        intensity layer of the same peril (data/reference/hazard_intensity_layers.json)
  damage_basis                          what the ratio is a share of: "building", "contents" or "building_and_contents"
  source {authors, year, title, publisher, url, file, sha256}   the publication, and the copy held
  licence                               as the publisher states it
  curves [{key, occupancy, region, points [[x, ratio], …], quote {table, page}}]
  beyond_last                           "hold": the ratio at the last point holds beyond it (no extrapolation)"""
from __future__ import annotations

import json
from functools import lru_cache

from services.loss import registry

DIR = registry.REF / "vulnerability"
BASES = {"building", "contents", "building_and_contents"}


class CurveError(ValueError):
    pass


def check_family(doc: dict) -> list[str]:
    """Every problem in one family document; empty when it is sound."""
    out = []
    fam = doc.get("family", "?")
    metrics = {(L["peril"], L["metric"], L["unit"]) for L in registry.layers().values()}
    if (doc.get("peril"), doc.get("metric"), doc.get("unit")) not in metrics:
        out.append(f"{fam}: no intensity layer measures {doc.get('peril')} as {doc.get('metric')} in {doc.get('unit')}")
    if doc.get("damage_basis") not in BASES:
        out.append(f"{fam}: damage basis must be one of {sorted(BASES)}")
    src = doc.get("source") or {}
    for k in ("authors", "year", "title", "publisher", "url", "file", "sha256"):
        if not src.get(k):
            out.append(f"{fam}: the source lacks '{k}'")
    if not doc.get("licence"):
        out.append(f"{fam}: no licence")
    if doc.get("beyond_last") != "hold":
        out.append(f"{fam}: beyond the last point the ratio holds ('hold'); nothing else is allowed")
    keys = set()
    classes = set(registry.occupancy_classes())
    for c in doc.get("curves") or []:
        k = c.get("key", "?")
        if k in keys:
            out.append(f"{fam}: curve {k} appears twice")
        keys.add(k)
        if c.get("occupancy") not in classes:
            out.append(f"{fam}/{k}: occupancy '{c.get('occupancy')}' is not a registered class")
        if not c.get("region"):
            out.append(f"{fam}/{k}: no region")
        q = c.get("quote") or {}
        if not (q.get("table") and q.get("page")):
            out.append(f"{fam}/{k}: the table and page it was transcribed from are not quoted")
        pts = c.get("points") or []
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if len(pts) < 2 or xs != sorted(set(xs)) or xs[0] < 0:
            out.append(f"{fam}/{k}: intensities must be at least two, distinct, ascending and non-negative")
        if any(y < 0 or y > 1 for y in ys) or any(b < a for a, b in zip(ys, ys[1:])):
            out.append(f"{fam}/{k}: damage ratios must lie in [0, 1] and never fall as intensity rises")
    if not keys:
        out.append(f"{fam}: no curves")
    return out


@lru_cache(maxsize=None)
def families() -> dict[str, dict]:
    """The registered families, each checked: a family with a problem is refused, never half-used."""
    out = {}
    for path in sorted(DIR.glob("*.json")) if DIR.exists() else []:
        doc = json.loads(path.read_text(encoding="utf-8"))
        problems = check_family(doc)
        if problems:
            raise CurveError(f"{path.name}: " + "; ".join(problems))
        out[doc["family"]] = doc
    return out


def ratio(points: list, x: float) -> float:
    """The damage ratio at intensity x: linear between the published points, the last ratio held beyond them, zero
    below the first point's intensity when that point's ratio is zero."""
    if x <= points[0][0]:
        return float(points[0][1]) if x == points[0][0] else 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return float(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return float(points[-1][1])
