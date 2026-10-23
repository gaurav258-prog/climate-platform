#!/usr/bin/env python3
"""Bind every Pillar 3 ESG template cell (Implementing Regulation (EU) 2024/3172, Annex I section 21, as the platform's
specification captures it) to its datapoint in the EBA's taxonomy for the Pillar 3 data hub (module ESGDIS), read from
the EBA's own package — never typed.

    venv/bin/python -I scripts/build_eba_p3esg_map.py <framework_root> <dictionary_root> <spec.json> <out.json>

framework_root   the unpacked EBA_XBRL_<release>_Reporting_Frameworks package (holds www.eba.europa.eu/...)
dictionary_root  the unpacked EBA_XBRL_<release>_Dictionary package
spec.json        data/reference/regspec/bank_p3esg/<version>.json

For each table of the module (its xBRL-CSV metadata, <table>.json) every datapoint carries its cell code
'{K_41.00, r0010, c0020}'. The row and column are resolved to the specification's row id and column letter from the
EBA's own labels (table linkbase rc-codes + English labels): a label numbered as the ITS prints it ('3. B - Mining…',
'c. Of which…') binds by that number when its wording agrees; a label without the ITS number ('GAR stock') or with a
number the ITS does not print ('0.1 GAR') binds by its wording alone. The template is the table's title ('Template 1').
Open tables (rows keyed by code lists or text: Templates 3, 5, 10) bind their columns, and their key columns with the
code-list members and the members' labels. Everything that does not pair up — an ITS cell with no datapoint, a datapoint
with no ITS cell, wording that differs — is recorded, not dropped. A rebuild keeps what the output already records about
the packages it was built from, their licence, the validation and the declared readings.
"""
from __future__ import annotations

import difflib
import glob
import json
import os
import re
import sys

from lxml import etree

XL = "{http://www.w3.org/1999/xlink}"
T = "http://xbrl.org/2014/table"
RC = "http://www.eurofiling.info/xbrl/role/rc-code"
FW = "www.eba.europa.eu/eu/fr/xbrl/crr/fws/pillar3"


def _labels(path: str, role: str | None = None) -> dict:
    out = {}
    root = etree.parse(path).getroot()
    locs = {loc.get(XL + "label"): loc.get(XL + "href").split("#")[1]
            for loc in root.iter("{http://www.xbrl.org/2003/linkbase}loc")}
    res = {r.get(XL + "label"): r for r in root.iter() if r.tag.endswith("}label") and r.get(XL + "type") == "resource"}
    for a in root.iter():
        if a.get(XL + "type") == "arc" and a.get(XL + "from") in locs and a.get(XL + "to") in res:
            r = res[a.get(XL + "to")]
            if role is None or r.get(XL + "role") == role:
                out.setdefault(locs[a.get(XL + "from")], r.text)
    return out


