"""One standard workbook per sector (the product owner's decision of 2026-10-23): every book a sector's customer sends,
in one Excel file — built from the same definitions the intake checks read (services/intake/catalog.TEMPLATES and each
book's fields), so the file a customer fills and the checks it meets can never drift apart.

  build(org_type)                       the workbook: 'Start here', one sheet per book (headers marked * when required,
                                        a dropdown where a field takes fixed values), a field guide, and a hidden map of
                                        each sheet to its book
  sheets(raw, org_type)                 the books a received workbook holds: [(sheet, template key, rows)]
  submit(session, org_id, org_type, …)  each sheet with rows received as its own batch through the intake pipeline —
                                        the same security inspection, malware scan, checks, second-person approval and
                                        landing as a single book (services/intake/pipeline.submit with its sheet named)
  check(session, org_id, org_type, …)   the same, nothing stored: each sheet's checks now

A book that lands queues its scores and, for a book of physical assets, its loss run (pipeline._land), so the platform
starts working once the file is accepted.
"""
from __future__ import annotations

import io
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.orm import Session

from core import messages
from services.intake.catalog import Template, template_fields, templates_for
from services.templates.workbook import HEADER_FILL, HEADER_FONT, REQUIRED_FONT

MAP_SHEET = "_tellumen"          # hidden: which book each sheet is, so a renamed sheet is still read as its book
LISTS_SHEET = "_lists"           # hidden: the fixed values a dropdown offers
START, GUIDE = "Start here", "Field guide"


class WorkbookError(ValueError):
    pass


def books(org_type: str) -> list[Template]:
    """The books of a sector's workbook, in the order they are read: a book other books refer to comes first (the
    catalogue's order — sites before their year-end values, parties before their shipments)."""
    out = templates_for(org_type)
    if not out:
        raise WorkbookError(f"no standard workbook for the organisation type {org_type!r}")
    return out


def build(org_type: str) -> io.BytesIO:
    tpls = books(org_type)
    wb = Workbook()
    start = wb.active
    start.title = START
    lists = wb.create_sheet(LISTS_SHEET)
    lists.sheet_state = "hidden"
    list_col = 0
    for tpl in tpls:
        ws = wb.create_sheet(tpl.sheet_name)
        for i, f in enumerate(template_fields(tpl.key), start=1):
            cell = ws.cell(row=1, column=i, value=f["name"] + (" *" if f["required"] else ""))
            cell.fill, cell.font = HEADER_FILL, HEADER_FONT
            cell.comment = Comment(f"{f['label']}\n{f['description']}", "Tellumen")
            ws.column_dimensions[cell.column_letter].width = max(14, len(f["name"]) + 4)
            if f.get("allowed"):
                list_col += 1
                for r, v in enumerate(f["allowed"], start=1):
                    lists.cell(row=r, column=list_col, value=v)
                col = lists.cell(row=1, column=list_col).column_letter
                dv = DataValidation(type="list", formula1=f"={LISTS_SHEET}!${col}$1:${col}${len(f['allowed'])}",
                                    allow_blank=not f["required"])
                ws.add_data_validation(dv)
                dv.add(f"{cell.column_letter}2:{cell.column_letter}100000")
        ws.freeze_panes = "A2"
    _guide(wb.create_sheet(GUIDE), tpls)
    _start(start, org_type, tpls)
    m = wb.create_sheet(MAP_SHEET)
    m.sheet_state = "hidden"
    m.append(["sheet", "book"])
    for tpl in tpls:
        m.append([tpl.sheet_name, tpl.key])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _start(ws, org_type: str, tpls: list[Template]) -> None:
    intro = messages.render("intake.workbook.start", sector=messages.name("admin.sector", org_type))
    ws["A1"] = intro["label"]
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = intro["detail"]["what"]
    ws["A3"] = intro["detail"]["next"]
    for c in ("A2", "A3"):
        ws[c].alignment = Alignment(wrap_text=True, vertical="top")
    ws.append([])
    ws.append(["Sheet", "What it holds", "Required fields"])
    for cell in ws[ws.max_row]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for tpl in tpls:
        fields = template_fields(tpl.key)
        ws.append([tpl.sheet_name, messages.label(f"intake.book.{tpl.key}"), sum(1 for f in fields if f["required"])])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["C"].width = 28, 70, 16


