"""docs/TECHNICAL_REQUIREMENTS.md — what the platform runs on and how it is built, tested and deployed, read from the
files that define it. Prose about security, tenancy, deployment and non-functional characteristics stays in
docs/SOFTWARE_DESCRIPTION.md and is linked, not repeated; only §9 is quoted, because it states a gap."""
from __future__ import annotations

import json
import re
import tomllib
from collections import Counter

from scripts.project_docs.source import ROOT, banner, read, table

SD = "SOFTWARE_DESCRIPTION.md"


def _yaml(rel: str) -> list:
    import yaml  # PyYAML arrives with mlflow (the api extra); imported here so the text helpers need nothing else
    return [d for d in yaml.safe_load_all(read(rel)) if d is not None]


def python_dependencies(raw: str) -> list[tuple[str, str, str]]:
    """(group, requirement, the comment that explains it) in pyproject order; 'core' is [project].dependencies."""
    data = tomllib.loads(raw)
    notes: dict[str, str] = {}
    last = ""
    for line in raw.splitlines():
        s = line.strip()
        if s.endswith("= [") or s == "]":
            last = ""
        elif s.startswith("#"):
            last = s.lstrip("# ")
        elif m := re.match(r'"([^"]+)",?\s*(?:#\s*(.*))?$', s):
            notes.setdefault(m.group(1), m.group(2) or last)
    groups = [("core", data["project"]["dependencies"])] + list(data["project"]["optional-dependencies"].items())
    return [(g, req, notes.get(req, "")) for g, reqs in groups for req in reqs]


def web_dependencies(package: dict, lock: dict) -> list[list[str]]:
    rows = []
    for kind in ("dependencies", "devDependencies"):
        for name, declared in sorted(package.get(kind, {}).items()):
            resolved = lock.get("packages", {}).get(f"node_modules/{name}", {}).get("version", "not in the lock file")
            rows.append([f"`{name}`", declared, resolved, "runtime" if kind == "dependencies" else "build / dev"])
    return rows


def gate_steps(precommit: str) -> list[str]:
    return re.findall(r'^step "(.+)"$', precommit, re.M)


def settings_fields(config_src: str) -> list[list[str]]:
    """Each `NAME: type = …` field of class Settings with its same-line comment — never its value."""
    body = config_src.split("class Settings", 1)[1]
    return [[f"`{m.group(1)}`", m.group(2).strip(), (m.group(3) or "").strip()]
            for m in re.finditer(r"^    ([A-Z][A-Z0-9_]*)\s*:\s*([^=\n]+?)\s*=[^\n#]*(?:#\s*(.*))?$", body, re.M)]


