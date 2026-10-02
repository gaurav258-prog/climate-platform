"""E114 guard: a scheduled feed refresh lands files only where git does not track them.

The default live-data root is gitignored and holds no tracked file; every committed reference file a refresh hook
touches has a live counterpart there. tests/integration/test_feed_auto_refresh.py runs every auto-refresh hook for
real and checks the checkout is unchanged afterwards."""
import shutil
import subprocess

import pytest

from core import live_data
from core.config import settings

pytestmark = pytest.mark.skipif(shutil.which("git") is None or not (live_data.REPO_ROOT / ".git").exists(),
                                reason="not a git checkout")


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=live_data.REPO_ROOT, capture_output=True, text=True)


def test_default_live_root_is_gitignored_and_untracked(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_DATA_PATH", "")
    root = live_data.live_root()
    rel = root.relative_to(live_data.REPO_ROOT)
    assert _git("check-ignore", "-q", f"{rel}/reference/probe.json").returncode == 0, f"{rel}/ is not gitignored"
    assert _git("ls-files", str(rel)).stdout.strip() == "", f"files under {rel}/ are tracked"


def test_gvp_refresh_targets_the_live_root_not_the_snapshot(monkeypatch):
    import scripts.fetch_gvp_catalogue as G
    monkeypatch.setattr(settings, "LIVE_DATA_PATH", "")
    target = live_data.live_path(G.SNAPSHOT_PATH).relative_to(live_data.REPO_ROOT)
    assert _git("check-ignore", "-q", str(target)).returncode == 0
    assert target != G.SNAPSHOT_PATH.relative_to(live_data.REPO_ROOT)
