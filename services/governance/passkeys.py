"""WebAuthn passkeys (FIDO2) — passwordless / phishing-resistant credentials.

Full registration and authentication ceremonies via the `webauthn` library: the server issues options with a
one-time challenge, the browser's authenticator signs it, and the server verifies against the stored public key
(counter-checked to detect cloned authenticators). Additive to password + TOTP — a passkey never weakens them,
and a broken ceremony simply fails to authenticate. The actual create/get ceremony runs on a real device, so
like SSO it activates against real hardware; the option/challenge server flow is what's exercised here.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from core.config import settings

CHALLENGE_TTL_MIN = 5


class PasskeyError(ValueError):
    pass


def _rp() -> tuple[str, str]:
    origin = settings.APP_BASE_URL.rstrip("/")
    host = urlparse(origin).hostname or "localhost"
    return host, origin


def _now():
    return datetime.now(timezone.utc)


def _store_challenge(session: Session, *, ref: str, challenge: bytes, kind: str) -> None:
    session.execute(text("""
        INSERT INTO webauthn_challenge (ref, challenge, kind, expires_at)
        VALUES (:r, :c, :k, :exp)
        ON CONFLICT (ref) DO UPDATE SET challenge = :c, kind = :k, expires_at = :exp, created_at = now()
    """), {"r": ref, "c": bytes_to_base64url(challenge), "k": kind, "exp": _now() + timedelta(minutes=CHALLENGE_TTL_MIN)})
    session.commit()


def _pop_challenge(session: Session, *, ref: str, kind: str) -> bytes:
    row = session.execute(text("SELECT challenge FROM webauthn_challenge WHERE ref = :r AND kind = :k AND expires_at > now()"),
                          {"r": ref, "k": kind}).first()
    if not row:
        raise PasskeyError("challenge expired — start again")
    session.execute(text("DELETE FROM webauthn_challenge WHERE ref = :r"), {"r": ref})
    session.commit()
    return base64url_to_bytes(row[0])


def _descriptors(session: Session, user_id: str) -> list[PublicKeyCredentialDescriptor]:
    ids = session.execute(text("SELECT credential_id FROM webauthn_credential WHERE user_id = CAST(:u AS uuid)"),
                          {"u": user_id}).scalars().all()
    return [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c)) for c in ids]


# ── registration ─────────────────────────────────────────────────────────────
def registration_options(session: Session, *, user_id: str, email: str, full_name: str | None) -> dict:
    rp_id, _ = _rp()
    opts = generate_registration_options(
        rp_id=rp_id, rp_name="Tellumen", user_id=user_id.encode(), user_name=email,
        user_display_name=full_name or email, exclude_credentials=_descriptors(session, user_id))
    _store_challenge(session, ref=f"reg:{user_id}", challenge=opts.challenge, kind="register")
    return json.loads(options_to_json(opts))


def registration_verify(session: Session, *, user_id: str, credential: dict, name: str | None) -> dict:
    rp_id, origin = _rp()
    challenge = _pop_challenge(session, ref=f"reg:{user_id}", kind="register")
    try:
        v = verify_registration_response(credential=json.dumps(credential), expected_challenge=challenge,
                                         expected_rp_id=rp_id, expected_origin=origin)
    except Exception as e:  # noqa: BLE001
        raise PasskeyError(f"passkey registration failed: {e}") from e
    cid = bytes_to_base64url(v.credential_id)
    session.execute(text("""
        INSERT INTO webauthn_credential (credential_id, user_id, public_key, sign_count, name)
        VALUES (:c, CAST(:u AS uuid), :pk, :sc, :n) ON CONFLICT (credential_id) DO NOTHING
    """), {"c": cid, "u": user_id, "pk": v.credential_public_key, "sc": v.sign_count, "n": name or "Passkey"})
    session.commit()
    return {"credential_id": cid, "name": name or "Passkey"}


def list_credentials(session: Session, user_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT credential_id, name, created_at, last_used_at FROM webauthn_credential
        WHERE user_id = CAST(:u AS uuid) ORDER BY created_at
    """), {"u": user_id}).mappings().all()
    return [dict(r) for r in rows]


def delete_credential(session: Session, *, user_id: str, credential_id: str) -> bool:
    n = session.execute(text("DELETE FROM webauthn_credential WHERE credential_id = :c AND user_id = CAST(:u AS uuid)"),
                        {"c": credential_id, "u": user_id}).rowcount
    session.commit()
    return n > 0


# ── authentication (passwordless login) ──────────────────────────────────────
def _user_by_email(session: Session, email: str):
    return session.execute(text("SELECT user_id, org_id FROM users WHERE lower(email) = lower(:e) AND status = 'active'"),
                           {"e": email}).mappings().first()


def authentication_options(session: Session, email: str) -> dict | None:
    user = _user_by_email(session, email)
    if not user:
        return None
    creds = _descriptors(session, str(user["user_id"]))
    if not creds:
        return None
    rp_id, _ = _rp()
    opts = generate_authentication_options(rp_id=rp_id, allow_credentials=creds)
    _store_challenge(session, ref=f"auth:{email.lower()}", challenge=opts.challenge, kind="auth")
    return json.loads(options_to_json(opts))


def authentication_verify(session: Session, *, email: str, credential: dict) -> dict:
    user = _user_by_email(session, email)
    if not user:
        raise PasskeyError("no such account")
    rp_id, origin = _rp()
    challenge = _pop_challenge(session, ref=f"auth:{email.lower()}", kind="auth")
    cid = credential.get("id")
    row = session.execute(text("SELECT public_key, sign_count FROM webauthn_credential WHERE credential_id = :c AND user_id = CAST(:u AS uuid)"),
                          {"c": cid, "u": str(user["user_id"])}).mappings().first()
    if not row:
        raise PasskeyError("unknown passkey")
    try:
        v = verify_authentication_response(
            credential=json.dumps(credential), expected_challenge=challenge, expected_rp_id=rp_id,
            expected_origin=origin, credential_public_key=bytes(row["public_key"]),
            credential_current_sign_count=row["sign_count"])
    except Exception as e:  # noqa: BLE001
        raise PasskeyError(f"passkey verification failed: {e}") from e
    session.execute(text("UPDATE webauthn_credential SET sign_count = :sc, last_used_at = now() WHERE credential_id = :c"),
                    {"sc": v.new_sign_count, "c": cid})
    session.commit()
    return {"user_id": str(user["user_id"]), "org_id": str(user["org_id"])}
