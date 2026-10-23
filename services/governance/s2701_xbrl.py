"""S.27.01.01 (natural catastrophe risk) — or a group's S.27.01.04 — as an XBRL instance in EIOPA's Solvency II
taxonomy: the part of the undertaking's or group's annual quantitative reporting this platform computes.

Every cell's XBRL representation — the metric, its data type and the dimension members of its table — is read from
data/reference/eiopa/s2701_xbrl.<taxonomy>.json (solo: S.27.01.01 under the annual solo entry point ars) or
s2704_xbrl.<taxonomy>.json (group: S.27.01.04 under the annual group entry point arg, each cell with the group members
'method of consolidation' and 'entities under consolidation'), parsed from EIOPA's own table linkbase and cross-checked
against EIOPA's annotated templates (0 disagreements). The template is the one the filing froze (s2701.tid_of); the
taxonomy is chosen by the reporting reference date. The instance follows EIOPA's XBRL Filing Rules: one absolute
schemaRef to the entry point, the entity's LEI (scheme http://standards.iso.org/iso/17442), one instant, one ISO 4217
unit, @decimals only, no nil or duplicate fact, a cell with nothing to report omitted, one filing indicator 'S.27.01' on
a context without dimensions.

A group's S.27.01.04 is produced only on its frozen group-solvency method (services.governance.group_solvency): method 1,
or a combination (the method-1 part). Method 2 exclusively (the template does not apply), a method not stated, or a
method-1 undertaking held through a method-2 one is refused with its reason (a catalogue code).

It is the S.27.01 contribution to the annual submission, not the whole submission: the module also requires S.01.01
(content of the submission) and S.01.02 (basic information), and the other templates, which the QRT package holds. The
instance says so.
"""
from __future__ import annotations

import json
import os
from datetime import date
from functools import lru_cache
from xml.sax.saxutils import escape

_DIR = os.path.join("data", "reference", "eiopa")
_LEI_SCHEME = "http://standards.iso.org/iso/17442"


class XbrlError(ValueError):
    """Why no instance is produced; `code` and `params`, where set, are a catalogue message (filing.refused.*)."""

    def __init__(self, message: str, code: str | None = None, **params):
        super().__init__(message)
        self.code, self.params = code, params


_MAPS = {"S2701": "s2701_xbrl", "S2704": "s2704_xbrl"}       # template → its map files (s2701.TID / GROUP_TID)


@lru_cache(maxsize=8)
def _load(version: str, prefix: str = "s2701_xbrl") -> dict:
    with open(os.path.join(_DIR, f"{prefix}.{version}.json")) as f:
        return json.load(f)


def taxonomy_for(reference_date: date, tid: str = "S2701") -> dict:
    """The EIOPA taxonomy map of a template that applies to a reporting reference date."""
    d = reference_date.isoformat()
    prefix = _MAPS[tid]
    for name in sorted(f for f in os.listdir(_DIR) if f.startswith(prefix + ".") and f.endswith(".json")):
        m = _load(name[len(prefix) + 1:-len(".json")], prefix)
        a = m["applies"]
        if a["from"] <= d and (a["until"] is None or d <= a["until"]):
            return m
    raise XbrlError(f"no EIOPA Solvency II taxonomy on file applies to the reference date {d}")


def _simplification_codes(text: str | None) -> str | None:
    """R0002/C0001 as the codes BV653 accepts: '1,2,4' (ascending), or '9' when no simplification is used."""
    if not text:
        return None
    codes = sorted({part.split("–")[0].strip() for part in text.split(";") if part.strip()}, key=lambda c: int(c))
    return ",".join(codes)


def _value(cell: dict, v, m: dict):
    """(lexical value, unit id, decimals) for a fact of the cell's data type."""
    t = cell["datatype"]
    if t == "xbrli:monetaryItemType":
        return f"{round(float(v))}", "uCCY", "0"
    if t.endswith("percentItemType"):
        return f"{float(v):.6f}", "uPURE", "6"          # a ratio (0.000720), at least 4 decimals (S.2.18.(e))
    if t.startswith("enum:"):
        member = m["enumerations"]["scenario"].get(str(v))
        if member is None:
            raise XbrlError(f"'{v}' is not a scenario the taxonomy enumerates")
        return member, None, None
    return escape(str(v)), None, None


def group_refusal(payload: dict, role: str | None = None) -> XbrlError | None:
    """Why a group filing has no S.27.01.04 instance, or None. A group filing (role 'consolidated') frozen before its
    group-solvency method was recorded is refused too: its book was not limited to the method-1 part."""
    st = (payload or {}).get("_group_solvency")
    if st is None:
        if role == "consolidated":
            return XbrlError("a group filing frozen before its group-solvency method was recorded",
                             "filing.refused.xbrl_group_refresh")
        return None
    if st["status"] == "no_related":
        return XbrlError("no related undertaking with a consolidated book", "filing.refused.xbrl_group_no_related",
                         group=st["group_name"])
    if st["status"] == "not_stated":
        return XbrlError(f"method not stated for {', '.join(st['not_stated'])}", "filing.refused.xbrl_group_not_stated",
                         undertakings=", ".join(st["not_stated"]))
    if st["status"] == "nested":
        x = st["nested"][0]
        return XbrlError(f"{x['undertaking']} (method 1) is held through {x['held_through']} (method 2)",
                         "filing.refused.xbrl_group_nested", undertaking=x["undertaking"], held_through=x["held_through"])
    if st["method"] == "method_2":
        return XbrlError("method 2 exclusively: S.27.01.04 does not apply (ITS 2023/894 Annex III S.27.01 (c))",
                         "filing.refused.xbrl_group_method_two", group=st["group_name"])
    return None


