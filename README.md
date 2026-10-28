# Month-End Close Reliability & Financial Performance Analytics

> **Status: Phase 1 (product design). The repository holds the raw extract, the folder chart and documentation only.**
> There is no cleaning code, SQL, test, dashboard or CI workflow yet. Folders marked `.gitkeep` are empty on purpose.

All data is stated by the project owner to be **synthetic** (not independently verified; see `docs/DATA_PROVENANCE.md`). It is not a real company's financials.

## What this project will become

A month-end close and financial-performance analysis for a fictional group, **NovaBridge Industries**, covering **January 2023 to December 2025**.

- Six legal entities and five divisions.
- Each row is a **posting** (one journal line), not a summary.
- P&L flows and balance-sheet balances sit in the **same** extract.
- Actual, budget, forecast and prior year are **separate columns**.
- `scenario_tag` is noise. It is not a reliable scenario selector.

## Business Objective, Scope & Success Criteria

**Problem.** A group's month-end close arrives as one extract from several source systems, with mixed formats, labels, scales and journal statuses. Before anyone reports performance, a finance team has to know how much of that extract can be trusted and why the rest cannot.

**Audience.** Finance, FP&A and financial-analytics professionals, and anyone reviewing this as a portfolio project.

**Questions the project will answer**
1. How many rows qualify for reported totals, and what is the reason for each exclusion?
2. Which data-quality and control issues (formats, placeholders, scale mismatches, duplicate candidates, missing keys, unposted journals) most affect reliability, by entity and source system?
3. On the validated scope, how do actual results compare with budget, forecast and prior year by period, entity, division and account?
4. How accurate were forecasts?
5. Do Python, SQL and Excel agree on the same scope, and where they do not, why?

**Intended outputs.** Written cleaning and accounting rules, a cleaned dataset with an exclusion reconciliation, a data-quality and close-control report, a reconciliation log, automated tests, and an interactive dashboard.

**In scope.** Cleaning and validating this one extract, P&L analysis by entity, a separate balance-sheet view where the data allows, and reconciliation across three tools.

**Out of scope.** Conclusions about any real company. Consolidated group results and intercompany eliminations (unresolved). Forecasting models. Tax or statutory reporting. **Month-end close duration and on-time close rate**: the file has no close start or end time, deadline or approval timestamp, so these are not promised. The project focuses on close-control, data-quality and reporting-reliability measures that the data does support.

**Done when**
- Every rule in `docs/FINANCIAL_METRICS.md` is marked Confirmed, or Unresolved with a stated default.
- Every one of the 152,682 raw rows is accounted for: eligible or excluded under exactly one reason.
- The raw file's SHA-256 is unchanged.
- Python, SQL and Excel reconcile on a fixed scope, and every difference is explained.
- The tests in `docs/TEST_PLAN.md` are implemented and pass in CI.
- Dashboard totals match the validated outputs.
- No result is published before the first four points hold.

## What is in the repository

| Path | Purpose |
|---|---|
| `data/raw/fpa_monthly_close_raw_messy.csv` | The raw extract, committed exactly as received. Not edited, not regenerated. 43 columns, 152,682 data rows (counted with a CSV parser). |
| `docs/DATA_DICTIONARY.md` | All 43 columns: observed formats, proposed types, meaning status. |
| `docs/FINANCIAL_METRICS.md` | Candidate formulas and accounting rules, each marked Confirmed, Proposed or Unresolved. No results. |
| `docs/DATA_PROVENANCE.md` | Origin, synthetic-data disclosure, integrity and limits. Unknowns are marked Not recorded. |
| `docs/TEST_PLAN.md` | The tests planned for later stages. Nothing is implemented. |
| `requirements.txt`, `.gitignore` | Environment pins and ignore rules. |

File integrity (SHA-256): `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff`

## Read this before using the raw file

1. **Amounts are text.** Money columns (`amount_local_raw`, `actual_usd_raw`, `budget_usd_raw`, `forecast_usd_raw`, `prior_year_usd_raw` and others) hold mixed formats and placeholders. **Do not sum them as they are.**
2. **Do not add balance-sheet rows to P&L rows.** Balances and flows are different things. The `statement` column labels them, and the labels themselves are inconsistent.
3. **`TOTAL`, `Subtotal` and `TEST ENTITY` rows must not be summed.** They are not postings. Including them double counts or adds junk. The file also has `Do not use` and `xxx` entities (see `docs/FINANCIAL_METRICS.md`).
4. **A repeated `document_no` is not automatically a duplicate journal.** One journal has many lines. A true duplicate needs an agreed rule, and it will be defined and tested before anything is removed.
5. **`report_scale` is dangerous.** Some rows labelled Thousands or Lakhs were really divided, and some labels lie. This is stated by the data owner. First diagnostic evidence is in `docs/FINANCIAL_METRICS.md` section 8, but the rule is still **unresolved**. It will be written down **before any total is published**.
6. **Python, SQL and Excel may disagree.** Differences are investigated and explained. They are not forced to match.

## Planned layout

```
Month-End Close Reliability & Financial Performance Analytics
├── README.md
├── .gitignore
├── requirements.txt
├── data/raw/fpa_monthly_close_raw_messy.csv
├── data/processed/
├── src/
├── sql/
├── tests/
├── dashboard/
├── outputs/
├── docs/DATA_DICTIONARY.md
├── docs/FINANCIAL_METRICS.md
├── docs/DATA_PROVENANCE.md
├── docs/TEST_PLAN.md
└── .github/workflows/
```

## Setup (for later stages)

Python 3.11 or newer.

```
python -m venv .venv
pip install -r requirements.txt
```

## Next stages (not started)

Cleaning rules and code, SQL layer, tests, dashboard, GitHub Actions. See `docs/TEST_PLAN.md`.
