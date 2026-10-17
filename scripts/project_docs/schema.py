"""docs/BACKEND_SCHEMA.md — the tables, columns, keys, constraints, triggers and tenancy columns the migrations build,
rendered from the catalogue `catalogue.read_catalogue` returns (no database access here)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from scripts.project_docs.domains import DOMAINS, TITLES, domain_of
from scripts.project_docs.source import banner, mermaid, table

TENANT = "public.organizations"


def _short(qualified: str) -> str:
    schema, _, name = qualified.partition(".")
    return name if schema == "public" else qualified


def _er_name(qualified: str) -> str:
    return re.sub(r"\W", "_", _short(qualified))


def _er_type(t: str) -> str:
    for long, short in (("character varying", "varchar"), ("timestamp with time zone", "timestamptz"),
                        ("timestamp without time zone", "timestamp"), ("double precision", "float8"),
                        ("time with time zone", "timetz"), ("time without time zone", "time")):
        t = t.replace(long, short)
    return re.sub(r"\W", "_", re.sub(r"\(.*?\)", "", t).replace("[]", "_array")).strip("_")


def _unique_sets(r: dict) -> list[set[str]]:
    return [set(r["pk"])] * bool(r["pk"]) + [set(u["columns"]) for u in r["uniques"]]


def _er_diagram(tables: dict[str, dict]) -> str:
    """Entities with their key columns (PK and FK), and one relationship per foreign key inside the set."""
    lines = ["erDiagram"]
    for q, r in tables.items():
        fk_cols = {c for f in r["fks"] for c in f["columns"]}
        keys = [c for c in r["columns"] if c["name"] in set(r["pk"]) | fk_cols] or r["columns"][:1]
        lines.append(f"  {_er_name(q)} {{")
        for c in keys:
            mark = ",".join(m for m, on in (("PK", c["name"] in r["pk"]), ("FK", c["name"] in fk_cols)) if on)
            lines.append(f"    {_er_type(c['type'])} {c['name']}{' ' + mark if mark else ''}")
        lines.append("  }")
    for q, r in tables.items():
        nullable = {c["name"]: c["nullable"] for c in r["columns"]}
        for f in r["fks"]:
            if f["ref"] not in tables:
                continue
            parent = "|o" if any(nullable[c] for c in f["columns"]) else "||"
            child = "o|" if set(f["columns"]) in _unique_sets(r) else "o{"
            lines.append(f'  {_er_name(f["ref"])} {parent}--{child} {_er_name(q)} : "{", ".join(f["columns"])}"')
    return mermaid("\n".join(lines))


def _column_rows(r: dict) -> list[list]:
    fk_of = {c: f for f in r["fks"] for c in f["columns"]}
    single_unique = {next(iter(u["columns"])) for u in r["uniques"] if len(u["columns"]) == 1}
    rows = []
    for c in r["columns"]:
        notes = []
        if c["name"] in r["pk"]:
            notes.append("PK")
        if c["name"] in fk_of:
            f = fk_of[c["name"]]
            ref = f"{_short(f['ref'])}.{f['ref_columns'][f['columns'].index(c['name'])]}"
            notes.append(f"FK → {ref}" + (f" (on delete {f['on_delete']})" if f["on_delete"] != "no action" else ""))
        if c["name"] in single_unique:
            notes.append("unique")
        if c["identity"]:
            notes.append(f"identity ({c['identity']})")
        if c["generated"]:
            notes.append("generated")
        if c["comment"]:
            notes.append(c["comment"])
        rows.append([f"`{c['name']}`", c["type"], "yes" if c["nullable"] else "no",
                     f"`{c['default']}`" if c["default"] else "", "; ".join(notes)])
    return rows


def _table_section(q: str, r: dict) -> list[str]:
    out = [f"#### `{_short(q)}`", ""]
    if r["comment"]:
        out += [f"> {' '.join(r['comment'].split())}", ""]
    out += [table(["Column", "Type", "Null", "Default", "Key / notes"], _column_rows(r)), ""]
    extra = []
    if len(r["pk"]) > 1:
        extra.append(f"- Primary key: ({', '.join(r['pk'])})")
    extra += [f"- Unique `{u['name']}`: ({', '.join(u['columns'])})" for u in r["uniques"] if len(u["columns"]) > 1]
    extra += [f"- Foreign key `{f['name']}`: ({', '.join(f['columns'])}) → {_short(f['ref'])} "
              f"({', '.join(f['ref_columns'])})" for f in r["fks"] if len(f["columns"]) > 1]
    extra += [f"- Check `{k['name']}`: `{k['definition']}`" for k in r["checks"]]
    extra += [f"- Exclusion `{k['name']}`: `{k['definition']}`" for k in r["excludes"]]
    extra += [f"- Index: `{i['definition']}`" for i in r["indexes"]]
    extra += [f"- Trigger `{t['name']}`: {t['timing']} {t['events']} for each {t['per']} → `{t['function']}`"
              for t in r["triggers"]]
    return out + (extra + [""] if extra else [])


def render(cat: dict, migrations: dict) -> str:
    rel = cat["relations"]
    tables = {q: r for q, r in rel.items() if r["kind"] == "table"}
    views = {q: r for q, r in rel.items() if r["kind"] == "view"}
    dom = {q: domain_of(q) for q in tables}
    by_domain: dict[str, dict] = defaultdict(dict)
    for q in tables:
        by_domain[dom[q]][q] = tables[q]
    fks = [(q, f) for q, r in tables.items() for f in r["fks"]]
    triggers = [(q, t) for q, r in tables.items() for t in r["triggers"]]
    raising = [(q, t) for q, t in triggers if t["raises"]]
    schemas = Counter(q.partition(".")[0] for q in tables)

    out = ["# Backend schema — Tellumen climate platform", "",
           banner("the PostgreSQL catalogue of a scratch database the migration files build to head "
                  "(`scripts/project_docs/catalogue.py`)"), "",
           f"The database as the migrations build it: **{len(tables)} tables** "
           f"({', '.join(f'{n} in `{s}`' for s, n in sorted(schemas.items()))}), {len(views)} views, "
           f"{sum(len(r['columns']) for r in tables.values())} table columns, {len(fks)} foreign keys, "
           f"{sum(len(r['uniques']) for r in tables.values())} unique constraints, "
           f"{sum(len(r['checks']) for r in tables.values())} check constraints, "
           f"{sum(len(r['indexes']) for r in tables.values())} further indexes and {len(triggers)} triggers "
           f"({len(raising)} of them on a function that raises an exception). Built by "
           f"{migrations['revisions']} migration revisions in `core/db/migrations/versions/`, head "
           f"{', '.join(f'`{h}`' for h in migrations['heads'])}. Extensions present: "
           f"{', '.join(cat['extensions'])}.", "",
           "It supersedes the earlier hand-drawn map [docs/board/database_blueprint.html](board/database_blueprint.html), "
           "which is kept unchanged as a record. Architecture, tenancy enforcement and deployment are described in "
           "[SOFTWARE_DESCRIPTION.md](SOFTWARE_DESCRIPTION.md) §5–§7.", "",
           "**Reading the column tables.** *Null* is whether the column accepts NULL; *Default* is the expression "
           "PostgreSQL stores; *FK → t.c* is a foreign key; a table's further constraints, indexes and triggers are "
           "listed under its columns.", "",
           "## Contents", "", "1. [Domains](#1-domains)", "2. [Tenancy and access control](#2-tenancy-and-access-control)",
           "3. [Append-only and guard triggers](#3-append-only-and-guard-triggers)",
           "4. [Tables by domain](#4-tables-by-domain)", "5. [Views](#5-views)", "6. [Functions](#6-functions)", ""]

    # 1 · domains
    cross: Counter = Counter()
    for q, f in fks:
        if f["ref"] in dom and dom[f["ref"]] != dom[q]:
            cross[(dom[q], dom[f["ref"]])] += 1
    hubs = ("tenants", "identity")       # nearly every domain points at these: counted in the table, not drawn
    rows = []
    for key, title, _ in DOMAINS:
        ts = by_domain.get(key, {})
        if ts:
            inside = sum(1 for r in ts.values() for f in r["fks"] if f["ref"] in ts)
            guarded = sum(1 for r in ts.values() if any(t["raises"] for t in r["triggers"]))
            rows.append([title, len(ts), sum(len(r["columns"]) for r in ts.values()), inside,
                         cross.get((key, "tenants"), 0), cross.get((key, "identity"), 0), guarded])
    drawn = {(a, b): n for (a, b), n in cross.items() if b not in hubs}
    nodes = sorted({x for ab in drawn for x in ab}, key=[k for k, _, _ in DOMAINS].index)
    flow = ["flowchart LR"] + [f'  {k}["{TITLES[k]} ({len(by_domain[k])})"]' for k in nodes]
    flow += [f'  {a} -->|{n}| {b}' for (a, b), n in sorted(drawn.items())]
    out += ["## 1. Domains", "",
            "A declared grouping (`scripts/project_docs/domains.py`; the database records none). Every table is in "
            "exactly one domain, and a table in none stops the generator. *→ Tenants* and *→ Identity* count the "
            "domain's foreign keys into those two domains.", "",
            table(["Domain", "Tables", "Columns", "Foreign keys inside the domain", "→ Tenants", "→ Identity",
                   "Tables with a raising trigger"], rows), "",
            "Foreign keys between the other domains (an arrow points from the referencing domain to the referenced "
            "one; the label is the number of foreign keys; links into Tenants and Identity are in the table above):",
            "", mermaid("\n".join(flow)), ""]

    # 2 · tenancy
    org_tables = {q: r for q, r in tables.items() if q != TENANT and any(c["name"] == "org_id" for c in r["columns"])}
    with_fk = {q for q, r in org_tables.items() if any(f["columns"] == ["org_id"] and f["ref"] == TENANT
                                                         for f in r["fks"])}
    nullable = {q for q, r in org_tables.items() if next(c for c in r["columns"] if c["name"] == "org_id")["nullable"]}
    rls = [q for q, r in tables.items() if r["rls"]]
    to_tenant = {q: [f for f in r["fks"] if f["ref"] == TENANT] for q, r in tables.items() if q != TENANT}
    to_tenant = {q: fs for q, fs in to_tenant.items() if fs}
    other_cols = Counter(c for fs in to_tenant.values() for f in fs for c in f["columns"] if c != "org_id")
    rows = []
    for key, title, _ in DOMAINS:
        ts = by_domain.get(key, {})
        if ts:
            o = [q for q in ts if q in org_tables]
            rows.append([title, len(ts), len(o), sum(1 for q in o if q in with_fk), sum(1 for q in o if q in nullable),
                         sum(1 for q in ts if q in to_tenant)])
    identity = {q: r for q, r in tables.items() if dom[q] == "identity" or q == TENANT}
    out += ["## 2. Tenancy and access control", "",
            f"The tenant table is `organizations`. **{len(org_tables)} of the other {len(tables) - 1} tables** carry an `org_id` "
            f"column; {len(with_fk)} of them declare it a foreign key to `organizations`, and in {len(nullable)} it "
            f"accepts NULL. Counting every column, **{len(to_tenant)} tables** hold at least one foreign key to "
            "`organizations`; the columns other than `org_id` that do so are "
            + ", ".join(f"`{c}` ({n})" for c, n in sorted(other_cols.items())) + ". "
            f"**{len(rls)} tables** have row-level security enabled and **{len(cat['policies'])}** row-level "
            "policies exist (`pg_class.relrowsecurity`, `pg_policies`): the database does not filter rows by tenant "
            "itself. How the application scopes reads and writes to the signed-in organisation and checks "
            "permissions: [SOFTWARE_DESCRIPTION.md §6](SOFTWARE_DESCRIPTION.md#6-security-multi-tenancy--access-control).",
            "", table(["Domain", "Tables", "With org_id", "org_id → organizations", "org_id nullable",
                       "Any foreign key → organizations"], rows), ""]
    no_fk = sorted(_short(q) for q in org_tables if q not in with_fk)
    if no_fk:
        out += [f"Tables whose `org_id` has no foreign key to `organizations` ({len(no_fk)}): "
                + ", ".join(f"`{t}`" for t in no_fk) + ".", ""]
    if nullable:
        out += [f"Tables whose `org_id` accepts NULL ({len(nullable)}): "
                + ", ".join(f"`{_short(t)}`" for t in sorted(nullable)) + ".", ""]
    out += ["Identity and access tables with the tenant table (key columns and their foreign keys):", "",
            _er_diagram(identity), ""]
    if cat["permissions"]:
        out += [f"**Permission catalogue** — the {len(cat['permissions'])} rows the migrations insert into "
                "`permissions` (roles are per organisation and hold permissions through `role_permissions`):", "",
                table(["Code", "Description"], [[f"`{c}`", d] for c, d in cat["permissions"]]), ""]

    # 3 · triggers
    out += ["## 3. Append-only and guard triggers", "",
            f"{len(raising)} triggers on {len({q for q, _ in raising})} tables run a function that raises an "
            "exception — it refuses the statement it fires on (the condition is in the function). The message is "
            "quoted as the function writes it (`%` is filled in at run time).", "",
            table(["Table", "Trigger", "Fires", "Function", "Raises"],
                  [[f"`{_short(q)}`", f"`{t['name']}`", f"{t['timing']} {t['events']}", f"`{t['function']}`",
                    " · ".join(t["raises"])] for q, t in raising]), ""]
    other = [(q, t) for q, t in triggers if not t["raises"]]
    if other:
        out += [f"The other {len(other)} triggers raise nothing (they maintain a column or write history):", "",
                table(["Table", "Trigger", "Fires", "Function"],
                      [[f"`{_short(q)}`", f"`{t['name']}`", f"{t['timing']} {t['events']}", f"`{t['function']}`"]
                       for q, t in other]), ""]

    # 4 · tables by domain
    out += ["## 4. Tables by domain", ""]
    for n, (key, title, _) in enumerate(DOMAINS, 1):
        ts = by_domain.get(key, {})
        if not ts:
            continue
        out += [f"### 4.{n} {title} ({len(ts)} tables)", "", _er_diagram(ts), ""]
        to_org = sorted(_short(q) for q, r in ts.items() if q != TENANT and any(f["ref"] == TENANT for f in r["fks"]))
        if to_org:
            out += [f"{len(to_org)} of these tables reference `organizations` (not drawn).", ""]
        links = [[f"`{_short(q)}`", ", ".join(f["columns"]), f"`{_short(f['ref'])}`", TITLES[dom[f["ref"]]]]
                 for q, r in ts.items() for f in r["fks"]
                 if f["ref"] not in ts and f["ref"] != TENANT and f["ref"] in dom]
        if links:
            out += ["Foreign keys to other domains:", "", table(["Table", "Columns", "References", "Domain"], links), ""]
        for q, r in ts.items():
            out += _table_section(q, r)

    # 5 · views, 6 · functions
    out += ["## 5. Views", "", table(["View", "Columns", "Reads"],
                                     [[f"`{_short(q)}`", len(r["columns"]), ", ".join(f"`{_short(x)}`" for x in r["reads"])]
                                      for q, r in views.items()]), "",
            "## 6. Functions", "", "Functions other than trigger functions:", ""]
    out += [f"- `{f}`" for f in cat["functions"]] or ["- none"]
    return "\n".join(out).rstrip() + "\n"
