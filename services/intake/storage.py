"""Write-once, content-addressed storage for received customer files.

Every file a customer sends is kept exactly as received, addressed by its SHA-256, so that (1) we can always show
what we were given, (2) a batch held for 4-eyes approval is imported later from the SAME bytes the checks ran on,
and (3) any engine run or filing can be traced back to its source file. Stored files are never overwritten: a
second receipt of identical bytes resolves to the same object.

Only the local-directory backend exists today. An object-store backend is a go-live dependency; asking for it
fails loudly rather than silently writing somewhere else.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from core.config import settings


class StorageError(RuntimeError):
    pass


def _root() -> Path:
    if settings.INTAKE_STORAGE_BACKEND != "local":
        raise StorageError(f"Intake storage backend '{settings.INTAKE_STORAGE_BACKEND}' is not available in this build "
                           "(only 'local'). See docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md.")
    root = Path(settings.INTAKE_STORAGE_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path_for(sha256: str) -> Path:
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise StorageError("invalid content address")
    return _root() / sha256[:2] / sha256[2:4] / sha256


def put(raw: bytes) -> tuple[str, str]:
    """Store bytes; returns (sha256, storage_uri). Idempotent for identical content; never overwrites."""
    sha = hashlib.sha256(raw).hexdigest()
    path = _path_for(sha)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:   # a corrupted object must never be reused
            raise StorageError(f"stored object {sha} is corrupted")
        return sha, f"local://{sha}"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with open(tmp, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o440)   # read-only once written
    return sha, f"local://{sha}"


def get(sha256: str) -> bytes:
    """Read a stored file back, verifying it is byte-identical to what was received."""
    path = _path_for(sha256)
    if not path.exists():
        raise StorageError(f"stored file {sha256[:12]}… not found")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise StorageError(f"stored file {sha256[:12]}… does not match its fingerprint")
    return raw
