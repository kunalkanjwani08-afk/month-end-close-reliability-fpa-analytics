# Project File Catalog

**Month-End Close Reliability & Financial Performance Analytics**

> **Status (updated at Phase 9 publication, 30 Oct 2026):** published as part of the complete project. The owner decided to publish the whole project, including the dataset he describes as synthetic. Dataset provenance and redistribution rights remain **owner-stated and not independently verified**. Any wording below from Phase 8 that calls the release *blocked*, *draft* or *not approved* describes the Phase 8 state and is superseded by [PUBLICATION_DECISION.md](PUBLICATION_DECISION.md). No calculation, figure or finding was changed.
> **Source of truth:** the Phase 7 SHA-256 manifest, [`outputs/phase7/file_manifest_sha256.txt`](../outputs/phase7/file_manifest_sha256.txt) (220 entries). In Phase 8 every manifest entry that exists in the repository was re-hashed and compared. Results are in section 1.
> **Hashes:** the first 12 hexadecimal characters are shown; full SHA-256 values are in the manifest.
> **Machine paths:** none are quoted here. Paths are repository-relative.

Related: [End-to-end workflow](END_TO_END_WORKFLOW.md) · [Changelog](PROJECT_CHANGELOG.md) · [QA summary](QA_AND_VALIDATION_SUMMARY.md)

---

## 1. How to use this catalogue

**Status values**

| Status | Meaning |
|---|---|
| Authoritative (approved) | The latest approved version of a deliverable, identified by the manifest |
| Current | A current supporting file |
| Historical | A record of an earlier phase or review, kept unchanged; may be outdated in content |
| Evidence | Test output or QA record; not to be edited |
| Placeholder | An empty folder keeper or instruction stub |

**Manifest verification (Phase 8, read-only).**
- Entries in the manifest: 220.
- Entries found in the repository and re-hashed: 219. Hash matches: **216**. Hash differences: **3**.
  - `outputs/phase7/DATA_LINEAGE_RECONCILIATION.xlsx` ‡
  - `outputs/phase7/FINANCIAL_RECONCILIATION.xlsx` ‡
  - `outputs/phase7/ISSUE_LOG.xlsx` ‡
