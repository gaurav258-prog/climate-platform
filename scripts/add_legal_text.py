"""Add official EU legal texts to data/sources/legal (read by services.reference.legal_texts).

Each act is fetched from the Publications Office (Cellar) by its CELEX number — content negotiation, English, XHTML —
normalised to plain text (tags removed, entities decoded, whitespace collapsed), gzipped, and recorded in manifest.json
with its source, retrieval date, checksum and title. An act already stored is left as it is unless --refresh.

  venv/bin/python scripts/add_legal_text.py 32023R1115 02023R1115-20260918 ... [--refresh]

An act Cellar does not serve by CELEX (a corrigendum) is given as CELEX=<its Cellar work URI> (from the SPARQL endpoint):
  venv/bin/python scripts/add_legal_text.py "32023R1115R(01)=http://publications.europa.eu/resource/cellar/<id>"
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

import httpx

DIR = Path(__file__).resolve().parents[1] / "data" / "sources" / "legal"
SOURCE = "http://publications.europa.eu/resource/celex/{}"
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
_TITLE_Q = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?t WHERE {{ ?w cdm:resource_legal_id_celex "{}"^^<http://www.w3.org/2001/XMLSchema#string> .
  ?e cdm:expression_belongs_to_work ?w ; cdm:expression_uses_language
     <http://publications.europa.eu/resource/authority/language/ENG> ; cdm:expression_title ?t }} LIMIT 1"""


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._skip = max(0, self._skip - 1)
        if tag == "title":
            self._in_title = False
        if tag in ("p", "div", "td", "tr", "li", "br", "h1", "h2", "h3", "h4", "table"):
            self.parts.append(" ")

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        elif not self._skip:
            self.parts.append(data)


def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s).replace(" ", " ")).strip()


def title_of(celex: str) -> str | None:
    """The act's English title as the Publications Office records it."""
    r = httpx.get(SPARQL, params={"query": _TITLE_Q.format(celex)}, timeout=60,
                  headers={"Accept": "application/sparql-results+json"})
    r.raise_for_status()
    b = r.json()["results"]["bindings"]
    return normalise(b[0]["t"]["value"]) if b else None


def fetch(url: str) -> tuple[str, str]:
    r = httpx.get(url, follow_redirects=True, timeout=120,
                  headers={"Accept": "application/xhtml+xml, text/html;q=0.9", "Accept-Language": "eng"})
    r.raise_for_status()
    p = _Text()
    p.feed(r.text)
    return normalise("".join(p.parts)), normalise("".join(p.title))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("celex", nargs="+")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    mpath = DIR / "manifest.json"
    man = json.loads(mpath.read_text())
    for arg in a.celex:
        celex, _, uri = arg.partition("=")
        url = uri or SOURCE.format(quote(celex, safe=""))
        if celex in man["texts"] and not a.refresh:
            print(f"{celex}: already stored")
            continue
        body, page_title = fetch(url)
        title = title_of(celex) or page_title
        if len(body) < 1000:
            print(f"{celex}: the text retrieved is too short ({len(body)} chars) — not stored", file=sys.stderr)
            return 1
        raw = body.encode("utf-8")
        (DIR / f"{celex}.txt.gz").write_bytes(gzip.compress(raw, mtime=0))
        man["texts"][celex] = {"title": title or celex, "celex": celex, "source": url,
                               "retrieved": date.today().isoformat(), "sha256": hashlib.sha256(raw).hexdigest(),
                               "chars": len(body)}
        man["texts"] = dict(sorted(man["texts"].items()))
        mpath.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")      # after each act: none half-stored
        print(f"{celex}: {len(body):,} chars — {title[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
