"""Shared XBRL / Inline-XBRL serialization plumbing — one core for every framework's tagger.

Each per-framework tagger (ESRS Climate & Nature pack, SFDR PAI, …) owns its own concepts, units and the
VISIBLE report table; the mechanical, identical parts — the xbrli contexts, unit measures, the ix:nonFraction
tags, the plain xbrli instance wrapper, and the Inline-XBRL (iXBRL/ESEF) HTML shell — live here, written and
validated ONCE instead of re-implemented (and diverging) per framework. The taxonomy namespace/binding is the
tagger's choice (a provisional placeholder until the official EFRAG/ESMA/EBA element map is supplied).
"""
from __future__ import annotations

XBRLI = "http://www.xbrl.org/2003/instance"
LINK = "http://www.xbrl.org/2003/linkbase"
XLINK = "http://www.w3.org/1999/xlink"
ISO4217 = "http://www.xbrl.org/2003/iso4217"
IX = "http://www.xbrl.org/2013/inlineXBRL"
LEI_SCHEME = "http://standards.iso.org/iso/17442"

DEFAULT_STYLE = (
    "body{font-family:system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#1c241f}"
    "h1{font-size:1.4rem} .meta{color:#555;font-size:.85rem}"
    "table{border-collapse:collapse;width:100%;margin-top:1rem}"
    "td,th{border-bottom:1px solid #e2ddd0;padding:.5rem;text-align:left;font-size:.9rem}"
    "td.dr{font-family:monospace;font-size:.75rem;color:#777;white-space:nowrap}"
    "td.num{text-align:right;font-variant-numeric:tabular-nums}"
    ".ix{display:none} .note{background:#fff7e6;border:1px solid #e0c98a;padding:.7rem;border-radius:6px;font-size:.8rem;margin-top:1rem}"
)


def context_instant(cid: str, scheme: str, ident: str, instant: str) -> str:
    return (f'  <xbrli:context id="{cid}">\n'
            f'    <xbrli:entity><xbrli:identifier scheme="{scheme}">{ident}</xbrli:identifier></xbrli:entity>\n'
            f'    <xbrli:period><xbrli:instant>{instant}</xbrli:instant></xbrli:period>\n'
            f'  </xbrli:context>')


def context_duration(cid: str, scheme: str, ident: str, start: str, end: str) -> str:
    return (f'  <xbrli:context id="{cid}">\n'
            f'    <xbrli:entity><xbrli:identifier scheme="{scheme}">{ident}</xbrli:identifier></xbrli:entity>\n'
            f'    <xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period>\n'
            f'  </xbrli:context>')


def unit(uid: str, measure: str) -> str:
    return f'  <xbrli:unit id="{uid}"><xbrli:measure>{measure}</xbrli:measure></xbrli:unit>'


def ix_nonfraction(qname: str, ctx: str, unit_ref: str | None, decimals: str, value) -> str:
    u = f' unitRef="{unit_ref}"' if unit_ref else ""
    return f'<ix:nonFraction name="{qname}" contextRef="{ctx}"{u} decimals="{decimals}">{value}</ix:nonFraction>'


def _ns_lines(extra_ns: dict, indent: str) -> str:
    return "".join(f'\n{indent}xmlns:{p}="{u}"' for p, u in extra_ns.items())


def xbrl_instance(extra_ns: dict, schema_ref: str, contexts: list[str], units: list[str],
                  facts: list[str], comment: str = "") -> str:
    """A well-formed plain xbrli:xbrl instance. `extra_ns` adds the taxonomy prefix(es); contexts/units/facts
    are pre-rendered fragment lists (use context_*/unit/ix helpers or raw fact strings)."""
    cblock = f"<!-- {comment} -->\n" if comment else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n{cblock}'
            f'<xbrli:xbrl xmlns:xbrli="{XBRLI}"\n'
            f'            xmlns:link="{LINK}"\n'
            f'            xmlns:xlink="{XLINK}"\n'
            f'            xmlns:iso4217="{ISO4217}"{_ns_lines(extra_ns, "            ")}>\n'
            f'  <link:schemaRef xlink:type="simple" xlink:href="{schema_ref}"/>\n'
            + "\n".join(contexts) + "\n" + "\n".join(units) + "\n" + "\n".join(facts) + "\n"
            f'</xbrli:xbrl>\n')


def ixbrl_document(*, title: str, extra_ns: dict, schema_ref: str, contexts: list[str], units: list[str],
                   body_html: str, style: str = DEFAULT_STYLE) -> str:
    """A well-formed Inline-XBRL (iXBRL/ESEF-shaped) XHTML document: the hidden ix:header carrying the
    contexts/units + schemaRef, and the framework's own visible `body_html` (which contains the ix:nonFraction
    tags). One document a person reads and a machine parses."""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml"\n'
            f'      xmlns:ix="{IX}"\n'
            f'      xmlns:xbrli="{XBRLI}"\n'
            f'      xmlns:link="{LINK}"\n'
            f'      xmlns:xlink="{XLINK}"\n'
            f'      xmlns:iso4217="{ISO4217}"{_ns_lines(extra_ns, "      ")}>\n'
            f'<head>\n  <meta charset="UTF-8"/>\n  <title>{title}</title>\n  <style>{style}</style>\n</head>\n'
            f'<body>\n'
            f'  <div style="display:none">\n    <ix:header>\n'
            f'      <ix:references><link:schemaRef xlink:type="simple" xlink:href="{schema_ref}"/></ix:references>\n'
            f'      <ix:resources>\n' + "\n".join(contexts) + "\n" + "\n".join(units) + "\n"
            f'      </ix:resources>\n    </ix:header>\n  </div>\n\n'
            f'{body_html}\n'
            f'</body>\n</html>\n')