- Entries not present in the repository: 1 (`fpa_monthly_close_cleaned.xlsx`). That file is the Phase 2 review workbook; it is held outside the repository (owner's Downloads and the master archive), so it was not re-hashed.
- Files on disk that are not in the manifest: the manifest itself and the Phase 7 report (hashed after it was written); 30 dashboard screenshots in `outputs/phase6/qa_screens/`; 28 work files under `outputs/phase7/evidence/work/` (including a LibreOffice recalculation copy); a git-ignored `.pytest_cache/` folder (5 files); and everything under `outputs/phase8/` (this documentation package). Nothing else was found. The work files and screenshots are QA evidence and were not modified.

**Marks used below.** ‡ = the file's current SHA-256 differs from the manifest entry. The three Phase 7 workbooks were rewritten about two seconds after the manifest was produced (file times 11:58:38–11:58:41 against 11:58:36), so the manifest holds the pre-rewrite hashes and sizes. The current hashes are shown. This is a Phase 7 housekeeping defect, not a Phase 8 change; the files were not modified in Phase 8 and the manifest was not altered. † = the file is not in the manifest (the Phase 7 report is hashed after it is written, so the manifest cannot contain it).

**Which version to use.** Where two versions of a document exist, the manifest entry is the approved one. Historical documents are not replaced; see section 8.

## 2. Authoritative data and deliverables

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`data/raw/fpa_monthly_close_raw_messy.csv`](../data/raw/fpa_monthly_close_raw_messy.csv.gz) | Raw extract: 152,682 rows × 43 text columns. **Never edited.** Tracked in git; present in the public `main` branch | Authoritative (approved) | 51,938,535 | `a0e6eddde252…` |
| [`data/processed/fpa_monthly_close_cleaned.csv`](../data/processed/fpa_monthly_close_cleaned.csv.gz) | Canonical cleaned file: 152,682 rows × 192 columns | Authoritative (approved) | 174,545,248 | `c184b677bacc…` |
| `data/processed/phase4_fpa.duckdb` | DuckDB database (generated local file, not tracked by git; rebuilt by the pipeline, not byte-reproducible) | Authoritative (approved) | 86,257,664 | `00e7437697c8…` |
| [`outputs/phase5/fpa_month_end_close_analysis.xlsx`](../outputs/phase5/fpa_month_end_close_analysis.xlsx) | 12-sheet Excel workbook | Authoritative (approved) | 272,343 | `71e23dca9e0b…` |
| [`outputs/phase6/fpa_financial_analytics_dashboard.html`](../outputs/phase6/fpa_financial_analytics_dashboard.html) | Standalone interactive dashboard | Authoritative (approved) | 7,317,802 | `43d2505abe21…` |
| `fpa_monthly_close_cleaned.xlsx` (outside the repository) | Phase 2 review workbook (77 fields per the Phase 3 design; not the CSV's 192) | Historical review artefact | 67,381,749 | `270edc6b33ae…` |

The raw file is the only source for every downstream number. The DuckDB file is a local build product; its content, not its bytes, is reproducible (Phase 7, ISS-02).

## 3. Project root and configuration

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`README.md`](../README.md) | Root README written after Phase 5; **outdated** (says the dashboard does not exist). Replaced by the Phase 8 draft in a later phase | Historical (preserved unchanged) | 10,617 | `44759e0611f7…` |
| [`HOW_TO_RUN.txt`](../HOW_TO_RUN.txt) | Run instructions, corrected in Phase 7 (ISS-01, ISS-02). Does not include the dashboard build step | Current | 4,306 | `6556e83d6d8e…` |
| [`requirements.txt`](../requirements.txt) | Pinned Python dependencies (QA-only tools such as Playwright are not listed) | Current | 238 | `3497bbbced84…` |
| [`.gitignore`](../.gitignore) | Working-copy edit (uncommitted): ignores the database, processed CSVs, raw CSVs and caches. Ignoring does **not** untrack the raw CSV, which is already tracked and public | Current | 436 | `eebe1697e750…` |
| `.github/workflows/.gitkeep`, `dashboard/.gitkeep`, `outputs/.gitkeep`, `sql/.gitkeep`, `src/.gitkeep`, `tests/.gitkeep`, `data/processed/.gitkeep` | Empty folder keepers (no CI workflow exists) | Placeholder | 0 | — |
| `data/raw/PUT_RAW_CSV_HERE.txt` | Instruction stub for the raw file | Placeholder | 156 | `e23a22a7bb8d…` |
| `data/processed/PUT_CLEANED_CSV_HERE.txt` | Instruction stub for the cleaned file | Placeholder | 230 | `650162c1015b…` |

