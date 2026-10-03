"""SFDR product disclosures — the pre-contractual and periodic templates of Delegated Regulation (EU) 2022/1288
(Annexes II–V, every version: family sfdr_product), filled item by item from the governing specification.

Each printed item of a template is either fixed wording (printed as captured), computed from the fund's frozen
book, or answered by the manager (template_answers, keyed by the item's id). Nothing is typed here about what the
template says: the items, their order and wording come from the spec; this module only says how each is filled
(binding) and fills it (build).

Computed, from the frozen book:
  * the product's name and LEI
  * the Yes / No of 'sustainable investment objective' — the product's SFDR classification (Art. 9 / Art. 8)
  * periodic only — the top investments (Art. 52: the fifteen largest over the reference period, averaged over the
    position dates held in it), the economic sectors with the fossil-fuel share (Art. 54 / 61), the Taxonomy-alignment
    graphs (Art. 55 / 62: each investee's own turnover / CapEx / OpEx KPIs, value-weighted, split into fossil gas,
    nuclear and the rest, with and without sovereign exposures) and the fossil gas / nuclear Yes / No
An investee whose KPIs are not on file adds nothing to the aligned share (it is never assumed aligned), nor does one
whose DNSH or minimum-safeguards attestation is explicitly false (services.issuer_taxonomy.gate_failures — the same
gate as the PAI statement); the share of value that states its KPIs is shown with the graph.
"""
from __future__ import annotations

from datetime import date

import services.regspec as R

FAMILY = "sfdr_product"
BASES = ("turnover", "capex", "opex")
# the items filled from the book, per document; every other item to fill is the manager's answer
_COMPUTED = {"product_name", "lei", "q_sust_obj", "q_sust_obj.yes", "q_sust_obj.no"}
_COMPUTED_PERIODIC = {"q_top_inv", "table_top_inv", "q_proportion.sectors", "chart_tax_incl", "chart_tax_excl",
                      "q_taxonomy.fossil_nuclear", "q_taxonomy.fossil_nuclear.yes", "q_taxonomy.fossil_nuclear.yes.fossil_gas",
                      "q_taxonomy.fossil_nuclear.yes.nuclear", "q_taxonomy.fossil_nuclear.no"}
TOP_N = 15      # Art. 52(1) / 59: 'the fifteen investments constituting the largest proportion of investments'


def document_of(template_id: str) -> str:
    return "precontractual" if template_id in ("AII", "AIII") else "periodic"


def binding(spec: dict) -> dict:
    """{template: {'items': {item_id: 'computed' | 'input'}}} for every item to fill of every template."""
    out = {}
    for t in spec["templates"]:
        computed = _COMPUTED | (_COMPUTED_PERIODIC if document_of(t["id"]) == "periodic" else set())
        out[t["id"]] = {"items": {i["id"]: ("computed" if i["id"] in computed else "input")
                                  for i in R.items_to_fill(t)}}
    return out


# ───────────────────────────── the frozen book ─────────────────────────────

