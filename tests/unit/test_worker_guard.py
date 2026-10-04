"""E166: the worker never forks, and a job that kills its worker is failed after MAX_DELIVERIES, not re-run forever."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.tasks import worker_guard
from services.tasks.celery_app import celery_app
from services.tasks.worker_guard import (
    MAX_DELIVERIES,
    GuardedTask,
    TaskAbandoned,
    refuse_forking_pool,
)

ROOT = Path(__file__).resolve().parents[2]


def test_pool_is_threads_by_configuration_and_in_the_procfile():
    assert celery_app.conf.worker_pool == "threads"
    worker = next(line for line in (ROOT / "Procfile").read_text().splitlines() if line.startswith("worker:"))
    assert "--pool=threads" in worker


@pytest.mark.parametrize("pool", ["prefork", "processes", "celery.concurrency.prefork:TaskPool"])
def test_a_forking_pool_is_refused(pool):
    with pytest.raises(SystemExit, match="E166"):
        refuse_forking_pool(sender=SimpleNamespace(pool_cls=pool))


@pytest.mark.parametrize("pool", ["threads", "solo"])
def test_a_fork_free_pool_starts(pool):
    refuse_forking_pool(sender=SimpleNamespace(pool_cls=pool))


def test_every_task_counts_its_deliveries():
    for name, task in celery_app.tasks.items():
        if not name.startswith("celery."):
            assert isinstance(task, GuardedTask), name


@pytest.fixture
def counts(monkeypatch):
    store: dict[str, int] = {}

    def count(task_id):
        store[task_id] = store.get(task_id, 0) + 1
        return store[task_id]

    monkeypatch.setattr(worker_guard, "count_delivery", count)
    monkeypatch.setattr(worker_guard, "clear_deliveries", lambda task_id: store.pop(task_id, None))
    return store


STATE = {"ran": 0, "abandoned": []}


class _JobBase(GuardedTask):
    def on_abandon(self, args, kwargs):
        STATE["abandoned"].append(args)


@celery_app.task(name="test.worker_guard.job", base=_JobBase)
def _job(x):
    STATE["ran"] += 1
    if x == "raise":
        raise ValueError("ordinary failure")
    return x


def _deliver(task_id, *args):
    """Call the task the way the worker's tracer does: with a request carrying the delivery's task id."""
    _job.push_request(id=task_id, is_eager=False)
    try:
        return _job(*args)
    finally:
        _job.pop_request()


def test_a_finished_job_clears_its_count(counts):
    assert _deliver("t-ok", "done") == "done"
    assert "t-ok" not in counts


def test_an_ordinary_failure_clears_its_count(counts):
    with pytest.raises(ValueError):
        _deliver("t-raise", "raise")
    assert "t-raise" not in counts


def test_a_job_whose_worker_died_each_time_is_abandoned_not_run(counts):
    STATE.update(ran=0, abandoned=[])
    counts["t-crash"] = MAX_DELIVERIES          # three deliveries, each ended by the worker dying (no clear)
    with pytest.raises(TaskAbandoned):
        _deliver("t-crash", "lookup-1")
    assert STATE["ran"] == 0
    assert STATE["abandoned"] == [("lookup-1",)]
    assert "t-crash" not in counts


def test_the_last_allowed_delivery_still_runs(counts):
    STATE["ran"] = 0
    counts["t-last"] = MAX_DELIVERIES - 1
    assert _deliver("t-last", "ok") == "ok"
    assert STATE["ran"] == 1


def test_an_uncounted_delivery_runs(monkeypatch):
    """Redis unreachable → count 0: the cap stops loops, it never blocks work."""
    monkeypatch.setattr(worker_guard, "count_delivery", lambda task_id: 0)
    monkeypatch.setattr(worker_guard, "clear_deliveries", lambda task_id: None)
    assert _deliver("t-uncounted", "ok") == "ok"


def test_an_abandoned_lookup_ends_failed(monkeypatch):
    from services.tasks import hazard_tasks
    seen = []

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            seen.append((str(sql), params))

        def commit(self):
            seen.append("commit")

    monkeypatch.setattr("core.db.session.get_session", lambda: _S())
    hazard_tasks.heat_acute_task.on_abandon(("lookup-9", 1.0, 2.0), {})
    sql, params = seen[0]
    assert "status='failed'" in sql and "status='computing'" in sql
    assert params["id"] == "lookup-9" and seen[-1] == "commit"


def test_redis_count_round_trip():
    """The real counter, when Redis is up: increments per delivery and clears."""
    try:
        worker_guard._client().ping()
    except Exception:
        pytest.skip("redis not reachable")
    tid = "test-worker-guard-roundtrip"
    worker_guard.clear_deliveries(tid)
    assert [worker_guard.count_delivery(tid) for _ in range(3)] == [1, 2, 3]
    worker_guard.clear_deliveries(tid)
    assert worker_guard.count_delivery(tid) == 1
    worker_guard.clear_deliveries(tid)
