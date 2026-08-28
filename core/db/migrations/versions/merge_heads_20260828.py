"""Merge the three divergent Alembic heads into one.

The chain had grown three parallel heads (org_calc_interp_202608, passkeys_esign_20260826,
nav_role_perms_20260827) because features landed on independent branches. Multiple heads make
`alembic upgrade head` ambiguous and block a clean single-command migration — a production
change-control red flag. This is a no-op merge revision: it introduces no schema change, it only
re-joins the branches so there is exactly one head again. A CI guard (scripts/check_migrations.py)
now fails the build if more than one head ever reappears.

Revision ID: merge_heads_20260828
Revises: org_calc_interp_202608, passkeys_esign_20260826, nav_role_perms_20260827
"""
from __future__ import annotations

revision = "merge_heads_20260828"
down_revision = ("org_calc_interp_202608", "passkeys_esign_20260826", "nav_role_perms_20260827")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: this revision only re-joins branches; it changes no schema."""


def downgrade() -> None:
    """No-op: splitting back into three heads is never desired."""
