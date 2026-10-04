"""The calibration pipeline (E162): every active recipe is run on the data of the day, each run recorded with its
ledger entry; the runs that would change a publication are proposed together for review. Nothing publishes here.

Triggered by a landed yield release (the recipes reading that source — services.tasks.jobs 'calibration.run'), or by an
operator (scripts/run_calibration_pipeline, which also adopts the fits published before the pipeline as recipes).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.calibration import publish, runner, specs


def adopt_legacy(session: Session) -> list[dict]:
    """Record a recipe for every fit published before the pipeline (an explicit operator step, not part of a run)."""
    return specs.legacy(session)


def run(session: Session, *, sources: list[str] | None = None, propose: bool = True,
        reason: str = "Calibration pipeline run") -> dict:
    """Run the active recipes (those reading one of `sources`, when given). Returns the runs and the proposal.
    Not committed here — the caller commits (a dry run rolls back)."""
    runs = [runner.run(session, sp) for sp in runner.active_specs(session)
            if sources is None or sp["yield_source"] in sources]
    proposal = publish.propose(session, [r["run_id"] for r in runs], reason) if propose else None
    return {"runs": runs, "proposal": proposal}


def run_job(sources: list[str] | None = None) -> dict:
    """The background job (services.tasks.jobs 'calibration.run'): its own session, committed — run after a yield
    release lands, for the recipes reading that source."""
    from core.db.session import get_session
    with get_session() as session:
        out = run(session, sources=sources,
                  reason=f"Re-run after a landed release of {', '.join(sources)}" if sources else "Calibration pipeline run")
        session.commit()
    return {"runs": len(out["runs"]), "proposed": (out["proposal"] or {}).get("runs", 0)}


def build_weather(session: Session) -> str:
    """A weather build for every registry crop with a crop map and every box a box recipe reads (soil water aside)."""
    from ml.features.crop_registry import crops as registry
    from services.calibration import crop_weather
    crops = [c["commodity"] for c in registry() if c.get("crop_map")]
    boxes = sorted({sp["weather_key"] for sp in runner.active_specs(session)
                    if sp["weather_kind"] == "box" and sp["driver"] != "soil_water"})
    return crop_weather.build(session, crops, boxes)


def refresh_weather(fetch: bool = True) -> dict:
    """The monthly weather refresh (job 'calibration.refresh_weather', E163): fetch the missing ERA5-Land years and the
    current year's months, rebuild the weather, generate the recipes new data allows, re-run every recipe and propose the
    runs that would change a publication. Each step commits on its own; nothing publishes here."""
    import logging

    from core.db.session import get_session
    from scripts.fetch_era5_land_global import FetchRunning, fetch_all
    from services.calibration import registry_specs
    log = logging.getLogger(__name__)
    if fetch:
        try:
            fetch_all(log=log.info)
        except FetchRunning as e:
            return {"skipped": str(e)}
    with get_session() as session:
        build_id = build_weather(session)
        session.commit()
        generated = registry_specs.generate(session)
        session.commit()
        out = run(session, reason=f"Re-run after weather build {build_id}")
        session.commit()
    return {"build_id": build_id, "generated": generated, "runs": len(out["runs"]),
            "proposed": (out["proposal"] or {}).get("runs", 0)}
