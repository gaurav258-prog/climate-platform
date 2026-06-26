"""
Historical EMSC earthquake catalog backfill — 1990 to present.

Fetches all M≥4.5 events from the EMSC FDSN-event API.
Writes to both seismic_events (normalized) and satellite_observations (observation layer).

Expected output: ~7,000–10,000 events spanning 35 years.
Run time: ~15–20 minutes (API rate limit ~1 req/s, paginated by year).
"""
import logging
import sys
from datetime import datetime, date, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from services.ingestion.adapters.emsc import EMSCAdapter
from core.db.models import SeismicEvent, SatelliteObservation
from core.db.session import get_session
from core.types import HazardType
import h3

def backfill_year(year: int) -> tuple[int, int]:
    """
    Fetch all M≥4.5 events for a single year.
    Returns (seismic_events written, satellite_observations written).
    """
    start_dt = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    adapter = EMSCAdapter(start_dt=start_dt, end_dt=end_dt, min_magnitude=4.5)
    try:
        raw_events = adapter.fetch()
    except Exception as exc:
        logger.warning(f"[EMSC] {year}: fetch failed — {exc}")
        return 0, 0

    if not raw_events:
        logger.info(f"[EMSC] {year}: no events found")
        return 0, 0

    observations = adapter.to_observations(raw_events)
    seismic_events_written = 0
    obs_written = 0

    with get_session() as session:
        for feature in raw_events:
            try:
                props = feature["properties"]
                coords = feature["geometry"]["coordinates"]

                event_id = props.get("unid") or feature.get("id", "")
                magnitude = float(props["mag"])
                mag_type = props.get("magtype", "M")
                depth_km = float(coords[2])
                lat = float(coords[1])
                lon = float(coords[0])
                origin_time_str = props["time"]
                origin_time = datetime.fromisoformat(origin_time_str.replace("Z", "+00:00"))
                region = props.get("flynn_region", "")
                status = props.get("evtype", "ke")
                source = props.get("source_catalog", "EMSC")

                # Map to H3
                h3_cell = h3.latlng_to_cell(lat, lon, 8)

                # Check if already exists
                existing = session.query(SeismicEvent).filter(
                    SeismicEvent.event_id == event_id
                ).first()
                if existing:
                    continue

                # Create seismic_events entry
                seismic_event = SeismicEvent(
                    event_id=event_id,
                    magnitude=magnitude,
                    mag_type=mag_type,
                    depth_km=depth_km,
                    epicentre_lat=lat,
                    epicentre_lon=lon,
                    epicentre_h3=h3_cell,
                    origin_time=origin_time,
                    region_name=region,
                    source_catalog=source,
                    review_status="reviewed" if status == "ke" else "preliminary",
                    damage_assessment_status="pending" if magnitude >= 5.0 else None,
                )
                session.add(seismic_event)
                seismic_events_written += 1

            except Exception as exc:
                logger.debug(f"[EMSC] {year}: skipping malformed event — {exc}")
                continue

        # Write observations
        if observations:
            session.add_all(observations)
            obs_written = len(observations)

    logger.info(f"[EMSC] {year}: {seismic_events_written} events, {obs_written} observations")
    return seismic_events_written, obs_written


def main():
    logger.info("")
    logger.info("=" * 70)
    logger.info("  EMSC Historical Backfill — 1990 to present")
    logger.info("  M≥4.5 events, EU region")
    logger.info("=" * 70)
    logger.info("")

    start_year = 1990
    end_year = date.today().year

    total_events = 0
    total_obs = 0

    for year in range(start_year, end_year + 1):
        events, obs = backfill_year(year)
        total_events += events
        total_obs += obs

    logger.info("")
    logger.info("=" * 70)
    logger.info(f"  Backfill complete: {total_events} seismic events")
    logger.info(f"                     {total_obs} observations")
    logger.info("=" * 70)
    logger.info("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
