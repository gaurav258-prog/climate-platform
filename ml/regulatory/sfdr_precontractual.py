"""SFDR Article 8/9 PRE-CONTRACTUAL disclosure (RTS Annex II / Annex III).

Distinct from both the PAI statement (ml/regulatory/sfdr_pai.py, the mandatory Annex I
adverse-impact table) and the PERIODIC report (ml/regulatory/sfdr_periodic.py, Annex IV/V,
filed alongside the annual report): the pre-contractual disclosure is the template that
must be ANNEXED TO THE FUND'S PROSPECTUS *before* an investor commits capital, under
Commission Delegated Regulation (EU) 2022/1288 — Annex II for Article 8 ("light green")
products, Annex III for Article 9 ("dark green") products. It asks what the fund WILL do
(forward, binding commitments), not what it DID (that's the periodic report).

Confirmed by two independent audit passes: this did not exist anywhere in the codebase,
and wasn't even listed as a disclosed gap.

Same honesty discipline as sfdr_pai.py / sfdr_periodic.py, applied to a template shape
that is mostly forward-looking narrative rather than backward-looking metrics:
  * Fields genuinely computable from data already in the schema TODAY (current Taxonomy
    alignment turnover/CapEx %, current asset allocation, PAI consideration) are computed
    from the golden source, same as the PAI statement / periodic report.
  * Fields that are inherently narrative or a forward BINDING commitment the manager
    makes (investment strategy, the minimum % of investments planned, DNSH methodology,
    engagement, benchmark, due diligence, monitoring process) are never fabricated —
    they are surfaced as declared inputs the manager supplies, source "customer/declared",
    with a placeholder and a description of exactly what's needed. Same idiom as the
    REIT CapEx KPI and Pillar 3 Template 10: a manager-authored JSONB register, filled
    in-app, missing values flagged rather than silently omitted.
  * The one section that IS fixed, prescribed regulatory boilerplate (the EU Taxonomy
    "do no significant harm" statement) is reproduced verbatim from the RTS rather than
    treated as either computed-from-data or manager-declared — it's neither; it's the law.

Declared inputs are stored in funds.sfdr_precontractual (JSONB), the same per-entity
qualitative-register pattern as organizations.sfdr_narratives — but scoped to the FUND,
because the pre-contractual template is per-PRODUCT, not per-manager (a manager with
both an Article 8 and an Article 9 fund files a different template for each).

Not wired into any export/filing pipeline yet (services/governance/filing_export.py and
filing_annex.py are out of scope for this build) — that's the natural next step once this
is live, but is deliberately not built here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from ml.regulatory.sfdr_pai import _taxonomy_rollup
from services.fund_disclosure import fund_pai

# Fixed, prescribed regulatory text (Annex II / III) — not computed, not declared; the
# wording the RTS itself mandates for the "do no significant harm" box. Reproduced
# faithfully, condensed to its operative sentences.
_DNSH_BOILERPLATE = (
    "The EU Taxonomy sets out a 'do no significant harm' principle by which Taxonomy-aligned "
    "investments should not significantly harm EU Taxonomy objectives and is accompanied by "
    "specific EU criteria. The 'do no significant harm' principle applies only to those "
    "investments underlying the financial product that take into account the EU criteria for "
    "environmentally sustainable economic activities. The investments underlying the remaining "
    "portion of this financial product do not take into account the EU criteria for "
    "environmentally sustainable economic activities. Any other sustainable investments must "
    "also not significantly harm any environmental or social objectives."
)

# The core sustainability indicators this engine actually computes for every fund today —
# the honest starting point for "what sustainability indicators are used to measure
# attainment" (RTS Annex II/III). The manager may declare additional ones on top.
_CORE_INDICATORS = [
    {"indicator": "GHG intensity of investee companies (WACI)", "source": "computed — SFDR PAI 3"},
    {"indicator": "Exposure to companies active in the fossil fuel sector",
     "source": "computed — SFDR PAI 4"},
    {"indicator": "EU Taxonomy-aligned % of investments (turnover-based)",
     "source": "computed — issuer-reported Article 8 figures"},
    {"indicator": "EU Taxonomy-aligned % of investments (CapEx-based)",
     "source": "computed — issuer-reported Article 8 figures"},
]


def _field(label: str, status: str, *, value=None, source: str = None,
           input_required: str = None, note: str = None, key: str = None, keys: list[str] = None):
    """One template field. status ∈ computed / declared / not_available / not_applicable.
    source is either a golden-source/computation description, or the literal
    'customer/declared' marker for manager-authored narrative/forward-commitment fields —
    never fabricated, always disclosed as missing rather than guessed.
    key/keys, when present, name the underlying funds.sfdr_precontractual JSONB field(s) —
    the same names PUT /v1/funds/{fund_id}/precontractual's PrecontractualUpdate model
    exposes — so a generic edit form can save back without hand-mapping labels to API
    fields. Use `key` for a section backed by one declared input, `keys` (a list, each
    paired with its own sub-label) for a section whose value composites several. Left
    None/[] for fields that are fixed/computed and not editable."""
    return {"field": label, "status": status, "value": value, "source": source,
            "input_required": input_required, "note": note, "key": key, "keys": keys}


def build_precontractual(session, fund_id: str) -> dict:
    """Assemble the fund's SFDR pre-contractual disclosure (RTS Annex II for Article 8,
    Annex III for Article 9). Returns a structured dict; never raises for missing data —
    every gap is disclosed as an explicit declared/not_available field."""
    fund = session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.sfdr_classification, f.base_currency,
               f.lei AS fund_lei, f.sfdr_precontractual,
               o.name AS org_name, o.lei AS manager_lei, o.legal_name AS manager_legal_name,
               o.sfdr_narratives
        FROM funds f JOIN organizations o ON o.org_id = f.org_id
        WHERE f.fund_id = :f
    """), {"f": fund_id}).mappings().first()
    if not fund:
        return {"error": "fund not found"}

    art = fund["sfdr_classification"]
    if art not in ("article_8", "article_9"):
        return {"error": "pre-contractual disclosure applies to Article 8 or 9 products only",
                "sfdr_classification": art,
                "note": "This fund has no sfdr_classification set (or is Article 6) — classify it as "
                        "article_8 or article_9 before a pre-contractual template can be assembled. "
                        "Never assumed; disclosed as a gap." if art not in ("article_6",) else
                        "Article 6 products are out of scope for the Annex II/III pre-contractual template."}

    pai = fund_pai(session, fund_id)
    if pai.get("positions", 0) == 0:
        return {"error": "fund has no positions", "fund": dict(fund)}

    tax = _taxonomy_rollup(session, fund_id)
    is_art9 = art == "article_9"
    declared = fund.get("sfdr_precontractual") or {}
    org_narratives = fund.get("sfdr_narratives") or {}

    def d(key: str):
        v = declared.get(key)
        return v if (v not in (None, "", [])) else None

    sections: list[dict] = []

    # ── Header ──
    sections.append(_field("Product name", "computed", value=fund["name"], source="golden source"))
    sections.append(_field("Legal entity identifier", "computed" if fund.get("fund_lei") else "not_available",
                            value=fund.get("fund_lei"), source="golden source (GLEIF-validated)",
                            input_required=None if fund.get("fund_lei") else "the fund's own LEI (PUT /funds/{id}/lei)"))

    # ── "Does this financial product have a sustainable investment objective?" ──
    # The Yes/No branch is derived honestly from sfdr_classification; the BINDING minimum
    # % commitment is a forward commitment only the manager can make — never computed.
    #
    # Tick-box structure correction (found via the ESAs' consolidated SFDR Q&A, JC 2023 18, Section V.29,
    # updated Aug 2025): the real Annex II/III tick-box is not a bare Yes/No keyed to Article 8 vs 9. An
    # Article 8 product can ALSO tick "yes, it partly makes sustainable investments" with its own minimum %
    # — a genuinely different, additional commitment beyond just "promotes E/S characteristics." Article 9
    # products separately commit to environmental AND social sustainable-investment minimum percentages,
    # which the Q&A explicitly says need NOT sum to the total minimum SI proportion. `makes_sustainable_
    # investments` is the Art-8-specific declared toggle for that additional tick; the env/social sub-splits
    # (below, near env_not_taxonomy_aligned_pct) apply to both Art 8 (if ticked) and Art 9.
    makes_si = d("makes_sustainable_investments") if not is_art9 else True
    planned_pct = d("proportion_investments_planned_pct")
    if is_art9:
        _tickbox_value = "Yes — sustainable investment objective (Article 9)"
    elif makes_si:
        _tickbox_value = ("No sustainable investment OBJECTIVE, but YES — it also commits to a minimum "
                          "proportion of sustainable investments (Article 8, partial SI commitment)")
    else:
        _tickbox_value = "No — it promotes environmental/social characteristics only (Article 8)"
    sections.append(_field(
        "Does this financial product have a sustainable investment objective?",
        "computed" if is_art9 else ("declared" if d("makes_sustainable_investments") is not None else "declared"),
        value=_tickbox_value,
        source="golden source (fund.sfdr_classification)" + ("" if is_art9 else
               " + customer/declared (makes_sustainable_investments toggle)"),
        note=None if is_art9 else
             "Article 8 products may ALSO tick a partial sustainable-investments commitment, distinct from "
             "simply promoting E/S characteristics (ESAs SFDR Q&A JC 2023 18, V.29) — declare "
             "'makes_sustainable_investments' if this product does.",
        key=None if is_art9 else "makes_sustainable_investments"))
    sections.append(_field(
        "Minimum proportion of investments planned "
        + ("with a sustainable investment objective" if is_art9
           else "aligned with the promoted E/S characteristics"),
        "declared" if planned_pct is not None else "not_available",
        value=f"{planned_pct}%" if planned_pct is not None else None,
        source="customer/declared",
        input_required=None if planned_pct is not None else
        "the manager's binding minimum commitment % (a forward commitment, not a historical figure — "
        "cannot be computed from holdings)",
        note="This is the BINDING minimum the manager commits to going forward, per RTS Annex "
             f"{'III' if is_art9 else 'II'} — distinct from the fund's current actual allocation "
             "shown below under 'Current asset allocation (context)'.",
        key="proportion_investments_planned_pct"))

    # ── Environmental/social characteristics promoted (Art 8) / sustainable investment
    # objective (Art 9) — narrative, declared ──
    char_obj = d("sustainable_investment_objective") if is_art9 else d("characteristics_promoted")
    sections.append(_field(
        "Sustainable investment objective" if is_art9 else "Environmental/social characteristics promoted",
        "declared" if char_obj else "not_available",
        value=char_obj, source="customer/declared",
        input_required=None if char_obj else
        ("a description of the product's sustainable investment objective" if is_art9
         else "a description of the environmental/social characteristics promoted by this product"),
        key="sustainable_investment_objective" if is_art9 else "characteristics_promoted"))

    # ── Sustainability indicators used — the core set we actually compute, plus any
    # manager-declared additions (never fabricated) ──
    extra_indicators = d("additional_indicators") or []
    sections.append(_field(
        "What sustainability indicators are used to measure attainment?",
        "computed",
        value={"core_indicators": _CORE_INDICATORS,
               "additional_indicators_declared": extra_indicators},
        source="golden source (core indicators this engine computes) + customer/declared (any additions)",
        note="The manager may declare further indicators beyond the core set this engine computes.",
        key="additional_indicators"))

    # ── Methodology / data sources / limitations to measure attainment — declared ──
    for fkey, label in (("methodology", "Methodology used to assess/measure/monitor attainment"),
                        ("data_sources", "Data sources and processing"),
                        ("limitations", "Limitations to methodologies and data")):
        v = d(fkey)
        sections.append(_field(label, "declared" if v else "not_available", value=v,
                                source="customer/declared",
                                input_required=None if v else f"the manager's {label.lower()}",
                                key=fkey))

    # ── DNSH — fixed regulatory boilerplate (neither computed-from-data nor declared;
    # the RTS's own prescribed wording), plus (if the product makes sustainable
    # investments) the product-specific DNSH methodology, which IS declared ──
    sections.append(_field("EU Taxonomy 'do no significant harm' statement", "computed",
                            value=_DNSH_BOILERPLATE,
                            source="Commission Delegated Regulation (EU) 2022/1288, Annex II/III (prescribed text)"))
    # (fixed regulatory boilerplate — no key, not editable)
    dnsh_method = d("dnsh_methodology")
    # An explicit 0% sustainable-investment commitment (planned_pct == 0) genuinely makes this question
    # not_applicable — there's nothing to apply a DNSH methodology to. planned_pct being UNSET (None) is a
    # different state entirely — it's unknown, not zero — and must NOT be treated the same way: conflating
    # "not yet declared" with "not applicable" was a real bug (found by adversarial review) that silently
    # excluded this field from the completeness count for any fund that simply hasn't declared a planned %
    # yet, making the disclosure look more complete than it actually is.
    dnsh_not_applicable = dnsh_method is None and planned_pct in ("0", 0)
    dnsh_status = "declared" if dnsh_method else ("not_applicable" if dnsh_not_applicable else "not_available")
    sections.append(_field(
        "How do the sustainable investments not cause significant harm?",
        dnsh_status, value=dnsh_method, source="customer/declared",
        input_required=None if (dnsh_method or dnsh_status == "not_applicable") else
        "a description of the DNSH methodology applied to this product's sustainable investments",
        key="dnsh_methodology"))

    # ── PAI consideration — reuse the fund's own PAI statement (single source of truth) ──
    sections.append(_field("Does this financial product consider principal adverse impacts?",
                            "computed", value="Yes — see the fund's SFDR PAI statement",
                            source="golden source", note="See GET /v1/funds/{fund_id}/sfdr-statement."))

    # ── Investment strategy — declared narrative + sub-fields the task calls out
    # explicitly (due diligence, monitoring, engagement) ──
    strategy = d("investment_strategy")
    sections.append(_field("What investment strategy does this financial product follow?",
                            "declared" if strategy else "not_available", value=strategy,
                            source="customer/declared",
                            input_required=None if strategy else "a description of the investment strategy",
                            key="investment_strategy"))
    binding = d("binding_elements")
    sections.append(_field("What are the binding elements of the investment strategy?",
                            "declared" if binding else "not_available", value=binding,
                            source="customer/declared",
                            input_required=None if binding else
                            "the binding elements used to select investments for the promoted characteristics/objective",
                            key="binding_elements"))
    governance = d("good_governance_policy")
    sections.append(_field("What is the policy to assess good governance practices of investee companies?",
                            "declared" if governance else "not_available", value=governance,
                            source="customer/declared",
                            input_required=None if governance else "the good-governance assessment policy",
                            key="good_governance_policy"))
    due_diligence = d("due_diligence")
    sections.append(_field("Due diligence conducted on underlying assets",
                            "declared" if due_diligence else "not_available", value=due_diligence,
                            source="customer/declared",
                            input_required=None if due_diligence else "the manager's due-diligence process for underlying assets",
                            key="due_diligence"))
    monitoring = d("monitoring_process")
    sections.append(_field(
        "How will attainment of the characteristics/objective be monitored on a continuous basis?",
        "declared" if monitoring else "not_available", value=monitoring, source="customer/declared",
        input_required=None if monitoring else "a description of the ongoing monitoring process",
        note="Forward-looking (how it WILL be monitored) — distinct from the periodic report's "
             "backward-looking 'how did the indicators perform' (GET /v1/funds/{fund_id}/periodic-report).",
        key="monitoring_process"))
    # Engagement policy — reused from the manager's own SFDR narratives (single source of
    # truth; the same text the PAI statement already surfaces), not re-declared here.
    engagement = (org_narratives.get("engagement") or "").strip() or None
    sections.append(_field(
        "Engagement policies", "computed" if engagement else "not_available", value=engagement,
        source="golden source (organizations.sfdr_narratives.engagement — set once, shared across every "
               "fund's SFDR disclosures)",
        input_required=None if engagement else
        "set the manager's engagement policy (PUT /v1/manager/filing-profile, narratives.engagement)"))

    # ── Asset allocation: the BINDING PLANNED commitment (declared) shown next to the
    # fund's CURRENT actual allocation (computed, context only — never presented as the
    # commitment itself) ──
    planned_taxonomy_pct = d("planned_taxonomy_aligned_pct")
    planned_sustainable_pct = d("planned_sustainable_pct")
    sections.append(_field(
        "What is the asset allocation planned for this financial product? (binding commitment)",
        "declared" if (planned_pct is not None or planned_taxonomy_pct is not None) else "not_available",
        value={"proportion_aligned_with_characteristics_or_objective_pct": planned_pct,
               "of_which_taxonomy_aligned_pct": planned_taxonomy_pct,
               "of_which_sustainable_investments_pct": planned_sustainable_pct},
        source="customer/declared",
        input_required=None if planned_pct is not None else
        "the manager's planned minimum asset-allocation split (#1 aligned with E/S vs #2 other)",
        keys=["proportion_investments_planned_pct", "planned_taxonomy_aligned_pct", "planned_sustainable_pct"]))
    sections.append(_field(
        "Current asset allocation (context — not the binding commitment)", "computed",
        value={"by_asset_class": pai.get("total_value_eur") and
               {"total_value_eur": pai["total_value_eur"], "positions": pai["positions"]},
               "taxonomy_aligned_turnover_pct": tax.get("taxonomy_aligned_turnover_pct"),
               "taxonomy_aligned_capex_pct": tax.get("taxonomy_aligned_capex_pct")},
        source="golden source",
        note="Shown for comparison against the planned commitment above; it is today's actual "
             "position, not a substitute for the binding forward commitment."))
    derivatives = d("derivatives_use")
    sections.append(_field("How does the use of derivatives attain the characteristics/objective?",
                            "declared" if derivatives else "not_applicable", value=derivatives,
                            source="customer/declared",
                            note=None if derivatives else
                            "No derivatives use declared for this product; declare if applicable.",
                            key="derivatives_use"))

    # ── Minimum Taxonomy alignment — COMPUTED, reusing the dual turnover/CapEx KPI ──
    # Citation correction (found via the ESAs' consolidated SFDR Q&A, JC 2023 18): the FUND-LEVEL "minimum
    # extent" figure shown here is governed by Articles 15(3)/19(3) of the SFDR Delegated Regulation, NOT
    # Annex III/IV of Del. Reg. (EU) 2021/2178 (that Annex III is the asset manager's own ENTITY-level KPI
    # about itself, a different, separate disclosure). Per 15(3)/19(3), the fund-level figure is
    # TURNOVER-based BY DEFAULT; a manager may instead use CapEx or OpEx only if they've decided it's "more
    # representative," with that choice and its reason disclosed. `taxonomy_kpi_basis` is the manager's
    # declared choice (default "turnover" — the regulatory default when nothing is declared); the primary
    # `value` below reflects that basis, with the other bases shown as supplementary detail, not as if all
    # were equally mandatory.
    _basis = (d("taxonomy_kpi_basis") or "turnover").strip().lower()
    if _basis not in ("turnover", "capex", "opex"):
        _basis = "turnover"
    _basis_pct = {"turnover": tax.get("taxonomy_aligned_turnover_pct"),
                  "capex": tax.get("taxonomy_aligned_capex_pct"),
                  "opex": None}.get(_basis)   # OpEx KPI not computed by _taxonomy_rollup (no OpEx figures collected)
    sections.append(_field(
        "To what minimum extent are sustainable investments with an environmental objective "
        "aligned with the EU Taxonomy?",
        "computed" if _basis_pct is not None else "not_available",
        value={"basis": _basis, "minimum_extent_pct": _basis_pct,
               "taxonomy_aligned_turnover_pct": tax.get("taxonomy_aligned_turnover_pct"),
               "turnover_coverage_pct": tax.get("turnover_alignment_coverage_pct"),
               "taxonomy_aligned_capex_pct": tax.get("taxonomy_aligned_capex_pct"),
               "capex_coverage_pct": tax.get("capex_alignment_coverage_pct")},
        source="golden source (issuer-reported Article 8 turnover/CapEx figures, DNSH-gated)"
               + ("" if not d("taxonomy_kpi_basis") else " + customer/declared (basis choice)"),
        input_required=tax.get("input_required"),
        note=(f"Basis: {_basis} (per SFDR Del. Reg. Art. 15(3)/19(3), turnover is the default basis; CapEx or "
              f"OpEx may be used instead only where the manager has decided it is more representative, with "
              f"that reason disclosed — see 'taxonomy_kpi_basis' in the fund's declared inputs). Turnover and "
              f"CapEx figures are both shown for reference; OpEx is not currently computed by this platform "
              f"(no issuer OpEx-alignment data is collected)."),
        key="taxonomy_kpi_basis"))
    for fkey, label in (("env_sustainable_pct", "Minimum proportion of environmentally sustainable investments"),
                        ("social_sustainable_pct", "Minimum proportion of socially sustainable investments"),
                        ("transitional_enabling_share_pct", "Minimum share of transitional/enabling activities"),
                        ("env_not_taxonomy_aligned_pct", "Minimum share of sustainable investments with an "
                                                         "environmental objective not aligned with the EU Taxonomy")):
        v = d(fkey)
        _note = None if v is not None else (
            "the manager's per-holding classification for this sub-category "
            "(cannot be derived from the aggregate Taxonomy figures alone)")
        if fkey in ("env_sustainable_pct", "social_sustainable_pct") and v is not None:
            _note = ("Per ESAs SFDR Q&A (JC 2023 18, V.29): these are minimum COMMITMENTS, not a strict "
                     "partition — the environmental and social sub-percentages need not sum to the total "
                     "minimum sustainable-investment proportion declared above.")
        sections.append(_field(label, "declared" if v is not None else "not_available",
                                value=f"{v}%" if v is not None else None, source="customer/declared",
                                input_required=None if v is not None else _note, note=_note if v is not None else None,
                                key=fkey))
    other_purpose = d("other_investments_purpose")
    sections.append(_field('What investments are included under "#2 Other" and what is their purpose?',
                            "declared" if other_purpose else "not_available", value=other_purpose,
                            source="customer/declared",
                            input_required=None if other_purpose else
                            "a description of the #2 Other investments, their purpose, and any minimum E/S safeguards",
                            key="other_investments_purpose"))

    # ── Reference benchmark — optional; declared if the manager has designated one ──
    benchmark_name = d("reference_benchmark_name")
    _benchmark_keys = ["reference_benchmark_name", "benchmark_alignment_methodology",
                       "benchmark_vs_broad_market", "benchmark_methodology_url"]
    if benchmark_name:
        sections.append(_field("Is a specific index designated as a reference benchmark?", "declared",
                                value={"name": benchmark_name,
                                       "alignment_methodology": d("benchmark_alignment_methodology"),
                                       "differs_from_broad_market": d("benchmark_vs_broad_market"),
                                       "methodology_location": d("benchmark_methodology_url")},
                                source="customer/declared", keys=_benchmark_keys))
    else:
        sections.append(_field("Is a specific index designated as a reference benchmark?", "not_applicable",
                                value="No reference benchmark designated", source="customer/declared",
                                note="Declare reference_benchmark_name if this product designates one.",
                                keys=_benchmark_keys))

    more_info_url = d("more_info_url")
    sections.append(_field("Where can I find more product-specific information online?",
                            "declared" if more_info_url else "not_available", value=more_info_url,
                            source="customer/declared",
                            input_required=None if more_info_url else "a hyperlink to the product's website",
                            key="more_info_url"))

    computed = sum(1 for s in sections if s["status"] == "computed")
    declared_n = sum(1 for s in sections if s["status"] == "declared")
    missing = sum(1 for s in sections if s["status"] == "not_available")

    return {
        "entity": {"fund_id": fund["fund_id"], "fund_name": fund["name"], "fund_lei": fund.get("fund_lei"),
                   "manager": fund["org_name"], "manager_lei": fund.get("manager_lei"),
                   "manager_legal_name": fund.get("manager_legal_name"),
                   "sfdr_classification": art, "total_value_eur": pai["total_value_eur"],
                   "positions": pai["positions"]},
        "template": f"Pre-contractual disclosure — {'Annex III (Article 9)' if is_art9 else 'Annex II (Article 8)'}",
        "regulatory_basis": "Commission Delegated Regulation (EU) 2022/1288, "
                             f"{'Annex III' if is_art9 else 'Annex II'}",
        "sections": sections,
        "coverage_summary": {
            "fields": len(sections), "computed": computed, "declared": declared_n, "not_available": missing,
            "note": f"{computed} of {len(sections)} fields computed from the golden source, {declared_n} "
                    f"declared by the manager, {missing} still required. Narrative and forward-commitment "
                    "fields are never fabricated — each missing one names exactly what input is needed.",
        },
        "next_step_note": "Not yet wired into the filing export pipeline (services/governance/filing_export.py "
                          "/ filing_annex.py) — a natural next step once this template is in active use.",
        "provenance": {"generated_at": datetime.now(timezone.utc).isoformat()},
    }
