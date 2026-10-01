"""A group filing consolidates by the rule of the text that governs it — never a switch or a platform default (E75).
data/reference/consolidation/regimes.json declares, per framework, the regime and quotes it."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from services.governance.entities import consolidation_regimes, regime_for

REG = consolidation_regimes()


def test_every_entity_scoped_framework_is_governed_by_a_declared_regime():
    from services.governance.filings import _ENTITY_SCOPED
    for fw in _ENTITY_SCOPED:
        assert REG["regimes"][regime_for(fw)]["refs"], fw
    with pytest.raises(ValueError, match="no consolidation regime"):
        regime_for("no_such_framework")


def test_every_regime_has_the_three_methods_and_quotes():
    for name, r in REG["regimes"].items():
        assert set(r["factors"]) == {"full", "proportional", "equity"}, name
        assert set(r["factors"].values()) <= {"full", "proportional", "excluded"}, name
        assert r["refs"] and all(x["ref"] and x["quote"] for x in r["refs"]), name


def test_the_platform_offers_no_equity_switch():
    from services.calc_settings import INTERPRETATION_SCHEMA
    assert "equity_consolidation" not in INTERPRETATION_SCHEMA


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip()


@pytest.mark.skipif(not os.getenv("ESRS_SOURCE_TEXTS"), reason="ESRS_SOURCE_TEXTS (the downloaded texts) not set")
def test_every_quote_is_in_the_downloaded_texts():
    texts = []
    for p in Path(os.environ["ESRS_SOURCE_TEXTS"]).glob("*.txt"):
        texts.append(_norm(re.sub(r"<[^>]+>", " ", p.read_text(errors="ignore"))))
    missing = [x["ref"] for r in REG["regimes"].values() for x in r["refs"] if not any(_norm(x["quote"]) in t for t in texts)]
    assert not missing, missing
