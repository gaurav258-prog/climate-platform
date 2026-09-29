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
| 5 Implement the diff only | The spec is the regulation only. Beside the code that fills it, a binding says how every row and column is filled: computed, input (a named per-loan fact the client supplies) or n/a. Titles, labels and legal citations are read from the spec, never typed in code. | `BINDING` (e.g. `services/governance/pillar3_grids.py`) |
| 6 Automatic checks | Coverage: every row and column of every adopted spec is bound, nothing bound is stale. A golden test book gives known answers under every adopted version (dual run). Each filing freezes the spec it was prepared under (version + file sha256) and is always rendered to it. | `tests/unit/test_regspec.py`, `test_pillar3_grids.py` |
| 7 Sign-off and release | A regulatory reviewer and an engineer — two different people — sign the spec file's exact sha256 (the database refuses the same person twice; editing the file voids earlier sign-offs). A filing built to an unsigned spec carries a warning on its run. Clients are told through the CRCS alerts. | `regspec_signoff`, operator page *Change pipeline* |
| 8 Retire | The previous version stays supported for restatements for six months after it stops applying, then is retired. | `reg_versions.LEGACY_SUPPORT_DAYS` |

A draft act (e.g. an EBA final draft ITS not yet adopted by the Commission) may be captured as a spec with status
`draft`: it is diffed and prepared, never used for a filing until adopted.

Where the official text is silent, the spec records a **declared reading** (`interpretations`: the reading, why, who
declared it) — never an unverified statement presented as the text. An adopted spec may not contain the word
UNVERIFIED (validation refuses it).

### Runs of the route

| Run | Change | What the diff said | What it found | Made faster / safer for next time |
|---|---|---|---|---|
| 1 · 2026-09-28 | Pillar 3 ESG: ITS 2022/2453 → ITS 2024/3172; EBA/ITS/2026/02 captured as draft | 2022 → 2024: references only (no row or column changed). 2024 → draft: template change (T1–T9 replaced by CRFR1–4). | Our Template 5 did not match the text (E9); the 2024 instructions sit in the EBA IT solutions, not the Official Journal — fetched and verified. | Spec capture + independent second pass as two parallel agents; machine diff; coverage and golden book reusable for the draft when adopted. |
| 2 · 2026-09-29 | SFDR PAI statement: RTS 2022/1288 captured (2023/363 confirmed not to touch Annex I); ESAs JC 2023 55 as draft | 2022/1288 → draft: template change — T1 +2 rows, T2 and T3 rows renumbered (read as moves), added and removed | Tables 2 and 3 were never shown on the form (E14); two optional indicators had the wrong metric or wording (E13); GHG emissions showed only its total. Second pass: 4 page-reference slips, fixed. | The diff now recognises renumbered rows (moves), so the next adoption diff reads truly; `_frozen_spec` makes every framework on the route render to the version it was prepared under; undated drafts allowed. Next: pre-contractual / periodic templates (Annexes II–V, replaced by 2023/363). |

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
| E9 | 2026-09-28 | Pillar 3 Template 5 did not match the regulation: "chronic" included exposures sensitive to both; maturity and IFRS 9 columns covered all exposures, not the physical-risk-sensitive ones; rows were the sectors present, not the fixed 13; two impairment columns were missing. | The template was typed from a summary, not built from the instruction text. | The template is built from the verified spec (verbatim instructions); a golden book with hand-worked answers runs under every adopted version; coverage fails the build on any unmapped row or column. |
| E10 | 2026-09-28 | The XBRL element map cited Template 1 "Scope 1" and "Scope 2" columns that the template does not have. | References written from memory. | A test checks every template column the map cites exists in the governing spec. |
| E11 | 2026-09-28 | The pre-commit gate carried on after a lint failure. | `a && b || c` runs `c` when `b` fails. | Written as if / else; the gate stops at the first failure. |
| E12 | 2026-09-28 | A test found a form section by its title and broke when titles began to follow the regulation. | Tests keyed on display text. | Sections carry stable keys; tests find them by key. |
| E13 | 2026-09-29 | Two optional SFDR indicators did not match the regulation: 'non-recycled waste' was a % of total waste (the RTS asks tonnes per € million invested, attributed), and 'threatened species' carried Table 1 no. 7's wording. | A hand-kept catalogue of indicators, named from memory. | The opt-in catalogue is generated from the spec's rows (official number and wording); the aggregation is declared per row in the binding and tested. |
| E14 | 2026-09-29 | The adopted Table 2 / 3 indicators never appeared on the SFDR form. | The form looked up datapoints under keys nothing produced; no test rendered them. | The form emits a datapoint per adopted indicator; a golden-payload test renders them with their official row numbers. |
| E15 | 2026-09-29 | Sign-off tests failed once real sign-offs existed. | The tests signed the real spec files, so they depended on live data state. | They sign a private copy of a spec in a temporary folder; only the freeze and lineage tests read the real specs. |
| E16 | 2026-09-29 | Regulatory lists and citations still typed in code after two runs: NACE groupings in the Pillar 3 bindings, the "high impact climate sectors" set, the EU member list, the collateral fallback, act numbers in the version register, outlook and supervisor profiles, the XBRL fact list twice. | Moving templates onto specs left the surrounding lists and texts where they were. | Groupings are read from the spec layout; regulatory sets and declarations live in cited reference data (`nace_sector_sets.json`, `declarations/`, EU membership from Eurostat GISCO); watched acts and titles come from specs plus `crcs/tracked_acts.json`; draft outlook entries are generated from draft specs and their diff; supervisor citations are read from the framework references; the XBRL map file is the one fact list, enforced by a test. |

