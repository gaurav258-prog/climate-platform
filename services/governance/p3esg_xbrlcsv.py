"""Pillar 3 ESG as the EBA's xBRL-CSV report package for the Pillar 3 data hub (module ESGDIS of the EBA taxonomy).

Every template cell is bound to its EBA datapoint in data/reference/eba/p3esg_xbrlcsv.<release>.json, read from the
EBA's own package by scripts/build_eba_p3esg_map.py (each datapoint's cell code and the table's labels; nothing typed
here). The module is chosen by the reference date (its FromReferenceDate / toReferenceDate). Implementing Regulation
(EU) 2026/722 amends Implementing Regulation (EU) 2024/3172 for institutions' use of the EBA's single access point
for their disclosures; the package follows the EBA Filing Rules v5.8 for xBRL-CSV (file naming, report package,
parameters, a filing indicator for every template of the module).

The package is rendered from the FROZEN filing: the templates are rebuilt from its frozen book, specification and
supplied values with the builders the form uses (pillar3_grids, pillar3_gar, pillar3_other, pillar3_t1) — never a
live rebuild. Values take the EBA's type of their datapoint: amounts in the presentation currency to the unit,
percentages as ratios to four decimals, integers rounded half to even (EBA rule 2.18). A cell the platform leaves
blank has no fact (the EBA has no other way to say it — rule 1.7: in a template indicated as reported such a cell may
be read as zero); a template without any figure is indicated as not reported. What is left out, and why, is listed in
the summary returned with the file.
"""
from __future__ import annotations

import csv
import glob
import io
import json
import os
import re
import zipfile
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from functools import lru_cache

from core.errors import UserError

_DIR = os.path.join("data", "reference", "eba")
_DECIMALS = {"m": ("decimalsMonetary", "0"), "p": ("decimalsPercentage", "4"), "i": ("decimalsInteger", "0"),
             "r": ("decimalsDecimal", "2")}
_LEVEL = {"solo": "IND", "consolidated": "CON"}          # EBA Filing Rules v5.8, 'Reporting subject': LEI + .IND / .CON


class XbrlCsvError(UserError, ValueError):
    """Why the package cannot be produced: a message-catalogue code with its values."""


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def map_for(reference_date: date) -> dict:
    """The binding whose EBA module applies to the reference date."""
    d = reference_date.isoformat()
    found = []
    for path in sorted(glob.glob(os.path.join(_DIR, "p3esg_xbrlcsv.*.json"))):
        m = _load(path)
        a = m["module"]["applies"]
        found.append(m)
        if a["from"] <= d and (a["until"] is None or d <= a["until"]):
            return m
    first = min((m["module"]["applies"]["from"] for m in found), default="—")
    raise XbrlCsvError("filing.refused.xbrlcsv_reference_date", date=d, start=first)


