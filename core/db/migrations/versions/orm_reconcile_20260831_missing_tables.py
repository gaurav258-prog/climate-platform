"""Reconcile the 9 tables that lived only in the ORM (create_all), never in the migration chain.

Context: the app historically provisioned schema with SQLAlchemy `create_all`, so a handful of ORM models
were added without a matching migration. A fresh `alembic upgrade head` therefore produced a schema missing
these 9 tables. This migration brings them into the chain verbatim (DDL captured from the ORM's own
create_all output) so that — once `create_all` is retired — `upgrade head` reproduces the FULL application
schema on an empty database. All 9 reference tables created earlier in the chain (organizations,
regulatory_frameworks), so the FKs resolve at this point.

Idempotent-safe additions (IF NOT EXISTS) so the same migration can also be applied to the existing live DB
(where create_all already made these tables) without erroring — the reconciliation there is "stamp, don't
rebuild", but the guards make a belt-and-braces re-run harmless.
"""
from alembic import op

revision = "orm_reconcile_20260831"
down_revision = "validation_framework_20260828"
branch_labels = None
depends_on = None


TABLES = [
    "analytics_saved_view", "commodity_price_index", "entity_source_refs", "gl_balance",
    "kri_breach_episode", "loan_arrears", "notifiable_event", "regulatory_document_snapshots",
    "source_systems",
]

