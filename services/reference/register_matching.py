"""EEA industrial register sites proposed to issuers by name, and a person's decision on each (the product owner's
decisions of 2026-10-23). The EEA's register names each facility's parent company only by its name — no identifier — so
a name match is never used until a person confirms it.

A facility (functional in the register's latest reporting year) is proposed to an issuer when the parent company it
names is, letter for letter once case, accents, punctuation and spacing are set aside, a name GLEIF records (legal name,
other names, transliterated names) of the issuer itself or of an entity GLEIF records the issuer consolidates (its
ultimate or direct children: data/datasets/gleif_relations, scripts/fetch_gleif_relations.py). Nothing else proposes a
match: a similar name, a shared word or a shared country never does.

  normalise(name)                     the comparison form of a name
  entity_names(doc)                   {comparison form: (lei, name as GLEIF writes it, relation)} for one issuer
  candidates(session)                 the proposals for every issuer (no database writes)
  stage(session, proposals)           record them as pending candidates (one per issuer and facility)
  decide(session, id, user, org, ok)  a person's decision: confirmed → the facility becomes the issuer's site (weight not
                                      stated, match_basis 'reviewed_name'); rejected → kept as rejected, never proposed
                                      again; audited either way
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.reference.register_sites import ROOT, RegisterError, checked_files, manifest, record

RULE = "the parent company the register names is a name GLEIF records for this entity, once case, accents, " \
       "punctuation and spacing are set aside"
FUNCTIONAL = "functional"


def normalise(name: Optional[str]) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _names(entity: dict) -> list[str]:
    e = entity.get("attributes", {}).get("entity", {})
    out = [(e.get("legalName") or {}).get("name")]
    out += [o.get("name") for o in e.get("otherNames") or []]
    out += [o.get("name") for o in e.get("transliteratedOtherNames") or []]
    return [n for n in out if n]


def entity_names(doc: dict) -> dict[str, tuple[str, str, str]]:
    """{comparison form: (LEI, legal name, relation)} for the issuer ('issuer') and every entity GLEIF records it
    consolidates ('consolidated_entity'). A comparison form shared by two different entities is ambiguous and dropped."""
    out: dict[str, set] = defaultdict(set)
    rows = [(doc["record"], "issuer")] if doc.get("record") else []
    rows += [(c, "consolidated_entity") for c in (doc.get("ultimate_children") or []) + (doc.get("direct_children") or [])]
    for ent, relation in rows:
        legal = (ent.get("attributes", {}).get("entity", {}).get("legalName") or {}).get("name")
        for n in _names(ent):
            k = normalise(n)
            if len(k) >= 3:
                out[k].add((ent["id"], legal, relation))
    return {k: next(iter(v)) for k, v in out.items() if len({x[0] for x in v}) == 1}


def _gleif_docs() -> dict[str, dict]:
    docs = {}
    for p in checked_files("gleif_issuer_relations", r"\.json$"):
        d = json.loads(p.read_text(encoding="utf-8"))
        docs[d["lei"]] = d
    return docs


def candidates(session: Session) -> dict:
    """{proposals: [...], counts: {...}, vintage} — every functional EEA facility whose named parent company is, by the
    rule, a name of an issuer or of an entity it consolidates."""
    from services.reference.register_sites import issuers_by_lei
    eea_entry = manifest("eea_industrial_sites")
    (path,) = checked_files("eea_industrial_sites", r"^ProductionFacility_RY\d{4}\.json$")
    rows = json.loads(path.read_text(encoding="utf-8"))
    vintage = f"reporting year {eea_entry['reporting_year']}, read {eea_entry['read_at'][:10]}"
    by_name: dict[str, list[dict]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.get("status") != FUNCTIONAL:
            counts[f"not functional ({r.get('status')})"] += 1
            continue
        if r.get("x_4326") is None or r.get("y_4326") is None:
            counts["no coordinates"] += 1
            continue
        k = normalise(r.get("parentCompanyName"))
        if len(k) >= 3:
            by_name[k].append(r)
    leis = issuers_by_lei(session)
    proposals = []
    for lei, doc in _gleif_docs().items():
        for k, (ent_lei, legal, relation) in entity_names(doc).items():
            for r in by_name.get(k, []):
                for issuer_id in leis.get(lei, []):
                    proposals.append({
                        "issuer_id": issuer_id, "register": "eea_ied", "register_ref": f"eea_ied:{r['localId']}",
                        "register_vintage": vintage, "name": (r.get("facilityName") or "")[:300] or None,
                        "latitude": float(r["y_4326"]), "longitude": float(r["x_4326"]),
                        "country": r.get("countryCode"), "owner_named": r["parentCompanyName"][:300],
                        "matched_lei": ent_lei, "matched_name": legal[:300], "relation": relation, "rule": RULE,
                        "site_facts": {"register": "EEA industrial register (IED / E-PRTR)", "facility_id": r["id"],
                                       "local_id": r["localId"], "site_id": r.get("siteId"),
                                       "activity": r.get("EPRTRAnnexIMainActivity"), "type": r.get("facilityType"),
                                       "city": r.get("city"), "reporting_year": r.get("reportingYear"),
                                       "owner_named": r["parentCompanyName"], "owner_url": r.get("parentCompanyURL")}})
                    counts[relation] += 1
    return {"proposals": proposals, "counts": dict(counts), "vintage": vintage}


def stage(session: Session, proposals: list[dict]) -> dict:
    """Record proposals as pending candidates; one already recorded (pending, confirmed or rejected) is left as it is."""
    added = 0
    for p in proposals:
        got = session.execute(text("""
            INSERT INTO issuer_site_candidates (issuer_id, register, register_ref, register_vintage, name, latitude,
                                                longitude, country, site_facts, owner_named, matched_lei, matched_name,
                                                relation, rule)
            VALUES (CAST(:issuer_id AS uuid), :register, :register_ref, :register_vintage, :name, :latitude, :longitude,
                    :country, CAST(:facts AS jsonb), :owner_named, :matched_lei, :matched_name, :relation, :rule)
            ON CONFLICT (issuer_id, register, register_ref) DO NOTHING RETURNING candidate_id"""),
            {**p, "facts": json.dumps(p["site_facts"])}).first()
        added += 1 if got else 0
    return {"proposed": len(proposals), "added": added, "held": len(proposals) - added}


class DecisionError(ValueError):
    def __init__(self, code: str, **params) -> None:
        self.code, self.params = code, params
        super().__init__(code)


def decide(session: Session, candidate_id: str, user_id: str, org_id: Optional[str], confirm: bool,
           note: Optional[str] = None) -> dict:
    """A person's decision on one pending candidate, audited. Confirmed: the facility is recorded as the issuer's site
    (services.reference.register_sites.record: weight not stated, match_basis 'reviewed_name') and its cell is returned
    for scoring. A decided candidate cannot be decided again."""
    from api.services.rbac import write_audit
    c = session.execute(text("""SELECT * FROM issuer_site_candidates WHERE candidate_id = CAST(:c AS uuid) FOR UPDATE"""),
                        {"c": candidate_id}).mappings().first()
    if c is None:
        raise DecisionError("sites.review.error.not_found")
    if c["status"] != "pending":
        raise DecisionError("sites.review.error.decided")
    facility_id, cells = None, {}
    if confirm:
        country = (c["country"] or "").strip().upper()
        from services.reference.iso_country import to_iso2
        got = record(session, [{
            "issuer_id": str(c["issuer_id"]), "source": c["register"], "source_ref": c["register_ref"],
            "name": (c["name"] or c["owner_named"])[:200], "facility_type": "production_facility",
            "latitude": c["latitude"], "longitude": c["longitude"], "country": to_iso2(country),
            "owner_share": None, "match_basis": "reviewed_name",
            "site_facts": {**c["site_facts"], "matched_lei": c["matched_lei"], "matched_name": c["matched_name"],
                           "relation": c["relation"], "rule": c["rule"]}}])
        cells = got["cells"]
        facility_id = session.execute(text("""
            SELECT facility_id::text FROM issuer_facilities
            WHERE issuer_id = :i AND source = :s AND source_ref = :r AND match_basis IS NOT NULL"""),
            {"i": c["issuer_id"], "s": c["register"], "r": c["register_ref"]}).scalar()
        if facility_id is None:
            raise RegisterError("the confirmed site was not recorded")
    session.execute(text("""
        UPDATE issuer_site_candidates SET status = :st, decided_by = CAST(:u AS uuid), decided_at = now(), note = :n,
               facility_id = CAST(:f AS uuid)
        WHERE candidate_id = CAST(:c AS uuid)"""),
        {"st": "confirmed" if confirm else "rejected", "u": user_id, "n": note, "f": facility_id, "c": candidate_id})
    write_audit(session, org_id=org_id, actor_user_id=user_id,
                action="issuer_site.confirm" if confirm else "issuer_site.reject",
                target_type="issuer_site_candidate", target_id=candidate_id,
                detail={"issuer_id": str(c["issuer_id"]), "register_ref": c["register_ref"], "owner_named": c["owner_named"],
                         "matched_lei": c["matched_lei"], "facility_id": facility_id, "note": note})
    return {"candidate_id": candidate_id, "status": "confirmed" if confirm else "rejected", "facility_id": facility_id,
            "cells": cells}


__all__ = ["RULE", "candidates", "decide", "entity_names", "normalise", "stage", "ROOT"]
