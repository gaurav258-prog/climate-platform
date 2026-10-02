"""Live data — where scheduled feed refreshes land files, apart from the committed reference snapshots.

A reference file in git (data/reference/…) is a versioned snapshot: it changes only when someone promotes a new
version on purpose, in a commit about that. A scheduled refresh lands its copy here instead — settings.LIVE_DATA_PATH,
by default <repo>/data/live, which git ignores — so a refresh never dirties the checkout, never blocks a merge and
never rides along in an unrelated commit (E114). Readers take the live copy when one has landed and fall back to
the committed snapshot otherwise (`prefer_live`).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def live_root() -> Path:
    """The live-data directory (read at call time, so a test or deployment can point it elsewhere)."""
    p = Path(settings.LIVE_DATA_PATH) if settings.LIVE_DATA_PATH else REPO_ROOT / "data" / "live"
    return p if p.is_absolute() else REPO_ROOT / p


def live_path(committed: Path) -> Path:
    """The live counterpart of a committed reference file: same path relative to data/, under the live root
    (data/reference/x.json → <live>/reference/x.json)."""
    return live_root() / Path(committed).resolve().relative_to(REPO_ROOT / "data")


def prefer_live(committed: Path) -> Path:
    """The file a reader should open: the refreshed live copy when one has landed, else the committed snapshot."""
    live = live_path(committed)
    return live if live.exists() else Path(committed)


def write_live(committed: Path, content: str) -> Path:
    """Land a refreshed copy atomically under the live root. Never writes the committed snapshot."""
    out = live_path(committed)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(content)
    tmp.replace(out)
    return out


def promote(committed: Path) -> Path:
    """Copy the live copy over the committed snapshot — the deliberate step that changes a versioned reference
    file (then commit it on its own). Raises when nothing live has landed."""
    live = live_path(committed)
    if not live.exists():
        raise FileNotFoundError(f"no live copy to promote: {live}")
    shutil.copyfile(live, committed)
    return Path(committed)
