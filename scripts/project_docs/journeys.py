"""The key user journeys docs/APP_FLOW.md draws — each one walked in the running app, step by step, on the date given.

A step is (route, how it was reached, what the page showed). How it was reached is one of:
  'sign-in: <role> › <sector>'  the sign-in page's one-click demo sectors (no password typed)
  'front door'                   where `/` sent the user
  'sidebar: <label>'             the sidebar entry with that label (must point at the route)
  'tab: <label>'                 a hub tab with that label (must point at the route)
  'page: <text>'                 a link or row inside the previous page
`check` refuses a step whose route no longer exists or whose sidebar / tab label no longer leads there: the journey
must then be walked again and this record corrected.
"""
from __future__ import annotations

import re

from scripts.project_docs.source import mermaid, table

WALKED = "2026-10-16"
JOURNEYS: list[dict] = [
    {"title": "Bank analyst: sign in, then the operational loop",
     "who": "analyst of the bank demo tenant (Meridian Bank, role `analyst` only)", "walked": WALKED, "steps": [
         ("/", "sign-in: analyst › Bank", "Horizon globe, headed 'HORIZON · MERIDIAN BANK (DEMO)'; the sidebar held "
                                          "exactly the entries section 4.1 lists for analyst / bank"),
         ("/portfolio", "sidebar: Portfolio", "page 'Portfolio'"),
         ("/kri", "sidebar: Risk & analysis", "page 'KRI dashboard'"),
         ("/loss", "tab: Loss", "page 'Loss from the hazard itself'"),
         ("/decisions", "sidebar: Decisions", "page 'Forward-risk decisions'"),
         ("/compliance", "sidebar: Reports & filings", "page 'Reports & filings'"),
         ("/tasks", "sidebar: Tasks", "page 'Tasks'"),
         ("/approvals", "sidebar: My approvals", "page 'Approvals'")]},
    {"title": "Agriculture analyst: sites, risk and filings",
     "who": "analyst of the agriculture demo tenant (Terra Foods)", "walked": WALKED, "steps": [
         ("/", "sign-in: analyst › Agriculture", "Horizon globe, headed 'HORIZON · TERRA FOODS (DEMO)'; the sidebar "
                                                 "held exactly the entries section 4.1 lists for analyst / manufacturer"),
         ("/home", "sidebar: Overview", "page 'Overview'"),
         ("/data", "sidebar: Your data", "page 'Your data' with the tabs Your data, Our sites, Suppliers & crops, "
                                         "Data dictionary, Data sources, Transmission"),
         ("/sourcing", "tab: Suppliers & crops", "page 'Sourcing book'"),
         ("/riskmap", "sidebar: Risk map", "page 'Risk map'"),
         ("/early-warning", "sidebar: Early warning", "page 'Early warning'"),
         ("/filings", "sidebar: Reports & filings", "page 'Filings' with the tabs Reports & filings, EUDR statements, "
                                                    "Supply disclosure, ESRS statement, Prior filings"),
         ("/eudr", "tab: EUDR statements", "page 'EUDR due diligence statements'"),
         ("/esrs", "tab: ESRS statement", "page 'ESRS sustainability statement'")]},
    {"title": "Asset-manager administrator: first-run funnel, a fund, filings",
     "who": "admin of the asset-manager demo tenant (Nordkap Asset Management, role `admin` only)", "walked": WALKED,
     "steps": [
         ("/onboarding", "sign-in: admin › Asset manager", "sent from / to Get started (the first-run rule of section 1); "
                                                           "the sidebar held exactly the entries section 4.1 lists for "
                                                           "admin / asset_manager"),
         ("/funds", "sidebar: Funds", "page 'Funds' with the list of the organisation's funds"),
         ("/funds/:id", "page: a fund in the list", "the fund's page, headed with its name and 'SFDR Art. 8'"),
         ("/compliance", "sidebar: Reports & filings", "page 'Reports & filings'"),
         ("/approvals", "sidebar: My approvals", "page 'Approvals'")]},
    {"title": "Banking supervisor (line supervisor): population, entity file, follow-up",
     "who": "approver of the banking-supervisor demo tenant (EU Banking Supervisor, role `supervisor` only)",
     "walked": WALKED, "steps": [
         ("/", "sign-in: approver › Banking supervisor", "Horizon globe, headed 'HORIZON · EU BANKING SUPERVISOR (DEMO)'; "
                                                         "the sidebar held exactly the entries section 4.2 lists for "
                                                         "role supervisor"),
         ("/supervisor/mandates", "sidebar: Regulations", "page 'Mandates and who they apply to'"),
         ("/supervised", "sidebar: Population", "page 'Supervised population'"),
         ("/supervised/:orgId", "page: an entity in the list", "the entity file, headed with the entity's name"),
         ("/supervisor/map", "sidebar: Exposure map", "page 'Where the supervised exposure sits'"),
         ("/supervisor/requests", "sidebar: Requests & findings", "page 'Engage and follow up'")]},
    {"title": "Administrator: settings, onboarding, single sign-on, billing, own security",
     "who": "admin of the bank demo tenant (Meridian Bank; this user holds the roles `admin` and `analyst`)",
     "walked": WALKED, "steps": [
         ("/", "sign-in: admin › Bank", "Horizon globe (the Get-started funnel did not apply)"),
         ("/admin", "sidebar: Settings & team", "page 'Control center'"),
         ("/onboarding", "tab: Get started", "page 'Go-live checklist'"),
         ("/sso", "tab: Single sign-on", "page 'Single sign-on & provisioning'"),
         ("/billing", "tab: Plan & billing", "page 'Plan & billing'"),
         ("/account-security", "sidebar: My security", "page 'Security'")]},
]
# Journeys deliberately not walked, and why (a named gap, not a guess at what they would show).
NOT_WALKED = [
    "Platform operator (Tenants, Client intake, Change pipeline, Reference data, Calibrations): the sign-in page has no "
    "one-click demo sector for the operator, and walking it would mean typing a password.",
    "Respondent portal (`/portal`): no one-click demo sector signs in as a respondent.",
    "The public token pages (`/onboarding/form/:token`, `/activate/:token`, `/remit/:token`, `/assurance/:token`, "
    "`/reset/:token`): each needs a token issued to a real recipient.",
]


