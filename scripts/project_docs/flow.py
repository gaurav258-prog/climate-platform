"""docs/APP_FLOW.md — the routes, the sidebar, the hub tabs and who sees what, read from the web app's own
configuration (web/src/App.tsx, web/src/components/Shell.tsx and the tab components) and the role templates a tenant is
created with. The gating rules are mirrored here in Python; each mirror is tied to the TypeScript it copies, so a change
to that code stops the generator until the mirror is re-read (source.tied)."""
from __future__ import annotations

import ast
import re

from scripts.project_docs import journeys
from scripts.project_docs.source import (
    banner,
    const_value,
    function_source,
    mermaid,
    read,
    string_list_consts,
    table,
    tied,
)

APP, SHELL = "web/src/App.tsx", "web/src/components/Shell.tsx"
HUBS = [  # (hub, file, const) — the tab sets several pages share
    ("Your data", "web/src/components/SectionTabs.tsx", "DATA_TABS"),
    ("Settings & team", "web/src/components/SectionTabs.tsx", "ADMIN_TABS"),
    ("Help & guides", "web/src/components/SectionTabs.tsx", "HELP_TABS"),
    ("Risk & analysis", "web/src/components/ReviewTabs.tsx", "TABS"),
    ("Reports & filings (agriculture)", "web/src/components/ReportTabs.tsx", "TABS"),
    ("Clients (operator)", "web/src/components/OperatorTabs.tsx", "TABS"),
]
CUSTOMER_SECTORS = ["bank", "insurer", "asset_manager", "reit", "manufacturer"]


# ── reading the configuration ───────────────────────────────────────────────────────────────────────────────────────
def routes(app_src: str) -> dict:
    """{'public': [...], 'workspace': [...]} — each route {path, kind: page|redirect|front-door, component, file, to}."""
    pages = dict(re.findall(r"const (\w+) = lazy\(\(\) => import\('\./pages/(\w+)'\)\)", app_src))
    pages.update(dict(re.findall(r"^import (\w+) from '\./pages/(\w+)'", app_src, re.M)))
    out = {}
    for block, fn in (("public", "App"), ("workspace", "Workspace")):
        found = []
        for path, element in re.findall(r'<Route\s+path="([^"]+)"\s+element=\{(.*?)\}\s*/>', function_source(app_src, fn)):
            nav = re.fullmatch(r'<Navigate to="([^"]+)" replace />', element.strip())
            comp = re.fullmatch(r"<(\w+)(\s[^>]*)?/>", element.strip())
            if nav:
                found.append({"path": path, "kind": "redirect", "to": nav.group(1)})
            elif comp and comp.group(1) in pages:
                found.append({"path": path, "kind": "page", "component": comp.group(1),
                              "file": f"web/src/pages/{pages[comp.group(1)]}.tsx", "props": (comp.group(2) or "").strip()})
            elif comp and comp.group(1) == "Workspace":
                found.append({"path": path, "kind": "workspace"})
            else:
                found.append({"path": path, "kind": "front-door"})
        out[block] = found
    return out


def sidebar(shell_src: str) -> dict[str, list[dict]]:
    consts = string_list_consts(shell_src)
    return {name: const_value(shell_src, name, consts) for name in ("GROUPS", "REG_GROUPS", "RESPONDENT_GROUPS")}


def hubs() -> list[dict]:
    out = []
    for hub, path, const in HUBS:
        src = read(path)
        out.append({"hub": hub, "file": path, "const": const, "tabs": const_value(src, const, string_list_consts(src))})
    return out


def operator_permissions() -> list[str]:
    """The permissions scripts/seed_platform_operator.py grants the 'platform-operator' role."""
    src = read("scripts/seed_platform_operator.py")
    m = re.search(r'"c":\s*(\[[^\]]*\])', src)
    return ast.literal_eval(m.group(1))


def role_templates() -> dict[str, dict[str, list[str]]]:
    from services.governance.tenant_provisioning import DEFAULT_ROLE_PERMS, RESPONDENT_ROLE_PERMS
    from services.supervision.profiles import role_templates as supervisor_roles
    return {"customer": DEFAULT_ROLE_PERMS,
            "regulator": {k: list(v["permissions"]) for k, v in supervisor_roles().items()},
            "respondent": RESPONDENT_ROLE_PERMS,
            "operator": {"platform-operator": operator_permissions()}}


