"""EBA Pillar 3 ESG — the QUALITATIVE disclosure tables (Tables 1, 2, 3 of Annex XXXIX, ITS (EU) 2022/2453),
transcribed VERBATIM from the adopted regulation (OJ L 324, 19.12.2022). These are free-format narrative the
institution AUTHORS — there is nothing to compute — so this module holds the exact row structure (row id +
group + the prompt text) and the app renders them as editable text the user fills in-app, versioned + attested
with the rest of the filing. Stored org-level (institution-level qualitative disclosure), same as SFDR narratives.
"""
from __future__ import annotations

# Each table: (row_id, group, prompt). row_id keys the stored value; group is the Annex's own sub-heading.
TABLE1_ENVIRONMENTAL = [
    ("a", "Business strategy and processes", "Institution's business strategy to integrate environmental factors and risks, taking into account the impact of environmental factors and risks on institution's business environment, business model, strategy and financial planning"),
    ("b", "Business strategy and processes", "Objectives, targets and limits to assess and address environmental risk in short-, medium-, and long-term, and performance assessment against these objectives, targets and limits, including forward-looking information in the design of business strategy and processes"),
    ("c", "Business strategy and processes", "Current investment activities and (future) investment targets towards environmental objectives and EU Taxonomy-aligned activities"),
    ("d", "Business strategy and processes", "Policies and procedures relating to direct and indirect engagement with new or existing counterparties on their strategies to mitigate and reduce environmental risks"),
    ("e", "Governance", "Responsibilities of the management body for setting the risk framework, supervising and managing the implementation of the objectives, strategy and policies in the context of environmental risk management covering relevant transmission channels"),
    ("f", "Governance", "Management body's integration of short-, medium- and long-term effects of environmental factors and risks, organisational structure both within business lines and internal control functions"),
    ("g", "Governance", "Integration of measures to manage environmental factors and risks in internal governance arrangements, including the role of committees, the allocation of tasks and responsibilities, and the feedback loop from risk management to the management body covering relevant transmission channels"),
    ("h", "Governance", "Lines of reporting and frequency of reporting relating to environmental risk"),
    ("i", "Governance", "Alignment of the remuneration policy with institution's environmental risk-related objectives"),
    ("j", "Risk management", "Integration of short-, medium- and long-term effects of environmental factors and risks in the risk framework"),
    ("k", "Risk management", "Definitions, methodologies and international standards on which the environmental risk management framework is based"),
    ("l", "Risk management", "Processes to identify, measure and monitor activities and exposures (and collateral where applicable) sensitive to environmental risks, covering relevant transmission channels"),
    ("m", "Risk management", "Activities, commitments and exposures contributing to mitigate environmental risks"),
    ("n", "Risk management", "Implementation of tools for identification, measurement and management of environmental risks"),
    ("o", "Risk management", "Results and outcome of the risk tools implemented and the estimated impact of environmental risk on capital and liquidity risk profile"),
    ("p", "Risk management", "Data availability, quality and accuracy, and efforts to improve these aspects"),
    ("q", "Risk management", "Description of limits to environmental risks (as drivers of prudential risks) that are set, and triggering escalation and exclusion in the case of breaching these limits"),
    ("r", "Risk management", "Description of the link (transmission channels) between environmental risks with credit risk, liquidity and funding risk, market risk, operational risk and reputational risk in the risk management framework"),
]

