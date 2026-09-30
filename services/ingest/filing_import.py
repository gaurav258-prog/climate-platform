"""Read a filed ESG report and break it into its individual reported lines.

The customer uploads the actual report they filed and had accepted — an XBRL / iXBRL package, or the PDF or
Excel as submitted. We read it against the framework we already model and return each line as a cell, mapped
to a canonical datapoint where the line is recognised. Nothing is saved here; the caller previews the read
lines and the preparer confirms them before they are stored.

Three readers, one output shape:
  - XBRL / iXBRL : tagged facts are read directly (concept, value, unit)
  - Excel        : labelled rows with a value are read against the sheet
  - PDF          : tables and labelled lines are read from the document

Output cell: {template_ref, label, datapoint_key, value_num, value_text, unit, read_method}

The ESRS statement (esrs_pack) has no keyword map: a line is one of the concepts the governing version prints
(data/reference/esrs/concepts.json) only when its label is that concept's label — XBRL element names of EFRAG's ESRS
taxonomy are not bound yet, so a tagged fact is left for the preparer to map.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from typing import Optional

from services.governance.datapoint_catalog import catalog
from services.ingest import units

MAX_LINES = 600  # a filed disclosure is at most a few hundred lines; guard against a pathological upload

# ── keyword → canonical datapoint, per framework ──────────────────────────────────────────────────────
# A read line is matched to a catalog datapoint by keyword. Unmatched lines are kept with datapoint_key
# None (the preparer maps or drops them at confirm) — never guessed.
_KEYWORDS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "bank_p3esg": [
        ("p3_transition_top20", ("top 20", "top-20", "top20", "carbon-intensive", "template 4", "template4")),
        ("p3_transition_align", ("transition", "alignment metric", "nze", "iea", "template 3", "template3", "distance")),
        ("p3_gar_aligned",      ("aligned", "alignment", "dnsh", "safeguard")),
        ("p3_gar_eligible",     ("gar", "green asset ratio", "taxonomy-eligible", "taxonomy eligible", "eligible", "template 7", "template 8")),
        ("p3_scope3",           ("financed emission", "scope 3", "scope3", "ghg", "pcaf", "tco2", "emissions")),
        ("p3_physical",         ("physical", "template 5", "template5", "acute", "chronic", "flood", "hazard")),
        ("p3_qualitative",      ("governance", "strategy", "risk management", "qualitative", "narrative")),
    ],
    "bank_tcfd": [
        ("phys_risk",         ("physical", "value at risk", "acute", "chronic", "flood", "hazard")),
        # transition BEFORE taxonomy-aligned, so "transition alignment …" maps to transition risk, not GAR
        ("transition_risk",   ("transition", "carbon price", "carbon-price", "stranded")),
        ("taxonomy_aligned",  ("aligned", "alignment", "dnsh", "safeguard")),
        ("taxonomy_eligible", ("gar", "green asset ratio", "taxonomy-eligible", "taxonomy eligible", "eligible")),
        ("financed_emissions",("financed emission", "scope 3", "scope3", "pcaf", "ghg", "tco2", "emissions")),
        ("tcfd_narrative",    ("governance", "strategy", "narrative", "transition plan")),
    ],
    "sfdr_pai": [
        ("pai_nature",     ("biodiversity", "emissions to water", "water", "hazardous waste", "nature", "pai 7", "pai 8", "pai 9")),
        ("pai_social",     ("ungc", "oecd", "gender pay", "board gender", "social", "human rights", "pai 10", "pai 11", "pai 12", "pai 13", "pai 14")),
        ("pai_climate",    ("ghg", "emission", "carbon footprint", "waci", "carbon intensity", "fossil", "energy", "scope", "pai 1", "pai 2", "pai 3")),
        ("pai_additional", ("additional", "opt-in", "opt in", "table 2", "table 3", "voluntary")),
        ("sfdr_narrative", ("narrative", "policy", "engagement", "reference standard")),
    ],
}


def _norm(label: str) -> str:
    s = re.sub(r"\s+", " ", (label or "").replace("\u2013", "-").replace("\u2014", "-")).strip().lower()
    return re.sub(r"\s*(\([^()]*\)|:)\s*$", "", s)             # a trailing unit '(tCO2eq)' or colon


def match_datapoint(framework: str, label: str, targets: Optional[dict[str, str]] = None) -> Optional[str]:
    """The datapoint a read line is. With `targets` (key → label: the ESRS concepts the governing version prints) only
    an exact match of the line's label — the concept's own label, or its key — counts; anything else is left for the
    preparer to map. Otherwise the framework's keyword map."""
    if targets is not None:
        text = _norm(label)
        return next((k for k, lb in targets.items() if text in (_norm(lb), k.lower())), None)
    text = (label or "").lower()
    for key, kws in _KEYWORDS.get(framework, []):
        if any(k in text for k in kws):
            return key
    return None


