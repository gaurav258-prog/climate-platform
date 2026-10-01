"""Multi-currency phase 3: a filing presents money in its own currency and removes group-internal exposures.

  * solo → the entity's functional currency; an amount sent in that currency is shown exactly as sent;
  * consolidated → the group's presentation currency, balances at the closing rate of the period end, flows at the
    period average, the IAS 21.41(a) difference shown per entity;
  * an exposure to another group company stays in the solo filing and is eliminated on consolidation (in full against
    a fully consolidated counterparty, to the group's share against a proportional one);
  * every rate used is frozen with the filing; a later revision flags it; a restatement keeps the filing's scope.
Runs on the seeded Meridian hierarchy inside a rolled-back transaction."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from api.routers.bank import build_disclosure_snapshot
from services.governance import entities as E
from services.governance import filings as F
from services.governance.translation import plan, summary, translate_row
from services.reference.fx import average_rate, rate_for
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
PE = date(2025, 12, 31)


def _tree(s):
    by = {e["name"]: e for e in E.entity_tree(s, BANK_ORG)}
    need = ("Meridian Financial Group", "Meridian Bank AG", "Meridian Leasing GmbH", "Meridian Corporate Finance")
    if not all(n in by for n in need):
        pytest.skip("Meridian hierarchy not seeded")
    return [by[n] for n in need]


def _assets(s, eid, n):
    return [dict(r) for r in s.execute(text("""
        SELECT entity_id::text AS id, CAST(primary_value_eur AS FLOAT) AS v FROM portfolio_entities
        WHERE reporting_entity_id = CAST(:e AS uuid) AND vertical = 'banking' ORDER BY entity_id LIMIT :n
    """), {"e": eid, "n": n}).mappings()]


def _usd_asset(s, asset_id, amount):
    """Record an asset as sent in USD on the period end (and store its EUR value at that day's rate)."""
    u = rate_for(s, "USD", PE)["units_per_eur"]
    eur = round(amount / u, 2)
    ms = {"fields": {"appraised_value_eur": {"amount": amount, "currency": "USD", "book_date": PE.isoformat(), "eur": eur,
                                             "policy": "closing", "units_per_eur": u, "source": "ecb"}}}
    s.execute(text("UPDATE portfolio_entities SET primary_value_eur = :v, money_source = CAST(:m AS jsonb) WHERE entity_id = CAST(:i AS uuid)"),
              {"v": eur, "m": json.dumps(ms), "i": asset_id})
    return u


def _values(snap):
    return {a["asset_id"]: a["value_eur"] for a in snap["assets"]}


def test_solo_filing_presents_in_the_entitys_own_currency_exactly_as_sent(session_rolled_back):
    s = session_rolled_back
    _, _, leasing, _ = _tree(s)
    s.execute(text("UPDATE reporting_entities SET functional_currency = 'USD' WHERE entity_id = CAST(:e AS uuid)"),
              {"e": leasing["entity_id"]})
    a1, a2 = _assets(s, leasing["entity_id"], 2)
    u = _usd_asset(s, a1["id"], 1_234_567.89)
    t = plan(s, BANK_ORG, leasing["entity_id"], PE, scope=[leasing["entity_id"]])
    assert t.presentation == "USD"
    vals = _values(build_disclosure_snapshot(s, BANK_ORG, "baseline", "current", entity_ids=[leasing["entity_id"]], translation=t))
    assert vals[a1["id"]] == pytest.approx(1_234_567.89, abs=0.005)            # as sent — no round trip through EUR
    assert vals[a2["id"]] == pytest.approx(a2["v"] * u, rel=1e-9)             # entered in EUR: at the closing rate
    fx = summary(t)
    assert fx["presentation_currency"] == "USD" and any(r["currency"] == "USD" and r["basis"] == "closing"
                                                        and r["as_of"] == "2025-12-31" for r in fx["rates_used"])


def test_consolidation_translates_to_the_group_currency_and_eliminates_intragroup(session_rolled_back):
    s = session_rolled_back
    grp, bank, leasing, corp = _tree(s)
    s.execute(text("UPDATE reporting_entities SET functional_currency = 'USD' WHERE entity_id = CAST(:e AS uuid)"),
              {"e": leasing["entity_id"]})
    (la,) = _assets(s, leasing["entity_id"], 1)
    u = _usd_asset(s, la["id"], 5_000_000.0)
    b1, b2 = _assets(s, bank["entity_id"], 2)
    for asset, other in ((b1, leasing), (b2, corp)):
        s.execute(text("UPDATE portfolio_entities SET intragroup_entity_id = CAST(:o AS uuid) WHERE entity_id = CAST(:i AS uuid)"),
                  {"o": other["entity_id"], "i": asset["id"]})
    scope = E.subtree_ids(s, BANK_ORG, grp["entity_id"])
    w = E.ownership_weights(s, BANK_ORG, root_entity_id=grp["entity_id"], regime="crr_prudential")
    t = plan(s, BANK_ORG, grp["entity_id"], PE, scope=scope, weights=w)
    assert t.presentation == "EUR"
    vals = _values(build_disclosure_snapshot(s, BANK_ORG, "baseline", "current", entity_ids=scope, value_weights=w, translation=t))
    wl = w[leasing["entity_id"]]
    assert vals[la["id"]] == pytest.approx(5_000_000.0 / u * wl, rel=1e-9)    # USD → EUR at closing, then the 60% stake
    assert b2["id"] not in vals                                             # against a fully consolidated company: gone
    assert vals[b1["id"]] == pytest.approx(b1["v"] * (1 - wl), rel=1e-9)     # against the 60% joint operation: 60% removed
    fx = summary(t)
    assert fx["n_eliminations"] == 2 and fx["value_eliminated_total"] == pytest.approx(b1["v"] * wl + b2["v"], rel=1e-6)
    lrow = next(e for e in fx["translation"] if e["entity_id"] == leasing["entity_id"])
    assert lrow["functional_currency"] == "USD"

    # the same exposures stay in the holder's solo filing
    solo = plan(s, BANK_ORG, bank["entity_id"], PE, scope=[bank["entity_id"]])
    sv = _values(build_disclosure_snapshot(s, BANK_ORG, "baseline", "current", entity_ids=[bank["entity_id"]], translation=solo))
    assert sv[b1["id"]] == pytest.approx(b1["v"]) and sv[b2["id"]] == pytest.approx(b2["v"])
    assert summary(solo)["n_eliminations"] == 0


def test_flows_translate_at_the_period_average_and_the_difference_is_shown(session_rolled_back):
    s = session_rolled_back
    grp, _, leasing, _ = _tree(s)
    s.execute(text("UPDATE reporting_entities SET functional_currency = 'USD' WHERE entity_id = CAST(:e AS uuid)"),
              {"e": leasing["entity_id"]})
    t = plan(s, BANK_ORG, grp["entity_id"], PE, scope=E.subtree_ids(s, BANK_ORG, grp["entity_id"]))
    avg = average_rate(s, "USD", PE - timedelta(days=364), PE)["units_per_eur"]
    close = rate_for(s, "USD", PE)["units_per_eur"]
    noi_usd = 1_000_000.0
    ms = {"fields": {"annual_noi_eur": {"amount": noi_usd, "currency": "USD", "book_date": PE.isoformat(), "eur": round(noi_usd / avg, 2),
                                        "policy": "average", "period_start": (PE - timedelta(days=364)).isoformat()}}}
    row = {"reporting_entity_id": leasing["entity_id"], "annual_noi_eur": round(noi_usd / avg, 2)}
    translate_row(s, t, row, ms)
    assert row["annual_noi_eur"] == pytest.approx(noi_usd / avg, rel=1e-6)
    lrow = next(e for e in summary(t)["translation"] if e["entity_id"] == leasing["entity_id"])
    assert lrow["flows_functional"] == pytest.approx(noi_usd)
    assert lrow["translation_difference"] == pytest.approx(noi_usd / close - noi_usd / avg, abs=0.02)


def test_filing_freezes_its_currency_flags_rate_revisions_and_restates_in_scope(session_rolled_back):
    s = session_rolled_back
    _, _, leasing, _ = _tree(s)
    s.execute(text("UPDATE reporting_entities SET functional_currency = 'USD' WHERE entity_id = CAST(:e AS uuid)"),
              {"e": leasing["entity_id"]})
    user = s.execute(text("SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) ORDER BY created_at LIMIT 1"),
                     {"o": BANK_ORG}).scalar()
    tok = F.preflight(s, BANK_ORG, "bank", "bank_tcfd", leasing["entity_id"])["confirm_token"]   # the scope filed
    f = F.generate_filing(s, BANK_ORG, "bank", "bank_tcfd", user, confirm_token=tok, entity_id=leasing["entity_id"])
    assert f["presentation_currency"] == "USD" and f["filing_role"] == "solo"
    full = F.get_filing(s, BANK_ORG, f["filing_id"])
    fx = full["snapshot"]["payload"]["_fx"]
    assert fx["presentation_currency"] == "USD" and full["snapshot"]["reporting_basis"]["presentation_currency"] == "USD"
    assert full["fx_revisions"] == []

    # every rendering says USD: the form, the official annex, the XBRL unit (whole units at decimals="0")
    from services.governance.filing_export import export_filing
    form = F.form_view(s, BANK_ORG, f["filing_id"])
    assert form["currency"] == "USD" and form["fx"]["presentation_currency"] == "USD"
    assert "€" not in json.dumps(form["annex"], ensure_ascii=False)
    xml = export_filing(s, BANK_ORG, f["filing_id"], "xbrl")[2].decode()
    assert "iso4217:USD" in xml and "iso4217:EUR" not in xml and 'unitRef="uUSD" decimals="0"' in xml
    import re
    assert all("." not in v for v in re.findall(r'unitRef="uUSD" decimals="0">([^<]+)<', xml))

    # the ECB corrects the USD rate the filing used → the filing says so
    used = next(r for r in fx["rates_used"] if r["currency"] == "USD" and r["basis"] == "closing")
    s.execute(text("UPDATE fx_rates SET units_per_eur = units_per_eur * 1.001 WHERE ccy = 'USD' AND rate_date = :d AND source = :s"),
              {"d": date.fromisoformat(used["rate_date"][:10]), "s": used["source"]})
    rev = F.get_filing(s, BANK_ORG, f["filing_id"], with_payload=False)["fx_revisions"]
    assert rev and rev[0]["currency"] == "USD" and "revised" in rev[0]["change"]

    # a restatement keeps the filing's entity, role and currency (it used to become a whole-organisation filing)
    s.execute(text("ALTER TABLE regulatory_filing DISABLE TRIGGER USER"))
    s.execute(text("UPDATE regulatory_filing SET status = 'submitted' WHERE filing_id = CAST(:f AS uuid)"), {"f": f["filing_id"]})
    s.execute(text("ALTER TABLE regulatory_filing ENABLE TRIGGER USER"))
    new = F.restate_filing(s, BANK_ORG, f["filing_id"], user, "USD rate corrected by the ECB")
    assert (new["entity_id"], new["filing_role"], new["presentation_currency"]) == (leasing["entity_id"], "solo", "USD")


def test_a_file_names_the_holding_entity_and_the_intragroup_counterparty(session_rolled_back):
    import uuid

    import pandas as pd

    from services.intake import staging
    from services.intake.catalog import TEMPLATES
    from services.intake.pipeline import enrich_specs
    from tests.integration.test_intake_pipeline import _rows
    s = session_rolled_back
    _, bank, leasing, _ = _tree(s)
    tag = uuid.uuid4().hex[:8]
    rows = [{**r, "external_ref": f"{tag}-{i}"} for i, r in enumerate(_rows(tag, n=4))]
    rows[0]["reporting_entity"] = "meridian leasing gmbh"                       # by name, any case
    rows[1].update(reporting_entity=bank["entity_id"], intragroup_counterparty="Meridian Leasing GmbH")
    rows[2]["reporting_entity"] = "Nope Holdings Ltd"                           # not one of theirs → refused
    rows[3].update(reporting_entity="Meridian Leasing GmbH", intragroup_counterparty="Meridian Leasing GmbH")
    tpl = TEMPLATES["bank_assets"]
    df = pd.DataFrame(rows)
    st = staging.stage(s, BANK_ORG, tpl.sector, df, enrich_specs(tpl.specs(df)),
                       {"currency": "EUR", "book_date": date(2026, 6, 30), "field_currency": {}})
    why = {e["row"]: " ".join(e["problems"]) for e in st["report"]["errors"]}
    assert "not one of your legal entities" in why[4] and "same entity" in why[5] and len(st["staged"]) == 2
    staging.land(s, BANK_ORG, tpl.sector, st)
    got = {r[0]: (r[1], r[2]) for r in s.execute(text("""
        SELECT external_ref, reporting_entity_id::text, intragroup_entity_id::text FROM portfolio_entities
        WHERE org_id = CAST(:o AS uuid) AND external_ref LIKE :t"""), {"o": BANK_ORG, "t": f"{tag}-%"})}
    assert got == {f"{tag}-0": (leasing["entity_id"], None), f"{tag}-1": (bank["entity_id"], leasing["entity_id"])}


def test_an_entity_filing_is_identified_by_the_entitys_own_lei(session_rolled_back):
    from services.governance.filing_export import ExportError, export_filing
    s = session_rolled_back
    _, _, leasing, _ = _tree(s)
    with pytest.raises(E.EntityError, match="not a valid LEI"):
        E.update_entity(s, BANK_ORG, leasing["entity_id"], lei="5493001KJTIIGC8Y1R13")          # check digits wrong
    E.update_entity(s, BANK_ORG, leasing["entity_id"], lei="5493001kjtiigc8y1r12")              # stored upper-case
    user = s.execute(text("SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) ORDER BY created_at LIMIT 1"),
                     {"o": BANK_ORG}).scalar()
    tok = F.preflight(s, BANK_ORG, "bank", "bank_tcfd", leasing["entity_id"])["confirm_token"]   # the scope filed
    f = F.generate_filing(s, BANK_ORG, "bank", "bank_tcfd", user, confirm_token=tok, entity_id=leasing["entity_id"])
    xml = export_filing(s, BANK_ORG, f["filing_id"], "xbrl")[2].decode()
    assert ">5493001KJTIIGC8Y1R12<" in xml and "filing entity's own LEI" in xml
    E.update_entity(s, BANK_ORG, leasing["entity_id"], lei=None)
    xml = export_filing(s, BANK_ORG, f["filing_id"], "xbrl")[2].decode()
    assert "has no LEI on file — identified by the organisation's LEI" in xml
    s.execute(text("UPDATE organizations SET lei = NULL WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG})
    with pytest.raises(ExportError, match="no LEI on file"):                                     # never a made-up identifier
        export_filing(s, BANK_ORG, f["filing_id"], "xbrl")
