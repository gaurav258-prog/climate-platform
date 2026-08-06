"""How much of each mandatory filing Tellumen can produce from the data it holds — the honest coverage map.

For every framework, the regulator's disclosure breaks into sections. Each is classified by SOURCE:
  computed      — produced from your book + our physical/nature engine (the moat)
  integrated    — a datapoint the regulator wants but that comes from outside this engine (GHG inventory,
                  Taxonomy alignment flags, EPC ratings) — you provide it / we integrate a feed
  client        — you author (qualitative narrative, governance, transition plan)
  out_of_scope  — not something this platform produces (e.g. carbon-price transition-risk modelling)

This is deliberately conservative: 'computed' means we actually build it today (verified against the
disclosure builders), never an aspiration.
"""
from __future__ import annotations

# (section the regulator expects, source)
COVERAGE: dict[str, list[tuple[str, str]]] = {
    "bank_tcfd": [
        ("Physical climate-risk exposure — value at risk by hazard, scenario × horizon", "computed"),
        ("Financed emissions — PCAF Scope 1–3 (from your issuer-emissions feed)", "computed"),
        ("EU Taxonomy Art. 8 — eligibility (GAR numerator)", "computed"),
        ("EU Taxonomy Art. 8 — alignment: DNSH + minimum safeguards (→ Green Asset Ratio)", "integrated"),
        ("Transition risk — carbon-price sensitivity / stranded assets", "out_of_scope"),
        ("TCFD governance, strategy & transition-plan narrative", "client"),
    ],
    "reit_tcfd": [
        ("Physical climate-risk to property value + net-operating-income impact", "computed"),
        ("EU Taxonomy Art. 8 — eligibility", "computed"),
        ("EU Taxonomy Art. 8 — alignment", "integrated"),
        ("Energy performance (EPC ratings)", "integrated"),
        ("TCFD governance & strategy narrative", "client"),
    ],
    "sfdr_pai": [
        ("PAI 1–6 climate indicators — emissions, carbon footprint, WACI, fossil-fuel, energy", "computed"),
        ("PAI 7–9 nature indicators — biodiversity, emissions to water, hazardous waste", "computed"),
        ("PAI 10–14 social & governance indicators (from your issuer feed)", "computed"),
        ("Additional / opt-in PAI indicators (Tables 2–3)", "integrated"),
        ("Narratives — policies, actions, engagement, reference standards", "client"),
    ],
    "csrd_e1": [
        ("ESRS E1-9 — physical-risk anticipated financial effects (own ops + upstream)", "computed"),
        ("ESRS E1-6 — GHG emissions (Scope 1–3) & energy", "integrated"),
        ("ESRS E1-1/4 — transition plan, targets, carbon price", "out_of_scope"),
        ("ESRS E1 — governance & impact/risk/opportunity narrative", "client"),
    ],
    "esrs_pack": [
        ("ESRS E1-9 — physical-risk anticipated financial effects", "computed"),
        ("ESRS E3 — water-stress exposure (own ops + upstream)", "computed"),
        ("ESRS E4 — deforestation determination (EUDR, satellite)", "computed"),
        ("ESRS E1-6 — GHG emissions (Scope 1–3) & energy", "integrated"),
        ("ESRS E3/E4 — measured water withdrawal / biodiversity-area metrics", "integrated"),
        ("ESRS — transition plan & narrative", "client"),
    ],
    "insurer_climate": [
        ("NatCat expected annual loss + loss ratio by peril", "computed"),
        ("Sum insured at risk (High+) by peril & geography", "computed"),
        ("Underwriting strategy & climate narrative", "client"),
    ],
    "eudr_dds": [
        ("Per-plot geolocation + deforestation-free determination (satellite vs 2020 cutoff)", "computed"),
        ("Legality evidence + supplier declarations", "integrated"),
    ],
}

_SOURCES = ("computed", "integrated", "client", "out_of_scope")


def coverage(framework: str) -> dict | None:
    """The section-by-section coverage of a filing + a summary (how much we produce from your data)."""
    secs = COVERAGE.get(framework)
    if not secs:
        return None
    sections = [{"section": s, "source": src} for s, src in secs]
    counts = {k: sum(1 for _, src in secs if src == k) for k in _SOURCES}
    total = len(secs)
    return {"sections": sections, "counts": counts, "total": total,
            "pct_computed": round(100 * counts["computed"] / total) if total else 0}
