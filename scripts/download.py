"""One way to fetch a large file for every dataset script (E173): a dropped connection costs a retry, never the run.

  remote_size(url)           (HTTP status, the file's size in bytes or None) — read with a HEAD request
  download(url, out, size)   fetch `url` to `out`, expecting `size` bytes (remote_size, read before the plan was
                             priced). A partial file (<out>.part) resumes where it stopped with an HTTP
                             Range request; a server that ignores the range restarts it. Up to `attempts` tries with a
                             growing pause; the file is renamed into place only at exactly `size` bytes. Returns
                             "fetched", "held" (already complete) or "failed: <why>" — never raises, so one file's
                             trouble is recorded against that file and the rest of the plan carries on.

Both ask for the file as stored ('Accept-Encoding: identity', E177): a server that compresses text in transit reports
the compressed length while the client hands back the uncompressed bytes, so a size taken one way never matched a file
fetched the other.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests

CHUNK = 1 << 20
IDENTITY = {"Accept-Encoding": "identity"}


def remote_size(url: str, timeout: int = 60) -> tuple[int, Optional[int]]:
    """(status code, Content-Length of the file as stored — None when the server states none)."""
    h = requests.head(url, timeout=timeout, allow_redirects=True, headers=IDENTITY)
    n = h.headers.get("Content-Length")
    return h.status_code, (int(n) if n is not None and h.status_code < 400 else None)


def download(url: str, out: Path, size: int, attempts: int = 5, timeout: int = 600, pause_s: float = 5.0) -> str:
    if out.exists() and out.stat().st_size == size:
        return "held"
    part = out.with_name(out.name + ".part")
    why = "no attempt made"
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if part.exists() else 0
        if have > size:
            part.unlink()
            have = 0
        try:
            headers = {**IDENTITY, **({"Range": f"bytes={have}-"} if have else {})}
            with requests.get(url, stream=True, timeout=timeout, headers=headers) as r:
                if r.status_code == 416 and have == size:
                    pass                                    # the partial file is already whole
                elif have and r.status_code != 206:         # the server ignored the range: start again
                    r.raise_for_status()
                    have = 0
                    with open(part, "wb") as f:
                        for chunk in r.iter_content(CHUNK):
                            f.write(chunk)
                else:
                    r.raise_for_status()
                    with open(part, "ab" if have else "wb") as f:
                        for chunk in r.iter_content(CHUNK):
                            f.write(chunk)
            got = part.stat().st_size
            if got == size:
                part.replace(out)
                return "fetched"
            why = f"{got} of {size} bytes after attempt {attempt}"
        except (requests.RequestException, OSError) as e:
            why = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
        time.sleep(pause_s * attempt)
    return f"failed: {why}"
