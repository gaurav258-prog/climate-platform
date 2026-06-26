import csv
import io
from pathlib import Path

import pytest

from core.types import HazardType
from services.ingestion.adapters.nasa_firms import NASAFIRMSAdapter, CONFIDENCE_THRESHOLD

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load_fixture(filename: str) -> list[dict]:
    text = (FIXTURES / filename).read_text()
    return list(csv.DictReader(io.StringIO(text)))


def test_high_confidence_rows_are_not_flagged():
    adapter = NASAFIRMSAdapter()
    raw = load_fixture("sample_firms.csv")
    obs = adapter.to_observations(raw)

    good = [o for o in obs if o.quality_flag == 0]
    # rows with confidence 87, 92, 75 are above threshold (50)
    assert len(good) == 3


def test_low_confidence_rows_are_flagged():
    adapter = NASAFIRMSAdapter()
    raw = load_fixture("sample_firms.csv")
    obs = adapter.to_observations(raw)

    flagged = [o for o in obs if o.quality_flag == 1]
    # rows with confidence 30 and 20 are below threshold
    assert len(flagged) == 2
    assert all(o.quality_notes is not None for o in flagged)


def test_all_observations_are_wildfire():
    adapter = NASAFIRMSAdapter()
    raw = load_fixture("sample_firms.csv")
    obs = adapter.to_observations(raw)

    assert all(o.hazard_type == HazardType.WILDFIRE.value for o in obs)


def test_raw_value_is_frp_in_mw():
    adapter = NASAFIRMSAdapter()
    raw = load_fixture("sample_firms.csv")
    obs = adapter.to_observations(raw)

    # First row: frp=23.1
    assert float(obs[0].raw_value) == pytest.approx(23.1)
    assert obs[0].raw_unit == "MW"


def test_h3_cell_is_assigned_and_correct_length():
    adapter = NASAFIRMSAdapter()
    raw = load_fixture("sample_firms.csv")
    obs = adapter.to_observations(raw)

    assert all(o.h3_cell is not None for o in obs)
    # H3 resolution 8 cell IDs are 15 hex chars
    assert all(len(o.h3_cell) == 15 for o in obs)


def test_source_provider_is_set():
    adapter = NASAFIRMSAdapter()
    raw = load_fixture("sample_firms.csv")
    obs = adapter.to_observations(raw)

    assert all(o.source_provider == "nasa_firms_viirs" for o in obs)


def test_malformed_row_is_skipped_not_raised():
    adapter = NASAFIRMSAdapter()
    raw = [{"latitude": "not_a_number", "longitude": "6.78", "frp": "10", "confidence": "80",
            "acq_date": "2024-07-25", "acq_time": "1342"}]
    obs = adapter.to_observations(raw)
    # Should silently skip rather than raise
    assert obs == []
