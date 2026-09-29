"""SFDR product disclosures (RTS 2022/1288 Annexes II–V) on the governed filing route, and one store per fact.

  * a filing (and an obligation) may have a financial product as its subject: regulatory_filing.fund_id and
    regulatory_obligation.fund_id. The pre-contractual and periodic templates are per product, not per legal entity
  * fund_sfdr_answers — the manager's answers to the template items the platform cannot know (commitments, narratives,
    choices), keyed by the spec's item id: one row per fund, document (precontractual / periodic), reference period
    (periodic only) and item. It replaces funds.sfdr_precontractual (moved here, then dropped)
  * issuer_taxonomy_kpi is the one store of an investee's own Taxonomy KPIs, for banks and funds alike: objective 'all'
    holds a total whose split by objective is not stated; the fossil gas and nuclear parts of the aligned share
    (Annex XII of Delegated Regulation 2021/2178) are added; org_id NULL is a shared vendor figure. The duplicate
    columns in issuer_esg_metrics (taxonomy_eligible_pct, taxonomy_aligned_pct, taxonomy_aligned_capex_pct) are moved
    here and dropped

Revision ID: sfdr_product_20260929
Revises: reit_7_7_facts_20260929
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sfdr_product_20260929"
down_revision: Union[str, None] = "reit_7_7_facts_20260929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SIX = ("ccm", "cca", "wtr", "ce", "ppc", "bio")      # Regulation (EU) 2020/852 Art. 9 (a)-(f), frozen here
# funds.sfdr_precontractual key -> (item id in Annex II (Art. 8), item id in Annex III (Art. 9), answer shape) — frozen here
# from the item ids of the sfdr_product specs. None: the annex has no such item (the value is kept, see _unmapped).
_ITEM = {
    "characteristics_promoted": ("q_es_chars", None, "text"),
    "sustainable_investment_objective": (None, "q_objective", "text"),
    "additional_indicators": ("q_es_chars.indicators", "q_objective.indicators", "text"),
    "dnsh_methodology": ("q_es_chars.dnsh", "q_objective.dnsh", "text"),
    "oecd_un_alignment": ("q_es_chars.dnsh.oecd", "q_objective.dnsh.oecd", "text"),
    "investment_strategy": ("q_strategy", "q_strategy", "text"),
    "binding_elements": ("q_strategy.binding", "q_strategy.binding", "text"),
    "investment_scope_reduction_min_pct": ("q_strategy.min_rate", None, "percent"),
    "good_governance_policy": ("q_strategy.governance", "q_strategy.governance", "text"),
    "derivatives_use": ("q_asset_alloc.derivatives", "q_asset_alloc.derivatives", "text"),
    "other_investments_purpose": ("q_other", "q_not_sustainable", "text"),
    "reference_benchmark_name": ("q_benchmark", "q_benchmark", "text"),
    "benchmark_alignment_methodology": ("q_benchmark.alignment", "q_benchmark.alignment", "text"),
    "benchmark_vs_broad_market": ("q_benchmark.differ", "q_benchmark.differ", "text"),
    "benchmark_methodology_url": ("q_benchmark.methodology", "q_benchmark.methodology", "text"),
    "more_info_url": ("q_online", "q_online", "text"),
    "planned_taxonomy_aligned_pct": ("q_taxonomy", "q_taxonomy", "percent"),
    "transitional_enabling_share_pct": ("q_taxonomy.transitional", "q_taxonomy.transitional", "percent"),
    "env_not_taxonomy_aligned_pct": ("q_env_non_taxonomy", "q_env_non_taxonomy", "percent"),
    "social_sustainable_pct": ("q_social", "q_social", "percent"),
}
# the Art. 10 SFDR website disclosures are not template items: kept per fund under 'website.<key>'
_WEBSITE = ("methodology", "data_sources", "limitations", "due_diligence", "monitoring_process")


def _answers(doc: dict, article: str) -> list[tuple[str, dict]]:
    """The item answers one fund's legacy register becomes."""
    out, col = [], 0 if article == "article_8" else 1
    for k, v in doc.items():
        if k in _ITEM and _ITEM[k][col]:
            shape = _ITEM[k][2]
            text = "\n".join(v) if isinstance(v, list) else v
            out.append((_ITEM[k][col], {"percent": float(v)} if shape == "percent" else {"text": str(text)}))
        elif k in _WEBSITE:
            out.append((f"website.{k}", {"text": str(v)}))
        else:
            out.append((f"legacy.{k}", {"value": v}))
    if article == "article_8" and doc.get("makes_sustainable_investments") is not None:
        out.append(("q_sust_obj.no.es_with_si", {"ticked": bool(doc["makes_sustainable_investments"]),
                                                 **({"percent": float(doc["planned_sustainable_pct"])}
                                                    if doc.get("planned_sustainable_pct") is not None else {})}))
        out.append(("q_sust_obj.no.es_no_si", {"ticked": not doc["makes_sustainable_investments"]}))
    if doc.get("proportion_investments_planned_pct") is not None:
        out.append(("chart_asset_alloc", {"values": {("chart_asset_alloc.aligned_es" if article == "article_8"
                                                       else "chart_asset_alloc.sustainable"):
                                                      float(doc["proportion_investments_planned_pct"])}}))
    return out

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee1', 'refusal probe', 'asset_manager', 'DE');
                INSERT INTO issuers (issuer_id, name) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee4', 'refusal probe');
                INSERT INTO issuer_taxonomy_kpi (issuer_id, org_id, reporting_year, basis, objective, aligned_pct)
                VALUES ('0bbe0bbe-0000-4000-8000-00000000fee4', '0bbe0bbe-0000-4000-8000-00000000fee1', 2025, 'opex', 'all', 5);""",
    "cleanup": """DELETE FROM issuer_taxonomy_kpi WHERE issuer_id = '0bbe0bbe-0000-4000-8000-00000000fee4';
                  DELETE FROM issuers WHERE issuer_id = '0bbe0bbe-0000-4000-8000-00000000fee4';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee1';""",
}


