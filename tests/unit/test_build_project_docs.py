"""The project-document generator (scripts/build_project_docs.py, scripts/project_docs/): its readers, the gating
mirrors, the schema rendering on a small catalogue, and — without a database — that docs/APP_FLOW.md,
docs/DESIGN_BRIEF.md and docs/TECHNICAL_REQUIREMENTS.md are what the code produces now (the gate checks all four,
docs/BACKEND_SCHEMA.md from a scratch build of the migrations)."""
from __future__ import annotations

import pytest

from scripts.build_project_docs import compare
from scripts.project_docs import catalogue, design, domains, flow, journeys, schema, stack
from scripts.project_docs.source import (
    ROOT,
    Ident,
    StaleText,
    const_value,
    css_block,
    css_vars,
    exported_functions,
    function_source,
    sha12,
    string_list_consts,
    table,
    tied,
)

TS = """
const AGRI = ['manufacturer']
const FIN = ['bank', 'insurer']
// a comment with an apostrophe: it's ignored
const GROUPS: Group[] = [
  { label: 'Sense', color: 'var(--stage-sense)', flow: true, items: [
    { to: '/a', label: 'A', icon: Globe, perm: 'modules.view' },   // trailing comment
    { to: '/b', label: "B's", icon: Home, sectors: [...FIN, ...AGRI],
      anyPerm: ['x', 'y'] },
  ] },
  { label: null, items: [] },
]
export function Box({ value, format = (n) => `${Math.round(n)}`, size = 3 }: { value: number }) { return null }
function Gate() {
  const q = useQuery({ a: 1 })
  if (q) { return <X /> }
  return <Y />
}
"""


def test_typescript_literals_are_read_with_spreads_identifiers_and_comments():
    consts = string_list_consts(TS)
    assert consts == {"AGRI": ["manufacturer"], "FIN": ["bank", "insurer"]}
    groups = const_value(TS, "GROUPS", consts)
    assert groups[0]["flow"] is True and groups[1]["label"] is None
    a, b = groups[0]["items"]
    assert isinstance(a["icon"], Ident) and a["perm"] == "modules.view"
    assert b["label"] == "B's" and b["sectors"] == ["bank", "insurer", "manufacturer"] and b["anyPerm"] == ["x", "y"]


def test_function_source_and_exported_parameters():
    assert function_source(TS, "Gate").startswith("function Gate()") and function_source(TS, "Gate").endswith("}")
    (box,) = exported_functions(TS)
    assert box["name"] == "Box" and box["params"] == ["value", "format", "size"]   # a template literal in a default


def test_css_custom_properties_with_their_comment():
    css = ':root {\n  --a: #fff;   /* white */\n  --b: 1px solid var(--a);\n}\n[data-theme="dark"] { --a: #000; }\n'
    assert css_vars(css_block(css, ":root")) == [("--a", "#fff", "white"), ("--b", "1px solid var(--a)", "")]
    assert css_vars(css_block(css, '[data-theme="dark"]')) == [("--a", "#000", "")]


def test_a_tied_passage_stops_when_its_source_changes():
    src = {"f": "function f() {}"}
    ok = sha12("f\nfunction f() {}")
    assert tied("x", "text", src, ok) == "text"
    with pytest.raises(StaleText, match="set its checksum to"):
        tied("x", "text", {"f": "function f() { return 1 }"}, ok)


def test_markdown_table_escapes_pipes_and_html_outside_code():
    assert table(["a"], [["x | <b> `<c>`"]]).splitlines()[-1] == "| x \\| &lt;b&gt; `<c>` |"


def test_every_table_needs_a_domain():
    assert domains.domain_of("public.sc_eudr_dds") == "eudr"          # EUDR before the agri sc_* pattern
    assert domains.domain_of("public.sc_suppliers") == "agri"
    assert domains.domain_of("migration_meta.applied_file") == "reference"
    with pytest.raises(domains.UnassignedTable):
        domains.domain_of("public.no_such_table_anywhere")
    with pytest.raises(domains.UnassignedTable):
        domains.domain_of("other.users")                                # a pattern without a schema is public only


def _col(name, typ="uuid", nullable=False):
    return {"name": name, "type": typ, "nullable": nullable, "default": "", "comment": "", "identity": "",
            "generated": False}


def _rel(columns, pk, fks=(), uniques=(), triggers=(), kind="table"):
    return {"kind": kind, "comment": "", "rls": False, "columns": columns, "pk": pk, "uniques": list(uniques),
            "fks": list(fks), "checks": [], "excludes": [], "indexes": [], "triggers": list(triggers), "reads": []}


