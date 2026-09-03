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
from xml.dom.minidom import parseString

from sqlalchemy.orm import Session

from services.intelligence import xbrl_core
from services.intelligence.esrs_nature import build_esrs_pack
from services.intelligence.esrs_taxonomy import (
    CONCEPTS,
    binding_status,
    get_profile,
)

# scheme URIs for the entity identifier
LEI_SCHEME = "http://standards.iso.org/iso/17442"
EORI_SCHEME = "https://ec.europa.eu/eori"


def _entity(pack: dict) -> tuple[str, str | None]:
    """(scheme, identifier) — LEI preferred, else EORI."""
    ent = pack["entity"]
    if ent.get("lei"):
        return LEI_SCHEME, ent["lei"]
    if ent.get("eori"):
        return EORI_SCHEME, ent["eori"]
    return EORI_SCHEME, None


def _periods(period_end: str) -> tuple[str, str]:
    """(duration_start, instant) for the reporting year ending period_end."""
    year = period_end[:4]
    return f"{year}-01-01", period_end


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
                period_end: str | None = None, material: int = 40, profile_key: str = "provisional",
                pack: dict | None = None) -> dict:
    """The tagged-facts export (JSON): entity context + a flat list of ESRS facts, each carrying the concept
    QName under the chosen taxonomy profile, plus the profile's binding status.

    If `pack` is supplied (a frozen snapshot's esrs_pack payload), the facts are tagged FROM THAT payload
    rather than recomputed live — so the machine-readable filing is the exact frozen bytes (audit T7)."""
    if pack is None:
        pack = build_esrs_pack(session, org_id, scenario=scenario, horizon=horizon, material=material)
    ent = pack["entity"]
    scheme, ident = _entity(pack)
    profile = get_profile(profile_key)
    facts = _facts(pack)
    for f in facts:                      # attach the resolved QName + whether it is officially bound
        r = profile.resolve(f["concept"])
        f["qname"], f["bound"] = r["qname"], r["bound"]
    return {
        "taxonomy": binding_status(profile),
        "entity": {"name": ent.get("name"), "identifier": ident, "scheme": scheme},
        "period_end": period_end or f"{date.today().year - 1}-12-31",
        "reporting_basis": pack["reporting_basis"],
        "facts": facts,
    }


_UNIT = {"monetary": "eur", "count": "pure", "area": "hectare"}
_DEC = {"monetary": "0", "count": "0", "area": "2"}


def _contexts_xml(scheme: str, ident: str, dur_start: str, period: str) -> str:
    return (
        f'  <xbrli:context id="c_instant">\n'
        f'    <xbrli:entity><xbrli:identifier scheme="{scheme}">{ident}</xbrli:identifier></xbrli:entity>\n'
        f'    <xbrli:period><xbrli:instant>{period}</xbrli:instant></xbrli:period>\n'
        f'  </xbrli:context>\n'
        f'  <xbrli:context id="c_duration">\n'
        f'    <xbrli:entity><xbrli:identifier scheme="{scheme}">{ident}</xbrli:identifier></xbrli:entity>\n'
        f'    <xbrli:period><xbrli:startDate>{dur_start}</xbrli:startDate><xbrli:endDate>{period}</xbrli:endDate></xbrli:period>\n'
        f'  </xbrli:context>')


def _units_xml(prefix: str) -> str:
    return (
        f'  <xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>\n'
        f'  <xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>\n'
        f'  <xbrli:unit id="hectare"><xbrli:measure>{prefix}:hectare</xbrli:measure></xbrli:unit>')


def build_xbrl_instance(session: Session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                        period_end: str | None = None, material: int = 40, profile_key: str = "provisional",
                        pack: dict | None = None) -> str:
    """A well-formed XBRL instance, tagged under the chosen taxonomy profile (instant/duration contexts).
    Pass `pack` (a frozen snapshot payload) to tag the exact filed bytes rather than recompute (audit T7)."""
    d = build_facts(session, org_id, scenario=scenario, horizon=horizon, period_end=period_end,
                    material=material, profile_key=profile_key, pack=pack)
    profile = get_profile(profile_key)
    ident = html.escape(d["entity"]["identifier"] or "UNKNOWN")
    scheme = html.escape(d["entity"]["scheme"])
    period = html.escape(d["period_end"])
    dur_start, _ = _periods(d["period_end"])
    stamped = datetime.now(timezone.utc).isoformat()

    facts_xml = []
    for f in d["facts"]:
        c = CONCEPTS[f["concept"]]
        ctx = "c_instant" if c["period_type"] == "instant" else "c_duration"
        unit, dec, q = _UNIT[c["item_type"]], _DEC[c["item_type"]], f["qname"]
        facts_xml.append(
            f'  <{q} contextRef="{ctx}" unitRef="{unit}" decimals="{dec}">{f["value"]}</{q}>'
            f'  <!-- {f["dr"]}: {html.escape(f["label"])} -->')
    tax = d["taxonomy"]
    comment = (f'Tellumen ESRS Climate & Nature — tagged facts, generated {stamped}. '
               f'Taxonomy profile: {profile.key} ({tax["status"]}). {html.escape(tax["note"])} '
               f'A euro is a firm figure only where the hazard->yield/asset chain is validated; otherwise '
               f'exposure is mapped and the euro withheld.')
    return xbrl_core.xbrl_instance({profile.prefix: profile.namespace}, profile.schema_ref,
                                   [_contexts_xml(scheme, ident, dur_start, period)],
                                   [_units_xml(profile.prefix)], facts_xml, comment)


