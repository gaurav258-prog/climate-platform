"""No ingestion adapter may fabricate observations with a random generator.

Audit finding: `services/ingestion/adapters/flood_sources.py` produced gauge/precip rows via
`np.random.gamma` / `np.random.normal` and wrote them to the DB as if real (it was dead code —
not in ACTIVE_ADAPTERS, no landing table — but importable and mislabelled "real/free"). The whole
platform's credibility is that a number is never fabricated. This test scans the ingestion adapters
for random-generation patterns so that failure mode can never be reintroduced.
"""
from __future__ import annotations

import pathlib
import re

ADAPTERS_DIR = pathlib.Path(__file__).resolve().parents[2] / "services" / "ingestion"

# random-generation calls that would synthesise observation values
_FORBIDDEN = re.compile(r"\b(np\.random|numpy\.random|random\.(gauss|normal|gamma|uniform|random|randint))\b")


def test_ingestion_never_generates_random_observations():
    offenders = []
    for py in ADAPTERS_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _FORBIDDEN.search(line):
                offenders.append(f"{py.relative_to(ADAPTERS_DIR.parents[1])}:{i}: {line.strip()}")
    assert not offenders, (
        "ingestion code uses a random generator to produce values — fabrication risk:\n"
        + "\n".join(offenders)
    )
