# Phase 7 - End-to-end QA, independent financial validation and project audit

Project: Month-End Close Reliability & Financial Performance Analytics (NovaBridge, synthetic extract, Jan 2023 - Dec 2025).  
Report generated 2026-10-30T11:58:35 from `outputs/phase7/qa_results.json` by `tests/phase7/p7_report_md.py`. Every count below is computed from the check registry.

## 1. Executive summary

- **Checks executed: 780** - **774 PASS, 1 FAIL, 1 BLOCKED, 4 NOT TESTED** (plus 43 INFO observations that are not tests).
- **The 16,352-row difference is fully explained by the data.** Every one of those rows fails a documented non-status gate (non-posting row, junk or unresolvable entity, Balance Sheet, missing actual, undetermined scale). 4,996 of them are non-Posted lines that would otherwise belong to the status diagnostic: 4,958 have no actual amount and 38 have an undetermined scale. 0 rows are unexplained (check P05).
- **No critical or high-severity issue was found.** The independent pandas reference reproduced the SQL outputs, the Excel workbook and the dashboard on identical populations: every table row within one cent, every ratio within 1e-9. The dashboard was tested in 17 filter/scenario states, including the CSV export of every filtered line.
- **The single FAIL** (`PR.03.detail`) is the evidence for ISS-02 under the ORIGINAL instructions: 123 PASS / 2 FAIL. After the correction the same sequence passes (checks RG.*).
- **Two medium reproducibility defects (ISS-01, ISS-02) were found in the run instructions and corrected in `HOW_TO_RUN.txt`**, then regression-tested in a fresh copy. No data, calculation, workbook or dashboard was changed.
- **Publication is blocked by an owner decision, not by a defect.** Provenance and the redistribution licence of the data are unverified (ISS-06), and two QC files record build-machine paths (ISS-03).
- **Release recommendation: QA sign-off for the documentation stage. Not ready for public publication** until ISS-06 and ISS-03 are resolved and the Windows run (ISS-05) is done.

## 2. Scope and files tested

Authoritative inputs (cloud working copy; each hash was verified against the approved master zip `NovaBridge_FPA_All_Phases_1-6_Master.zip` built on 30 Oct 2026):