## 4. Source code

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`src/clean_fpa_monthly_close.py`](../src/clean_fpa_monthly_close.py) | Phase 3 cleaner (row-preserving; refuses a raw file with the wrong hash) | Authoritative (approved) | 216,147 | `e9eadd252b0c…` |
| [`src/phase4_pipeline.py`](../src/phase4_pipeline.py) | Phase 4 pipeline: loads, builds the database, runs the SQL, validates, exports 72 CSVs and a manifest | Authoritative (approved) | 17,545 | `6814959b079b…` |
| [`src/phase4_crosscheck.py`](../src/phase4_crosscheck.py) | Python cross-check of the SQL results | Authoritative (approved) | 20,685 | `93e7b70e13b5…` |
| [`src/phase4_report.py`](../src/phase4_report.py) | Generates the Phase 4 analysis report and insight register from the validated database | Authoritative (approved) | 81,827 | `692309b7e9fa…` |
| [`src/phase5_excel.py`](../src/phase5_excel.py) | Generates the Excel workbook; fails closed on tampered inputs | Authoritative (approved) | 188,592 | `02b45089fc71…` |
| [`src/phase6_dashboard.py`](../src/phase6_dashboard.py) | Builds the dashboard HTML from the template, style and scripts | Authoritative (approved) | 11,267 | `282b947bd3c9…` |
| [`src/phase6_template.html`](../src/phase6_template.html) | Dashboard HTML template | Authoritative (approved) | 5,842 | `a122eb962f9e…` |
| [`src/phase6_style.css`](../src/phase6_style.css) | Dashboard styles (light and dark themes) | Authoritative (approved) | 13,734 | `53e54052d322…` |
| [`src/phase6_core.js`](../src/phase6_core.js) | Dashboard state, filters, aggregation engine | Authoritative (approved) | 50,346 | `2607be6b7b9b…` |
| [`src/phase6_views.js`](../src/phase6_views.js) | Dashboard tabs, charts, tables, export, checks | Authoritative (approved) | 97,234 | `e68232aaa4e7…` |
| [`src/phase6_report.py`](../src/phase6_report.py) | Generates the Phase 6 QA report | Current | 10,689 | `8ab0a3ec4a24…` |

## 5. SQL

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`sql/phase4/01_dimensions_and_views.sql`](../sql/phase4/01_dimensions_and_views.sql) | Account dimension, views, macros | Authoritative (approved) | 7,412 | `30a2198df2d7…` |
| [`sql/phase4/02_grain_and_overview.sql`](../sql/phase4/02_grain_and_overview.sql) | Grain proof and overview tables a0–a8 | Authoritative (approved) | 10,395 | `2fc635a00fa6…` |
| [`sql/phase4/03_load_validation.sql`](../sql/phase4/03_load_validation.sql) | Load validation | Authoritative (approved) | 18,557 | `206b025d464d…` |
| [`sql/phase4/04_budget_variance.sql`](../sql/phase4/04_budget_variance.sql) | Budget variance b1–b11 | Authoritative (approved) | 14,008 | `6dfd7ccb5ca1…` |
| [`sql/phase4/05_forecast_error.sql`](../sql/phase4/05_forecast_error.sql) | Forecast error c1–c8 | Authoritative (approved) | 7,975 | `257993f1b0aa…` |
| [`sql/phase4/06_prior_year.sql`](../sql/phase4/06_prior_year.sql) | Prior year d1–d5 | Authoritative (approved) | 5,420 | `bf10be797b31…` |
| [`sql/phase4/07_gross_profit.sql`](../sql/phase4/07_gross_profit.sql) | Gross profit e1–e6 | Authoritative (approved) | 9,274 | `126dfc5e4073…` |
| [`sql/phase4/08_cost_structure.sql`](../sql/phase4/08_cost_structure.sql) | Cost structure f1–f7 | Authoritative (approved) | 7,584 | `ac5faa1887d2…` |
| [`sql/phase4/09_trend_volatility.sql`](../sql/phase4/09_trend_volatility.sql) | Trends g1–g6 | Authoritative (approved) | 5,503 | `4869bc3ce785…` |
| [`sql/phase4/10_balance_sheet.sql`](../sql/phase4/10_balance_sheet.sql) | Balance sheet h1–h6 | Authoritative (approved) | 5,539 | `7d57da44481b…` |
| [`sql/phase4/11_dq_exposure_scenarios.sql`](../sql/phase4/11_dq_exposure_scenarios.sql) | Scenarios i1–i10 | Authoritative (approved) | 20,917 | `67a76b9220e2…` |
| [`sql/phase4/99_analytical_validation.sql`](../sql/phase4/99_analytical_validation.sql) | Independent validation tables | Authoritative (approved) | 27,517 | `85d5ed05a0af…` |

Guide: [SQL_ANALYTICS_GUIDE.md](SQL_ANALYTICS_GUIDE.md).

