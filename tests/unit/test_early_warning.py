"""Early-warning fires on the physical hazard, never gated by whether the euro is publishable."""
from types import SimpleNamespace

from api.routers.supply import early_warning_alerts


def _c(commodity, avg, status, calib="indicative"):
    return SimpleNamespace(commodity=commodity, top_hazard="frost", avg_hazard=avg, annual_spend_eur=1000,
                           cogs_at_risk_p50=None, calibration=calib, status=status)


def test_held_high_hazard_still_alerts():
    # the regression: a 'held' commodity (€ withheld by the honesty gate) at extreme hazard must still warn
    alerts = early_warning_alerts([_c("Coffee", 99.4, "held")])
    assert len(alerts) == 1
    assert alerts[0]["level"] == "VH" and alerts[0]["euro_published"] is False


def test_scored_marks_euro_published():
    alerts = early_warning_alerts([_c("Cocoa", 80, "scored", calib="calibrated")])
    assert alerts[0]["euro_published"] is True


def test_pending_and_low_hazard_do_not_alert():
    alerts = early_warning_alerts([
        _c("Maize", 90, "pending"),   # no hazard score yet
        _c("Barley", 40, "held"),     # real but below the 55 threshold
        _c("Wheat", 88, "held"),      # should alert
    ])
    assert {a["commodity"] for a in alerts} == {"Wheat"}


def test_sorted_most_severe_first():
    alerts = early_warning_alerts([_c("A", 60, "held"), _c("B", 99, "held"), _c("C", 75, "scored")])
    assert [a["commodity"] for a in alerts] == ["B", "C", "A"]
