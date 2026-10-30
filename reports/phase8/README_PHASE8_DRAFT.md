> **Historical document (Phase 8 draft, kept unchanged below this note).** Superseded by the root [README](../../README.md) and by [docs/PUBLICATION_DECISION.md](../../docs/PUBLICATION_DECISION.md); its status statements describe the Phase 8 state.

# Month-End Close Reliability & Financial Performance Analytics

> **Status: draft (Phase 8). Not approved for public release. The GitHub repository was publicly accessible when checked, and it contains the raw CSV: read *Repository status and data exposure* below first.**
> Phases 1–7 are completed. Phase 8 (documentation) is in preparation. Public release remains blocked pending data provenance, redistribution rights, repository-history review and outstanding portability checks (see [Project status](#h-project-status)).
>
> **About the data.** NovaBridge Industries is a fictional group. The project owner describes the dataset as synthetic; that description, its provenance and its redistribution licence have **not** been independently verified. Nothing in this project is evidence of how a real company performed.
>
> **Evidence labels used throughout the documentation package:** **Verified** = checked against a project file or a Phase 7 check. **Owner-stated** = stated by the project owner, not independently checked. **Assumption** = a provisional project rule. **Unresolved** = neither the data nor the owner has settled it.
>
> This file is a draft replacement for the root `README.md`. The existing root `README.md` has not been changed (it still describes the project as it stood after Phase 5). Replacing it is a Phase 9 decision.

---

## A. Project introduction

**Project.** Month-End Close Reliability & Financial Performance Analytics — a month-end close and financial-performance analysis of one extract from a fictional group, NovaBridge Industries (six legal entities, five divisions, January 2023 to December 2025).

## Repository status and data exposure (read first)

| Fact | Status | Evidence |
|---|---|---|
| The GitHub repository `kunalkanjwani08-afk/month-end-close-reliability-fpa-analytics` is **publicly accessible** | **Verified** on 2026-10-30 (read-only GitHub API call: `private: false`, `visibility: public`, default branch `main`, last push 2026-10-28T06:29:51Z). Earlier project notes recorded the repository as created private; when or how it became public is **not known**. | Phase 8 correction round |
| The raw CSV (51,938,535 bytes) is **present in the public `main` branch** | **Verified** (same check: `data/raw/fpa_monthly_close_raw_messy.csv` appears in the `main` tree at 51,938,535 bytes) | Phase 8 correction round |
| The raw CSV was **committed to Git earlier in the project** | **Verified**: Stage 0 commit `1d601c0` (2026-10-28 05:34 UTC) | `git log` |
| What is on the remote | Three commits (Stage 0, Phase 1 twice) and these files only: `.gitignore`, `README.md`, `requirements.txt`, `docs/` (data dictionary, financial metrics, provenance, test plan), placeholder files and the raw CSV. The Phase 2 to Phase 8 work is **not** on the remote. | Same check |
| Phase 7 and Phase 8 work | Phase 7 did not push or publish additional changes. Phase 8 documents have **not** been committed or pushed by this work. | Git status in the working copy |
| Dataset provenance and redistribution permission | **Unverified.** The owner describes the data as synthetic; no provenance record or licence exists. The extract contains person-like cost-centre owner names and user IDs. | `docs/DATA_PROVENANCE.md`; risk register item 1 |
| Making the repository private | Would **not** erase historical commits, forks, clones, caches or copies already downloaded. This work did **not** change visibility, delete files or rewrite history. **The owner must make any such change manually and re-check the current visibility**; this table is a point-in-time check. | - |

Distinguish: the **tracked raw CSV** (in git and in public `main`) from the **generated local outputs** (`data/processed/` cleaned CSV and DuckDB file: not tracked, not on the remote). The working-copy `.gitignore` now lists `data/raw/*.csv`, but that edit is uncommitted and does not remove a file already tracked.

**The repository is therefore a publication blocker until the owner has decided what may be public.**

**Purpose.** To show, end to end and with evidence, how a finance analytics team takes a messy month-end extract, decides how much of it can be trusted, analyses the trusted part against budget, forecast and prior year, and reports the result in tools a finance team actually uses (SQL, Excel and an interactive dashboard), while independently checking every number.

**Data facts.** The dataset contains 152,682 source extract records, including 350 non-posting subtotal/check records. These 350 records are not treated as ordinary posted journal lines. The `source_system` field contains these observed labels: SAP, Oracle, Excel upload, NetSuite and Tally (SAP also appears with a trailing space in 2,038 raw rows). The actual originating platforms have not been independently authenticated.

**Business problem.** A group's month-end close arrives as one extract with mixed number formats, placeholder text, inconsistent labels and scales, non-posting subtotal rows, test entities and journals in different approval states. Before anyone reports performance, finance has to know how much of the extract is reportable and why the rest is not.

**Why it matters.** Month-end reporting is only as reliable as the population behind it. In this extract only 58,340 of 152,682 source rows (38.2%) qualify for the reported P&L under the project's provisional rules, and the choice of journal-status rule alone moves reported revenue from $202.65M to $471.58M. Stating the population, the rule and the sensitivity next to each number is the core of the exercise.

**What the project demonstrates.**
- Data cleaning that preserves every source row and records each decision (Python, pandas).
- A fixed, auditable rule for what is reportable, with one exclusion reason per row.
- SQL analysis in DuckDB: budget variance, forecast error, prior-year comparison, gross-profit scenarios, cost concentration and data-quality sensitivity.
- An Excel workbook with live formulas and a live reconciliation sheet.
- A standalone interactive HTML dashboard.
- Independent QA: a separate pandas reference rebuilt every figure and compared it with the SQL, workbook and dashboard.
- Honest handling of unresolved accounting questions: they are disclosed and carried as sensitivities, not settled by assumption.

**Target audience.** FP&A managers, financial controllers, finance business analysts and recruiters reviewing finance analytics work — once publication permission and privacy checks are resolved.

---

## B. Project overview

The journey runs in one direction, and each stage is checked before the next one relies on it:

1. **Messy extract.** 152,682 rows × 43 text columns. Amounts are text in several formats, with placeholders such as `###`, `#N/A`, `NA`, `null` and `-`.
2. **Financial data cleaning and data quality (Python).** Every row is kept. The cleaner parses amounts, restores likely divided amounts to full scale where evidence supports it, flags duplicate candidates, FX anomalies and sign anomalies, and assigns each row exactly one primary exclusion reason (or "eligible"). Output: a canonical 192-column cleaned CSV and a QC report.
3. **SQL analytical processing (DuckDB).** The cleaned CSV is loaded, checked against the cleaner's counts and turned into defined populations (`v_pl_actual`, `v_pl_budget`, `v_pl_forecast`, `v_pl_prior`, `v_bs_actual` and others). All analysis reads those views and writes 72 output tables.
4. **Budget and variance analysis.** Variance = actual − budget, with a guarded percentage. Results are shown on four sign populations because the account sign convention is unresolved.
5. **Forecast and prior-year comparisons.** Forecast error, bias and WAPE; the prior-year *column* is compared with the dataset's own prior-year actuals. No forecast-skill claim is made, because the extract has no forecast version or as-of date.
6. **Gross-profit scenarios.** Three explicit treatments of the discount account (GL 4190) are shown side by side. None is declared authoritative.
7. **Cost concentration.** Pareto shares, top-member shares and a Herfindahl–Hirschman index (HHI) by GL account, entity, division and cost centre.
8. **Excel review and reconciliation.** A 12-sheet workbook built only from the validated database, with a Reconciliation & QA sheet of live PASS/FAIL formulas.
9. **Interactive dashboard.** A standalone HTML file with nine tabs, global filters, scenario selectors, cross-filtering, CSV export and print.
10. **Quality assurance (Phase 7).** An independent pandas reference reproduced the SQL outputs, the workbook and the dashboard on identical populations: 780 checks executed (774 PASS, 1 FAIL, 1 BLOCKED, 4 NOT TESTED, plus 43 INFO observations).

Data quality and the exclusion rule decide *what* is analysed; SQL and Excel decide *how* it is calculated; the dashboard decides *how it is read*; QA decides *whether the three agree*. A successfully cleaned dataset is not the same as resolved business definitions: several accounting questions remain open and are listed in [ASSUMPTIONS_LIMITATIONS_AND_RISKS.md](../../docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md).

---

## C. Technology stack

Only technologies actually used are listed. Versions are those recorded in `requirements.txt` or in the Phase 7 QA environment.

| Technology | Used for | Version evidence |
|---|---|---|
| Python | Cleaning script, pipeline, report and workbook generators, QA code | 3.11+ required by the instructions; QA ran on 3.13.16 |
| pandas, NumPy | Cleaning, independent QA reference | pandas 3.0.5; NumPy pinned 2.4.6, QA ran on 2.5.3 |
| DuckDB and SQL | Analytical database and the 12 SQL scripts in `sql/phase4/` | duckdb 2.0.0 |
| Excel (.xlsx) | Phase 5 analysis workbook; Phase 2 review workbook | written with XlsxWriter 3.2.9, read with openpyxl 3.1.5 |
| HTML, CSS, JavaScript | Phase 6 dashboard (no third-party library, no network request) | standalone file, 7,317,802 bytes |
| pytest | Phase 4 and Phase 5 automated tests | 9.2.0 |
| Playwright with Chromium | Browser tests of the dashboard (QA only; not listed in `requirements.txt`) | Playwright 1.56.0, Chromium 141 |
| LibreOffice (headless) | Independent recalculation of workbook formulas (QA only) | 24.2.7.2 |

Not used: Power BI, any hosted service, any continuous-integration workflow (`.github/workflows/` holds only a placeholder).

---

## D. Project phases

> **Phase numbering note.** Phases 2 and 3 are labelled differently in different project files. The master archive and the Phase 7 report call the cleaned dataset and QC outputs "Phase 2 outputs" and the cleaning script "Phase 3". The Phase 4 documents call the same cleaned CSV the "Phase 3 canonical output". This package follows the archive and Phase 7 labelling and notes the alternative where it matters. No file is affected by the difference.

| Phase | Objective | Major work and deliverables | Connection to the next phase |
|---|---|---|---|
| **1 — Project Design and Data Understanding** | Define the problem, scope, success criteria and rules before touching the data. | Repository set-up with the raw CSV committed unchanged; `docs/DATA_DICTIONARY.md`, `docs/FINANCIAL_METRICS.md` (rules R1–R14), `docs/DATA_PROVENANCE.md`, `docs/TEST_PLAN.md`, `requirements.txt`, `.gitignore`. | The rules register and exclusion precedence become the cleaning and SQL specification. |
| **2 — Data Acquisition and Initial Data Quality Review** | Register the raw file, verify its identity and profile its quality. | SHA-256, row and column gate on the raw file; profile of all 43 columns; 43 prioritised findings; outputs packaged as Phase 2: the canonical cleaned CSV (192 columns), the review workbook (77 shared fields), `QC_Report.txt`, `qc_summary.json`. | The cleaned CSV is the only input to Phase 4. |
| **3 — Python Data Cleaning and Validation** | Make the cleaning reproducible and self-checking. | `src/clean_fpa_monthly_close.py` (version 1.0.0): integrity gate, row-preserving cleaning, per-row scale decisions, duplicate and sign flags, 43 in-memory and 27 read-back checks (all PASS). | Re-running it on the approved raw file reproduces the cleaned CSV byte for byte (Phase 7). |
| **4 — SQL Database, Financial Analysis and Analytical Outputs** | Turn the cleaned data into validated financial analysis. | `src/phase4_pipeline.py`, 12 SQL scripts, DuckDB database, 72 output tables, `docs/PHASE4_ANALYSIS_REPORT.md`, `docs/PHASE4_INSIGHT_REGISTER.md` (7 insights), 289 validation rows (55 + 24 + 86 + 124), 74 tests. | The validated database and output tables are the only source for the workbook and dashboard. |
| **5 — Excel Financial Analysis and Reconciliation** | Give finance users a formula-driven review workbook. | `outputs/phase5/fpa_month_end_close_analysis.xlsx` (12 sheets, 3,819 formulas, 137 live reconciliation checks), 51 tests, `PHASE5_QA_REPORT.md`. | The same populations and definitions feed the dashboard. |
| **6 — Interactive FP&A Financial Analytics Dashboard** | Let users explore the validated data interactively. | `outputs/phase6/fpa_financial_analytics_dashboard.html` (nine tabs, 136,330 embedded lines), `DASHBOARD_QA_REPORT.md`, 297 PASS / 0 FAIL / 1 SKIP browser checks, 6 of 6 negative controls detected. | Phase 7 tests it independently. |
| **7 — End-to-End QA and Independent Financial Validation** | Prove the numbers and the process independently. | `outputs/phase7/`: report, three reconciliation workbooks, check registry, manifest, logs and evidence; 780 checks; 18 issues logged (none critical or high). | Findings and the corrected `HOW_TO_RUN.txt` feed this documentation phase. |
| **8 — Professional Documentation and Project Presentation** | Explain what was built, how, why and with what limits. | This package: the README draft, 13 documents and a documentation QA report. No analysis, calculation or dashboard change. | Phase 9 (publication preparation) starts only when requested. |

---

## E. Key deliverables

Paths are relative to the repository root. The raw CSV under `data/raw/` is **tracked by git and present in the public `main` branch**. The cleaned CSV and DuckDB file under `data/processed/` are generated local outputs (large, not tracked, not on the remote).

| Deliverable | Path |
|---|---|
| Raw extract (never edited) | data/raw/fpa_monthly_close_raw_messy.csv (`data/raw/fpa_monthly_close_raw_messy.csv` — not published directly; see README) |
| Canonical cleaned dataset (192 columns; generated, not tracked by git) | data/processed/fpa_monthly_close_cleaned.csv (`data/processed/fpa_monthly_close_cleaned.csv` — not published directly; see README) |
| Cleaning QC report and summary | [data/processed/QC_Report.txt](../../data/processed/QC_Report.txt), [data/processed/qc_summary.json](../../data/processed/qc_summary.json) |
| Cleaning script | [src/clean_fpa_monthly_close.py](../../src/clean_fpa_monthly_close.py) |
| Analytical database (generated; not tracked by git) | data/processed/phase4_fpa.duckdb (`data/processed/phase4_fpa.duckdb` — not published directly; see README) |
| SQL scripts | [sql/phase4/](../../sql/phase4/) |
| Phase 4 output tables and manifest | [outputs/phase4/](../../outputs/phase4/), [outputs/phase4/MANIFEST.json](../../outputs/phase4/MANIFEST.json) |
| Phase 4 analysis report and insight register | [docs/PHASE4_ANALYSIS_REPORT.md](../../docs/PHASE4_ANALYSIS_REPORT.md), [docs/PHASE4_INSIGHT_REGISTER.md](../../docs/PHASE4_INSIGHT_REGISTER.md) |
| Excel analysis workbook | [outputs/phase5/fpa_month_end_close_analysis.xlsx](../../outputs/phase5/fpa_month_end_close_analysis.xlsx) |
| Phase 5 QA report | [outputs/phase5/PHASE5_QA_REPORT.md](../../outputs/phase5/PHASE5_QA_REPORT.md) |
| Interactive dashboard | [outputs/phase6/fpa_financial_analytics_dashboard.html](../../outputs/phase6/fpa_financial_analytics_dashboard.html) |
| Phase 6 QA report | [outputs/phase6/DASHBOARD_QA_REPORT.md](../../outputs/phase6/DASHBOARD_QA_REPORT.md) |
| Phase 7 QA report and workbooks | [outputs/phase7/PHASE7_QA_REPORT.md](../../outputs/phase7/PHASE7_QA_REPORT.md), [outputs/phase7/DATA_LINEAGE_RECONCILIATION.xlsx](../../outputs/phase7/DATA_LINEAGE_RECONCILIATION.xlsx), [outputs/phase7/FINANCIAL_RECONCILIATION.xlsx](../../outputs/phase7/FINANCIAL_RECONCILIATION.xlsx), [outputs/phase7/ISSUE_LOG.xlsx](../../outputs/phase7/ISSUE_LOG.xlsx) |
| Corrected run instructions | [HOW_TO_RUN.txt](../../HOW_TO_RUN.txt) |

Phase 8 documentation (this package):

| Document | Audience |
|---|---|
| [docs/EXECUTIVE_SUMMARY.md](../../docs/EXECUTIVE_SUMMARY.md) | Finance director, hiring manager |
| [docs/PROJECT_OVERVIEW.md](../../docs/PROJECT_OVERVIEW.md) | Finance director, FP&A manager |
| [docs/END_TO_END_WORKFLOW.md](../../docs/END_TO_END_WORKFLOW.md) | Technical reviewer |
| [docs/DATA_AND_CLEANING_METHODOLOGY.md](../../docs/DATA_AND_CLEANING_METHODOLOGY.md) | Analyst, reviewer |
| [docs/SQL_ANALYTICS_GUIDE.md](../../docs/SQL_ANALYTICS_GUIDE.md) | SQL reader |
| [docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md](../../docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md) | Excel user |
| [docs/DASHBOARD_USER_GUIDE.md](../../docs/DASHBOARD_USER_GUIDE.md) | Dashboard user |
| [docs/FINANCIAL_METRICS_AND_METHODOLOGY.md](../../docs/FINANCIAL_METRICS_AND_METHODOLOGY.md) | Analyst, reviewer |
| [docs/QA_AND_VALIDATION_SUMMARY.md](../../docs/QA_AND_VALIDATION_SUMMARY.md) | Reviewer |
| [docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md](../../docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md) | Everyone |
| [docs/PROJECT_FILE_CATALOG.md](../../docs/PROJECT_FILE_CATALOG.md) | Maintainer |
| [docs/PROJECT_CHANGELOG.md](../../docs/PROJECT_CHANGELOG.md) | Maintainer |
| [docs/PORTFOLIO_CASE_STUDY_DRAFT.md](../../docs/PORTFOLIO_CASE_STUDY_DRAFT.md) | Recruiter (future) |

---

## F. Project limitations

- **The data is owner-described as synthetic; its provenance and redistribution licence are not independently verified.** It must not be described as verified real-world business data, and no figure is evidence of real performance.
- **Every headline figure is conditional on provisional assumptions:** the Posted-only journal-status rule (R6), per-row scale restoration (R7), FX direction (R8), the variance-percentage convention (R10) and the per-line summing of budget, forecast and prior-year amounts. The account sign convention (R9), duplicate handling (R11) and consolidation (R12) are unresolved.
- Only **58,340 of 152,682** source rows (38.2%) are in the reported P&L population.
- **4,996 non-Posted lines appear in no dashboard view.** They fail the amount or scale gates (4,958 with no actual amount, 38 with an undetermined scale) and are counted only in the Phase 4 exclusion waterfall and the workbook's Data Quality sheet. The dashboard's journal-status table therefore covers 77,990 of the 82,986 status-excluded lines, not all of them.
- No favourable/unfavourable labels, EBITDA, DSO, DPO, working capital, close-duration or forecast-skill metric is produced; the data cannot support them.
- Microsoft Excel, Windows, a clean-machine install, Firefox, Safari, screen readers and a physical printer have **not** been tested.

The full register, with evidence needed to resolve each item, is in [docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md](../../docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md).

---

## G. Reproducibility

The steps below follow the corrected [HOW_TO_RUN.txt](../../HOW_TO_RUN.txt) (corrected in Phase 7 for issues ISS-01 and ISS-02). Commands use Windows syntax; Linux and macOS equivalents are given in that file.

**Environment.** Python 3.11 or newer. Dependencies are pinned in [requirements.txt](../../requirements.txt): pandas 3.0.5, numpy 2.4.6, openpyxl 3.1.5, XlsxWriter 3.2.9, duckdb 2.0.0, pytest 9.2.0. LibreOffice is needed for two Phase 5 tests (they are skipped, and the run is reported incomplete, without it).

**Inputs that must exist locally** (the raw CSV is tracked in git and present in public `main`; the cleaned CSV is generated and not tracked): `data\raw\fpa_monthly_close_raw_messy.csv` (SHA-256 `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff`). The cleaned CSV is regenerated from it; the pipeline refuses any cleaned file whose SHA-256 is not `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47`.

**Execution sequence.**

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Only if the cleaned CSV is missing (about 4-5 minutes). PowerShell line continuation is the backtick:
python src/clean_fpa_monthly_close.py `
  --input data/raw/fpa_monthly_close_raw_messy.csv `
  --output-dir data/processed
python src\phase4_pipeline.py                                      # ~20-30 s; exit 0 = all validation passed
python src\phase4_report.py                                        # regenerates the two Phase 4 documents
python -m pytest tests -q --ignore=tests\test_phase5_excel.py      # after a database rebuild
python src\phase5_excel.py
python -m pytest tests\test_phase5_excel.py -q
python src\phase5_excel.py --qa-report
python src\phase6_dashboard.py                                     # NOT in HOW_TO_RUN.txt; rebuilds the dashboard HTML
```

**Why `--input` is given.** The cleaner supports `--input` (verified in the script's argument parser) and otherwise searches for the file automatically. Naming the approved raw file explicitly reduces the risk of the cleaner selecting a different file that has the same name. No alternate raw file is deleted or overwritten by this. `HOW_TO_RUN.txt` (a Phase 7 file, not changed here) still shows the shorter form without `--input`; this command was **not re-executed in the Phase 8 correction round**; the cleaner was run in Phases 2 to 7.

`HOW_TO_RUN.txt` covers Phases 4 and 5 only. The last command (the dashboard build) is not in it; it exited 0 in the Phase 7 isolated re-run (step `07_phase6_build`). Adding it to `HOW_TO_RUN.txt` is a recommended Phase 9 change, not made here because the instruction file is an approved deliverable.

Without `--output-dir data\processed` the cleaner writes to a Downloads folder the pipeline does not read (ISS-01). The `--ignore` flag is needed because a rebuilt DuckDB file is not byte-identical to the previous one although its content is, and two Phase 5 tests compare the database hash (ISS-02).

**What has and has not been validated.** In Phase 7 the steps above were re-run in isolated copies on Linux (Python 3.13): the cleaner reproduced the cleaned CSV byte for byte, and the pipeline reproduced all 72 output tables and both Phase 4 documents byte for byte. **No Windows run and no clean-machine install (fresh virtual environment from `requirements.txt`) has been performed**; the QA environment used NumPy 2.5.3 rather than the pinned 2.4.6. The Phase 7 QA scripts in `tests/phase7/` document the method; one of them reads logs from the original build session and is not portable as it stands.

---

## H. Project status

| Item | Status |
|---|---|
| Phases 1–7 | Completed. Phase 7 gave no critical or high issue; two medium documentation defects were corrected and regression-tested. |
| Phase 8 | Documentation in preparation (this package). |
| Version control | Three commits exist (Stage 0 and Phase 1, dated 2026-10-28) and the remote repository is **publicly accessible** and holds the raw CSV (see *Repository status* above). Everything from Phase 2 onward is local and uncommitted. Phase 7 and Phase 8 pushed and published nothing. |
| Public release | **Blocked.** Open items: (1) data provenance, synthetic status and redistribution rights unverified (ISS-06); (2) the raw CSV has been tracked by git since Stage 0, so repository history and GitHub visibility need review; (3) `QC_Report.txt` and `qc_summary.json` record build-machine paths (ISS-03); (4) Windows and clean-machine reproducibility untested (ISS-05); (5) native Microsoft Excel validation untested. |