def _group_note(payload: dict) -> str:
    st = (payload or {}).get("_group_solvency")
    if not st:
        return ""
    return (" · group solvency: method 1" if st["method"] == "method_1" else
            " · group solvency: combination of methods 1 and 2, the method-1 part")


def instance(payload: dict, identity: dict, role: str | None = None) -> str:
    """The XBRL instance of the filing's S.27.01.01 — or, for a group, its S.27.01.04 — from its frozen specification,
    standard-formula result and (a group's) group-solvency method. `role`: the filing's role ('consolidated' = a group)."""
    import services.regspec as R
    from services.governance import s2701
    from services.governance.filing_annex import _supplied
    from services.governance.insurer_solvency import natcat_block
    sf = natcat_block(payload).get("standard_formula_natcat") or {}
    rec = ((payload or {}).get("_specs") or {}).get(s2701.FAMILY) or {}
    if not rec.get("version") or "version" not in sf:
        raise XbrlError("this filing was frozen before S.27.01.01 was on the change route — refresh the draft to export XBRL")
    why = group_refusal(payload, role)
    if why is not None:
        raise why
    tid = s2701.tid_of(payload)
    ref_date = date.fromisoformat(sf["reference_date"])
    m = taxonomy_for(ref_date, tid)
    code = m.get("template", "S.27.01.01")
    missing_rows = [f"{v['label']} ({r})" for r, v in (m.get("rows_added_after_its_2023_894") or {}).items()]
    if missing_rows:
        raise XbrlError(f"EIOPA taxonomy {m['taxonomy_version']} (from {m['applies']['from']}) prints rows that ITS 2023/894 "
                        f"does not: {', '.join(missing_rows)}. Capture the amended template on the change route before "
                        "exporting a report for this reference date.")
    spec = R.load(s2701.FAMILY, rec["version"])
    grid = s2701.grid(spec, sf, _supplied(payload), tid)
    ccy = ((payload.get("_fx") or {}).get("presentation_currency") or "EUR").upper()

    contexts: dict[tuple, str] = {(): "c0"}                 # c0: no dimensions — the filing indicator's context too
    facts: list[str] = []
    # cells that are one data point in EIOPA's model (a peril's summary row and its 'total after diversification')
    # are reported once — and must agree
    seen: dict[tuple, tuple[str, str]] = {}
    for row, cols in sorted(grid.items()):
        for col, v in sorted(cols.items()):
            cell = m["cells"].get(f"{row}|{col}")
            if cell is None:
                raise XbrlError(f"{code} {row}/{col} has no XBRL representation in taxonomy {m['taxonomy_version']}")
            if row == "R0002":
                v = _simplification_codes(v)
            if v is None:
                continue                                  # nothing to report: the fact is omitted (S.21), never 0
            key = tuple(sorted(cell["dims"].items()))
            lex, unit, dec = _value(cell, v, m)
            point = (cell["concept"], key)
            if point in seen:
                if seen[point][0] != lex:
                    raise XbrlError(f"{code} {seen[point][1]} and {row}/{col} are one EIOPA data point but differ "
                                    f"({seen[point][0]} vs {lex})")
                continue
            seen[point] = (lex, f"{row}/{col}")
            cid = contexts.setdefault(key, f"c{len(contexts)}")
            attrs = f' contextRef="{cid}"' + (f' unitRef="{unit}" decimals="{dec}"' if unit else "")
            facts.append(f"  <{cell['concept']}{attrs}>{lex}</{cell['concept']}>")

    ns = m["namespaces"]
    decl = " ".join(f'xmlns:{p}="{u}"' for p, u in sorted(ns.items()) if p not in ("link", "xlink", "xbrli", "xbrldi", "iso4217", "find"))
    lei = escape(identity["lei"])
    period = ref_date.isoformat()

    def context(cid: str, dims: tuple) -> str:
        members = "".join(f'<xbrldi:explicitMember dimension="{d}">{mem}</xbrldi:explicitMember>' for d, mem in dims)
        scen = f"<xbrli:scenario>{members}</xbrli:scenario>" if dims else ""
        return (f'  <xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="{_LEI_SCHEME}">{lei}</xbrli:identifier>'
                f"</xbrli:entity><xbrli:period><xbrli:instant>{period}</xbrli:instant></xbrli:period>{scen}</xbrli:context>")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:link="http://www.xbrl.org/2003/linkbase" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
        'xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:find="http://www.eurofiling.info/xbrl/ext/filing-indicators" '
        f"{decl}>",
        f'  <!-- {code} natural catastrophe risk · {escape(identity["name"])} · {escape(identity["note"])} · EIOPA taxonomy '
        f'{m["taxonomy_version"]} · {escape(sf.get("version_name") or sf["version"])}{_group_note(payload)}. The S.27.01 part of '
        f'the annual submission: S.01.01, S.01.02 and the other templates come from the QRT package. -->',
        f'  <link:schemaRef xlink:type="simple" xlink:href="{m["entry_point"]}"/>',
        f'  <xbrli:unit id="uCCY"><xbrli:measure>iso4217:{ccy}</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uPURE"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>',
        *(context(cid, dims) for dims, cid in contexts.items()),
        f'  <find:fIndicators><find:filingIndicator contextRef="c0">{m["filing_indicator"]}</find:filingIndicator></find:fIndicators>',
        *facts,
        "</xbrli:xbrl>",
    ]
    return "\n".join(lines) + "\n"
