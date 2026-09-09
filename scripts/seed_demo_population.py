"""Demo population: eight supervised entities per sector, each with a real, scored book.

Banking, insurance, markets (asset managers + REITs) and agri-food supervisors each get eight entities to work
with — the existing demo tenant plus seven more per sector. Every new entity carries a portfolio whose locations
are drawn from the platform's richly scored cells (≥ 15 hazards at baseline/today), so exposure, benchmark, map,
lens and plausibility all read on real scores from the first minute; values, names and countries vary per entity.
Filings and obligations are seeded in mixed states so the population, timeliness and workflow views have
something to sort on; five banks get a submitted Pillar 3 template (three with two periods) for the Tier-1 band.

Idempotent: deterministic ids (uuid5), upserts, books rebuilt from scratch on every run.
    .venv/bin/python -m scripts.seed_demo_population
"""
from __future__ import annotations

import random
import uuid
from datetime import date, timedelta

import h3
from sqlalchemy import text

from api.security import hash_password
from core.db.session import get_session
from core.types import score_to_bucket
from services.geo.regions import region_for
from services.governance.filings import FRAMEWORKS
from services.governance.pillar3_templates import _section
from services.governance.tenant_provisioning import DEFAULT_ROLE_PERMS

NS = uuid.UUID("7d0b3b1e-2a4c-4b7e-9c1f-5a6d7e8f9a0b")
TEMPLATES = {   # sector → (template org, entitlements, supervisory body, jurisdiction, frameworks by sector come from FRAMEWORKS)
    "bank": ("11111111-1111-4111-8111-111111111111", ["physical-risk", "reporting", "trust"], "88888888-8888-4888-8888-888888888888", "EU/SSM"),
    "insurer": ("22222222-2222-4222-8222-222222222222", ["underwriting", "parametric", "trust"], "88888888-8888-4888-8888-888888888802", "EU/EIOPA"),
    "asset_manager": ("44444444-4444-4444-8444-444444444444", ["portfolio-var", "trust", "securities"], "88888888-8888-4888-8888-888888888803", "EU/ESMA"),
    "reit": ("33333333-3333-4333-8333-333333333333", ["portfolio-risk", "trust"], "88888888-8888-4888-8888-888888888803", "EU/ESMA"),
    "manufacturer": ("66666666-6666-4666-8666-666666666666", ["supply-chain", "trust"], "88888888-8888-4888-8888-888888888804", "EU/CSRD"),
}
NEW = {   # seven new entities per sector: (name, slug, home country, size factor)
    "bank": [("Rhein-Main Kreditbank", "rheinmain", "DE", 1.6), ("Banque Atlantique", "atlantique", "FR", 1.2), ("Banco do Tejo", "tejo", "PT", 0.7),
             ("Lombardia Credito", "lombardia", "IT", 1.1), ("Nordsee Sparkasse", "nordsee", "DE", 0.5), ("Caja Levante", "levante", "ES", 0.8), ("Hibernia Bank", "hibernia", "UK", 0.9)],
    "insurer": [("Alpenrück Versicherung", "alpenrueck", "DE", 1.4), ("Assurances du Rhône", "rhone", "FR", 1.0), ("Lusitânia Seguros", "lusitania", "PT", 0.5),
                ("Adriatica Assicurazioni", "adriatica", "IT", 0.9), ("Nordlys Forsikring", "nordlys", "NO", 0.6), ("Baltic Mutual", "baltic", "SE", 0.7), ("Delta Verzekeringen", "delta", "NL", 1.1)],
    "asset_manager": [("Helvetica Asset Partners", "helvetica", "DE", 1.3), ("Seine Capital", "seine", "FR", 1.0), ("Tagus Investimentos", "tagus", "PT", 0.4),
                      ("Tiber Asset Management", "tiber", "IT", 0.8), ("Fjord Capital", "fjord", "NO", 0.9), ("Øresund Funds", "oresund", "DK", 0.7), ("Amstel Investment Management", "amstel", "NL", 1.2)],
    "reit": [("Hanse Logistik REIT", "hanse", "DE", 1.2), ("Île-de-France Property Trust", "idf", "FR", 1.5), ("Atlântico Real Estate", "atlantico", "PT", 0.5),
             ("Mediterraneo Immobiliare", "mediterraneo", "IT", 0.9), ("Nordic Warehouses", "nordicwh", "SE", 0.8), ("Randstad Offices", "randstad", "NL", 1.0), ("Thames Estates", "thames", "UK", 1.1)],
    "manufacturer": [("Bavaria Foods AG", "bavariafoods", "DE", 1.3), ("Provence Agroalimentaire", "provence", "FR", 0.9), ("Douro Alimentar", "douro", "PT", 0.5),
                     ("Padania Alimentari", "padania", "IT", 1.0), ("Skåne Foods", "skane", "SE", 0.6), ("Flevo Agro", "flevo", "NL", 0.8), ("Andalus Olive Group", "andalus", "ES", 0.7)],
}
CASE_LEADS = {"88888888-8888-4888-8888-888888888888": "approver@supervisor.demo", "88888888-8888-4888-8888-888888888802": "approver@insurance-supervisor.demo",
              "88888888-8888-4888-8888-888888888803": "approver@markets-supervisor.demo", "88888888-8888-4888-8888-888888888804": "approver@agrifood-authority.demo"}
