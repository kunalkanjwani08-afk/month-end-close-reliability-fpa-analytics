# Financial Metrics and Accounting Rules

Related: [DATA_DICTIONARY.md](DATA_DICTIONARY.md) (columns), [DATA_PROVENANCE.md](DATA_PROVENANCE.md) (origin), [TEST_PLAN.md](TEST_PLAN.md) (how each rule is tested; not repeated here).

**This document defines candidate metrics and the rules that must be validated before any financial result is published. It contains no financial results.** Counts of rows are shown as evidence for rules; no revenue, profit or variance totals are reported anywhere in the repository yet.

## Status labels

| Label | Meaning |
|---|---|
| **Confirmed** | Stated by the project owner in the brief, or a plain observed fact about the file. Not an accounting judgement. |
| **Proposed—Needs Validation** | A candidate rule supported by some evidence. It becomes Confirmed only after the stated validation passes and the owner agrees. |
| **Unresolved** | The data does not settle it. A decision or source information is needed. Until then the safe default is shown, and affected rows are counted, not silently dropped or guessed. |

A rule being written here does not make it verified.

## 1. Rules register

| ID | Rule | Status | Basis |
|---|---|---|---|
| R1 | Amounts are text. Do not sum raw values. | Confirmed | Owner-stated; all 43 columns are text. |
| R2 | P&L flows and balance-sheet balances are never added together. | Confirmed | Owner-stated. |
| R3 | `TOTAL`, `Subtotal`, `CHECK` rows (identified by `notes` = `subtotal row`, 350 rows) are not postings and are excluded from all calculations. | Confirmed (identification) | All 350 rows carry non-posting labels in `account_name` or `fs_line`; every row with such a label is in the 350. The exclusion principle is owner-stated. |
| R4 | Rows for the junk entities `TEST ENTITY`, `Do not use`, `xxx` (173 rows) are excluded. | Confirmed (owner-stated for TEST ENTITY); Proposed—Needs Validation for the other two names | Not independently confirmed that `Do not use` and `xxx` are non-reporting. |
| R5 | `document_no` is not a unique posting key and repeated numbers are not automatically duplicates. | Confirmed | 4,260 numbers repeat over 8,540 rows; no two rows are identical apart from `row_id`. |
| R6 | Only `approval_status` values with an explicit treatment enter reported totals (section 5). | Proposed—Needs Validation | See section 5. |
| R7 | `report_scale` labels are not trusted; scale is decided per row by a written rule. | Confirmed (labels unreliable, owner-stated); rule itself Unresolved | Section 8. |
| R8 | FX direction is USD = local ÷ rate (local currency per 1 USD). | Proposed—Needs Validation | Section 9. Not final. |
| R9 | Account sign convention. | Unresolved | Section 6. |
| R10 | Variance = Actual − Budget; variance percent uses \|Budget\| as denominator. This is a proposed project convention, not an accounting standard. | Proposed—Needs Validation | Section 2. |
| R14 | Every raw row gets exactly one primary exclusion reason or is eligible, using a fixed precedence. Secondary issues are separate flags. | Proposed—Needs Validation | Section 4. |
| R11 | Duplicate rule for journal lines. | Unresolved | Section 11. |
| R12 | Consolidation and intercompany elimination. | Unresolved | Section 12. |
| R13 | Python, SQL and Excel reconcile on a fixed scope; differences are investigated, not forced. | Confirmed (principle) | Owner-stated; method in TEST_PLAN section 9. |

## 2. Actual versus budget variance

- **Candidate formula:** `variance = actual_usd − budget_usd`. Percent: `variance % = (actual − budget) / |budget|`.
- **Required fields:** `actual_usd_raw`, `budget_usd_raw` (parsed), `legal_entity`, `fiscal_period`, `gl_account`, `statement`, `approval_status`, `report_scale`.
- **Scope:** P&L rows only, eligible rows only (section 4), aggregated first and then compared. Never average row-level percentages.
- **Interpretation:** the sign shows the arithmetic difference. Whether it is good or bad depends on the account type (section 6).
- **Denominator choices and consequences.** The absolute-budget denominator is a **proposed project convention**. It is common in FP&A practice but it is not an accounting standard, and other teams use different bases. The convention must be stated wherever a percent is shown.
  - `|budget|` (proposed convention): stable when actual is volatile and defined whenever a non-zero budget exists. Using the absolute value keeps the sign of the percent equal to the sign of the variance when budget is negative.
  - Signed budget: flips the percent's sign for negative budgets and misleads.
  - Actual: answers a different question (variance relative to outcome), is unstable when actual is near zero, and is rarely used for budget variance.
  - Prior year: this is a year-on-year measure, not budget variance.
  - The chosen proposal must be written on every report that shows a percent.