def _num(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def fact_value(kind: str, v) -> str | None:
    """A value in the lexical form of its EBA type (m amount, p percentage → ratio, i integer, r decimal, s string)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if kind == "m":
        return str(_num(v).quantize(Decimal(1), ROUND_HALF_EVEN))
    if kind == "p":
        return format((_num(v) / 100).quantize(Decimal("0.0001"), ROUND_HALF_EVEN).normalize(), "f")
    if kind == "i":
        return str(_num(v).quantize(Decimal(1), ROUND_HALF_EVEN))
    if kind == "r":
        return format(_num(v).normalize(), "f")
    if kind in ("s", "e"):
        return str(v).strip()
    raise ValueError(f"no lexical rule for EBA type {kind!r}")


def _nace_member(allowed: dict, digits: str) -> str | None:
    """The EBA NACE member whose label code is the Annex XL code ('0811' ↔ 'B8.11 - …'; EBA spacing varies)."""
    for member, lab in allowed.items():
        mm = re.match(r"\s*([A-U])(\d+)(?:\.(\d+))?\s*-", lab or "")
        if mm and mm.group(2).zfill(2) + (mm.group(3) or "") == digits:
            return member
    return None


def _keys(table: dict) -> list[dict]:
    """Key columns in the order the EBA lays them out: row-axis keys by header code, then the sheet axis."""
    return sorted(table["keys"], key=lambda k: (k["axis"] == "Z", k["header"] or ""))


def template_values(payload: dict) -> dict:
    """The templates of a frozen filing as its form prints them: {'cells': {'T1|1|a': v}, 'T3': {...}, 'T5': [...],
    'T10': {...}, 'narrative': {...}, 'gaps': [...]} — built with the form's own builders."""
    from services.governance import pillar3_gar, pillar3_other
    from services.governance import pillar3_grids as G
    from services.governance.filing_annex import _p3_spec, _period_end, _supplied
    from services.governance.pillar3_t1 import RECORD, narrative_lines
    from services.governance.pillar3_templates import stated_level
    spec, assets = _p3_spec(payload), (payload or {}).get("assets") or []
    if not assets:
        raise XbrlCsvError("filing.refused.xbrlcsv_no_book")
    supplied, period_end, gaps = _supplied(payload), _period_end(payload), []
    cells: dict[str, object] = {}

    def put(tid, rows, gross_only=False):
        for rid, row in rows.items():
            for col, v in (row or {}).items():
                if not col.startswith("_") and not (gross_only and row.get("_gross_only") and col != "a"):
                    cells[f"{tid}|{rid}|{col}"] = v
    put("T1", {r["id"]: r["values"] for r in G.build(spec, "T1", assets, t1=payload.get(RECORD))["rows"]})
    gar = pillar3_gar.build(spec, assets, period_end)
    for tid in ("T2", "T6", "T7", "T8", "T9_1", "T9_2", "T9_3"):
        put(tid, gar[tid], gross_only=tid in ("T7", "T9_1"))
    put("T4", pillar3_other.template4_values(assets))
    t3 = pillar3_other.template3_values(spec, assets, period_end.year)
    for rid in t3:
        for sub in t3[rid]:
            sub["g"] = supplied.get(f"T3.{rid}.g")
    level, geos = stated_level(payload), []
    if level is None:
        gaps.append({"template": "T5", "why": "the at-risk threshold is not stated"})
    else:
        geos = G.template5(spec, assets, level)["geographies"]
    t10 = {str(i): {c: supplied.get(f"T10.{i}.{c}") for c in "cdef"} for i in range(1, 12)}
    rec = payload.get(RECORD)
    narrative = {"T1": " | ".join(narrative_lines(rec))} if rec is not None and narrative_lines(rec) else {}
    return {"spec": spec["version"], "cells": cells, "T3": t3, "T5": geos, "T10": t10, "narrative": narrative,
            "period_end": period_end, "gaps": gaps}


def facts(m: dict, tv: dict) -> tuple[dict[str, list[dict]], dict]:
    """{table code: [{dp, value, keys}]} and what was left out — every value placed by the binding, never by name."""
    out: dict[str, list[dict]] = {}
    left = {"not_in_eba_model": [], "named_gaps": [], "unknown_member": []}
    gap_cells = {k.split("|")[0] + "|" + k.split("|")[1] for k, r in m.get("readings", {}).items()
                 if r.get("status", "").startswith("not bound")}

    def add(entry, value, keys=None):
        lex = fact_value(entry["type"], value)
        if lex is not None:
            out.setdefault(entry["table"], []).append({"dp": entry["dp"], "value": lex, "type": entry["type"],
                                                       "keys": keys or {}})
    for key, v in tv["cells"].items():
        tid, rid, col = key.split("|")
        if f"{tid}|{col}" in gap_cells:
            if v is not None:
                left["named_gaps"].append(key)
            continue
        entry = m["cells"].get(key)
        if entry is None:
            if v not in (None, 0, 0.0):
                left["not_in_eba_model"].append(key)
            continue
        add(entry, v)
    rk = m["row_keys"]
    nac3 = next(k["allowed"] for k in m["tables"]["K_43.00.a"]["keys"] if k["name"] == "NAC")
    for rid, subs in tv["T3"].items():
        for sub in subs:
            member = _nace_member(nac3, sub["nace"])
            if member is None:
                left["unknown_member"].append(f"T3 row {rid} NACE {sub['b']}")
                continue
            keys = {"IEA": rk["T3"][rid]["IEA"], "NAC": member, "ALG": sub["metric"]}
            for col, v in (("c", sub["c"]), ("e", sub["value"]), ("f", sub["f"]), ("g", sub["g"])):
                add(m["open_cells"][f"K_43.00.a|{col}"], v, keys)
    nac5 = next(k["allowed"] for k in m["tables"]["K_45.00.b"]["keys"] if k["name"] == "NAC")
    for geo in tv["T5"]:
        gpr = geo["label"]
        for row in geo["rows"]:
            for col, v in row["values"].items():
                entry = m["cells"].get(f"T5|{row['id']}|{col}")
                if entry is not None:
                    add(entry, v, {"GPR": gpr})
            for part in row.get("breakdown") or []:
                member = f"eba_NC:{part['section']}" if f"eba_NC:{part['section']}" in nac5 else None
                if member is None:
                    left["unknown_member"].append(f"T5 row {row['id']} section {part['section']}")
                    continue
                for col, v in part["values"].items():
                    entry = m["open_cells"].get(f"K_45.00.b|{col}")
                    if entry is not None:
                        add(entry, v, {"NAC": member, "GPR": gpr})
    for rid, vals in tv["T10"].items():
        keys = {"MCY": rk["T10"][rid]["MCY"], "CTN": rk["T10"][rid]["CTN"]}
        if any(v is not None for v in vals.values()):
            for col, v in vals.items():
                add(m["open_cells"][f"K_50.00|{col}"], v, keys)
    for tid, text_ in tv["narrative"].items():
        entry = m["cells"].get(f"NARRATIVE|{tid}")
        if entry is not None:
            add(entry, text_)
    return out, left


def _csv(header: list[str], rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")       # OIM CSV quoting: a comma, quote or line break is quoted
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def package(payload: dict, identity: dict, *, role: str | None, country: str, created: datetime) -> tuple[str, bytes, dict]:
    """(file name, the zipped report package, summary) for a frozen bank_p3esg filing. Refused, in this order: a reference
    date no EBA module on file covers, a filing that does not say individual or consolidated, an entity identified by an
    identifier not its own (identity['own_lei'] False), another template version, a filing frozen without its exposures."""
    from services.governance.filing_annex import _p3_spec, _period_end
    m = map_for(_period_end(payload))
    level = _LEVEL.get(role or "")
    if level is None:
        raise XbrlCsvError("filing.refused.xbrlcsv_level")
    if not identity.get("own_lei", True):
        raise XbrlCsvError("filing.refused.xbrlcsv_entity_lei", name=identity.get("entity") or "The filing entity")
    if _p3_spec(payload)["version"] != m["spec"]["version"]:
        raise XbrlCsvError("filing.refused.xbrlcsv_spec", version=_p3_spec(payload)["version"])
    tv = template_values(payload)
    by_table, left = facts(m, tv)
    mod = m["module"]
    subject = f"{identity['lei']}.{level}"
    stamp = created.strftime("%Y%m%d%H%M%S") + f"{created.microsecond // 1000:03d}"
    root = f"{subject}_{country.upper()}_{mod['framework_code']}{mod['file_module_version']}_{mod['code']}_{tv['period_end'].isoformat()}_{stamp}"
    used = {f["type"] for rows in by_table.values() for f in rows}
    params = [["entityID", f"rs:{subject}"], ["refPeriod", tv["period_end"].isoformat()]]
    if "m" in used:
        params.append(["baseCurrency", f"iso4217:{identity['currency']}"])
    params += [list(_DECIMALS[t]) for t in sorted(used) if t in _DECIMALS]
    reported = {ind: any(m["tables"][t]["indicator"] == ind for t in by_table) for ind in m["indicators"]}
    files = {"META-INF/reportPackage.json": json.dumps({"documentInfo": {"documentType": "https://xbrl.org/report-package/2023"}},
                                                       indent=2).encode(),
             "reports/report.json": json.dumps({"documentInfo": {"documentType": "https://xbrl.org/2021/xbrl-csv",
                                                                 "extends": [mod["entry"]]}}, indent=4).encode(),
             "reports/parameters.csv": _csv(["name", "value"], params),
             "reports/FilingIndicators.csv": _csv(["templateID", "reported"],
                                                  [[ind, "true" if ok else "false"] for ind, ok in sorted(reported.items())])}
    for code, rows in sorted(by_table.items()):
        t = m["tables"][code]
        keys = [k["name"] for k in _keys(t)]
        body = sorted([[f["dp"], f["value"], *[f["keys"][k] for k in keys]] for f in rows])
        files[f"reports/{t['csv']}"] = _csv(["datapoint", "factValue", *keys], body)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(f"{root}/{name}", date_time=created.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    summary = {"file": f"{root}.zip", "module": f"{mod['code']} {mod['version']}", "release": m["framework_release"],
               "facts": {ind: sum(len(r) for c, r in by_table.items() if m["tables"][c]["indicator"] == ind)
                         for ind in m["indicators"]},
               "not_reported": sorted(ind for ind, ok in reported.items() if not ok), "left_out": left, "gaps": tv["gaps"]}
    return f"{root}.zip", buf.getvalue(), summary