def upgrade() -> None:
    # a filing's subject may be a financial product (its role 'product'; never alongside an entity)
    for t, ck in (("regulatory_filing", "ck_reg_filing_role"), ("regulatory_obligation", "ck_reg_obligation_role")):
        op.execute(f"ALTER TABLE {t} ADD COLUMN fund_id UUID REFERENCES funds(fund_id) ON DELETE RESTRICT")
        op.execute(f"CREATE INDEX ix_{t}_fund ON {t} (fund_id) WHERE fund_id IS NOT NULL")
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT {ck}")
        op.execute(f"""ALTER TABLE {t} ADD CONSTRAINT {ck} CHECK (filing_role IS NULL OR
                       filing_role IN ('solo', 'consolidated', 'whole_org', 'product'))""")
        op.execute(f"""ALTER TABLE {t} ADD CONSTRAINT ck_{t}_product_subject CHECK (
                       (fund_id IS NULL) OR (entity_id IS NULL AND filing_role = 'product'))""")

    # the manager's answers, per template item
    op.execute("""
        CREATE TABLE fund_sfdr_answers (
            answer_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fund_id      UUID NOT NULL REFERENCES funds(fund_id) ON DELETE CASCADE,
            document     TEXT NOT NULL CHECK (document IN ('precontractual', 'periodic')),
            period_end   DATE,
            item_id      TEXT NOT NULL CHECK (item_id ~ '^[a-z0-9_.]+$'),
            value        JSONB NOT NULL,
            updated_by   UUID REFERENCES users(user_id),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_fund_sfdr_answers_period CHECK ((document = 'periodic') = (period_end IS NOT NULL)),
            CONSTRAINT ux_fund_sfdr_answers UNIQUE NULLS NOT DISTINCT (fund_id, document, period_end, item_id)
        )""")
    import json

    import sqlalchemy as sa
    conn = op.get_bind()
    for fid, doc, art in conn.execute(sa.text(
            "SELECT fund_id, sfdr_precontractual, sfdr_classification FROM funds WHERE sfdr_precontractual IS NOT NULL")):
        for item, value in _answers(doc or {}, art or "article_8"):
            conn.execute(sa.text("""INSERT INTO fund_sfdr_answers (fund_id, document, item_id, value)
                                    VALUES (:f, 'precontractual', :i, CAST(:v AS jsonb))"""),
                         {"f": fid, "i": item, "v": json.dumps(value)})
    # the keys the legacy register carried alongside its items, kept (their items are derived, not re-typed)
    for fid, doc in conn.execute(sa.text("SELECT fund_id, sfdr_precontractual FROM funds WHERE sfdr_precontractual IS NOT NULL")):
        for k in ("makes_sustainable_investments", "planned_sustainable_pct", "proportion_investments_planned_pct"):
            if k in (doc or {}):
                conn.execute(sa.text("""INSERT INTO fund_sfdr_answers (fund_id, document, item_id, value)
                                        VALUES (:f, 'precontractual', :i, CAST(:v AS jsonb)) ON CONFLICT DO NOTHING"""),
                             {"f": fid, "i": f"legacy.{k}", "v": json.dumps({"value": doc[k]})})
    op.execute("ALTER TABLE funds DROP COLUMN sfdr_precontractual")

    # one store of an investee's Taxonomy KPIs
    op.execute("ALTER TABLE issuer_taxonomy_kpi DROP CONSTRAINT issuer_taxonomy_kpi_objective_check")
    op.execute(f"""ALTER TABLE issuer_taxonomy_kpi ADD CONSTRAINT issuer_taxonomy_kpi_objective_check
                   CHECK (objective IN ({', '.join(repr(v) for v in _SIX)}, 'all'))""")
    op.execute("ALTER TABLE issuer_taxonomy_kpi ALTER COLUMN org_id DROP NOT NULL")
    op.execute("ALTER TABLE issuer_taxonomy_kpi DROP CONSTRAINT ux_issuer_taxonomy_kpi")
    op.execute("""ALTER TABLE issuer_taxonomy_kpi ADD CONSTRAINT ux_issuer_taxonomy_kpi
                   UNIQUE NULLS NOT DISTINCT (issuer_id, org_id, reporting_year, basis, objective)""")
    op.execute("""ALTER TABLE issuer_taxonomy_kpi
                   ADD COLUMN fossil_gas_aligned_pct NUMERIC(7,4) CHECK (fossil_gas_aligned_pct BETWEEN 0 AND 100),
                   ADD COLUMN nuclear_aligned_pct NUMERIC(7,4) CHECK (nuclear_aligned_pct BETWEEN 0 AND 100),
                   ADD CONSTRAINT ck_issuer_taxonomy_kpi_gas_nuclear CHECK (aligned_pct IS NULL OR
                       COALESCE(fossil_gas_aligned_pct, 0) + COALESCE(nuclear_aligned_pct, 0) <= aligned_pct)""")
    op.execute("""
        INSERT INTO issuer_taxonomy_kpi (issuer_id, org_id, reporting_year, basis, objective, eligible_pct, aligned_pct, source, data_vintage)
        SELECT issuer_id, org_id, reporting_year, 'turnover', 'all', taxonomy_eligible_pct, taxonomy_aligned_pct, source,
               COALESCE(data_vintage::timestamptz, created_at)
        FROM issuer_esg_metrics WHERE taxonomy_eligible_pct IS NOT NULL OR taxonomy_aligned_pct IS NOT NULL
        ON CONFLICT DO NOTHING""")
    op.execute("""
        INSERT INTO issuer_taxonomy_kpi (issuer_id, org_id, reporting_year, basis, objective, aligned_pct, source, data_vintage)
        SELECT issuer_id, org_id, reporting_year, 'capex', 'all', taxonomy_aligned_capex_pct, source,
               COALESCE(data_vintage::timestamptz, created_at)
        FROM issuer_esg_metrics WHERE taxonomy_aligned_capex_pct IS NOT NULL
        ON CONFLICT DO NOTHING""")
    op.execute("""ALTER TABLE issuer_esg_metrics DROP COLUMN taxonomy_eligible_pct, DROP COLUMN taxonomy_aligned_pct,
                   DROP COLUMN taxonomy_aligned_capex_pct""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_filing WHERE fund_id IS NOT NULL)
               OR EXISTS (SELECT 1 FROM regulatory_obligation WHERE fund_id IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade sfdr_product_20260929: filings or obligations have a financial product '
                                'as their subject, which the prior shape cannot hold';
            END IF;
            IF EXISTS (SELECT 1 FROM fund_sfdr_answers WHERE document = 'periodic' OR updated_by IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade sfdr_product_20260929: answers to template items exist that '
                                'funds.sfdr_precontractual cannot hold';
            END IF;
            IF EXISTS (SELECT 1 FROM issuer_taxonomy_kpi WHERE org_id IS NULL
                           OR fossil_gas_aligned_pct IS NOT NULL OR nuclear_aligned_pct IS NOT NULL
                           OR (objective = 'all' AND (basis = 'opex' OR transitional_pct IS NOT NULL
                               OR enabling_pct IS NOT NULL OR (basis = 'capex' AND eligible_pct IS NOT NULL)))) THEN
                RAISE EXCEPTION 'cannot downgrade sfdr_product_20260929: issuer Taxonomy KPIs exist that the prior '
                                'shape cannot hold (shared vendor figures, gas / nuclear parts, or totals beyond '
                                'turnover eligible / aligned and CapEx aligned)';
            END IF;
        END $$;
    """)
    op.execute("""ALTER TABLE issuer_esg_metrics ADD COLUMN taxonomy_eligible_pct NUMERIC(6,3),
                   ADD COLUMN taxonomy_aligned_pct NUMERIC(6,3), ADD COLUMN taxonomy_aligned_capex_pct NUMERIC(6,3)""")
    op.execute("""
        UPDATE issuer_esg_metrics m SET taxonomy_eligible_pct = k.eligible_pct, taxonomy_aligned_pct = k.aligned_pct
        FROM issuer_taxonomy_kpi k
        WHERE k.objective = 'all' AND k.basis = 'turnover' AND k.issuer_id = m.issuer_id
          AND k.org_id IS NOT DISTINCT FROM m.org_id AND k.reporting_year = m.reporting_year""")
    op.execute("""
        UPDATE issuer_esg_metrics m SET taxonomy_aligned_capex_pct = k.aligned_pct
        FROM issuer_taxonomy_kpi k
        WHERE k.objective = 'all' AND k.basis = 'capex' AND k.issuer_id = m.issuer_id
          AND k.org_id IS NOT DISTINCT FROM m.org_id AND k.reporting_year = m.reporting_year""")
    op.execute("DELETE FROM issuer_taxonomy_kpi WHERE objective = 'all'")
    op.execute("""ALTER TABLE issuer_taxonomy_kpi DROP CONSTRAINT ck_issuer_taxonomy_kpi_gas_nuclear,
                   DROP COLUMN fossil_gas_aligned_pct, DROP COLUMN nuclear_aligned_pct""")
    op.execute("ALTER TABLE issuer_taxonomy_kpi DROP CONSTRAINT ux_issuer_taxonomy_kpi")
    op.execute("""ALTER TABLE issuer_taxonomy_kpi ADD CONSTRAINT ux_issuer_taxonomy_kpi
                   UNIQUE (issuer_id, org_id, reporting_year, basis, objective)""")
    op.execute("ALTER TABLE issuer_taxonomy_kpi ALTER COLUMN org_id SET NOT NULL")
    op.execute("ALTER TABLE issuer_taxonomy_kpi DROP CONSTRAINT issuer_taxonomy_kpi_objective_check")
    op.execute(f"""ALTER TABLE issuer_taxonomy_kpi ADD CONSTRAINT issuer_taxonomy_kpi_objective_check
                   CHECK (objective IN ({', '.join(repr(v) for v in _SIX)}))""")

    op.execute("ALTER TABLE funds ADD COLUMN sfdr_precontractual JSONB")
    # only migrated answers remain (no one has answered since — checked above): rebuild the register from them
    import json

    import sqlalchemy as sa
    conn = op.get_bind()
    back = {}
    for k, (a8, a9, shape) in _ITEM.items():
        for item in {a8, a9} - {None}:
            back.setdefault(item, []).append((k, shape))
    docs: dict = {}
    for fid, item, value, art in conn.execute(sa.text("""
            SELECT a.fund_id, a.item_id, a.value, f.sfdr_classification FROM fund_sfdr_answers a
            JOIN funds f USING (fund_id) WHERE a.document = 'precontractual'""")):
        d = docs.setdefault(fid, {})
        if item.startswith(("legacy.", "website.")):
            d[item.split(".", 1)[1]] = value.get("value", value.get("text"))
            continue
        col = 0 if (art or "article_8") == "article_8" else 1
        for k, shape in back.get(item, []):
            if _ITEM[k][col] == item:
                d[k] = value.get("percent") if shape == "percent" else value.get("text")
                if k == "additional_indicators":
                    d[k] = (value.get("text") or "").split("\n")
    for fid, d in docs.items():
        conn.execute(sa.text("UPDATE funds SET sfdr_precontractual = CAST(:d AS jsonb) WHERE fund_id = :f"),
                     {"d": json.dumps(d), "f": fid})
    op.execute("DROP TABLE fund_sfdr_answers")
    for t, ck in (("regulatory_filing", "ck_reg_filing_role"), ("regulatory_obligation", "ck_reg_obligation_role")):
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT ck_{t}_product_subject")
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT {ck}")
        op.execute(f"""ALTER TABLE {t} ADD CONSTRAINT {ck} CHECK (filing_role IS NULL OR
                       filing_role IN ('solo', 'consolidated', 'whole_org'))""")
        op.execute(f"DROP INDEX IF EXISTS ix_{t}_fund")
        op.execute(f"ALTER TABLE {t} DROP COLUMN fund_id")
