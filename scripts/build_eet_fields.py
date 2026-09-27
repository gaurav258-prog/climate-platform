"""Build the European ESG Template (EET) field list from FinDatEx's official file.

The EET is the file fund manufacturers send distributors and insurers: one row per share-class ISIN, one column per
field, in a fixed order. FinDatEx publishes the definition as an Excel sheet; this turns it into
data/reference/eet/eet_fields.json — every field in order with its section, definition, format ("codification"), and
whether it is Mandatory / Conditional / Optional for each use:

    periodic          SFDR products periodic               precontractual   SFDR products pre-contractual
    entity            SFDR entity (insurers & distributors) mifid            MiFID products (incl. target market)
    idd               IDD products                          look_through     funds of funds / look-through

Re-run when FinDatEx publishes a new version (set URL):  python -m scripts.build_eet_fields
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import openpyxl
import requests

URL = ("https://findatex.eu/mediaitem/496b7581-e739-4400-883f-130878015974/"
       "20260410-+EET+V1.1.3_Editorial+update.xlsx")
VERSION = "V1.1.3"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "eet" / "eet_fields.json"
USES = {10: "periodic", 11: "precontractual", 12: "entity", 13: "mifid", 14: "idd", 18: "look_through"}


def build() -> int:
    data = requests.get(URL, timeout=120).content
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)["EET"]
    fields, section = [], None
    for r in ws.iter_rows(min_row=7, values_only=True):
        name = (str(r[1]).strip() if r[1] else "")
        if r[0] and not name:
            section = " ".join(str(r[0]).split())
            continue
        if not name or "_" not in name or not name.split("_", 1)[0].isdigit():
            continue
        def txt(v):
            return " ".join(str(v).split()) if v is not None else None
        fields.append({"order": len(fields) + 1, "name": name, "code": name.split("_", 1)[0], "section": section,
                       "definition": txt(r[2]), "codification": (str(r[3]).strip() if r[3] is not None else None),
                       "comment": txt(r[4]),
                       "req": {k: (str(r[i]).strip().upper()[:1] if r[i] else None) for i, k in USES.items()}})
    if not fields or fields[0]["name"] != "00010_EET_Version":
        raise SystemExit("unexpected layout — the first field is not 00010_EET_Version; refusing to write")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"version": VERSION, "source": URL, "n_fields": len(fields), "fields": fields},
                              indent=1, ensure_ascii=False))
    print(f"wrote {len(fields)} EET {VERSION} fields → {OUT}")
    return len(fields)


if __name__ == "__main__":
    build()