PERIOD_END, PERIOD = date(2025, 12, 31), "FY2025"


def oid(slug: str) -> str:
    return str(uuid.uuid5(NS, f"org:{slug}"))


def rid(*parts) -> str:
    return str(uuid.uuid5(NS, ":".join(str(p) for p in parts)))


def scored_pool(s) -> dict[str, list[tuple[str, float, float, str]]]:
    """country → [(cell, lat, lon, region name)] of cells with ≥ 15 hazards at baseline/today."""
    rows = s.execute(text("""SELECT h3_cell FROM canonical_scores WHERE score_lane = 'standing' AND valid_to IS NULL
                             AND scenario = 'baseline' AND time_horizon = 'current' GROUP BY 1 HAVING count(DISTINCT hazard_type) >= 15""")).scalars().all()
    pool: dict[str, list] = {}
    for c in rows:
        lat, lon = h3.cell_to_latlng(c)
        r = region_for(lat, lon)
        country = r["country"] if r["kind"] == "nuts3" else (r["country"] or "XX")
        pool.setdefault(country, []).append((c, lat, lon, r["name"]))
    return pool


def pick_cells(pool, home: str, n: int, rng: random.Random) -> list[tuple[str, float, float, str, str]]:
    home_cells = pool.get(home) or pool["ES"]
    iberia = pool["ES"] + pool.get("PT", [])
    everything = [x for xs in pool.values() for x in xs]
    out = []
    for i in range(n):
        u = rng.random()
        src, cc = (home_cells, home) if u < 0.55 else (iberia, "ES") if u < 0.8 else (everything, None)
        c = rng.choice(src)
        out.append((c[0], c[1], c[2], c[3], cc or next((k for k, v in pool.items() if c in v), "XX")))
    return out


def upsert_org(s, org_id: str, name: str, typ: str, country: str, ents: list[str], size: float) -> None:
    s.execute(text("""INSERT INTO organizations (org_id, name, type, country, aum_eur, employees, lei, legal_name, created_at, updated_at)
                      VALUES (CAST(:o AS uuid), :n, :t, :c, :a, :e, :lei, :ln, now(), now())
                      ON CONFLICT (org_id) DO UPDATE SET name = EXCLUDED.name, type = EXCLUDED.type, country = EXCLUDED.country, lei = EXCLUDED.lei"""),
              {"o": org_id, "n": f"{name} (demo)", "t": typ, "c": country, "a": int(20e9 * size), "e": int(1500 * size),
               "lei": ("5493" + uuid.uuid5(NS, name).hex[:16].upper()), "ln": name})
    for off in ents:
        s.execute(text("INSERT INTO org_entitlements (org_id, offering_id, enabled) VALUES (CAST(:o AS uuid), :f, true) ON CONFLICT (org_id, offering_id) DO UPDATE SET enabled = true"), {"o": org_id, "f": off})
    for role_name, perms in DEFAULT_ROLE_PERMS.items():
        role_id = s.execute(text("""INSERT INTO roles (org_id, name, description, is_system) VALUES (CAST(:o AS uuid), :n, :d, true)
                                    ON CONFLICT (org_id, name) DO UPDATE SET description = EXCLUDED.description RETURNING role_id"""),
                            {"o": org_id, "n": role_name, "d": f"{role_name} role"}).scalar()
        for code in perms:
            s.execute(text("INSERT INTO role_permissions (role_id, permission_id) SELECT :r, permission_id FROM permissions WHERE code = :c ON CONFLICT DO NOTHING"), {"r": role_id, "c": code})