# ── number parsing ────────────────────────────────────────────────────────────────────────────────────
_NUM = re.compile(r"-?\d[\d\s.,]*")


def parse_number(raw, apply_scale: bool = True) -> tuple[Optional[float], Optional[str]]:
    """Return (value, unit). The unit is normalised (services.ingest.units: ISO code for money — € $ £ ¥ or a code —
    '%', 'tCO2e', …; None when the value says nothing) and a magnitude word ('€12.3m', 'USD 4 bn') scales the value
    unless apply_scale=False (plain XBRL facts are already in units). Both , and . work as thousands separators."""
    v, unit, scale = read_value(raw)
    return (v * scale if (v is not None and apply_scale) else v), unit


def read_value(raw) -> tuple[Optional[float], Optional[str], float]:
    """(number as written, unit, scale stated) for one cell."""
    if raw is None:
        return None, None, 1.0
    if isinstance(raw, (int, float)):
        return float(raw), None, 1.0
    s = str(raw).strip()
    if not s:
        return None, None, 1.0
    unit, scale = units.from_text(s)
    m = _NUM.search(s.replace(" ", " "))
    if not m:
        return None, unit, scale
    token = m.group(0).strip().replace(" ", "")
    # decide decimal separator: the last of , or . that is followed by 1-2 digits is the decimal point
    dec = None
    for sep in (",", "."):
        i = token.rfind(sep)
        if i != -1 and len(token) - i - 1 in (1, 2):
            dec = sep
    if dec == ",":
        token = token.replace(".", "").replace(",", ".")
    else:
        token = token.replace(",", "")
    try:
        return float(token), unit, scale
    except ValueError:
        return None, unit, scale


def _with_label(value: Optional[float], unit: Optional[str], scale: float, label: str) -> tuple[Optional[float], Optional[str]]:
    """A value cell that states no unit / magnitude takes them from its row label ('Total assets (EUR m)')."""
    lu, ls = units.from_text(label)
    if unit is None:
        unit = lu
    if scale == 1.0 and unit != "%":
        scale = ls
    return (value * scale if value is not None else None), unit


