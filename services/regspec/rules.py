"""Reference rule files on the change route — rules the platform applies that are not a template (E78).

A spec (services.regspec) captures a template; some rules govern how every template is computed instead — which
entities a group filing consolidates, for one. They are quoted from the governing texts, and where a text sets no rule
of its own the file says so and carries the reading Tellumen declares. They are signed the same way as a spec: two
different people sign the file's exact sha256 (signoff.py), so any edit voids the sign-off, and a filing stamps the sha
it was computed on. The engineering sign-off is refused while `check` finds a problem.

  load     the file, with its sha256 as `_sha256`
  check    every reason the file cannot be signed (a quote not in the official texts, a ref its regime does not hold,
           a declared reading without its wording, a group framework without a rule)
  card     the file shaped as an entry of the spec register, for the sign-off screen
"""
from __future__ import annotations

import json
from pathlib import Path

from services.regspec import SpecError, sha256_of

_REF = Path(__file__).resolve().parents[2] / "data" / "reference"
# (framework, version) → file. The version names the file; a sign-off is on its sha, so an edit always needs re-signing.
RULES: dict[tuple[str, str], Path] = {
    ("consolidation", "regimes"): _REF / "consolidation" / "regimes.json",
}


def is_rule(framework: str, version: str) -> bool:
    return (framework, version) in RULES


def load(framework: str, version: str) -> dict:
    p = RULES.get((framework, version))
    if p is None or not p.exists():
        raise SpecError(f"no rule file {framework}/{version}")
    return {**json.loads(p.read_text()), "_sha256": sha256_of(p), "framework": framework, "version": version,
            "status": "adopted"}


def _quote_parts(q: str) -> list[str]:
    return [x.strip() for x in q.split("…") if x.strip()]


def check(doc: dict) -> list[str]:
    """Every reason the consolidation rule file cannot be signed (empty = it can)."""
    from services.governance.filings import GROUP_FRAMEWORKS
    from services.reference import legal_texts
    errs: list[str] = []
    regimes, frameworks = doc.get("regimes") or {}, doc.get("frameworks") or {}
    for name, r in regimes.items():
        if set(r.get("factors") or {}) != {"full", "proportional", "equity"}:
            errs.append(f"{name}: factors must give full, proportional and equity")
        if any(v not in ("full", "proportional", "excluded") for v in (r.get("factors") or {}).values()):
            errs.append(f"{name}: a factor is not one of full / proportional / excluded")
        for x in r.get("refs") or []:
            if not all(legal_texts.contains(p) for p in _quote_parts(x.get("quote") or "")) or not x.get("quote"):
                errs.append(f"{name}: '{x.get('ref')}' is not found word for word in the official texts")
    for fw, e in frameworks.items():
        reg = regimes.get(e.get("regime"))
        if reg is None:
            errs.append(f"{fw}: unknown regime '{e.get('regime')}'")
            continue
        held = {x["ref"] for x in reg.get("refs") or []}
        if not e.get("refs") or any(r not in held for r in e["refs"]):
            errs.append(f"{fw}: cites a ref its regime does not quote")
        if e.get("basis") not in ("text", "declared"):
            errs.append(f"{fw}: basis must be 'text' or 'declared'")
        d = e.get("declaration")
        if e.get("basis") == "declared" and not (d and d.get("reading") and d.get("declared_by") and d.get("declared")):
            errs.append(f"{fw}: a declared reading needs its wording, who declared it and when")
        if e.get("basis") == "text" and d:
            errs.append(f"{fw}: a rule set by the text carries no declaration")
    for fw in sorted(GROUP_FRAMEWORKS - set(frameworks)):
        errs.append(f"{fw}: can be filed for a group but has no consolidation rule")
    return errs


def card(doc: dict) -> dict:
    """The rule file as an entry of the spec register: its declared readings are its interpretations."""
    from services.governance.filings import FRAMEWORKS
    errs = check(doc)
    return {"name": doc.get("title") or doc["framework"], "act": doc["act"], "applies": doc["applies"],
            "legal_basis": doc.get("legal_basis") or {}, "capture": doc.get("capture"),
            "interpretations": [{"subject": FRAMEWORKS.get(fw, {}).get("label", fw), "reading": e["declaration"]["reading"],
                                 "basis": e["declaration"].get("why") or "the text that governs this filing sets no consolidation scope of its own",
                                 "declared_by": e["declaration"]["declared_by"]}
                                for fw, e in (doc.get("frameworks") or {}).items() if e.get("basis") == "declared"],
            "templates": [], "coverage": {"complete": not errs, "missing": errs, "stale": [], "invalid": []},
            "diff_from_previous": None}
