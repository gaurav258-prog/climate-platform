"""Storm v3 is a return level over annual maxima, not the worst event on record."""
import numpy as np

from ml.scoring.storm_physics import wind_to_score
from ml.scoring.storm_return_level import return_level_kt


def test_return_level_reads_the_annual_maxima_not_the_worst_event():
    quiet = np.array([0.0] * 44 + [120.0, 0.0])          # one monster storm in 46 seasons
    assert return_level_kt(quiet) == 0.0                   # 1-in-10: nothing to expect most decades
    busy = np.array([70.0] * 40 + [0.0] * 6)             # hurricane-force most seasons
    assert return_level_kt(busy) == 70.0
    assert return_level_kt(np.array([50.0] * 5)) == 0.0    # fewer than 10 seasons: no level claimed
    assert wind_to_score(96.0) == 65.0 and wind_to_score(0.0) == 0.0


class _Session:
    """Stub: only the season-range query the guard runs before any cell is loaded."""
    def __init__(self, y0, y1, basins): self.row = (y0, y1, basins)
    def execute(self, *_a, **_k):
        row = self.row
        class R:
            def first(self_inner): return row
        return R()


def test_holdout_refuses_a_window_shorter_than_the_return_period():
    from services.validation.validators.storm_holdout import _run
    r = _run(_Session(1981, 2026, 5), holdout_from=2019)        # 8 seasons held out < 10-year level
    assert r.predicted == [] and "only 8 seasons are held out" in r.notes and "STORM_HOLDOUT_FROM ≤ 2017" in r.notes
    r = _run(_Session(2015, 2026, 1), holdout_from=2019)        # short, single-basin record
    assert r.predicted == [] and "12 seasons" in r.notes


def test_severity_target_reads_the_storm_not_one_track_point():
    from services.validation.validators.storm_severity import RADIUS_KM
    assert RADIUS_KM == 100.0
