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
from services.regspec import rules as RULES

ROLES = ("regulatory", "engineering")


class SignoffError(ValueError):
    pass


def _document(framework: str, version: str) -> dict:
    """A template spec, or a reference rule file on the same route (services.regspec.rules)."""
    return RULES.load(framework, version) if RULES.is_rule(framework, version) else R.load(framework, version)


def status(session: Session, framework: str, version: str) -> dict:
    spec = _document(framework, version)
    rows = session.execute(text("""
        SELECT s.role, s.sha256, s.signed_at, s.note, s.sole_reviewer, u.email, u.full_name, s.user_id::text AS user_id
        FROM regspec_signoff s JOIN users u ON u.user_id = s.user_id
        WHERE s.framework = :f AND s.version = :v ORDER BY s.signed_at"""), {"f": framework, "v": version}).mappings().all()
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
        raise SignoffError(f"role must be one of {ROLES}")
    spec = _document(framework, version)
    if sha256 != spec["_sha256"]:
        raise SignoffError("the file has changed since you reviewed it — review the current version")
    if role == "engineering" and RULES.is_rule(framework, version):
        problems = RULES.check(spec)
        if problems:
            raise SignoffError("the rule file does not pass its checks yet: " + "; ".join(problems[:8]))
    elif role == "engineering":
        from services.regspec.bindings import binding_for
        b = binding_for(framework, spec)
        cov = R.coverage(spec, b) if b is not None else None
        if spec["status"] == "adopted" and (cov is None or not cov["complete"]):
            raise SignoffError("the implementation does not cover this spec yet: "
                               + ("no binding" if cov is None else ", ".join((cov["missing"] + cov["stale"] + cov["invalid"])[:8])))
    st = status(session, framework, version)
    if any(s["role"] == role for s in st["signed"]):
        raise SignoffError(f"already signed as {role}")
    if sole_reviewer and not any(s["user_id"] == user_id for s in st["signed"]):
        raise SignoffError("a sole-reviewer declaration is for signing the second role after signing the first yourself")
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
                               "declare it (sole reviewer)") from e
        raise
    return status(session, framework, version)


def overview(session: Session) -> list[dict]:
    """Every spec, its sign-off state, and the diff from the version before it."""
    out = []
    for fw in R.frameworks():
        prev = None
        for s in R.versions(fw):
            st = status(session, fw, s["version"])
            cov = None
            from services.regspec.bindings import binding_for
            b = binding_for(fw, s)
            if b is not None:
                cov = R.coverage(s, b)
            from services.governance.reg_reference import REFERENCE
            out.append({**st, "name": (REFERENCE.get(fw) or {}).get("official_name") or fw,
                        "act": s["act"], "applies": s["applies"], "legal_basis": s["legal_basis"],
                        "capture": s.get("capture"), "interpretations": s.get("interpretations") or [],
                        "templates": [{"id": t["id"], "code": t.get("code"), "title": t["title"], "structure": t["structure"]}
                                      for t in s["templates"]],
                        "coverage": cov, "diff_from_previous": R.diff(prev, s) if prev else None})
            prev = s
    for (fw, v) in RULES.RULES:
        doc = RULES.load(fw, v)
        out.append({**status(session, fw, v), **RULES.card(doc)})
    return out


def signed_on(session: Session, framework: str, version: str, sha256: str) -> dict:
    """The sign-off of one exact version of a file (the sha a filing stamped) — it stays what it was after later edits."""
    rows = session.execute(text("""
        SELECT s.role, s.sole_reviewer, s.signed_at, s.user_id::text AS user_id, u.full_name, u.email
        FROM regspec_signoff s JOIN users u ON u.user_id = s.user_id
        WHERE s.framework = :f AND s.version = :v AND s.sha256 = :h ORDER BY s.signed_at"""),
        {"f": framework, "v": version, "h": sha256}).mappings().all()
    signed = [{"role": r["role"], "by": r["full_name"] or r["email"], "signed_at": r["signed_at"].isoformat(),
               "sole_reviewer": r["sole_reviewer"]} for r in rows]
    roles = {r["role"] for r in rows}
    return {"sha256": sha256, "signed": signed, "approved": roles == set(ROLES),
            "one_person": roles == set(ROLES) and len({r["user_id"] for r in rows}) == 1}
