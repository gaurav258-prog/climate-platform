"""Every heavy job is registered by name and resolves to one function the worker and the fallback both run."""
import pytest

from services.tasks.jobs import JOBS, resolve


def test_every_registered_job_resolves():
    for name in JOBS:
        assert callable(resolve(name)), name


def test_unknown_job_fails_fast():
    with pytest.raises(KeyError):
        resolve("no.such.job")


def test_celery_tasks_exist_for_every_supervision_job():
    from services.tasks import supervision_tasks  # noqa: F401
    from services.tasks.celery_app import celery_app
    for name in ("supervision.project_cells", "supervision.rebuild_geo_priors"):
        assert name in celery_app.tasks
    assert "rebuild-geo-priors-daily" in celery_app.conf.beat_schedule