def test_schema_renders_tenancy_triggers_and_cardinality():
    fk = lambda cols, ref: {"name": f"fk_{cols[0]}", "columns": cols, "ref": ref, "ref_columns": ["org_id"],  # noqa: E731
                            "on_delete": "cascade", "on_update": "no action"}
    guard = {"name": "no_update", "timing": "BEFORE", "events": "UPDATE OR DELETE", "per": "row",
             "function": "public.refuse", "raises": ["users is append-only"], "definition": ""}
    cat = {"relations": {
        "public.organizations": _rel([_col("org_id")], ["org_id"]),
        "public.users": _rel([_col("user_id"), _col("org_id")], ["user_id"], [fk(["org_id"], "public.organizations")],
                             triggers=[guard]),
        "public.api_keys": _rel([_col("key_id"), _col("org_id", nullable=True)], ["key_id"],
                                [fk(["org_id"], "public.organizations")],
                                uniques=[{"name": "u_org", "columns": ["org_id"]}]),
        "public.v_users": _rel([_col("user_id")], [], kind="view")},
        "functions": [], "policies": [], "extensions": ["plpgsql"], "permissions": [["modules.view", "see"]]}
    md = schema.render(cat, {"revisions": 2, "heads": ["h"]})
    assert "**3 tables**" in md and "1 views" in md and "2 foreign keys" in md
    assert "**2 of the other 2 tables** carry an `org_id`" in md and "in 1 it accepts NULL" in md
    assert "| `users` | `no_update` | BEFORE UPDATE OR DELETE | `public.refuse` | users is append-only |" in md
    assert 'organizations ||--o{ users : "org_id"' in md          # not-null FK, many children
    assert 'organizations |o--o| api_keys : "org_id"' in md        # nullable FK, unique → at most one
    assert "| `modules.view` | see |" in md


def test_sidebar_gate_and_stage_numbering_mirror_the_shell():
    groups = [{"label": "Sense", "flow": True, "items": [{"to": "/a", "label": "A", "perm": "p"}]},
              {"label": "Assess", "flow": True, "items": [{"to": "/b", "label": "B", "sectors": ["bank"]}]},
              {"label": "Set up", "items": [{"to": "/c", "label": "C", "anyPerm": ["q", "r"]}]}]
    assert flow.visible(groups[2]["items"][0], ["r"], "") and not flow.visible(groups[2]["items"][0], ["p"], "")
    shown = flow.menu(groups, ["r"], "bank")                        # Sense hidden: Assess becomes stage 1
    assert [g for g, _ in shown] == ["1 · Assess", "Set up"]


def test_a_journey_whose_screen_moved_is_refused(monkeypatch):
    rs = {"workspace": [{"path": "/kri"}, {"path": "/funds/:id"}]}
    nav = {"GROUPS": [{"items": [{"to": "/kri", "label": "Risk & analysis"}]}]}
    hubs = [{"tabs": [{"to": "/kri", "label": "KRI dashboard"}]}]
    monkeypatch.setattr(journeys, "JOURNEYS", [{"title": "J", "steps": [
        ("/kri", "sidebar: Risk & analysis", ""), ("/funds/42", "page: a fund", ""), ("/kri", "tab: KRI dashboard", "")]}])
    journeys.check(rs, nav, hubs)
    monkeypatch.setattr(journeys, "JOURNEYS", [{"title": "J", "steps": [("/gone", "sidebar: Risk & analysis", "")]}])
    with pytest.raises(journeys.StaleJourney, match="route /gone no longer exists"):
        journeys.check(rs, nav, hubs)


def test_contrast_is_the_wcag_ratio():
    assert design.contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert design.contrast("#777777", "#777777") == pytest.approx(1.0)


def test_python_dependencies_carry_their_comment_and_settings_never_their_value():
    raw = ('[project]\nname = "x"\ndependencies = [\n    # Database\n    "a>=1",\n    "b>=2",  # bee\n]\n'
           '[project.optional-dependencies]\napi = [\n    "c>=3",\n]\n')
    assert stack.python_dependencies(raw) == [("core", "a>=1", "Database"), ("core", "b>=2", "bee"), ("api", "c>=3", "")]
    src = 'class Settings(BaseSettings):\n    SECRET_KEY: str = "dev-insecure"  # signing key\n    N: int = 3\n'
    rows = stack.settings_fields(src)
    assert rows == [["`SECRET_KEY`", "str", "signing key"], ["`N`", "int", ""]] and "dev-insecure" not in str(rows)
    assert stack.gate_steps('step "lint"\nruff\nstep "tests (+ guard)"\n') == ["lint", "tests (+ guard)"]


def test_compare_names_a_document_that_differs():
    (diff,) = compare({"NO_SUCH_DOCUMENT.md": "line\n"})
    assert "docs/NO_SUCH_DOCUMENT.md (from the code)" in diff and "+line" in diff


@pytest.mark.parametrize("name, render", [
    ("APP_FLOW.md", flow.render), ("DESIGN_BRIEF.md", design.render),
    ("TECHNICAL_REQUIREMENTS.md", lambda: stack.render(catalogue.migration_files()))])
def test_generated_documents_match_the_code(name, render):
    assert (ROOT / "docs" / name).read_text(encoding="utf-8") == render(), (
        f"docs/{name} differs from the code — venv/bin/python -m scripts.build_project_docs --write")


def test_the_ui_standard_governs_the_design_brief():
    import json
    std = json.loads((ROOT / design.STANDARD).read_text(encoding="utf-8"))
    assert std["stated_by"] and std["date"] and std["applies_to"]
    assert {r["id"] for r in std["rules"]} == {"customer_language", "minimal_text", "visual_first"}
    md = design.render()
    first = md.index("## 1. The standard every screen must meet (governing)")
    assert first < md.index("## 2. ") and all(f"**{r['title']}.**" in md for r in std["rules"])
