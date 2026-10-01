"""KRI appetite bands follow their KRI set when the report it was anchored on is retired (E87).

The REIT and insurer KRI sets were keyed by the retired TCFD-style report types (reit_tcfd, insurer_climate); they are
now anchored on the sector's live governed report (reit_taxonomy, insurer_solvency). A band is stored per (framework,
kri_key), so the platform defaults and every organisation's own bands are copied to the new key — the organisation's
copy recorded as the next version of that band, with the reason. The old rows and their version history stay as they
were (history). The asset-manager holdings set had no band (it now sits in the sfdr_pai set).

Revision ID: kri_reanchor_20261001
Revises: event_sequence_20261001
"""
from alembic import op

revision = "kri_reanchor_20261001"
down_revision = "event_sequence_20261001"
branch_labels = None
depends_on = None

_MOVES = (("reit_tcfd", "reit_taxonomy"), ("insurer_climate", "insurer_solvency"))
_REASON = "re-anchored from {old} (report type retired) — E87"


def upgrade() -> None:
    for old, new in _MOVES:
        reason = _REASON.format(old=old)
        op.execute(f"""
            INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction, updated_by, updated_at)
            SELECT k.org_id, '{new}', k.kri_key, k.amber, k.red, k.direction, k.updated_by, now()
            FROM kri_threshold k
            WHERE k.framework = '{old}'
              AND NOT EXISTS (SELECT 1 FROM kri_threshold n WHERE n.framework = '{new}' AND n.kri_key = k.kri_key
                                                            AND n.org_id IS NOT DISTINCT FROM k.org_id)
        """)
        op.execute(f"""
            INSERT INTO kri_threshold_version (org_id, framework, kri_key, version, amber, red, direction, previous, reason)
            SELECT k.org_id, '{new}', k.kri_key,
                   COALESCE((SELECT max(v.version) FROM kri_threshold_version v
                             WHERE v.org_id = k.org_id AND v.framework = '{new}' AND v.kri_key = k.kri_key), 0) + 1,
                   k.amber, k.red, k.direction, NULL, '{reason}'
            FROM kri_threshold k
            WHERE k.framework = '{old}' AND k.org_id IS NOT NULL
        """)


def downgrade() -> None:
    for old, new in _MOVES:
        reason = _REASON.format(old=old)
        op.execute(f"DELETE FROM kri_threshold_version WHERE framework = '{new}' AND reason = '{reason}'")
        op.execute(f"""
            DELETE FROM kri_threshold n
            WHERE n.framework = '{new}'
              AND EXISTS (SELECT 1 FROM kri_threshold k WHERE k.framework = '{old}' AND k.kri_key = n.kri_key
                                                         AND k.org_id IS NOT DISTINCT FROM n.org_id
                                                         AND k.amber IS NOT DISTINCT FROM n.amber
                                                         AND k.red IS NOT DISTINCT FROM n.red
                                                         AND k.direction = n.direction)
        """)
