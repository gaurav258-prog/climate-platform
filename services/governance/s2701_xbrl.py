"""S.27.01.01 (natural catastrophe risk) as an XBRL instance in EIOPA's Solvency II taxonomy — the part of the
undertaking's annual quantitative reporting this platform computes.

Every cell's XBRL representation — the metric, its data type and the dimension members of its table — is read from
data/reference/eiopa/s2701_xbrl.<taxonomy>.json, parsed from EIOPA's own table linkbase and cross-checked against
EIOPA's annotated templates (0 disagreements). The taxonomy is chosen by the reporting reference date. The instance
follows EIOPA's XBRL Filing Rules: one absolute schemaRef to the annual solo entry point (ars), the entity's LEI
(scheme http://standards.iso.org/iso/17442), one instant, one ISO 4217 unit, @decimals only, no nil or duplicate fact,
a cell with nothing to report omitted, one filing indicator 'S.27.01' on a context without dimensions.

It is the S.27.01 contribution to the undertaking's annual submission, not the whole submission: the module also
requires S.01.01 (content of the submission) and S.01.02 (basic information), and the undertaking's other templates,
which its QRT package holds. The instance says so.
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
    pass


@lru_cache(maxsize=4)
def _load(version: str) -> dict:
    with open(os.path.join(_DIR, f"s2701_xbrl.{version}.json")) as f:
        return json.load(f)


def taxonomy_for(reference_date: date) -> dict:
    """The EIOPA taxonomy that applies to a reporting reference date."""
    d = reference_date.isoformat()
    for name in sorted(f for f in os.listdir(_DIR) if f.startswith("s2701_xbrl.") and f.endswith(".json")):
        m = _load(name[len("s2701_xbrl."):-len(".json")])
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


def instance(payload: dict, identity: dict) -> str:
    """The XBRL instance of the filing's S.27.01.01, from its frozen specification and standard-formula result."""
    import services.regspec as R
    from services.governance import s2701
    from services.governance.filing_annex import _supplied
    from services.governance.insurer_solvency import natcat_block
    sf = natcat_block(payload).get("standard_formula_natcat") or {}
    rec = ((payload or {}).get("_specs") or {}).get(s2701.FAMILY) or {}
    if not rec.get("version") or "version" not in sf:
        raise XbrlError("this filing was frozen before S.27.01.01 was on the change route — refresh the draft to export XBRL")
    ref_date = date.fromisoformat(sf["reference_date"])
    m = taxonomy_for(ref_date)
    missing_rows = [f"{v['label']} ({r})" for r, v in (m.get("rows_added_after_its_2023_894") or {}).items()]
    if missing_rows:
        raise XbrlError(f"EIOPA taxonomy {m['taxonomy_version']} (from {m['applies']['from']}) prints rows that ITS 2023/894 "
                        f"does not: {', '.join(missing_rows)}. Capture the amended template on the change route before "
                        "exporting a report for this reference date.")
    spec = R.load(s2701.FAMILY, rec["version"])
    grid = s2701.grid(spec, sf, _supplied(payload))
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
                raise XbrlError(f"S.27.01.01 {row}/{col} has no XBRL representation in taxonomy {m['taxonomy_version']}")
            if row == "R0002":
                v = _simplification_codes(v)
            if v is None:
                continue                                  # nothing to report: the fact is omitted (S.21), never 0
            key = tuple(sorted(cell["dims"].items()))
            lex, unit, dec = _value(cell, v, m)
            point = (cell["concept"], key)
            if point in seen:
                if seen[point][0] != lex:
                    raise XbrlError(f"S.27.01.01 {seen[point][1]} and {row}/{col} are one EIOPA data point but differ "
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
        f'  <!-- S.27.01.01 natural catastrophe risk · {escape(identity["name"])} · {escape(identity["note"])} · EIOPA taxonomy '
        f'{m["taxonomy_version"]} · {escape(sf.get("version_name") or sf["version"])}. The S.27.01 part of the annual submission: '
        f'S.01.01, S.01.02 and the other templates come from the undertaking\'s QRT package. -->',
        f'  <link:schemaRef xlink:type="simple" xlink:href="{m["entry_point"]}"/>',
        f'  <xbrli:unit id="uCCY"><xbrli:measure>iso4217:{ccy}</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uPURE"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>',
        *(context(cid, dims) for dims, cid in contexts.items()),
        f'  <find:fIndicators><find:filingIndicator contextRef="c0">{m["filing_indicator"]}</find:filingIndicator></find:fIndicators>',
        *facts,
        "</xbrli:xbrl>",
    ]
    return "\n".join(lines) + "\n"
