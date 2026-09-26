"""Methodology facts for regulatory packages — derived, never re-typed.

A package's methodology section is an attestation: every claim in it must be something the platform actually
does. So nothing here is hand-written prose about models or sources. Each fact is read from the registry that
owns it, scoped to the hazards actually present in the package:

  data sources     ← services.data.feeds (HAZARD_FEEDS → FEEDS, with each feed's maturity)
  hazard coverage  ← core.hazard_taxonomy (EU Taxonomy hazard, acute/chronic, maturity tier, model basis)
  model versions   ← canonical_scores.model_version on the very rows in the package
  projections      ← ml.scoring.projection_coverage (how each hazard is carried to 2030/2050/2100)

Pure: takes the package rows, touches no DB.
"""
from __future__ import annotations

from collections import defaultdict


def _tier_labels() -> dict[str, str]:
    from services.intelligence.coverage import eu_taxonomy_coverage
    return {t["tier"]: t["label"] for t in eu_taxonomy_coverage()["tiers"]}


def _taxonomy_by_channel() -> dict[str, list]:
    from core.hazard_taxonomy import EU_TAXONOMY, EXTRA_CHANNELS
    out: dict[str, list] = defaultdict(list)
    for h in (*EU_TAXONOMY, *EXTRA_CHANNELS):
        for c in h.internal:
            out[c.value].append(h)
    return out


def package_hazards(rows: list[dict]) -> list[str]:
    return sorted({r["hazard_type"] for r in rows if r.get("hazard_type")})


def data_sources(hazards: list[str]) -> dict:
    """The registered feeds behind the package's hazards, with maturity. A hazard with no registered feed is
    listed as such — a source is never invented for it."""
    from services.data.feeds import FEEDS, HAZARD_FEEDS
    by_key = {f["key"]: f for f in FEEDS}
    used: dict[str, list[str]] = defaultdict(list)
    unmapped = []
    for hz in hazards:
        keys = [k for k in HAZARD_FEEDS.get(hz, []) if k in by_key]
        if not keys:
            unmapped.append(hz)
        for k in keys:
            used[k].append(hz)
    sources = []
    for k in (f["key"] for f in FEEDS if f["key"] in used):   # registry order
        f = by_key[k]
        src = {"key": k, "name": f["name"], "maturity": f["maturity"], "hazards": used[k]}
        if f["maturity"] != "live":
            src["caveat"] = f.get("note")                   # proxy / partial / on-demand: the gap, stated
        sources.append(src)
    return {"sources": sources, "hazards_without_registered_feed": unmapped}


def hazard_coverage(hazards: list[str]) -> list[dict]:
    """Each package hazard → its EU Taxonomy hazard(s), acute/chronic nature and maturity tier."""
    tax = _taxonomy_by_channel()
    labels = _tier_labels()
    out = []
    for hz in hazards:
        eu = tax.get(hz, [])
        if not eu:
            out.append({"hazard_type": hz, "eu_taxonomy_hazards": [], "nature": None,
                        "tier": None, "tier_label": "Not in hazard registry"})
            continue
        tiers = {h.tier.value for h in eu}
        tier = eu[0].tier.value if len(tiers) == 1 else None
        out.append({
            "hazard_type": hz,
            # `model_basis` is the hazard registry's own statement of what the model reads and how it was validated
            "eu_taxonomy_hazards": [{"id": h.id, "name": h.name, "model_basis": h.source} for h in eu],
            "nature": eu[0].nature,
            "tier": tier,
            "tier_label": labels.get(tier) if tier else ", ".join(sorted(labels.get(t, t) for t in tiers)),
        })
    return out


def hazard_coverage_text(coverage: list[dict]) -> str:
    """One-line summary of `hazard_coverage` for consumers that read a string."""
    def part(nature: str) -> str:
        items = [f"{c['hazard_type']} ({c['tier_label']})" for c in coverage if c["nature"] == nature]
        return ", ".join(items) or "none in package"
    text_ = f"Acute: {part('acute')}. Chronic: {part('chronic')}."
    other = [c["hazard_type"] for c in coverage if c["nature"] is None]
    if other:
        text_ += f" Not in hazard registry: {', '.join(other)}."
    return text_


def model_versions(rows: list[dict]) -> dict[str, list[str]]:
    """The model version(s) that actually produced the package's scores, per hazard."""
    out: dict[str, set] = defaultdict(set)
    for r in rows:
        if r.get("hazard_type") and r.get("model_version"):
            out[r["hazard_type"]].add(r["model_version"])
    return {hz: sorted(v) for hz, v in sorted(out.items())}


def projection_by_hazard(hazards: list[str]) -> dict[str, dict]:
    """How each package hazard is carried forward to future horizons (the engine's projection registry)."""
    from ml.scoring.projection_coverage import projection_coverage
    reg = {e["hazard"]: e for e in projection_coverage()["items"]}
    return {hz: {"mode": reg[hz]["mode"], "mode_label": reg[hz]["mode_label"]}
            for hz in hazards if hz in reg}


def scenarios(rows: list[dict]) -> list[str]:
    return sorted({r["scenario"] for r in rows if r.get("scenario")})


def build(rows: list[dict]) -> dict:
    """All derived methodology facts for a package."""
    hazards = package_hazards(rows)
    coverage = hazard_coverage(hazards)
    versions = model_versions(rows)
    return {
        "hazards": hazards,
        "scoring_model": ("Per-hazard scoring models; the model version that produced each score is "
                          "stamped on the score and listed in model_versions"),
        "model_versions": versions,
        "data_sources": data_sources(hazards),
        "hazard_coverage": coverage,
        "hazard_coverage_text": hazard_coverage_text(coverage),
        "scenarios": scenarios(rows),
        "projection_by_hazard": projection_by_hazard(hazards),
    }