def axes(tdir: str) -> dict:
    """{axis: {rc-code: label}} of a table, from its table linkbase."""
    tid = os.path.basename(tdir)
    rend = etree.parse(os.path.join(tdir, tid + "-rend.xml")).getroot()
    codes = _labels(os.path.join(tdir, tid + "-lab-codes.xml"), RC)
    en = _labels(os.path.join(tdir, tid + "-lab-en.xml"))
    ids = {el.get(XL + "label"): el.get("id") for el in rend.iter() if el.get(XL + "label") and el.get("id")}
    kids: dict[str, list] = {}
    axis = {a.get(XL + "to"): a.get("axis") for a in rend.iter("{%s}tableBreakdownArc" % T)}
    for tag in ("breakdownTreeArc", "definitionNodeSubtreeArc"):
        for a in rend.iter("{%s}%s" % (T, tag)):
            kids.setdefault(a.get(XL + "from"), []).append((float(a.get("order") or 0), a.get(XL + "to")))
    out: dict[str, dict] = {"x": {}, "y": {}, "z": {}}
    paths: dict[str, dict] = {"x": {}, "y": {}, "z": {}}

    def walk(lbl, ax, above):
        nid = ids.get(lbl)
        here = (en.get(nid) or "").strip()
        if codes.get(nid):
            out[ax][codes[nid]] = here
            paths[ax][codes[nid]] = " > ".join([*above, _split(here)[1]] if here else above)
        for _, k in sorted(kids.get(lbl, [])):
            walk(k, ax, [*above, _split(here)[1]] if here else above)
    for bd, ax in axis.items():
        for _, k in sorted(kids.get(bd, [])):
            walk(k, ax, [])
    title = next((v for k, v in en.items() if k.startswith("eba_t")), "")
    return {**out, "paths": paths, "title": title}


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("–", "-").replace("ccovered", "covered")
    s = re.sub(r"\(in mn eur\)|\(mln eur\)|\(mn eur\)|\(in meur\)|\(million eur\)", "", s)
    s = re.sub(r"[*]+", "", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def _split(label: str) -> tuple[str | None, str]:
    """'3. B - Mining' → ('3', 'B - Mining'); 'c. Of which' → ('c', 'Of which'); '0.1 GAR' → ('0.1', 'GAR')."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?|[a-z]{1,2})\.?\s+(.*)$", label)
    if m and (m.group(1)[0].isdigit() or label.strip()[len(m.group(1))] == "."):
        return m.group(1), m.group(2)
    return None, label


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


_CACHE: dict = {}
_HEADING = re.compile(r"h\d+")                                  # a heading row of the spec ('h1'), never a column 'h'


def _resolve(label: str, path: str, items: list[dict]) -> tuple[str | None, str, float]:
    """The spec item an EBA header names: (id, how, wording similarity).

    A candidate agrees in wording with the EBA header (its last part). When the ITS number on the EBA label names a
    candidate whose wording no other item shares, that number binds. Where several items share the wording ('Of which
    non-performing exposures' under gross amount and under impairment), the group each sits in decides: the last part
    of its ITS label before the leaf must be among the EBA header's parent groups, and the item whose ITS parent groups
    are closest to the EBA path wins, then the closest wording (the number breaks a tie). When the number names none of the best (EBA's
    '0.1 GAR', or a letter EBA mislabels) the single best binds by wording."""
    key = (label, path, id(items))
    if key in _CACHE:
        return _CACHE[key]
    num, text = _split(label)
    above = [a for a in path.split(" > ")[:-1] if a.strip()]

    def leaf(i):
        if not i["label"] and i.get("unlabelled"):
            return 1.0
        return max(_similar(text, i["label"].split(" > ")[-1]), _similar(text, i["label"]))

    def parents(i):
        parts = i["label"].split(" > ")[:-1]
        if not parts:
            return 1.0
        if not above:                                          # a top-level EBA header: no group to compare
            return 0.0
        close = [max(_similar(p, a) for a in above) for p in parts]
        return sum(close) / len(close) if close[-1] >= 0.85 else -1.0
    items = [i for i in items if not _HEADING.fullmatch(i["id"])]
    by_id = {i["id"]: i for i in items}
    if num in by_id and leaf(by_id[num]) >= 0.8 and not any(
            i["id"] != num and leaf(i) >= leaf(by_id[num]) - 0.02 for i in items):
        _CACHE[key] = (num, "number", round(leaf(by_id[num]), 3))
        return _CACHE[key]
    agree = [((round(parents(i), 4), round(leaf(i), 4)), i) for i in items if leaf(i) >= 0.8]
    agree = [(sc, i) for sc, i in agree if sc[0] >= 0]
    best = max((sc for sc, _ in agree), default=None)
    top = [i for sc, i in agree if sc == best]
    by_num = next((i for i in top if i["id"] == num), None)
    if by_num is not None:
        out = (num, "number", round(leaf(by_num), 3))
    elif len(top) == 1 and leaf(top[0]) >= 0.9:
        differs = num is not None and any(i["id"] == num for i in items)
        out = (top[0]["id"], "wording (EBA label number differs)" if differs else "wording", round(leaf(top[0]), 3))
    else:
        out = (None, "ambiguous" if len(top) > 1 else "unmatched", 0.0)
    _CACHE[key] = out
    return out


def main(fw_root: str, dict_root: str, spec_path: str, out_path: str) -> None:
    spec = json.load(open(spec_path))
    by_code = {t["code"]: t for t in spec["templates"]}
    fw = os.path.join(fw_root, FW)
    release = os.path.basename(sorted(glob.glob(os.path.join(fw, "*", "mod", "esgdis.json")))[-1].split("/mod/")[0])
    mod_path = os.path.join(fw, release, "mod", "esgdis.json")
    mod = json.load(open(mod_path))
    doc = mod["documentInfo"]["eba:documentation"]
    members = {}
    for p in glob.glob(os.path.join(dict_root, "www.eba.europa.eu/eu/fr/xbrl/crr/dict/dom", "*")):
        if os.path.isdir(p):
            dom = os.path.basename(p).upper()
            for f in glob.glob(os.path.join(p, "**", "mem-lab-en.xml"), recursive=True):
                for k, v in _labels(f).items():
                    members.setdefault(f"eba_{dom}:{k[len('eba_'):]}", v)

    tables, cells, open_cells, problems, wording = {}, {}, {}, [], []
    seen_its: set[str] = set()
    for ref in mod["documentInfo"]["extends"]:
        if not ref.startswith(".."):
            continue
        meta = os.path.normpath(os.path.join(os.path.dirname(mod_path), ref))
        tdir = os.path.dirname(meta)
        code = os.path.basename(tdir).upper()                       # 'K_41.00', 'K_42.00.A'
        code = code[:-2] + code[-2:].lower() if re.search(r"\.[A-Z]$", code) else code
        ax = axes(tdir)
        md = json.load(open(meta))
        (tt_name, tt), = md["tableTemplates"].items()
        indicator = re.match(r"K_\d+\.\d+", code).group(0)
        tmpl_code = re.search(r"(Template \d+(?:\.\d+)?)", ax["title"])
        tmpl = by_code.get(tmpl_code.group(1)) if tmpl_code else None
        keys = []
        for name, col in tt["columns"].items():
            if name in ("datapoint", "factValue"):
                continue
            d = col.get("eba:documentation", {})
            keys.append({"name": name, "header": d.get("headerCode"), "axis": d.get("headerDirection"), "type": d.get("type"),
                         "constraints": col.get("tc:constraints"),
                         "allowed": {m: members.get(m) for m in sorted(d.get("AllowedValue") or {})} or None})
        rel = os.path.relpath(meta, os.path.join(fw_root, "www.eba.europa.eu")).replace(os.sep, "/")
        tables[code] = {"csv": os.path.basename(tdir) + ".csv", "metadata": "http://www.eba.europa.eu/" + rel,
                        "table_template": tt_name, "indicator": indicator, "title": ax["title"],
                        "template": tmpl["id"] if tmpl else None, "keys": keys}
        if tmpl is None:                                            # K_00.03: the accompanying narrative, per template
            for dp, v in tt["columns"]["datapoint"]["propertyGroups"].items():
                r = re.match(r"\{[^,]+, r(\w+|\*), c(\w+)", v["eba:documentation"]["cellcode"]).group(1)
                about = re.search(r"(Template \d+(?:\.\d+)?)", ax["y"].get(r, ""))
                t = by_code.get(about.group(1)) if about else None
                cells[f"NARRATIVE|{t['id'] if t else r}"] = {"table": code, "dp": dp, "type": v["eba:documentation"]["type"],
                                                             "eba": v["eba:documentation"]["cellcode"]}
            continue
        for dp, v in tt["columns"]["datapoint"]["propertyGroups"].items():
            d = v["eba:documentation"]
            m = re.match(r"\{([^,]+), r(\w+|\*), c(\w+)(?:, s\*)?\}", d["cellcode"])
            r, c = m.group(2), m.group(3)
            cid, chow, csim = _resolve(ax["x"].get(c, ""), ax["paths"]["x"].get(c, ""), tmpl["columns"])
            entry = {"table": code, "dp": dp, "type": d["type"], "concept": v["dimensions"]["concept"],
                     "decimals": (v.get("decimals") or "").lstrip("$") or None, "eba": d["cellcode"]}
            if cid is None:
                problems.append({"eba": d["cellcode"], "why": "column label names no ITS column", "label": ax["x"].get(c)})
                continue
            if r == "*":                                            # an open table: rows keyed by its key columns
                open_cells[f"{code}|{cid}"] = {**entry, "template": tmpl["id"]}
                seen_its.add(f"{tmpl['id']}|*|{cid}")
                continue
            rid, rhow, rsim = _resolve(ax["y"].get(r, ""), ax["paths"]["y"].get(r, ""), tmpl["rows"])
            if rid is None:
                problems.append({"eba": d["cellcode"], "why": "row label names no ITS row", "label": ax["y"].get(r)})
                continue
            key = f"{tmpl['id']}|{rid}|{cid}"
            if key in cells:
                problems.append({"eba": d["cellcode"], "why": f"ITS cell {key} already bound to {cells[key]['eba']}"})
                continue
            cells[key] = entry
            seen_its.add(key)
            for what, how, sim, lab, its in (("row", rhow, rsim, ax["y"].get(r), rid), ("column", chow, csim, ax["x"].get(c), cid)):
                if how != "number" or sim < 1:
                    wording.append({"eba": d["cellcode"], what: its, "how": how, "similarity": sim, "eba_label": lab})
    # every ITS cell of a bound template that has no datapoint
    unbound = []
    bound_tmpl = {t["template"] for t in tables.values() if t["template"]}
    for tid in sorted(bound_tmpl):
        t = next(x for x in spec["templates"] if x["id"] == tid)
        open_cols = {k.split("|")[1] for k, e in open_cells.items() if e["template"] == tid}
        for row in t["rows"]:
            if _HEADING.fullmatch(row["id"]):                   # a heading row prints no cell
                continue
            for col in t["columns"]:
                k = f"{tid}|{row['id']}|{col['id']}"
                if k not in seen_its and col["id"] not in open_cols:
                    unbound.append(k)
    # the row keys of the open tables whose ITS rows are fixed: Template 3's IEA sectors, Template 10's instrument and
    # counterparty — each ITS row bound to the code-list member that names it (EBA's labels; elimination recorded)
    row_keys, key_notes = {}, []

    def members_of(table, key):
        return next(k["allowed"] for k in tables[table]["keys"] if k["name"] == key)
    t3 = next(x for x in spec["templates"] if x["id"] == "T3")
    for row in t3["rows"]:
        hit = [m for m, lab in members_of("K_43.00.a", "IEA").items() if _split(lab)[0] == row["id"]
               and _similar(_split(lab)[1], row["label"]) >= 0.9]
        if len(hit) == 1:
            row_keys.setdefault("T3", {})[row["id"]] = {"table": "K_43.00.a", "IEA": hit[0]}
        else:
            row_keys.setdefault("T3", {})[row["id"]] = {"table": "K_43.00.b", "IES": "text"}
            key_notes.append({"its": f"T3 row {row['id']}", "how": "no IEA sector member names it: the open part "
                              "K_43.00.b (sector and NACE as text)"})
    t10 = next(x for x in spec["templates"] if x["id"] == "T10")
    mcy, ctn = members_of("K_50.00", "MCY"), members_of("K_50.00", "CTN")
    for row in t10["rows"]:
        parts = row["label"].split(" > ")
        instr = [m for m, lab in mcy.items() if parts[0].split(" (")[0].strip().lower() == lab.lower()]
        cp_text = ", ".join(p[0].lower() + p[1:] if i else p for i, p in enumerate(parts[1:]))
        ranked = sorted(ctn, key=lambda m: _similar(cp_text, ctn[m]), reverse=True)    # 'Financial' ≠ 'Non-financial'
        cp = [m for m in ranked[:1] if _similar(cp_text, ctn[m]) >= 0.9
              and _similar(cp_text, ctn[m]) > _similar(cp_text, ctn[ranked[1]])]
        row_keys.setdefault("T10", {})[row["id"]] = {"table": "K_50.00", "MCY": instr[0] if len(instr) == 1 else None,
                                                     "CTN": cp[0] if len(cp) == 1 else None, "_cp": cp_text}
    for group in ({r for r, k in row_keys["T10"].items() if k["MCY"] == m} for m in mcy):
        left_rows = [r for r in group if not row_keys["T10"][r]["CTN"]]
        if len(left_rows) == 1:
            options = [m for m in ctn if m not in {row_keys["T10"][r]["CTN"] for r in group if row_keys["T10"][r]["CTN"]}
                       and not any(_similar(k["_cp"], ctn[m]) >= 0.9 for k in row_keys["T10"].values())]
            if len(options) == 1:
                row_keys["T10"][left_rows[0]]["CTN"] = options[0]
                key_notes.append({"its": f"T10 row {left_rows[0]} '{row_keys['T10'][left_rows[0]]['_cp']}'",
                                  "how": f"by elimination: {options[0]} '{ctn[options[0]]}' is the only counterparty "
                                         "member that no row of the template names"})
    for k in row_keys["T10"].values():
        k.pop("_cp")
    unkeyed = [f"T10 row {r}" for r, k in row_keys["T10"].items() if not (k["MCY"] and k["CTN"])]
    key_notes += [{"its": u, "how": "no member names it"} for u in unkeyed]
    wording_unique = {(w["eba"].split(",")[0], w.get("row"), w.get("column"), w["how"], w["eba_label"]): w for w in wording}
    out = {
        "_source": (f"EBA taxonomy for the Pillar 3 data hub, release {release} (module ESGDIS), read from the EBA's package by "
                    "scripts/build_eba_p3esg_map.py: each datapoint's cell code from the table metadata, its row and column "
                    "from the table linkbase labels, bound to the ITS cells of " + os.path.basename(spec_path)),
        "framework_release": release,
        "module": {"code": "ESGDIS", "framework_code": "PILLAR3", "version": doc["ModuleVersion"],
                   "file_module_version": "".join(f"{int(p):02d}" for p in doc["ModuleVersion"].split(".")),
                   "entry": f"http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/pillar3/{release}/mod/esgdis.json",
                   "applies": {"from": doc["FromReferenceDate"], "until": doc["toReferenceDate"] or None,
                               "basis": "reference date",
                               "quote": f"FromReferenceDate {doc['FromReferenceDate']}, toReferenceDate "
                                        f"'{doc['toReferenceDate']}' (esgdis.json eba:documentation)"},
                   "parameters": sorted(mod.get("parameters", {}).keys() | {"entityID", "refPeriod", "baseCurrency",
                                                                            "decimalsMonetary", "decimalsPercentage",
                                                                            "decimalsInteger", "decimalsDecimal"})},
        "spec": {"family": spec["framework"], "version": spec["version"]},
        "indicators": sorted({t["indicator"] for t in tables.values()}),
        "tables": tables,
        "cells": dict(sorted(cells.items())),
        "open_cells": dict(sorted(open_cells.items())),
        "row_keys": row_keys,
        "differences": {"its_cells_without_datapoint": unbound, "datapoints_not_bound": problems,
                        "bound_by_wording_or_differing_wording": sorted(wording_unique.values(), key=lambda w: w["eba"]),
                        "row_keys": key_notes},
        "counts": {"tables": len(tables), "cells": len(cells), "open_cells": len(open_cells),
                   "its_cells_without_datapoint": len(unbound), "datapoints_not_bound": len(problems)},
    }
    if os.path.exists(out_path):                                # kept across rebuilds: what was fetched and decided
        kept = json.load(open(out_path))
        out.update({k: kept[k] for k in ("packages", "licence", "validation", "readings") if k in kept})
    json.dump(out, open(out_path, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(out["counts"]))


if __name__ == "__main__":
    main(*sys.argv[1:5])
