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

ROLES = ("regulatory", "engineering")


class SignoffError(ValueError):
    pass


def status(session: Session, framework: str, version: str) -> dict:
    spec = R.load(framework, version)
    rows = session.execute(text("""
        SELECT s.role, s.sha256, s.signed_at, s.note, u.email
        FROM regspec_signoff s JOIN users u ON u.user_id = s.user_id
        WHERE s.framework = :f AND s.version = :v ORDER BY s.signed_at"""), {"f": framework, "v": version}).mappings().all()
    current = [dict(r) | {"signed_at": r["signed_at"].isoformat()} for r in rows if r["sha256"] == spec["_sha256"]]
    voided = [dict(r) | {"signed_at": r["signed_at"].isoformat()} for r in rows if r["sha256"] != spec["_sha256"]]
    roles = {r["role"] for r in current}
    return {"framework": framework, "version": version, "sha256": spec["_sha256"], "status": spec["status"],
            "signed": current, "voided_by_edit": voided, "needs": [r for r in ROLES if r not in roles],
            "approved": roles == set(ROLES)}


def sign(session: Session, framework: str, version: str, role: str, user_id: str, sha256: str, note: str | None = None) -> dict:
    """Sign the file as `role`. `sha256` is the hash the signer reviewed — refused if the file has changed since."""
    if role not in ROLES:
        raise SignoffError(f"role must be one of {ROLES}")
    spec = R.load(framework, version)
    if sha256 != spec["_sha256"]:
        raise SignoffError("the file has changed since you reviewed it — review the current version")
    if role == "engineering":
        from services.regspec.bindings import binding_for
        b = binding_for(framework)
        cov = R.coverage(spec, b) if b is not None else None
        if spec["status"] == "adopted" and (cov is None or not cov["complete"]):
            raise SignoffError("the implementation does not cover this spec yet: "
                               + ("no binding" if cov is None else ", ".join((cov["missing"] + cov["stale"] + cov["invalid"])[:8])))
    st = status(session, framework, version)
    if any(s["role"] == role for s in st["signed"]):
        raise SignoffError(f"already signed as {role}")
    try:
        with session.begin_nested():
            session.execute(text("""
                INSERT INTO regspec_signoff (framework, version, sha256, role, user_id, note)
                VALUES (:f, :v, :h, :r, CAST(:u AS uuid), :n)"""),
                {"f": framework, "v": version, "h": sha256, "r": role, "u": user_id, "n": (note or None)})
    except Exception as e:  # noqa: BLE001 — the unique index is the four-eyes rule
        if "ux_regspec_signoff_person" in str(e):
            raise SignoffError("the second sign-off must be by a different person") from e
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
            b = binding_for(fw)
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
    return out
