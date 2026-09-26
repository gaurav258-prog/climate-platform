"""Drop-folder channels (the landing side of an SFTP feed): a finished file runs through the same intake pipeline as an
upload and is filed under processed/ or refused/ (with the reason beside it); a file still being written waits.
The sweep commits per file, so each test removes what it created."""
from __future__ import annotations

import os
import time
import uuid

import pytest
from sqlalchemy import text

from core.config import settings
from core.db.session import get_session
from services.intake import dropfolder
from tests.integration.test_intake_pipeline import BANK_ORG, _csv, _landed, _purge, _rows

pytestmark = pytest.mark.integration


def _user(email):
    with get_session() as s:
        return s.execute(text("SELECT user_id::text FROM users WHERE email = :e"), {"e": email}).scalar()


@pytest.fixture()
def channel(tmp_path, monkeypatch):
    import services.tasks.jobs as jobs
    monkeypatch.setattr(settings, "INTAKE_DROP_DIR", str(tmp_path))
    monkeypatch.setattr(jobs, "submit", lambda *a, **k: {"job": "stubbed-in-test"})
    tag = uuid.uuid4().hex[:8]
    with get_session() as s:
        s.execute(text("DELETE FROM intake_channels WHERE org_id = CAST(:o AS uuid) AND template = 'bank_assets'"), {"o": BANK_ORG})
        ch = dropfolder.create_channel(s, BANK_ORG, "bank_assets", _user("admin@meridian.demo"), _user("admin@meridian.demo"))
        s.commit()
    ch["tag"], ch["dirs"] = tag, {k: tmp_path / ch["folder"] / k for k in ("incoming", "processed", "refused")}
    yield ch
    _purge(tag)
    with get_session() as s:
        s.execute(text("UPDATE ingest_batches SET channel_id = NULL WHERE channel_id = CAST(:c AS uuid)"), {"c": ch["channel_id"]})
        s.execute(text("DELETE FROM intake_channels WHERE channel_id = CAST(:c AS uuid)"), {"c": ch["channel_id"]})
        s.commit()


def _drop(ch, name, raw, age_s=120):
    p = ch["dirs"]["incoming"] / name
    p.write_bytes(raw)
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


def test_finished_file_is_imported_and_filed(channel):
    tag = channel["tag"]
    _drop(channel, f"{tag}-book.csv", _csv(_rows(tag, n=3)))
    res = dropfolder.sweep_channel(channel, BANK_ORG)
    assert [r["state"] for r in res] == ["imported"] and _landed(tag) == 3
    assert not list(channel["dirs"]["incoming"].iterdir()) and len(list(channel["dirs"]["processed"].iterdir())) == 1
    with get_session() as s:
        b = s.execute(text("SELECT b.via, b.channel_id::text, f.received_via FROM ingest_batches b JOIN intake_files f ON f.file_id = b.file_id "
                           "WHERE b.batch_id = CAST(:b AS uuid)"), {"b": res[0]["batch_id"]}).one()
    assert b == ("sftp", channel["channel_id"], "sftp")


def test_file_still_arriving_or_partial_is_left_for_the_next_sweep(channel):
    tag = channel["tag"]
    _drop(channel, f"{tag}-new.csv", _csv(_rows(tag, n=2)), age_s=0)
    _drop(channel, f"{tag}-upload.csv.part", b"asset_name\n")
    assert dropfolder.sweep_channel(channel, BANK_ORG) == []
    assert sorted(p.name for p in channel["dirs"]["incoming"].iterdir()) == sorted([f"{tag}-new.csv", f"{tag}-upload.csv.part"])


def test_failed_check_goes_to_a_second_person_with_the_owner_as_sender(channel):
    tag = channel["tag"]
    _drop(channel, f"{tag}-bad.csv", _csv(_rows(tag, n=4, bad=2)))
    res = dropfolder.sweep_channel(channel, BANK_ORG)
    assert res[0]["state"] == "awaiting_approval" and _landed(tag) == 0
    with get_session() as s:
        maker = s.execute(text("SELECT a.maker_user_id::text FROM ingest_batches b JOIN approval_requests a ON a.request_id = b.approval_request_id "
                               "WHERE b.batch_id = CAST(:b AS uuid)"), {"b": res[0]["batch_id"]}).scalar()
    assert maker == channel["owner_user_id"]


