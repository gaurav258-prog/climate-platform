"""Machine-readable SFDR PAI export — XBRL instance.

Regulators are moving disclosures to structured, tagged formats (ESEF/iXBRL). SFDR
PAI does not yet have an official public XBRL taxonomy, so this emits a valid XBRL
*instance* against a documented Tellumen PAI taxonomy: proper xbrli contexts
(entity = manager LEI, reference period), units (tCO₂e, EUR, pure), and one tagged
fact per mandatory indicator that carries a value.

Honest scope: the STRUCTURE is real XBRL and machine-consumable today; the taxonomy
namespace is ours as a placeholder — swap `TPAI_NS`/`schemaRef` for ESMA's official
SFDR taxonomy the moment it is published, and the instance is submission-shaped.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

XBRLI_NS = "http://www.xbrl.org/2003/instance"
LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"
ISO4217_NS = "http://www.xbrl.org/2003/iso4217"
LEI_SCHEME = "http://standards.iso.org/iso/17442"
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


def _fact(name, ctx, unit, value, decimals="2"):
    return (f'  <tpai:{name} contextRef="{ctx}"'
            + (f' unitRef="{unit}"' if unit else "")
            + f' decimals="{decimals}">{value}</tpai:{name}>')


def sfdr_pai_xbrl(statement: dict) -> str:
    """Serialize a PAI statement (fund- or entity-level) to an XBRL instance string."""
    ent = statement.get("entity", {})
    lei = ent.get("manager_lei") or "LEIUNAVAILABLE00000"
    ref_year = (statement.get("summary", {}) or {}).get("reference_year")
    period = f"{ref_year}" if ref_year else "2023"
    scheme = escape(LEI_SCHEME, {'"': "&quot;"})
    lei_x = escape(str(lei))

    # Duration context over the reference year (period-type facts) + an instant.
    ctx_dur = "d0"
    contexts = [
        f'  <xbrli:context id="{ctx_dur}">',
        '    <xbrli:entity>',
        f'      <xbrli:identifier scheme="{scheme}">{lei_x}</xbrli:identifier>',
        '    </xbrli:entity>',
        '    <xbrli:period>',
        f'      <xbrli:startDate>{period}-01-01</xbrli:startDate>',
        f'      <xbrli:endDate>{period}-12-31</xbrli:endDate>',
        '    </xbrli:period>',
        '  </xbrli:context>',
    ]

    units = [
        '  <xbrli:unit id="uPure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uEUR"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uCO2e"><xbrli:measure>tpai:tCO2e</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uCO2ePerMEUR"><xbrli:measure>tpai:tCO2ePerMEUR</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uCO2ePerMEURRevenue"><xbrli:measure>tpai:tCO2ePerMEURRevenue</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uGWhPerMEUR"><xbrli:measure>tpai:GWhPerMEUR</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uTonnesPerMEUR"><xbrli:measure>tpai:tonnesPerMEUR</xbrli:measure></xbrli:unit>',
    ]

    facts = []
    for ind in statement.get("indicators", []):
        num = ind.get("number")
        val = ind.get("value")
        if num not in _ELEMENT or val is None:
            continue
        name, unit = _ELEMENT[num]
        if num == 1 and isinstance(val, dict):
            # PAI 1 has scope 1/2/3 + total — emit each as its own fact.
            for scope_key, suffix in (("scope_1", "Scope1"), ("scope_2", "Scope2"),
                                      ("scope_3", "Scope3"), ("total", "Total")):
                v = val.get(scope_key)
                if v is not None:
                    facts.append(_fact(name + suffix, ctx_dur, "uCO2e", int(round(v)), decimals="0"))
        elif isinstance(val, (int, float)):
            facts.append(_fact(name, ctx_dur, unit, val))

    # Taxonomy alignment/eligibility facts, where present.
    tax = statement.get("taxonomy", {}) or {}
    for key, elem in (("taxonomy_eligible_pct", "TaxonomyEligiblePct"),
                      ("taxonomy_aligned_pct", "TaxonomyAlignedPct")):
        if tax.get(key) is not None:
            facts.append(_fact(elem, ctx_dur, "uPure", tax[key]))

    header = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<xbrli:xbrl',
        f'    xmlns:xbrli="{XBRLI_NS}"',
        f'    xmlns:link="{LINK_NS}"',
        f'    xmlns:xlink="{XLINK_NS}"',
        f'    xmlns:iso4217="{ISO4217_NS}"',
        f'    xmlns:tpai="{TPAI_NS}">',
        f'  <link:schemaRef xlink:type="simple" xlink:href="{TPAI_SCHEMA}"/>',
        f'  <!-- Tellumen SFDR PAI XBRL instance. Reference period FY{period}. Entity LEI {lei_x}.',
        '       Taxonomy namespace is a placeholder; swap for ESMA official when published. -->',
    ]
    body = header + contexts + units + facts + ["</xbrli:xbrl>"]
    return "\n".join(body) + "\n"