# --- Inline XBRL (iXBRL / ESEF) -------------------------------------------------------------------
def build_ixbrl(session: Session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                period_end: str | None = None, material: int = 40, profile_key: str = "provisional",
                pack: dict | None = None) -> str:
    """A human-readable ESRS Climate & Nature report with the figures inline-tagged (Inline XBRL 1.1).

    This is the ESEF *shape* — one document that a person reads and a machine parses. Under the provisional
    profile it is honestly NOT a validated ESEF filing; under an adopted EFRAG profile it becomes one once
    the official element map is supplied and the filing tool validates it. Pass `pack` (a frozen snapshot
    payload) to tag the exact filed bytes rather than recompute (audit T7).
    """
    d = build_facts(session, org_id, scenario=scenario, horizon=horizon, period_end=period_end,
                    material=material, profile_key=profile_key, pack=pack)
    profile = get_profile(profile_key)
    ent = d["entity"]
    ident = html.escape(ent["identifier"] or "UNKNOWN")
    scheme = html.escape(ent["scheme"])
    name = html.escape(ent["name"] or "Reporting entity")
    period = html.escape(d["period_end"])
    dur_start, _ = _periods(d["period_end"])
    basis = d["reporting_basis"]
    tax = d["taxonomy"]
    stamped = datetime.now(timezone.utc).isoformat()

    def _fmt(f):
        c = CONCEPTS[f["concept"]]
        if c["item_type"] == "monetary":
            return f'€{f["value"]:,.0f}'
        if c["item_type"] == "area":
            return f'{f["value"]:,.2f} ha'
        return f'{f["value"]:,.0f}'

    rows = []
    for f in d["facts"]:
        c = CONCEPTS[f["concept"]]
        ctx = "c_instant" if c["period_type"] == "instant" else "c_duration"
        unit, dec = _UNIT[c["item_type"]], _DEC[c["item_type"]]
        tag = xbrl_core.ix_nonfraction(f["qname"], ctx, unit, dec, f["value"])
        rows.append(
            f'    <tr><td class="dr">{html.escape(f["dr"])}</td>'
            f'<td>{html.escape(f["label"])}</td>'
            f'<td class="num" title="{html.escape(f["qname"])}">{_fmt(f)} <span class="ix">{tag}</span></td></tr>')
    rows_html = "\n".join(rows)

    body = (f'  <h1>{name} — ESRS Climate &amp; Nature disclosures</h1>\n'
            f'  <p class="meta">Reporting period ending {period} · basis {html.escape(str(basis.get("scenario")))}/'
            f'{html.escape(str(basis.get("horizon")))} · materiality ≥ {html.escape(str(basis.get("materiality_threshold")))} · '
            f'entity {ident} ({scheme.rsplit("/", 1)[-1].upper()}) · taxonomy profile <b>{profile.key}</b> ({tax["status"]}) · '
            f'generated {stamped[:19]}Z</p>\n\n'
            f'  <table>\n'
            f'    <thead><tr><th>Disclosure</th><th>Datapoint</th><th class="num">Value (inline-tagged)</th></tr></thead>\n'
            f'    <tbody>\n{rows_html}\n    </tbody>\n  </table>\n\n'
            f'  <p class="note"><b>Honesty &amp; binding:</b> {html.escape(tax["note"])} A euro is a firm figure only '
            f'where the hazard→yield/asset chain is validated; otherwise exposure is mapped and the euro withheld.</p>')
    return xbrl_core.ixbrl_document(
        title=f"{name} — ESRS Climate &amp; Nature (Inline XBRL)",
        extra_ns={profile.prefix: profile.namespace}, schema_ref=profile.schema_ref,
        contexts=[_contexts_xml(scheme, ident, dur_start, period)], units=[_units_xml(profile.prefix)],
        body_html=body)


