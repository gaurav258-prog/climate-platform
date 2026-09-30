"""How every item of an ESRS specification version is filled (family 'esrs': E1, E3, E4), read from the concept
registry data/reference/esrs/concepts.json — nothing about the standards is typed here.

  heading / text              printed as is
  question / choice / table   the undertaking's answer (template answers, per undertaking and period)
  field                       each datapoint through its concept's lane:
                                computed  the platform's engine (physical risk, own sites in sensitive areas)
                                provided  the undertaking's figure, attested by a second person (provided_datapoint)
                                derived   a ratio the application requirements define from other concepts
                                same_as   a summary point whose figures other items report
                              a field whose words also ask for an explanation is answered as well (narrative)

coverage() proves the binding complete for a version: every datapoint bound, no binding to a datapoint the version
does not print, every concept named exists, every derived input and same_as target exists.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "esrs" / "concepts.json"
LANES = ("computed", "provided", "derived")
FIXED = ("heading", "text")
ANSWERED = ("question", "choice", "table")


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads(_REF.read_text())


def concepts() -> dict[str, dict]:
    return registry()["concepts"]


def binding(version: str) -> dict[str, object]:
    """datapoint ref ('<item id>:<datapoint key>') → concept key, or {'same_as': [concept keys]}."""
    b = registry()["bindings"][version]
    return registry()["bindings"][b] if isinstance(b, str) else b      # a version identical to another names it


def datapoints(spec: dict):
    """Every printed datapoint of a version: (template id, item, datapoint)."""
    for t in spec["templates"]:
        for i in t["items"]:
            for d in i.get("datapoints") or []:
                yield t["id"], i, d


def lane_of(spec: dict, item: dict) -> dict:
    """How one item is filled: {'lane': fixed|input|field, 'datapoints': [{key, concept|same_as, lane}], 'narrative'}."""
    if item["kind"] in FIXED:
        return {"lane": "fixed"}
    if item["kind"] in ANSWERED:
        return {"lane": "input"}
    b, cs = binding(spec["version"]), concepts()
    out = []
    for d in item.get("datapoints") or []:
        target = b.get(f"{item['id']}:{d['key']}")
        if isinstance(target, dict):
            out.append({"key": d["key"], "same_as": target["same_as"], "lane": "same_as"})
        else:
            out.append({"key": d["key"], "concept": target, "lane": (cs.get(target) or {}).get("lane")})
    return {"lane": "field", "datapoints": out, "narrative": bool(item.get("narrative"))}


def coverage(spec: dict) -> dict:
    """The binding against every datapoint the version prints (the change route's coverage check)."""
    b, cs = binding(spec["version"]), concepts()
    printed = {f"{i['id']}:{d['key']}" for _, i, d in datapoints(spec)}
    missing = sorted(printed - set(b))
    stale = sorted(set(b) - printed)
    invalid = []
    for ref, target in b.items():
        names = target["same_as"] if isinstance(target, dict) else [target]
        invalid += [f"{ref} → unknown concept '{n}'" for n in names if n not in cs]
    for key, c in cs.items():
        if c.get("lane") not in LANES:
            invalid.append(f"{key}: lane must be one of {LANES}")
        invalid += [f"{key}: derived from unknown '{f}'" for f in c.get("from") or [] if f not in cs]
        if c.get("lane") == "derived" and not c.get("from"):
            invalid.append(f"{key}: a derived concept names what it is derived from")
    return {"framework": "esrs", "version": spec["version"], "complete": not (missing or stale or invalid),
            "missing": missing, "stale": stale, "invalid": invalid, "n_datapoints": len(printed)}


def item_binding(spec: dict) -> dict:
    """The route's generic binding ({template: {"items": {item id: source}}}, services.regspec.coverage): an answered
    item is 'input'; a field is 'computed' when the platform fills every datapoint (computed, derived or reported by
    other items), 'input:provided' when the undertaking supplies at least one. A field with a datapoint the concept
    registry does not bind is left out — the generic coverage then names it missing."""
    out: dict = {}
    for t in spec["templates"]:
        items = {}
        for i in t["items"]:
            if i["kind"] in FIXED:
                continue
            ln = lane_of(spec, i)
            if ln["lane"] == "input":
                items[i["id"]] = "input"
                continue
            lanes = [d["lane"] for d in ln["datapoints"]]
            if not lanes or None in lanes:
                continue
            items[i["id"]] = "input:provided" if "provided" in lanes else "computed"
        out[t["id"]] = {"items": items}
    return out


def concepts_of(spec: dict) -> set[str]:
    """Every concept a version prints (bound directly, through same_as, or as the input of a derived one)."""
    cs, out = concepts(), set()
    for target in binding(spec["version"]).values():
        out |= set(target["same_as"] if isinstance(target, dict) else [target])
    for key in list(out):
        out |= set(cs.get(key, {}).get("from") or [])
    return out


def provided_catalog(spec: dict) -> dict[str, dict]:
    """The undertaking's own figures a version needs: concept → label, unit, period, breakdown, and whether it is only a
    denominator (input_only). What provided_data accepts for an ESRS report under this version."""
    cs = concepts()
    return {k: {"label": cs[k]["label"], "unit": cs[k]["unit"], "period": cs[k].get("period"),
                "breakdown": cs[k].get("breakdown"), "input_only": bool(cs[k].get("input_only")),
                "reconcile": cs[k].get("reconcile")}
            for k in sorted(concepts_of(spec)) if cs[k]["lane"] == "provided"}
