"""Inbox storage for drop-folder channels: where an SFTP feed's files land, behind one small interface.

    ensure(folder)                      create incoming/ processed/ refused/
    ready(folder, min_age)              finished files in incoming/ (a file still changing, or a .part, waits)
    read(folder, name) -> bytes
    file_away(folder, name, dest, why)  move to processed/ or refused/ (with <name>.reason.txt) → the new name

The drop-folder logic (dropfolder.py) only talks to this interface, never to a filesystem, so moving the inbox to
object storage (the managed-SFTP case: files land in a bucket) is one more backend class. Only the local-directory
backend exists today; asking for another fails loudly (go-live #12 / #13), never silently writes elsewhere.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.config import settings

SKIP_SUFFIXES = (".part", ".tmp", ".filepart", ".partial", ".reason.txt")
AREAS = ("incoming", "processed", "refused")


class InboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class Entry:
    name: str
    size: int
    modified: float


class LocalInbox:
    def __init__(self, root: str):
        r = Path(root)
        self.root = r if r.is_absolute() else Path(__file__).resolve().parents[2] / r

    def _dir(self, folder: str, area: str) -> Path:
        if area not in AREAS or ".." in Path(folder).parts:
            raise InboxError("invalid inbox path")
        return self.root / folder / area

    def ensure(self, folder: str) -> None:
        for a in AREAS:
            self._dir(folder, a).mkdir(parents=True, exist_ok=True)

    def ready(self, folder: str, min_age: float) -> list[Entry]:
        d = self._dir(folder, "incoming")
        if not d.exists():
            return []
        now, out = time.time(), []
        for p in sorted(d.iterdir()):
            if not p.is_file() or p.name.startswith(".") or p.name.lower().endswith(SKIP_SUFFIXES):
                continue
            st = p.stat()
            if now - st.st_mtime >= min_age:          # still being written — the next sweep takes it
                out.append(Entry(p.name, st.st_size, st.st_mtime))
        return out

    def read(self, folder: str, name: str) -> bytes:
        p = self._dir(folder, "incoming") / name
        if p.parent != self._dir(folder, "incoming"):
            raise InboxError("invalid file name")
        return p.read_bytes()

    def file_away(self, folder: str, name: str, dest: str, reason: Optional[str] = None) -> str:
        src = self._dir(folder, "incoming") / name
        if src.parent != self._dir(folder, "incoming"):
            raise InboxError("invalid file name")
        to = self._dir(folder, dest)
        to.mkdir(parents=True, exist_ok=True)
        stamped = to / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{name}"
        os.replace(src, stamped)
        if reason:
            stamped.with_name(stamped.name + ".reason.txt").write_text(reason + "\n", encoding="utf-8")
        return stamped.name


def backend() -> LocalInbox:
    kind = settings.INTAKE_DROP_BACKEND
    if kind != "local":
        raise InboxError(f"Drop-folder backend '{kind}' is not available in this build (only 'local'). "
                         "See docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md #12 and #13.")
    return LocalInbox(settings.INTAKE_DROP_DIR)