## 6. Outputs by phase

### Phase 3 (cleaning outputs)

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`data/processed/QC_Report.txt`](../data/processed/QC_Report.txt) | Cleaner QC report (**contains build-environment paths**, ISS-03) | Current; open defect | 50,141 | `886b2b868a22…` |
| [`data/processed/qc_summary.json`](../data/processed/qc_summary.json) | Machine-readable QC summary (**contains build-environment paths**, ISS-03) | Current; open defect | 16,328 | `02df16bbfcbc…` |

### Phase 4 (SQL results)

`outputs/phase4/` holds 73 files: 72 result CSVs and one manifest. All carry the status **Authoritative (approved)**. Their row counts and hashes are listed in [`outputs/phase4/MANIFEST.json`](../outputs/phase4/MANIFEST.json), which the Phase 5 build verifies.

| Family | Files | Content |
|---|---:|---|
| `a*` | 9 | Grain, period, entity, division, GL, reliability, coverage, mapping |
| `b*` | 11 | Budget variance |
| `c*` | 8 | Forecast error |
| `d*` | 5 | Prior year |
| `e*` | 6 | Gross profit |
| `f*` | 7 | Cost structure |
| `g*` | 6 | Trends and volatility |
| `h*` | 6 | Balance sheet |
| `i*` | 10 | Scenarios and data-quality exposure |
| `val*` | 4 | Validation tables |
| Total CSVs | 72 | |
| [`outputs/phase4/MANIFEST.json`](../outputs/phase4/MANIFEST.json) | Manifest of the 72 CSVs with hashes and row counts | Authoritative (approved) | 10,203 | `41f572e0cca2…` |

### Phase 5 (workbook)

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`outputs/phase5/PHASE5_QA_REPORT.md`](../outputs/phase5/PHASE5_QA_REPORT.md) | Workbook QA report | Authoritative (approved) | 9,702 | `7df3b6d1a0d7…` |
| [`outputs/phase5/MANIFEST.json`](../outputs/phase5/MANIFEST.json) | Workbook manifest (records inputs and generator hash) | Authoritative (approved) | 3,486 | `2a2ab765ceb1…` |

### Phase 6 (dashboard)

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`outputs/phase6/DASHBOARD_QA_REPORT.md`](../outputs/phase6/DASHBOARD_QA_REPORT.md) | Dashboard QA report (298 browser checks) | Evidence | 53,662 | `643739bcb8a3…` |
| [`outputs/phase6/qa_results.json`](../outputs/phase6/qa_results.json) | Machine-readable Phase 6 results | Evidence | 69,806 | `17c76bd712ee…` |
| [`outputs/phase6/negative_controls.json`](../outputs/phase6/negative_controls.json) | Negative-control results (6 of 6 detected) | Evidence | 1,233 | `b27e0ce5d52f…` |
| [`outputs/phase6/payload_stats.json`](../outputs/phase6/payload_stats.json) | Dashboard payload statistics | Evidence | 178 | `f5518f0a97fc…` |
| [`outputs/phase6/qa_print_preview.pdf`](../outputs/phase6/qa_print_preview.pdf) | Chromium print-media PDF preview (38 pages) | Evidence | 4,505,544 | `05d3cd58c55e…` |
| `outputs/phase6/qa_screens/` | 30 screenshots of the dashboard tabs from the Phase 6 QA | Evidence | — | not in the manifest |