class StaleJourney(RuntimeError):
    """A recorded journey no longer matches the app's routes or navigation."""


def _matches(pattern: str, path: str) -> bool:
    return re.fullmatch(re.sub(r":\w+", r"[^/]+", pattern), path) is not None


def check(rs: dict, nav: dict, hub_list: list[dict]) -> None:
    paths = [r["path"] for block in rs.values() for r in block if r["path"] != "*"]
    items = {(it["label"], it["to"]) for groups in nav.values() for g in groups for it in g["items"]}
    tabs = {(t["label"], t["to"]) for h in hub_list for t in h["tabs"]}
    problems = []
    for j in JOURNEYS:
        for route, how, _seen in j["steps"]:
            path = route.split("?")[0]
            if not any(_matches(p, path) for p in paths):
                problems.append(f"{j['title']}: route {route} no longer exists")
            kind, _, label = how.partition(": ")
            if kind == "sidebar" and (label, path) not in items:
                problems.append(f"{j['title']}: no sidebar entry '{label}' leads to {path}")
            if kind == "tab" and (label, path) not in tabs:
                problems.append(f"{j['title']}: no hub tab '{label}' leads to {path}")
    if problems:
        raise StaleJourney("walk these journeys again and correct scripts/project_docs/journeys.py:\n  "
                           + "\n  ".join(problems))


def _flow(j: dict) -> str:
    lines = ["flowchart LR", '  IN(["Sign-in page"])']
    for k, (route, how, _seen) in enumerate(j["steps"]):
        lines.append(f'  N{k}["{route}"]')
        lines.append(f'  {f"N{k - 1}" if k else "IN"} -- "{how.replace(chr(34), "")}" --> N{k}')
    return mermaid("\n".join(lines))


def render(rs: dict, nav: dict, hub_list: list[dict]) -> list[str]:
    check(rs, nav, hub_list)
    out: list[str] = []
    for n, j in enumerate(JOURNEYS, 1):
        out += [f"### 6.{n} {j['title']}", "", f"*Who:* {j['who']} · *walked:* {j['walked']}", "", _flow(j), "",
                table(["Step", "Route", "How", "Seen"],
                      [[k, f"`{route}`", how, seen] for k, (route, how, seen) in enumerate(j["steps"], 1)]), ""]
    if not JOURNEYS:
        out += ["No journey has been walked and recorded yet.", ""]
    if NOT_WALKED:
        out += ["**Not walked:**", ""] + [f"- {x}" for x in NOT_WALKED] + [""]
    return out
