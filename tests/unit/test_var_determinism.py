"""Monte-Carlo VaR must be reproducible across processes (audit T2).

The seed used to derive from Python's builtin `hash()` of a string tuple, which is salted per-process
(PYTHONHASHSEED). That made the *published* VaR change on every app restart — non-reproducible, which
contradicts the module's own promise. The seed is now a stable SHA-256 digest. This test proves the same
portfolio+settings yields the same VaR from two interpreters started with different hash seeds.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_SNIPPET = (
    "from ml.scoring.valuation_discount import monte_carlo_var;"
    "h=[{'position_value_eur':1_000_000,'bucket':'high','hazard':'flood'},"
    "   {'position_value_eur':500_000,'bucket':'moderate','hazard':'drought'}];"
    "r=monte_carlo_var(h,'org-123','baseline','current',n_sims=5000);"
    "print(f\"{r['var95_eur']:.4f}|{r['var99_eur']:.4f}|{r['median_loss_eur']:.4f}\")"
)


def _run(hashseed: str) -> str:
    env = {"PYTHONHASHSEED": hashseed, "PATH": "/usr/bin:/bin"}
    out = subprocess.check_output([sys.executable, "-c", _SNIPPET], cwd=str(REPO), env=env, timeout=120)
    return out.decode().strip()


def test_var_is_identical_across_processes_with_different_hash_seeds():
    a = _run("1")
    b = _run("12345")
    assert a == b, f"VaR differs across processes (non-reproducible): {a!r} vs {b!r}"
    # sanity: the run actually produced non-trivial numbers
    assert all(float(x) >= 0 for x in a.split("|"))
