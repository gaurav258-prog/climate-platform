"""E303: the validation ledger's text-column lengths, as the engine checks them when a result is built, are the ones
the database declares — so a result too long is refused before anything is written, never at INSERT half-way through
a batch."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.validation.engine import LIMITS, ValidationResult

pytestmark = pytest.mark.integration


def test_the_engine_checks_every_text_column_of_the_ledger_at_its_declared_length(session_rolled_back):
    declared = dict(session_rolled_back.execute(text("""
        SELECT column_name, character_maximum_length FROM information_schema.columns
        WHERE table_name = 'validation_run' AND character_maximum_length IS NOT NULL""")).all())
    # gate, skill_grade, code_version and created_by are written by the engine itself, never by a validator
    assert {k: declared[k] for k in LIMITS} == LIMITS
    assert set(declared) - set(LIMITS) == {"gate", "skill_grade", "code_version", "created_by"}


def test_a_result_too_long_for_the_ledger_is_refused_when_built():
    with pytest.raises(ValueError, match="data_vintage is 61 characters"):
        ValidationResult(hazard_type="flood_loss", kind="rank", predicted=[], observed=[], target_source="x",
                         data_vintage="v" * 61)
