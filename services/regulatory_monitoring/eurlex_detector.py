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

# framework id -> the CELEX acts we track for it: the governing act FIRST (its legal dates drive the outlook's
# verified date), then any key amending / related acts so a change to either is caught. Acts without a single
# clean CELEX (e.g. TCFD guidance) are omitted — the outlook falls back to the curated library for those.
FRAMEWORK_CELEX: dict[str, list[str]] = {
    "bank_tcfd": ["32021R2178"],
    "reit_tcfd": ["32021R2178"],
    "bank_p3esg": ["32022R2453", "32024R3172"],   # the 2022 ITS and the 2024 ITS that replaced it
    "sfdr_pai": ["32022R1288", "32019R2088"],    # RTS + base SFDR
    "csrd_e1": ["32023R2772", "32022L2464"],     # ESRS Delegated Act + CSRD Directive
    "esrs_pack": ["32023R2772", "32022L2464"],
    "insurer_climate": ["32009L0138"],
    "insurer_solvency": ["32009L0138"],          # S.26.01 NatCat SCR — Solvency II
    "reit_taxonomy": ["32021R2178"],             # Art. 8 KPIs — Taxonomy Disclosures DA
    "eudr_dds": ["32023R1115", "32024R3234"],    # EUDR + the application-date amendment
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


_RELATIONS = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?rel ?eif ?inforce ?title WHERE {
  ?target cdm:resource_legal_id_celex "%s"^^<http://www.w3.org/2001/XMLSchema#string> .
  { ?w cdm:resource_legal_repeals_resource_legal ?target . BIND("repeals" AS ?rel) }
  UNION { ?w cdm:resource_legal_implicitly_repeals_resource_legal ?target . BIND("implicitly_repeals" AS ?rel) }
  UNION { ?w cdm:resource_legal_amends_resource_legal ?target . BIND("amends" AS ?rel) }
  ?w cdm:resource_legal_id_celex ?celex .
  OPTIONAL { ?w cdm:resource_legal_date_entry-into-force ?eif }
  OPTIONAL { ?w cdm:resource_legal_in-force ?inforce }
  OPTIONAL { ?e cdm:expression_belongs_to_work ?w ; cdm:expression_title ?title ;
             cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> }
}"""


def _query_relations(celex: str, timeout: float = 40.0) -> list[dict] | None:
    """The acts that amend or repeal `celex`, as the register states them — None if the source can't be reached."""
    try:
        import requests
        r = requests.get(_ENDPOINT, params={"query": _RELATIONS % celex, "format": "application/sparql-results+json"},
                         timeout=timeout, headers={"Accept": "application/sparql-results+json"})
        if r.status_code != 200:
            return None
        rows = (r.json().get("results") or {}).get("bindings") or []
    except Exception:
        return None
    acts: dict[tuple, dict] = {}
    for b in rows:
        key = (b["celex"]["value"], b["rel"]["value"])
        a = acts.setdefault(key, {"related_celex": key[0], "relation": key[1], "entry_into_force": set(),
                                  "in_force": None, "title": None})
        if "eif" in b:
            a["entry_into_force"].add(b["eif"]["value"])
        if "inforce" in b:
            a["in_force"] = b["inforce"]["value"] in ("true", "1", "yes")
        if "title" in b and not a["title"]:
            a["title"] = " ".join(b["title"]["value"].split())
    return [{**a, "entry_into_force": sorted(a["entry_into_force"])} for a in acts.values()]


def scan_relations(session: Session) -> dict:
    """Refresh which acts amend or replace every tracked act. A relation seen for the first time is a detected change
    (pending review) against each framework filed under the act. The first scan of an act records its existing
    amendments as the baseline, quietly; an act that replaces it is raised even then — a successor is never silent."""
    from services.governance.reg_reference import REFERENCE
    celex_fw: dict[str, list[str]] = {}
    for fw, acts in FRAMEWORK_CELEX.items():
        for cx in acts:
            celex_fw.setdefault(cx, []).append(fw)
    new, errors = [], []
    for cx, fws in celex_fw.items():
        rels = _query_relations(cx)
        if rels is None:
            errors.append(cx)
            continue
        baseline = session.execute(text("SELECT 1 FROM reg_act_relation WHERE celex=:c LIMIT 1"), {"c": cx}).first() is None
        for rel in rels:
            seen = session.execute(text("""SELECT 1 FROM reg_act_relation WHERE celex=:c AND related_celex=:r AND relation=:k"""),
                                   {"c": cx, "r": rel["related_celex"], "k": rel["relation"]}).first()
            session.execute(text("""
                INSERT INTO reg_act_relation (celex, related_celex, relation, title, entry_into_force, in_force)
                VALUES (:c, :r, :k, :t, CAST(:e AS jsonb), :i)
                ON CONFLICT (celex, related_celex, relation) DO UPDATE SET title = COALESCE(EXCLUDED.title, reg_act_relation.title),
                    entry_into_force = EXCLUDED.entry_into_force, in_force = EXCLUDED.in_force, last_seen_at = now()
            """), {"c": cx, "r": rel["related_celex"], "k": rel["relation"], "t": rel["title"],
                   "e": json.dumps(rel["entry_into_force"]), "i": rel["in_force"]})
            if seen or (baseline and rel["relation"] == "amends"):
                continue
            new.append((cx, rel["related_celex"], rel["relation"]))
            verb = "replaces" if rel["relation"] != "amends" else "amends"
            for fw in fws:
                label = (REFERENCE.get(fw) or {}).get("official_name") or fw
                session.execute(text("""INSERT INTO reg_detected_change (framework, celex, title, summary, effective_date, url)
                                        VALUES (:f, :c, :t, :s, :d, :u)"""),
                                {"f": fw, "c": rel["related_celex"],
                                 "t": f"{label} — a new act {verb} {cx}",
                                 "s": f"{rel['title'] or rel['related_celex']} {verb} the act this framework is filed under "
                                      f"(entry into force {', '.join(rel['entry_into_force']) or 'not stated'}).",
                                 "d": min(rel["entry_into_force"]) if rel["entry_into_force"] else None,
                                 "u": f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{rel['related_celex']}"})
    session.commit()
    return {"checked": len(celex_fw), "new_relations": new, "errors": errors}


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
    """Query every tracked act (one row per CELEX), update its snapshot, and record any that moved. A single act
    used by several frameworks (e.g. the Taxonomy DA) records a detected change against each of them."""
    from services.governance.reg_reference import REFERENCE
    celex_fw: dict[str, list[str]] = {}
    for fw, acts in FRAMEWORK_CELEX.items():
        for cx in acts:
            celex_fw.setdefault(cx, []).append(fw)
    baselines, changed, unchanged, errors = [], [], [], []
    for cx, fws in celex_fw.items():
        sig = _query_cellar(cx)
        if sig is None:
            errors.append(cx)
            continue
        fp = _fingerprint(sig)
        prev = session.execute(text("SELECT fingerprint, signal FROM reg_source_snapshot WHERE celex=:c"),
                               {"c": cx}).mappings().first()
        if prev is None:
            session.execute(text("""INSERT INTO reg_source_snapshot (celex, framework, fingerprint, signal)
                                    VALUES (:c,:f,:fp, CAST(:s AS jsonb))"""),
                            {"c": cx, "f": fws[0], "fp": fp, "s": json.dumps(sig)})
            baselines.append(cx)
        elif prev["fingerprint"] != fp:
            old = prev["signal"] or {}
            old_eif = ", ".join(old.get("entry_into_force") or []) or "—"
            new_eif = ", ".join(sig["entry_into_force"]) or "—"
            for fw in fws:
                label = (REFERENCE.get(fw) or {}).get("official_name") or fw
                session.execute(text("""INSERT INTO reg_detected_change (framework, celex, title, summary, effective_date, url)
                                        VALUES (:f,:c,:t,:s,:d,:u)"""),
                                {"f": fw, "c": cx,
                                 "t": f"{label} — legal dates changed at source",
                                 "s": f"EUR-Lex now lists entry-into-force {new_eif} (was {old_eif}).",
                                 "d": _next_effective(sig["entry_into_force"]),
                                 "u": f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{cx}"})
            session.execute(text("""UPDATE reg_source_snapshot
                                    SET fingerprint=:fp, signal=CAST(:s AS jsonb), checked_at=now(), updated_at=now()
                                    WHERE celex=:c"""),
                            {"c": cx, "fp": fp, "s": json.dumps(sig)})
            changed.append(cx)
        else:
            session.execute(text("UPDATE reg_source_snapshot SET checked_at=now() WHERE celex=:c"), {"c": cx})
            unchanged.append(cx)
    session.commit()
    return {"checked": len(celex_fw), "baselines": baselines, "changed": changed,
            "unchanged": unchanged, "errors": errors}


def verified_dates(session: Session) -> dict:
    """Per-framework live-verified legal dates — from the framework's PRIMARY (governing) act's snapshot."""
    snaps = {r["celex"]: r for r in
             session.execute(text("SELECT celex, signal, checked_at FROM reg_source_snapshot")).mappings()}
    out: dict[str, dict] = {}
    for fw, acts in FRAMEWORK_CELEX.items():
        r = snaps.get(acts[0])
        if not r:
            continue
        sig = r["signal"] or {}
        out[fw] = {"celex": acts[0], "in_force": sig.get("in_force"),
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