def _guide(ws, tpls: list[Template]) -> None:
    head = ["Sheet", "Field", "Required", "What it is", "Example", "Allowed values", "Range"]
    ws.append(head)
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for tpl in tpls:
        for f in template_fields(tpl.key):
            allowed = f.get("value_labels") or {v: v for v in f.get("allowed") or []}
            ws.append([tpl.sheet_name, f["name"], "Required" if f["required"] else "Optional",
                       f"{f['label']}. {f['description']}", f.get("example"),
                       ", ".join(f"{k} ({v})" if k != v else k for k, v in allowed.items()) or None,
                       " to ".join(str(x) for x in f["range"]) if f.get("range") else None])
            if f["required"]:
                ws.cell(row=ws.max_row, column=3).font = REQUIRED_FONT
            ws.cell(row=ws.max_row, column=4).alignment = Alignment(wrap_text=True, vertical="top")
    for col, width in zip("ABCDEFG", (24, 30, 11, 70, 22, 40, 14)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"


def sheets(raw: bytes, org_type: str) -> list[tuple[str, str, int]]:
    """(sheet, book, data rows) for every book sheet of a received workbook: read through its hidden map, a sheet the map
    does not name read by its title. A workbook with no book sheet of this sector is refused."""
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001 — any unreadable file is the customer's to fix, said plainly
        raise WorkbookError("not a readable Excel workbook") from e
    keys = {t.key for t in books(org_type)}
    mapped: dict[str, str] = {}
    if MAP_SHEET in wb.sheetnames:
        for row in wb[MAP_SHEET].iter_rows(min_row=2, values_only=True):
            if row and row[0] in wb.sheetnames and row[1] in keys:
                mapped[row[0]] = row[1]
    by_title = {t.sheet_name: t.key for t in books(org_type)}
    out = []
    for name in wb.sheetnames:
        key = mapped.get(name) or by_title.get(name)
        if not key:
            continue
        rows = sum(1 for r in wb[name].iter_rows(min_row=2, values_only=True) if any(v not in (None, "") for v in r))
        out.append((name, key, rows))
    wb.close()
    if not out:
        raise WorkbookError("the workbook holds no sheet of this sector's books")
    order = [t.key for t in books(org_type)]
    return sorted(out, key=lambda s: order.index(s[1]))


def submit(session: Session, org_id: str, org_type: str, raw: bytes, filename: Optional[str], *, user_id: str,
           reason: Optional[str] = None, currency: Optional[str] = None, book_date: Optional[str] = None) -> dict:
    """Each sheet with rows through the pipeline as its own batch, in the books' order; one sheet's refusal never stops
    the next. Each sheet's outcome is committed on its own, so the record of every attempt stays."""
    from services.intake import pipeline
    results = []
    for name, key, rows in sheets(raw, org_type):
        if rows == 0:
            results.append({"sheet": name, "book": key, "state": "empty"})
            continue
        try:   # the file's own name (its ending is checked); the sheet is recorded on the batch beside it
            out = pipeline.submit(session, org_id, key, raw, filename, via="upload", user_id=user_id, reason=reason,
                                  currency=currency, book_date=book_date, sheet=name)
            out.pop("http_status", None)
            results.append({"sheet": name, "book": key, **{k: out.get(k) for k in (
                "state", "batch_id", "n_total", "n_valid", "n_error", "n_uploaded", "msg", "scoring", "losses")}})
        except pipeline.IntakeError as e:
            results.append({"sheet": name, "book": key, "state": e.body.get("state") or "refused",
                            "batch_id": e.body.get("batch_id"), "msg": e.body.get("msg"),
                            "n_error": e.body.get("n_error"), "errors": (e.body.get("errors") or [])[:20]})
        session.commit()
    return {"filename": filename, "sheets": results}


def check(session: Session, org_id: str, org_type: str, raw: bytes, filename: Optional[str], *,
          currency: Optional[str] = None, book_date: Optional[str] = None) -> dict:
    """Every sheet's checks on the file now — nothing stored."""
    from services.intake import pipeline
    results = []
    for name, key, rows in sheets(raw, org_type):
        if rows == 0:
            results.append({"sheet": name, "book": key, "state": "empty"})
            continue
        try:
            out = pipeline.preview(session, org_id, key, raw, filename, currency=currency,
                                   book_date=book_date, sheet=name)
            gate = out["controls"]["gate"]
            results.append({"sheet": name, "book": key, "state": "checked", "gate": gate["status"],
                            "gate_messages": gate.get("messages") or [], **{k: out.get(k) for k in ("n_total", "n_valid", "n_error")},
                            "errors": out["errors"][:20]})
        except pipeline.IntakeError as e:
            results.append({"sheet": name, "book": key, "state": "refused", "msg": e.body.get("msg")})
    return {"filename": filename, "sheets": results}