### Phase 7 (QA package)

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`outputs/phase7/PHASE7_QA_REPORT.md`](../outputs/phase7/PHASE7_QA_REPORT.md) | End-to-end QA and project audit report | Evidence | 23,055 | `2e7f8f956314…` † |
| [`outputs/phase7/qa_results.json`](../outputs/phase7/qa_results.json) | Registry of the 823 recorded checks and observations | Evidence | 413,271 | `55add337a0d4…` |
| [`outputs/phase7/DATA_LINEAGE_RECONCILIATION.xlsx`](../outputs/phase7/DATA_LINEAGE_RECONCILIATION.xlsx) | Record-count lineage and reconciliation | Evidence | 40,286 | `c904fb4a312f…` ‡ |
| [`outputs/phase7/FINANCIAL_RECONCILIATION.xlsx`](../outputs/phase7/FINANCIAL_RECONCILIATION.xlsx) | Metric-by-metric reconciliation | Evidence | 94,032 | `f4d7860663b6…` ‡ |
| [`outputs/phase7/ISSUE_LOG.xlsx`](../outputs/phase7/ISSUE_LOG.xlsx) | Issue log ISS-01 to ISS-18 | Evidence | 15,344 | `b2debccc4c3e…` ‡ |
| `outputs/phase7/file_manifest_sha256.txt` | The SHA-256 manifest used by this catalogue | Evidence | — | not self-hashed |
| `outputs/phase7/test_execution_logs/` | Logs of the isolated re-run, the cleaner re-run and the corrected-instructions regression (46 files) | Evidence | — | listed in the manifest |
| `outputs/phase7/evidence/` | Dashboard evidence (12 files), pre-Phase-7 hash list, the **original `HOW_TO_RUN.txt` preserved before the ISS-01/02 correction**, and 28 unmanifested work files | Evidence | — | dashboard evidence and originals listed in the manifest; work files not |

Phase 8 did not modify any Phase 7 evidence.

## 7. Tests

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`tests/conftest.py`](../tests/conftest.py) | pytest fixtures | Current | 2,287 | `8dc006eed9ce…` |
| [`tests/test_phase4.py`](../tests/test_phase4.py) | Phase 4 full-data tests | Current | 13,351 | `1d90705fd31f…` |
| [`tests/test_phase4_units.py`](../tests/test_phase4_units.py) | Phase 4 fixture tests | Current | 19,463 | `53d0a8aede91…` |
| [`tests/test_phase5_excel.py`](../tests/test_phase5_excel.py) | Workbook tests (51) | Current | 45,842 | `73361c8e9064…` |
| [`tests/phase6_dashboard_qa.py`](../tests/phase6_dashboard_qa.py) | Phase 6 browser QA (Playwright, Chromium) | Current | 129,251 | `a38c934224d3…` |
| [`tests/phase6_negative_controls.py`](../tests/phase6_negative_controls.py) | Phase 6 negative controls | Current | 5,401 | `656aff3ec2d7…` |
| `tests/phase7/` (12 Python modules, `p7_*.py`) | Phase 7 independent reference and audit code; it imports no project module | Evidence | — | each file listed in the manifest |

Two test scripts contain environment-specific paths (see [ASSUMPTIONS_LIMITATIONS_AND_RISKS.md](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md), item 17).

## 8. Documentation

