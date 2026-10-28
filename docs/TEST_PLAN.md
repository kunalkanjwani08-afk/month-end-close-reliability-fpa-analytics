# Test Plan

**Status: plan only. No test is implemented in this commit.**
Each section says what will be tested and how. Rules named here (cleaning, duplicates, scale, signs) are written down **before** the code that applies them, and the tests check the code against those written rules, not against the code's own output.

Data: `data/raw/fpa_monthly_close_raw_messy.csv` (synthetic, 43 columns, 152,682 data rows).

## 1. Schema validation
- **What:** all 43 expected columns exist, with expected names and order; each column has an expected type once cleaned; required fields are named.
- **How:** a schema file lists column, type and required flag. A test loads the raw file as text and compares the header exactly. After cleaning, a second test checks types. A file with a missing, renamed or extra column must fail with a clear message.

## 2. Data cleaning
- **What:** messy dates, currency amounts, placeholders (`#N/A`, `NA`, `n/a`, `null`, `-`, `###`, blank), inconsistent labels (entity, division, statement, cost center code).
- **How:** the rules are written in a cleaning-rules document first. A table of input and expected-output pairs covers every format seen, for example `$ 1,234.56`, `(1,234.56)`, `1.234,5`. Ambiguous values (a date such as 03/04/2024 where day and month could swap) are tested against the written rule, and rows the rule cannot resolve must be flagged, not guessed.

## 3. Duplicate records
- **What:** a true duplicate versus legitimate journal lines that share a `document_no`.
- **How:** the duplicate key is defined in writing. Controlled fixtures contain (a) an exact repeat that must be removed, (b) two lines of one journal that must both stay, (c) a near-duplicate that must be flagged for review. Row counts before and after are reconciled: kept + removed + flagged = input.

## 4. Missing values
- **What:** required fields must be present. Blanks are allowed where the field does not apply (for example a cost center on a balance-sheet line).
- **How:** each column is marked required, conditional or optional in the schema. Tests count missing values in required fields after cleaning (expected: zero, or each one listed with a reason), and confirm conditional blanks match their stated condition.

## 5. Financial calculations
- **What:** actual-versus-budget variance, variance percent, forecast error, and currency conversion **only where the data supports it**.
- **How:** hand-computed examples with known answers. Variance percent with a zero budget must return a defined result, not a crash or infinity. FX direction is fixed in writing (USD = local ÷ rate, rate in local currency per USD, to be confirmed against the data) and tested both ways. Rows with a zero or missing rate are not converted and are counted.

## 6. Accounting business rules
- **What:** account signs, reporting periods, journal status, reporting scale. P&L and balance sheet stay separate.
- **How:** a sign convention is written per account group and checked on fixtures. `fiscal_period` must map to exactly one calendar month. Only journals with an eligible approval status (the file has no `Approved` value; see FINANCIAL_METRICS.md section 5) enter reported totals, per a written rule. `report_scale` handling is tested on rows where the label and the real magnitude disagree, using the written rule. Tests assert that no total mixes statement types.

## 7. Referential integrity
- **What:** entity, account, cost center and other mapped dimensions.
- **How:** only where a map is defined. Each map is a reference table. A test finds values with no match (for example junk entities, `TEST ENTITY`, retired codes) and checks they are excluded or flagged by rule. Where no map exists, no test is written and the gap is documented.

## 8. Edge cases
- **What:** negative amounts, zero exchange rates, extremely large values, invalid dates, an empty file, conflicting identifiers.
- **How:** small fixtures, one per case. The code must either handle the case by rule or fail loudly. An empty file must give a clear error, not an empty report. Conflicting identifiers (one `row_id` on two different rows) must be reported.

## 9. Financial reconciliation
- **What:** the same scope computed in Python, SQL and Excel.
- **How:** one scope is fixed in writing (for example one entity, one month, one statement type). Each tool produces its total independently. Differences are **investigated and explained**, never forced to match. A reconciliation note records each difference and its cause.

## 10. SQL integration
- **What:** tables, joins, aggregations and views.
- **How:** load a small controlled example into the database, run each view and query, and compare with hand-computed results. Join tests check that a join does not multiply rows.

## 11. End to end
- **What:** raw file through cleaning, SQL and dashboard outputs.
- **How:** run the whole pipeline on the real raw file. Check row-count reconciliation at every step, and that final totals trace back to the cleaned data.

## 12. Dashboard
- **What:** KPI math, filters, date selections, displayed totals against validated results.
- **How:** compare each displayed KPI with the validated output from section 9. Apply each filter and date range and check totals against an independent calculation. Check that filters never combine P&L and balance-sheet rows.

## Regression
After any code change, rerun every test that already passed. A previously passing test that fails is investigated before new work continues.

## CI
GitHub Actions will run the full suite on every push and every pull request. **Not included in this commit.** The workflow file is added at a later stage.
