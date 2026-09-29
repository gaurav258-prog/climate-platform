"""A reporting period's label is one fact with its end: the database refuses a label that does not match (E27)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("table", ["regulatory_filing", "regulatory_obligation", "supervision_deadline"])
def test_a_label_that_contradicts_its_period_end_is_refused(session_rolled_back, table):
    s = session_rolled_back
    only_drafts = " WHERE status = 'draft'" if table == "regulatory_filing" else ""   # a filed record is write-protected
    row = s.execute(text(f"SELECT ctid FROM {table}{only_drafts} LIMIT 1")).scalar()
    if row is None:
        pytest.skip(f"no {table} rows in this database")
    with pytest.raises(IntegrityError, match="period_label"):
        with s.begin_nested():
            s.execute(text(f"UPDATE {table} SET period_label = period_label || '-Q3' WHERE ctid = :c"), {"c": row})
