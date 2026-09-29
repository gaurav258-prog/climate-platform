"""The EU acts CRCS watches, per framework: every adopted template specification's act (automatically) plus the acts in
data/reference/crcs/tracked_acts.json that no specification covers yet. One source for the register scans, version
pinning and the version register — nothing typed in code.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "crcs" / "tracked_acts.json"


@lru_cache(maxsize=1)
def _acts() -> dict[str, list[dict]]:
    import services.regspec as R
    out: dict[str, list[dict]] = {}
    for fw in R.frameworks():                                  # every adopted spec's act, oldest first
        for s in R.versions(fw):
            cx = s["act"].get("celex")
            if s["status"] == "adopted" and cx and cx not in {a["celex"] for a in out.get(fw, [])}:
                out.setdefault(fw, []).append({"celex": cx, "title": s["act"].get("short") or s["act"]["title"],
                                               "role": "base", "spec": s["version"]})
    # a report type watches the acts of every specification family that governs it (regspec_usage.json), so a filing
    # asking by its report type (sfdr_periodic, bank_tcfd, reit_taxonomy) sees the same acts as the family
    for rt in R.report_types():
        for fam in R.families_for(rt):
            for a in out.get(fam, []) if fam != rt else []:
                if a["celex"] not in {x["celex"] for x in out.get(rt, [])}:
                    out.setdefault(rt, []).append(a)
    for fw, acts in json.loads(_FILE.read_text())["frameworks"].items():
        for a in acts:
            if a["celex"] not in {x["celex"] for x in out.get(fw, [])}:
                out.setdefault(fw, []).append(a)
    return out


def framework_celex() -> dict[str, list[str]]:
    return {fw: [a["celex"] for a in acts] for fw, acts in _acts().items()}


def act_meta(celex: str) -> dict:
    """{title, role} of a watched act (the first framework that lists it)."""
    for acts in _acts().values():
        for a in acts:
            if a["celex"] == celex:
                return {"title": a["title"], "role": a.get("role", "base")}
    return {"title": celex, "role": "base"}
