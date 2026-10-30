# NovaBridge — Month-End Close Reliability & Financial Performance Analytics

**An end-to-end FP&A analytics portfolio project:** a messy, 152,682-row month-end ledger extract for a fictional group is cleaned without deleting a row, analysed in SQL (DuckDB), reviewed in a formula-driven Excel workbook, explored in an interactive dashboard, and independently re-checked in a 780-check QA phase.

> **Portfolio project on synthetic data.** NovaBridge Industries is fictional. The project owner states that the dataset is synthetic and was created for portfolio and learning purposes; that statement is **not independently verified** (no generator, seed or licence record exists). Nothing here describes the performance of a real company, and no figure should be read as one.
>
> **Licence: none.** No open-source licence has been selected and there is no `LICENSE` file. The code and data are visible for review; default copyright applies. This repository is not "open source".

| | |
|---|---|
| **Data** | 152,682 posting lines × 43 text columns (raw) → 192-column cleaned file, 36 months (Jan 2023 – Dec 2025), 6 entities, 5 divisions |
| **Code** | Python (cleaning, pipeline, Excel and dashboard builders), 12 SQL scripts, pytest suites (Phases 4–5), a dashboard browser-QA suite and the Phase 7 QA scripts |
| **Deliverables** | Cleaned dataset · 72 SQL output tables · 12-sheet Excel workbook (3,819 formulas) · 9-tab standalone dashboard · QA evidence · 24 documents |
| **Tested on 30 Oct 2026** | Fresh Python 3.13 environment on Linux: 125 pytest tests pass, 297 dashboard browser checks pass, 1 skipped (see [Testing](#testing)) |

---

## Contents

1. [The finance problem](#the-finance-problem)
2. [What the analysis shows (synthetic data)](#what-the-analysis-shows-synthetic-data)
3. [The nine phases](#the-nine-phases)
4. [Repository map](#repository-map)
5. [Data: what is here, and how to use it](#data)
6. [Data cleaning and validation](#data-cleaning-and-validation)
7. [SQL analysis](#sql-analysis)
8. [Excel workbook and reconciliation](#excel-workbook-and-reconciliation)
9. [Dashboard](#dashboard)
10. [Testing](#testing)
11. [Technologies](#technologies)
12. [Run it yourself](#run-it-yourself)
13. [Assumptions, limitations and open issues](#assumptions-limitations-and-open-issues)
14. [How this was built (AI assistance)](#how-this-was-built-ai-assistance)
15. [Licence and repository notes](#licence-and-repository-notes)

---

## The finance problem

A group's month-end close often arrives as **one extract** with mixed number formats (`1,234.56` next to `1.234,56`), placeholder text (`###`, `#N/A`, `NA`, `null`), inconsistent labels, unreliable scale fields, non-posting subtotal rows, test entities, and journals in different approval states. Adding it up produces a confident but unreliable number.

Before reporting performance, finance has to answer: **how much of this extract is reportable, and how far do the answers move under rules we cannot settle?** This project works through that:

* decide which records count, and give every excluded row **exactly one documented reason**;
* keep the as-reported value beside every adjusted value, and never delete or silently repair a row;
* vary each unresolved rule (journal status, scale, sign, duplicates) one at a time and report how far the headline moves;
* reconcile Python, SQL, Excel and the dashboard against each other, and **investigate differences rather than force them to match**;
* refuse to draw conclusions the extract cannot support.

## What the analysis shows (synthetic data)

These are findings about the synthetic extract, shown to illustrate the method, not about any real business.

* Only **58,340 of 152,682 rows (38.2%)** qualify for the reported P&L under the project's provisional rules.
* The journal-status rule alone moves reported revenue from **$202.65M** (Posted only) to **$471.58M** (all statuses). Stating the population and the rule beside every number is the point of the exercise.
* Seven insights are registered with evidence in [`docs/PHASE4_INSIGHT_REGISTER.md`](docs/PHASE4_INSIGHT_REGISTER.md), covering budget variance, forecast error (WAPE and bias), prior-year comparison, three explicit gross-profit treatments, and cost concentration (Pareto, HHI).
* Several things are deliberately **not** computed because the data cannot support them: no favourable/unfavourable labels, EBITDA, DSO, DPO, working capital, close-duration or forecast-skill metric.

## The nine phases

| # | Phase | Main deliverables | Where |
|---|---|---|---|
| 1 | **Project design and data understanding** | Rules register (R1–R14), data dictionary, provenance record, test plan | [`docs/`](docs/) |
| 2 | **Data acquisition and initial quality review** | Raw file identity gate (SHA-256, rows, columns); profile of all 43 columns; cleaned CSV and QC report | [`data/`](data/) |
| 3 | **Python data cleaning and validation** | `clean_fpa_monthly_close.py`: row-preserving cleaner, per-row scale decisions, duplicate and sign flags, 43 in-memory + 27 read-back checks | [`src/`](src/) |
| 4 | **SQL database and financial analysis** | 12 DuckDB scripts, pipeline, 72 output tables, 289 validation rows, analysis report, insight register | [`sql/`](sql/), [`outputs/phase4/`](outputs/phase4/) |
| 5 | **Excel analysis and reconciliation** | 12-sheet workbook, 3,819 formulas, 137 live reconciliation checks, 7 charts | [`excel/`](excel/), [`outputs/phase5/`](outputs/phase5/) |
| 6 | **Interactive dashboard** | Standalone HTML, nine tabs, filters, scenarios, cross-filtering, CSV export, print, light/dark | [`dashboard/`](dashboard/), [`outputs/phase6/`](outputs/phase6/) |
| 7 | **End-to-end QA and independent validation** | An independent pandas reference rebuilt every figure and compared it with SQL, Excel and the dashboard: 780 checks, 18 issues logged (none critical or high) | [`outputs/phase7/`](outputs/phase7/) |
| 8 | **Professional documentation** | 13 documents (executive summary, workflow, methodology, guides, risk register, catalog) | [`docs/`](docs/) |
| 9 | **Publication** | Full project published; lossless data compression; this README; publication reports | [`reports/phase9/`](reports/phase9/) |

## Repository map

```
.
├── README.md                    this file
├── HOW_TO_RUN.txt               exact run sequence (Windows / Linux / macOS)
├── requirements.txt             pinned dependencies (Python 3.11+)
├── data/
│   ├── raw/                     original extract (gzip) + checksum README
│   └── processed/               cleaned dataset (gzip), QC_Report.txt, qc_summary.json
├── src/                         cleaner, SQL pipeline, cross-check, report, Excel and dashboard builders
├── sql/phase4/                  12 numbered DuckDB scripts (+ sql/README.md)
├── excel/                       guide to the workbooks (the files live in outputs/)
├── dashboard/                   guide to the dashboard (the HTML lives in outputs/phase6/)
├── tests/                       fixture, full-data, Excel, dashboard and Phase 7 QA scripts
├── docs/                        24 documents (data dictionary, metrics, methodology, risks, ...)
├── outputs/
│   ├── phase4/                  72 analytical tables + MANIFEST.json
│   ├── phase5/                  Excel workbook, manifest, QA report
│   ├── phase6/                  dashboard HTML, QA report, screenshots
│   └── phase7/                  QA report, reconciliation workbooks, logs, evidence
├── reports/phase8/              documentation QA reports
├── reports/phase9/              publication inventory, manifest, validation, exclusions
└── .github/workflows/           (placeholder only; no CI exists)
```

Paths such as `outputs/phaseN/` are kept because the generators, manifests and tests write to and verify them; moving files would break those checks.

## Data

| File | Stored as | After decompression |
|---|---|---|
| [`data/raw/fpa_monthly_close_raw_messy.csv.gz`](data/raw/) | 11.2 MB | 51,938,535 bytes · SHA-256 `a0e6eddd…ff` |
| [`data/processed/fpa_monthly_close_cleaned.csv.gz`](data/processed/) | 28.5 MB | 174,545,248 bytes · SHA-256 `c184b677…9b47` |

* Both are **lossless GZIP** copies. On 30 Oct 2026 each was decompressed and compared with its original: identical SHA-256 and identical line count (152,683 lines each, i.e. 152,682 rows plus a header). Full hashes are in [`data/raw/README.md`](data/raw/README.md) and [`data/processed/README.md`](data/processed/README.md).
* The raw file is the **original, never-edited** extract. The cleaned file is a separate output of the cleaning script.
* **What the synthetic data represents:** a month-end ledger for NovaBridge Industries, a fictional group. Each row is one posting line with actual, budget, forecast and prior-year amounts in separate USD columns; P&L and balance-sheet lines are mixed; `scenario_tag` is noise by design. See the [data dictionary](docs/DATA_DICTIONARY.md) and [provenance record](docs/DATA_PROVENANCE.md).
* **Personal-data check (30 Oct 2026):** the data contains 8 person-like cost-centre owner names (initial + surname) and 8 generic system user IDs; no email address, phone number or URL appears in the columns checked. They are treated as fictional because the group is fictional; that is not proven.
* The Phase 4 DuckDB file (86 MB) is not published; it is rebuilt in about 20 seconds by the pipeline.

## Data cleaning and validation

[`src/clean_fpa_monthly_close.py`](src/clean_fpa_monthly_close.py) turns the 43-column text extract into a 192-column analytical file **without deleting a row**:

1. **Integrity gate**: checks the input's SHA-256, row and column counts before doing anything.
2. **Amount parsing**: US and European separators, currency marks, brackets, placeholders; ambiguous strings are flagged, not guessed.
3. **Scale restoration**: where `report_scale` is unreliable, a value is restored to full scale only when a direct identity test or a peer comparison supports it, and left *undetermined* otherwise.
4. **Flags, not repairs**: duplicate candidates, FX anomalies and sign anomalies are flagged and retained.
5. **One exclusion reason per row**: an ordered rule list assigns each row its first failed test (non-posting, test entity, balance-sheet line, journal status, unresolvable period, missing actual, undecidable scale) or marks it eligible.
6. **Self-checks**: 43 in-memory and 27 read-back checks, plus a row-for-row preservation check.

Methodology: [`docs/DATA_AND_CLEANING_METHODOLOGY.md`](docs/DATA_AND_CLEANING_METHODOLOGY.md) · rules register: [`docs/FINANCIAL_METRICS.md`](docs/FINANCIAL_METRICS.md).

## SQL analysis

Twelve numbered scripts in [`sql/phase4/`](sql/phase4/) define each population once and build, in order: dimensions and views; grain and overview; load validation; **budget variance**; **forecast error (WAPE, bias)**; **prior-year comparison**; **gross profit** under three treatments of a contra-revenue account; **cost concentration** (Pareto, HHI); trend and volatility; balance sheet (kept apart from the P&L); **data-quality scenarios** (status, scale, sign, duplicates); and a structural validation script. [`src/phase4_pipeline.py`](src/phase4_pipeline.py) runs them and fails closed: on any failed validation nothing is promoted. An independent pandas cross-check recomputes 124 figures. Guide: [`sql/README.md`](sql/README.md), [`docs/SQL_ANALYTICS_GUIDE.md`](docs/SQL_ANALYTICS_GUIDE.md).

## Excel workbook and reconciliation

[`outputs/phase5/fpa_month_end_close_analysis.xlsx`](outputs/phase5/fpa_month_end_close_analysis.xlsx) has 12 sheets (Start Here, Executive Summary, Monthly P&L, Budget vs Actual, Forecast & Prior Year, Entity & Division, GL & Cost Drivers, Gross Profit, Insights & Actions, Data Quality, Reconciliation & QA, Definitions), 3,819 formulas and 7 charts. Its **Reconciliation & QA** sheet holds 137 live PASS/FAIL formulas that tie the workbook back to the SQL outputs. Three further Phase 7 workbooks hold the independent lineage and financial reconciliation and the issue log. Guide: [`excel/README.md`](excel/README.md), [`docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md`](docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md).

## Dashboard

[`outputs/phase6/fpa_financial_analytics_dashboard.html`](outputs/phase6/fpa_financial_analytics_dashboard.html) is a **standalone 7.3 MB HTML file** (no server, no network, no third-party library) with nine tabs, global filters, journal-status / scale / sign / duplicate scenario selectors, chart cross-filtering, CSV export, print layout and light/dark themes. It embeds 136,330 line-level records.

**To use it: download the file and open it in a browser.** GitHub displays it as source code and does **not** run it; there is no hosted live demo. User guide: [`docs/DASHBOARD_USER_GUIDE.md`](docs/DASHBOARD_USER_GUIDE.md) · screenshots: [`outputs/phase6/qa_screens/`](outputs/phase6/qa_screens/).

## Testing

Distinguishing what was **run now** from what is **historical**:

**Re-run on 30 Oct 2026 for this publication** (Linux, Python 3.13.16, fresh virtual environment from `requirements.txt`; full evidence in [`reports/phase9/`](reports/phase9/)):

| Check | Result |
|---|---|
| `pip install -r requirements.txt` and `pip check` | clean, no conflicts |
| Python syntax (`compileall` of `src`, `tests`) | 0 errors |
| Phase 4 fixture tests | 42 passed |
| SQL: pipeline executes all 12 scripts on the real data and validates | exit 0; 72 tables rebuilt, **byte-identical** to the published `outputs/phase4/` |
| Phase 4 full-data tests | 74 passed (includes the 42 fixture tests) |
| Excel: workbook rebuild and Phase 5 tests | 3,819 formulas, 137/137 reconciliation checks, 51 tests passed |
| Excel: independent recalculation in headless LibreOffice | 137 PASS, 0 FAIL, 0 Excel error values |
| Dashboard: headless Chromium browser QA suite | 297 PASS, 0 FAIL, 1 SKIP (the screen-reader test, impossible here); covers filters, scenarios, themes, responsive widths, console errors |
| Lossless data compression | identical SHA-256 and line count after round trip |
| Secret, personal-data, path and prohibited-file scans; link check | see [`reports/phase9/PHASE9_VALIDATION_REPORT.md`](reports/phase9/PHASE9_VALIDATION_REPORT.md) |

In total, **125 pytest tests** (74 Phase 4 + 51 Phase 5; the 42 fixture tests are part of the 74) and **297 browser checks** (1 further check skipped, see above) were run now.

**Historical (Phase 7, not re-run as a whole):** an independent pandas reference compared with SQL, Excel and the dashboard: **780 checks executed: 774 PASS, 1 FAIL, 1 BLOCKED, 4 NOT TESTED, plus 43 INFO**. The single FAIL was a defect in the original run instructions (corrected and regression-tested), not in the data or calculations. See [`docs/QA_AND_VALIDATION_SUMMARY.md`](docs/QA_AND_VALIDATION_SUMMARY.md). The pipeline reproduced the cleaned CSV byte for byte in Phase 7; the cleaner was **not** re-run in this publication step.

**Not tested:** Windows, other Python versions, native Microsoft Excel, Firefox, Safari, screen readers, a physical printer.

## Technologies

Python 3.11+ (pandas 3.0.5, NumPy 2.4.6, OpenPyXL 3.1.5, XlsxWriter 3.2.9) · DuckDB 2.0.0 and SQL · pytest 9.2.0 · HTML/CSS/JavaScript (hand-written dashboard; no framework) · QA only: Playwright 1.56 with Chromium, LibreOffice (headless). Power BI is **not** used in this project.

## Run it yourself

```bash
git clone https://github.com/kunalkanjwani08-afk/month-end-close-reliability-fpa-analytics.git
cd month-end-close-reliability-fpa-analytics
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
gunzip -k data/raw/*.csv.gz data/processed/*.csv.gz      # or the Python one-liner in HOW_TO_RUN.txt
python src/phase4_pipeline.py                            # ~20 s; exit 0 = every validation passed
python -m pytest tests -q --ignore=tests/test_phase5_excel.py
python src/phase5_excel.py && python -m pytest tests/test_phase5_excel.py -q
python src/phase6_dashboard.py                           # rebuild the dashboard HTML
```

`HOW_TO_RUN.txt` has the full sequence, the Windows commands and the known pitfalls (for example, the cleaner must be given `--output-dir data/processed`). Quick look without running anything: open the dashboard HTML or the Excel workbook directly.

## Assumptions, limitations and open issues

* **Provenance:** synthetic status and the dataset's origin are owner-stated, not verified; no licence for the data exists.
* **Every headline figure is conditional** on provisional rules: the Posted-only journal-status rule, per-row scale restoration, FX direction, the variance-% convention and per-line summing of budget, forecast and prior-year amounts. The account **sign convention**, **duplicate handling** and **consolidation** remain unresolved.
* **4,996 non-Posted lines appear in no dashboard view** (they fail the amount or scale gates); they are counted in the Phase 4 exclusion waterfall and the workbook's Data Quality sheet.
* The account-to-section mapping has not been checked against an authoritative chart of accounts.
* **Sandbox build paths** (for example `/tmp/...`, no personal paths) remain in `QC_Report.txt`, `qc_summary.json` and Phase 7 logs; they are published unchanged because other files record their hashes.
* The Phase 7 scripts in `tests/phase7/` document the QA method; one reads logs from the original build session and is not portable as it stands.
* The full register, with the evidence that would resolve each item, is in [`docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md`](docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md).

Older documents keep their original wording as the historical record; where they call the release "blocked" or "draft" they describe Phase 8 and are superseded by [`docs/PUBLICATION_DECISION.md`](docs/PUBLICATION_DECISION.md).

## How this was built (AI assistance)

I (Kunal Kanjwani) set the scope, the finance rules, the analytical requirements, the review of every phase and the acceptance decisions, and I required that failures and untested areas be reported. **Claude (an AI assistant made by Anthropic) wrote most of the code and drafted most of the documentation under my direction**; I did not hand-write every line. Deliverables were also cross-reviewed with a second AI tool, and only corrections that held up against the project files were applied. Treat this as an AI-assisted project directed by a finance student, not as a demonstration of unaided coding.

## Licence and repository notes

* **No licence is granted.** No MIT, Apache, GPL or other open-source licence applies; default copyright is retained. Viewing and forking on GitHub is allowed by GitHub's Terms of Service, which does not grant wider redistribution rights.
* The raw CSV was committed uncompressed in the first commit of this repository (Stage 0). The history was **not** rewritten, so that earlier ~52 MB copy remains in git history; the current tree stores only the compressed copy.
* Phase 9 reports, including the superseded restricted-release plan, are in [`reports/phase9/`](reports/phase9/).
