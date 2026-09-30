"""Solvency II standard formula — natural catastrophe risk sub-module (Delegated Regulation (EU) 2015/35, Arts 90b and
119-126; as amended by 2019/981 and, from 30 January 2027, by 2026/269). Reported on S.27.01.01 (ITS (EU) 2023/894).

Everything regulatory is reference data (services.governance.solvency2_natcat_tables): the version in force on the
reference date, its factors, zones, weights and correlations, its scenarios, Annex XIII, and the readings the
platform declares where the text leaves a point open. Per peril, as the Articles set it out:

  specified gross loss, region r   L_r = √(Σ_i Σ_j Corr(r,i,j) · WSI_i · WSI_j),  WSI_i = Q_r · W_i · SI_i
      the zones i of Annex IX, weights W of Annex X, correlations of Annexes XXII-XXVI (exact); where a risk's zone is
      not known, or the region's zone labels could not be matched from the text, all the region's zones form one
      group (Art. 90b) at the highest Annex X weight — an upper bound; a region without zones is one zone, W = 1
  capital requirement, region r    the loss in basic own funds from the scenario's events (each set gross, as a
      share of L_r), after the reinsurance in force (Art. 126) — the larger of scenarios A and B where there are two
  other regions                    L = f · (0,5 · DIV + 0,5) · P for risks outside Annex XIII (Arts 121(8)-124(9)),
      P the undertaking's attested premiums by Annex III region, DIV = Σ P_r² / (Σ P_r)² over regions 5 to 18;
      missing, the peril is marked incomplete — never charged on zero
  peril                            SCR = √(Σ_r Σ_s Corr(r,s) · SCR_r · SCR_s + SCR_other²)
  nat-cat                          SCR_natCAT = √(Σ SCR_peril²)                                       (Art. 120)

Every figure is given before and after risk mitigation, as S.27.01.01 asks. Only an attested treaty mitigates: the
platform's illustrative reinsurance programme is never used for a regulatory figure.
"""
from __future__ import annotations

import math
from datetime import date

from services.governance import solvency2_natcat_tables as T
from services.reference.iso_country import to_iso2

REGULATION = "Commission Delegated Regulation (EU) 2015/35, Arts 90b, 119-126; S.27.01.01 (ITS (EU) 2023/894)"
UK_READINGS = ("region_only", "region_and_premium")


def _sum_insured(pol: dict, peril: str, motor: dict) -> float:
    """Property sum insured, plus the motor sum insured times the Article's multiplier (flood, hail)."""
    return (pol.get("sum_insured_eur") or 0) + motor.get(peril, 0) * (pol.get("motor_sum_insured_eur") or 0)


def _treaty_after(events: list[float], treaty: dict | None) -> tuple[float, float, float]:
    """(recoveries, reinstatement premiums, loss in basic own funds) for a sequence of events under the treaty:
    the quota share cedes its share of each event; the per-event excess of loss protects the retained part; the
    limit is reinstated only where reinstatements and their premium are stated (declared reading), at a premium pro
    rata to the limit used."""
    gross = sum(events)
    if not treaty:
        return 0.0, 0.0, gross
    qs = (treaty.get("quota_share_pct") or 0) / 100
    att, lim = treaty.get("xol_attachment_eur") or 0, treaty.get("xol_limit_eur") or 0
    n_re, rp = treaty.get("xol_reinstatements"), treaty.get("xol_reinstatement_premium_eur")
    reinstating = lim > 0 and n_re is not None and n_re > 0 and rp is not None
    cap, left, recovered, premiums = lim, (n_re or 0), 0.0, 0.0
    for x in events:
        retained = x * (1 - qs)
        layer = min(max(retained - att, 0.0), cap) if lim > 0 else 0.0
        recovered += x * qs + layer
        cap -= layer
        if reinstating and layer > 0 and left > 0:
            share = min(layer / lim, left)
            premiums += rp * share
            left -= share
            cap += share * lim
    return recovered, premiums, gross - recovered + premiums


def _scenario(peril: str, loss: float, treaty: dict | None) -> dict:
    """The capital requirement for a region: the scenario with the larger loss in basic own funds."""
    options = T.rules()["scenarios"][peril]
    best = None
    for name in ("A", "B", "single"):
        if name not in options:
            continue
        events = [f * loss for f in options[name]]
        rec, rp, after = _treaty_after(events, treaty)
        cand = {"scenario": None if name == "single" else name, "before": sum(events), "mitigation": rec,
                "reinstatement": rp, "after": after}
        if best is None or round(cand["after"], 2) > round(best["after"], 2):     # a tie keeps A
            best = cand
    return best


