"""Machine-readable (XBRL) tagging of the ESRS Climate & Nature pack.

Turns the pack into structured **facts** — each carrying its ESRS disclosure-requirement reference,
context (entity + period + scenario), unit and value — and emits a well-formed **XBRL instance**.

Honesty about the one external dependency: real ESEF filing binds facts to the *adopted EFRAG ESRS
Set 1 XBRL taxonomy*. We don't ship that taxonomy, so the concepts here use a clearly PROVISIONAL
`tesrs:` namespace that must be re-pointed at the official taxonomy in the filing tool. Everything
else — the xbrli contexts, units, fact structure — is genuine XBRL. So this is a real tagged-data
layer + a real instance shape, NOT a validated ESEF/iXBRL filing, and we say so.
"""
from __future__ import annotations

import html
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from services.intelligence.esrs_nature import build_esrs_pack

# scheme URIs for the entity identifier
LEI_SCHEME = "http://standards.iso.org/iso/17442"
EORI_SCHEME = "https://ec.europa.eu/eori"
PROVISIONAL_NS = "https://tellumen.example/xbrl/esrs-provisional"


def _facts(pack: dict) -> list[dict]:
    """Each fact: {concept, dr (ESRS disclosure requirement), label, value, unit, kind}."""
    out: list[dict] = []
    by = {t["topic"]: t for t in pack["topics"]}

    e1 = by.get("E1", {})
    fe = e1.get("financial_effects", {})
    if fe:
        for concept, dr, label, val in [
            ("AssetValueAtMaterialPhysicalRisk", "ESRS E1-9", "Asset value at material physical risk", fe["asset_value_at_risk_eur"]),
            ("BusinessInterruptionExposure", "ESRS E1-9", "Business-interruption exposure (v0)", fe["business_interruption_eur"]),
            ("SourcingCOGSAtRiskPublished", "ESRS E1-9", "Sourcing COGS at risk (published)", fe["cogs_at_risk_published_eur"]),
            ("ExposureMappedWithheld", "ESRS E1-9", "Exposure mapped, euro withheld (chain not validated)", fe["exposure_mapped_but_withheld_eur"]),
        ]:
            out.append({"concept": concept, "dr": dr, "label": label, "value": round(val), "unit": "eur", "kind": "monetary"})

    e3 = by.get("E3")
    if e3:
        oo, up = e3["own_operations"], e3["upstream"]
        out += [
            {"concept": "SitesWaterStressed", "dr": "ESRS E3-4", "label": "Own sites under water stress", "value": oo["sites_water_stressed"], "unit": "pure", "kind": "count"},
            {"concept": "AssetValueExposedToWaterStress", "dr": "ESRS E3-5", "label": "Asset value exposed to water stress", "value": round(oo["asset_value_exposed_eur"]), "unit": "eur", "kind": "monetary"},
            {"concept": "SourcingPlotsWaterStressed", "dr": "ESRS E3-4", "label": "Sourcing plots under water stress", "value": up["plots_water_stressed"], "unit": "pure", "kind": "count"},
            {"concept": "SpendExposedToWaterStress", "dr": "ESRS E3-5", "label": "Sourcing spend exposed to water stress", "value": round(up["spend_exposed_eur"]), "unit": "eur", "kind": "monetary"},
        ]

    e4 = by.get("E4")
    if e4:
        out += [
            {"concept": "EUDRCoveredPlots", "dr": "ESRS E4-5", "label": "EUDR-covered sourcing plots", "value": e4["eudr_covered_plots"], "unit": "pure", "kind": "count"},
            {"concept": "DeforestationFreePlots", "dr": "ESRS E4-5", "label": "Deforestation-free plots (determined)", "value": e4["deforestation_free"], "unit": "pure", "kind": "count"},
            {"concept": "NonCompliantPlots", "dr": "ESRS E4-5", "label": "Non-compliant plots (post-cutoff forest loss)", "value": e4["non_compliant"], "unit": "pure", "kind": "count"},
            {"concept": "PostCutoffForestLossHa", "dr": "ESRS E4-5", "label": "Post-cutoff forest loss", "value": e4["post_cutoff_forest_loss_ha"], "unit": "hectare", "kind": "area"},
        ]
    return out


def build_facts(session: Session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                period_end: str | None = None) -> dict:
    """The tagged-facts export (JSON): entity context + a flat list of ESRS facts + the binding caveat."""
    pack = build_esrs_pack(session, org_id, scenario=scenario, horizon=horizon)
    ent = pack["entity"]
    scheme, ident = ((LEI_SCHEME, ent.get("lei")) if ent.get("lei") else (EORI_SCHEME, ent.get("eori")) if ent.get("eori") else (EORI_SCHEME, None))
    return {
        "taxonomy": {"status": "provisional", "namespace": PROVISIONAL_NS,
                     "note": "Concepts use a provisional namespace; bind to the adopted EFRAG ESRS Set 1 XBRL "
                             "taxonomy in your filing tool. This is a tagged-data layer, not a validated ESEF/iXBRL filing."},
        "entity": {"name": ent.get("name"), "identifier": ident, "scheme": scheme},
        "period_end": period_end or f"{date.today().year - 1}-12-31",
        "reporting_basis": pack["reporting_basis"],
        "facts": _facts(pack),
    }


def build_xbrl_instance(session: Session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                        period_end: str | None = None) -> str:
    """A well-formed XBRL instance built from the facts (provisional taxonomy namespace, disclosed)."""
    d = build_facts(session, org_id, scenario=scenario, horizon=horizon, period_end=period_end)
    ident = html.escape(d["entity"]["identifier"] or "UNKNOWN")
    scheme = html.escape(d["entity"]["scheme"])
    period = html.escape(d["period_end"])
    stamped = datetime.now(timezone.utc).isoformat()

    facts_xml = []
    for f in d["facts"]:
        unit = f["unit"]
        dec = "0" if f["kind"] in ("monetary", "count") else "2"
        facts_xml.append(
            f'  <tesrs:{f["concept"]} contextRef="c1" unitRef="{unit}" decimals="{dec}">{f["value"]}</tesrs:{f["concept"]}>'
            f'  <!-- {f["dr"]}: {html.escape(f["label"])} -->')
    facts_block = "\n".join(facts_xml)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- Tellumen ESRS Climate & Nature — tagged facts, generated {stamped}.
     PROVISIONAL: concepts use the tesrs placeholder namespace ({PROVISIONAL_NS}) and MUST be bound to the
     adopted EFRAG ESRS Set 1 XBRL taxonomy before filing. This is a real XBRL instance shape + a real
     tagged-data layer, NOT a validated ESEF/iXBRL filing. A euro is a firm figure only where the
     hazard->yield/asset chain is validated; otherwise exposure is mapped and the euro withheld. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:link="http://www.xbrl.org/2003/linkbase"
            xmlns:xlink="http://www.w3.org/1999/xlink"
            xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
            xmlns:tesrs="{PROVISIONAL_NS}">
  <link:schemaRef xlink:type="simple" xlink:href="{PROVISIONAL_NS}.xsd"/>
  <xbrli:context id="c1">
    <xbrli:entity><xbrli:identifier scheme="{scheme}">{ident}</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>{period}</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>
  <xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
  <xbrli:unit id="hectare"><xbrli:measure>tesrs:hectare</xbrli:measure></xbrli:unit>
{facts_block}
</xbrli:xbrl>
'''