# ── the gating rules, mirrored ──────────────────────────────────────────────────────────────────────────────────────
def _gate_sources() -> dict[str, str]:
    shell, app = read(SHELL), read(APP)
    section = read("web/src/components/SectionTabs.tsx")
    review, report = read("web/src/components/ReviewTabs.tsx"), read("web/src/components/ReportTabs.tsx")

    def grab(src: str, pattern: str, what: str) -> str:
        m = re.search(pattern, src, re.S)
        if not m:
            raise LookupError(f"{what}: the code this document mirrors is gone — re-read it and update flow.py")
        return m.group(0)
    return {
        "Shell.tsx visible()": grab(shell, r"const visible = \(it: Item\) =>.*?\n\n", "sidebar gate"),
        "Shell.tsx menu choice": grab(shell, r"\(profile\?\.org\?\.plan === 'respondent' \?[^\n]*GROUPS\)", "menu choice"),
        "SectionTabs.tsx filter": grab(section, r"const shown = tabs\.filter\([^\n]*", "hub tab gate"),
        "ReviewTabs.tsx filter": grab(review, r"const tabs = TABS\.filter\([^\n]*", "review tab gate"),
        "ReportTabs.tsx gate": grab(report, r"if \(profile\?\.org\?\.type !== 'manufacturer'\) return null", "report tab gate"),
        "App.tsx Workspace": function_source(app, "Workspace"),
        "App.tsx FirstRunGate": function_source(app, "FirstRunGate"),
    }


def visible(item: dict, perms: list[str], sector: str) -> bool:
    """Shell.tsx `visible`: the permission, any of the permissions, and the sector must all allow the item."""
    return ((not item.get("perm") or item["perm"] in perms)
            and (not item.get("anyPerm") or any(p in perms for p in item["anyPerm"]))
            and (not item.get("sectors") or sector in item["sectors"]))


def menu(groups: list[dict], perms: list[str], sector: str) -> list[tuple[str, list[dict]]]:
    """The groups a user sees, in order, flow stages numbered after filtering (as Shell.tsx numbers them)."""
    out, stage = [], 0
    for g in groups:
        items = [it for it in g["items"] if visible(it, perms, sector)]
        if items:
            if g.get("flow"):
                stage += 1
            out.append(((f"{stage} · " if g.get("flow") else "") + (g.get("label") or ""), items))
    return out


def _rule(item: dict) -> str:
    parts = [f"`{item['perm']}`"] if item.get("perm") else []
    if item.get("anyPerm"):
        parts.append("any of " + ", ".join(f"`{p}`" for p in item["anyPerm"]))
    return " and ".join(parts) or "none"


def _route_pattern(path: str) -> re.Pattern:
    return re.compile("^" + re.sub(r":\w+", r"[^/]+", path) + "$")


# ── rendering ───────────────────────────────────────────────────────────────────────────────────────────────────────
FRONT_DOOR = """\
- Not signed in: the sign-in page (`Login`), whatever the path — except the public pages listed above, which work by link.
- Signed in, path `/`:
  - a platform operator (holds `platform.admin` but not `modules.view`) is sent to `/platform`;
  - an organisation on the `respondent` plan is sent to `/portal`;
  - an administrator (holds `admin.users.manage`) whose organisation's onboarding is available and not yet live
    (`GET /v1/admin/onboarding`) is sent to `/onboarding` (Get started);
  - everyone else sees Horizon (the globe).
- Any other unknown path is sent to `/`.
- Which menu the sidebar shows: the respondent menu for a `respondent`-plan organisation, the supervisor menu for an
  organisation of type `regulator`, the customer workspace menu otherwise."""

FRONT_DOOR_FLOW = """\
flowchart TD
  A([Open the app]) --> P{"Public route?<br/>{public}"}
  P -- yes --> PUB[Public page, no sign-in]
  P -- no --> S{Signed in?}
  S -- no --> L[Sign-in page]
  S -- yes --> R{Path is /?}
  R -- no --> K{Known route?}
  K -- yes --> PAGE[That page, inside the shell]
  K -- no --> R
  R -- yes --> O{platform.admin and not modules.view?}
  O -- yes --> OPS["/platform · Tenants"]
  O -- no --> RP{Plan = respondent?}
  RP -- yes --> PORTAL["/portal · Supervisory portal"]
  RP -- no --> AD{Admin and onboarding not live?}
  AD -- yes --> ON["/onboarding · Get started"]
  AD -- no --> H[Horizon globe]"""


