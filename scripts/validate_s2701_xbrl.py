"""Validate an S.27.01.01 XBRL instance with Arelle against EIOPA's Solvency II taxonomy and EIOPA's own validation rules.

    venv/bin/python -m scripts.validate_s2701_xbrl <instance.xbrl>

Needs, outside the repository (EIOPA and Eurofiling files, not redistributed here):
  EIOPA_XBRL_PACKAGE  the taxonomy package WITH external files, e.g.
                      EIOPA_SolvencyII_XBRL_Taxonomy_2.8.2_Final_with_external_files.zip (dev.eiopa.europa.eu)
  EIOPA_IAF_FILE      Eurofiling's interval-arithmetic function implementation, interval-arithmetics.xml
                      (www.eurofiling.info/eu/fr/xbrl/func/) — EIOPA's rules call iaf:* and a validator supplies it
Arelle is the arelle-release package. The functions file is linked from a validation copy of the instance (the
instance to file never carries a linkbaseRef, per the filing rules).

A rule that fails only because it needs rows outside the nat-cat part (man-made, non-proportional property, other
non-life catastrophe; the S.27.01 totals over them) is reported apart: those cells come from the undertaking's own
package. Exit 1 when any rule within the nat-cat part fails or the instance is not valid XBRL.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

_MAP = os.path.join("data", "reference", "eiopa", "s2701_xbrl.2.8.2.json")


def validate(instance_path: str, package: str | None = None, iaf: str | None = None) -> dict:
    package = package or os.environ.get("EIOPA_XBRL_PACKAGE")
    iaf = iaf or os.environ.get("EIOPA_IAF_FILE")
    if not (package and iaf and os.path.exists(package) and os.path.exists(iaf)):
        raise FileNotFoundError("set EIOPA_XBRL_PACKAGE and EIOPA_IAF_FILE to EIOPA's taxonomy package and the iaf file")
    text = open(instance_path, encoding="utf-8").read()
    at = text.index("\n", text.index("<link:schemaRef")) + 1
    link = (f'  <link:linkbaseRef xlink:type="simple" xlink:href="file://{os.path.abspath(iaf)}" '
            'xlink:arcrole="http://www.w3.org/1999/xlink/properties/linkbase"/>\n')
    with tempfile.TemporaryDirectory() as d:
        copy, log = os.path.join(d, "validation.xbrl"), os.path.join(d, "arelle.log")
        with open(copy, "w", encoding="utf-8") as f:
            f.write(text[:at] + link + text[at:])
        arelle = os.path.join(os.path.dirname(sys.executable), "arelleCmdLine")
        subprocess.run([arelle, "--file", copy, "--packages", package, "--internetConnectivity", "offline", "--validate",
                        "--formula", "run", "--formulaAsserResultCounts", "--logFile", log],
                       check=True, capture_output=True, timeout=1800)
        lines = open(log, encoding="utf-8").read().splitlines()
    ours = {k.split("|")[0] for k in json.load(open(_MAP))["cells"]}
    counts, failed = {}, {}
    for ln in lines:
        m = re.search(r"Assertion s2md_(BV[\w-]+) evaluations : (\d+) satisfied, (\d+) not satisfied", ln)
        if m and int(m.group(2)) + int(m.group(3)):
            counts[m.group(1)] = (int(m.group(2)), int(m.group(3)))
        m = re.match(r"\[message:s2md_(BV[\w-]+)\] (.*)", ln)
        if m:
            failed.setdefault(m.group(1), m.group(2))
    # errors about the instance itself (EIOPA's taxonomy files carry schema / generic-link notices of their own)
    instance_errors = [ln for ln in lines if "validation.xbrl" in ln and ln.startswith("[") and not ln.startswith(("[info", "[message", "[formula:trace"))]
    scope = {r: sorted(set(re.findall(r"r: (R\d{4})", msg)) - ours) for r, msg in failed.items()}
    return {"evaluated": counts, "instance_errors": instance_errors,
            "failed_in_scope": sorted(r for r, out in scope.items() if not out),
            "failed_needing_other_submodules": {r: out for r, out in scope.items() if out}}


if __name__ == "__main__":
    res = validate(sys.argv[1])
    print(json.dumps({**res, "evaluated": {k: list(v) for k, v in res["evaluated"].items()}}, indent=1))
    sys.exit(1 if res["failed_in_scope"] or res["instance_errors"] else 0)
