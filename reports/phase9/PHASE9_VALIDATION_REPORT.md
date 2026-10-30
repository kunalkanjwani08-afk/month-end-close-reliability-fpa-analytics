# Phase 9 validation report (30 Oct 2026)

Everything in section 1 was **run during this publication step**. Section 2 is **historical** (earlier phases) and was not re-run. Section 3 lists what was **not** done.

Environment: Linux (cloud sandbox), Python 3.13.16, fresh virtual environment created from `requirements.txt`, Chromium 141 via Playwright 1.56.0, headless LibreOffice 24.2. Raw logs: [`test_logs/`](test_logs/).

## 1. Run now

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Source selection: working-copy files compared by SHA-256 with the master-archive manifest (raw CSV, cleaned CSV, cleaner) and with the standalone copies in Downloads (Phase 5 workbook, dashboard HTML, Phase 7 report) | all identical; the Downloads `DASHBOARD_QA_REPORT.md` is an older version and was not used | `EXCLUDED_FILES_AND_REASONS.md` |
| 2 | Lossless compression: `gzip -9 -n`, then decompress and compare | raw `a0e6edde…` and cleaned `c184b677…` identical; 152,683 lines each; `gzip -t` OK | this section |
| 3 | Documented Python decompress one-liner on a clean temp copy | both SHA-256 values reproduced | this section |
| 4 | `pip install -r requirements.txt`; `pip check` | exit 0; no broken requirements | `test_logs/01`, `02` |
| 5 | `python -m compileall src tests sql` | exit 0 | `test_logs/03` |
| 6 | Phase 4 fixture tests | 42 passed | `test_logs/04` |
| 7 | Phase 4 pipeline on the real data (executes and validates all 12 SQL scripts) | exit 0, 19 s; 72 tables; validation 55+24+86+124 passed | `test_logs/05` |
| 8 | Rebuilt `outputs/phase4/` compared byte for byte with the published copy; regenerated Phase 4 report and insight register | 73 files identical; both documents identical | this section |
| 9 | Phase 4 tests with the full data | 74 passed, 0 failed, 0 skipped (incl. the 42 fixture tests) | `test_logs/06` |
| 10 | Phase 5 workbook rebuild and tests | 3,819 formulas; 137/137 reconciliation PASS; 51 tests passed | `test_logs/07`, `08` |
| 11 | Published Phase 5 workbook recalculated independently in headless LibreOffice | 137 PASS, 0 FAIL on *Reconciliation & QA*; 0 Excel error values (`#REF!`, `#DIV/0!`, `#N/A`, `#VALUE!`, `#NAME?`, `#NUM!`) in any cell | this section |
| 12 | All four published workbooks opened with openpyxl | 12 / 9 / 6 / 2 sheets; 3,819 / 240 / 1,268 / 0 formulas | this section |
| 13 | Dashboard browser QA suite (`tests/phase6_dashboard_qa.py`) in headless Chromium against the published HTML | **297 PASS, 0 FAIL, 1 SKIP** (screen-reader test impossible here); includes load, tab switching, filters, scenarios, cross-filtering, CSV export, themes, 390/768/1024 px widths, print, no console errors | `test_logs/10` |
| 14 | Secret scan (tokens, keys, `password=`, private keys) over all text files | 0 hits | this section |
| 15 | Email, phone, URL scan of the raw and cleaned data (all 152,682 rows, fields `line_text`, `notes`, `cost_center_owner`, `user_id`) | 0 hits; 8 person-like owner names and 8 generic user IDs present | this section |
| 16 | Local-path scan (Windows paths, `/home/<user>`, the owner's name) | 0 hits; sandbox paths (`/tmp/...`) exist only in QC and Phase 7 log files | this section |
| 17 | Prohibited-file scan: caches, `.pkl`, `.duckdb`, archives, `.env`, backups, `LICENSE`/`COPYING` | none present in the staging set (only `.gitignore` is a dotfile) | this section |
| 18 | Largest published file | 28.5 MB (GitHub limit: 100 MB) | inventory |
| 19 | Relative-link check over all Markdown files | 236 links; 12 broken links found and fixed (see edit register); re-checked after fixes | `DOCUMENT_EDIT_REGISTER.csv` |
| 20 | Manifest check: every published file listed exactly once; hashes recalculated | see `PUBLICATION_MANIFEST_SHA256.txt` and `sha256sum -c` result in the final report | manifest |

## 2. Historical, not re-run

* Phase 7: 780 checks executed (774 PASS, 1 FAIL, 1 BLOCKED, 4 NOT TESTED, 43 INFO) by an independent pandas reference; 18 issues logged. See `outputs/phase7/PHASE7_QA_REPORT.md`.
* Phase 3 cleaner self-checks (43 in memory, 27 read-back) and the Phase 7 byte-for-byte reproduction of the cleaned CSV.
* Phase 6 negative controls (6 of 6 re-introduced defects detected) and Phase 6 print-preview checks.
* Phase 5 and Phase 6 QA reports as written at the time.

## 3. Not performed

* `src/clean_fpa_monthly_close.py` was **not re-run** in this step (about 5 minutes, 174 MB output); the published cleaned file is the approved one, hash-matched to the master-archive manifest. Its re-run was verified in Phase 7.
* `tests/phase6_negative_controls.py` and the Phase 7 QA scripts were not re-run.
* Windows, macOS, other Python versions, native Microsoft Excel, Firefox, Safari, screen readers, physical printer.
* The documented clean-environment setup was exercised on Linux only; the Windows command lines in `HOW_TO_RUN.txt` were not executed.
* An independent human review. All scans are pattern-based and cannot prove the absence of every sensitive item.
* No hosted dashboard exists or was created.
