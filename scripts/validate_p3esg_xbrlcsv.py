"""Validate a Pillar 3 ESG xBRL-CSV report package (EBA Pillar 3 data hub, module ESGDIS) against the EBA's taxonomy and
the EBA Filing Rules v5.8 for xBRL-CSV.

    venv/bin/python -m scripts.validate_p3esg_xbrlcsv <package.zip>

1. Arelle loads the package as xBRL-CSV against the EBA's pinned packages (data/reference/eba/p3esg_xbrlcsv.<release>.json
   'packages', held in XBRL_PACKAGES_DIR/eba/<release>/ by scripts/fetch_xbrl_packages.py, checksums verified): the
   Dictionary and Reporting Frameworks packages and the EBA's latest rule set (SET), with the Eurofiling base files the
   EBA's entry point imports taken from EIOPA's pinned 'with external files' package (the EBA's package does not carry
   them). Every fact is checked against its datapoint — type, dimensions, code-list members (XBRL 2.1, Dimensions,
   xBRL-CSV). The EBA's own assertions run too; its severity sets switch every ESGDIS assertion off, and the run says
   how many were evaluated.
2. The EBA Filing Rules v5.8 for an xBRL-CSV package, checked on the files: the file and root-folder name, the fixed
   reportPackage.json, one absolute 'extends' to the module's entry point, parameters.csv (entityID, refPeriod,
   baseCurrency and decimals only when used, decimals within rule 2.18's accuracy table), a filing indicator for every
   template of the module and no table file for a template indicated as not reported, every table's header (no empty
   cell, every column of its metadata), the same number of fields in every row, a value in every key column, no special
   value ('#…') and no decimals suffix.
Exit 1 when either finds a problem.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

from scripts.fetch_xbrl_packages import sha256

_EBA = os.path.join("data", "reference", "eba")
_EIOPA_EXTERNAL = os.path.join("data", "reference", "eiopa", "s2701_xbrl.2.8.2.json")
_NAME = re.compile(r"^(?P<subject>[A-Z0-9]{20}\.(?:IND|CON))_(?P<country>[A-Z]{2})_(?P<fw>[A-Z0-9]+?)(?P<ver>\d{6})_"
                   r"(?P<module>[A-Z0-9]+)_(?P<ref>\d{4}-\d{2}-\d{2})_(?P<stamp>\d{17})$")
_MIN_DECIMALS = {"decimalsMonetary": -6, "decimalsPercentage": 4, "decimalsInteger": 0}   # rule 2.18, Pillar3 modules


def _map_for(entry: str) -> dict:
    for f in sorted(os.listdir(_EBA)):
        m = json.load(open(os.path.join(_EBA, f)))
        if m["module"]["entry"] == entry:
            return m
    raise FileNotFoundError(f"no binding on file has the entry point {entry}")


def _pinned(root: str, publisher: str, version: str, name: str, digest: str) -> str:
    path = os.path.join(root, publisher, version, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} is missing — run scripts/fetch_xbrl_packages.py")
    if sha256(path) != digest:
        raise FileNotFoundError(f"{path} is not the file the publisher published (SHA-256 differs from the pin)")
    return path


def packages(m: dict, root: str | None = None) -> list[str]:
    """The EBA Dictionary, Reporting Frameworks and latest rule-set packages, and EIOPA's package for the Eurofiling files."""
    root = root or os.environ.get("XBRL_PACKAGES_DIR")
    if not root:
        raise FileNotFoundError("set XBRL_PACKAGES_DIR (scripts/fetch_xbrl_packages.py places the packages there)")
    members = {x["member"]: x["sha256"] for p in m["packages"] for x in p.get("extract") or []}
    want = [n for n in members if "_Dictionary_" in n or "_Reporting_Frameworks_" in n or "_SET_" in n]
    out = [_pinned(root, "eba", m["framework_release"], n, members[n]) for n in sorted(want)]
    e = json.load(open(_EIOPA_EXTERNAL))
    out.append(_pinned(root, "eiopa", e["taxonomy_version"], e["package"]["file"], e["package"]["sha256"]))
    return out


