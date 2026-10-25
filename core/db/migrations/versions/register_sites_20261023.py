"""Issuers' real sites from public registers of facilities (the product owner's decisions of 2026-10-23).

501 of 505 fund issuers were located only by their head office. Registers of facilities name each site's owner: Climate
TRACE's ownership files state the owner's LEI (matched to an issuer by that LEI); the EEA's industrial register names
the parent company only (a name, matched to an issuer only after a person confirms it). A register states no site's
share of the company's value, so such a site's weight is 'not stated' — a named gap, never assumed.

  issuer_facilities       weight_basis + 'not_stated' (weight 0); source + 'eea_ied'
                          + match_basis   how the site was tied to the issuer: 'register_lei' (the register states the
                                          issuer's LEI as the site's owner) or 'reviewed_name' (a person confirmed the
                                          register's owner name); NULL for a site provided or geocoded as before
                          + owner_share   the issuer's share of the site as the register states it (0..1)
                          + site_facts    what the register states of the site (its own id, activity, capacity with its
                                          unit, emissions, year, ownership path) — facts, never a weight
                          one register site per issuer, source and register id
  issuer_site_candidates  a register site whose owner's name equals the GLEIF name of the issuer or of an entity GLEIF
                          records the issuer consolidates — waiting for a person's decision (pending → confirmed, with
                          the facility it became, or rejected); who decided and when

Downgrade refuses while a register site or a candidate is recorded.

Revision ID: register_sites_20261023
Revises: regional_crops_20261023
"""
from typing import Sequence, Union

from alembic import op

revision: str = "register_sites_20261023"
down_revision: Union[str, None] = "regional_crops_20261023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ISSUER = "0bbe0bbe-0000-4000-8000-000000323a01"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO issuers (issuer_id, name) VALUES ('{ISSUER}', 'refusal probe');
                INSERT INTO issuer_facilities (issuer_id, name, materiality_weight, weight_basis, source, source_ref,
                                               match_basis, site_facts)
                VALUES ('{ISSUER}', 'probe site', 0, 'not_stated', 'climate_trace', 'probe', 'register_lei', '{{}}');""",
    "cleanup": f"DELETE FROM issuers WHERE issuer_id = '{ISSUER}';",
}

_BASES = "'revenue', 'assets', 'production_capacity', 'headcount', 'equal'"
_SOURCES = "'climate_trace', 'gem', 'osm', 'disclosure', 'client', 'manual'"


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE issuer_facilities
            DROP CONSTRAINT issuer_facilities_weight_basis_check,
            ADD CONSTRAINT issuer_facilities_weight_basis_check CHECK (weight_basis IN ({_BASES}, 'not_stated')),
            DROP CONSTRAINT issuer_facilities_source_check,
            ADD CONSTRAINT issuer_facilities_source_check CHECK (source IN ({_SOURCES}, 'eea_ied')),
            ADD COLUMN match_basis varchar(20) CHECK (match_basis IN ('register_lei', 'reviewed_name')),
            ADD COLUMN owner_share numeric(9,6) CHECK (owner_share > 0 AND owner_share <= 1),
            ADD COLUMN site_facts  jsonb,
            -- a register site states no share of the company: its weight is not stated, never a number
            ADD CONSTRAINT issuer_facilities_register_weight CHECK (match_basis IS NULL
                OR (weight_basis = 'not_stated' AND materiality_weight = 0 AND source_ref IS NOT NULL
                    AND site_facts IS NOT NULL)),
            ADD CONSTRAINT issuer_facilities_not_stated_zero CHECK (weight_basis <> 'not_stated' OR materiality_weight = 0);
        CREATE UNIQUE INDEX ux_facilities_register_site ON issuer_facilities (issuer_id, source, source_ref)
            WHERE match_basis IS NOT NULL;

        CREATE TABLE issuer_site_candidates (
            candidate_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            issuer_id        uuid NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
            register         varchar(20) NOT NULL CHECK (register IN ('eea_ied')),
            register_ref     varchar(160) NOT NULL,
            register_vintage varchar(80) NOT NULL,
            name             varchar(300),
            latitude         double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
            longitude        double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
            country          varchar(2),
            site_facts       jsonb NOT NULL,
            owner_named      varchar(300) NOT NULL,
            matched_lei      varchar(20) NOT NULL,
            matched_name     varchar(300) NOT NULL,
            relation         varchar(30) NOT NULL CHECK (relation IN ('issuer', 'consolidated_entity')),
            rule             varchar(200) NOT NULL,
            status           varchar(12) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'rejected')),
            decided_by       uuid REFERENCES users(user_id),
            decided_at       timestamptz,
            note             text,
            facility_id      uuid REFERENCES issuer_facilities(facility_id),
            created_at       timestamptz NOT NULL DEFAULT now(),
            UNIQUE (issuer_id, register, register_ref),
            CHECK ((status = 'pending') = (decided_by IS NULL AND decided_at IS NULL)),
            CHECK ((status = 'confirmed') = (facility_id IS NOT NULL))
        );
        CREATE INDEX ix_site_candidates_status ON issuer_site_candidates (status, issuer_id);
    """)


def downgrade() -> None:
    op.execute(f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM issuer_facilities WHERE match_basis IS NOT NULL OR weight_basis = 'not_stated'
                       OR source = 'eea_ied')
               OR EXISTS (SELECT 1 FROM issuer_site_candidates) THEN
                RAISE EXCEPTION 'register sites or site candidates are recorded — they cannot be removed';
            END IF;
        END $$;
        DROP TABLE issuer_site_candidates;
        DROP INDEX ux_facilities_register_site;
        ALTER TABLE issuer_facilities
            DROP CONSTRAINT issuer_facilities_not_stated_zero,
            DROP CONSTRAINT issuer_facilities_register_weight,
            DROP COLUMN site_facts, DROP COLUMN owner_share, DROP COLUMN match_basis,
            DROP CONSTRAINT issuer_facilities_source_check,
            ADD CONSTRAINT issuer_facilities_source_check CHECK (source IN ({_SOURCES})),
            DROP CONSTRAINT issuer_facilities_weight_basis_check,
            ADD CONSTRAINT issuer_facilities_weight_basis_check CHECK (weight_basis IN ({_BASES}));
    """)
