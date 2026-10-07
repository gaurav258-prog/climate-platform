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
  kind                                  "published" (transcribed from the publisher's table: each curve quotes
                                        {table, page}) or "measured" (computed from a recorded dataset under
                                        data/reference/loss_protocol.json: a derivation, each curve's bands with
                                        their spread, and the held-out test with whether it passed)
  curves [{key, occupancy, region, countries [ISO2 …], points [[x, ratio], …], quote | bands}]
                                        a published curve may carry the publisher's standard deviation per point
                                        (sd [[x, σ], …]) or say "spread": "none published"; with spread_required
                                        on the family, every curve must say which
  beyond_last                           "hold": the ratio at the last point holds beyond it (no extrapolation)"""
from __future__ import annotations

import json
from functools import lru_cache

from services.loss import registry

DIR = registry.REF / "vulnerability"
BASES = {"building", "contents", "building_and_contents", "asset_value"}
ALL_USES = "*"          # an aggregate curve (damage_basis asset_value): every occupancy


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
    kind = doc.get("kind", "published")
    if kind not in ("published", "measured"):
        out.append(f"{fam}: kind must be 'published' or 'measured'")
    if kind == "measured":
        d, t = doc.get("derivation") or {}, doc.get("test") or {}
        if not (d.get("protocol") and d.get("claims_used")):
            out.append(f"{fam}: a measured family records its protocol and the claims it used")
        if not isinstance(t.get("passed"), bool) or not t.get("events_tested"):
            out.append(f"{fam}: a measured family records its held-out test and whether it passed")
    keys = set()
    classes = set(registry.occupancy_classes())
    for c in doc.get("curves") or []:
        k = c.get("key", "?")
        if k in keys:
            out.append(f"{fam}: curve {k} appears twice")
        keys.add(k)
        if c.get("occupancy") == ALL_USES:
            if doc.get("damage_basis") != "asset_value":
                out.append(f"{fam}/{k}: only an aggregate curve (damage basis asset_value) applies to every occupancy")
        elif c.get("occupancy") not in classes:
            out.append(f"{fam}/{k}: occupancy '{c.get('occupancy')}' is not a registered class")
        if not c.get("region"):
            out.append(f"{fam}/{k}: no region")
        if not c.get("countries"):
            out.append(f"{fam}/{k}: no countries the curve applies to")
        if kind == "published":
            q = c.get("quote") or {}
            if not (q.get("table") and q.get("page")):
                out.append(f"{fam}/{k}: the table and page it was transcribed from are not quoted")
            sd, xs_ = c.get("sd"), [p[0] for p in c.get("points") or []]
            if sd is not None:
                if [p[0] for p in sd] != xs_ or any(p[1] is None or p[1] < 0 for p in sd):
                    out.append(f"{fam}/{k}: its published standard deviation needs one non-negative value per depth")
            elif c.get("spread") not in ("none published", None) or (doc.get("spread_required") and c.get("spread") is None):
                out.append(f"{fam}/{k}: a curve states its published spread ('sd') or that none is published")
        else:
            bands = c.get("bands") or []
            if not bands or any(b.get("n", 0) <= 0 or b.get("p10") is None or b.get("p90") is None
                                or not (b["p10"] <= b["p90"]) for b in bands):
                out.append(f"{fam}/{k}: its bands each need their claims and a 10th–90th percentile range")
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
def _load() -> tuple[dict[str, dict], dict[str, list[str]]]:
    sound, refused = {}, {}
    for path in sorted(DIR.glob("*.json")) if DIR.exists() else []:
        doc = json.loads(path.read_text(encoding="utf-8"))
        problems = check_family(doc)
        if problems:
            refused[doc.get("family", path.stem)] = problems
        else:
            sound[doc["family"]] = doc
    return sound, refused


def families() -> dict[str, dict]:
    """The registered families that are sound — one with a problem is refused (see refused()), never half-used, and
    never stops the others."""
    return _load()[0]


def refused() -> dict[str, list[str]]:
    """{family: its problems} for every registered family that cannot be used, so a screen can say why."""
    return _load()[1]


def reload() -> None:
    _load.cache_clear()


def curve_for(family: str, occupancy: str, country: str) -> dict | None:
    """The family's curve for this occupancy in this country, or None."""
    fam = families().get(family)
    if not fam:
        return None
    return next((c for c in fam["curves"] if c["occupancy"] in (occupancy, ALL_USES) and country in c["countries"]),
                None)


def ratio(points: list, x: float) -> float:
    """The damage ratio at intensity x: linear between the published points, the last ratio held beyond them, zero
    below the first point's intensity when that point's ratio is zero."""
    if x <= points[0][0]:
        return float(points[0][1]) if x == points[0][0] else 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return float(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return float(points[-1][1])
