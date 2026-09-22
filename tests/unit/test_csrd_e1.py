"""CSRD / ESRS E1 report (services/intelligence/csrd_e1.py) — ESRS E1-9 para 66(a)/(b)/(d) additions.

Pins the new percentage-of-total figures (para 66(a) assets, para 66(d) revenue) and the quantified
adaptation-coverage share of at-risk assets addressed by a disclosed action (para 66(b)). Own-ops
sites and upstream sourcing are monkeypatched with canned data (pure-function testing, no DB), same
approach as the other agri unit tests using a tiny fake session for the two raw SQL reads left.
"""
from dataclasses import dataclass, field
from typing import Optional

import services.intelligence.csrd_e1 as csrd_e1


class _Result:
    def __init__(self, rows): self._rows = rows
    def mappings(self): return self
    def first(self): return self._rows[0] if self._rows else None
    def all(self): return self._rows


class _FakeSession:
    """Only serves the two raw queries build_e1_report still issues directly: the org row and the
    forward-horizons rollup (irrelevant to the figures under test, so it's always empty)."""
    def __init__(self, org): self._org = org
    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM organizations" in sql:
            return _Result([self._org])
        return _Result([])  # horizons query — not under test here


@dataclass
class _Portfolio:
    ingredient_spend_eur: float = 0.0
    total_cogs_eur: float = 0.0
    cogs_at_risk_p50: float = 0.0
    volume_at_risk_eur: float = 0.0
    pct_cogs_at_risk: float = 0.0
    n_commodities: int = 0
    commodities: list = field(default_factory=list)


ORG = {"name": "Terra Foods", "type": "cpg", "country": "ES", "eori": "ES123"}


def _site(value_eur, throughput_eur, hazard_score, top_hazard):
    return {"value_eur": value_eur, "throughput_eur": throughput_eur,
            "hazard_score": hazard_score, "top_hazard": top_hazard}


def _run(monkeypatch, sites, portfolio=None):
    monkeypatch.setattr(csrd_e1, "list_sites_with_risk", lambda *a, **k: sites)
    monkeypatch.setattr(csrd_e1, "project_org_supply", lambda *a, **k: portfolio or _Portfolio())
    return csrd_e1.build_e1_report(_FakeSession(ORG), "org")


def test_pct_of_assets_and_revenue_at_risk_are_computed_against_the_own_ops_total(monkeypatch):
    # one site at risk (drought, 60) out of two: 40% of asset value, 100% of the throughput sits on
    # the at-risk site here so business-interruption is a known fraction of total throughput.
    sites = [_site(600_000, 200_000, 60, "drought"), _site(400_000, 0, 10, "drought")]
    rep = _run(monkeypatch, sites)
    fe = rep["financial_effects"]
    assert fe["asset_value_at_risk_eur"] == 600_000
    assert fe["pct_of_assets_at_risk"] == round(100.0 * 600_000 / 1_000_000, 1)
    assert fe["pct_of_revenue_at_risk"] == round(100.0 * fe["business_interruption_eur"] / 200_000, 1)


def test_pct_fields_are_none_not_zero_when_there_is_no_own_ops_total(monkeypatch):
    rep = _run(monkeypatch, [])
    fe = rep["financial_effects"]
    assert fe["pct_of_assets_at_risk"] is None
    assert fe["pct_of_revenue_at_risk"] is None
    assert fe["adaptation_coverage_pct_of_at_risk_assets"] is None


def test_adaptation_coverage_counts_only_at_risk_value_whose_hazard_has_a_disclosed_action(monkeypatch):
    # drought has a disclosed adaptation action (services.intelligence.adaptation); landslide is a real
    # CLIMATE hazard (hazard_scope.ACUTE) but has no entry in adaptation._ACTIONS — genuinely uncovered.
    sites = [
        _site(300_000, 0, 55, "drought"),     # covered
        _site(200_000, 0, 55, "landslide"),   # at risk, but NO disclosed action → uncovered
    ]
    rep = _run(monkeypatch, sites)
    fe = rep["financial_effects"]
    assert fe["asset_value_at_risk_eur"] == 500_000
    assert fe["asset_value_at_risk_addressed_by_adaptation_eur"] == 300_000
    assert fe["adaptation_coverage_pct_of_at_risk_assets"] == round(100.0 * 300_000 / 500_000, 1)


def test_adaptation_coverage_full_when_every_at_risk_hazard_has_an_action(monkeypatch):
    sites = [_site(500_000, 0, 70, "flood")]
    rep = _run(monkeypatch, sites)
    assert rep["financial_effects"]["adaptation_coverage_pct_of_at_risk_assets"] == 100.0


def test_below_threshold_sites_never_enter_the_at_risk_or_coverage_figures(monkeypatch):
    sites = [_site(1_000_000, 500_000, 10, "drought")]   # score below MATERIAL_THRESHOLD (40)
    rep = _run(monkeypatch, sites)
    fe = rep["financial_effects"]
    assert fe["asset_value_at_risk_eur"] == 0
    assert fe["pct_of_assets_at_risk"] == 0.0
    assert fe["adaptation_coverage_pct_of_at_risk_assets"] is None
