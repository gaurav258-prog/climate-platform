"""Pure-logic tests for the engagement SLA metrics: time to acknowledge / respond / close, on-time rate,
overdue ageing buckets, and per-kind / per-entity grouping. No DB — feeds `compute`/`by_group` synthetic rows
shaped exactly like `services.supervision.sla.load_rows` produces."""
from datetime import date, datetime, timezone

from services.supervision.sla import AGEING_BUCKETS, ageing_bucket, by_group, compute

TODAY = date(2026, 9, 12)


def dt(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def row(**kw):
    base = {"kind": "information_request", "kind_label": "Information request", "status": "open", "closed": False,
            "sent_at": None, "acknowledged_at": None, "responded_at": None, "closed_at": None, "due_date": None,
            "supervised_org_id": "e1", "supervised_org_id_label": "Entity 1"}
    base.update(kw)
    return base


def test_ageing_buckets_cover_boundaries_with_no_gaps():
    assert ageing_bucket(1) == "1-7"
    assert ageing_bucket(7) == "1-7"
    assert ageing_bucket(8) == "8-30"
    assert ageing_bucket(30) == "8-30"
    assert ageing_bucket(31) == "31-90"
    assert ageing_bucket(90) == "31-90"
    assert ageing_bucket(91) == "90+"
    assert ageing_bucket(365) == "90+"
    assert ageing_bucket(0) is None  # not overdue yet


def test_time_to_acknowledge_and_respond_hours():
    rows = [row(sent_at=dt(2026, 9, 1), acknowledged_at=dt(2026, 9, 2), responded_at=dt(2026, 9, 3), closed_at=dt(2026, 9, 5), closed=True)]
    out = compute(rows, TODAY)
    assert out["time_to_acknowledge_hours"] == {"n": 1, "median": 24.0, "p90": 24.0, "max": 24.0}
    assert out["time_to_respond_hours"] == {"n": 1, "median": 48.0, "p90": 48.0, "max": 48.0}
    assert out["time_to_close_hours"] == {"n": 1, "median": 96.0, "p90": 96.0, "max": 96.0}


def test_missing_timestamp_is_excluded_from_its_own_sample_not_fabricated():
    rows = [row(sent_at=dt(2026, 9, 1), acknowledged_at=dt(2026, 9, 2)),  # no responded_at yet
            row(sent_at=dt(2026, 9, 1), acknowledged_at=None)]            # never acknowledged
    out = compute(rows, TODAY)
    assert out["time_to_acknowledge_hours"]["n"] == 1
    assert out["time_to_respond_hours"]["n"] == 0
    assert out["time_to_respond_hours"]["median"] is None
    assert out["awaiting_acknowledgement"]["n"] == 1


def test_responded_on_time_rate_against_due_date():
    rows = [row(sent_at=dt(2026, 8, 1), responded_at=dt(2026, 8, 10), due_date=date(2026, 8, 15)),   # on time
            row(sent_at=dt(2026, 8, 1), responded_at=dt(2026, 8, 20), due_date=date(2026, 8, 15)),   # late
            row(sent_at=dt(2026, 8, 1), responded_at=None, due_date=date(2026, 8, 15))]              # not yet responded: outside sample
    out = compute(rows, TODAY)
    assert out["responded_on_time"] == {"n": 2, "on_time": 1, "rate": 0.5}


def test_overdue_only_counts_open_items_past_due_date_with_ageing():
    rows = [row(due_date=date(2026, 9, 5), closed=False),   # 7 days overdue
            row(due_date=date(2026, 9, 1), closed=False),   # 11 days overdue
            row(due_date=date(2026, 8, 1), closed=True),    # closed: not overdue regardless of date
            row(due_date=date(2026, 9, 20), closed=False)]  # not yet due
    out = compute(rows, TODAY)
    assert out["overdue"]["n"] == 2
    assert out["overdue"]["ageing"]["1-7"] == 1
    assert out["overdue"]["ageing"]["8-30"] == 1
    assert out["overdue"]["oldest_days"] == 11
    assert out["overdue"]["total_days"] == 7 + 11


def test_compute_never_fabricates_a_metric_for_an_empty_sample():
    out = compute([], TODAY)
    assert out == {"n": 0, "n_open": 0, "n_closed": 0,
                   "time_to_acknowledge_hours": {"n": 0, "median": None, "p90": None, "max": None},
                   "time_to_respond_hours": {"n": 0, "median": None, "p90": None, "max": None},
                   "time_to_close_hours": {"n": 0, "median": None, "p90": None, "max": None},
                   "responded_on_time": {"n": 0, "on_time": 0, "rate": None},
                   "awaiting_acknowledgement": {"n": 0, "oldest_days": None},
                   "awaiting_response": {"n": 0},
                   "overdue": {"n": 0, "ageing": {label: 0 for label, _, _ in AGEING_BUCKETS}, "oldest_days": None, "total_days": 0}}


def test_by_group_sorts_worst_overdue_first_and_carries_label():
    rows = [row(kind="information_request", kind_label="Information request", due_date=date(2026, 9, 1), closed=False),
            row(kind="finding", kind_label="Finding", due_date=date(2026, 8, 1), closed=False),
            row(kind="finding", kind_label="Finding", due_date=date(2026, 7, 1), closed=False)]
    out = by_group(rows, "kind", TODAY)
    assert [g["kind"] for g in out] == ["finding", "information_request"]
    assert out[0]["label"] == "Finding"
    assert out[0]["overdue"]["n"] == 2
    assert out[1]["overdue"]["n"] == 1


def test_by_group_by_entity_uses_supervised_org_id_label():
    rows = [row(supervised_org_id="e1", supervised_org_id_label="Alpha Bank"),
            row(supervised_org_id="e2", supervised_org_id_label="Beta Re")]
    out = by_group(rows, "supervised_org_id", TODAY)
    ids = {g["supervised_org_id"]: g["label"] for g in out}
    assert ids == {"e1": "Alpha Bank", "e2": "Beta Re"}
