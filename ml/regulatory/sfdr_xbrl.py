"""Machine-readable SFDR PAI export — XBRL instance + Inline XBRL (iXBRL).

Regulators are moving disclosures to structured, tagged formats (ESEF/iXBRL). SFDR PAI does not yet have an
official public XBRL taxonomy, so this emits valid documents against a documented Tellumen PAI taxonomy: proper
xbrli contexts (entity = manager LEI, reference period), units (tCO₂e, EUR, pure), and one tagged fact per
mandatory indicator that carries a value.

Honest scope: the STRUCTURE is real XBRL and machine-consumable today; the taxonomy namespace is ours as a
placeholder — swap `TPAI_NS`/`schemaRef` for ESMA's official SFDR taxonomy the moment it is published, and the
instance is submission-shaped. Both the plain instance and the inline form share ONE serialization core
(services/intelligence/xbrl_core), the same core the ESRS tagger uses — so the XBRL plumbing lives in one place.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from services.intelligence import xbrl_core

XBRLI_NS = xbrl_core.XBRLI
LINK_NS = xbrl_core.LINK
XLINK_NS = xbrl_core.XLINK
ISO4217_NS = xbrl_core.ISO4217
LEI_SCHEME = xbrl_core.LEI_SCHEME
# Placeholder Tellumen PAI taxonomy — replace with the official ESMA SFDR namespace.
TPAI_NS = "https://taxonomy.tellumen.eu/sfdr/pai/2022"
TPAI_SCHEMA = "https://taxonomy.tellumen.eu/sfdr/pai/2022/pai.xsd"

# indicator number → (element localname, unit ref). Dict-valued PAI 1 handled specially.
_ELEMENT = {
    1: ("FinancedGHGEmissions", "uCO2e"),
    2: ("CarbonFootprint", "uCO2ePerMEUR"),
    3: ("WACI", "uCO2ePerMEURRevenue"),
    4: ("FossilFuelExposurePct", "uPure"),
    5: ("NonRenewableEnergyPct", "uPure"),
    6: ("EnergyIntensityHighImpact", "uGWhPerMEUR"),
    7: ("BiodiversityImpactPct", "uPure"),
    8: ("EmissionsToWater", "uTonnesPerMEUR"),
    9: ("HazardousWasteRatio", "uTonnesPerMEUR"),
    10: ("UNGCOECDViolationsPct", "uPure"),
    11: ("NoUNGCMonitoringPct", "uPure"),
    12: ("GenderPayGapPct", "uPure"),
    13: ("BoardGenderDiversityPct", "uPure"),
    14: ("ControversialWeaponsPct", "uPure"),
}

_UNITS = [
    xbrl_core.unit("uPure", "xbrli:pure"),
    xbrl_core.unit("uEUR", "iso4217:EUR"),
    xbrl_core.unit("uCO2e", "tpai:tCO2e"),
    xbrl_core.unit("uCO2ePerMEUR", "tpai:tCO2ePerMEUR"),
    xbrl_core.unit("uCO2ePerMEURRevenue", "tpai:tCO2ePerMEURRevenue"),
    xbrl_core.unit("uGWhPerMEUR", "tpai:GWhPerMEUR"),
    xbrl_core.unit("uTonnesPerMEUR", "tpai:tonnesPerMEUR"),
]


def _lei_period(statement: dict) -> tuple[str, str]:
    ent = statement.get("entity", {}) or {}
    lei = escape(str(ent.get("manager_lei") or "LEIUNAVAILABLE00000"))
    ref_year = (statement.get("summary", {}) or {}).get("reference_year")
    return lei, (f"{ref_year}" if ref_year else "2023")


def _facts(statement: dict) -> list[tuple]:
    """(localname, unit_ref, value, decimals, label) per reportable PAI/Taxonomy fact — the ONE source of
    truth both the plain XBRL and the inline form tag from."""
    out: list[tuple] = []
    for ind in statement.get("indicators", []):
        num, val = ind.get("number"), ind.get("value")
        if num not in _ELEMENT or val is None:
            continue
        name, unit = _ELEMENT[num]
        label = ind.get("metric") or name
        if num == 1 and isinstance(val, dict):            # PAI 1: scope 1/2/3 + total, each its own fact
            for sk, suffix in (("scope_1", "Scope1"), ("scope_2", "Scope2"), ("scope_3", "Scope3"), ("total", "Total")):
                v = val.get(sk)
                if v is not None:
                    out.append((name + suffix, "uCO2e", int(round(v)), "0", f"{label} — {suffix}"))
        elif isinstance(val, (int, float)):
            out.append((name, unit, val, "2", label))
    tax = statement.get("taxonomy", {}) or {}
    for key, elem in (("taxonomy_eligible_pct", "TaxonomyEligiblePct"), ("taxonomy_aligned_pct", "TaxonomyAlignedPct")):
        if tax.get(key) is not None:
            out.append((elem, "uPure", tax[key], "2", elem))
    return out


def sfdr_pai_xbrl(statement: dict) -> str:
    """Serialize a PAI statement (fund- or entity-level) to a plain XBRL instance string."""
    lei, period = _lei_period(statement)
    ctx = xbrl_core.context_duration("d0", LEI_SCHEME, lei, f"{period}-01-01", f"{period}-12-31")
    facts = [f'  <tpai:{n} contextRef="d0"' + (f' unitRef="{u}"' if u else "") + f' decimals="{d}">{v}</tpai:{n}>'
             for n, u, v, d, _ in _facts(statement)]
    comment = (f"Tellumen SFDR PAI XBRL instance. Reference period FY{period}. Entity LEI {lei}. "
               f"Taxonomy namespace is a placeholder; swap for ESMA official when published.")
    return xbrl_core.xbrl_instance({"tpai": TPAI_NS}, TPAI_SCHEMA, [ctx], _UNITS, facts, comment)


def sfdr_pai_ixbrl(statement: dict) -> str:
    """The same PAI facts as an Inline XBRL (iXBRL/ESEF-shaped) report — human-readable + machine-parseable,
    sharing the ESRS tagger's serialization core."""
    lei, period = _lei_period(statement)
    ent = statement.get("entity", {}) or {}
    name = escape(str(ent.get("manager_name") or ent.get("name") or "Reporting entity"))
    ctx = xbrl_core.context_duration("d0", LEI_SCHEME, lei, f"{period}-01-01", f"{period}-12-31")
    rows = []
    for n, u, v, d, label in _facts(statement):
        tag = xbrl_core.ix_nonfraction(f"tpai:{n}", "d0", u, d, v)
        rows.append(f'    <tr><td class="dr">SFDR</td><td>{escape(str(label))}</td>'
                    f'<td class="num" title="tpai:{n}">{v} <span class="ix">{tag}</span></td></tr>')
    body = (f'  <h1>{name} — SFDR Principal Adverse Impacts</h1>\n'
            f'  <p class="meta">Reference period FY{period} · entity {lei} (LEI) · '
            f'taxonomy namespace provisional (swap for ESMA official when published)</p>\n\n'
            f'  <table>\n    <thead><tr><th>Framework</th><th>Indicator</th><th class="num">Value (inline-tagged)</th></tr></thead>\n'
            f'    <tbody>\n' + "\n".join(rows) + '\n    </tbody>\n  </table>\n\n'
            f'  <p class="note"><b>Honesty &amp; binding:</b> the structure is real XBRL; the tpai: namespace is a '
            f"placeholder for ESMA's official SFDR taxonomy, bound in the filing tool once published.</p>")
    return xbrl_core.ixbrl_document(title=f"{name} — SFDR PAI (Inline XBRL)", extra_ns={"tpai": TPAI_NS},
                                    schema_ref=TPAI_SCHEMA, contexts=[ctx], units=_UNITS, body_html=body)
