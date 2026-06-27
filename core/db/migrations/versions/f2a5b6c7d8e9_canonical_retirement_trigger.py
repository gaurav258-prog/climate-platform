"""canonical_retirement_trigger

Correct the canonical_scores immutability rule. The original trigger blocked ALL
UPDATEs, but the platform marks a score stale by setting valid_to (everything
queries `valid_to IS NULL`). So re-scoring a cell could never retire the old
row — the append-only rule and the retirement mechanism contradicted each other,
and scoring failed the moment it tried to re-score.

The correct rule is append-only WITH logical retirement: the score payload is
immutable, but a live row (valid_to IS NULL) may be retired exactly once by
setting valid_to. DELETE stays forbidden; retired rows stay immutable;
un-retiring is forbidden; and changing any payload column is forbidden.

Revision ID: f2a5b6c7d8e9
Revises: e1f4a5b6c7d8
Create Date: 2026-06-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f2a5b6c7d8e9"
down_revision: Union[str, None] = "e1f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_FN = """
CREATE OR REPLACE FUNCTION prevent_canonical_score_mutation() RETURNS TRIGGER AS $$
DECLARE chk canonical_scores;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'canonical_scores is append-only: DELETE is not permitted';
    END IF;
    -- UPDATE: the only permitted change is retiring a live row via valid_to.
    IF OLD.valid_to IS NOT NULL THEN
        RAISE EXCEPTION 'canonical_scores: retired rows are immutable';
    END IF;
    IF NEW.valid_to IS NULL THEN
        RAISE EXCEPTION 'canonical_scores is append-only: only setting valid_to (retirement) is permitted';
    END IF;
    -- Neutralise valid_to and compare the whole row: any other change is rejected.
    chk := NEW; chk.valid_to := OLD.valid_to;
    IF chk IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'canonical_scores: score payload is immutable; only valid_to may change';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

OLD_FN = """
CREATE OR REPLACE FUNCTION prevent_canonical_score_mutation() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'canonical_scores is append-only: % operations are not permitted',
        TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(NEW_FN)


def downgrade() -> None:
    op.execute(OLD_FN)
