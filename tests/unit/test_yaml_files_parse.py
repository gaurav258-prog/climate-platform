"""Every YAML file in the repository parses (E181). docs/observability/slo.yaml called itself a machine-readable target
spec, yet no YAML parser could read it: a mapping key sat inside the `slos` list at item level, and one value nested a
mapping on a single line. Nothing had ever read it, so nothing noticed."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_every_yaml_file_parses():
    files = subprocess.run(["git", "ls-files", "*.yaml", "*.yml"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    assert "docs/observability/slo.yaml" in files
    bad = []
    for f in files:
        try:
            list(yaml.safe_load_all((ROOT / f).read_text(encoding="utf-8")))
        except yaml.YAMLError as e:
            bad.append(f"{f}: {str(e).splitlines()[0]}")
    assert not bad, "YAML files that do not parse:\n" + "\n".join(bad)
