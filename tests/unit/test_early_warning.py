"""Early-warning fires on the physical hazard at the stated at-risk level, never gated by whether the euro is publishable."""
from types import SimpleNamespace

from api.routers.supply import early_warning_alerts

LEVEL = 55.0     # the company's stated at-risk level — a test value (method.at_risk_level)


def _c(commodity, avg, status, calib="indicative"):
    return SimpleNamespace(commodity=commodity, top_hazard="frost", avg_hazard=avg, annual_spend_eur=1000,
                           cogs_at_risk_p50=None, calibration=calib, status=status)


def test_held_high_hazard_still_alerts():
    # the regression: a 'held' commodity (€ withheld by the honesty gate) at extreme hazard must still warn
    alerts = early_warning_alerts([_c("Coffee", 99.4, "held")], LEVEL)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "VH" and alerts[0]["euro_published"] is False


def test_scored_marks_euro_published():
    alerts = early_warning_alerts([_c("Cocoa", 80, "scored", calib="calibrated")], LEVEL)
    assert alerts[0]["euro_published"] is True


def test_pending_and_low_hazard_do_not_alert():
    alerts = early_warning_alerts([
        _c("Maize", 90, "pending"),   # no hazard score yet
        _c("Barley", 40, "held"),     # real but below the stated level
        _c("Wheat", 88, "held"),      # should alert
    ], LEVEL)
    assert {a["commodity"] for a in alerts} == {"Wheat"}


def test_sorted_most_severe_first():
    alerts = early_warning_alerts([_c("A", 60, "held"), _c("B", 99, "held"), _c("C", 75, "scored")], LEVEL)
    assert [a["commodity"] for a in alerts] == ["B", "C", "A"]


def test_the_alert_line_is_the_stated_level():
    assert early_warning_alerts([_c("Barley", 60, "held")], 70.0) == []
    assert [a["commodity"] for a in early_warning_alerts([_c("Barley", 60, "held")], 60.0)] == ["Barley"]
    assert early_warning_alerts([_c("Barley", 60, "held")], 60.0)[0]["level"] == "H"      # the one shared band
