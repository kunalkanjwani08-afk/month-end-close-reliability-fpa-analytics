# Phase 4 - SQL, Financial Analysis and Evidence-Based FP&A Insights: Analysis Report

Data: NovaBridge Industries - a **synthetic, fictional** group (provenance and licence unverified; results are not facts about a real company). Local only; nothing is committed or published.

## 1. Verified input

- File: `data/processed/fpa_monthly_close_cleaned.csv` (Phase 3 canonical output; the 77-column workbook sheet is not used).
- Gate (src/phase4_pipeline.py `verify_input`): exists and non-empty; SHA-256 `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47`; 174,545,248 bytes; 152,682 data rows; 192 unique columns; header fingerprint; 32 required fields present. A mismatch stops the run (exit 1 for a missing/unreadable file, exit 2 for an integrity mismatch) without touching an existing database.
- The raw file and the canonical CSV are never modified; the run writes only the database and `outputs/phase4/`.

## 2. Financial meaning established before calculating

| Question | Answer used in this phase | Evidence |
|---|---|---|
| What is one row? | One journal line (posting). 350 non-posting TOTAL/Subtotal/CHECK label rows remain in the CSV for traceability and are in no population. | out_a0, L29-L30 |
| Grain | entity x period x GL x journal line; 4,210 of 4,907 populated entity x period x GL cells have several lines, so the lines are treated as separate postings that add up; `document_no` is not a line key. Pattern evidence only: in 4,201 multi-row cells the actual amounts differ between lines (out_a0); this is consistent with per-line amounts but is not proof of additivity, which rests on the business meaning (one row = one journal line) and the reconciliations in section 5. | out_a0 |
| Actual / budget / forecast / prior year | Four attributes of the **same line**, not separate records. Budget, forecast and PY are compared with actual on the same line; they are not independent observations. | schema |
| P&L vs Balance Sheet | Separate populations (`v_pl_actual`, `v_bs_actual`). Balance Sheet lines are treated as statement lines with an UNRESOLVED measurement basis (opening, closing or movement is not established); they are never summed across periods and no cash-flow or working-capital metric is built. | L25-L26, out_h6 |
| Populations | P&L actual 58,340 lines; P&L vs budget 55,043; Balance Sheet 2,953. Forecast and prior-year populations = P&L actual with that column present (project convention). | L21-L23 |
| Eligibility flags | Used after verifying: `eligible_PL_variance` = `eligible_PL_actual` AND budget present; Posted subset of the any-status view equals the eligible set; exclusion reasons add up to 152,682 per scope. | L24, L27, L33-L36 |
| Reported vs parsed vs adjusted | `*_usd_parsed` = parsed from the source text without scale restoration; `*_usd_adj` = scale-adjusted (provisional). Never mixed in one measure. Scenario names say which is used: `ALL_LINES` = scale-adjusted amounts with signs as recorded (not the unadjusted parsed amounts); `AS_REPORTED_PARSED (no restoration)` = parsed amounts. | out_i1 |
| Reliable dimensions | division and region 100% filled; cost centre 95%-96%; product family, channel, customer segment partly blank (blank bucket kept); quantity and unit of measure unsuitable for aggregation. | out_a5 |
| Period coverage | 2023-01 to 2025-12: 36 periods, 0 entity-period gaps. | out_a7 |

Carried-forward limitations: the 6,265 scale restorations (1,814 HIGH / 4,451 MEDIUM) and 73 undetermined lines (INS-07); duplicate **candidates** are kept and never excluded in the baseline; FX has 2,517 zero rates and is not repaired; signs are never flipped; the journal-status rule is provisional; unit of measure is unresolved; no close-duration metric exists in the data and none is invented.

## 3. Method and conventions

