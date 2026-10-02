"""scripts/commit_paths.sh moves the branch checked out where it runs — never a fixed 'main' (E124): run from a worktree,
it once moved the main checkout's branch to a commit made on another."""
from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "commit_paths.sh"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_a_worktree_commit_moves_its_own_branch_only(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("one\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "first")
    main_before = _git(repo, "rev-parse", "main")

    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "side", str(wt))
    (wt / "a.txt").write_text("two\n")
    subprocess.run(["bash", str(SCRIPT), "side change", "a.txt"], cwd=wt, check=True, capture_output=True, text=True)

    assert _git(repo, "rev-parse", "main") == main_before                 # the other checkout's branch did not move
    assert _git(repo, "log", "-1", "--format=%s", "side") == "side change"
    assert _git(wt, "status", "--porcelain") == ""                         # the worktree's index followed its commit


def test_a_detached_head_is_refused(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("one\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "first")
    _git(repo, "checkout", "-q", "--detach")
    (repo / "a.txt").write_text("two\n")
    r = subprocess.run(["bash", str(SCRIPT), "x", "a.txt"], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 2 and "detached" in r.stderr