def _specified_loss(v: dict, peril: str, region: str, q: float, zones_si: dict,
                    unzoned: float) -> tuple[float, str, str, float]:
    """(L_r, method, why, Σ WSI before diversification between zones) — exact zonal, the Art. 90b grouping of all the
    region's zones, or a one-zone region."""
    si = sum(zones_si.values()) + unzoned
    zt = T.zonal(v, peril, region)
    if zt is None:
        return q * si, "single_zone", T.reading("Single-zone regions"), q * si
    table = zt["zones"]
    unknown = sum(s for z, s in zones_si.items() if z not in table)
    if not zt.get("labels_verified", False):
        why = "the region's zone-correlation labels cannot be matched to Annex IX from the text"
    elif unzoned or unknown:
        why = f"{round(100 * (unzoned + unknown) / si)} % of the sum insured has no Annex IX zone (postal code)"
    else:
        corr = zt["correlation"]
        wsi = {z: q * table[z]["w"] * s for z, s in zones_si.items()}
        var = sum(corr[i][j] * wsi[i] * wsi[j] for i in wsi for j in wsi)
        return (math.sqrt(max(var, 0.0)), "exact_zonal", "Annex IX zones, Annex X weights, zone correlations",
                sum(wsi.values()))
    w_max = max(z["w"] for z in table.values())
    return q * w_max * si, "grouped_art90b", why, q * w_max * si


def diversification(premium_by_region: dict[int, float]) -> float:
    """DIV of Annex III(1) on the premiums, restricted to regions 5 to 18: Σ P_r² / (Σ P_r)². With no premium in those
    regions there is nothing to diversify: 1 (declared reading 'Premiums for other regions')."""
    lo, hi = T.rules()["other_regions"]["annex_iii_regions"]["div_regions"]
    ps = [v for r, v in premium_by_region.items() if lo <= r <= hi and v > 0]
    total = sum(ps)
    return sum(v * v for v in ps) / (total * total) if total > 0 else 1.0


def _zones_undiversified(peril: str, undiversified: dict[str, float], treaty: dict | None) -> dict | None:
    if not undiversified:
        return None
    s = _scenario(peril, sum(undiversified.values()), treaty)
    return {"specified_gross_loss_eur": round(sum(undiversified.values())), "before_eur": round(s["before"]),
            "mitigation_eur": round(s["mitigation"]), "reinstatement_eur": round(s["reinstatement"]),
            "after_eur": round(s["after"])}


def _aggregate(table: dict, by_region: dict[str, float], other: float) -> float:
    idx = {r: i for i, r in enumerate(table["region_order"])}
    corr = table["correlation"]
    var = sum(corr[r][idx[s]] * a * b for r, a in by_region.items() for s, b in by_region.items())
    return math.sqrt(max(var + other * other, 0.0))


def _subsidence_2019_table(v: dict) -> dict:
    """Art. 125 before 2026/269: France only (Annex IX puts Monaco and Andorra in French zones), Q = 0,0005."""
    ws = T.peril_table(v, "windstorm")
    rule = T.rules()["subsidence"]
    return {"region_order": ["FR"], "regions": {"FR": {"name": ws["regions"]["FR"]["name"], "q": rule["factor"]}},
            "correlation": {"FR": [1.0]}, "iso2_to_region": {c: r for c, r in ws["iso2_to_region"].items() if r == "FR"},
            "citation": "Del. Reg. (EU) 2015/35, Art. 125 + Annexes IX, X, XXVI"}


