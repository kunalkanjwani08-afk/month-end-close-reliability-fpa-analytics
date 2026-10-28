# Month-End Close Reliability & Financial Performance Analytics

> **Status: Stage 0. This commit contains only the raw extract and the folder chart.**
> There is no cleaning code, SQL, test, dashboard or CI workflow yet. Folders marked `.gitkeep` are empty on purpose.

All data is **synthetic**. It is not a real company's financials.

## What this project will become

A month-end close and financial-performance analysis for a fictional group, **NovaBridge Industries**, covering **January 2023 to December 2025**.

- Six legal entities and five divisions.
- Each row is a **posting** (one journal line), not a summary.
- P&L flows and balance-sheet balances sit in the **same** extract.
- Actual, budget, forecast and prior year are **separate columns**.
- `scenario_tag` is noise. It is not a reliable scenario selector.

## What is in this commit

| Path | Purpose |
|---|---|
| `data/raw/fpa_monthly_close_raw_messy.csv` | The raw extract, committed exactly as received. Not edited, not regenerated. 43 columns, 152,682 data rows (counted with a CSV parser). |
| `docs/TEST_PLAN.md` | The tests planned for later stages. Nothing is implemented. |
| `requirements.txt`, `.gitignore` | Environment pins and ignore rules. |

File integrity (SHA-256): `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff`

## Read this before using the raw file

1. **Amounts are text.** Money columns (`amount_local_raw`, `actual_usd_raw`, `budget_usd_raw`, `forecast_usd_raw`, `prior_year_usd_raw` and others) hold mixed formats and placeholders. **Do not sum them as they are.**
2. **Do not add balance-sheet rows to P&L rows.** Balances and flows are different things. The `statement` column labels them, and the labels themselves are inconsistent.
3. **`TOTAL`, `Subtotal` and `TEST ENTITY` rows must not be summed.** They are not postings. Including them double counts or adds junk.
4. **A repeated `document_no` is not automatically a duplicate journal.** One journal has many lines. A true duplicate needs an agreed rule, and it will be defined and tested before anything is removed.
5. **`report_scale` is dangerous.** Some rows labelled Thousands or Lakhs were really divided, and some labels lie. This is stated by the data owner and has **not yet been measured** here. The cleaning rule will be written down **before any total is published**.
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
