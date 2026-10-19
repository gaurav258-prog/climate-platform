"""Four-eyes sign-off of a spec file (the change route, step 7).

A spec is approved when two different people have signed its exact bytes (sha256): one as regulatory reviewer (the
text matches the official act), one as engineer (the implementation covers it). The database refuses the same person
signing twice for one file, and a sign-off names the sha it saw — so editing the file voids every earlier sign-off
without anyone having to remember to revoke it. Sign-offs are append-only.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

import services.regspec as R
from core import messages
from services.regspec import rules as RULES

ROLES = ("regulatory", "engineering")


class SignoffError(ValueError):
    """A refused sign-off: the English cause for the log, and the catalogue code (with its values) the screen shows."""
    def __init__(self, message: str, code: str, **params):
        super().__init__(message)
        self.code, self.params = code, params


def _document(framework: str, version: str) -> dict:
    """A template spec, or a reference rule file on the same route (services.regspec.rules)."""
    return RULES.load(framework, version) if RULES.is_rule(framework, version) else R.load(framework, version)


def status(session: Session, framework: str, version: str) -> dict:
    spec = _document(framework, version)
    rows = session.execute(text("""
        SELECT s.role, s.sha256, s.signed_at, s.note, s.sole_reviewer, u.email, u.full_name, s.user_id::text AS user_id
        FROM regspec_signoff s JOIN users u ON u.user_id = s.user_id
        WHERE s.framework = :f AND s.version = :v ORDER BY s.seq"""), {"f": framework, "v": version}).mappings().all()
    current = [dict(r) | {"signed_at": r["signed_at"].isoformat()} for r in rows if r["sha256"] == spec["_sha256"]]
    voided = [dict(r) | {"signed_at": r["signed_at"].isoformat()} for r in rows if r["sha256"] != spec["_sha256"]]
    roles = {r["role"] for r in current}
    return {"framework": framework, "version": version, "sha256": spec["_sha256"], "status": spec["status"],
            "signed": current, "voided_by_edit": voided, "needs": [r for r in ROLES if r not in roles],
            "approved": roles == set(ROLES),
            # a team of one may sign both roles only by declaring it; the record never passes that off as four eyes
            "one_person": roles == set(ROLES) and len({r["user_id"] for r in current}) == 1}


SOLE_NOTE = "Sole reviewer: the same person signed both roles; this is not a four-eyes review."


def sign(session: Session, framework: str, version: str, role: str, user_id: str, sha256: str, note: str | None = None,
         sole_reviewer: bool = False) -> dict:
    """Sign the file as `role`. `sha256` is the hash the signer reviewed — refused if the file has changed since.
    `sole_reviewer` declares that the person who signed the other role is signing this one too (a team of one)."""
    if role not in ROLES:
        raise SignoffError(f"role must be one of {ROLES}", "regchange.spec.error.role")
    spec = _document(framework, version)
    if sha256 != spec["_sha256"]:
        raise SignoffError("the file has changed since you reviewed it — review the current version", "regchange.spec.error.changed")
    if role == "engineering" and RULES.is_rule(framework, version):
        problems = RULES.check(spec)
        if problems:
            raise SignoffError("the rule file does not pass its checks yet: " + "; ".join(problems[:8]),
                                  "regchange.spec.error.checks", n=len(problems))
    elif role == "engineering":
        from services.regspec.bindings import binding_for
        b = binding_for(framework, spec)
        cov = R.coverage(spec, b) if b is not None else None
        if spec["status"] == "adopted" and (cov is None or not cov["complete"]):
            gaps = [] if cov is None else cov["missing"] + cov["stale"] + cov["invalid"]
            raise SignoffError("the implementation does not cover this spec yet: "
                               + ("no binding" if cov is None else ", ".join(gaps[:8])),
                               "regchange.spec.error.not_covered", n=len(gaps) if cov is not None else _cells(spec))
    st = status(session, framework, version)
    if any(s["role"] == role for s in st["signed"]):
        raise SignoffError(f"already signed as {role}", "regchange.spec.error.already_signed",
                           role=messages.name("regchange.role", role))
    if sole_reviewer and not any(s["user_id"] == user_id for s in st["signed"]):
        raise SignoffError("a sole-reviewer declaration is for signing the second role after signing the first yourself",
                           "regchange.spec.error.sole_first")
    if sole_reviewer:
        note = f"{SOLE_NOTE} {note or ''}".strip()
    try:
        with session.begin_nested():
            session.execute(text("""
                INSERT INTO regspec_signoff (framework, version, sha256, role, user_id, note, sole_reviewer)
                VALUES (:f, :v, :h, :r, CAST(:u AS uuid), :n, :sole)"""),
                {"f": framework, "v": version, "h": sha256, "r": role, "u": user_id, "n": (note or None), "sole": sole_reviewer})
    except Exception as e:  # noqa: BLE001 — the unique index is the four-eyes rule
        if "ux_regspec_signoff_person" in str(e):
            raise SignoffError("the second sign-off must be by a different person — or, if you are the only reviewer, "
                               "declare it (sole reviewer)", "regchange.spec.error.same_person") from e
        raise
    return status(session, framework, version)


def _cells(spec: dict) -> int:
    """The rows, columns and items to fill of a spec's templates: what a binding must map."""
    return sum(len(t.get("rows") or []) + len(t.get("columns") or []) if t["structure"] == "full"
               else len(R.items_to_fill(t)) if t["structure"] == "document" else 0 for t in spec["templates"])