def peril_scr(policies: list[dict], peril: str, *, v: dict, treaty: dict | None = None,
              other_inputs: dict | None = None, uk_reading: str = "region_only") -> dict:
    """One peril's capital requirement, region by region and in total, before and after risk mitigation."""
    if peril == "subsidence" and v["subsidence"] == "france_art_125_2019":
        table = _subsidence_2019_table(v)
    else:
        table = T.peril_table(v, peril)
    if not table:
        return {"peril": peril, "available": False, "reason": f"no {peril} table in version {v['id']}"}
    motor = v.get("motor", {})
    buckets: dict[str, dict] = {}
    other_si = not_charged = unlocated = 0.0
    residential_unknown = 0
    for pol in policies:
        si = _sum_insured(pol, peril, motor)
        if si <= 0:
            continue
        if peril == "subsidence" and pol.get("residential") is False:
            continue                                              # Art. 125: residential buildings only
        iso = to_iso2(pol.get("country"))
        if not iso:
            unlocated += si
            continue
        region = table["iso2_to_region"].get(iso)
        outside = not T.in_annex_xiii(iso)
        if region:
            b = buckets.setdefault(region, {"zones": {}, "unzoned": 0.0, "n": 0})
            b["n"] += 1
            residential_unknown += peril == "subsidence" and pol.get("residential") is None
            z = T.zone_of(v, peril, region, iso, pol.get("postal_code"))
            if z is None:
                b["unzoned"] += si
            else:
                b["zones"][z] = b["zones"].get(z, 0.0) + si
        if outside and (not region or uk_reading == "region_and_premium"):     # only the UK is both
            if not (peril == "subsidence" and v["subsidence"] == "france_art_125_2019"):   # France-only: no 'other'
                other_si += si
        elif not region:
            not_charged += si

    rows, before_r, after_r, undiversified = [], {}, {}, {}
    for region, b in sorted(buckets.items(), key=lambda kv: -(sum(kv[1]["zones"].values()) + kv[1]["unzoned"])):
        q = table["regions"][region]["q"]
        si = sum(b["zones"].values()) + b["unzoned"]
        loss, method, why, undiv = _specified_loss(v, peril, region, q, b["zones"], b["unzoned"])
        undiversified[region] = undiv
        s = _scenario(peril, loss, treaty)
        before_r[region], after_r[region] = s["before"], s["after"]
        rows.append({"region": region, "region_name": table["regions"][region]["name"], "n_policies": b["n"],
                     "exposure_eur": round(si), "specified_gross_loss_eur": round(loss),
                     "charge_factor": round(loss / si, 6) if si else None, "scenario": s["scenario"],
                     "before_eur": round(s["before"]), "mitigation_eur": round(s["mitigation"]),
                     "reinstatement_eur": round(s["reinstatement"]), "after_eur": round(s["after"]),
                     "method": method, "method_reason": why})

    incomplete, other = [], None
    if unlocated:
        incomplete.append(f"{round(unlocated)} EUR of sum insured has no country and is not placed")
    # the premium-based charge follows the premiums the undertaking states for contracts covering risks outside Annex
    # XIII (Arts 121(8)-(9) …): charged whenever they are stated; exposure there without them makes the peril incomplete
    by_region = {int(k): float(v) for k, v in (((other_inputs or {}).get(peril) or {}).get("by_region") or {}).items()
                 if v is not None} if peril != "subsidence" else {}
    if other_si > 0 or by_region:
        other = {"exposure_eur": round(other_si)}
        if peril == "subsidence":
            other["status"] = "not_calculated"
            other["reason"] = T.reading("Subsidence outside Annex XIII (from 2027)")
        else:
            if not by_region:
                other["status"] = "missing_input"
                incomplete.append(f"{peril}: exposure outside Annex XIII needs the premiums to be earned by Annex III "
                                  "region (S.27.01.01) — not stated")
            else:
                p, div = sum(by_region.values()), diversification(by_region)
                f = T.rules()["other_regions"]["factor"][peril]
                loss = f * (0.5 * div + 0.5) * p
                rec, rp, after = _treaty_after([loss], treaty)
                other.update({"status": "computed", "premium_eur": round(p), "premium_by_region": by_region,
                              "div": round(div, 6), "factor": f, "before_eur": round(loss), "mitigation_eur": round(rec),
                              "reinstatement_eur": round(rp), "after_eur": round(after)})
    ob = (other or {}).get("before_eur") or 0.0
    oa = (other or {}).get("after_eur") or 0.0
    total_b = _aggregate(table, before_r, ob) if (before_r or ob) else 0.0
    total_a = _aggregate(table, after_r, oa) if (after_r or oa) else 0.0
    return {
        "peril": peril, "available": bool(rows) or other is not None, "citation": table.get("citation"),
        "regions": rows, "other_regions": other,
        "not_charged_exposure_eur": round(not_charged),        # in Annex XIII but in no region of this peril
        "regions_before_eur": round(sum(before_r.values())), "regions_after_eur": round(sum(after_r.values())),
        "all_before_eur": round(sum(before_r.values()) + ob), "all_after_eur": round(sum(after_r.values()) + oa),
        "diversification_before_eur": round(sum(before_r.values()) + ob - total_b),
        "diversification_after_eur": round(sum(after_r.values()) + oa - total_a),
        "before_eur": round(total_b), "after_eur": round(total_a),
        "residential_not_stated": residential_unknown if peril == "subsidence" else None,
        # subsidence reports its zones before diversification between them (S.27.01.01 R1950-R1970)
        "before_zone_diversification": _zones_undiversified(peril, undiversified, treaty) if peril == "subsidence" else None,
        "complete": not incomplete, "incomplete": incomplete,
    }


