"""Static security inspection of a received file, before anything parses it.

Answers: is this really the kind of file it claims to be, and does it carry anything we must not open?
Findings are either BLOCK (the file is refused) or WARN (the file may proceed, but the batch needs a second
person's approval — principle 3). Malware scanning is separate (malware.py); both must pass.

Accepted formats are deliberately narrow: CSV/TXT (plain text) and XLSX (Office Open XML without macros).
Legacy .xls, macro-enabled .xlsm/.xlsb and anything encrypted are refused with a plain instruction to re-save,
because they can carry macros or hide content from inspection.
"""
from __future__ import annotations

import io
import re
import zipfile

from core.config import settings

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"   # legacy Office / encrypted OOXML container
ZIP_MAGIC = b"PK\x03\x04"
MAX_UNCOMPRESSED = 300 * 1024 * 1024               # an XLSX that expands beyond this is refused
MAX_RATIO = 200                                    # per-entry compression ratio above this = zip-bomb shape
MAX_ENTRIES = 5000
_FORMULA_LIKE = re.compile(r"^\s*[=@]|^\s*[+\-][A-Za-z(]")   # =CMD(...), @SUM, +A1, -HYPERLINK( — but not -5 / +3.2

_EXT_TYPE = {".csv": "csv", ".txt": "csv", ".xlsx": "xlsx"}
_REFUSED_EXT = {".xls": "legacy Excel (.xls)", ".xlsm": "macro-enabled Excel (.xlsm)", ".xlsb": "binary Excel (.xlsb)"}


def _finding(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def _ext(filename: str | None) -> str:
    name = (filename or "").lower()
    return name[name.rfind("."):] if "." in name else ""


def detect_type(raw: bytes) -> str:
    """The file's real type from its content: 'xlsx', 'ole', 'zip', 'text' or 'binary'."""
    if raw.startswith(OLE_MAGIC):
        return "ole"
    if raw.startswith(ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names = set(z.namelist())
            return "xlsx" if "[Content_Types].xml" in names and any(n.startswith("xl/") for n in names) else "zip"
        except zipfile.BadZipFile:
            return "binary"
    sample = raw[:65536]
    if b"\x00" in sample:
        # UTF-16 text legitimately contains NULs; accept it only with a BOM
        return "text" if sample[:2] in (b"\xff\xfe", b"\xfe\xff") else "binary"
    try:
        sample.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        try:
            sample.decode("cp1252")
            return "text"
        except UnicodeDecodeError:
            return "binary"


def _inspect_xlsx(raw: bytes) -> list[dict]:
    out: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES:
            out.append(_finding("too_many_parts", "block", f"The workbook has {len(infos)} internal parts — refused as unsafe."))
            return out
        total = 0
        for i in infos:
            total += i.file_size
            if i.compress_size and i.file_size / max(i.compress_size, 1) > MAX_RATIO and i.file_size > 10 * 1024 * 1024:
                out.append(_finding("compression_bomb", "block", "The workbook expands far beyond its size (compression-bomb pattern) — refused."))
                return out
        if total > MAX_UNCOMPRESSED:
            out.append(_finding("too_large_uncompressed", "block", f"The workbook expands to {total / 1e6:.0f} MB — refused as unsafe."))
        names = {i.filename.lower() for i in infos}
        if any(n.endswith("vbaproject.bin") for n in names):
            out.append(_finding("macros", "block", "The workbook contains macros. Save it as a plain .xlsx (no macros) or CSV and send again."))
        if any(n.startswith("xl/embeddings/") for n in names):
            out.append(_finding("embedded_objects", "block", "The workbook contains embedded files or objects. Remove them and send again."))
        if any(n.startswith("xl/externallinks/") for n in names):
            out.append(_finding("external_links", "warn", "The workbook links to other files; only the values saved in this file are used."))
        if any(n.startswith("xl/activex/") for n in names):
            out.append(_finding("activex", "block", "The workbook contains ActiveX controls. Remove them and send again."))
    return out


def _inspect_text(raw: bytes) -> list[dict]:
    out: list[dict] = []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("cp1252")
        except UnicodeDecodeError:
            return [_finding("unreadable_text", "block", "The file is not readable text.")]
    hits = 0
    for line in text.splitlines()[:200000]:
        for cell in line.split(","):
            c = cell.strip().strip('"')
            if c and _FORMULA_LIKE.match(c):
                hits += 1
    if hits:
        out.append(_finding("formula_like_text", "warn",
                            f"{hits} cell(s) start like a spreadsheet formula (=, @, +, -). They are read as plain text, "
                            "never executed, but the batch needs a second person's approval."))
    return out


def inspect(raw: bytes, filename: str | None, allowed: tuple[str, ...] = ("csv", "xlsx")) -> dict:
    """Returns {"detected_type", "status": passed|warned|blocked, "findings": [...]}. Never raises on bad input."""
    findings: list[dict] = []
    size = len(raw)
    detected = detect_type(raw) if size else "empty"
    ext = _ext(filename)

    if size == 0:
        findings.append(_finding("empty", "block", "The file is empty."))
    elif size > settings.INTAKE_MAX_BYTES:
        findings.append(_finding("too_large", "block", f"The file is {size / 1e6:.1f} MB; the limit is {settings.INTAKE_MAX_BYTES / 1e6:.0f} MB. Split it and send in parts."))
    elif ext in _REFUSED_EXT:
        findings.append(_finding("unsupported_format", "block", f"{_REFUSED_EXT[ext]} is not accepted. Save as .xlsx or .csv and send again."))
    elif detected == "ole":
        findings.append(_finding("encrypted_or_legacy", "block", "This is a password-protected or legacy Office file. Remove the password and save as .xlsx or .csv."))
    elif detected in ("binary", "zip"):
        findings.append(_finding("not_a_table", "block", "This is not a spreadsheet or CSV file."))
    else:
        expected = _EXT_TYPE.get(ext)
        real = "xlsx" if detected == "xlsx" else "csv"
        if expected is None:
            findings.append(_finding("unsupported_format", "block", f"Files ending '{ext or '(none)'}' are not accepted. Send .csv or .xlsx."))
        elif expected != real:
            findings.append(_finding("type_mismatch", "block", f"The file is named {ext} but its content is {'an Excel workbook' if real == 'xlsx' else 'plain text'}. Rename or re-save it."))
        elif real not in allowed:
            findings.append(_finding("unsupported_format", "block", f"This upload accepts {' or '.join(allowed).upper()} only."))
        else:
            findings += _inspect_xlsx(raw) if real == "xlsx" else _inspect_text(raw)

    status = "blocked" if any(f["severity"] == "block" for f in findings) else ("warned" if findings else "passed")
    return {"detected_type": detected, "status": status, "findings": findings}
