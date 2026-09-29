"""Regulation reference — the authoritative context for each framework the platform files.

Plain-language, faithful summaries with links to the OFFICIAL source (EUR-Lex / IFRS / EFRAG / EIOPA) so a
preparer can see, per obligation: what the regulation is, who mandates it, how often, what the official form
is, and what data must be supplied. The linked source is authoritative; the `summary` is a readable digest,
not a substitute for the legal text. Keyed by the platform's framework id.
"""
from __future__ import annotations

# framework_id -> reference metadata
REFERENCE: dict[str, dict] = {
    # `url` = the governing act, guaranteed-English EUR-Lex (CELEX). `form_url` = the document that actually
    # carries the reporting TEMPLATES — deliberately distinct from `url` where the templates live in a separate
    # amending act / annex / regulator page, so "Official regulation" and "Official form" no longer collide.
    "bank_tcfd": {
        "official_name": "TCFD-aligned climate disclosures with EU Taxonomy Article 8 KPIs",
        "authority": "National competent authority / EBA",
        "legal_basis": "Taxonomy Regulation (EU) 2020/852, Art. 8 · Disclosures Delegated Act (EU) 2021/2178 (credit-institution KPIs apply from 2024) · TCFD recommendations",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32021R2178",
        "summary": "Credit institutions disclose the EU-Taxonomy eligibility and alignment of their exposures "
                   "(including the Green Asset Ratio) together with TCFD-aligned governance, strategy, "
                   "risk-management and metrics for climate physical and transition risk.",
        "official_form": "Green Asset Ratio reporting templates — Annexes V–XI of Delegated Reg. (EU) 2021/2178 (credit-institution KPIs)",
        "form_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32021R2178",
        "inputs": "Loan / exposure book: counterparty, NACE sector, collateral location, outstanding balance, "
                  "and EU-Taxonomy eligibility & alignment flags.",
    },
    "bank_p3esg": {
        "official_name": "Pillar 3 disclosures of ESG risks (EBA prudential templates)",
        "authority": "National competent authority / EBA",
        # the implementing act, its templates and their location come from the governing specification (reference())
        "legal_basis": "CRR (EU) 575/2013, Art. 449a",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32013R0575",
        "summary": "Large institutions disclose prudential information on ESG risks — quantitative templates for "
                   "the banking book's exposure to climate-change physical risk (by geography and sector) and "
                   "transition risk, the Green Asset Ratio / BTAR, and mitigating actions.",
        "official_form": "ESG disclosure templates of the implementing act in force",
        "form_url": None,
        "inputs": "Loan / exposure book: counterparty, NACE sector, collateral location & maturity, outstanding "
                  "balance, EU-Taxonomy eligibility & alignment, and counterparty GHG (Scope 1–3) for transition metrics.",
    },
    "reit_tcfd": {
        "official_name": "TCFD-aligned climate disclosures with EU Taxonomy Article 8 KPIs (property portfolio)",
        "authority": "National competent authority (CSRD transposition)",
        "legal_basis": "Taxonomy Regulation (EU) 2020/852, Art. 8 · Disclosures Delegated Act (EU) 2021/2178, Annexes I–II (non-financial undertaking KPIs) · TCFD recommendations",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32021R2178",
        "summary": "Real-estate undertakings disclose the Taxonomy eligibility/alignment and TCFD-aligned "
                   "physical & transition climate risk of their property portfolio.",
        "official_form": "Art. 8 reporting templates — Annexes I–II (turnover/CapEx/OpEx KPIs), Delegated Reg. (EU) 2021/2178",
        "form_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32021R2178",
        "inputs": "Property schedule: location, property value, net operating income, construction attributes, "
                  "and EU-Taxonomy eligibility.",
    },
    "reit_taxonomy": {
        "official_name": "EU Taxonomy Article 8 KPIs — turnover / CapEx / OpEx (property portfolio)",
        "authority": "National competent authority (CSRD transposition)",
        "legal_basis": "Delegated Regulation (EU) 2021/2178, Art. 8 (Taxonomy KPI disclosure)",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32021R2178",
        "summary": "Real-estate undertakings disclose the proportion of turnover, CapEx and OpEx that is "
                   "Taxonomy-eligible and, of that, Taxonomy-aligned, per Climate Delegated Act (EU) 2021/2139 "
                   "Annex I §7.7 (acquisition and ownership of buildings).",
        "official_form": "Art. 8 reporting templates — Annexes I–II (turnover/CapEx/OpEx KPIs), Delegated Reg. (EU) 2021/2178",
        "form_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32021R2178",
        "inputs": "Property schedule: rental income (turnover proxy), EU-Taxonomy eligibility, EPC rating; "
                  "the undertaking's CapEx/OpEx ledger by activity (Annex I §1.1.2/1.1.3).",
    },
    "sfdr_pai": {
        "official_name": "SFDR Statement on Principal Adverse Impacts on sustainability factors",
        "authority": "National competent authority (ESAs — ESMA / EBA / EIOPA)",
        # the RTS, its template and its link come from the governing specification (reference())
        "legal_basis": "SFDR Regulation (EU) 2019/2088, Art. 4",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32019R2088",
        "summary": "Financial market participants report the 14 mandatory (plus selected additional) Principal "
                   "Adverse Impact indicators of their investments — GHG emissions, carbon footprint, fossil-fuel "
                   "exposure, biodiversity, water, waste and social/governance factors — on the Annex I template.",
        "official_form": "PAI statement template of the regulatory technical standards in force",
        "form_url": None,
        "inputs": "Holdings by ISIN with market value; issuer GHG (Scope 1–3), revenue / EVIC, and the voluntary-PAI "
                  "attributes; fund look-through where a fund is held.",
    },
    "sfdr_precontractual": {
        "official_name": "SFDR pre-contractual disclosure of a financial product (Art. 8 / Art. 9)",
        "authority": "National competent authority (ESAs — ESMA / EBA / EIOPA)",
        # the RTS, its templates and its link come from the governing specification (family sfdr_product)
        "legal_basis": "SFDR Regulation (EU) 2019/2088, Arts. 8 and 9",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32019R2088",
        "summary": "For each product that promotes environmental or social characteristics (Art. 8) or has a sustainable "
                   "investment objective (Art. 9), the template annexed to its prospectus: what it promotes or pursues, "
                   "its strategy, planned asset allocation, minimum Taxonomy alignment and sustainable investment shares.",
        "official_form": "Annex II / III template of the regulatory technical standards in force",
        "form_url": None,
        "inputs": "The fund's SFDR classification and LEI; the manager's commitments and answers to each template item.",
    },
    "sfdr_periodic": {
        "official_name": "SFDR periodic disclosure of a financial product (Art. 8 / Art. 9)",
        "authority": "National competent authority (ESAs — ESMA / EBA / EIOPA)",
        "legal_basis": "SFDR Regulation (EU) 2019/2088, Art. 11",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32019R2088",
        "summary": "Annexed to the product's annual report: how far its characteristics or objective were met over the "
                   "reference period, its top investments, asset allocation, sectors, and Taxonomy alignment (turnover, "
                   "CapEx and OpEx, with fossil gas and nuclear shown separately).",
        "official_form": "Annex IV / V template of the regulatory technical standards in force",
        "form_url": None,
        "inputs": "Holdings over the reference period by issuer; each investee's own Taxonomy KPIs; the manager's answers.",
    },
    "csrd_e1": {
        "official_name": "CSRD — ESRS E1 Climate Change disclosure",
        "authority": "National competent authority (CSRD transposition)",
        "legal_basis": "CSRD Directive (EU) 2022/2464 · ESRS Delegated Regulation (EU) 2023/2772, ESRS E1",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2772",
        "summary": "Undertakings disclose their material physical and transition climate risks, transition plan, "
                   "GHG emissions (Scope 1–3), energy, and the financial effects of climate risk per the ESRS E1 "
                   "datapoints, tagged in the EFRAG ESRS XBRL taxonomy.",
        "official_form": "ESRS E1 disclosure requirements & datapoints — Annex I to Delegated Reg. (EU) 2023/2772 · EFRAG ESRS XBRL taxonomy",
        "form_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2772",
        "inputs": "Own sites (location, asset value, throughput / business interruption), upstream sourcing "
                  "(commodity spend by origin), and GHG / energy data.",
    },
    "esrs_pack": {
        "official_name": "ESRS Climate & Nature pack (E1 Climate · E3 Water & Marine · E4 Biodiversity)",
        "authority": "National competent authority (CSRD transposition)",
        "legal_basis": "CSRD Directive (EU) 2022/2464 · ESRS Delegated Regulation (EU) 2023/2772, ESRS E1 / E3 / E4",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2772",
        "summary": "The environmental ESRS topical standards — climate (E1), water & marine resources (E3), and "
                   "biodiversity & ecosystems (E4): impacts, risks, dependencies and metrics.",
        "official_form": "ESRS E1 / E3 / E4 disclosure requirements & datapoints — Annex I to Delegated Reg. (EU) 2023/2772 · EFRAG ESRS XBRL taxonomy",
        "form_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2772",
        "inputs": "Own sites + upstream sourcing, plus water-stress and biodiversity-sensitive-area attributes.",
    },
    "insurer_climate": {
        "official_name": "Climate / natural-catastrophe exposure disclosure (underwriting book)",
        "authority": "National competent authority / EIOPA",
        "legal_basis": "Solvency II (Directive 2009/138/EC) climate-risk supervision · IFRS S2 Climate-related Disclosures",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0138",
        "summary": "Insurers disclose the natural-catastrophe and climate exposure of their underwriting book — "
                   "sums insured, expected annual loss and loss ratios by peril and geography.",
        "official_form": "IFRS S2 Climate-related Disclosures (industry-based guidance, insurance) · EIOPA climate-risk supervisory reporting",
        "form_url": "https://www.ifrs.org/issued-standards/ifrs-sustainability-standards-navigator/ifrs-s2-climate-related-disclosures/",
        "inputs": "Statement of Values / policy book: insured location, sum insured, peril coverage, and "
                  "attachment / exhaustion where parametric.",
    },
    # EUDR is filed through the agri Disclosure page (TRACES DDS), but included for completeness of the reference.
    "eudr_dds": {
        "official_name": "EU Deforestation Regulation — Due Diligence Statement (TRACES)",
        "authority": "EU competent authorities (national) · European Commission (TRACES)",
        "legal_basis": "Regulation (EU) 2023/1115 (EUDR), Art. 33 (DDS) · Annex II (DDS content)",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1115",
        "summary": "Operators placing in-scope commodities on the EU market submit a Due Diligence Statement "
                   "with geolocation of plots of land and a deforestation-free / legality assessment, via TRACES.",
        "official_form": "TRACES Due Diligence Statement (DDS) — content per EUDR Annex II",
        "form_url": "https://webgate.ec.europa.eu/tracesnt/",
        "inputs": "Sourcing plots with geolocation (polygons), commodity, volume, and legality evidence.",
    },
}


def reference(framework: str, on=None) -> dict | None:
    """The framework's reference entry; where a template specification governs (services/regspec), the implementing act,
    where its templates and instructions sit, and its link come from that specification — never typed here."""
    ref = REFERENCE.get(framework)
    if ref is None:
        return None
    import services.regspec as R
    if framework not in R.frameworks():
        return ref
    spec = R.governing(framework, period_end=on or _today(), disclosure_date=on)
    return with_spec(ref, spec) if spec else ref


def with_spec(ref: dict, spec: dict) -> dict:
    """A reference entry stated for one specification — the act, the templates' location, the instructions and link."""
    act = spec["act"]
    url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{act['celex']}" if act.get("celex") else act.get("url")
    return {**ref,
            "legal_basis": f"{ref['legal_basis']} · {spec['legal_basis']['article']}",
            "url": url, "form_url": url, "act_celex": act.get("celex"), "spec_version": spec["version"],
            "official_form": f"{act.get('short') or act['title']} — {spec['legal_basis']['templates_in']}; instructions: "
                             f"{spec['legal_basis']['instructions_in']}"}


def _today():
    from datetime import date
    return date.today()
