# Engineering process — regulatory change and error prevention

Regulation changes constantly. This is the one route every change takes, and the log that turns every error into an
automatic guard. Improve both over time: each run of the route should be faster than the last, and no error should be
possible twice.

## 1. The regulatory-change route

| Step | What happens | Where |
|---|---|---|
| 1 Detect | CRCS finds the change: the EU register daily (dates, amending and replacing acts), and earlier, the regulators' own feeds and the press (unconfirmed signals). | `services/regulatory_monitoring/eurlex_detector.py`, `early_signals.py` |
| 2 Triage (≤ 1 day) | A person classifies the detected change: no impact · wording only · template change · new module. The decision is recorded on the change. | `reg_detected_change` |
| 3 Capture as a specification | Each version of a regulation's templates is a **versioned spec file**: templates, rows, columns, the instruction reference and a verbatim quote per element, the act (CELEX), its status (adopted / draft) and the dates it applies. Drafted from the official text by an agent, verified by a second pass. | `data/reference/regspec/<framework>/<version>.json` |
| 4 Diff | The machine compares the new spec with the one in force and lists what changed: templates, rows, columns added / removed / renamed, references moved. Unchanged cells carry over. | `services/regspec` |
| 5 Implement the diff only | Every cell of a spec says where its value comes from: computed (a named engine datapoint), client input, or not applicable. Titles and labels are read from the spec, never typed in code. | spec `source` field |
| 6 Automatic checks | Coverage: every spec cell is mapped or explicitly marked. A golden test book gives known answers per version. Old and new versions run side by side; version pinning decides which one a filing period uses. | `tests/…/test_regspec_*.py` |
| 7 Sign-off and release | A regulatory reviewer and an engineer approve the spec (four eyes); only an approved, adopted spec can govern a filing. Clients are told through the CRCS alerts. | approval type `regspec.approve` |
| 8 Retire | The previous version stays supported for restatements for six months after it stops applying, then is retired. | `reg_versions.LEGACY_SUPPORT_DAYS` |

A draft act (e.g. an EBA final draft ITS not yet adopted by the Commission) may be captured as a spec with status
`draft`: it is diffed and prepared, never used for a filing until adopted.

## 2. Before every commit — one command

```
scripts/precommit.sh
```

It runs, in order, and stops at the first failure: lint on the changed Python files · the migration graph check · the
web build · the full test suite (which ends with the demo-data guard) · the running-code check. Nothing is committed
until it passes.

## 3. Error log

Every error — found by a test, a review, a user or ourselves — gets a line here: what happened, the root cause, the fix,
and the **automatic guard** that makes it impossible (or at least loud) next time. A fix without a guard is not done.

| # | Date | What happened | Root cause | Automatic guard |
|---|---|---|---|---|
| E1 | 2026-09-28 | A "rolled-back" test renamed four demo sites for real. | The code under test called `session.commit()`; the test fixture only rolled back at the end. | `session_rolled_back` makes every commit a flush (`tests/integration/conftest.py`); `views.in_view` restores any override it replaces. |
| E2 | 2026-09-28 | Tests left 202 rows in an append-only table. | Committed tests cleaned their assets but not the new fact history. | Suite-wide demo-data guard: fingerprints the business tables and append-only counts before and after the run; any change fails the run and names the table (`tests/conftest.py`). |
| E3 | 2026-09-28 | A new module overwrote an unrelated existing file of the same name. | A file was written without checking the path was free. | Every module is imported by a test (`tests/unit/test_every_module_imports.py`); plus: check a path is free before creating a file. |
| E4 | 2026-09-28 | A live check ran against an API still serving the previous code. | The server was not restarted after a backend change. | `/health` reports the code version loaded; `scripts/check_running_code.sh` fails when it differs from the checkout. |
| E5 | 2026-09-28 | Security headers and metrics were silently off. | They sat in one try-block with a package that pyproject.toml never declared; a second, stale requirements file drifted. | Security headers always on (`api/security_headers.py`) and tested; one dependency list (pyproject.toml) checked against the environment (`tests/unit/test_environment_matches_requirements.py`); a missing optional package now logs a warning. |
| E6 | 2026-09-28 | Two helper agents were launched with unfilled placeholders in their instructions. | A prompt was written as a template and not completed. | Write every agent instruction in full — never with placeholders. |
| E7 | 2026-09-28 | Pillar 3 filings were prepared under an act the register shows replaced. | Template structure and its legal citation were typed into code; nothing compared them with the register. | Version pinning stamps and checks the act on every freeze; the regulatory-change route (spec files, diff, coverage) replaces hand-typed templates. |
| E8 | 2026-09-28 | A task-approval test left an approved request (and a finished task) behind on every run — 60 by the time the E2 guard caught it on its first run. | The test relied on a final rollback while the approval step inside it commits; its HTTP part cleaned the task but not the request. | The module's session makes commits flushes; the HTTP test deletes its own request; the E2 guard fails any recurrence. |
