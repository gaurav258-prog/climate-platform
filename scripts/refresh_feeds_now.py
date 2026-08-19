"""Run the golden-source auto-refresh once, now — the dev/demo stand-in for Celery beat.

In production the beat scheduler (celery_app.beat_schedule → feeds.refresh_due) runs this on a clock and
no one touches it. Without a running broker (local dev), run it by hand to populate the freshness monitor:

    python -m scripts.refresh_feeds_now          # only feeds due by their cadence
    python -m scripts.refresh_feeds_now --force  # refresh every auto-scheduled feed regardless of cadence
"""
import sys

from core.db.session import get_session
from services.data.feeds import run_scheduled_refreshes


def main() -> None:
    force = "--force" in sys.argv
    with get_session() as s:
        done = run_scheduled_refreshes(s, force=force)
    if not done:
        print("Nothing due — all auto-scheduled feeds are within cadence.")
        return
    for d in done:
        print(f"  {d['status']:9s} {d['feed_key']}")
    print(f"{sum(1 for d in done if d['status']=='refreshed')} refreshed, "
          f"{sum(1 for d in done if d['status']=='failed')} failed.")


if __name__ == "__main__":
    main()
