"""Live EUR-Lex change detector — the authoritative feed behind the regulatory outlook.

For each framework's governing act (its CELEX id) this queries the EU's official Cellar SPARQL endpoint
(publications.europa.eu) for the machine-readable legal signal: the entry-into-force date(s), end-of-validity,
in-force flag and document date. It fingerprints that signal and stores it. On a later scan, if the fingerprint
has moved — e.g. an amendment added or shifted an entry-into-force date — it records a detected change (marked
'pending_review', because an auto-detected change is a prompt for a human to confirm, never presented as
settled fact). The customer outlook reads these live-verified dates and detected changes alongside the curated
library. EUR-Lex's own web pages are bot-protected, so we deliberately use the Cellar SPARQL API, not scraping.

Network- and failure-tolerant: a source that can't be reached is simply skipped (honest empty), never guessed.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

# framework id -> the governing act's CELEX (the act whose legal dates we track). Acts without a single clean
# CELEX (e.g. TCFD guidance) are omitted — the outlook falls back to the curated library for those.
FRAMEWORK_CELEX: dict[str, str] = {
    "bank_tcfd": "32021R2178", "reit_tcfd": "32021R2178",
    "bank_p3esg": "32022R2453",
    "sfdr_pai": "32022R1288",
    "csrd_e1": "32023R2772", "esrs_pack": "32023R2772",
    "insurer_climate": "32009L0138",
    "eudr_dds": "32023R1115",
}

_QUERY = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?eif ?eov ?inforce ?doc WHERE {
  ?work cdm:resource_legal_id_celex "%s"^^<http://www.w3.org/2001/XMLSchema#string> .
  OPTIONAL { ?work cdm:resource_legal_date_entry-into-force ?eif }
  OPTIONAL { ?work cdm:resource_legal_date_end-of-validity ?eov }
  OPTIONAL { ?work cdm:resource_legal_in-force ?inforce }
  OPTIONAL { ?work cdm:work_date_document ?doc }
}"""


def _query_cellar(celex: str, timeout: float = 20.0) -> dict | None:
    """The official legal signal for a CELEX, or None if the source can't be reached / parsed."""
    try:
        import requests
    except Exception:
        return None
    try:
        r = requests.get(_ENDPOINT, params={"query": _QUERY % celex, "format": "application/sparql-results+json"},
                         timeout=timeout, headers={"Accept": "application/sparql-results+json"})
        if r.status_code != 200:
            return None
        rows = (r.json().get("results") or {}).get("bindings") or []
    except Exception:
        return None
    if not rows:
        return None
    eif = sorted({b["eif"]["value"] for b in rows if "eif" in b})
    eov = next((b["eov"]["value"] for b in rows if "eov" in b), None)
    inforce = next((b["inforce"]["value"] for b in rows if "inforce" in b), None)
    doc = next((b["doc"]["value"] for b in rows if "doc" in b), None)
    return {"celex": celex, "entry_into_force": eif, "end_of_validity": eov,
            "in_force": inforce in ("true", "1", "yes"), "doc_date": doc}


def _fingerprint(sig: dict) -> str:
    return f"{sig['in_force']}|{','.join(sig['entry_into_force'])}|{sig['end_of_validity']}|{sig['doc_date']}"


def _next_effective(eif: list[str]) -> str | None:
    """The nearest entry-into-force date that is today or in the future (else the latest)."""
    if not eif:
        return None
    today = date.today().isoformat()
    future = [d for d in eif if d >= today]
    return min(future) if future else max(eif)


def scan(session: Session) -> dict:
    """Query every tracked framework's act, update snapshots, and record any that moved since last time."""
    from services.governance.reg_reference import REFERENCE
    baselines, changed, unchanged, errors = [], [], [], []
    for fw, celex in FRAMEWORK_CELEX.items():
        sig = _query_cellar(celex)
        if sig is None:
            errors.append(fw)
            continue
        fp = _fingerprint(sig)
        prev = session.execute(text("SELECT fingerprint, signal FROM reg_source_snapshot WHERE framework=:f"),
                               {"f": fw}).mappings().first()
        if prev is None:
            session.execute(text("""INSERT INTO reg_source_snapshot (framework, celex, fingerprint, signal)
                                    VALUES (:f,:c,:fp, CAST(:s AS jsonb))"""),
                            {"f": fw, "c": celex, "fp": fp, "s": json.dumps(sig)})
            baselines.append(fw)
        elif prev["fingerprint"] != fp:
            old = prev["signal"] or {}
            old_eif = ", ".join(old.get("entry_into_force") or []) or "—"
            new_eif = ", ".join(sig["entry_into_force"]) or "—"
            label = (REFERENCE.get(fw) or {}).get("official_name") or fw
            session.execute(text("""INSERT INTO reg_detected_change (framework, celex, title, summary, effective_date, url)
                                    VALUES (:f,:c,:t,:s,:d,:u)"""),
                            {"f": fw, "c": celex,
                             "t": f"{label} — legal dates changed at source",
                             "s": f"EUR-Lex now lists entry-into-force {new_eif} (was {old_eif}).",
                             "d": _next_effective(sig["entry_into_force"]),
                             "u": f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"})
            session.execute(text("""UPDATE reg_source_snapshot
                                    SET fingerprint=:fp, signal=CAST(:s AS jsonb), checked_at=now(), updated_at=now()
                                    WHERE framework=:f"""),
                            {"f": fw, "fp": fp, "s": json.dumps(sig)})
            changed.append(fw)
        else:
            session.execute(text("UPDATE reg_source_snapshot SET checked_at=now() WHERE framework=:f"), {"f": fw})
            unchanged.append(fw)
    session.commit()
    return {"checked": len(FRAMEWORK_CELEX), "baselines": baselines, "changed": changed,
            "unchanged": unchanged, "errors": errors}


def verified_dates(session: Session) -> dict:
    """Per-framework live-verified legal dates from the latest snapshot — for the outlook to show/reconcile."""
    out: dict[str, dict] = {}
    for r in session.execute(text("SELECT framework, celex, signal, checked_at FROM reg_source_snapshot")).mappings():
        sig = r["signal"] or {}
        out[r["framework"]] = {"celex": r["celex"], "in_force": sig.get("in_force"),
                               "entry_into_force": sig.get("entry_into_force") or [],
                               "next_effective": _next_effective(sig.get("entry_into_force") or []),
                               "checked_at": r["checked_at"].date().isoformat() if r["checked_at"] else None}
    return out


def detected_changes(session: Session, framework: str | None = None) -> list[dict]:
    """Open (pending/confirmed, not dismissed) detected changes — optionally for one framework."""
    q = "SELECT framework, celex, title, summary, effective_date, status, url, detected_at FROM reg_detected_change WHERE status <> 'dismissed'"
    params: dict = {}
    if framework:
        q += " AND framework=:f"
        params["f"] = framework
    q += " ORDER BY detected_at DESC"
    rows = session.execute(text(q), params).mappings().all()
    return [{"framework": r["framework"], "celex": r["celex"], "title": r["title"], "summary": r["summary"],
             "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
             "status": r["status"], "url": r["url"],
             "detected_at": r["detected_at"].date().isoformat() if r["detected_at"] else None} for r in rows]
