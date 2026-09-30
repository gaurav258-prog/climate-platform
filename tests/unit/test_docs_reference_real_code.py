"""The documentation describes the code as it is (feedback: facts only). Every repository path a living document names
— a module, script, config, reference file, page or test — exists, unless the document says, on that line or the next,
that it was removed, retired or never built. Guards the error found on 2026-09-30: four documents still described the
ESRS XBRL engine, the CSRD package's XBRL and the drop-in binding file after E60 / E66 removed them.

What is history, not description, is not read: the change log of SOFTWARE_DESCRIPTION.md (§12 onward), the error-log
rows of ENGINEERING_PROCESS.md (| E<n> |), and a document that opens with a status block declaring itself 'kept as a
record' (its status block is still read).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = re.compile(r"\b((?:services|ml|api|core|scripts|config|web/src|data/reference|tests)/[A-Za-z0-9_./-]+"
                  r"\.(?:py|json|tsx|ts|yaml|yml|csv|md))")
GONE = re.compile(r"\b(removed|retired|never built|deleted)\b", re.IGNORECASE)


def _living_lines(doc: Path) -> list[str]:
    lines = doc.read_text(errors="ignore").splitlines()
    if doc.name == "SOFTWARE_DESCRIPTION.md":
        lines = lines[:next((i for i, x in enumerate(lines) if x.startswith("## 12. Change log")), len(lines))]
    if doc.name == "ENGINEERING_PROCESS.md":
        lines = [x for x in lines if not re.match(r"\|\s*E\d+\s*\|", x)]
    head = "\n".join(lines[:6])
    if "kept as a record" in head:                       # a record: only its status block describes the present
        block = [x for x in lines[:40] if x.startswith(">") or not x.strip() or x.startswith("#")]
        lines = block[:next((i for i, x in enumerate(block[2:], 2) if not x.startswith(">") and x.strip()), len(block))]
    return lines


def _stale(doc: Path) -> list[str]:
    lines = _living_lines(doc)
    out = []
    for i, line in enumerate(lines):
        for p in PATH.findall(line):
            if (ROOT / p).exists() or p.endswith("<version>.json"):
                continue
            if GONE.search(line) or (i + 1 < len(lines) and GONE.search(lines[i + 1])):
                continue
            out.append(f"{doc.relative_to(ROOT)}:{i + 1}: {p}")
    return out


def test_living_documents_name_only_code_that_exists():
    stale = [s for doc in sorted((ROOT / "docs").rglob("*.md")) for s in _stale(doc)]
    assert not stale, "documents name code that does not exist (correct the text, or say it was removed):\n" + "\n".join(stale)