| Role | Path | Bytes | SHA-256 |
|---|---|---:|---|
| raw CSV | `data/raw/fpa_monthly_close_raw_messy.csv` | 51,938,535 | `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff` |
| cleaned CSV (canonical) | `data/processed/fpa_monthly_close_cleaned.csv` | 174,545,248 | `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47` |
| DuckDB | `data/processed/phase4_fpa.duckdb` | 86,257,664 | `00e7437697c8e11baab5d2cff7036d6dda3d251a139774adee0a2dfe92c413e6` |
| Phase 5 workbook | `outputs/phase5/fpa_month_end_close_analysis.xlsx` | 272,343 | `71e23dca9e0bbce3295223188c296cd3bd5ff51759825487bae049705375f561` |
| Phase 6 dashboard | `outputs/phase6/fpa_financial_analytics_dashboard.html` | 7,317,802 | `43d2505abe218ca56fdab57fcf64722e1f6f10ccdf3263b89c4f8691d584efc0` |
| Phase 2 review workbook (owner's Downloads / master zip) | `fpa_monthly_close_cleaned.xlsx` | 67,381,749 | `270edc6b33ae74c46513b4529f6a6e314854c28a898c81f0877c0ac311bb3db6` |

Version decisions (no silent choice):

- **Raw CSV:** `a0e6edde...` (51,938,535 bytes) is authoritative. It is the hash given in the original cleaning brief and is enforced by the cleaner's integrity gate. A different file with the same name in the owner's Downloads folder (`845b78d8...`, 51,675,512 bytes) has the same 152,682 rows but different formatting in 149,469 rows. It was not used (ISS-17).
- **Phase 4 code and documents:** the Phase 5 package superseded `src/phase4_report.py` (76,306 -> 81,827 bytes), `PHASE4_ANALYSIS_REPORT.md` and `PHASE4_INSIGHT_REGISTER.md`. The later versions are authoritative. The isolated re-run regenerated both documents byte-identically.
- **Workbooks:** the Phase 2 *review workbook* `fpa_monthly_close_cleaned.xlsx` (sheet Cleaned_Data, 77 fields) is a different file from the *Phase 5 analysis workbook* `fpa_month_end_close_analysis.xlsx` (12 sheets) and from the 192-column canonical CSV. All three were tested separately (checks PY08-PY10, X*).
- **Excluded as non-authoritative:** the old v1 project folder and the older `fpa_monthly_close_cleaned` folder in Downloads (unapproved INCOMPLETE/test debris), and the stale loose `DASHBOARD_QA_REPORT.md`.
- A full SHA-256 list of every project file is in `file_manifest_sha256.txt`. A pre-QA snapshot is in `evidence/sha256_before_phase7.txt`; every file in it still matches except `HOW_TO_RUN.txt` (ISS-01/02 correction).

## 3. Methodology

1. **Independent reference.** `tests/phase7/` does not import any project module. It re-parses the raw amount strings with its own parser and re-derives statement, status, entity and exclusion reasons from raw values with explicit mappings. It then rebuilds every metric in pandas.
2. **Same population, same definition.** Each comparison states its population and definition. Definitions come from `docs/FINANCIAL_METRICS.md` and the SQL comments. Values on different populations are never called reconciled.
3. **Tolerances.** Counts are exact. Money is 0.01 USD: inputs have at most 4 decimals and float64 summation error on about 60k terms is around 1e-7 USD, so a cent is far above noise and far below any reportable amount. Ratios are 1e-9. Dashboard display values use their display precision ($0.005M on '$xx.xxM' cards, $0.5 on whole-dollar lines).
4. **Negative controls.** The financial comparison was re-run three times with a deliberately corrupted reference: one Posted line dropped, one line off by 2 cents, and one Pending line added to the Posted population. Each produced FAILs (checks NC.*), so the comparisons can detect population and one-cent errors.
5. **Isolation.** Pipeline, report, workbook and dashboard builds and the existing test suites were re-run only in copies of the repository under the scratch area. The approved outputs were never overwritten. Excel recalculation used a copy of the workbook.
6. **Test-harness corrections (disclosed).** Five first-run FAILs were defects in my own QA code, not in the project:
   - The chart-reference parser did not unescape `&amp;`.
   - The entity-table row finder also picked up rows from other tables.
   - Three disclosure regular expressions were too narrow.
   - One duplicate check used the wrong flag column.
   - The dashboard script clicked a Reset button that is correctly disabled at the default state.
   Each was fixed in the QA code and re-run. The reported counts are from the final runs.

## 4. Data lineage and record-count reconciliation

| Step | Stage | Records | How identified |
|---|---|---:|---|
| W00 | Raw records | 152,682 | len(raw) |
| W01 | Cleaned records (1:1 with raw, no row dropped) | 152,682 | L08/L09 |
| W11 | less 1_NON_POSTING_ROW | -350 | excl_PL_actual == '1_NON_POSTING_ROW' (independently re-derived, L47) |
| W12 | less 2_JUNK_ENTITY | -204 | excl_PL_actual == '2_JUNK_ENTITY' (independently re-derived, L47) |
| W13 | less 3_ENTITY_UNRESOLVABLE | -16 | excl_PL_actual == '3_ENTITY_UNRESOLVABLE' (independently re-derived, L47) |
| W14 | less 4_OUT_OF_SCOPE_STATEMENT | -7,125 | excl_PL_actual == '4_OUT_OF_SCOPE_STATEMENT' (independently re-derived, L47) |
| W15 | less 5_STATUS_NOT_ELIGIBLE | -82,986 | excl_PL_actual == '5_STATUS_NOT_ELIGIBLE' (independently re-derived, L47) |
| W16 | less 6_PERIOD_UNRESOLVABLE | 0 | excl_PL_actual == '6_PERIOD_UNRESOLVABLE' (independently re-derived, L47) |
| W17 | less 7_AMOUNT_MISSING | -3,637 | excl_PL_actual == '7_AMOUNT_MISSING' (independently re-derived, L47) |
| W18 | less 8_SCALE_UNDECIDABLE | -24 | excl_PL_actual == '8_SCALE_UNDECIDABLE' (independently re-derived, L47) |
| W20 | = Posted eligible P&L lines (dashboard main payload, SQL v_pl_actual) | 58,340 | eligible_PL_actual = 1 |
| W30 | Step-5 (status) exclusions | 82,986 | excl_PL_actual == 5 |
| W31 |   of which also pass steps 6-8 -> non-Posted diagnostic payload | 77,990 | v_pl_actual_any_status, status <> Posted |
| W32 |   of which fail step 7 (actual missing) as well -> in NO payload | 4,958 | status excl. AND actual missing |
| W33 |   of which fail step 8 (scale undetermined) only -> in NO payload | 38 |  |
| W40 | Combined Phase 6 payload | 136,330 | P03 |
| W41 | Not in any Phase 6 payload | 16,352 | P04 / gap_16352_breakdown.csv |
| W50 | P&L variance population (actual AND budget present) | 55,043 | eligible_PL_variance = 1 |
| W60 | Balance Sheet actual population (separate, never added to P&L) | 2,953 | eligible_BS_actual = 1 |
| W70 | P&L vs forecast population (eligible AND forecast present) | 54,851 | v_pl_forecast |
| W71 | P&L vs prior-year population (eligible AND PY present) | 54,923 | v_pl_prior |

**The 16,352 gap** (rows in neither Phase 6 population; first failing gate with the status gate ignored):

| Reason | Posted | non-Posted | All |
|---|---:|---:|---:|
| 1_NON_POSTING_ROW | 147 | 203 | 350 |
| 2_JUNK_ENTITY | 90 | 114 | 204 |
| 3_ENTITY_UNRESOLVABLE | 7 | 9 | 16 |
| 4_OUT_OF_SCOPE_STATEMENT (Balance Sheet) | 3,136 | 3,989 | 7,125 |
| 7_AMOUNT_MISSING (actual) | 3,637 | 4,958 | 8,595 |
| 8_SCALE_UNDECIDABLE | 24 | 38 | 62 |
| All | 7,041 | 9,311 | 16,352 |

Arithmetic: 152,682 - 58,340 Posted eligible - 77,990 non-Posted diagnostic = 16,352. The documented diagnostic population (`v_pl_actual_any_status`) applies gates 1-4 and 6-8 and drops only gate 5. So a non-Posted line that also lacks an actual amount (4,958) or has an undetermined scale (38) is in neither population: 82,986 status exclusions - 77,990 = 4,996. This is intended by the documented definition, but the dashboard does not show those 4,996 lines anywhere (see section 10).

Record-level results (all PASS unless listed in section 10):
- 152,682 raw = 152,682 cleaned. The row_id sets are identical, row order is preserved, and there are no exact duplicate raw rows.
- All 19 raw-value columns are preserved byte for byte in the cleaned file.
- The independent parser agrees with the cleaner on presence and value for all five amount columns.
- The eligibility reason was re-derived for every row in three scopes and matches `excl_PL_actual`, `excl_PL_variance` and `excl_BS_actual` row by row.
- The dashboard's embedded row sets equal the independent Posted (58,340) and non-Posted (77,990) sets exactly, with amounts within 1.5e-11 USD.
- Restored rows: 6,265 overall (1,814 HIGH, 4,451 MEDIUM); 73 undetermined; 2,374 in the Posted population; 3,220 in the non-Posted population. All match the reported figures. Sign-conflict duplicate candidates: 1,587, none deleted.
- Phase 2 review workbook vs canonical CSV: all 152,682 rows x 77 shared fields equal (0 mismatches after reading Excel date cells as calendar dates).

## 5. Independent financial calculation results

Headline from the independent reference (Posted eligible, scale-adjusted, signs as recorded, USD): revenue **202,649,002.15**, cost base (COGS+People+Opex) **176,329,755.99**, result proxy (not EBITDA) **26,319,246.16** on **58,340** lines.

| Comparison | What was compared | Result |
|---|---|---|
| SQL `F_A1` | P&L by month x section (252 rows) | 5/5 PASS |
| SQL `F_A2` | entity x section | 5/5 PASS |
| SQL `F_A3` | division x section | 5/5 PASS |
| SQL `F_A4` | GL account (24) | 6/6 PASS |
| SQL `F_B1` | budget variance, 4 sign populations, incl. guarded % | 9/9 PASS |
| SQL `F_B3` | variance by division | 5/5 PASS |
| SQL `F_C1` | forecast error, WAPE, bias | 9/9 PASS |
| SQL `F_D1` | prior-year column comparison by year | 6/6 PASS |
| SQL `F_E1` | gross profit S1/S2/S3 x 2 row sets x years | 6/6 PASS |
| SQL `F_F1` | cost by GL, Pareto share, rank | 7/7 PASS |
| SQL `F_F2` | concentration top-1/top-3/HHI incl. cost centres | 6/6 PASS |
| SQL `F_I1` | status / scale / duplicate / sign scenarios | 5/5 PASS |
| SQL `F_I5` | scale-restored exposure | 5/5 PASS |
| sql | SQL views read-only: grain, join fan-out, NULLs, populations, section/entity/cost-centre totals, re-run determinism | 33 PASS / 0 FAIL / 0 NOT TESTED (+1 INFO) |
| excel | Phase 5 workbook: formulas, charts, values vs reference | 31 PASS / 0 FAIL / 0 NOT TESTED (+3 INFO) |
| dashboard | Dashboard: 17 states x engine values, DOM, CSV export, status diagnostic, UI behaviour | 471 PASS / 0 FAIL / 3 NOT TESTED (+2 INFO) |

Full metric-by-metric detail (metric, population, definition, expected, actual, absolute and relative difference, tolerance, status, explanation) is in `FINANCIAL_RECONCILIATION.xlsx`. Its Summary sheet counts are live formulas, and a recheck column recomputes |difference| <= tolerance.

## 6. Python, SQL and Excel validation

- **Python cleaning:** re-run on a copy of the raw file. Exit 0; the output CSV is **byte-identical** to the canonical file (SHA-256 c184b677...); the raw copy is unchanged; the cleaner's own 43 + 27 checks show 0 FAILED; 253.7 s with peak RSS about 1.25 GB. The script refuses a raw file with the wrong hash and never overwrites its input. Its review workbook differs only in embedded run metadata.
- **SQL:** 33 read-only checks against the canonical DuckDB file, which is unchanged afterwards. Results:
  - Grain is one row per source row; the dim_account join does not multiply rows.
  - No unmapped sections; Posted-only and P&L-only populations hold; NULL budgets stay out of the variance view.
  - Undetermined scale stays out of the any-status view; Balance Sheet and P&L do not overlap.
  - Section, entity and cost-centre totals match the pandas reference.
  The isolated re-run reproduced all 72 Phase 4 CSVs and both Phase 4 documents byte for byte. The database *file* is not byte-reproducible (ISS-02).
- **Excel (Phase 5):** a copy was recalculated in LibreOffice with these results:
  - 3,819 formulas: 0 errors and 0 differences between stored and recalculated values.
  - No `#REF!`, external links, macros or broken defined names.
  - Chart series all point to populated ranges.
  - Monthly P&L (36 months x 7 measures), Executive Summary headline and variance %, GP1 (24 rows), entity and division tables, GL table and exclusion waterfall all match the independent reference.
  - The workbook has **not** been opened in Microsoft Excel (NOT TESTED).
- **Existing suites** (re-run in the copy, not counted as independent evidence):
  - Phase 4 + Phase 5 pytest gave 123 PASS / 2 FAIL in the documented order (ISS-02), then all Phase 5 tests passed after step 5.
  - Phase 6 QA gave 297 PASS / 0 FAIL / 1 SKIP; its negative controls detected 6/6.

## 7. Dashboard validation

Tested in headless Chromium against the delivered file (`43d2505a...`). Checks:
- **States (17).** Year chips, entity list, scale selector, a chart cross-filter click, and section-only (cost-only, revenue-only), multi-filter, cost-centre, single-GL, quarter + month-range, all scenario combinations, the three variance populations, a near-zero account and an empty selection.
- **Per state.** Line count, revenue, cost, result proxy, 7 section totals, budget variance for 4 sections (lines, actual, budget, net, gross cell variance, guarded %) and the 5-status diagnostic were compared with the independent reference. The CSV export of every filtered line was checked for count, row-set identity and section sums, and the DOM KPI cards for display precision.
- **Behaviour.** Undo, Reset, cross-filter clearing, detail pagination, theme switch, keyboard focus outline, print media (interactive controls hidden, PDF generated) and four widths (no horizontal overflow) were checked.
- **Errors.** There were 0 console errors and 0 non-local requests.
- **Cost-only selection.** Revenue $0 and proxy margin 'n/a'; the observation panel makes no revenue or margin claim.
- **Not tested.** Firefox, Safari, screen readers and physical printing.

## 8. Security and privacy findings

- **No credentials found.** There are no AWS/GitHub/Slack/API-key patterns, private keys or password assignments, no e-mail addresses, and no user-home paths in project text files.
- **Dashboard content.** The dashboard loads no external resources. It embeds line-level data: amounts for 136,330 lines and document numbers for 58,340. It does not embed user_id or cost-centre owner names.
- **Build-machine paths.** `data/processed/QC_Report.txt` and `qc_summary.json` contain machine paths and are not git-ignored (ISS-03).
- **Tracked raw data.** The raw CSV has been tracked by git since Stage 0 and the repository has a GitHub remote. Visibility was not checked. Nothing was committed, pushed or published in Phase 7.
- **Owner decision needed.** The data has person-like cost-centre owner names (e.g. 'K. Iyer') and system user ids. This is fine if the data is synthetic, but provenance is unverified (BLOCKED, ISS-06).

## 9. Reproducibility and performance

Environment used: Python 3.13.16, pandas 3.0.5, numpy 2.5.3 (pinned 2.4.6), duckdb 2.0.0, openpyxl 3.1.5, pytest 9.2.0, Playwright 1.56.0, Chromium 141.0.7390.37, LibreOffice 24.2.7.2 420(Build:2). Linux container; **no clean-machine or Windows run** (ISS-05).

| Step | Command | Exit | Seconds | Peak MB |
|---|---|---:|---:|---:|
| 01_phase4_pipeline | (isolated copy) | 0 | 19.1 | 940.8 |
| 02_phase4_report | (isolated copy) | 0 | 0.4 | 106.0 |
| 03_pytest_phase4_phase5 | (isolated copy) | 1 | 84.9 | 1133.2 |
| 04_phase5_excel | (isolated copy) | 0 | 1.2 | 117.5 |
| 05_pytest_phase5 | (isolated copy) | 0 | 13.5 | 356.4 |
| 06_phase5_qa_report | (isolated copy) | 0 | 19.1 | 353.5 |
| 07_phase6_build | (isolated copy) | 0 | 1.4 | 381.4 |
| 08_phase6_qa | (isolated copy) | 0 | 165.9 | 818.3 |
| 09_phase6_negative_controls | (isolated copy) | 0 | 6.9 | 121.0 |

Cleaner: 253.7 s, about 1.25 GB peak. Dashboard boot in headless Chromium: 0.71 s. The 7.3 MB HTML embeds 7.15 MB of payload.

## 10. Known limitations

- Accepted, disclosed limitations: ISS-06 to ISS-16 in the issue log. Each was checked for consistent implementation and for disclosure in the dashboard, workbook and docs (checks AS01-AS13, all PASS).
- **Hidden population (Low, documentation).** The 4,996 status-excluded lines with no actual amount or with undetermined scale appear in no dashboard view. They are counted in the Phase 4 waterfall and the Data Quality sheet, and this report documents them.
- Selection consistency inside the dashboard was tested in 17 states, not in every possible filter combination.
- NOT TESTED: Microsoft Excel, Firefox/Safari, assistive technology, physical printer, clean-machine install and a Windows run.

## 11. Open issues and severity

| ID | Severity | Status | Issue |
|---|---|---|---|
| ISS-01 | Medium | Corrected (documentation) and regression-tested | Documented command to regenerate the cleaned CSV writes it to the wrong folder |
| ISS-02 | Medium | Corrected (documentation); code unchanged | Following the documented order after a database rebuild produces 2 failing Phase 5 tests |
| ISS-03 | Low | Open - action before publication | QC files record build-machine paths |
| ISS-04 | Low | Open (accepted) | Phase 6 QA suite finds the palette validator through a machine-specific path |
| ISS-05 | Low | Open - NOT TESTED | No clean-machine install was performed; installed numpy differs from the pin |
| ISS-06 | Accepted limitation (publication blocker) | BLOCKED - owner decision | Synthetic status, provenance and redistribution rights of the dataset are unverified |
| ISS-07 | Accepted limitation | Disclosed | Posted-only rule (R6) is provisional; only 58,340 of 152,682 rows (38.2%) are reported |
| ISS-08 | Accepted limitation | Disclosed | Scale restoration (6,265 rows: 1,814 HIGH, 4,451 MEDIUM) is provisional; 73 rows undetermined |
| ISS-09 | Accepted limitation | Disclosed | Account sign convention (R9) unresolved; no favourable/unfavourable labels |
| ISS-10 | Accepted limitation | Disclosed | 2,517 zero FX rates and missing rates unresolved; USD columns used as reported |
| ISS-11 | Accepted limitation | Disclosed | 3,930 duplicate-candidate rows (incl. 1,587 sign-conflict) retained, none deleted |
| ISS-12 | Accepted limitation | Disclosed | Forecast has no version / as-of date: no forecast-skill claim |
| ISS-13 | Accepted limitation | Disclosed | Gross-profit discount treatment unresolved: S1, S2, S3 kept separate |
| ISS-14 | Accepted limitation | Disclosed | Balance-sheet basis not established; DSO, DPO, working capital, close duration not computed |
| ISS-15 | Accepted limitation | Disclosed | NOS vs EA unit equivalence unverified; no unit economics built |
| ISS-16 | Accepted limitation | Evidence supports current reading | About 9,100-9,300 amounts per column look like 'n,nnn' (thousands or 3-decimal comma) |
| ISS-17 | Low | Open - housekeeping | A different file with the raw file's name exists in the owner's Downloads folder |
| ISS-18 | Low | Open - documentation | 4,996 status-excluded lines are in no dashboard view |

Critical: none. High: none.

Checks reported FAIL:
- `PR.03.detail` Documented step 4 (pytest tests) right after a DB rebuild, ORIGINAL instructions (before the ISS-02 correction): PASS/FAIL/SKIP - FAILED: test_lineage_and_source_identity_recorded, test_manifest_matches_the_saved_workbook_and_inputs - DB SHA-256 changed on rebuild (ISS-02)

Checks BLOCKED / NOT TESTED:
- `UI50` (NOT TESTED) Firefox / Safari (WebKit) rendering - only Chromium is installed in this environment
- `UI51` (NOT TESTED) Screen reader / assistive technology - no assistive technology available; ARIA attributes are not a substitute
- `UI52` (NOT TESTED) Physical printer output - print-media emulation and Chromium PDF only
- `ENV.clean_machine` (NOT TESTED) Clean-machine reproduction (fresh OS + pip install -r requirements.txt) - Re-runs used this container's existing Python 3.13.16 / pandas 3.0.5 / numpy 2.5.3 (pinned 2.4.6) / duckdb 2.0.0 / openpyxl 3.1.5 / pytest 9.2.0; no venv install, no Windows run
- `SEC.prov` (BLOCKED) Data provenance and redistribution licence - Owner states the data is synthetic; no licence or provenance document exists to verify it (docs/DATA_PROVENANCE.md). Cannot be resolved by testing.

## 12. Overall release recommendation

- **Financial accuracy, data integrity and traceability:** accepted. Raw -> cleaned -> SQL -> Excel -> dashboard reconcile on identical populations, and the population gap is fully explained.
- **Documentation stage:** ready, with the corrected `HOW_TO_RUN.txt`.
- **Publication:** not ready. First resolve ISS-06 (provenance/licence and repository visibility), clean ISS-03, and complete ISS-05 on the Windows laptop.
- **Headline figures:** all depend on provisional owner rules (R6 status, scale restoration, R9 signs). They must be presented as provisional, as the outputs already do.

Deliverables: `PHASE7_QA_REPORT.md`, `DATA_LINEAGE_RECONCILIATION.xlsx`, `FINANCIAL_RECONCILIATION.xlsx`, `ISSUE_LOG.xlsx`, `qa_results.json`, `file_manifest_sha256.txt`, `test_execution_logs/`, `evidence/`. QA code is in `tests/phase7/`.