def _named(spec: dict) -> dict:
    return {t["id"]: {"code": t.get("code") or t["id"], "title": t["title"]} for t in spec["templates"]}


def _coverage_by_template(spec: dict, cov: dict | None, prev: dict | None) -> list[dict]:
    """What a binding does not cover, counted per template (its printed code and title), never as cell keys. A template
    the binding still maps but this version dropped is named from the version before."""
    if cov is None:
        return []
    names, out = {**(_named(prev) if prev else {}), **_named(spec)}, {}
    for kind in ("missing", "stale", "invalid"):
        for key in cov[kind]:
            tid = key.split(".", 1)[0].split(" ", 1)[0]
            row = out.setdefault(tid, {**names.get(tid, {"code": tid, "title": None}), "missing": 0, "stale": 0, "invalid": 0})
            row[kind] += 1
    return list(out.values())


def _diff_view(prev: dict, spec: dict, df: dict) -> dict:
    """The diff in counts and template names, for the screen: what the new version adds, removes and changes."""
    old, new = _named(prev), _named(spec)
    axes = ("rows", "columns", "items")
    count = {a: {k: sum(len((c.get(a) or {}).get(k) or []) for c in df["changed"]) for k in ("added", "removed", "relabelled", "moved")}
             for a in axes}
    return {"kind_label": messages.name("regchange.diff", df["kind"]),
            "templates": {"added": len(df["templates_added"]), "removed": len(df["templates_removed"]),
                          "changed": len(df["changed"]), "unchanged": len(df["unchanged"])},
            "cells": count,
            "added": [new[t] for t in df["templates_added"]], "removed": [old[t] for t in df["templates_removed"]],
            "changed": [{**new[c["id"]], "title_changed": "title" in c, "moved": "ref" in c,
                         **{a: {k: len((c.get(a) or {}).get(k) or []) for k in ("added", "removed", "relabelled", "moved")}
                            for a in axes if c.get(a)}} for c in df["changed"]],
            "legal_basis": df["legal_basis"]}


def overview(session: Session) -> list[dict]:
    """Every spec, its sign-off state, and the diff from the version before it — with customer names for every code
    (the family's name, the deciding date, the roles, the kind of change) and coverage counted per template."""
    from services.regspec.bindings import binding_for
    out = []
    for fw in R.frameworks():
        prev = None
        name = R.family_name(fw)
        for s in R.versions(fw):
            st = status(session, fw, s["version"])
            b = binding_for(fw, s)
            cov = R.coverage(s, b) if b is not None else None
            df = R.diff(prev, s) if prev else None
            out.append({**st, "name": name, "act": s["act"],
                        "applies": {**s["applies"], "basis_label": messages.name("regchange.basis", s["applies"]["basis"])},
                        "legal_basis": s["legal_basis"], "capture": s.get("capture"), "interpretations": s.get("interpretations") or [],
                        "templates": [{"id": t["id"], "code": t.get("code"), "title": t["title"], "structure": t["structure"]}
                                      for t in s["templates"]],
                        "coverage": cov, "coverage_by_template": _coverage_by_template(s, cov, prev),
                        "uncovered": None if cov is None else len(cov["missing"]) + len(cov["stale"]) + len(cov["invalid"]),
                        "checks": None, "diff_from_previous": df, "diff": _diff_view(prev, s, df) if df else None})
            prev = s
    for (fw, v) in RULES.RULES:
        doc = RULES.load(fw, v)
        card = RULES.card(doc)
        failing = len(card["coverage"]["missing"])
        out.append({**status(session, fw, v), **card,
                    "applies": {**card["applies"], "basis_label": messages.name("regchange.basis", card["applies"]["basis"])},
                    "coverage_by_template": [], "uncovered": None, "diff": None,
                    "checks": {"failing": failing,
                               "message": messages.render("regchange.spec.checks_failing", n=failing) if failing else None}})
    for e in out:
        e["needs_labels"] = [messages.name("regchange.role", r) for r in e["needs"]]
        for g in e["signed"] + e["voided_by_edit"]:
            g["role_label"] = messages.name("regchange.role", g["role"])
    return out


def signed_on(session: Session, framework: str, version: str, sha256: str) -> dict:
    """The sign-off of one exact version of a file (the sha a filing stamped) — it stays what it was after later edits."""
    rows = session.execute(text("""
        SELECT s.role, s.sole_reviewer, s.signed_at, s.user_id::text AS user_id, u.full_name, u.email
        FROM regspec_signoff s JOIN users u ON u.user_id = s.user_id
        WHERE s.framework = :f AND s.version = :v AND s.sha256 = :h ORDER BY s.seq"""),
        {"f": framework, "v": version, "h": sha256}).mappings().all()
    signed = [{"role": r["role"], "by": r["full_name"] or r["email"], "signed_at": r["signed_at"].isoformat(),
               "sole_reviewer": r["sole_reviewer"]} for r in rows]
    roles = {r["role"] for r in rows}
    return {"sha256": sha256, "signed": signed, "approved": roles == set(ROLES),
            "one_person": roles == set(ROLES) and len({r["user_id"] for r in rows}) == 1}
