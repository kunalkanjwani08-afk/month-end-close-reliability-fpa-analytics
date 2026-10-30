# V2 Test Environment Report

Run on 2026-10-30. All commands were run against the V2 folder only.

## Environment

| Item | Value |
|---|---|
| OS | Ubuntu 24.04.5 LTS, Linux 6.18 (container) |
| Python | 3.13.16 (fresh virtual environment, created for this run) |
| Install command | `pip install -r requirements.txt` (pinned; wheels pre-downloaded) |
| `pip check` | `No broken requirements found.` |
| LibreOffice (manual demo recalculation only) | 24.2.7.2 |
| Node (syntax checks) | v22.22.0 |

Installed packages (`pip freeze`): duckdb 2.0.0, et_xmlfile 2.0.0, iniconfig 2.3.1, numpy 2.4.6, openpyxl 3.1.5, packaging 26.3, pandas 3.0.5, pluggy 1.7.0, Pygments 2.21.0, pytest 9.2.0, python-dateutil 3.0.0, six 1.17.0, tzdata 2026.6, XlsxWriter 3.2.9.

## Exact test command and output

```
python -m pytest -q -p no:cacheprovider tests
........................................................................ [ 97%]
..                                                                       [100%]
============= TEST RESULT (PASS / FAIL / SKIP reported separately) =============
PASS: 74    FAIL: 0    SKIP: 0 (of which full-data tests skipped: 0)
74 passed in 2.99s
```

## Other checks actually run

| Check | Result |
|---|---|
| `py_compile` on all Python files | OK |
| `node --check` on `phase6_core.js`, `phase6_views.js` | OK |
| SQL smoke test: build the schema-only database from a header-only file and a dummy config, run all 12 SQL scripts through `run_sql_files` | All 12 scripts executed (parse and bind). The database had **zero rows**, so **no query result and no validation outcome was verified** |
| Demo workbook recalculated in LibreOffice (earlier in the session, on unchanged code) | Check cells evaluated TRUE after forced recalculation; not repeated after the final doc edits because the code is unchanged |
| Markdown link and anchor check | 0 broken |
| `git add -n` in a scratch copy (no commit) | Private config, CSV, XLSX, DuckDB, `.env`, `outputs/` ignored; template and sources included |

## What the tests are

A **fixture and unit test suite** on invented values. It is not end-to-end validation, does not read the dataset, and does not validate any financial result. The 74 tests cover the private-config loader, pipeline helpers and gates, the generic cleaning toolkit and the synthetic Excel demo.

## Compatibility limits (not tested)

Windows; macOS; Python versions other than 3.13.16; other package versions (the pins were taken from the project, one Phase 7 environment used a different numpy build than the pin); native Microsoft Excel; browsers (the dashboard JS was syntax-checked only in this phase); the data-dependent pipeline stages; the dashboard builder.