- DuckDB 2.0 database `data/processed/phase4_fpa.duckdb` (local, git-ignored): `stg_close_raw` (parsed source field values held as text; byte-level integrity rests on the CSV SHA-256, not on this table), `fact_close` (typed, 192 columns, 152,682 rows), `dim_account` (one-to-one account mapping verified for 32 of 32 GL accounts, out_a8 and L49/L52-L55), and 72 `out_*` result tables. Numbered SQL files in `sql/phase4/` are commented and re-runnable.
- Variance = Actual - Budget. Percentage = variance / ABS(net budget), published only when |net budget| >= 50% of gross budget (otherwise NULL); zero or missing budgets give NULL. Net and gross are always shown; contribution shares are suppressed when the section net is below 5% of gross.
- Forecast error = Forecast - Actual; bias = sum(F-A)/sum|A|; WAPE = sum|F-A|/sum|A|. MAPE is not used. **Limitation:** the extract has no forecast version or date, so forecast skill cannot be separated from a late re-forecast.
- Costs are positive magnitudes: a positive cost variance means spend above budget. No favourable/unfavourable label is attached because the sign convention is not validated.
- Sign categories (actual vs budget / forecast / prior year): SAME_SIGN_NONZERO, OPPOSITE_SIGN_NONZERO, ZERO_INVOLVED (either amount exactly 0, including both zero) and MISSING_OR_UNAVAILABLE (either amount missing; empty in the populations used). Scenarios: ALL_LINES (scale-adjusted amounts, signs as recorded), SAME_SIGN_ONLY, OPPOSITE_SIGN_ONLY, ZERO_INVOLVED_ONLY - rows are filtered, signs are never flipped, and ALL_LINES = the three categories exactly. An opposite-sign line is an observation, not a confirmed error; account-level sign conventions are not verified.
- Project conventions (labelled, not standards): 50% net-budget guard; 5% suppression; |robust z| >= 3 for the anomaly scan; 90% dominant-direction share and 3% variance for 'persistent'; no accounting materiality standard is applied: cell importance is shown as two labelled sensitivities instead of one fixed threshold - contribution to total absolute cell variance (0.25%-5%, `out_b9`) and variance as a percentage of the cell's gross budget (0.5%-10%, `out_b11`).

## 4. Questions investigated and what was found

### A. Performance overview

| Section | Lines | Actual (signed) | Absolute activity |
|---|---|---|---|
| REVENUE | 32,813 | $202.65M | $254.53M |
| COGS | 12,198 | $92.81M | $128.00M |
| PEOPLE | 3,285 | $39.71M | $54.89M |
| OPEX | 8,645 | $43.81M | $60.72M |
| D&A | 345 | $1.84M | $2.43M |
| BELOW_EBITDA | 697 | $0.60M | $1.08M |
| TAX | 357 | $2.75M | $3.79M |

| Entity | Legal entity | Lines | Revenue | COGS | People | Opex |
|---|---|---|---|---|---|---|
| AE01 | NovaBridge MENA FZE | 9,634 | $21.15M | $8.73M | $3.80M | $4.37M |
| DE01 | NovaBridge Europe GmbH | 9,772 | $29.55M | $15.10M | $6.72M | $6.78M |
| GB01 | NovaBridge UK Ltd | 9,882 | $20.50M | $9.75M | $4.21M | $4.33M |
| IN01 | NovaBridge India Pvt Ltd | 9,692 | $48.35M | $21.65M | $9.13M | $10.00M |
| SG01 | NovaBridge APAC Pte Ltd | 9,706 | $27.76M | $13.58M | $6.13M | $6.52M |
| US01 | NovaBridge Americas Inc | 9,654 | $55.34M | $24.00M | $9.71M | $11.80M |

The same breakdown by division, GL account, account group, FS line and period is in `out_a1` - `out_a4` (shares of section activity included); period coverage grid in `out_a6`.

Every entity has data in every one of the 36 months (0 gaps; 232-325 eligible lines per entity-month), so period comparisons are not distorted by missing months. The Posted-only rule retains 42.8% of the P&L lines, so all totals are 'Posted lines only'.

### B. Actual vs budget (same-sign non-zero lines; all lines in brackets)