- **Edge cases:** budget of zero or missing gives percent = null, counted and listed, not zero or infinity. Negative budgets handled by `|budget|`. Placeholders (`NA`, `###`) are treated as missing, not zero. Whether `-` means zero is an open decision (section 15, item 2).
- **Open question (Unresolved):** budget, forecast and prior year sit on every posting row. Whether those values are per-line amounts that can be summed, or repeated header values that cannot, is not known. If they cannot be summed, variance must be computed on a different grain.
- **Validation:** hand-computed examples; aggregated totals reconciled in Python, SQL and Excel (section 13).

## 3. Forecast error and accuracy

- **Candidate formulas:** forecast error `= forecast − actual`. Absolute percent error `= |forecast − actual| / |actual|`. For an aggregate: `WAPE = Σ|forecast − actual| / Σ|actual|`. A related score is `1 − WAPE`. This is a **WAPE-derived score**, not a standard accuracy measure, and the name "accuracy" should not be used for it without that explanation. It **can be negative** when total absolute error exceeds total absolute actuals. It is reported as calculated and is not floored at zero.
- **Scope:** P&L, eligible rows, at a chosen grain (entity, account, period). The grain must be fixed first because errors cancel when summed over larger groups.
- **Interpretation:** WAPE weights large lines more; mean of row percentages weights all lines equally and is dominated by small values.
- **Edge cases:** actual of zero gives an undefined line percent (excluded from the mean, still counted in WAPE); `1 − WAPE` can be negative and must not be floored silently.
- **Status:** Proposed—Needs Validation. Depends on the same open question as section 2 about the grain of forecast values.

## 4. Eligible rows and exclusion-reason precedence (scope gate)

A row enters a reported total only if it passes every step below. To make the row accounting exact, each raw row gets **one primary exclusion reason**: the first step in the list that it fails. Rows that fail none are **eligible**. The order is fixed and deterministic, so the same row always gets the same reason.

For each metric scope: `eligible + Σ rows per primary reason = 152,682`. This identity must hold exactly, and it is a test (TEST_PLAN section 11).

| Order | Primary exclusion reason (row fails this step) | Status |
|---|---|---|
| 1 | Non-posting row (`notes` = `subtotal row`; R3) | Confirmed |
| 2 | Junk entity (`TEST ENTITY`, `Do not use`, `xxx`; R4) | Proposed—Needs Validation |
| 3 | Entity not resolvable (blank or unmapped after name and code mapping) | Proposed—Needs Validation |
| 4 | Out of scope for this metric: balance-sheet row in a P&L metric, or the reverse (R2). Not an error; reported in its own view | Confirmed |
| 5 | Journal status not eligible (section 5). The status value is kept, so `Rejected`, `pending`, `Parked` and blank are separately countable | Proposed—Needs Validation |
| 6 | Period not resolvable to a month | Proposed—Needs Validation |
| 7 | Amount missing or unparsable in the column this metric uses | Proposed—Needs Validation |
| 8 | Scale undecidable (section 8) | Unresolved |
| 9 | Removed as a duplicate (section 11) | Unresolved |

**Why this order.** Structural facts first (is it a posting, whose is it), then scope, then workflow status, then data usability. A row that is both a non-posting row and has a blank status is counted once, as non-posting, because the status of a total row has no meaning. The order is itself a proposal and is validated by the owner with the rest of this document. Steps 8 and 9 stay in the list so that the identity holds once their rules are written.

**Secondary quality issues are not reasons.** Problems that do not by themselves exclude a row are recorded as separate yes/no flags and are never used to assign the primary reason. Examples: whitespace or case variants fixed by cleaning, blank cost centre or region, placeholder `qty_raw`, missing or zero FX rate, unexplained negative sign, `scenario_tag` noise, duplicate-candidate flag, and a missing amount in a column the metric does not use (for example a missing budget when only actuals are summed). Each flag is counted over **all** rows, and also split by primary reason, so a reader can see both "how many rows have this problem" and "how many of those rows were also excluded". Flag counts are overlapping and are not meant to add up to 152,682.

**Metric-level note.** Step 7 depends on the amount column. A variance needs both actual and budget; a row missing only the budget is excluded from variance with step 7 for that metric but stays eligible for an actual-only total. Each metric therefore has its own reconciliation of eligible plus exclusions.

## 5. Journal status

Observed `approval_status`: `Posted` 65,381 (42.8% of rows), `pending` 22,072, `Rejected` 21,795, `Parked` 21,650, empty 21,784. There is no `Approved` value. The statuses are **not** treated identically.

