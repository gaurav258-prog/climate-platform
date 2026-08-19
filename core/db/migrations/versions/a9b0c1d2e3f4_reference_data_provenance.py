"""reference_data_provenance

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-07-11

Provenance for the reference-data layer.

The asset-management product's promise is "upload ISINs alone → a filing-ready,
AUDITABLE SFDR PAI + EU Taxonomy report". Auditable is the operative word: an
auditor signing a client's SFDR statement must be able to trace every reference
figure back to WHERE it came from and WHEN. So provenance cannot be bolted on
later -- it belongs in the reference schema itself.

The holdings foundation (f8a9b0c1d2e3) built the relational graph
(issuers/securities/facilities/emissions) but assumed rows arrive pre-populated
by hand-written seed scripts. This migration makes those tables carry their own
provenance so the resolver (services/reference/*) can populate them from OPEN
data -- GLEIF (issuer identity + ISIN→LEI), Climate TRACE / Global Energy
Monitor / OSM (facility footprints), disclosed-or-estimated emissions -- with
every record stamped by source + vintage, and every ISIN resolution logged.

Nothing here fabricates data. It records where data came from, so unmatched
ISINs and estimated figures are surfaced honestly rather than hidden.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
-- ── Issuer identity provenance ──────────────────────────────────────────
-- Where the issuer record came from and the vintage of that source, so an
-- issuer resolved from GLEIF's ISIN→LEI mapping is distinguishable from one a
-- client hand-entered or one we had to estimate.
ALTER TABLE issuers
    ADD COLUMN source        VARCHAR(20) NOT NULL DEFAULT 'manual'
        CHECK (source IN ('gleif','client','manual','estimated','vendor')),
    ADD COLUMN data_vintage  DATE,
    ADD COLUMN resolved_at   TIMESTAMPTZ;

-- ── Security (instrument→issuer) provenance ─────────────────────────────
ALTER TABLE securities
    ADD COLUMN source        VARCHAR(20) NOT NULL DEFAULT 'manual'
        CHECK (source IN ('gleif','client','manual','vendor')),
    ADD COLUMN data_vintage  DATE;

-- ── Facility footprint provenance ───────────────────────────────────────
-- A facility is only defensible if we can say which open dataset placed it and
-- how confident we are. source_ref holds the external primary key (Climate
-- TRACE asset id, GEM unit id, OSM node/way id) so it is re-checkable.
ALTER TABLE issuer_facilities
    ADD COLUMN source        VARCHAR(30) NOT NULL DEFAULT 'manual'
        CHECK (source IN ('climate_trace','gem','osm','disclosure','client','manual')),
    ADD COLUMN source_ref    VARCHAR(160),
    ADD COLUMN data_vintage  DATE,
    ADD COLUMN confidence    NUMERIC(4,3)
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));

-- ── Emissions estimation transparency ───────────────────────────────────
-- issuer_emissions.source already distinguishes disclosed/estimated/cdp/vendor.
-- When source='estimated', estimation_method states HOW (e.g.
-- 'nace_intensity_x_revenue:transition-v1'), held to the same disclosure bar as
-- the measured figures. data_vintage dates the underlying inputs.
ALTER TABLE issuer_emissions
    ADD COLUMN estimation_method VARCHAR(80),
    ADD COLUMN data_vintage      DATE;

-- ── Resolution audit log: one row per ISIN resolution attempt ───────────
-- The trail a filing cites: "these N holdings resolved against GLEIF vintage
-- YYYY-MM-DD; these M were unmatched and excluded". Append-only history, so a
-- past filing's coverage claim stays reproducible even as reference data grows.
CREATE TABLE reference_resolution_log (
    log_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    isin          VARCHAR(12) NOT NULL,
    status        VARCHAR(12) NOT NULL
                  CHECK (status IN ('resolved','cached','unmatched','error')),
    issuer_id     UUID REFERENCES issuers(issuer_id) ON DELETE SET NULL,
    security_id   UUID REFERENCES securities(security_id) ON DELETE SET NULL,
    lei           VARCHAR(20),
    source        VARCHAR(20) NOT NULL DEFAULT 'gleif',
    data_vintage  DATE,
    detail        TEXT,                                   -- error / disambiguation note, never a silent drop
    org_id        UUID REFERENCES organizations(org_id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_resolution_log_isin ON reference_resolution_log(isin);
CREATE INDEX ix_resolution_log_created ON reference_resolution_log(created_at DESC);
CREATE INDEX ix_resolution_log_org ON reference_resolution_log(org_id);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS reference_resolution_log;
ALTER TABLE issuer_emissions  DROP COLUMN IF EXISTS estimation_method, DROP COLUMN IF EXISTS data_vintage;
ALTER TABLE issuer_facilities DROP COLUMN IF EXISTS source, DROP COLUMN IF EXISTS source_ref,
                              DROP COLUMN IF EXISTS data_vintage, DROP COLUMN IF EXISTS confidence;
ALTER TABLE securities        DROP COLUMN IF EXISTS source, DROP COLUMN IF EXISTS data_vintage;
ALTER TABLE issuers           DROP COLUMN IF EXISTS source, DROP COLUMN IF EXISTS data_vintage,
                              DROP COLUMN IF EXISTS resolved_at;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