def test_unusable_file_is_refused_with_the_reason_beside_it(channel):
    tag = channel["tag"]
    _drop(channel, f"{tag}-wrong.csv", b"foo,bar\n1,2\n")
    res = dropfolder.sweep_channel(channel, BANK_ORG)
    assert res[0]["state"] == "refused" and "missing required column" in res[0]["reason"]
    names = sorted(p.name for p in channel["dirs"]["refused"].iterdir())
    assert len(names) == 2 and names[1].endswith(".reason.txt")


def test_channel_only_for_the_organisations_own_sector():
    with get_session() as s:
        with pytest.raises(dropfolder.ChannelError, match="for 'insurer'"):
            dropfolder.create_channel(s, BANK_ORG, "insurance_policies", _user("admin@meridian.demo"), _user("admin@meridian.demo"))
        s.rollback()


def test_two_pickups_at_once_never_take_the_same_file(channel):
    tag = channel["tag"]
    _drop(channel, f"{tag}-book.csv", _csv(_rows(tag, n=2)))
    with get_session() as other:   # another sweep (another server, or 'pick up now') holds this folder
        other.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), {"k": f"dropfolder:{channel['channel_id']}"})
        try:
            assert dropfolder.sweep_channel(channel, BANK_ORG)[0]["state"] == "busy"
            assert _landed(tag) == 0 and len(list(channel["dirs"]["incoming"].iterdir())) == 1
        finally:
            other.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": f"dropfolder:{channel['channel_id']}"})
    assert [r["state"] for r in dropfolder.sweep_channel(channel, BANK_ORG)] == ["imported"]


def test_an_unavailable_inbox_backend_fails_loudly(monkeypatch):
    from services.intake import inbox
    monkeypatch.setattr(settings, "INTAKE_DROP_BACKEND", "s3")
    with pytest.raises(inbox.InboxError, match="not available"):
        inbox.backend()


def test_sftp_keys_register_refuse_and_revoke(intake_client):
    from services.intake.sftp_keys import authorized_keys
    from tests.unit.test_sftp_keys import ED, RSA2048
    c, h = intake_client, intake_client.maker
    with get_session() as s:
        s.execute(text("DELETE FROM intake_sftp_keys WHERE fingerprint = 'SHA256:k8X8j55gMeYOp1yLjdkxwALAla+pSfqsYMDb0ayZoW8'"))
        s.commit()
    try:
        r = c.post("/v1/intake/sftp-keys", headers=h, json={"label": "Core banking", "public_key": ED})
        assert r.status_code == 201, r.text
        kid = r.json()["key_id"]
        assert c.post("/v1/intake/sftp-keys", headers=h, json={"label": "again", "public_key": ED}).status_code == 400
        assert "2048 bits" in c.post("/v1/intake/sftp-keys", headers=h, json={"label": "old", "public_key": RSA2048}).text
        bad = c.post("/v1/intake/sftp-keys", headers=h, json={"label": "oops", "public_key": "-----BEGIN OPENSSH PRIVATE KEY----- abc"})
        assert bad.status_code == 400 and "PRIVATE key" in bad.text
        assert [k["label"] for k in c.get("/v1/intake/sftp-keys", headers=h).json()["keys"]][:1] == ["Core banking"]
        with get_session() as s:
            assert f"tellumen-key:{kid}" in authorized_keys(s, BANK_ORG)
        assert c.delete(f"/v1/intake/sftp-keys/{kid}", headers=h).status_code == 200
        with get_session() as s:
            assert f"tellumen-key:{kid}" not in authorized_keys(s, BANK_ORG)
        assert c.get("/v1/intake/sftp-keys", headers=c.checker).status_code == 403     # admins only
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM intake_sftp_keys WHERE fingerprint = 'SHA256:k8X8j55gMeYOp1yLjdkxwALAla+pSfqsYMDb0ayZoW8'"))
            s.commit()