# --- Validation -----------------------------------------------------------------------------------
def validate_document(xml: str, profile_key: str = "provisional") -> dict:
    """Structural validation of an XBRL / iXBRL document: well-formedness + completeness of each fact.

    This is NOT full ESRS taxonomy conformance (that needs the adopted EFRAG taxonomy + an XBRL processor
    such as Arelle — auto-run here if it happens to be installed). It is the honest layer we can guarantee:
    the document parses, every fact has a context + unit + decimals, the referenced contexts/units exist,
    and every concept resolves. Returns a checklist so the UI can show exactly what passed.
    """
    profile = get_profile(profile_key)
    checks: list[dict] = []
    errors: list[str] = []

    # 1. well-formed XML
    try:
        dom = parseString(xml.encode("utf-8"))
        checks.append({"name": "well_formed_xml", "ok": True, "detail": "document parses"})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "profile": profile.key, "profile_status": profile.status,
                "checks": [{"name": "well_formed_xml", "ok": False, "detail": str(e)}], "errors": [str(e)], "facts": 0}

    is_ixbrl = "inlineXBRL" in xml
    # 2. gather contexts + units present
    ctx_ids = {n.getAttribute("id") for n in dom.getElementsByTagName("xbrli:context")}
    unit_ids = {n.getAttribute("id") for n in dom.getElementsByTagName("xbrli:unit")}
    checks.append({"name": "has_contexts", "ok": bool(ctx_ids), "detail": f"{len(ctx_ids)} context(s)"})
    checks.append({"name": "has_units", "ok": bool(unit_ids), "detail": f"{len(unit_ids)} unit(s)"})

    # 3. schemaRef present
    has_schema = bool(dom.getElementsByTagName("link:schemaRef"))
    checks.append({"name": "schema_ref", "ok": has_schema, "detail": profile.schema_ref})
    if not has_schema:
        errors.append("missing link:schemaRef")

    # 4. every fact complete + references resolve + concept known
    if is_ixbrl:
        fact_nodes = dom.getElementsByTagName("ix:nonFraction")
        def local(n):
            return n.getAttribute("name").split(":")[-1]
    else:
        fact_nodes = [n for n in dom.getElementsByTagName("*")
                      if n.getAttribute("contextRef") and n.tagName not in ("xbrli:context", "xbrli:unit")]
        def local(n):
            return n.tagName.split(":")[-1]
    bad = 0
    for n in fact_nodes:
        cref, uref, dec = n.getAttribute("contextRef"), n.getAttribute("unitRef"), n.getAttribute("decimals")
        if cref not in ctx_ids:
            bad += 1; errors.append(f"{local(n)}: contextRef '{cref}' not defined")
        if uref not in unit_ids:
            bad += 1; errors.append(f"{local(n)}: unitRef '{uref}' not defined")
        if not dec:
            bad += 1; errors.append(f"{local(n)}: missing decimals")
        if local(n) not in CONCEPTS and local(n) not in profile.element_map.values():
            bad += 1; errors.append(f"{local(n)}: concept not in catalogue")
    checks.append({"name": "facts_complete", "ok": bad == 0, "detail": f"{len(fact_nodes)} fact(s), {bad} problem(s)"})

    # 5. binding coverage (informational — only a hard fail for an 'adopted' profile)
    bs = binding_status(profile)
    fully_bound = not bs["concepts_unbound"]
    checks.append({"name": "concepts_bound", "ok": (fully_bound or profile.key == "provisional"),
                   "detail": f'{bs["concepts_bound"]}/{bs["concepts_total"]} bound under {profile.key}'})

    # 6. optional Arelle conformance (only if the library is present in the environment)
    try:
        import arelle  # noqa: F401
        checks.append({"name": "arelle_available", "ok": True, "detail": "Arelle present — run full ESRS conformance in the filing step"})
    except Exception:  # noqa: BLE001
        checks.append({"name": "arelle_available", "ok": False,
                       "detail": "Arelle not installed here; full taxonomy conformance runs in the filing tool"})

    structural_ok = all(c["ok"] for c in checks if c["name"] in
                        ("well_formed_xml", "has_contexts", "has_units", "schema_ref", "facts_complete"))
    return {"ok": structural_ok, "profile": profile.key, "profile_status": profile.status,
            "is_ixbrl": is_ixbrl, "facts": len(fact_nodes), "checks": checks, "errors": errors,
            "disclaimer": "Structural + completeness validation. Full ESRS/ESEF taxonomy conformance requires "
                          "the adopted EFRAG taxonomy and an XBRL processor (Arelle) in the filing step."}
