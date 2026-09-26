"""SFTP access keys: which public keys may log in to an organisation's drop folders.

A key is checked before it is stored: an OpenSSH public key line of an accepted type whose encoded key actually
decodes and names the same type; RSA must be at least 3072 bits (NIST/BSI guidance for keys in use beyond 2030).
Its SHA-256 fingerprint (as `ssh-keygen -lf` prints it) identifies it; the same active key can't be registered twice
(an active key belongs to one organisation only). Keys are revoked, never deleted. The SFTP server (go-live #13) is
configured from `authorized_keys()`.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import struct
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

ACCEPTED = {"ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521", "ssh-rsa"}
MIN_RSA_BITS = 3072


class SftpKeyError(ValueError):
    pass


def _read_string(blob: bytes, off: int) -> tuple[bytes, int]:
    if off + 4 > len(blob):
        raise SftpKeyError("the key data is cut short")
    (n,) = struct.unpack(">I", blob[off:off + 4])
    if off + 4 + n > len(blob):
        raise SftpKeyError("the key data is cut short")
    return blob[off + 4:off + 4 + n], off + 4 + n


def parse(line: str) -> dict:
    """An OpenSSH public-key line → {key_type, public_key (type + base64, no comment), fingerprint, bits, comment}."""
    parts = (line or "").strip().split()
    if len(parts) < 2:
        raise SftpKeyError("Paste the whole public key line, e.g. 'ssh-ed25519 AAAAC3Nza… name@host'.")
    ktype, b64 = parts[0], parts[1]
    if ktype not in ACCEPTED:
        raise SftpKeyError(f"Key type '{ktype}' is not accepted. Use ssh-ed25519 (preferred), ECDSA, or RSA ≥ {MIN_RSA_BITS} bits.")
    try:
        blob = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise SftpKeyError("The key's encoded part is not valid.")
    inner, off = _read_string(blob, 0)
    if inner.decode("ascii", "replace") != ktype:
        raise SftpKeyError("The key's encoded part does not match its type.")
    bits: Optional[int] = None
    if ktype == "ssh-rsa":
        _e, off = _read_string(blob, off)
        n, off = _read_string(blob, off)
        bits = int.from_bytes(n, "big").bit_length()
        if bits < MIN_RSA_BITS:
            raise SftpKeyError(f"This RSA key is {bits} bits; at least {MIN_RSA_BITS} is required (or use ssh-ed25519).")
    elif ktype == "ssh-ed25519":
        pk, off = _read_string(blob, off)
        if len(pk) != 32:
            raise SftpKeyError("This ed25519 key is malformed.")
        bits = 256
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return {"key_type": ktype, "public_key": f"{ktype} {b64}", "fingerprint": fp, "bits": bits,
            "comment": " ".join(parts[2:]) or None}


def add(session: Session, org_id: str, label: str, line: str, user_id: str) -> dict:
    label = (label or "").strip()
    if not label:
        raise SftpKeyError("Give the key a label (which system uses it).")
    k = parse(line)
    taken = session.execute(text("SELECT 1 FROM intake_sftp_keys WHERE fingerprint = :f AND revoked_at IS NULL"),
                            {"f": k["fingerprint"]}).first()
    if taken:
        raise SftpKeyError("This key is already registered. Each system should have its own key.")
    kid = session.execute(text("""
        INSERT INTO intake_sftp_keys (org_id, label, key_type, public_key, fingerprint, bits, created_by)
        VALUES (CAST(:o AS uuid), :l, :t, :p, :f, :b, CAST(:u AS uuid)) RETURNING key_id::text
    """), {"o": org_id, "l": label[:80], "t": k["key_type"], "p": k["public_key"], "f": k["fingerprint"], "b": k["bits"],
           "u": user_id}).scalar()
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=user_id, action="sftp_key.add", target_type="sftp_key",
                target_id=kid, detail={"label": label, "fingerprint": k["fingerprint"], "type": k["key_type"]})
    return {"key_id": kid, "label": label, **{x: k[x] for x in ("key_type", "fingerprint", "bits")}}


def revoke(session: Session, org_id: str, key_id: str, user_id: str) -> bool:
    r = session.execute(text("""
        UPDATE intake_sftp_keys SET revoked_at = now(), revoked_by = CAST(:u AS uuid)
        WHERE key_id = CAST(:k AS uuid) AND org_id = CAST(:o AS uuid) AND revoked_at IS NULL RETURNING fingerprint
    """), {"k": key_id, "o": org_id, "u": user_id}).scalar()
    if r:
        from api.services.rbac import write_audit
        write_audit(session, org_id=org_id, actor_user_id=user_id, action="sftp_key.revoke", target_type="sftp_key",
                    target_id=key_id, detail={"fingerprint": r})
    return bool(r)


def list_keys(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT k.key_id::text, k.label, k.key_type, k.fingerprint, k.bits, k.created_at, u.email AS created_by, k.revoked_at
        FROM intake_sftp_keys k LEFT JOIN users u ON u.user_id = k.created_by
        WHERE k.org_id = CAST(:o AS uuid) ORDER BY k.revoked_at NULLS FIRST, k.created_at DESC
    """), {"o": org_id}).mappings().all()
    return [{**dict(r), "created_at": str(r["created_at"])[:19], "revoked_at": str(r["revoked_at"])[:19] if r["revoked_at"] else None}
            for r in rows]


def authorized_keys(session: Session, org_id: str) -> str:
    """The organisation's active keys as an OpenSSH authorized_keys file for the SFTP server (no shell, no forwarding)."""
    rows = session.execute(text("""SELECT key_id::text, public_key FROM intake_sftp_keys
                                   WHERE org_id = CAST(:o AS uuid) AND revoked_at IS NULL ORDER BY created_at"""),
                           {"o": org_id}).all()
    return "".join(f"restrict {pk} tellumen-key:{kid}\n" for kid, pk in rows)