TABLE2_SOCIAL = [
    ("a", "Business strategy and processes", "Adjustment of the institution's business strategy to integrate social factors and risks taking into account the impact of social risk on the institution's business environment, business model, strategy and financial planning"),
    ("b", "Business strategy and processes", "Objectives, targets and limits to assess and address social risk in short-term, medium-term and long-term, and performance assessment against these objectives, targets and limits, including forward-looking information in the design of business strategy and processes"),
    ("c", "Business strategy and processes", "Policies and procedures relating to direct and indirect engagement with new or existing counterparties on their strategies to mitigate and reduce socially harmful activities"),
    ("d", "Governance", "Responsibilities of the management body for setting the risk framework, supervising and managing the implementation of the objectives, strategy and policies in the context of social risk management covering counterparties' approaches to: (i) activities towards the community and society; (ii) employee relationships and labour standards; (iii) customer protection and product responsibility; (iv) human rights"),
    ("e", "Governance", "Integration of measures to manage social factors and risks in internal governance arrangements, including the role of committees, the allocation of tasks and responsibilities, and the feedback loop from risk management to the management body"),
    ("f", "Governance", "Lines of reporting and frequency of reporting relating to social risk"),
    ("g", "Governance", "Alignment of the remuneration policy in line with institution's social risk-related objectives"),
    ("h", "Risk management", "Definitions, methodologies and international standards on which the social risk management framework is based"),
    ("i", "Risk management", "Processes to identify, measure and monitor activities and exposures (and collateral where applicable) sensitive to social risk, covering relevant transmission channels"),
    ("j", "Risk management", "Activities, commitments and assets contributing to mitigate social risk"),
    ("k", "Risk management", "Implementation of tools for identification and management of social risk"),
    ("l", "Risk management", "Description of setting limits to social risk and cases to trigger escalation and exclusion in the case of breaching these limits"),
    ("m", "Risk management", "Description of the link (transmission channels) between social risks with credit risk, liquidity and funding risk, market risk, operational risk and reputational risk in the risk management framework"),
]

TABLE3_GOVERNANCE = [
    ("a", "Governance", "Institution's integration in their governance arrangements of the governance performance of the counterparty, including committees of the highest governance body, committees responsible for decision-making on economic, environmental, and social topics"),
    ("b", "Governance", "Institution's accounting of the counterparty's highest governance body's role in non-financial reporting"),
    ("c", "Governance", "Institution's integration in governance arrangements of the governance performance of their counterparties including: (i) ethical considerations; (ii) strategy and risk management; (iii) inclusiveness; (iv) transparency; (v) management of conflict of interest; (vi) internal communication on critical concerns"),
    ("d", "Risk management", "Institution's integration in risk management arrangements the governance performance of their counterparties considering: (i) ethical considerations; (ii) strategy and risk management; (iii) inclusiveness; (iv) transparency; (v) management of conflict of interest; (vi) internal communication on critical concerns"),
]

TABLES = {
    "table1": {"title": "Table 1 — Qualitative information on Environmental risk", "rows": TABLE1_ENVIRONMENTAL},
    "table2": {"title": "Table 2 — Qualitative information on Social risk", "rows": TABLE2_SOCIAL},
    "table3": {"title": "Table 3 — Qualitative information on Governance risk", "rows": TABLE3_GOVERNANCE},
}


# Template 10 — other climate-change-mitigating actions NOT covered by the EU Taxonomy. A flexible register the
# preparer authors (green / sustainability bonds + specialised green lending); instrument type is not on the
# golden-source book, so every field is manual. Fixed columns per ITS 2022/2453, Annex XXXIX Template 10.
TEMPLATE10_FIELDS = [
    ("kind", "Instrument group", ["Bond", "Loan"]),
    ("instrument", "Type of financial instrument", None),
    ("counterparty", "Type of counterparty", None),
    ("gross_eur", "Gross carrying amount (€)", None),
    ("risk", "Type of risk mitigated", None),
    ("qualitative", "Qualitative information on the mitigating action", None),
]


def template10_structure(saved: dict | None) -> dict:
    """The Template 10 register (rows the preparer authors) + the fixed field schema. `saved` is the org-level
    JSONB; rows live under key 'template10' as a list of {field_key: value}."""
    rows = (saved or {}).get("template10") or []
    return {"fields": [{"key": k, "label": lbl, "options": opts} for k, lbl, opts in TEMPLATE10_FIELDS],
            "rows": rows, "count": len(rows)}


def qualitative_structure(saved: dict | None) -> dict:
    """The three qualitative tables with the institution's authored text merged in. `saved` is the org-level
    JSONB dict keyed 'table1.a' → text. Returns render-ready tables + a completion count."""
    saved = saved or {}
    out = []
    total = filled = 0
    for tkey, t in TABLES.items():
        rows = []
        for rid, group, prompt in t["rows"]:
            key = f"{tkey}.{rid}"
            val = saved.get(key) or ""
            total += 1
            if val.strip():
                filled += 1
            rows.append({"key": key, "row": rid, "group": group, "prompt": prompt, "value": val})
        out.append({"table": tkey, "title": t["title"], "rows": rows})
    return {"tables": out, "total_rows": total, "authored": filled}