| Value | Proposed treatment | Status |
|---|---|---|
| `Posted` | Eligible for reported totals | Proposed—Needs Validation |
| `Rejected` | Excluded from reported totals and from any pipeline view | Proposed—Needs Validation |
| `pending` | Excluded from reported totals. Counted and reported as unposted items in the close-control view | Proposed—Needs Validation |
| `Parked` | Same as `pending`. A parked journal is held, not rejected, so keep it separate from `Rejected` | Proposed—Needs Validation |
| empty | Excluded from reported totals until the owner decides what blank means. Counted as its own category | Unresolved |

Consequence: with this proposal only about 43% of rows could enter reported totals. That is large enough that the proportion itself must be confirmed as intended before any total is published. The status mix is nearly identical for every entity (Posted 42.5% to 43.2%, each other value about 14%) and for P&L and balance-sheet rows. A real posting workflow would rarely look this uniform, so the statuses may be generated noise. That is an observation to investigate, not a conclusion.

## 6. Account signs and favourable or unfavourable variance

Observed on rows labelled `Actual` scale (parsable, non-zero `actual_usd_raw`):

| Account | Negative values | Median |
|---|---|---|
| 4100 Product sales | 7.4% | positive (11,151) |
| 4190 Sales discounts and rebates | 57.8% | negative (−269) |
| 5100 Materials | 13.5% | positive (4,532) |
| 5120 Purchase price variance | 31.7% | positive (3,493) |
| 6xxx operating expenses (typical) | 13% to 15% | positive |
| 7200 FX gain or loss | 50.4% | −8 |
| 1xxx and 2xxx balance sheet (typical) | about 7% | positive for assets and liabilities alike |

- **Reading:** revenue, costs and balances look like positive magnitudes with a minority of negatives, not Dr/Cr signed values. Discounts and FX gain/loss are mixed. Whether negatives are credits, reversals or noise is not known.
- **Candidate convention (Proposed—Needs Validation):** treat revenue and costs as positive magnitudes. Profit measures subtract costs from revenue; they never add rows blindly. Variance interpretation: for revenue and profit accounts, positive variance is favourable; for cost accounts, positive variance is unfavourable. Discounts (4190) and FX (7200) need an explicit decision. **Unresolved.**
- **Edge cases:** negative values are not errors by default (credits, reversals). Balance-sheet balances are not netted without an asset/liability mapping.
- **Validation:** a per-account sign table reviewed by the owner before use, then tested against fixtures.

## 7. P&L versus balance sheet

- **Rule (Confirmed):** the two are separate. P&L amounts are flows over a period and can be summed across periods. Balance-sheet amounts are balances at a point in time and **cannot be summed across periods**.
- **Identification (Proposed—Needs Validation):** normalise the ten `statement` labels to two. Cross-checks that agree: `Working capital` account group appears only on balance-sheet labelled rows; every 1xxx/2xxx account is balance-sheet labelled; no 4xxx to 8xxx account is.
- **Unresolved:** whether a balance-sheet line is an opening, closing or movement amount. Without that, balance-sheet trends are not computed.
- **Trends:** P&L trends by period, entity, division and account only; balance-sheet shown separately as period snapshots once the above is answered.

## 8. Reporting-scale normalisation

Owner-stated: some `Thousands` and `Lakhs` rows really were divided, and some labels lie. Evidence on one account (4100 Product sales, `actual_usd_raw`, parsable and non-zero), as a diagnostic only:

| Label | Rows | Under 100 | 100 to 1,000 | 1,000 and above |
|---|---|---|---|---|
| `Actual` | 23,631 | 0.3% | 2.8% | 96.9% |
| `Thousands` | 977 | 84.7% | 1.0% | 14.2% |
| `000s` | 159 | 0.0% | 4.4% | 95.6% |
| `In thousands` | 151 | 0.7% | 4.0% | 95.4% |
| `Lakhs` | 164 | 100% | 0% | 0% |
| empty | 0 | – | – | – |

- **Reading:** `Thousands` and `Lakhs` rows are mostly small, as if divided. `000s` and `In thousands` rows look undivided (like `Actual`), so those labels disagree with the magnitude. Even `Thousands` has 14.2% of rows at full size.
- **Status: Unresolved.** One account and one column were checked. `amount_local_raw`, budget, forecast and prior-year columns, other accounts, and empty-label rows were not. A multiplier from the label alone (×1,000 for `Thousands`, ×100,000 for `Lakhs`) would be wrong for the mismatched rows.
- **Proposal:** decide scale per row by comparing magnitude with the typical magnitude for the same account and entity, keep both the label and the decision, and write the rule before any total is published. Flag rows where the decision is not clear.
- **Validation:** fixtures with known divided and undivided rows; count of rows whose label and magnitude disagree reported as a control metric.

## 9. Foreign-exchange conversion

