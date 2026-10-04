"""Recipes the registry and the protocol generate for every crop × origin the crop grows in (E163), and the coverage —
each crop × origin with its recipe, or the reason it has none.

For a crop with a crop map and a season source in the registry, and each origin where the map holds its area:
  * a slot that already has a recipe keeps it (a legacy box recipe is never replaced by a generated one) — a GENERATED
    recipe only while it is what the registry and protocol generate today: one whose inputs no longer stand (a season
    the reference now holds, a series the precedence no longer picks) is retired with the reason, its pending proposal
    withdrawn, and the slot generated afresh (E168); one with a publication is left for a reviewer and reported
  * the yield series is the origin's national series by the stated precedence (ml.features.yield_series)
  * the season is the origin's (services.calibration.seasons) — held when none is stated
  * the driver is the protocol's pre-registered one for generated recipes (drought, SPEI-6), the weather the crop's own
    growing area (services.calibration.crop_area), the cycle rule the registry's life cycle
Recipes are created; nothing is run or published here. The coverage snapshot is replaced whole on each generation.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.features import yield_series
from ml.features.crop_registry import crops as registry
from ml.features.crop_registry import is_alternate_bearing
from services.calibration import crop_area, seasons, specs
from services.calibration import crop_area_weights as W
from services.calibration.gates import protocol

MIN_YEARS = 12
ERA5_FIRST = 1991


def _m49(session: Session) -> dict[str, int]:
    return {r[0].strip(): int(r[1]) for r in session.execute(text(
        "SELECT iso2, numeric_code FROM ref_countries WHERE numeric_code IS NOT NULL AND is_country")).all()}


def _active(session: Session) -> dict[tuple[str, str, str], dict]:
    return {(r["commodity"], r["origin"], r["driver"]): dict(r) for r in session.execute(text("""
        SELECT spec_id::text, commodity, origin, driver, yield_source, weather_kind, weather_key, season_months,
               season_prev_months, spei_scale, allow_cycle,
               EXISTS (SELECT 1 FROM crop_calibration_runs r WHERE r.spec_id = s.spec_id AND r.status = 'published')
                 AS published
        FROM crop_calibration_specs s WHERE retired_at IS NULL AND yield_region = ''""")).mappings()}


_COMPARED = ("yield_source", "driver", "weather_key", "season_months", "season_prev_months", "spei_scale", "allow_cycle")


def _differs(have: dict, want: dict) -> list[str]:
    return [f"{k} {have[k]} → {want[k]}" for k in _COMPARED if (sorted(have[k]) if isinstance(have[k], list) else have[k])
            != (sorted(want[k]) if isinstance(want[k], list) else want[k])]


def retire(session: Session, spec_id: str, why: str) -> None:
    """Retire a recipe with its reason; a run of it awaiting a decision is withdrawn (never published on a recipe that
    no longer stands). Recorded and published runs stay as history."""
    session.execute(text("""UPDATE crop_calibration_specs SET retired_at = now(), retired_reason = :w
                            WHERE spec_id = CAST(:s AS uuid) AND retired_at IS NULL"""), {"s": spec_id, "w": why})
    session.execute(text("""UPDATE crop_calibration_runs SET status = 'superseded', decided_at = now(),
                            decision_reason = 'recipe retired before a decision: ' || :w
                            WHERE spec_id = CAST(:s AS uuid) AND status = 'proposed'"""), {"s": spec_id, "w": why})
    from services.calibration.publish import close_emptied_batches
    close_emptied_batches(session)


def generate(session: Session) -> dict:
    """Create the missing recipes and replace the coverage snapshot. Returns counts by status."""
    proto = protocol()
    gen = proto["generated"]
    driver = gen["driver"]
    m49 = _m49(session)
    active = _active(session)
    rows, created, retired, stale = [], 0, 0, []
    for c in registry():
        name = c["commodity"]
        if not c.get("crop_map"):
            continue
        weights = W.weights(name)
        total = sum(float(w.sum()) for _i, w in weights.values()) or 1.0
        for origin, (_idx, w) in sorted(weights.items()):
            area = float(w.sum())
            row = {"c": name, "o": origin, "a": area, "sh": area / total, "spec": None}
            have = active.get((name, origin, driver)) or next((v for (cc, oo, _d), v in active.items()
                                                                if cc == name and oo == origin), None)
            if have and have["weather_kind"] != "crop_area":     # a legacy box recipe: never replaced by a generated one
                rows.append({**row, "st": "recipe", "r": None, "spec": have["spec_id"]})
                continue
            held, want, se = None, None, None
            src = yield_series.national_source(session, name, origin)
            if src is None:
                held = ("no_yield_series", "no national yield series is held for the origin")
            else:
                years = [y for y in yield_series.series(session, name, origin, src) if y >= ERA5_FIRST]
                if len(years) < MIN_YEARS + 2 * 3:              # the fit needs 12 years with a full trend window
                    held = ("too_few_years", f"{len(years)} years of {src} since {ERA5_FIRST} — the fit needs at least 18")
                else:
                    se = seasons.season(name, origin, m49.get(origin), area)
                    if "held" in se:
                        held = ("no_season", se["held"])
                    else:
                        want = {"yield_source": src, "driver": driver, "weather_key": crop_area.map_key(name),
                                "season_months": se["months"], "season_prev_months": se["prev_months"],
                                "spei_scale": gen["spei_scale"], "allow_cycle": is_alternate_bearing(name)}
            if have:
                diff = _differs(have, want) if want else None
                if want and not diff:
                    rows.append({**row, "st": "recipe", "r": None, "spec": have["spec_id"]})
                    continue
                why = held[1] if held else "the recipe generated today differs: " + "; ".join(diff)
                if have["published"]:                            # a publication is withdrawn only by a reviewer
                    stale.append({"commodity": name, "origin": origin, "spec_id": have["spec_id"], "reason": why})
                    rows.append({**row, "st": "recipe", "r": None, "spec": have["spec_id"]})
                    continue
                retire(session, have["spec_id"], why)
                retired += 1
            if held:
                rows.append({**row, "st": held[0], "r": held[1]})
                continue
            sid = specs.create(session, commodity=name, origin=origin, weather_kind="crop_area", **want,
                               basis=f"generated by {proto['protocol']}: season {se['basis']}; weather over the crop's "
                                     f"area in {crop_area.map_key(name)}; yield {src} (national precedence)",
                               protocol=proto["protocol"])
            created += 1
            rows.append({**row, "st": "recipe", "r": None, "spec": sid})
    session.execute(text("DELETE FROM crop_calibration_coverage"))
    session.execute(text("""INSERT INTO crop_calibration_coverage (commodity, origin, area_ha, area_share, status, reason, spec_id)
                            VALUES (:c, :o, :a, :sh, :st, :r, CAST(:spec AS uuid))"""), rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["st"]] = counts.get(r["st"], 0) + 1
    return {"created": created, "retired": retired, "stale_published": stale, "coverage": counts}