def freeze(session, org_id: str, fund_id: str, document: str, period_end: date) -> dict:
    """What a filing of this fund's document freezes: the fund, its holdings over the reference period (each position
    date) with each investee's Taxonomy KPIs, and the manager's answers."""
    from sqlalchemy import text

    from ml.regulatory.sfdr_pai import SOVEREIGN_ASSET_CLASSES
    from services.asset_manager_engine import fund_descendant_ids
    from services.fund_disclosure import _is_fossil_fuel_nace
    fund = dict(session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.lei, f.sfdr_classification, f.base_currency,
               o.name AS manager, o.lei AS manager_lei
        FROM funds f JOIN organizations o ON o.org_id = f.org_id WHERE f.fund_id = CAST(:f AS uuid)"""),
        {"f": fund_id}).mappings().one())
    start = date(period_end.year, 1, 1)
    ids = fund_descendant_ids(session, fund_id)
    # the reference period's position dates (periodic); the latest holdings (pre-contractual: the current portfolio)
    dates = [r[0] for r in session.execute(text("""
        SELECT DISTINCT as_of_date FROM fund_positions WHERE fund_id = ANY(:ids)
          AND (:periodic = false OR as_of_date BETWEEN :s AND :e) ORDER BY 1"""),
        {"ids": ids, "periodic": document == "periodic", "s": start, "e": period_end})]
    if document != "periodic":
        dates = dates[-1:]
    rows = session.execute(text("""
        SELECT p.as_of_date, i.issuer_id::text AS issuer_id, i.name AS issuer, i.country, i.nace_code, s.asset_class,
               CAST(p.market_value_eur AS FLOAT) AS value
        FROM fund_positions p JOIN securities s ON s.security_id = p.security_id JOIN issuers i ON i.issuer_id = s.issuer_id
        WHERE p.fund_id = ANY(:ids) AND p.as_of_date = ANY(:d)"""), {"ids": ids, "d": dates}).mappings().all()
    from services.issuer_taxonomy import gate_failures
    from services.issuer_taxonomy import kpis as investee_kpis
    ids = sorted({r["issuer_id"] for r in rows})
    kpis, failing = investee_kpis(session, org_id, ids, period_end.year), gate_failures(session, org_id, ids)
    holdings = [{"date": r["as_of_date"].isoformat(), "issuer_id": r["issuer_id"], "issuer": r["issuer"],
                 "country": r["country"], "nace": r["nace_code"], "asset_class": r["asset_class"],
                 "sovereign": r["asset_class"] in SOVEREIGN_ASSET_CLASSES, "fossil_fuel": _is_fossil_fuel_nace(r["nace_code"]),
                 "value": r["value"] or 0.0, "kpi": kpis.get(r["issuer_id"]),
                 "gate_failed": r["issuer_id"] in failing} for r in rows]
    from services.governance.template_answers import read
    answers = read(session, org_id, FAMILY, document, fund_id=fund_id,
                   period_end=period_end if document == "periodic" else None)
    return {"fund": fund, "document": document, "period": {"start": start.isoformat(), "end": period_end.isoformat()},
            "position_dates": [d.isoformat() for d in dates], "holdings": holdings, "answers": answers}


# ───────────────────────────── computed figures ─────────────────────────────

def _averaged(holdings: list[dict]) -> list[dict]:
    """One line per investee: its value averaged over the position dates of the reference period."""
    dates = sorted({h["date"] for h in holdings}) or [None]
    by: dict = {}
    for h in holdings:
        g = by.setdefault(h["issuer_id"], {**h, "value": 0.0})
        g["value"] += h["value"] / len(dates)
    return list(by.values())


def top_investments(book: dict) -> list[dict]:
    lines = _averaged(book["holdings"])
    total = sum(h["value"] for h in lines) or 0.0
    lines.sort(key=lambda h: -h["value"])
    # keyed by the table's own columns (Annex IV / V: Largest investments | Sector | % Assets | Country)
    return [{"table_top_inv.largest": h["issuer"], "table_top_inv.sector": h["nace"],
             "table_top_inv.assets": round(100 * h["value"] / total, 2) if total else None,
             "table_top_inv.country": h["country"]} for h in lines[:TOP_N]]


def sectors(book: dict) -> dict:
    """The economic sectors (NACE section / division) of the investments, and the share in the fossil-fuel sector."""
    from services.reference import nace as _nace
    lines = _averaged(book["holdings"])
    total = sum(h["value"] for h in lines) or 0.0
    by: dict = {}
    for h in lines:
        hit = _nace.lookup(h["nace"]) if h["nace"] else None
        key = f"{hit['dotted'][:2]} {hit.get('label', '')}".strip() if hit else "sector not stated"
        by[key] = by.get(key, 0.0) + h["value"]
    return {"sectors": [{"sector": k, "pct": round(100 * v / total, 2)} for k, v in sorted(by.items(), key=lambda x: -x[1])] if total else [],
            "fossil_fuel_pct": round(100 * sum(h["value"] for h in lines if h["fossil_fuel"]) / total, 2) if total else None}


def taxonomy(book: dict) -> dict:
    """The Taxonomy-alignment graphs: per KPI basis, the share of investments aligned — fossil gas, nuclear, the rest
    — and not aligned, including and excluding sovereign exposures; the excluding graph's share of total investments."""
    lines = _averaged(book["holdings"])
    total = sum(h["value"] for h in lines)
    non_sov = [h for h in lines if not h["sovereign"]]
    base_ex = sum(h["value"] for h in non_sov)

    def graph(pop, base):
        out = {}
        for b in BASES:
            def part(k):
                """A measure over the population: None when no investee states it (blank, never 0); an investee
                failing the DNSH / safeguards gate counts nothing as aligned."""
                stated = [h for h in pop if ((h["kpi"] or {}).get(b) or {}).get(k) is not None]
                if not stated:
                    return None
                return sum(h["value"] * h["kpi"][b][k] / 100.0 for h in stated if not h.get("gate_failed"))
            gas, nuc, al = part("fossil_gas"), part("nuclear"), part("aligned")
            known = sum(h["value"] for h in pop if ((h["kpi"] or {}).get(b) or {}).get("aligned") is not None)

            def pct(v):
                return round(100 * v / base, 2) if (base and v is not None) else None
            out[b] = {"fossil_gas": pct(gas), "nuclear": pct(nuc),
                      "aligned_other": pct(al - (gas or 0.0) - (nuc or 0.0)) if al is not None else None,
                      "aligned": pct(al), "not_aligned": pct(base - (al or 0.0)) if base else None,
                      "transitional": pct(part("transitional")), "enabling": pct(part("enabling")),
                      "kpi_coverage": pct(known) if base else None}
        return out
    return {"incl": graph(lines, total), "excl": graph(non_sov, base_ex),
            "excl_share_of_total": round(100 * base_ex / total, 2) if total else None}


_FROM_HOLDINGS = ("q_top_inv", "table_top_inv", "q_proportion.sectors", "chart_tax_incl", "chart_tax_excl")


def _computed(item_id: str, book: dict, tax: dict | None) -> dict | None:
    fund, art = book["fund"], book["fund"]["sfdr_classification"]
    if item_id in _FROM_HOLDINGS and not book["holdings"]:
        return None                                  # no holdings in the reference period: nothing to show, not an empty table
    if item_id == "product_name":
        return {"text": fund["name"]}
    if item_id == "lei":
        return {"text": fund["lei"]} if fund.get("lei") else None
    if item_id == "q_sust_obj.yes":
        return {"ticked": art == "article_9"}
    if item_id == "q_sust_obj.no":
        return {"ticked": art == "article_8"}
    if item_id == "table_top_inv":
        return {"rows": top_investments(book)}
    if item_id == "q_proportion.sectors":
        return sectors(book)
    if item_id in ("chart_tax_incl", "chart_tax_excl"):
        g = tax["incl" if item_id.endswith("incl") else "excl"]
        return {"graph": g, **({"share_of_total": tax["excl_share_of_total"]} if item_id.endswith("excl") else {})}
    if item_id.startswith("q_taxonomy.fossil_nuclear"):
        # facts only (E142): an investee's aligned share counts toward the product's Taxonomy-aligned investments; a part
        # of it stated as fossil gas or nuclear (2022/1214 Annex XII) above 0 answers 'yes' for that part; 'no' for a part
        # needs it stated for every aligned share above 0 (nothing aligned is nothing of it). An aligned share without its
        # parts is never read as 'no' — that box stays open.
        cells = [((h["kpi"] or {}).get(b) or {}) for h in book["holdings"] if not h.get("gate_failed") for b in BASES]
        cells = [c for c in cells if c.get("aligned") is not None]

        def part(m):
            if any((c.get(m) or 0) > 0 for c in cells):
                return True
            return False if cells and all(c["aligned"] == 0 or c.get(m) is not None for c in cells) else None
        gas, nuc = part("fossil_gas"), part("nuclear")
        either = True if gas or nuc else (False if gas is False and nuc is False else None)
        box = {"q_taxonomy.fossil_nuclear": either,
               "q_taxonomy.fossil_nuclear.yes": either, "q_taxonomy.fossil_nuclear.yes.fossil_gas": gas,
               "q_taxonomy.fossil_nuclear.yes.nuclear": nuc, "q_taxonomy.fossil_nuclear.no": None if either is None else not either}
        v = box.get(item_id)
        if v is None:
            return None
        return {"answered": True} if item_id == "q_taxonomy.fossil_nuclear" else {"ticked": v}
    if item_id in ("q_sust_obj", "q_top_inv"):
        return {"answered": True}                   # a question answered by its computed children
    return None


def build(spec: dict, template_id: str, book: dict) -> list[dict]:
    """Every item of the template in reading order: fixed wording as printed; items to fill with their value, source
    and status ('filled', or 'missing' with what is needed)."""
    t = R.template(spec, template_id)
    b = binding(spec)[template_id]["items"]
    tax = taxonomy(book) if document_of(template_id) == "periodic" else None
    out = []
    for i in t["items"]:
        row = {k: i.get(k) for k in ("id", "kind", "label", "parent", "instruction", "blank")}
        src = b.get(i["id"])
        if src is None:
            row.update(source="fixed", status="printed")
        elif src == "computed":
            v = _computed(i["id"], book, tax)
            row.update(source="computed", value=v, status="filled" if v is not None else "missing",
                       needs=None if v is not None else _needs(i["id"]))
        else:
            v = book["answers"].get(i["id"])
            row.update(source="input", value=v, status="filled" if v is not None else "missing",
                       needs=None if v is not None else "the manager's answer")
        out.append(row)
    return out


def _needs(item_id: str) -> str:
    if item_id in _FROM_HOLDINGS:
        return "the fund's holdings in the reference period (none on file)"
    if item_id == "lei":
        return "the product's legal entity identifier (fund LEI)"
    if item_id.startswith("q_taxonomy.fossil_nuclear"):
        return ("the fossil gas and nuclear parts of every investee's aligned share (Delegated Regulation (EU) 2022/1214 "
                "Annex XII; holdings upload: taxonomy_fossil_gas_aligned_pct, taxonomy_nuclear_aligned_pct)")
    return "data on file"
