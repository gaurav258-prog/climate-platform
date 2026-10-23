"""Validate an S.27.01.01 (solo) or S.27.01.04 (group) XBRL instance with Arelle against EIOPA's Solvency II taxonomy
and EIOPA's own validation rules.

    venv/bin/python -m scripts.validate_s2701_xbrl <instance.xbrl>

The taxonomy is the one the instance's entry point belongs to: data/reference/eiopa/s2701_xbrl.<version>.json (solo,
ars) or s2704_xbrl.<version>.json (group, arg) names the package EIOPA published for it ('package': file, address, SHA-256) and EIOPA's current list of switched-off rules for
the entry point ('deactivations', published apart at dev.eiopa.europa.eu). Both are held outside the repository in
XBRL_PACKAGES_DIR/eiopa/<version>/ — scripts/fetch_xbrl_packages.py places them there and checks every checksum; a file
whose checksum is not the pinned one is refused.

EIOPA's rules call Eurofiling's functions (iaf:, mfn:, ifn:, cmf:), which a validator supplies: their implementations
are the copies inside EIOPA's own package, linked by their published addresses from a validation copy of the instance,
with EIOPA's deactivation list (the instance to file never carries a linkbaseRef, per the filing rules). Arelle is the
arelle-release package.

A rule that fails only because it needs rows outside the nat-cat part (man-made, non-proportional property, other
non-life catastrophe; the S.27.01 totals over them) is reported apart: those cells come from the undertaking's own
package. Exit 1 when any rule within the nat-cat part fails or the instance is not valid XBRL.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

_DIR = os.path.join("data", "reference", "eiopa")
_FUNC = "www.eurofiling.info/eu/fr/xbrl/func/"          # Eurofiling's function implementations, as EIOPA's package holds them


class PackageError(FileNotFoundError):
    pass


def taxonomy_of(instance_text: str) -> dict:
    """The S.27.01 map (solo S.27.01.01 / group S.27.01.04) whose entry point the instance names."""
    href = re.search(r'<link:schemaRef[^>]*xlink:href="([^"]+)"', instance_text).group(1)
    for path in sorted(glob.glob(os.path.join(_DIR, "s270[14]_xbrl.*.json"))):
        m = json.load(open(path))
        if m["entry_point"] == href:
            return m
    raise PackageError(f"no EIOPA taxonomy on file has the entry point {href}")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pinned(m: dict, key: str, root: str | None = None) -> str | None:
    """Path of the pinned file `key` ('package' / 'deactivations') of taxonomy map `m`, its checksum verified."""
    spec = m.get(key)
    if not spec:
        return None
    root = root or os.environ.get("XBRL_PACKAGES_DIR")
    if not root:
        raise PackageError("set XBRL_PACKAGES_DIR (scripts/fetch_xbrl_packages.py places EIOPA's files there)")
    path = os.path.join(root, "eiopa", m["taxonomy_version"], spec["file"])
    if not os.path.exists(path):
        raise PackageError(f"{path} is missing — run scripts/fetch_xbrl_packages.py")
    if sha256(path) != spec["sha256"]:
        raise PackageError(f"{path} is not the file EIOPA published (SHA-256 differs from the pinned one)")
    return path


def functions_in(package: str) -> list[str]:
    """Published addresses of the Eurofiling function implementations EIOPA's package carries."""
    with zipfile.ZipFile(package) as z:
        names = [n.split(_FUNC, 1)[1] for n in z.namelist() if _FUNC in n and n.endswith(".xml")]
    return [f"http://{_FUNC}{n}" for n in sorted(set(names)) if "/" not in n]


def validate(instance_path: str, root: str | None = None) -> dict:
    text = open(instance_path, encoding="utf-8").read()
    m = taxonomy_of(text)
    package = pinned(m, "package", root)
    deactivations = pinned(m, "deactivations", root)
    links = functions_in(package) + ([f"file://{os.path.abspath(deactivations)}"] if deactivations else [])
    at = text.index("\n", text.index("<link:schemaRef")) + 1
    refs = "".join(f'  <link:linkbaseRef xlink:type="simple" xlink:href="{href}" '
                   'xlink:arcrole="http://www.w3.org/1999/xlink/properties/linkbase"/>\n' for href in links)
    with tempfile.TemporaryDirectory() as d:
        copy, log = os.path.join(d, "validation.xbrl"), os.path.join(d, "arelle.log")
        with open(copy, "w", encoding="utf-8") as f:
            f.write(text[:at] + refs + text[at:])
        arelle = os.path.join(os.path.dirname(sys.executable), "arelleCmdLine")
        subprocess.run([arelle, "--file", copy, "--packages", package, "--internetConnectivity", "offline", "--validate",
                        "--formula", "run", "--formulaAsserResultCounts", "--logFile", log],
                       check=True, capture_output=True, timeout=1800)
        lines = open(log, encoding="utf-8").read().splitlines()
    ours = {k.split("|")[0] for k in m["cells"]}
    counts, failed = {}, {}
    for ln in lines:
        mm = re.search(r"Assertion s2md_(BV[\w-]+) evaluations : (\d+) satisfied, (\d+) not satisfied", ln)
        if mm and int(mm.group(2)) + int(mm.group(3)):
            counts[mm.group(1)] = (int(mm.group(2)), int(mm.group(3)))
        mm = re.match(r"\[message:s2md_(BV[\w-]+)\] (.*)", ln)
        if mm:
            failed.setdefault(mm.group(1), mm.group(2))
    # errors about the instance itself (EIOPA's taxonomy files carry schema / generic-link notices of their own)
    instance_errors = [ln for ln in lines if "validation.xbrl" in ln and ln.startswith("[") and not ln.startswith(("[info", "[message", "[formula:trace"))]
    scope = {r: sorted(set(re.findall(r"r: (R\d{4})", msg)) - ours) for r, msg in failed.items()}
    switched_off = sorted(set(re.findall(r"#s2md_(BV[\w-]+)", open(deactivations).read()))) if deactivations else []
    return {"taxonomy": m["taxonomy_version"], "package": m["package"]["file"],
            "deactivations": m["deactivations"]["published"] if deactivations else None,
            "switched_off_by_eiopa": switched_off, "functions": [h.rsplit("/", 1)[1] for h in links if h.startswith("http")],
            "evaluated": counts, "instance_errors": instance_errors,
            "failed_in_scope": sorted(r for r, out in scope.items() if not out),
            "failed_needing_other_submodules": {r: out for r, out in scope.items() if out}}


if __name__ == "__main__":
    res = validate(sys.argv[1])
    print(json.dumps({**res, "evaluated": {k: list(v) for k, v in res["evaluated"].items()}}, indent=1))
    sys.exit(1 if res["failed_in_scope"] or res["instance_errors"] else 0)