def natcat_scr(policies: list[dict], *, ref_date: date | None = None, treaty: dict | None = None,
               treaty_basis: str | None = None, other_inputs: dict | None = None,
               uk_reading: str = "region_only") -> dict:
    """The nat-cat capital requirement on the reference date: the five perils and their combination (Art. 120).
    treaty: the ATTESTED reinsurance in force (services.insurer_capital) or None; other_inputs: {peril: {"by_region":
    {Annex III region number: premium}}} attested for risks outside Annex XIII (S.27.01.01 premium cells); uk_reading:
    the governed switch sii_natcat_uk_other_regions."""
    if uk_reading not in UK_READINGS:
        raise ValueError(f"uk_reading must be one of {UK_READINGS}")
    v = T.version(ref_date)
    if treaty_basis != "attested":
        treaty = None
    perils = {p: peril_scr(policies, p, v=v, treaty=treaty, other_inputs=other_inputs, uk_reading=uk_reading)
              for p in (*T.REGIONAL_PERILS, "subsidence")}
    on = {p: r for p, r in perils.items() if r.get("available")}
    before = math.sqrt(sum(r["before_eur"] ** 2 for r in on.values()))
    after = math.sqrt(sum(r["after_eur"] ** 2 for r in on.values()))
    methods = {row["method"] for r in on.values() for row in r["regions"]}
    applied = ["Single-zone regions"] if "single_zone" in methods else []
    applied += ["Order of the reinsurance", "Reinstatements (Art. 126(2))"] if treaty else []
    applied += ["Residential cover (subsidence)"] if (perils["subsidence"].get("residential_not_stated") or 0) else []
    applied += ["United Kingdom"] if any(r["region"] == "UK" for p in on.values() for r in p["regions"]) else []
    return {
        "available": bool(on), "basis": "solvency_ii_standard_formula", "template": "S.27.01.01",
        "regulation": REGULATION, "version": v["id"], "version_name": v["name"], "version_source": v["source"],
        "reference_date": (ref_date or date.today()).isoformat(),
        "treaty_basis": "attested" if treaty else "none",
        "natcat_scr_before_mitigation_eur": round(before), "natcat_scr_eur": round(after),
        "diversification_between_perils_before_eur": round(sum(r["before_eur"] for r in on.values()) - before),
        "diversification_between_perils_after_eur": round(sum(r["after_eur"] for r in on.values()) - after),
        "scr_by_peril_eur": {p: r.get("after_eur", 0) if r.get("available") else 0 for p, r in perils.items()},
        "perils": perils,
        "simplification_art_90b": "grouped_art90b" in methods,
        "complete": all(r.get("complete", True) for r in perils.values()),
        "incomplete": [x for r in perils.values() for x in r.get("incomplete", [])],
        "uk_reading": uk_reading,
        "readings": [{"subject": s, "reading": T.reading(s)} for s in applied],
    }


PERIL_LABEL = {"windstorm": "Windstorm", "earthquake": "Earthquake", "flood": "Flood", "hail": "Hail",
               "subsidence": "Subsidence"}


def lines(sf: dict) -> list[dict]:
    """The standard-formula result as S.27.01.01-shaped lines — one per region, the other regions, and each peril's
    total after diversification, then the nat-cat total — shared by the filing form, the export and the annex."""
    out: list[dict] = []
    for p, r in (sf.get("perils") or {}).items():
        if not r.get("available"):
            continue
        name = PERIL_LABEL[p]
        for g in r["regions"]:
            out.append({"peril": name, "line": f"{g['region']} · {g['region_name']}", "exposure_eur": g["exposure_eur"],
                        "specified_gross_loss_eur": g["specified_gross_loss_eur"], "scenario": g["scenario"],
                        "before_eur": g["before_eur"], "mitigation_eur": g["mitigation_eur"],
                        "reinstatement_eur": g["reinstatement_eur"], "after_eur": g["after_eur"],
                        "note": g["method_reason"] if g["method"] != "exact_zonal" else "exact zones"})
        o = r.get("other_regions")
        if o:
            out.append({"peril": name, "line": "Other regions (outside Annex XIII)", "exposure_eur": o["exposure_eur"],
                        "premium_eur": o.get("premium_eur"), "before_eur": o.get("before_eur"),
                        "mitigation_eur": o.get("mitigation_eur"), "reinstatement_eur": o.get("reinstatement_eur"),
                        "after_eur": o.get("after_eur"),
                        "note": {"computed": "f · (0,5 · DIV + 0,5) · P", "missing_input": "premiums by region not stated",
                                 "not_calculated": o.get("reason")}.get(o["status"])})
        out.append({"peril": name, "line": "Diversification between regions", "before_eur": -r["diversification_before_eur"],
                    "after_eur": -r["diversification_after_eur"]})
        out.append({"peril": name, "line": f"Total {name.lower()} after diversification", "before_eur": r["before_eur"],
                    "after_eur": r["after_eur"], "total": True})
    out.append({"peril": "Natural catastrophe", "line": "Diversification between perils",
                "before_eur": -sf.get("diversification_between_perils_before_eur", 0),
                "after_eur": -sf.get("diversification_between_perils_after_eur", 0)})
    out.append({"peril": "Natural catastrophe", "line": "Natural catastrophe risk", "total": True,
                "before_eur": sf.get("natcat_scr_before_mitigation_eur"), "after_eur": sf.get("natcat_scr_eur")})
    return out
