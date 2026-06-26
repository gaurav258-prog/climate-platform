"""
Real-time seismic monitoring daemon.

Polls EMSC every 60 seconds for M≥5.0 events in Europe.
On a new event:
  1. Ingests the event into satellite_observations via EMSCAdapter
  2. Schedules a SAR damage assessment (runs after next Sentinel-1 pass)
  3. Logs an alert to the Operations view alert feed

Run:
    cd /path/to/climate-platform
    source .venv/bin/activate
    python scripts/monitor_seismic.py

Signals:
    SIGTERM / Ctrl-C → clean shutdown after current poll completes
"""
import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/seismic_monitor.log"),
    ],
)
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60
MIN_MAGNITUDE_INGEST = 4.5
MIN_MAGNITUDE_DAMAGE = 5.0

# Track which events we've already processed to avoid duplicates
_processed_event_ids: set[str] = set()
_running = True


def _handle_signal(signum, frame):
    global _running
    logger.info(f"[monitor] received signal {signum} — shutting down after current poll")
    _running = False


def poll_and_process():
    """Single poll cycle: fetch new events, ingest, schedule damage assessment."""
    from services.ingestion.adapters.emsc import EMSCAdapter

    now = datetime.now(timezone.utc)
    # Look back 5 minutes to catch any events missed in the last poll
    adapter = EMSCAdapter(
        start_dt=now - timedelta(minutes=5),
        end_dt=now,
        min_magnitude=MIN_MAGNITUDE_INGEST,
    )

    try:
        raw_events = adapter.fetch()
    except Exception as exc:
        logger.warning(f"[monitor] EMSC fetch failed: {exc}")
        return

    if not raw_events:
        return

    new_events = []
    for feature in raw_events:
        props = feature["properties"]
        event_id = props.get("unid") or feature.get("id", "")
        if event_id and event_id not in _processed_event_ids:
            new_events.append(feature)
            _processed_event_ids.add(event_id)

    if not new_events:
        return

    logger.info(f"[monitor] {len(new_events)} new events")
    observations = adapter.to_observations(new_events)
    if observations:
        from core.db.session import get_session
        with get_session() as session:
            session.add_all(observations)
        logger.info(f"[monitor] ingested {len(observations)} seismic observations")

    # Schedule damage assessment for M≥5.0 events
    for feature in new_events:
        props = feature["properties"]
        coords = feature["geometry"]["coordinates"]
        mag = float(props.get("mag", 0))
        if mag < MIN_MAGNITUDE_DAMAGE:
            continue

        event_id = props.get("unid") or feature.get("id", "")
        lat = float(coords[1])
        lon = float(coords[0])
        depth = float(coords[2])
        region = props.get("flynn_region", "Unknown region")
        origin_time_str = props["time"]
        origin_dt = datetime.fromisoformat(origin_time_str.replace("Z", "+00:00"))

        logger.warning(
            f"[monitor] *** M{mag} EVENT *** {region} | "
            f"lat={lat:.2f} lon={lon:.2f} depth={depth:.0f}km | "
            f"origin={origin_dt.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        logger.warning(
            f"[monitor] scheduling SAR damage assessment for {event_id} "
            f"— first Sentinel-1 pass expected within 6–18h"
        )

        _schedule_damage_assessment(
            event_id=event_id,
            magnitude=mag,
            origin_time=origin_dt,
            lat=lat,
            lon=lon,
        )
        _write_alert(
            event_id=event_id,
            magnitude=mag,
            region=region,
            lat=lat,
            lon=lon,
            depth_km=depth,
            origin_time=origin_dt,
        )


def _schedule_damage_assessment(
    event_id: str,
    magnitude: float,
    origin_time: datetime,
    lat: float,
    lon: float,
):
    """
    Attempt damage assessment immediately (in case post-event SAR pass already exists),
    then log a scheduled check for 24h later.

    In production this would push to a task queue (Celery / AWS SQS).
    Here we run inline and log if data is not yet available.
    """
    try:
        from services.processing.sar_coherence import run_damage_assessment
        result = run_damage_assessment(
            event_id=event_id,
            magnitude=magnitude,
            origin_time=origin_time,
            epicentre_lat=lat,
            epicentre_lon=lon,
        )
        if result is None:
            logger.info(
                f"[monitor] no post-event SAR pass available yet for {event_id} — "
                f"re-check in 6h when next Sentinel-1 pass expected"
            )
        else:
            logger.info(
                f"[monitor] damage assessment complete for {event_id}: "
                f"{result.cells_damaged} cells damaged "
                f"({result.cells_high_confidence} high-confidence)"
            )
    except Exception as exc:
        logger.error(f"[monitor] damage assessment failed for {event_id}: {exc}")


def _write_alert(
    event_id: str,
    magnitude: float,
    region: str,
    lat: float,
    lon: float,
    depth_km: float,
    origin_time: datetime,
):
    """Write alert to alert_events table for the Operations view."""
    try:
        from core.db.session import get_session
        from sqlalchemy import text
        import h3

        h3_cell = h3.latlng_to_cell(lat, lon, 8)

        with get_session() as session:
            session.execute(text("""
                INSERT INTO alert_events
                    (h3_cell, hazard_type, alert_level, message, triggered_at, source_ref)
                VALUES
                    (:cell, 'seismic', :level, :msg, :triggered_at, :source_ref)
                ON CONFLICT DO NOTHING
            """), {
                "cell": h3_cell,
                "level": "critical" if magnitude >= 6.0 else "high",
                "msg": (
                    f"M{magnitude} earthquake — {region} | "
                    f"depth {depth_km:.0f}km | "
                    f"SAR damage assessment scheduled"
                ),
                "triggered_at": origin_time,
                "source_ref": event_id,
            })
    except Exception as exc:
        logger.warning(f"[monitor] could not write alert for {event_id}: {exc}")


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Pre-populate seen events from last 24h to avoid re-processing on restart
    try:
        from services.ingestion.adapters.emsc import EMSCAdapter
        historical = EMSCAdapter(
            start_dt=datetime.now(timezone.utc) - timedelta(hours=24),
            min_magnitude=MIN_MAGNITUDE_INGEST,
        ).fetch()
        for f in historical:
            eid = f["properties"].get("unid") or f.get("id", "")
            if eid:
                _processed_event_ids.add(eid)
        logger.info(f"[monitor] pre-loaded {len(_processed_event_ids)} recent event IDs")
    except Exception as exc:
        logger.warning(f"[monitor] could not pre-load history: {exc}")

    logger.info(
        f"[monitor] starting seismic monitor — "
        f"polling EMSC every {POLL_INTERVAL_SECONDS}s for M≥{MIN_MAGNITUDE_INGEST} events"
    )

    while _running:
        try:
            poll_and_process()
        except Exception as exc:
            logger.error(f"[monitor] unexpected error in poll cycle: {exc}")
        if _running:
            time.sleep(POLL_INTERVAL_SECONDS)

    logger.info("[monitor] shutdown complete")


if __name__ == "__main__":
    main()