`actual_usd_raw` is already provided in USD, so conversion is not needed to build the reported figure. FX is used mainly to cross-check `amount_local_raw` and to flag disagreement.

- **Candidate direction (Proposed—Needs Validation):** `usd = local ÷ rate`, rate being local currency per 1 USD.
- **Evidence:** among 125,699 rows where local amount, rate and actual USD all parse, are non-zero and rate is above zero, `local ÷ rate` is within 2% (or 1 USD) of `actual_usd` in 109,581 rows (87.2%). `local × rate` fits 12,586 rows (10.0%). The remaining rows do not fit either, possibly because of scale or parsing issues. The two counts were not de-duplicated, so overlap is possible.
- **Unresolved items:**
  - 2,517 rows have rate `0`. A zero rate is invalid and cannot convert. Do not default to 1.
  - 7,743 rows have a rate of `NA`, `-` or empty.
  - Rows with USD currency carry rates other than 1 (for example `1.001498`), and for USD rows local equals USD in only 12,568 of 22,364 comparable rows. This is unexplained.
  - Whether the rate is period-average or spot is unknown.
- **Do not finalise** the formula until these are understood.
- **Validation:** direction tested both ways on fixtures; disagreement count reported as a control metric.

## 10. Missing values

- A value that cannot be parsed is **missing**, not zero, until the owner decides whether `-` means zero.
- Required for reported totals: entity, period, GL account, statement, amount in the relevant column, approval status. If any is missing the row is excluded and counted.
- Allowed to be blank: `cost_center_*` on non-cost-centre lines, `product_family`, `customer_segment`, `channel`, `qty_raw`, `uom`, `headcount_fte_raw`, `region` (derivable), `notes`. All are Proposed—Needs Validation.
- 3,101 rows have no `gl_account` and are not flagged non-posting. Whether they can be recovered from `account_name` or `fs_line` is Unresolved.

## 11. Duplicate journal lines

- **Observed:** zero pairs of rows are identical in every column except `row_id`. Removing `row_id`, `extract_batch`, `source_system`, `user_id`, `notes` and `scenario_tag` also finds zero.
- **Candidates only:** matching on `document_no`, `gl_account`, `actual_usd_raw` and normalised `entity_code` finds 1,104 pairs (2,208 rows). These are candidates for review, not duplicates: a journal can legitimately post the same amount to the same account twice.
- **Proposal:** (1) exact duplicates on all business fields after cleaning are removed; (2) candidate pairs are compared on `posting_date`, `line_text`, `user_id`, `fs_line` and cost centre and removed only if a written key says so; (3) everything else stays. Counts of kept, removed and flagged rows must reconcile.
- **Status:** Unresolved. No row is removed until a key is agreed.

## 12. Intercompany and consolidation

About 5,761 rows are flagged intercompany (after normalising spellings), 24,494 are blank, and `elimination_status` is mostly blank or `N/A`. Whether eliminations are already in the data is unknown, so consolidated group totals are **Unresolved**. Until then, report by legal entity, not consolidated.

## 13. Reconciliation across Python, SQL and Excel

- **Rule (Confirmed principle):** fix one scope in writing, compute it independently in each tool, and investigate every difference. Do not adjust one tool to match another.
- **Candidate scope for the first reconciliation:** one entity, one period, P&L, eligible rows. Totals compared to the cent, with the row count compared first.
- **Known sources of legitimate disagreement:** text-to-number parsing, rounding, treatment of empty strings versus nulls, case and whitespace in joins, and integer or float arithmetic.
- **Method and tests:** [TEST_PLAN.md](TEST_PLAN.md) section 9.

## 14. Metrics the data supports, and those it does not

| Supported by the data | Not supported |
|---|---|
| Data-quality and control measures: share of rows by approval status, non-posting rows, unmapped entities, unparsable amounts, label-versus-magnitude scale disagreements, duplicate candidates, missing required fields, reconciliation differences | Month-end close duration and on-time close rate. There is no close start or end time, no deadline and no approval timestamp. `posting_date` is a posting date with 7,681 blanks and four formats, and `extract_batch` is a label without a date. |
| Actual versus budget, forecast and prior year, once sections 4, 5, 8 and 9 are settled | Consolidated group results (section 12) |
| Trends by period, entity, division and account for P&L | Balance-sheet movement trends (section 7) |

## 15. Remaining decisions for the owner

1. Meaning of blank `approval_status`, and whether about 43% eligible rows is intended.
2. Whether `-` in an amount means zero.
3. Sign treatment of discounts (4190) and FX gain or loss (7200).
4. The scale rule, after checking all amount columns.
5. FX direction and the 2,517 zero-rate rows.
6. Whether budget, forecast and prior year are summable per line.
7. The duplicate key.
8. Whether results are by entity or consolidated.
