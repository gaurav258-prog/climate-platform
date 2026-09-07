"""Supervision profiles — the configuration that makes the regulator module sector-agnostic.

data/reference/supervision_profiles.json holds: role templates, the supervisory cycle, per-sector expectations
(frameworks, regional unit, benchmark metrics + threshold defaults) and named profiles (customer classes).
A regulator organization resolves to ONE profile plus per-org overrides (supervisor_settings). Nothing here
names a sector in code: adding a supervisor for a new sector is a JSON entry.
"""
from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Optional

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "supervision_profiles.json"
DEFAULT_PROFILE = "banking_supervisor"


@lru_cache(maxsize=1)
def registry() -> dict:
    d = json.loads(REGISTRY_PATH.read_text())
    strip = lambda m: {k: v for k, v in m.items() if not k.startswith("_")}  # noqa: E731
    return {"version": d["version"], "cycle": d["cycle"], "roles": strip(d["roles"]),
            "sectors": strip(d["sectors"]), "profiles": strip(d["profiles"]), "engagement": strip(d["engagement"])}


def profile_ids() -> list[str]:
    return sorted(registry()["profiles"])


def resolve(profile_id: Optional[str] = None, overrides: Optional[dict] = None) -> dict:
    """The effective configuration for one regulator: profile + sector expectations + overrides applied.
    overrides = {"profile": ..., "default_scenario": ..., "default_horizon": ...,
                 "thresholds": {"<sector>": {"<metric_id>": {"watch_above": .., "act_above": .., "watch_below": ..}}}}"""
    reg = registry()
    ov = overrides or {}
    pid = ov.get("profile") or profile_id or DEFAULT_PROFILE
    if pid not in reg["profiles"]:
        raise KeyError(f"unknown supervision profile {pid!r}; known: {profile_ids()}")
    prof = deepcopy(reg["profiles"][pid])
    sectors = {}
    for sec in prof["sectors"]:
        s = deepcopy(reg["sectors"][sec])
        for m in s["metrics"]:
            for k, v in (ov.get("thresholds", {}).get(sec, {}).get(m["id"], {}) or {}).items():
                m[k] = v
        sectors[sec] = s
    return {"profile_id": pid, "label": prof["label"], "sectors": sectors, "cycle": reg["cycle"],
            "roles": reg["roles"], "version": reg["version"],
            "default_scenario": ov.get("default_scenario") or prof["default_scenario"],
            "default_horizon": ov.get("default_horizon") or prof["default_horizon"]}


def sector_config(cfg: dict, org_type: str) -> Optional[dict]:
    """Expectations for a supervised entity of this type under the regulator's profile, None if out of profile."""
    return cfg["sectors"].get(org_type)


def role_templates() -> dict:
    return registry()["roles"]


def all_permission_codes() -> list[str]:
    return sorted({p for r in registry()["roles"].values() for p in r["permissions"]})
