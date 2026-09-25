"""Static security inspection, malware-scan client and write-once storage (services/intake)."""
from __future__ import annotations

import io
import os
import socket
import struct
import threading
import zipfile

import pytest

from services.intake import malware, security, storage

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
CSV = b"asset_name,latitude,longitude\nA,48.1,2.3\nB,48.2,2.4\n"


def _xlsx(extra: dict[str, bytes] | None = None) -> bytes:
    from openpyxl import Workbook
    buf = io.BytesIO()
    wb = Workbook(); wb.active.append(["asset_name", "latitude"]); wb.active.append(["A", 48.1]); wb.save(buf)
    if not extra:
        return buf.getvalue()
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            z.writestr(i, src.read(i.filename))
        for name, data in extra.items():
            z.writestr(name, data)
    return out.getvalue()


def _codes(rep):
    return {f["code"] for f in rep["findings"]}


def test_clean_csv_and_xlsx_pass():
    assert security.inspect(CSV, "book.csv")["status"] == "passed"
    r = security.inspect(_xlsx(), "book.xlsx")
    assert r["status"] == "passed" and r["detected_type"] == "xlsx"


def test_macros_embedded_objects_and_activex_are_blocked():
    assert "macros" in _codes(security.inspect(_xlsx({"xl/vbaProject.bin": b"x"}), "b.xlsx"))
    assert "embedded_objects" in _codes(security.inspect(_xlsx({"xl/embeddings/oleObject1.bin": b"x"}), "b.xlsx"))
    assert "activex" in _codes(security.inspect(_xlsx({"xl/activeX/activeX1.xml": b"x"}), "b.xlsx"))
    r = security.inspect(_xlsx({"xl/externalLinks/externalLink1.xml": b"x"}), "b.xlsx")
    assert r["status"] == "warned" and "external_links" in _codes(r)


def test_real_type_must_match_the_name():
    assert "type_mismatch" in _codes(security.inspect(_xlsx(), "book.csv"))
    assert "type_mismatch" in _codes(security.inspect(CSV, "book.xlsx"))
    assert "unsupported_format" in _codes(security.inspect(CSV, "book.xls"))
    assert "unsupported_format" in _codes(security.inspect(CSV, "book.exe"))
    assert "unsupported_format" in _codes(security.inspect(_xlsx(), "book.xlsx", allowed=("csv",)))


def test_legacy_or_encrypted_office_and_binaries_are_blocked():
    assert "encrypted_or_legacy" in _codes(security.inspect(security.OLE_MAGIC + b"\0" * 600, "book.xlsx"))
    assert "not_a_table" in _codes(security.inspect(b"MZ\x90\x00\x03\x00\x00\x00" * 50, "book.csv"))
    assert "empty" in _codes(security.inspect(b"", "book.csv"))


def test_compression_bomb_is_blocked():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("xl/workbook.xml", "<x/>")
        z.writestr("xl/worksheets/sheet1.xml", b"\0" * (20 * 1024 * 1024))
    assert "compression_bomb" in _codes(security.inspect(out.getvalue(), "b.xlsx"))


def test_too_large_is_blocked(monkeypatch):
    monkeypatch.setattr(security.settings, "INTAKE_MAX_BYTES", 10)
    assert "too_large" in _codes(security.inspect(CSV, "book.csv"))


def test_formula_like_cells_warn_but_negative_numbers_do_not():
    r = security.inspect(b"name,value\n=HYPERLINK(\"x\"),1\n@SUM(A1),2\n-5,3\n+3.2,4\n", "book.csv")
    assert r["status"] == "warned"
    assert "2 cell(s)" in r["findings"][0]["message"]
    assert security.inspect(b"name,value\nA,-5\nB,+3.2\n", "book.csv")["status"] == "passed"


# ── malware client, against a minimal clamd speaking the real INSTREAM protocol ──

@pytest.fixture()
def fake_clamd(monkeypatch):
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def serve():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                c, _ = srv.accept()
            except OSError:
                continue
            with c:
                cmd = b""
                while not cmd.endswith(b"\0"):
                    cmd += c.recv(1)
                if cmd == b"zVERSION\0":
                    c.sendall(b"ClamAV 1.4.1/27000\0"); continue
                data = b""
                while True:
                    (n,) = struct.unpack("!L", c.recv(4, socket.MSG_WAITALL))
                    if n == 0:
                        break
                    data += c.recv(n, socket.MSG_WAITALL)
                c.sendall(b"stream: Eicar-Test-Signature FOUND\0" if EICAR in data else b"stream: OK\0")
    t = threading.Thread(target=serve, daemon=True); t.start()
    monkeypatch.setattr(malware.settings, "CLAMD_HOST", "127.0.0.1")
    monkeypatch.setattr(malware.settings, "CLAMD_PORT", port)
    monkeypatch.setattr(malware.settings, "CLAMD_SOCKET", "")
    yield port
    stop.set(); srv.close()


def test_scan_clean_and_infected(fake_clamd):
    ok = malware.scan(CSV)
    assert ok["status"] == "clean" and ok["engine"].startswith("ClamAV")
    bad = malware.scan(b"name\n" + EICAR * 3)
    assert bad["status"] == "infected" and bad["signature"] == "Eicar-Test-Signature"


def test_scan_unreachable_is_error_and_unset_is_not_configured(monkeypatch):
    monkeypatch.setattr(malware.settings, "CLAMD_HOST", "127.0.0.1")
    monkeypatch.setattr(malware.settings, "CLAMD_PORT", 1)
    monkeypatch.setattr(malware.settings, "CLAMD_SOCKET", "")
    assert malware.scan(CSV)["status"] == "error"
    monkeypatch.setattr(malware.settings, "CLAMD_HOST", "")
    assert malware.scan(CSV)["status"] == "not_configured"


def test_scan_required_everywhere_but_development(monkeypatch):
    monkeypatch.setattr(malware.settings, "INTAKE_REQUIRE_MALWARE_SCAN", None)
    monkeypatch.setattr(malware.settings, "APP_ENV", "production")
    assert malware.scan_required() is True
    monkeypatch.setattr(malware.settings, "APP_ENV", "development")
    assert malware.scan_required() is False
    monkeypatch.setattr(malware.settings, "INTAKE_REQUIRE_MALWARE_SCAN", True)
    assert malware.scan_required() is True


# ── write-once storage ──

def test_storage_is_write_once_content_addressed_and_tamper_evident(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.settings, "INTAKE_STORAGE_DIR", str(tmp_path))
    sha, uri = storage.put(CSV)
    assert uri == f"local://{sha}" and storage.get(sha) == CSV
    assert storage.put(CSV) == (sha, uri)                       # idempotent, never rewritten
    p = storage._path_for(sha)
    assert oct(os.stat(p).st_mode & 0o777) == "0o440"          # read-only once written
    os.chmod(p, 0o640); p.write_bytes(b"tampered"); os.chmod(p, 0o440)
    with pytest.raises(storage.StorageError, match="does not match"):
        storage.get(sha)
    with pytest.raises(storage.StorageError):
        storage._path_for("../../etc/passwd")


def test_unknown_storage_backend_fails_loudly(monkeypatch):
    monkeypatch.setattr(storage.settings, "INTAKE_STORAGE_BACKEND", "s3")
    with pytest.raises(storage.StorageError, match="not available"):
        storage.put(CSV)