def detect_format(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    head = data[:4096].lstrip()[:400].lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return "excel"
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        return "pdf"
    if name.endswith(".xbrl") or (b"<xbrl" in head or b":xbrl" in head):
        return "xbrl"
    if name.endswith((".html", ".htm", ".xhtml")) or b"<ix:" in head or b"inlinexbrl" in head or b"<html" in head:
        return "ixbrl"
    if name.endswith(".xml"):
        return "xbrl"
    raise ValueError("unsupported_format")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _human(concept: str) -> str:
    # 'GreenAssetRatioEligibleStock' → 'Green Asset Ratio Eligible Stock', but keep acronym / number runs
    # intact: 'TransitionAlignmentDistanceNZE2050' → 'Transition Alignment Distance NZE2050'.
    name = concept.rsplit(":", 1)[-1].replace("_", " ")
    # split at lower/number→Upper boundaries, and at Acronym→Word boundaries (UPPERWord)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name).strip()
    return (s[:1].upper() + s[1:]) if s else concept


# ── readers ───────────────────────────────────────────────────────────────────────────────────────────
def _read_xbrl(match, data: bytes) -> list[dict]:
    """Read tagged facts from an XBRL or inline-XBRL (iXBRL) document. iXBRL wraps facts in ix: elements;
    plain XBRL exposes facts as elements carrying a contextRef. We read both."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        # iXBRL is XHTML and may carry undeclared entities; retry on a lenient byte clean
        root = ET.fromstring(re.sub(rb"&(?!amp;|lt;|gt;|quot;|apos;|#)", b"&amp;", data))
    # the document's own unit definitions: id → our unit (iso4217:USD → 'USD'; a divide → 'EUR/shares')
    unit_of: dict[str, str] = {}
    for u in root.iter():
        if _local(u.tag) != "unit" or not u.get("id"):
            continue
        measures = [units.from_measure((m.text or "").strip()) for m in u.iter() if _local(m.tag) == "measure"]
        measures = [m for m in measures if m]
        if measures:
            unit_of[u.get("id")] = "/".join(measures)
    cells: list[dict] = []
    for el in root.iter():
        lname = _local(el.tag)
        concept = el.get("name")  # ix:nonFraction / ix:nonNumeric carry the concept in @name
        is_ix_fact = lname in ("nonFraction", "nonNumeric") and concept
        is_plain_fact = concept is None and el.get("contextRef") is not None and (el.text or "").strip()
        if not (is_ix_fact or is_plain_fact):
            continue
        concept = concept or _local(el.tag)
        label = _human(concept)
        text = (el.text or "").strip()
        # a fact's unitRef is authoritative; the displayed text only when there is none. Plain XBRL values are in
        # units already (no magnitude words); iXBRL states its magnitude in @scale (below).
        val, text_unit = parse_number(text, apply_scale=False)
        ref = el.get("unitRef")
        unit = unit_of.get(ref) or text_unit or (units.from_measure(ref) if ref else None)
        # iXBRL numeric transforms: sign and scale (×10^scale)
        if is_ix_fact and val is not None:
            try:
                if el.get("scale"):
                    val *= 10 ** int(el.get("scale"))
                if (el.get("sign") or "") == "-":
                    val = -abs(val)
            except (ValueError, TypeError):
                pass
        cells.append({
            "template_ref": concept,
            "label": label,
            "datapoint_key": match(label) or match(concept),
            "value_num": val if lname != "nonNumeric" else None,
            "value_text": text if (lname == "nonNumeric" or val is None) else None,
            "unit": unit,
            "read_method": "auto",
        })
        if len(cells) >= MAX_LINES:
            break
    return cells


def _read_excel(match, data: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    cells: list[dict] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            if not row:
                continue
            label = next((str(c).strip() for c in row if isinstance(c, str) and c.strip()), None)
            if not label:
                continue
            # the reported value = the last numeric-looking cell on the row
            value, unit, scale, vtext = None, None, 1.0, None
            for c in reversed(row):
                if isinstance(c, (int, float)):
                    value = float(c); break
                if isinstance(c, str) and c.strip() and c.strip() != label:
                    v, u, k = read_value(c)
                    if v is not None:
                        value, unit, scale = v, u, k; break
                    if vtext is None and c.strip() != label:
                        vtext = c.strip()
            value, unit = _with_label(value, unit, scale, label)
            if value is None and vtext is None:
                continue
            cells.append({
                "template_ref": ws.title,
                "label": label,
                "datapoint_key": match(label) if match.exact else match(f"{ws.title} {label}"),
                "value_num": value,
                "value_text": vtext,
                "unit": unit,
                "read_method": "auto",
            })
            if len(cells) >= MAX_LINES:
                wb.close(); return cells
    wb.close()
    return cells


def _read_pdf(match, data: bytes) -> list[dict]:
    import pdfplumber
    cells: list[dict] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables() or []:
                for row in table:
                    vals = [(_c or "").strip() for _c in row]
                    label = next((v for v in vals if v and parse_number(v)[0] is None), None)
                    if not label:
                        continue
                    value, unit, scale = None, None, 1.0
                    for v in reversed(vals):
                        if v and v != label:
                            pv, pu, pk = read_value(v)
                            if pv is not None:
                                value, unit, scale = pv, pu, pk; break
                    if value is None:
                        continue
                    value, unit = _with_label(value, unit, scale, label)
                    cells.append({
                        "template_ref": f"p.{pno}",
                        "label": label,
                        "datapoint_key": match(label),
                        "value_num": value,
                        "value_text": None,
                        "unit": unit,
                        "read_method": "auto",
                    })
                    if len(cells) >= MAX_LINES:
                        return cells
    return cells


_READERS = {"xbrl": _read_xbrl, "ixbrl": _read_xbrl, "excel": _read_excel, "pdf": _read_pdf}


def extract(framework: str, filename: str, data: bytes, targets: Optional[dict[str, str]] = None) -> dict:
    """Read a filed report → {format, cells:[...], n_mapped, n_total}. targets: the datapoints a line may be (key →
    label), matched exactly — the ESRS statement's concepts for the filing's year; without them the framework's
    catalog keywords. Raises ValueError('unsupported_format') for an unknown file, or ValueError('unreadable') if the
    reader found no figures."""
    if targets is None and catalog(framework) is None:
        raise ValueError("unknown_framework")
    fmt = detect_format(filename, data)

    def match(label):
        return match_datapoint(framework, label, targets)
    match.exact = targets is not None
    try:
        cells = _READERS[fmt](match, data)
    except ValueError:
        raise
    except Exception:  # a corrupt/empty workbook, malformed XML, unreadable PDF → one clean error, not a 500
        raise ValueError("unreadable")
    if not cells:
        raise ValueError("unreadable")
    n_mapped = sum(1 for c in cells if c["datapoint_key"])
    return {"format": fmt, "cells": cells, "n_total": len(cells), "n_mapped": n_mapped}