def section(markdown: str, number: int) -> str:
    """The text of `## <number>.` in a document, without its heading."""
    m = re.search(rf"^## {number}\.[^\n]*\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    return m.group(1).strip() if m else ""


def _api_tags() -> tuple[int, int, list[list]]:
    import logging

    logging.disable(logging.CRITICAL)
    try:
        from api.main import app
        spec = app.openapi()
    finally:
        logging.disable(logging.NOTSET)
    ops = [o for v in spec["paths"].values() for o in v.values()]
    tags = Counter(" · ".join(o.get("tags") or ["(no tag)"]) for o in ops)
    return len(spec["paths"]), len(ops), [[t, n] for t, n in sorted(tags.items(), key=lambda x: (-x[1], x[0]))]


def _beat() -> list[list[str]]:
    from services.tasks.celery_app import celery_app
    rows = []
    for name, e in sorted(celery_app.conf.beat_schedule.items()):
        s = e["schedule"]
        when = (f"every {s:g} s" if isinstance(s, (int, float)) else
                "cron `" + " ".join(str(getattr(s, f"_orig_{k}")) for k in
                                    ("minute", "hour", "day_of_month", "month_of_year", "day_of_week")) + "`")
        rows.append([f"`{name}`", f"`{e['task']}`", when])
    return rows


def render(migrations: dict) -> str:
    pyproject = read("pyproject.toml")
    project = tomllib.loads(pyproject)["project"]
    package = json.loads(read("web/package.json"))
    lock = json.loads(read("web/package-lock.json"))
    ci = _yaml(".github/workflows/ci.yml")[0]
    dockerfile = read("infra/docker/Dockerfile")
    stages = re.findall(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?", dockerfile, re.M)
    paths, n_ops, tags = _api_tags()
    sd = (ROOT / "docs" / SD).read_text(encoding="utf-8")
    slo = _yaml("docs/observability/slo.yaml")[0]
    slo_head = [x.lstrip("# ").rstrip() for x in read("docs/observability/slo.yaml").split("\n\n")[0].splitlines()
                if x.startswith("#")]
    lock_ts = lock.get("packages", {}).get("node_modules/typescript", {}).get("version", "?")

    out = ["# Technical requirements — Tellumen climate platform (as built)", "",
           banner("`pyproject.toml`, `web/package.json` and its lock file, `.github/workflows/ci.yml`, "
                  "`scripts/precommit.sh`, `infra/`, `docker-compose.yml`, `core/config.py`, the API's OpenAPI schema "
                  "and the Celery beat schedule"), "",
           "What the platform runs on and how it is built, tested and deployed. The architecture, data, security, "
           "deployment and interface prose is in [SOFTWARE_DESCRIPTION.md](SOFTWARE_DESCRIPTION.md) §3 and §5–§9 and "
           "is linked here, not repeated. The database schema is [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md); the screens "
           "and routes are [APP_FLOW.md](APP_FLOW.md).", ""]

    py_ci = ci["env"]["PYTHON_VERSION"]
    node_ci = next(s["with"]["node-version"] for s in ci["jobs"]["web"]["steps"] if "setup-node" in s.get("uses", ""))
    pg_ci = ci["jobs"]["integration-tests"]["services"]["db"]["image"]
    compose = _yaml("docker-compose.yml")[0]["services"]
    out += ["## 1. Runtime", "", table(["Component", "Version", "Where it is stated"], [
        ["Package", f"`{project['name']}` {project['version']}", "`pyproject.toml` [project]"],
        ["Python", f"`{project['requires-python']}`", "`pyproject.toml` requires-python"],
        ["Python (CI)", f"`{py_ci}`", "`.github/workflows/ci.yml` env.PYTHON_VERSION"],
        ["Python (container)", f"`{stages[0][0]}`", "`infra/docker/Dockerfile` first stage"],
        ["Node.js (CI)", f"`{node_ci}`", "`.github/workflows/ci.yml` job web"],
        ["TypeScript", f"`{package['devDependencies']['typescript']}` → {lock_ts}", "`web/package.json` / lock file"],
        ["PostgreSQL (CI)", f"`{pg_ci}`", "`.github/workflows/ci.yml` integration-tests service"],
        ["PostgreSQL (local stack)", f"`{compose['db']['image']}`", "`docker-compose.yml` service db"],
        ["Database migrations", f"{migrations['revisions']} revisions, head "
                                + ", ".join(f"`{h}`" for h in migrations["heads"]), "`core/db/migrations/versions/`"],
    ]), ""]

    deps = python_dependencies(pyproject)
    out += ["## 2. Backend dependencies (Python)", "",
            "Declared in `pyproject.toml` — the one dependency list (`tests/unit/test_environment_matches_requirements.py` "
            "checks the environment against it). `core` is installed always; the others are extras "
            "(`pip install -e \".[all,dev]\"` in CI). *Note* is the comment beside or above the line in the file.", ""]
    for group in dict.fromkeys(g for g, _, _ in deps):
        out += [f"### `{group}`", "", table(["Requirement", "Note"], [[f"`{r}`", n] for g, r, n in deps if g == group]), ""]

    out += ["## 3. Web dependencies", "",
            "Declared in `web/package.json`; *Resolved* is the version `web/package-lock.json` pins.", "",
            table(["Package", "Declared", "Resolved", "Used for"], web_dependencies(package, lock)), "",
            "Scripts: " + ", ".join(f"`npm run {k}` → `{v}`" for k, v in package["scripts"].items()) + ".", ""]

    out += ["## 4. Services and processes", "",
            "### API", "",
            f"FastAPI application `api/main.py`. Its OpenAPI schema (`app.openapi()`) lists **{n_ops} operations on "
            f"{paths} paths**; routes registered with `include_in_schema=False` (such as `/metrics`) are not counted. "
            "Operations per tag:", "", table(["Tag", "Operations"], tags), "",
            "### Database", "",
            "PostgreSQL through SQLAlchemy 2 and psycopg 3 (`postgresql+psycopg://`, setting `DATABASE_URL`). The schema "
            "is built only by the Alembic migrations — see [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md).", "",
            "### Background workers", "",
            "Celery application `services/tasks/celery_app.py`, broker and result backend from setting `REDIS_URL`. "
            "Periodic tasks (`celery_app.conf.beat_schedule`):", "",
            table(["Entry", "Task", "Schedule"], _beat()), "",
            "### Web application", "",
            "React single-page application built with Vite (`web/`); routes, navigation and role gating are in "
            "[APP_FLOW.md](APP_FLOW.md), the visual system in [DESIGN_BRIEF.md](DESIGN_BRIEF.md).", ""]

    out += ["## 5. Configuration", "",
            "Fields of `Settings` in `core/config.py` (read from the environment / `.env`). Values are not reproduced.",
            "", table(["Setting", "Type", "Note"], settings_fields(read("core/config.py"))), ""]

    jobs = []
    for key, job in ci["jobs"].items():
        steps = [s.get("name") or s.get("uses", "") for s in job.get("steps", [])]
        needs = job.get("needs", [])
        jobs.append([f"`{key}` ({job.get('name', '')})", ", ".join(needs if isinstance(needs, list) else [needs]),
                     f"`{job['if']}`" if "if" in job else "every run", " → ".join(steps)])
    triggers = ci.get("on", ci.get(True, {}))
    out += ["## 6. Build and quality gate", "",
            "### Before every commit: `scripts/precommit.sh`", "",
            "Runs in order and stops at the first failure ([ENGINEERING_PROCESS.md §2](ENGINEERING_PROCESS.md)):", ""]
    out += [f"{k}. {s}" for k, s in enumerate(gate_steps(read("scripts/precommit.sh")), 1)]
    out += ["", "### Continuous integration: `.github/workflows/ci.yml`", "",
            "Runs on " + "; ".join(f"{ev} to {', '.join(v.get('branches', []))}" for ev, v in triggers.items()) + ".",
            "", table(["Job", "Needs", "Runs when", "Steps"], jobs), ""]

    k8s = []
    for path in sorted((ROOT / "infra" / "k8s").glob("*.yaml")):
        for d in _yaml(str(path.relative_to(ROOT))):
            sched = d.get("spec", {}).get("schedule", "") if d.get("kind") == "CronJob" else ""
            k8s.append([f"`infra/k8s/{path.name}`", d.get("kind", ""), d.get("metadata", {}).get("name", ""),
                        f"`{sched}`" if sched else ""])
    compose_rows = [[f"`{f}`", s, f"`{v.get('image', '')}`", ", ".join(map(str, v.get("ports", [])))]
                    for f in ("docker-compose.yml", "infra/docker/docker-compose.prod.yml")
                    for s, v in _yaml(f)[0]["services"].items()]
    out += ["## 7. Deployment artefacts", "",
            "How these fit together: [SOFTWARE_DESCRIPTION.md §7](SOFTWARE_DESCRIPTION.md#7-deployment--infrastructure).",
            "", "Container build stages (`infra/docker/Dockerfile`):", "",
            table(["Stage", "Built from"], [[f"`{name or '(unnamed)'}`", f"`{base}`"] for base, name in stages]), "",
            "Compose services:", "", table(["File", "Service", "Image", "Ports"], compose_rows), "",
            "Kubernetes manifests (`infra/k8s/`; applied by the CI deploy job only when a cluster is configured):", "",
            table(["File", "Kind", "Name", "Schedule"], k8s), ""]

    slo_rows = [[f"SLO `{s['name']}`", ", ".join(f"{k} {v}" for k, v in s.items() if k not in ("name", "description",
                                                                                             "sli"))]
                for s in slo.get("slos", []) if isinstance(s, dict)]
    for k, v in (slo.get("latency_targets") or {}).items():
        slo_rows.append([f"latency `{k}`", ", ".join(f"{a} {b}" for a, b in v.items()) if isinstance(v, dict) else v])
    for k, v in (slo.get("recovery") or {}).items():
        slo_rows.append([f"recovery `{k}`", v])
    nf = section(sd, 9)
    out += ["## 8. Security, observability and non-functional requirements", "",
            "- Security, multi-tenancy and access control: "
            "[SOFTWARE_DESCRIPTION.md §6](SOFTWARE_DESCRIPTION.md#6-security-multi-tenancy--access-control).",
            "- External interfaces and export formats: [SOFTWARE_DESCRIPTION.md §8](SOFTWARE_DESCRIPTION.md#8-external-interfaces).",
            "- Observability: `docs/observability/` — `RUNBOOK.md`, `CAPACITY.md` and `slo.yaml`.", "",
            "The service-level targets `docs/observability/slo.yaml` holds. Its header says what they are:", "",
            "> " + " ".join(slo_head), "", table(["Target", "Value"], slo_rows), "",
            "Non-functional characteristics as [SOFTWARE_DESCRIPTION.md §9](SOFTWARE_DESCRIPTION.md#9-non-functional-characteristics) "
            "states them (quoted):", ""]
    out += ["> " + line if line else ">" for line in nf.splitlines()]
    return "\n".join(out).rstrip() + "\n"