def render() -> str:
    gates = _gate_sources()
    rs = routes(read(APP))
    nav = sidebar(read(SHELL))
    hub_list = hubs()
    roles = role_templates()
    pages = [r for r in rs["workspace"] if r["kind"] == "page"]
    nav_at = {it["to"]: (g.get("label") or "", it["label"]) for name in nav for g in nav[name] for it in g["items"]}
    tab_at: dict[str, list[str]] = {}
    for h in hub_list:
        for t in h["tabs"]:
            tab_at.setdefault(t["to"], []).append(f"{h['hub']} › {t['label']}")

    out = ["# App flow — Tellumen climate platform", "",
           banner("`web/src/App.tsx`, `web/src/components/Shell.tsx`, the hub tab components, and the role templates "
                  "(`services/governance/tenant_provisioning.py`, `data/reference/supervision_profiles.json`, "
                  "`scripts/seed_platform_operator.py`)"), "",
           f"The web app has **{sum(r['kind'] == 'page' for r in rs['public'])} public pages** (no sign-in) and **{len(rs['workspace'])} routes in "
           f"the signed-in workspace** ({len(pages)} pages, {sum(r['kind'] == 'redirect' for r in rs['workspace'])} "
           "redirects and the front door), all inside one shell with a sidebar. What a signed-in user sees is gated "
           "twice: by the organisation's sector (its type) and by the permissions of the user's roles. The sidebar "
           "follows the operational loop in numbered stages. Section 6 has the key journeys, each walked in the "
           "running app. This document describes the screens as they are; the standard every screen must meet is "
           "[DESIGN_BRIEF.md](DESIGN_BRIEF.md) §1.", "",
           "## 1. The front door", "",
           "Public routes: " + ", ".join(f"`{r['path']}`" + (f" ({r['component']})" if r.get("component") else "")
                                         for r in rs["public"] if r["kind"] == "page") + ".", "",
           tied("APP_FLOW front door", FRONT_DOOR, gates, "5cb496441005"), "",
           mermaid(FRONT_DOOR_FLOW.replace("{public}", "<br/>".join(
               r["path"] for r in rs["public"] if r["kind"] == "page"))), ""]

    # 2 · the customer workspace sidebar
    stages = [g for g in nav["GROUPS"] if g.get("flow")]
    loop = ["flowchart LR"]
    for k, g in enumerate(stages, 1):
        loop.append(f'  S{k}["<b>{k} · {g["label"]}</b><br/>'
                    + "<br/>".join(f'{it["label"]} · {it["to"]}' for it in g["items"]) + '"]')
    loop += [f"  S{k} --> S{k + 1}" for k in range(1, len(stages))]
    rows = []
    for g in nav["GROUPS"]:
        for it in g["items"]:
            who = [r for r, p in roles["customer"].items() if visible({**it, "sectors": None}, p, "")]
            rows.append([g.get("label") or "", it["label"], f"`{it['to']}`",
                         ", ".join(it.get("sectors") or ["every sector"]), _rule(it), ", ".join(who) or "—"])
    named = re.search(r"operational loop \(([^)]*)\)", read("docs/SOFTWARE_DESCRIPTION.md"))
    out += ["## 2. The operational loop — the customer workspace sidebar", "",
            f"`GROUPS` in `{SHELL}`: {len(stages)} numbered stages — "
            + " → ".join(g["label"] for g in stages) + " — then *Set up* and *Platform*. "
            + (f"([SOFTWARE_DESCRIPTION.md](SOFTWARE_DESCRIPTION.md) §2 names the loop {named.group(1)}.) " if named else "")
            + "Each entry is one destination; related pages are tabs inside a hub (section 3). Stage numbers count "
            "only the stages a user can see.", "", mermaid("\n".join(loop)), "",
            "Every entry with its gates. *Default roles* are the role templates a new customer tenant gets "
            "(`DEFAULT_ROLE_PERMS`) that pass the permission rule; the sector rule applies on top.", "",
            table(["Group", "Entry", "Route", "Sectors", "Permission rule", "Default roles"], rows), ""]

    # 3 · hubs
    used: dict[str, list[str]] = {}
    for r in pages:
        src = read(r["file"])
        for h in hub_list:
            comp = h["file"].rsplit("/", 1)[1][:-4]
            marker = f"tabs={{{h['const']}}}" if comp == "SectionTabs" else f"<{comp}"
            if marker in src:
                used.setdefault(h["hub"], []).append(r["path"])
    out += ["## 3. Hubs — pages shown as tabs of one entry", "",
            "A hub's tab strip shows a tab only where the sector (and, for the `SectionTabs` hubs, the permission) "
            "allows it. `SectionTabs` hides itself when one tab or none would show; the agriculture *Reports & "
            "filings* strip shows only for sector `manufacturer`.", ""]
    for h in hub_list:
        out += [f"**{h['hub']}** — `{h['const']}` in `{h['file']}`; rendered on "
                + (", ".join(f"`{p}`" for p in sorted(used.get(h["hub"], []))) or "no page") + ".", "",
                table(["Tab", "Route", "Sectors", "Permission"],
                      [[t["label"], f"`{t['to']}`", ", ".join(t.get("sectors") or ["every sector"]),
                        f"`{t['perm']}`" if t.get("perm") else ""] for t in h["tabs"]]), ""]

    # 4 · screens per role
    out += ["## 4. Screens per role", "",
            "The role templates below are what a new organisation is created with; an administrator holding "
            "`admin.roles.manage` can change an organisation's roles afterwards, so a live organisation may differ.", "",
            "### 4.1 Customer workspaces (bank, insurer, asset manager, REIT, agriculture)", "",
            table(["Role", "Permissions (`DEFAULT_ROLE_PERMS`)"],
                  [[f"`{r}`", ", ".join(f"`{p}`" for p in ps)] for r, ps in roles["customer"].items()]), "",
            "The sidebar each role sees, per sector (group › entries):", ""]
    for sector in CUSTOMER_SECTORS:
        out += [f"**{sector}**", ""]
        for role, perms in roles["customer"].items():
            m = menu(nav["GROUPS"], perms, sector)
            out.append(f"- `{role}`: " + " · ".join(f"*{g}* › " + ", ".join(it["label"] for it in its) for g, its in m))
        out.append("")
    reg_rows = [[f"`{r}`", ", ".join(f"`{p}`" for p in ps),
                 " · ".join(", ".join(it["label"] for it in its) for _, its in menu(nav["REG_GROUPS"], ps, "regulator"))]
                for r, ps in roles["regulator"].items()]
    out += ["### 4.2 Supervisor workspace (organisation type `regulator`)", "",
            "`REG_GROUPS` in `Shell.tsx`; role templates from `data/reference/supervision_profiles.json` (`roles`).", "",
            table(["Entry", "Route", "Permission rule"],
                  [[it["label"], f"`{it['to']}`", _rule(it)] for g in nav["REG_GROUPS"] for it in g["items"]]), "",
            table(["Role", "Permissions", "Sidebar"], reg_rows), "",
            "### 4.3 Respondent (a supervised entity on the `respondent` plan)", "",
            table(["Role", "Permissions", "Sidebar"],
                  [[f"`{r}`", ", ".join(f"`{p}`" for p in ps),
                    ", ".join(it["label"] for _, its in menu(nav["RESPONDENT_GROUPS"], ps, "") for it in its)]
                   for r, ps in roles["respondent"].items()]), "",
            "### 4.4 Platform operator (Tellumen staff, organisation type `platform`)", "",
            table(["Role", "Permissions (`scripts/seed_platform_operator.py`)", "Sidebar"],
                  [[f"`{r}`", ", ".join(f"`{p}`" for p in ps),
                    " · ".join(f"*{g}* › " + ", ".join(it["label"] for it in its)
                               for g, its in menu(nav["GROUPS"], ps, "platform"))]
                   for r, ps in roles["operator"].items()]), ""]

    # 5 · all routes
    rows = []
    for r in rs["workspace"]:
        where = [f"sidebar › {' › '.join(x for x in nav_at[r['path']] if x)}"] if r["path"] in nav_at else []
        where += tab_at.get(r["path"], [])
        what = (f"`{r['component']}`" + (f" ({r['props']})" if r.get("props") else "") if r["kind"] == "page"
                else f"redirect → `{r['to']}`" if r["kind"] == "redirect" else "front door (section 1)")
        rows.append([f"`{r['path']}`", what, f"`{r['file']}`" if r.get("file") else "", "; ".join(where)])
    unreached = [r["path"] for r in pages if r["path"] not in nav_at and r["path"] not in tab_at]
    out += ["## 5. All routes in the workspace", "",
            table(["Route", "Renders", "File", "Reached from"], rows), "",
            f"{len(unreached)} pages are in neither the sidebar nor a hub tab — they are opened from inside other "
            "pages (detail views, sub-pages): " + ", ".join(f"`{p}`" for p in unreached) + ".", ""]

    # 6 · journeys
    out += ["## 6. Key journeys (walked in the running app)", "",
            "Each journey was walked in the running app on the date shown, signed in through the sign-in page's "
            "one-click demo sectors (no password typed). *Seen* is what the page showed. The generator checks every "
            "step's route against the routes above and every sidebar or tab label against the configuration, so a "
            "renamed or removed screen stops it until the journey is walked again.", ""]
    out += journeys.render(rs, nav, hub_list)
    return "\n".join(out).rstrip() + "\n"


def route_exists(path: str, rs: dict) -> bool:
    return any(_route_pattern(r["path"]).match(path) for block in rs.values() for r in block if r["path"] != "*")
