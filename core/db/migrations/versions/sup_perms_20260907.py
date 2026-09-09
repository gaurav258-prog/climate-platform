"""supervisor.* permission family — the regulator portal is gated by RBAC, not by org type alone.

Codes mirror data/reference/supervision_profiles.json (roles → permissions); a unit test keeps the two in step.

Revision ID: sup_perms_20260907
Revises: sup_settings_20260907
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_perms_20260907"
down_revision: Union[str, None] = "sup_settings_20260907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = [
    ("supervisor.population.view", "See the supervised population and its submission status"),
    ("supervisor.entity.view", "Open a supervised entity's released filings"),
    ("supervisor.entity.file", "Open the entity file (exposure, peer position, access history)"),
    ("supervisor.sites.view", "See individual sites of an entity that granted site-level access"),
    ("supervisor.benchmark.view", "See peer benchmarks across the supervised population"),
    ("supervisor.requests.manage", "Raise and track information requests to supervised entities"),
    ("supervisor.findings.manage", "Record findings and track remediation"),
    ("supervisor.intake.manage", "Work the filing intake register"),
    ("supervisor.validation.manage", "Run validation / plausibility checks on submissions"),
    ("supervisor.methodology.view", "See methodology, calibration tiers and model validation evidence"),
    ("supervisor.dashboard.view", "See the division-head dashboard"),
    ("supervisor.export", "Export population analyses"),
    ("supervisor.evidence.export", "Export an evidence pack for a case"),
    ("supervisor.assignments.manage", "Assign supervised entities to the people who work them"),
    ("supervisor.scope.manage", "Add and end the entities this authority supervises"),
    ("supervisor.mandates.manage", "Enable, adapt and acknowledge regulatory mandates for this authority"),
]


def upgrade() -> None:
    for code, desc in NEW:
        op.execute("INSERT INTO permissions (code, description) VALUES "
                   f"('{code}', '{desc.replace(chr(39), chr(39) * 2)}') ON CONFLICT (code) DO NOTHING")


def downgrade() -> None:
    for code, _ in NEW:
        op.execute("DELETE FROM role_permissions WHERE permission_id IN "
                   f"(SELECT permission_id FROM permissions WHERE code='{code}')")
        op.execute(f"DELETE FROM permissions WHERE code = '{code}'")