def upsert_user(s, org_id: str, email: str, full_name: str, role: str, pw: str) -> None:
    s.execute(text("""INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
                      VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :e, :r, :fn, :hp, 'active', now())
                      ON CONFLICT (org_id, email) DO UPDATE SET full_name = EXCLUDED.full_name, hashed_password = EXCLUDED.hashed_password, status = 'active'"""),
              {"u": rid("user", email), "o": org_id, "e": email, "r": role, "fn": full_name, "hp": hash_password(pw)})
    s.execute(text("""INSERT INTO user_roles (user_id, role_id) SELECT u.user_id, r.role_id FROM users u JOIN roles r ON r.org_id = u.org_id AND r.name = :n
                      WHERE u.org_id = CAST(:o AS uuid) AND u.email = :e ON CONFLICT DO NOTHING"""), {"n": role, "o": org_id, "e": email})


def clone_financial_book(s, template_org: str, org_id: str, name: str, home: str, size: float, pool, rng: random.Random) -> int:
    rows = s.execute(text("""SELECT vertical, entity_type, sector, nace_code, primary_value_eur, construction_type, year_built, number_of_stories, location_precision
                             FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND source IS DISTINCT FROM 'supervisor_shadow' ORDER BY entity_id"""),
                     {"o": template_org}).mappings().all()
    s.execute(text("DELETE FROM portfolio_entities WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})
    n = max(20, int(len(rows) * min(1.4, 0.6 + size / 2)))
    cells = pick_cells(pool, home, n, rng)
    ext_b = {r["entity_id"]: dict(r) for r in s.execute(text("SELECT * FROM ext_banking WHERE entity_id IN (SELECT entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid))"), {"o": template_org}).mappings().all()}
    ext_i = [dict(r) for r in s.execute(text("SELECT * FROM ext_insurance WHERE entity_id IN (SELECT entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid))"), {"o": template_org}).mappings().all()]
    ext_r = [dict(r) for r in s.execute(text("SELECT * FROM ext_realestate WHERE entity_id IN (SELECT entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid))"), {"o": template_org}).mappings().all()]
    ext_b_list = list(ext_b.values())
    for i, (cell, lat, lon, region, cc) in enumerate(cells):
        t = rows[i % len(rows)]
        eid = rid("pe", org_id, i)
        value = float(t["primary_value_eur"] or 1e6) * size * rng.uniform(0.6, 1.5)
        lat2, lon2 = lat + rng.uniform(-0.004, 0.004), lon + rng.uniform(-0.004, 0.004)
        s.execute(text("""INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, sector, nace_code, latitude, longitude, h3_cell, country, region,
                              primary_value_eur, construction_type, year_built, number_of_stories, source, location_precision, created_at, updated_at)
                          VALUES (CAST(:id AS uuid), CAST(:o AS uuid), :v, :n, :et, :sec, :nace, :lat, :lon, :h3, :c, :r, :val, :ct, :yb, :ns, 'own', NULL, now(), now())"""),
                  {"id": eid, "o": org_id, "v": t["vertical"], "n": f"{region} {t['entity_type'] or 'asset'} {i + 1}", "et": t["entity_type"], "sec": t["sector"], "nace": t["nace_code"],
                   "lat": lat2, "lon": lon2, "h3": cell, "c": cc, "r": region, "val": round(value, 2), "ct": t["construction_type"], "yb": t["year_built"], "ns": t["number_of_stories"]})
        if t["vertical"] == "banking" and ext_b_list:
            x = ext_b_list[i % len(ext_b_list)]
            s.execute(text("""INSERT INTO ext_banking (entity_id, annual_revenue_eur, expected_lifespan_years, gics_code, taxonomy_status, taxonomy_activity, energy_consumption_mwh,
                                  ghg_emissions_scope1_tco2e, ghg_emissions_scope2_tco2e, ghg_emissions_scope3_tco2e, carbon_intensity_tco2e_per_meur, insurance_coverage_eur, insurance_coverage_pct,
                                  resilience_rating, data_source, outstanding_loan_balance_eur, loan_origination_date, residual_maturity_years, epc_label, ifrs9_stage, emission_intensity)
                              VALUES (CAST(:id AS uuid), :rev, :life, :gics, :tax, :act, :en, :s1, :s2, :s3, :ci, :ic, :icp, :res, 'demo', :ol, :od, :rm, :epc, :st, :ei)"""),
                      {"id": eid, "rev": x.get("annual_revenue_eur"), "life": x.get("expected_lifespan_years"), "gics": x.get("gics_code"), "tax": x.get("taxonomy_status"), "act": x.get("taxonomy_activity"),
                       "en": x.get("energy_consumption_mwh"), "s1": x.get("ghg_emissions_scope1_tco2e"), "s2": x.get("ghg_emissions_scope2_tco2e"), "s3": x.get("ghg_emissions_scope3_tco2e"),
                       "ci": x.get("carbon_intensity_tco2e_per_meur"), "ic": x.get("insurance_coverage_eur"), "icp": x.get("insurance_coverage_pct"), "res": x.get("resilience_rating"),
                       "ol": round(value * rng.uniform(0.5, 0.9), 2), "od": x.get("loan_origination_date"), "rm": x.get("residual_maturity_years"), "epc": x.get("epc_label"), "st": x.get("ifrs9_stage"), "ei": x.get("emission_intensity")})
        elif t["vertical"] == "insurance" and ext_i:
            x = ext_i[i % len(ext_i)]
            s.execute(text("""INSERT INTO ext_insurance (entity_id, deductible_pct, building_value_eur, contents_value_eur, business_interruption_value_eur, cresta_zone)
                              VALUES (CAST(:id AS uuid), :d, :b, :c, :bi, :z)"""),
                      {"id": eid, "d": x.get("deductible_pct"), "b": round(value * 0.7, 2), "c": round(value * 0.2, 2), "bi": round(value * 0.1, 2), "z": x.get("cresta_zone") if cc == "ES" else None})
        elif t["vertical"] == "realestate" and ext_r:
            x = ext_r[i % len(ext_r)]
            s.execute(text("INSERT INTO ext_realestate (entity_id, annual_noi_eur, epc_rating) VALUES (CAST(:id AS uuid), :noi, :epc)"),
                      {"id": eid, "noi": round(value * 0.055, 2), "epc": x.get("epc_rating")})
    return n


def clone_agri_book(s, template_org: str, org_id: str, name: str, home: str, size: float, rng: random.Random) -> int:
    for t in ("sc_sourcing_plots", "sc_company_sites", "sc_suppliers"):
        s.execute(text(f"DELETE FROM {t} WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})
    sup_map = {}
    for r in s.execute(text("SELECT * FROM sc_suppliers WHERE org_id = CAST(:o AS uuid)"), {"o": template_org}).mappings().all():
        nid = rid("sup", org_id, r["supplier_id"]); sup_map[r["supplier_id"]] = nid
        s.execute(text("INSERT INTO sc_suppliers (supplier_id, org_id, name, commodity_id, tier, country) VALUES (CAST(:id AS uuid), CAST(:o AS uuid), :n, :c, :t, :cc)"),
                  {"id": nid, "o": org_id, "n": r["name"], "c": r["commodity_id"], "t": r["tier"], "cc": r["country"]})
    sites = s.execute(text("SELECT * FROM sc_company_sites WHERE org_id = CAST(:o AS uuid)"), {"o": template_org}).mappings().all()
    keep = rng.sample(list(sites), k=max(8, int(len(sites) * min(1.0, 0.3 + size / 2))))
    for i, r in enumerate(keep):
        s.execute(text("""INSERT INTO sc_company_sites (site_id, org_id, name, site_type, address, latitude, longitude, h3_cell, country, region, annual_value_eur, confidence, geocode_precision, source, annual_throughput_eur)
                          VALUES (CAST(:id AS uuid), CAST(:o AS uuid), :n, :st, :a, :lat, :lon, :h3, :c, :r, :v, :conf, :gp, 'demo', :tp)"""),
                  {"id": rid("site", org_id, r["site_id"]), "o": org_id, "n": r["name"].replace("Oranje Foods", name), "st": r["site_type"], "a": r["address"], "lat": r["latitude"], "lon": r["longitude"],
                   "h3": r["h3_cell"], "c": r["country"], "r": r["region"], "v": round(float(r["annual_value_eur"] or 0) * size * rng.uniform(0.7, 1.3), 2), "conf": r["confidence"], "gp": r["geocode_precision"],
                   "tp": r["annual_throughput_eur"]})
    plots = s.execute(text("SELECT * FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid)"), {"o": template_org}).mappings().all()
    keep_p = rng.sample(list(plots), k=max(40, int(len(plots) * min(1.0, 0.3 + size / 2))))
    for r in keep_p:
        s.execute(text("""INSERT INTO sc_sourcing_plots (plot_id, org_id, supplier_id, commodity_id, plot_name, latitude, longitude, h3_cell, country, region, annual_spend_eur, volume_share, eudr_status, confidence, geocode_precision, irrigation_status)
                          VALUES (CAST(:id AS uuid), CAST(:o AS uuid), CAST(:sup AS uuid), :com, :pn, :lat, :lon, :h3, :c, :r, :sp, :vs, :e, :conf, :gp, :irr)"""),
                  {"id": rid("plot", org_id, r["plot_id"]), "o": org_id, "sup": sup_map.get(r["supplier_id"]), "com": r["commodity_id"], "pn": r["plot_name"], "lat": r["latitude"], "lon": r["longitude"],
                   "h3": r["h3_cell"], "c": r["country"], "r": r["region"], "sp": round(float(r["annual_spend_eur"] or 0) * size * rng.uniform(0.7, 1.3), 2), "vs": r["volume_share"],
                   "e": r["eudr_status"], "conf": r["confidence"], "gp": r["geocode_precision"], "irr": r["irrigation_status"]})
    return len(keep) + len(keep_p)


def seed_filings(s, org_id: str, typ: str, rng: random.Random) -> None:
    for fw, f in FRAMEWORKS.items():
        if typ not in f["sectors"]:
            continue
        due = date(PERIOD_END.year + 1, *f["due"])
        s.execute(text("""INSERT INTO regulatory_obligation (obligation_id, org_id, framework, period_end, period_label, due_date, frequency)
                          VALUES (CAST(:id AS uuid), CAST(:o AS uuid), :fw, :pe, :pl, :due, :fq) ON CONFLICT DO NOTHING"""),
                  {"id": rid("obl", org_id, fw), "o": org_id, "fw": fw, "pe": PERIOD_END, "pl": PERIOD, "due": due, "fq": f["frequency"]})
        u = rng.random()
        status = "submitted" if u < 0.45 else "accepted" if u < 0.6 else "in_review" if u < 0.8 else None
        if status:
            filed_at = due + timedelta(days=rng.randint(-40, 25)) if status in ("submitted", "accepted") else due + timedelta(days=rng.randint(-10, 60))
            s.execute(text("""INSERT INTO regulatory_filing (filing_id, org_id, framework, period_end, period_label, status, created_at, updated_at)
                              VALUES (CAST(:id AS uuid), CAST(:o AS uuid), :fw, :pe, :pl, :st, :c, :u)
                              ON CONFLICT (filing_id) DO UPDATE SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at"""),
                      {"id": rid("fil", org_id, fw), "o": org_id, "fw": fw, "pe": PERIOD_END, "pl": PERIOD, "st": status, "c": filed_at - timedelta(days=20), "u": filed_at})


def seed_template(s, reg_id: str, org_id: str, period: str, scale: float, sens_scale: float, basis: dict, rng: random.Random) -> None:
    """A submitted Pillar 3 Template 5 derived from the bank's own book at the stated basis (Tier-1 material)."""
    import hashlib
    import json

    from services.geo.org_assets import org_asset_points
    pts = org_asset_points(s, org_id, basis["scenario"], basis["horizon"])
    cells: dict = {}
    for p in pts:
        geo, sec = (p.get("country") or "ES"), _section(p.get("nace_code") or p.get("sector"))
        c = cells.setdefault(f"{geo}|{sec}", {"geography": geo, "sector": sec, "gross_carrying_amount_eur": 0.0, "sensitive_physical_eur": 0.0, "sensitive_acute_eur": 0.0, "sensitive_chronic_eur": 0.0})
        v = float(p["value_eur"] or 0) * scale
        c["gross_carrying_amount_eur"] += v
        if p.get("score") is not None and score_to_bucket(float(p["score"])).value in ("H", "VH"):
            c["sensitive_physical_eur"] += v * sens_scale * rng.uniform(0.85, 1.0)
    for c in cells.values():
        for k in ("gross_carrying_amount_eur", "sensitive_physical_eur"):
            c[k] = round(c[k], 2)
    raw = json.dumps(cells, sort_keys=True).encode()
    s.execute(text("DELETE FROM supervisor_submissions WHERE regulator_org_id = CAST(:r AS uuid) AND subject_org_id = CAST(:s AS uuid) AND framework = 'pillar3_esg' AND period_label = :p"),
              {"r": reg_id, "s": org_id, "p": period})
    s.execute(text("""INSERT INTO supervisor_submissions (regulator_org_id, subject_org_id, framework, template, period_label, basis, cells, n_cells, source_file, source_sha256, column_mapping)
                      VALUES (CAST(:r AS uuid), CAST(:s AS uuid), 'pillar3_esg', 'template_5', :p, CAST(:b AS jsonb), CAST(:c AS jsonb), :n, :f, :sha, '{}'::jsonb)"""),
              {"r": reg_id, "s": org_id, "p": period, "b": json.dumps(basis), "c": json.dumps(cells), "n": len(cells), "f": f"pillar3_template5_{period}.csv", "sha": hashlib.sha256(raw).hexdigest()})


def seed_attributes(s, rng: random.Random) -> int:
    """Regulatory attributes the mandate criteria read — for every supervised demo entity, with a few deliberately left
    unset so the 'cannot determine → ask the entity' path is visible."""
    from services.supervision.mandates import set_attribute
    rows = s.execute(text("""SELECT DISTINCT o.org_id::text AS org_id, o.type, o.aum_eur, o.employees FROM supervision_scope ss
                             JOIN organizations o ON o.org_id = ss.supervised_org_id WHERE ss.active""")).mappings().all()
    n = 0
    for i, r in enumerate(rows):
        gap = (i % 6 == 4)          # every sixth entity leaves its size attributes unset
        aum = float(r["aum_eur"] or 0)
        listed = rng.random() < 0.6
        vals = {"listed": listed, "public_interest_entity": listed or rng.random() < 0.3}
        if not gap:
            if r["type"] in ("bank",):
                vals["total_assets_eur"] = aum
            elif r["type"] == "insurer":
                vals["gross_written_premium_eur"] = round(aum * 0.12)
                vals["total_assets_eur"] = aum
            elif r["type"] == "manufacturer":
                vals["turnover_eur"] = round(aum * 0.4)
                vals["total_assets_eur"] = round(aum * 0.6)
            elif r["type"] == "reit":
                vals["total_assets_eur"] = aum
                vals["turnover_eur"] = round(aum * 0.07)
        for k, v in vals.items():
            set_attribute(s, r["org_id"], k, v, source="entity", by_user_id=None, as_of=PERIOD_END.isoformat()); n += 1
    return n


def main() -> None:
    rng = random.Random(2026)
    with get_session() as s:
        pool = scored_pool(s)
        print(f"scored pool: {sum(len(v) for v in pool.values())} cells in {len(pool)} countries")
        created = []
        for typ, (template_org, ents, body, juris) in TEMPLATES.items():
            for name, slug, home, size in NEW[typ]:
                org_id = oid(slug)
                upsert_org(s, org_id, name, typ, home, ents, size)
                upsert_user(s, org_id, f"admin@{slug}.demo", f"Admin ({name})", "admin", "Demo!admin1")
                upsert_user(s, org_id, f"analyst@{slug}.demo", f"Analyst ({name})", "analyst", "Demo!analyst1")
                n = clone_agri_book(s, template_org, org_id, name, home, size, rng) if typ == "manufacturer" else clone_financial_book(s, template_org, org_id, name, home, size, pool, rng)
                seed_filings(s, org_id, typ, rng)
                s.execute(text("""INSERT INTO supervision_scope (regulator_org_id, supervised_org_id, jurisdiction, active, acknowledged_at)
                                  VALUES (CAST(:r AS uuid), CAST(:s AS uuid), :j, TRUE, CASE WHEN :ack THEN now() ELSE NULL END)
                                  ON CONFLICT (regulator_org_id, supervised_org_id) DO UPDATE SET active = TRUE, ended_at = NULL, jurisdiction = EXCLUDED.jurisdiction"""),
                          {"r": body, "s": org_id, "j": juris, "ack": rng.random() < 0.6})
                created.append((typ, name, n))
                s.commit()
        # Tier-1 templates: five of the eight banks, three with two periods, basis stated by the bank
        banking = TEMPLATES["bank"][2]
        for i, (name, slug, home, size) in enumerate(NEW["bank"][:5]):
            org_id = oid(slug); basis = {"scenario": rng.choice(["disorderly_2c", "orderly_1_5c", "baseline"]), "horizon": rng.choice(["2030", "current"]), "method_note": "internal physical-risk heat-map"}
            seed_template(s, banking, org_id, "FY2025", 1.0, rng.uniform(0.5, 1.1), basis, rng)
            if i < 3:
                seed_template(s, banking, org_id, "FY2024", rng.uniform(0.85, 0.97), rng.uniform(0.6, 1.0), basis, rng)
            s.commit()
        # case leads work three of their eight
        for body, email in CASE_LEADS.items():
            ents = s.execute(text("SELECT supervised_org_id::text FROM supervision_scope WHERE regulator_org_id = CAST(:r AS uuid) AND active ORDER BY supervised_org_id"), {"r": body}).scalars().all()
            for org_id in ents[:3]:
                s.execute(text("""INSERT INTO supervision_assignment (regulator_org_id, supervised_org_id, user_id, capacity)
                                  SELECT CAST(:r AS uuid), CAST(:s AS uuid), u.user_id, 'lead' FROM users u WHERE u.email = :e
                                    AND NOT EXISTS (SELECT 1 FROM supervision_assignment a WHERE a.regulator_org_id = CAST(:r AS uuid) AND a.supervised_org_id = CAST(:s AS uuid) AND a.user_id = u.user_id AND a.revoked_at IS NULL)"""),
                          {"r": body, "s": org_id, "e": email})
        s.commit()
        print(f"  regulatory attributes set: {seed_attributes(s, rng)}"); s.commit()
        for typ, name, n in created:
            print(f"  {typ:14s} {name:32s} {n:4d} book rows")
        print(f"population seeded: {len(created)} new entities; each supervisory body now has 8")


if __name__ == "__main__":
    main()