| Section | Actual | Budget | Variance | Variance % | Net/gross budget |
|---|---|---|---|---|---|
| REVENUE | $190.40M | $197.42M | -$7.02M (-$4.67M) | -3.6% (-2.4%) | 0.97 |
| COGS | $87.80M | $82.51M | $5.30M ($4.81M) | +6.4% (+5.8%) | 0.96 |
| PEOPLE | $38.26M | $35.97M | $2.29M ($0.04M) | +6.4% (+0.1%) | 0.99 |
| OPEX | $41.46M | $38.96M | $2.50M ($1.92M) | +6.4% (+4.9%) | 0.98 |
| D&A | $1.74M | $1.64M | $0.10M ($0.14M) | +6.3% (+8.7%) | 0.93 |
| BELOW_EBITDA | $0.53M | $0.49M | $0.03M ($0.06M) | +6.3% (+12.1%) | 0.68 |
| TAX | $2.81M | $2.65M | $0.17M (-$0.04M) | +6.3% (-1.3%) | 0.93 |

The variance is uniform across entity, division, GL and month (INS-03). Largest single cells (same-sign): COGS US01/5100 Materials $1.01M (+6.4%); OPEX US01/6220 Warehouse and distribution $0.15M (+6.3%); PEOPLE US01/6100 Salaries $0.38M (+6.4%); REVENUE US01/4100 Product sales -$1.64M (-3.5%). Sensitivity: 8 of the top-10 entity x GL cells are the same under the all-lines and same-sign views. Contribution sweep (same-sign; share of TOTAL absolute cell variance, not % of budget): cells contributing >= 0.25% -> 69 cells covering 91%; cells contributing >= 0.50% -> 38 cells covering 80%; cells contributing >= 1.00% -> 19 cells covering 67%; cells contributing >= 2.00% -> 14 cells covering 60%; cells contributing >= 5.00% -> 3 cells covering 23%. Budget-percentage sweep (same-sign; cell variance as % of the cell's gross budget): |variance| >= 0.5% of gross budget -> 138 of 144 cells; |variance| >= 1.0% of gross budget -> 133 of 144 cells; |variance| >= 2.0% of gross budget -> 130 of 144 cells; |variance| >= 5.0% of gross budget -> 86 of 144 cells; |variance| >= 10.0% of gross budget -> 0 of 144 cells. Both are project analytical conventions, not accounting materiality standards.

Robustness of the revenue and cost variance direction across the exposure scenarios (`out_i3`):

| Scenario | Revenue var. | COGS var. | People var. | Opex var. |
|---|---|---|---|---|
| all statuses | -$15.02M | $14.21M | $2.77M | $5.79M |
| all statuses + same-sign rows only | -$16.50M | $12.53M | $5.46M | $5.87M |
| baseline (Posted, scale-adjusted, signs as recorded) | -$4.67M | $4.81M | $0.04M | $1.92M |
| exclude duplicate candidates | -$4.43M | $4.84M | -$0.01M | $1.95M |
| exclude restored rows | -$5.00M | $4.56M | $0.23M | $1.91M |
| parsed amounts, no scale restoration | -$5.00M | $4.56M | $0.23M | $1.91M |
| same-sign rows only | -$7.02M | $5.30M | $2.29M | $2.50M |

Revenue is below budget and COGS and opex above budget in every scenario. People cost is not robust: its variance ranges from -$0.01M to $5.46M across the scenarios (INS-02).

### C. Forecast bias, error, persistence and trend

| Section | Bias (forecast vs actual) | WAPE forecast | WAPE budget | Quarters bias on same side |
|---|---|---|---|---|
| REVENUE | +1.6% | 2.6% | 3.7% | 12 of 12 |
| COGS | -2.5% | 3.4% | 6.0% | 12 of 12 |
| PEOPLE | -2.5% | 3.3% | 6.1% | 12 of 12 |
| OPEX | -2.6% | 3.5% | 6.1% | 12 of 12 |

Details and caveats in INS-02 and INS-05 (no forecast version or timing).

### D. Prior year

The prior-year **column** implies growth of +7.8% mean (entity range +6.1% to +8.2%, SD 0.39 points): a near-uniform step-up. It does not reconcile with the dataset's own prior-year actuals: revenue prior-year column for 2025 is $60.94M vs $70.36M actual for 2024 (-13.4%; both on the Posted population, so sign and status effects cannot be separated). True year-on-year revenue growth depends on the basis: Posted signed +14.8% (2024) and +0.9% (2025); all statuses, absolute +6.3% and +5.7%. 2023 has no prior calendar year in the file, so its growth is NULL. Small-baseline cells (baseline below 5% of the GL median) are listed in `out_d5` and excluded from any % statement.

### E. Revenue, COGS and gross profit

Classification validated (4100, 4110, 4120, 4190 = revenue; 5100-5300 = COGS). Three discount treatments and two row sets are shown; see INS-04. Gross margin by year (S1, all rows): 2023 53.0%, 2024 57.0%, 2025 52.5%. Unit margins by product family are **not** computed: the materials value per unit equals the sales value per unit in all 5 families (max difference 0.0000), i.e. a zero unit margin that is a data property, not economics. Materials / product sales = 44.6% (an indicator, not a margin).

### F. Cost structure and concentration

| GL | Account | Section | Absolute activity | Share | Cumulative |
|---|---|---|---|---|---|
| 5100 | Materials | COGS | $90.6M | 36.8% | 37% |
| 6100 | Salaries | PEOPLE | $38.9M | 15.8% | 53% |
| 5200 | Direct labor | COGS | $15.7M | 6.4% | 59% |
| 6220 | Warehouse and distribution | OPEX | $14.0M | 5.7% | 65% |
| 6210 | Marketing programs | OPEX | $11.9M | 4.9% | 70% |
| 5300 | Factory overhead | COGS | $11.3M | 4.6% | 74% |
| 6230 | Rent and facilities | OPEX | $10.5M | 4.3% | 78% |
| 6120 | Benefits | PEOPLE | $9.4M | 3.8% | 82% |

Concentration against the equal-share benchmark: cost_center (opex+people) - top member CC410 18% (equal share 12%), HHI 0.14; division - top member Consumer Durables 36% (equal share 20%), HHI 0.27; gl_account - top member 5100 37% (equal share 6%), HHI 0.18; legal_entity - top member US01 26% (equal share 17%), HHI 0.19. Materials (5100) is the largest line, but a high share is not called inefficiency: no driver beyond the salary-rate finding (INS-06) is available. Cost-to-revenue (absolute basis, 3 years): COGS 50.3%, people 21.6%, opex 23.9%; by year COGS 2023 51.2%, 2024 49.3%, 2025 50.5%. Persistent deviators: 112 of 144 entity x GL cells sit on the same side of budget in at least 90% of months, and 112 of them also exceed 3% (a consequence of the uniform pattern in INS-03).

### G. Trend, volatility and persistence

Revenue shows a seasonal shape (calendar-month index, 3 years pooled): 1: 0.89, 2: 0.93, 3: 0.99, 4: 1.02, 5: 1.08, 6: 1.12, 7: 1.11, 8: 1.05, 9: 0.99, 10: 0.95, 11: 0.94, 12: 0.93. Half-year growth (all statuses, absolute): 2024 H1 +6.7%; 2024 H2 +5.9%; 2025 H1 +5.6%; 2025 H2 +5.8%. The apparent slowdown in 2025 on the Posted-signed basis is a basis artefact (rejected finding R1). Anomaly scan over 864 entity x section months: within range: 860, amount unusual with normal row count - review lines: 3, coverage-driven (row count also unusual): 1 - close to what a |z| >= 3 rule flags by chance, so no month is called an anomaly (R5).

### H. Balance Sheet statement lines - measurement basis unresolved (no movement or working-capital metrics)

Coverage 86% of 1,728 entity x account x period cells; 64% of populated cells hold several lines (up to 6) whose sizes differ widely (median max/min 1.9x for 2 lines, 12.7x for 6). Per-account coefficient of variation 0.27-0.49, with 2 negative period totals. Lines do not behave like additive balances, so DSO, DPO, working capital and balance movements are not computed (R3; reasons in `out_h6`).

### I. Data-quality exposure scenarios (sensitivities, never the official answer)

Ranges are measured across the BASELINE and POLICY_SCENARIO rows of each factor only; single-status buckets are partition diagnostics and are not ranked (see INS-01).

| Factor | Scenarios ranked | Revenue range / baseline | Result-proxy range / baseline | Result proxy low | Result proxy high |
|---|---|---|---|---|---|
| status | 3 | 133% | 105% | $26.32M | $53.88M |
| sign | 3 | 19% | 56% | $11.62M | $26.32M |
| scale | 5 | 4% | 15% | $25.51M | $29.44M |
| duplicates | 3 | 1% | 1% | $26.16M | $26.48M |

Duplicate candidates are retained in every baseline. In the eligible population 363 lines are same-sign candidates and 235 sign-conflict candidates (0.9% of absolute value). Exact full-row duplicates are defined as lines identical in all 42 original source fields (every source column except the derived `row_id`; raw text compared strictly, NULL and blank treated as the same missing value, case and spacing as in the cleaned CSV): none exist. The Phase 3 candidate tiers are weaker: they match on document number, entity, GL, period and amount fields only ( 18 lines share document, entity, GL and all five amount texts). Excluding them as a labelled sensitivity changes revenue by 0.8%: not material (R6). FX and sign flags on the eligible population: 15% of lines (and 24% of absolute value) are USD-currency lines whose rate is not 1; 1.6% have a zero rate. These are not repaired (open question Q4).

## 5. Validation

| Suite | Checks | Passed | Failed |
|---|---|---|---|
| Load, population and rule checks (out_val_load) | 55 | 55 | 0 |
| Exclusion counts vs Phase 3 report (out_val_exclusion_counts) | 24 | 24 | 0 |
| Analytical reconciliations (out_val_analytical) | 86 | 86 | 0 |
| Independent pandas cross-check from the CSV (out_val_crosscheck) | 124 | 124 | 0 |

Largest absolute difference in any money reconciliation (SQL checks and pandas cross-check) is USD 0.000006 (tolerance USD 0.01); the largest ratio difference is 3.9e-14 (tolerance 1e-9). Checks have expected, actual, difference, tolerance and status in `outputs/phase4/val_*.csv`. The pytest suite (`tests/test_phase4.py`) includes mutation tests that corrupt the data or a published number and require the relevant checks to fail, so the checks are shown to be able to fail. A failing check stops the pipeline before the database is promoted. Repeat runs produce byte-identical outputs (single-threaded aggregation; `MANIFEST.json`; tested in `test_second_run_is_byte_identical`). Output promotion is staged: the accepted database, CSVs and manifest change only when every check passes (`finalize` in `src/phase4_pipeline.py`; tested with sentinel files).

## 6. Strongest validated insights

| ID | Insight | Confidence |
|---|---|---|
| INS-01 | The journal-status rule is the largest swing factor in the revenue and result headlines among the four assumptions tested (status, scale, sign, duplicates) | High that the dependency exists (arithmetic, reconciled). |
| INS-02 | Lines whose forecast and actual have opposite signs (10% to 13% of lines) carry 89% to 91% of the absolute forecast error; whether they are data defects or legitimate entries is unresolved | High on the arithmetic and on its independent recomputation. |
| INS-03 | Actuals sit a near-constant 3.6% below budget on revenue and 6.4% above budget on costs on same-sign lines in all 36 months, all 6 entities, all 5 divisions and every one of the 20 operating accounts (the all-lines view differs) | High on the numbers; Medium-Low on any business reading. |
| INS-04 | Gross profit is $12.3M below budget on same-sign lines: 57% of the gap is revenue below budget and 43% is COGS above budget; the margin gap holds under all three discount treatments | Medium. |
| INS-05 | On a matched same-sign subset the forecast is closer to actuals than the budget; on all comparable lines the margin is 26.8% vs 29.3% revenue WAPE (forecast vs budget) and reverses for people costs, and neither view establishes forecast skill | Medium for the arithmetic of each population; Low for any statement that the forecast is better than the budget in general: the populations give different margins, and the lack of version/timing prevents any conclusion about forecasting skill. |
| INS-06 | Salary lines carry a near-constant rate per FTE within each entity; without a budgeted FTE plan and the budget's rate method, the people-cost variance cannot be split into rate and volume | Medium for the rate pattern (data property); Low for the FTE-month figures (conditional on the stated assumptions). |
| INS-07 | Scale restoration moves the result proxy by $3.1M, and the larger (MEDIUM-confidence) tier cannot be verified against price | High for the HIGH tier consistency; Low for the MEDIUM tier. |

Full 14-element entries are in `docs/PHASE4_INSIGHT_REGISTER.md`.

## 7. Findings tested and rejected

- **R1 - '2025 growth slowdown'.** Posted-signed revenue growth falls from +14.8% to +0.9%, but the all-status absolute basis gives +6.3% and +5.7% and half-year growth is stable on that basis. The slowdown depends on the status and sign basis; rejected as an insight.
- **R2 - Unit margin by product family.** Materials and sales have identical value per unit in every family; rejected as economically meaningless.
- **R3 - Working capital, DSO, DPO, balance movement.** The measurement basis of Balance Sheet lines is unresolved and cells hold several lines that do not behave like additive balances (section H); not computed.
- **R4 - Forecast accuracy as a quality KPI.** About 90% of the absolute error sits on opposite-sign lines, whose accounting meaning is unresolved, and there is no forecast version or as-of date; not reported as a KPI until both are resolved.
- **R5 - Entity-month anomalies.** 4 of 864 months (0.5%) exceed |z| >= 3, against about 0.3% (2.3 months) expected for a normal distribution; not distinguishable from chance, so not reported as anomalies.
- **R6 - Duplicates as a material misstatement.** Excluding all candidate copies moves revenue by less than 1%; unproven as duplicates; kept.
- **R7 - 'Inefficient' cost areas from concentration.** High shares (materials, US01) are descriptive; no driver supports a judgement.
- **R8 - Prior-year column as a growth signal.** Uniform step-up that does not reconcile with the file's own prior-year actuals; not used.

## 8. Questions that need business context

1. Definitions of Posted / Pending / Parked / Rejected / blank and the extract cut-off (INS-01).
2. Sign convention by account (4190 discounts, 5120 PPV, credit notes) and whether opposite-sign lines are reversals (INS-02, INS-04).
3. How the budget and forecast were built, with version and date (INS-03, INS-05).
4. FX: meaning of zero and non-1.0 rates on USD lines, and which amount column is authoritative.
5. Report scale per extract batch to confirm the MEDIUM restorations (INS-07).
6. Budgeted FTE plan by entity and month (INS-06).
7. Balance Sheet lines: opening, closing or movement, and why a cell has several lines.
8. Provenance and licence of the dataset (unverified).

## 9. How to rerun

```
pip install -r requirements.txt
python src/phase4_pipeline.py          # verify input, build DB, run SQL, cross-check, validate, export
python src/phase4_report.py            # regenerate this report and the insight register
python -m pytest tests/test_phase4.py -q
```
The pipeline needs `data/processed/fpa_monthly_close_cleaned.csv` (Phase 3 output). It writes `data/processed/phase4_fpa.duckdb` (git-ignored) and `outputs/phase4/*.csv` with `MANIFEST.json`. Exit code 1 = missing/invalid input; 2 = integrity or validation failure (nothing accepted is overwritten; diagnostics go to `outputs/phase4_failed_run/` and `phase4_fpa.duckdb.failed`).