CREATE_SQL = r"""
CREATE TABLE IF NOT EXISTS public.analytics_saved_view (
    view_id uuid NOT NULL,
    org_id uuid NOT NULL,
    created_by uuid NOT NULL,
    name character varying(120) NOT NULL,
    config jsonb NOT NULL,
    is_shared boolean DEFAULT false NOT NULL,
    is_pinned boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT analytics_saved_view_pkey PRIMARY KEY (view_id),
    CONSTRAINT analytics_saved_view_org_id_fkey FOREIGN KEY (org_id)
        REFERENCES public.organizations(org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_analytics_view_org ON public.analytics_saved_view USING btree (org_id);

CREATE TABLE IF NOT EXISTS public.commodity_price_index (
    price_id uuid NOT NULL,
    source character varying(60) NOT NULL,
    commodity character varying(60) NOT NULL,
    period_ym character varying(7) NOT NULL,
    index_value numeric NOT NULL,
    unit character varying(40),
    ingested_at timestamp with time zone DEFAULT now(),
    CONSTRAINT commodity_price_index_pkey PRIMARY KEY (price_id),
    CONSTRAINT uq_price_source_commodity_period UNIQUE (source, commodity, period_ym)
);
CREATE INDEX IF NOT EXISTS idx_price_commodity_period ON public.commodity_price_index USING btree (commodity, period_ym);

CREATE TABLE IF NOT EXISTS public.entity_source_refs (
    ref_id uuid NOT NULL,
    org_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    source_system_key character varying(64) NOT NULL,
    source_record_id character varying(200) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT entity_source_refs_pkey PRIMARY KEY (ref_id),
    CONSTRAINT uq_entity_source_ref UNIQUE (org_id, entity_id, source_system_key)
);

CREATE TABLE IF NOT EXISTS public.gl_balance (
    gl_id uuid NOT NULL,
    org_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    account_code character varying(60) NOT NULL,
    account_name character varying(200),
    balance_eur numeric NOT NULL,
    control_for character varying(40),
    as_of_date date,
    uploaded_by uuid,
    uploaded_at timestamp with time zone DEFAULT now(),
    CONSTRAINT gl_balance_pkey PRIMARY KEY (gl_id),
    CONSTRAINT gl_balance_org_id_fkey FOREIGN KEY (org_id)
        REFERENCES public.organizations(org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gl_balance_org_batch ON public.gl_balance USING btree (org_id, batch_id);

CREATE TABLE IF NOT EXISTS public.kri_breach_episode (
    episode_id uuid NOT NULL,
    org_id uuid NOT NULL,
    framework character varying(60) NOT NULL,
    kri_key character varying(80) NOT NULL,
    label character varying(200),
    severity character varying(10) NOT NULL,
    direction character varying(20),
    onset_value numeric,
    peak_value numeric,
    threshold numeric,
    onset_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now(),
    acknowledged_at timestamp with time zone,
    acknowledged_by uuid,
    cleared_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT kri_breach_episode_pkey PRIMARY KEY (episode_id),
    CONSTRAINT kri_breach_episode_org_id_fkey FOREIGN KEY (org_id)
        REFERENCES public.organizations(org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_kri_episode_lookup ON public.kri_breach_episode USING btree (org_id, framework, kri_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kri_episode_open ON public.kri_breach_episode USING btree (org_id, framework, kri_key) WHERE (cleared_at IS NULL);

CREATE TABLE IF NOT EXISTS public.loan_arrears (
    arrears_id uuid NOT NULL,
    org_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    loan_ref character varying(80) NOT NULL,
    borrower_name character varying(200),
    crop character varying(60),
    region character varying(120),
    exposure_eur numeric,
    days_past_due integer NOT NULL,
    as_of_date date,
    uploaded_by uuid,
    uploaded_at timestamp with time zone DEFAULT now(),
    CONSTRAINT loan_arrears_pkey PRIMARY KEY (arrears_id),
    CONSTRAINT loan_arrears_org_id_fkey FOREIGN KEY (org_id)
        REFERENCES public.organizations(org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_loan_arrears_org_batch ON public.loan_arrears USING btree (org_id, batch_id);

CREATE TABLE IF NOT EXISTS public.notifiable_event (
    event_id uuid NOT NULL,
    org_id uuid NOT NULL,
    source_type character varying(30) NOT NULL,
    source_ref character varying(160),
    title character varying(240) NOT NULL,
    category character varying(40),
    severity character varying(10),
    authority character varying(120),
    arose_at timestamp with time zone NOT NULL,
    window_hours integer NOT NULL,
    due_at timestamp with time zone NOT NULL,
    status character varying(12) DEFAULT 'open'::character varying NOT NULL,
    notified_at timestamp with time zone,
    notified_ref character varying(160),
    notified_to character varying(200),
    notified_by uuid,
    assignee_user_id uuid,
    dismiss_reason text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT notifiable_event_pkey PRIMARY KEY (event_id),
    CONSTRAINT notifiable_event_org_id_fkey FOREIGN KEY (org_id)
        REFERENCES public.organizations(org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_notifiable_org_status ON public.notifiable_event USING btree (org_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_notifiable_open_source ON public.notifiable_event USING btree (org_id, source_type, source_ref) WHERE ((status)::text = 'open'::text);

CREATE TABLE IF NOT EXISTS public.regulatory_document_snapshots (
    snapshot_id uuid NOT NULL,
    framework_id uuid NOT NULL,
    source_name character varying(60) NOT NULL,
    title character varying(500),
    url character varying(1000),
    published_date character varying(60),
    content text,
    content_hash character varying(64) NOT NULL,
    scraped_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT regulatory_document_snapshots_pkey PRIMARY KEY (snapshot_id),
    CONSTRAINT regulatory_document_snapshots_framework_id_source_name_key UNIQUE (framework_id, source_name),
    CONSTRAINT regulatory_document_snapshots_framework_id_fkey FOREIGN KEY (framework_id)
        REFERENCES public.regulatory_frameworks(framework_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.source_systems (
    source_system_id uuid NOT NULL,
    org_id uuid NOT NULL,
    key character varying(64) NOT NULL,
    name character varying(120) NOT NULL,
    kind character varying(40) NOT NULL,
    deep_link_template text NOT NULL,
    active boolean NOT NULL,
    created_by character varying(255),
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT source_systems_pkey PRIMARY KEY (source_system_id),
    CONSTRAINT uq_source_system_org_key UNIQUE (org_id, key)
);
"""


def upgrade() -> None:
    op.execute(CREATE_SQL)


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"DROP TABLE IF EXISTS public.{t} CASCADE")
