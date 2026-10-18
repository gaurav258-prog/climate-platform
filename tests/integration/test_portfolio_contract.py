"""The Portfolio cards read what the server sends (ui-portfolio session): each card declares the shape it reads as a
TypeScript interface, and this test holds the server to it — every field the card requires is in the response, and every
optional field is one the server's code can send. It caught the expected-loss card reading three fields the server had
stopped sending (maturity_fed, maturity_assumed, default_tenor_years — the screen showed "/NaN loans use fed maturity")
and labelling every loan's maturity as assumed when all came from the loan tape. Also: the movers carry the year their
scores are for, the year the card names. Skips cleanly if the demo bank is not in this environment.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.expected_loss import bank_expected_loss
from services.intelligence.forward_risk import HORIZONS, forward_risk
from services.money.params import Method, for_org

ROOT = Path(__file__).resolve().parents[2]
BANK_ORG = "11111111-1111-4111-8111-111111111111"
STATED = {("method.at_risk_level", None): 50.0, ("method.runway_materiality", None): 0.05}


def fields(tsx: str, interface: str) -> tuple[set[str], set[str]]:
    """(required, optional) field names of a TypeScript interface in a web source file."""
    src = (ROOT / tsx).read_text(encoding="utf-8")
    at = re.search(rf"\binterface {interface}\s*\{{", src)
    assert at, f"{interface} not found in {tsx}"
    depth, i = 1, at.end()
    while depth:                                       # to the interface's own closing brace
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        i += 1
    body = re.sub(r"\{[^{}]*\}", "", src[at.end():i - 1])  # an inline object type's fields are not the interface's
    names = re.findall(r"(\w+)(\?)?\s*:", body)
    return {n for n, o in names if not o}, {n for n, o in names if o}


def holds(card: str, interface: str, sent: dict, server_code: list[str]) -> None:
    required, optional = fields(card, interface)
    assert required <= set(sent), f"{card} {interface} reads fields the server does not send: {sorted(required - set(sent))}"
    source = "".join((ROOT / f).read_text(encoding="utf-8") for f in server_code)
    unknown = sorted(n for n in optional if f'"{n}"' not in source)
    assert not unknown, f"{card} {interface} reads fields the server never sends: {unknown}"


@pytest.fixture(scope="module")
def bank():
    with get_session() as s:
        n = s.execute(text("SELECT COUNT(*) FROM portfolio_entities WHERE org_id=:o AND vertical='banking'"),
                      {"o": BANK_ORG}).scalar()
        if not n:
            pytest.skip("demo bank not present")
        return {"el": bank_expected_loss(s, BANK_ORG, "disorderly_2c", method=for_org(s, BANK_ORG)),
                "fwd": forward_risk(s, BANK_ORG, "banking", "disorderly_2c", Method.of(STATED, date(2025, 12, 31)))}


def test_the_expected_loss_card_reads_what_the_server_sends(bank):
    card, code = "web/src/components/ExpectedLossCard.tsx", ["services/intelligence/expected_loss.py"]
    holds(card, "ELResp", bank["el"], code)
    for a in bank["el"]["assets"][:20]:
        holds(card, "ELAsset", a, code)


def test_the_forward_risk_card_reads_what_the_server_sends(bank):
    card, code = "web/src/pages/portfolio/ForwardRisk.tsx", ["services/intelligence/forward_risk.py"]
    holds(card, "ForwardRisk", bank["fwd"], code)
    for p in bank["fwd"]["trajectory"]:
        holds(card, "Point", p, code)
    for m in bank["fwd"]["movers"]:
        holds(card, "Mover", m, code)


def test_the_movers_are_all_for_the_year_the_card_names(bank):
    movers = bank["fwd"]["movers"]
    if not movers:
        pytest.skip("no adverse movers in this environment")
    years = {m["horizon"] for m in movers}
    assert len(years) == 1 and years <= set(HORIZONS)
