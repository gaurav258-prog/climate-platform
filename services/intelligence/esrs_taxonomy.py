"""ESRS XBRL taxonomy binding — make "re-point at the adopted EFRAG taxonomy" a config drop-in.

Our XBRL facts must ultimately carry the concept names of the **adopted EFRAG ESRS Set 1 XBRL taxonomy**.
That taxonomy is still being finalized (the Omnibus reshuffle is moving it), and we don't ship it. So this
module separates the *mechanism* (how a fact is tagged) from the *binding* (which taxonomy's element name
it carries), behind a **TaxonomyProfile**:

  - `PROVISIONAL` — our own `tesrs:` namespace. Fully working today. Honestly labelled NOT a validated filing.
  - `EFRAG_SET1` — the real target. Its element map loads from `config/efrag_esrs_binding.json` the moment
    that file is dropped in (one JSON, no code change). Until then it reports `bound=False` per concept and
    the profile status stays `pending_adopted_taxonomy`, so we never pretend a concept is officially bound
    when it isn't.

That is the honest architecture: the tagging engine, the iXBRL shaping and the validator are all real now;
the only thing gated on an external artifact is the official element map, and swapping it in is data, not code.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# --- the concept catalogue: one row per ESRS datapoint we emit -------------------------------------
# item_type: monetary | count | area   ·   period_type: duration | instant
# `provisional` is the element local-name under the tesrs: namespace (always available).
CONCEPTS: dict[str, dict] = {
    "AssetValueAtMaterialPhysicalRisk":  {"dr": "ESRS E1-9", "label": "Asset value at material physical risk", "item_type": "monetary", "period_type": "instant"},
    "BusinessInterruptionExposure":      {"dr": "ESRS E1-9", "label": "Business-interruption exposure (v0)",     "item_type": "monetary", "period_type": "duration"},
    "SourcingCOGSAtRiskPublished":       {"dr": "ESRS E1-9", "label": "Sourcing COGS at risk (published)",       "item_type": "monetary", "period_type": "duration"},
    "ExposureMappedWithheld":            {"dr": "ESRS E1-9", "label": "Exposure mapped, euro withheld",          "item_type": "monetary", "period_type": "instant"},
    "SitesWaterStressed":                {"dr": "ESRS E3-4", "label": "Own sites under water stress",            "item_type": "count",    "period_type": "instant"},
    "AssetValueExposedToWaterStress":    {"dr": "ESRS E3-5", "label": "Asset value exposed to water stress",     "item_type": "monetary", "period_type": "instant"},
    "SourcingPlotsWaterStressed":        {"dr": "ESRS E3-4", "label": "Sourcing plots under water stress",       "item_type": "count",    "period_type": "instant"},
    "SpendExposedToWaterStress":         {"dr": "ESRS E3-5", "label": "Sourcing spend exposed to water stress",  "item_type": "monetary", "period_type": "duration"},
    "EUDRCoveredPlots":                  {"dr": "ESRS E4-5", "label": "EUDR-covered sourcing plots",             "item_type": "count",    "period_type": "instant"},
    "DeforestationFreePlots":            {"dr": "ESRS E4-5", "label": "Deforestation-free plots (determined)",   "item_type": "count",    "period_type": "instant"},
    "NonCompliantPlots":                 {"dr": "ESRS E4-5", "label": "Non-compliant plots (post-cutoff loss)",  "item_type": "count",    "period_type": "instant"},
    "PostCutoffForestLossHa":            {"dr": "ESRS E4-5", "label": "Post-cutoff forest loss",                 "item_type": "area",     "period_type": "duration"},
}

PROVISIONAL_NS = "https://tellumen.example/xbrl/esrs-provisional"
# Namespace the adopted taxonomy is expected to publish under. The ELEMENT MAP (local-names) is what we
# do not yet have — that's the drop-in file. The namespace being known is not the same as being bound.
EFRAG_SET1_NS = "https://xbrl.efrag.org/taxonomy/esrs/2024-12-31/esrs"
_BINDING_FILE = Path(os.getenv("EFRAG_ESRS_BINDING", "config/efrag_esrs_binding.json"))


@dataclass(frozen=True)
class TaxonomyProfile:
    key: str
    prefix: str
    namespace: str
    schema_ref: str
    status: str            # "provisional" | "adopted" | "pending_adopted_taxonomy"
    element_map: dict      # concept -> official local-name; empty until the adopted map is supplied

    def resolve(self, concept: str) -> dict:
        """Return how this concept is tagged under this profile: qname parts + whether it is officially bound."""
        official = self.element_map.get(concept)
        local = official or concept          # provisional falls back to our own local-name
        return {"prefix": self.prefix, "namespace": self.namespace,
                "local_name": local, "qname": f"{self.prefix}:{local}",
                "bound": self.key == "provisional" or official is not None}


def _load_efrag_map() -> dict:
    """Load the adopted-taxonomy element map if the config file is present; else empty (pending).
    A scaffold with unfilled (null/empty) values is honestly treated as pending — only real element
    names count as bound, so dropping the template in place never falsely reports 'adopted'."""
    try:
        if _BINDING_FILE.exists():
            data = json.loads(_BINDING_FILE.read_text())
            raw = data.get("elements", data) if isinstance(data, dict) else {}
            # keep only concepts with a real (non-empty string) official element name
            return {k: v for k, v in raw.items() if isinstance(v, str) and v.strip()}
    except Exception:
        pass
    return {}


def get_profile(key: str = "provisional") -> TaxonomyProfile:
    """The active taxonomy profile. `provisional` always works; `efrag_set1` lights up when its map drops in."""
    if key == "efrag_set1":
        emap = _load_efrag_map()
        return TaxonomyProfile(
            key="efrag_set1", prefix="esrs", namespace=EFRAG_SET1_NS,
            schema_ref=f"{EFRAG_SET1_NS}/esrs_all.xsd",
            status="adopted" if emap else "pending_adopted_taxonomy",
            element_map=emap)
    return TaxonomyProfile(
        key="provisional", prefix="tesrs", namespace=PROVISIONAL_NS,
        schema_ref=f"{PROVISIONAL_NS}.xsd", status="provisional", element_map={})


def binding_status(profile: TaxonomyProfile) -> dict:
    """Coverage of the profile: how many concepts are officially bound vs falling back."""
    resolved = {c: profile.resolve(c) for c in CONCEPTS}
    bound = [c for c, r in resolved.items() if r["bound"]]
    unbound = [c for c in CONCEPTS if c not in bound]
    return {
        "profile": profile.key, "status": profile.status, "namespace": profile.namespace,
        "concepts_total": len(CONCEPTS), "concepts_bound": len(bound), "concepts_unbound": unbound,
        "note": ("Provisional namespace — a real tagged-data layer, NOT a validated ESEF filing."
                 if profile.key == "provisional" else
                 ("Bound to the supplied EFRAG ESRS Set 1 element map." if not unbound else
                  "EFRAG profile selected but the adopted element map is not yet supplied; drop "
                  "config/efrag_esrs_binding.json to bind. Unbound concepts fall back to provisional names.")),
    }
