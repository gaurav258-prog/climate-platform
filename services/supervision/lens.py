"""The independent lens — a submitted template versus the same template rebuilt from granular data.

Pure functions (no DB): the router feeds them the submitted cells (as ingested), and the cells rebuilt from the
shadow book under two bases — the regulator's basis and the basis the bank states in its narrative. The gap on
each cell's "sensitive to physical risk" amount is split into four parts that add up exactly:
  scope     — exposure differs (the bank's gross amount ≠ what the granular data holds for that cell)
  basis     — scenario / horizon differ (rebuild at the bank's stated basis vs the regulator's)
  scoring   — at the same exposure and basis, the bank's sensitivity share ≠ the independent share
  coverage  — exposure the granular data could NOT locate (no region): we cannot judge it, so the bank's own
              share is assumed there and the amount is shown as unverifiable, never as a scoring gap
  unmatched — a cell present on only one side (no granular rows, or no submitted row)
Identities (ratios over LOCATED value; reb_gross = located + unlocated):
  total = rebuilt_reg.sensitive − submitted.sensitive
  scope = sub_ratio·(reb_gross − sub_gross); coverage = −sub_ratio·unlocated;
  basis = (ratio_reg − ratio_bank)·located; scoring = (ratio_bank − sub_ratio)·located
  → scope + coverage + basis + scoring = total.
Nothing here judges the bank; a flag is a question. Every result carries the precision of the rebuild.
"""
from __future__ import annotations

from typing import Iterable, Optional

from core.types import score_to_bucket

HIGH = {"H", "VH"}
FLAG_PCT_POINTS = 10.0     # sensitivity-share gap (percentage points) beyond which a cell is flagged


def cell_key(geography: str, sector: str) -> str:
    return f"{(geography or '').strip().upper()}|{(sector or '').strip().upper()}"


def rebuild_cells(points: Iterable[dict], geo_of, sector_of) -> dict[str, dict]:
    """Template cells from asset points: gross = Σ value, sensitive = Σ value of headline bucket High/Very high.
    geo_of(p) / sector_of(p) give the cell coordinates (country, NUTS region, NACE section …)."""
    cells: dict[str, dict] = {}
    for p in points:
        g, s = geo_of(p), sector_of(p)
        if not g or not s:
            continue
        c = cells.setdefault(cell_key(g, s), {"geography": g, "sector": s, "gross_carrying_amount_eur": 0.0,
                                               "sensitive_physical_eur": 0.0, "located_value_eur": 0.0, "n": 0, "n_scored": 0, "n_located": 0})
        v = float(p.get("value_eur") or 0)
        c["gross_carrying_amount_eur"] += v; c["n"] += 1
        if p.get("lat") is not None:
            c["n_located"] += 1; c["located_value_eur"] += v
        if p.get("score") is not None:
            c["n_scored"] += 1
            if score_to_bucket(float(p["score"])).value in HIGH:
                c["sensitive_physical_eur"] += v
    for c in cells.values():
        c["gross_carrying_amount_eur"] = round(c["gross_carrying_amount_eur"])
        c["sensitive_physical_eur"] = round(c["sensitive_physical_eur"])
        c["located_value_eur"] = round(c["located_value_eur"])
    return cells


def _ratio(c: Optional[dict]) -> Optional[float]:
    """Sensitive share. For rebuilt cells the denominator is the LOCATED value (what we could actually judge);
    for submitted cells it is the gross amount."""
    if not c:
        return None
    denom = c.get("located_value_eur") if "located_value_eur" in c else c.get("gross_carrying_amount_eur")
    return float(c["sensitive_physical_eur"]) / float(denom) if denom else None


