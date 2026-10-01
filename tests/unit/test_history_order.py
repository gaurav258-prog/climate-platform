"""A history is read in the order it was written — by its insert sequence, never by a timestamp (E51, E52, E86): now() is
the same for every row one transaction writes. Every query of a history table that orders it must order by `seq`."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ("regulatory_task_event", "regulatory_filing_event", "supervision_request_message", "reg_case_message",
           "model_status_event")
_STRING = re.compile(r'"""(.*?)"""|"((?:[^"\\\n]|\\.)*)"', re.S)


def test_history_tables_are_ordered_by_their_sequence():
    bad = []
    for p in [*ROOT.joinpath("services").rglob("*.py"), *ROOT.joinpath("api").rglob("*.py"), *ROOT.joinpath("tests").rglob("*.py")]:
        if p.name == Path(__file__).name:
            continue
        src = p.read_text()
        for m in _STRING.finditer(src):
            sql = m.group(1) or m.group(2) or ""
            if any(re.search(rf"\bFROM\s+{t}\b", sql) for t in HISTORY):
                order = re.search(r"ORDER BY\s+([^\n)]*)", sql)
                if order and "created_at" in order.group(1):
                    bad.append(f"{p.relative_to(ROOT)}:{src[:m.start()].count(chr(10)) + 1} ORDER BY {order.group(1).strip()}")
    assert not bad, bad
