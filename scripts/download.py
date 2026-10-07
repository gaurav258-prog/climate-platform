"""One way to fetch a large file for every dataset script (E173): a dropped connection costs a retry, never the run.

  download(url, out, size)   fetch `url` to `out`, expecting `size` bytes (the server's Content-Length, read before
                             the plan was priced). A partial file (<out>.part) resumes where it stopped with an HTTP
                             Range request; a server that ignores the range restarts it. Up to `attempts` tries with a
                             growing pause; the file is renamed into place only at exactly `size` bytes. Returns
                             "fetched", "held" (already complete) or "failed: <why>" — never raises, so one file's
                             trouble is recorded against that file and the rest of the plan carries on.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

CHUNK = 1 << 20


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
            headers = {"Range": f"bytes={have}-"} if have else {}
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