def compare(submitted: dict[str, dict], rebuilt_reg: dict[str, dict], rebuilt_bank: Optional[dict[str, dict]] = None,
            precision: str = "region-resolved (NUTS-3)", basis_separable: bool = True) -> dict:
    """Cell-by-cell comparison with the four-way gap split. rebuilt_bank = rebuild at the bank's stated basis
    (None when the bank stated no basis or it equals the regulator's → basis term is 0)."""
    rebuilt_bank = rebuilt_bank or rebuilt_reg
    keys = sorted(set(submitted) | set(rebuilt_reg))
    rows = []
    tot = {"submitted": 0.0, "rebuilt": 0.0, "scope": 0.0, "coverage": 0.0, "basis": 0.0, "scoring": 0.0, "unmatched": 0.0}
    for k in keys:
        s, r, rb = submitted.get(k), rebuilt_reg.get(k), rebuilt_bank.get(k)
        row = {"key": k, "geography": (s or r)["geography"], "sector": (s or r)["sector"],
               "submitted_gross": s["gross_carrying_amount_eur"] if s else None, "submitted_sensitive": s["sensitive_physical_eur"] if s else None,
               "rebuilt_gross": r["gross_carrying_amount_eur"] if r else None, "rebuilt_sensitive": r["sensitive_physical_eur"] if r else None,
               "submitted_share_pct": (round(100 * _ratio(s), 1) if _ratio(s) is not None else None),
               "rebuilt_share_pct": (round(100 * _ratio(r), 1) if _ratio(r) is not None else None),
               "coverage_pct": (round(100.0 * r.get("located_value_eur", r["gross_carrying_amount_eur"]) / r["gross_carrying_amount_eur"], 0) if r and r["gross_carrying_amount_eur"] else None),
               "gap": {"scope": 0.0, "coverage": 0.0, "basis": 0.0, "scoring": 0.0, "unmatched": 0.0}, "flag": "ok", "reason": ""}
        if s and r:
            sub_ratio, ratio_reg = _ratio(s) or 0.0, _ratio(r) or 0.0
            ratio_bank = _ratio(rb) if rb else ratio_reg
            if ratio_bank is None:
                ratio_bank = ratio_reg
            reb_gross, sub_gross = float(r["gross_carrying_amount_eur"]), float(s["gross_carrying_amount_eur"])
            located = float(r["located_value_eur"]) if "located_value_eur" in r else reb_gross   # absent = fully located
            unlocated = reb_gross - located
            if not basis_separable:
                ratio_bank = ratio_reg
            row["gap"] = {"scope": round(sub_ratio * (reb_gross - sub_gross)), "coverage": round(-sub_ratio * unlocated),
                          "basis": round((ratio_reg - ratio_bank) * located), "scoring": round((ratio_bank - sub_ratio) * located), "unmatched": 0.0}
            if located <= 0:
                row["flag"] = "question"; row["reason"] = "None of this exposure could be located, so it cannot be verified."
            else:
                share_gap = 100 * (ratio_reg - sub_ratio)
                if abs(share_gap) >= FLAG_PCT_POINTS:
                    row["flag"] = "question"
                    dom = max(("scope", "basis", "scoring"), key=lambda g: abs(row["gap"][g]))
                    row["reason"] = {"scope": "Reported exposure differs from the granular data.",
                                     "basis": "The entity's stated scenario or horizon differs from yours.",
                                     "scoring": "The sensitivity share differs at the same exposure and basis."}[dom]
                    if unlocated > 0:
                        row["reason"] += f" ({int(round(100 * located / reb_gross))}% of this exposure located.)"
            tot["submitted"] += s["sensitive_physical_eur"]; tot["rebuilt"] += r["sensitive_physical_eur"]
        elif s and not r:
            row["gap"]["unmatched"] = -float(s["sensitive_physical_eur"]); row["flag"] = "question"; row["reason"] = "No granular data for this geography and sector."
            tot["submitted"] += s["sensitive_physical_eur"]
        else:
            row["gap"]["unmatched"] = float(r["sensitive_physical_eur"]); row["flag"] = "question"; row["reason"] = "Not present in the submitted template."
            tot["rebuilt"] += r["sensitive_physical_eur"]
        for g in tot:
            if g in row["gap"]:
                tot[g] += row["gap"][g]
        rows.append(row)
    rows.sort(key=lambda x: -abs(sum(x["gap"].values())))
    tot = {k: round(v) for k, v in tot.items()}
    return {"precision": precision, "basis_separable": basis_separable, "n_cells": len(rows),
            "n_flagged": sum(1 for x in rows if x["flag"] == "question"),
            "totals": tot, "total_gap": round(tot["rebuilt"] - tot["submitted"]), "cells": rows}