| Path | Role | Status | Bytes | SHA-256 |
|---|---|---|---:|---|
| [`docs/DATA_DICTIONARY.md`](../docs/DATA_DICTIONARY.md) | Column dictionary for the 43 source fields | Historical (Phase 1) | 16,862 | `ab7d4971faad…` |
| [`docs/DATA_PROVENANCE.md`](../docs/DATA_PROVENANCE.md) | Provenance statement; confirms provenance and licence are unverified | Current | 4,713 | `aee2eb339227…` |
| [`docs/FINANCIAL_METRICS.md`](../docs/FINANCIAL_METRICS.md) | Phase 1–3 candidate rules R1–R14. **Pre-dates the delivered results**; its variance % is unguarded. Superseded in practice by FINANCIAL_METRICS_AND_METHODOLOGY.md | Historical (preserved unchanged) | 20,003 | `c93da2ea2d3f…` |
| [`docs/TEST_PLAN.md`](../docs/TEST_PLAN.md) | Test plan (Phase 1) | Historical | 8,551 | `b7d8d8942baa…` |
| [`docs/PHASE4_ANALYSIS_REPORT.md`](../docs/PHASE4_ANALYSIS_REPORT.md) | Phase 4 analysis report generated from the validated database | Authoritative (approved) | 22,236 | `f3cfbd0a6c5f…` |
| [`docs/PHASE4_INSIGHT_REGISTER.md`](../docs/PHASE4_INSIGHT_REGISTER.md) | Seven-insight register (INS-01 to INS-07) | Authoritative (approved) | 36,392 | `b2f3339e5057…` |
| [`docs/PHASE4_FILE_AUDIT_MATRIX.md`](../docs/PHASE4_FILE_AUDIT_MATRIX.md) | Phase 4 file audit matrix | Historical | 38,416 | `3ec8e8252d53…` |
| [`docs/PHASE4_ACCEPTANCE_REVIEW.md`](../docs/PHASE4_ACCEPTANCE_REVIEW.md) | Phase 4 acceptance review | Historical | 12,213 | `a5e373225429…` |
| [`docs/PHASE5_REVIEW_RESPONSE.md`](../docs/PHASE5_REVIEW_RESPONSE.md) | Response to the Phase 5 review | Historical | 5,712 | `59c90007de20…` |

### Phase 8 documentation package (this package)

Located in `outputs/phase8_final/package/` (corrected). The first, uncorrected package is preserved unchanged in `outputs/phase8/`. These files are **drafts**, not yet copied into the repository's `docs/` folder or root.

| File | Purpose |
|---|---|
| `README_PHASE8_DRAFT.md` | Draft replacement for the root README |
| `docs/PROJECT_OVERVIEW.md` | Context, objective, scope, findings |
| `docs/END_TO_END_WORKFLOW.md` | Workflow diagram, stages, folder structure |
| `docs/DATA_AND_CLEANING_METHODOLOGY.md` | Raw data, cleaning, exclusions |
| `docs/SQL_ANALYTICS_GUIDE.md` | Database, views, query families |
| `docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md` | The 12 worksheets |
| `docs/DASHBOARD_USER_GUIDE.md` | The nine tabs and controls |
| `docs/FINANCIAL_METRICS_AND_METHODOLOGY.md` | Metric definitions |
| `docs/QA_AND_VALIDATION_SUMMARY.md` | QA results |
| `docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md` | The 17-item register |
| `docs/EXECUTIVE_SUMMARY.md` | One-page summary |
| `docs/PROJECT_FILE_CATALOG.md` | This catalogue |
| `docs/PROJECT_CHANGELOG.md` | Phase-by-phase history |
| `docs/PORTFOLIO_CASE_STUDY_DRAFT.md` | Case-study draft (unpublished) |
| `docs/PHASE8_INDEPENDENT_REVIEW_ERRATA.md` | Errata from the independent review (also in `outputs/phase8_final/`) |
| `PHASE8_DOCUMENTATION_QA_REPORT.md` | Original documentation QA report, unchanged, with a supplemental addendum appended |
| `PHASE8_FINAL_DOCUMENTATION_QA.md` | QA of the correction round |

## 9. Superseded and conflicting material

| Item | Conflict | Treatment |
|---|---|---|
| Root `README.md` | Says Phase 6 and the dashboard do not exist | Preserved; draft replacement provided |
| `docs/FINANCIAL_METRICS.md` | States it contains no results; unguarded variance % | Preserved; new methodology document describes the delivered logic |
| `HOW_TO_RUN.txt` | Original version omitted the output-directory flag and the rebuild-order fix | Corrected in Phase 7; original preserved in `outputs/phase7/evidence/originals_before_correction/` |
| Phase 6 report line "Print outputs the visible tab" | Contradicted by the print stylesheet and the same report's print check (all nine views) | Dashboard guide follows the code; noted in the Phase 8 QA report |
| Junk-entity row count 173 (Phase 1 documents) versus 204 (cleaner) | 173 counts names only; 204 is names plus codes | Both explained in the methodology document |