def filing_rules(path: str) -> tuple[list[str], dict]:
    """EBA Filing Rules v5.8 for xBRL-CSV, on the package's files. (problems, the binding the package names)."""
    bad: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        roots = {n.split("/")[0] for n in names}
        stem = os.path.basename(path)[:-4] if path.endswith(".zip") else os.path.basename(path)
        if roots != {stem}:
            bad.append(f"the root folder must be named as the zip file ({stem}); found {sorted(roots)}")
        root = sorted(roots)[0]
        mm = _NAME.match(root)
        if not mm:
            bad.append(f"file name '{root}' is not ReportSubject_Country_FrameworkCodeModuleVersion_Module_ReferenceDate_CreationTimestamp")
        read = {n[len(root) + 1:]: z.read(n) for n in names}
    if json.loads(read.get("META-INF/reportPackage.json", b"{}")) != {"documentInfo": {"documentType": "https://xbrl.org/report-package/2023"}}:
        bad.append("META-INF/reportPackage.json is not the fixed content")
    rep = json.loads(read.get("reports/report.json", b"{}"))
    ext = (rep.get("documentInfo") or {}).get("extends") or []
    if len(ext) != 1 or not ext[0].startswith("http"):
        bad.append("report.json must extend exactly one absolute entry point URL")
        return bad, {}
    m = _map_for(ext[0])
    mod = m["module"]
    if mm and (mm["fw"] != mod["framework_code"] or mm["ver"] != mod["file_module_version"] or mm["module"] != mod["code"]):
        bad.append(f"file name names {mm['fw']}{mm['ver']}_{mm['module']}, the entry point is "
                   f"{mod['framework_code']}{mod['file_module_version']}_{mod['code']}")

    def rows(name):
        return list(csv.reader(io.StringIO(read[name].decode("utf-8"))))
    params = rows("reports/parameters.csv") if "reports/parameters.csv" in read else []
    if not params or params[0] != ["name", "value"]:
        bad.append("parameters.csv must start with the line 'name,value'")
    p = {r[0]: r[1] for r in params[1:] if len(r) == 2}
    for need in ("entityID", "refPeriod"):
        if not p.get(need):
            bad.append(f"parameters.csv has no {need}")
    if mm and p.get("entityID") != f"rs:{mm['subject']}":
        bad.append(f"entityID {p.get('entityID')} is not the file's reporting subject rs:{mm['subject']}")
    if mm and p.get("refPeriod") != mm["ref"]:
        bad.append(f"refPeriod {p.get('refPeriod')} is not the file's reference date {mm['ref']}")
    for k, low in _MIN_DECIMALS.items():
        if k in p and (not re.fullmatch(r"-?\d+", p[k]) or int(p[k]) < low or (k == "decimalsInteger" and int(p[k]) != 0)):
            bad.append(f"{k}={p[k]} is outside rule 2.18 ({'0' if k == 'decimalsInteger' else '>= ' + str(low)})")
    fi = rows("reports/FilingIndicators.csv") if "reports/FilingIndicators.csv" in read else []
    if not fi or fi[0] != ["templateID", "reported"]:
        bad.append("FilingIndicators.csv must start with 'templateID,reported'")
    ind = {r[0]: r[1] for r in fi[1:] if len(r) == 2}
    missing = sorted(set(m["indicators"]) - set(ind))
    if missing:
        bad.append(f"rule 1.6(d): no filing indicator for {', '.join(missing)}")
    used: set[str] = set()
    for code, t in m["tables"].items():
        name = f"reports/{t['csv']}"
        if name not in read:
            continue
        if ind.get(t["indicator"]) != "true":
            bad.append(f"rule 6: {t['csv']} is in the package but {t['indicator']} is not indicated as reported")
        r = rows(name)
        keys = [k["name"] for k in t["keys"]]
        if not r or any(not h.strip() for h in r[0]) or set(r[0]) != {"datapoint", "factValue", *keys}:
            bad.append(f"rule 2: {t['csv']} header must be datapoint, factValue and every key column ({', '.join(keys) or '—'})")
            continue
        types = {e["dp"]: e["type"] for e in [*m["cells"].values(), *m["open_cells"].values()] if e["table"] == code}
        for i, row in enumerate(r[1:], 2):
            if len(row) != len(r[0]):
                bad.append(f"rule 3: {t['csv']} line {i} has {len(row)} fields, the header {len(r[0])}")
                continue
            cells = dict(zip(r[0], row))
            if any(cells[k] == "" for k in keys):
                bad.append(f"rule 4: {t['csv']} line {i} leaves a key column empty")
            if any(v.startswith("#") for v in row):
                bad.append(f"rule 5: {t['csv']} line {i} uses a special value")
            if re.fullmatch(r"-?[\d.]+d-?\d+", cells["factValue"]):
                bad.append(f"rule 1: {t['csv']} line {i} uses a decimals suffix")
            used.add(types.get(cells["datapoint"], "?"))
    if "m" in used and "baseCurrency" not in p:
        bad.append("parameters.csv has no baseCurrency, yet a fact refers to it")
    for t, k in (("m", "baseCurrency"), ("m", "decimalsMonetary"), ("p", "decimalsPercentage"), ("i", "decimalsInteger"),
                 ("r", "decimalsDecimal")):
        if k in p and t not in used and not (k == "baseCurrency" and "m" in used):
            bad.append(f"parameters.csv carries {k}, which no fact refers to")
        if t in used and k not in p:
            bad.append(f"parameters.csv has no {k}, yet a fact needs it")
    return bad, m


def validate(path: str, root: str | None = None) -> dict:
    rules, m = filing_rules(path)
    if not m:
        return {"filing_rules": rules, "xbrl_errors": [], "assertions": 0, "evaluated": 0}
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "arelle.log")
        arelle = os.path.join(os.path.dirname(sys.executable), "arelleCmdLine")
        subprocess.run([arelle, "--file", os.path.abspath(path), "--packages", "|".join(packages(m, root)),
                        "--plugins", "loadFromOIM", "--internetConnectivity", "offline", "--validate", "--formula", "run",
                        "--formulaAsserResultCounts", "--logFile", log], check=True, capture_output=True, timeout=1800)
        lines = open(log, encoding="utf-8").read().splitlines()
    errors = [ln for ln in lines if ln.startswith("[") and not ln.startswith(("[info", "[formula:trace", "[] "))]
    counts = [re.search(r"evaluations : (\d+) satisfied, (\d+) not satisfied", ln) for ln in lines]
    counts = [c for c in counts if c]
    return {"module": f"{m['module']['code']} {m['module']['version']}", "release": m["framework_release"],
            "filing_rules": rules, "xbrl_errors": errors, "assertions": len(counts),
            "evaluated": sum(1 for c in counts if int(c.group(1)) + int(c.group(2))),
            "unsatisfied": sum(int(c.group(2)) for c in counts)}


if __name__ == "__main__":
    res = validate(sys.argv[1])
    print(json.dumps(res, indent=1))
    sys.exit(1 if res["filing_rules"] or res["xbrl_errors"] or res.get("unsatisfied") else 0)
