"""SFDR pre-contractual disclosure (RTS Annex II / III) — Article 8 vs Article 9
branching, and the honest computed-vs-declared field split. Requires PostgreSQL.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory.sfdr_precontractual import build_precontractual

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


def _seed(s, classification):
    fid = str(s.execute(text(
        "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
        "VALUES (:o,'TEST Precontractual Fund','fund',:c) RETURNING fund_id"),
        {"o": DEMO_ORG, "c": classification}).scalar())
    iid = str(s.execute(text(
        "INSERT INTO issuers (name,issuer_type,country,nace_code,source) "
        "VALUES ('Precontractual Issuer','corporate','DE','35.11','manual') RETURNING issuer_id")).scalar())
    sid = str(s.execute(text(
        "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
        "VALUES ('DE00PRECONT1','Precontractual Sec',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
    s.execute(text(
        "INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
        "VALUES (:f,:s,1000000,100,'2026-07-12')"), {"f": fid, "s": sid})
    return fid, iid


def _cleanup(fid, iid):
    with get_session() as s:
        s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": fid})
        s.execute(text("DELETE FROM securities WHERE isin='DE00PRECONT1'"))
        s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": iid})


def _find(sections, label_substr):
    return next(s for s in sections if label_substr.lower() in s["field"].lower())


@pytest.mark.integration
def test_article_9_branches_to_annex_iii_and_sustainable_objective():
    with get_session() as s:
        fid, iid = _seed(s, "article_9")
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        assert r["entity"]["sfdr_classification"] == "article_9"
        assert "Annex III" in r["template"]
        obj = next(s for s in r["sections"] if s["field"] == "Sustainable investment objective")
        # Art 9's top question is answered "Yes" — computed from classification, never guessed.
        top = _find(r["sections"], "Does this financial product have a sustainable investment objective")
        assert top["status"] == "computed"
        assert "Yes" in top["value"]
        assert obj["source"] == "customer/declared"
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_article_8_branches_to_annex_ii_and_characteristics():
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        assert r["entity"]["sfdr_classification"] == "article_8"
        assert "Annex II" in r["template"]
        top = _find(r["sections"], "Does this financial product have a sustainable investment objective")
        assert "No" in top["value"]
        char = _find(r["sections"], "characteristics promoted")
        assert char["source"] == "customer/declared"
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_unclassified_fund_is_an_honest_gap_not_a_guess():
    with get_session() as s:
        fid, iid = _seed(s, None)
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        assert r.get("error")
        assert r["sfdr_classification"] is None
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_narrative_fields_are_declared_never_fabricated_until_set():
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        strategy = _find(r["sections"], "investment strategy does this financial product")
        assert strategy["status"] == "not_available"
        assert strategy["value"] is None
        assert strategy["input_required"]

        # Declare it, then confirm it surfaces as a "declared" field, not silently computed.
        with get_session() as s:
            s.execute(text("UPDATE funds SET sfdr_precontractual = CAST(:p AS jsonb) WHERE fund_id = :f"),
                      {"p": json.dumps({"investment_strategy": "Best-in-class ESG screening across the universe."}),
                       "f": fid})
        with get_session() as s:
            r2 = build_precontractual(s, fid)
        strategy2 = _find(r2["sections"], "investment strategy does this financial product")
        assert strategy2["status"] == "declared"
        assert strategy2["source"] == "customer/declared"
        assert "Best-in-class" in strategy2["value"]
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_taxonomy_kpi_section_is_computed_from_golden_source():
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        tax_section = _find(r["sections"], "aligned with the EU Taxonomy")
        assert tax_section["source"].startswith("golden source")
        assert "taxonomy_aligned_turnover_pct" in tax_section["value"]
        assert "taxonomy_aligned_capex_pct" in tax_section["value"]
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_dnsh_boilerplate_is_fixed_regulatory_text():
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        dnsh = _find(r["sections"], "do no significant harm")
        assert dnsh["status"] == "computed"
        assert "do no significant harm" in dnsh["value"].lower()
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_dnsh_methodology_undeclared_is_not_available_not_not_applicable():
    """A fund with no declared planned-investment % (a fresh, never-configured fund) is UNKNOWN, not zero —
    the DNSH-methodology question must be 'not_available' (a real, counted gap needing operator input), never
    'not_applicable' (which would silently exclude it from the coverage_summary gap count and make the
    disclosure look more complete than it actually is). Adversarial-review regression test."""
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        dnsh_method = _find(r["sections"], "not cause significant harm")
        assert dnsh_method["status"] == "not_available"
        assert dnsh_method["input_required"] is not None
        assert r["coverage_summary"]["not_available"] >= 1
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_dnsh_methodology_genuinely_not_applicable_when_planned_pct_is_zero():
    """A fund that explicitly declared 0% planned sustainable investments genuinely has nothing for a DNSH
    methodology to apply to — that IS a correct 'not_applicable', distinct from simply not having declared
    anything yet."""
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
        s.execute(text(
            "UPDATE funds SET sfdr_precontractual = :p WHERE fund_id = :f"),
            {"f": fid, "p": json.dumps({"proportion_investments_planned_pct": 0})})
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        dnsh_method = _find(r["sections"], "not cause significant harm")
        assert dnsh_method["status"] == "not_applicable"
        assert dnsh_method["input_required"] is None
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_taxonomy_kpi_defaults_to_turnover_basis():
    """Per SFDR Del. Reg. Art. 15(3)/19(3), turnover is the default basis for the fund-level 'minimum
    extent' Taxonomy figure when the manager hasn't declared otherwise."""
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        tax_section = _find(r["sections"], "aligned with the EU Taxonomy")
        assert tax_section["value"]["basis"] == "turnover"
        assert "Art. 15(3)/19(3)" in tax_section["note"]
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_taxonomy_kpi_basis_respects_manager_declared_capex_choice():
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
        s.execute(text("UPDATE funds SET sfdr_precontractual = :p WHERE fund_id = :f"),
                  {"f": fid, "p": json.dumps({"taxonomy_kpi_basis": "capex"})})
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        tax_section = _find(r["sections"], "aligned with the EU Taxonomy")
        assert tax_section["value"]["basis"] == "capex"
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_article_8_sustainable_investments_toggle_undeclared_defaults_to_characteristics_only():
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        tickbox = _find(r["sections"], "have a sustainable investment objective")
        assert "characteristics only" in tickbox["value"]
        assert "Article 8" in tickbox["value"]
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_article_8_sustainable_investments_toggle_when_declared_true():
    """Per ESAs SFDR Q&A JC 2023 18 (V.29): an Article 8 product can ALSO tick a partial sustainable-
    investments commitment, distinct from simply promoting E/S characteristics."""
    with get_session() as s:
        fid, iid = _seed(s, "article_8")
        s.execute(text("UPDATE funds SET sfdr_precontractual = :p WHERE fund_id = :f"),
                  {"f": fid, "p": json.dumps({"makes_sustainable_investments": True})})
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        tickbox = _find(r["sections"], "have a sustainable investment objective")
        assert "partial SI commitment" in tickbox["value"]
    finally:
        _cleanup(fid, iid)


@pytest.mark.integration
def test_env_and_social_sustainable_pct_need_not_sum_to_total():
    with get_session() as s:
        fid, iid = _seed(s, "article_9")
        s.execute(text("UPDATE funds SET sfdr_precontractual = :p WHERE fund_id = :f"),
                  {"f": fid, "p": json.dumps({"env_sustainable_pct": 40, "social_sustainable_pct": 15})})
    try:
        with get_session() as s:
            r = build_precontractual(s, fid)
        env = _find(r["sections"], "environmentally sustainable investments")
        social = _find(r["sections"], "socially sustainable investments")
        assert env["value"] == "40%" and social["value"] == "15%"
        assert "need not sum" in env["note"]
    finally:
        _cleanup(fid, iid)
