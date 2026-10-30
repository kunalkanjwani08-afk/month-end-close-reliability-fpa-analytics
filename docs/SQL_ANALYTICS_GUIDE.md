# SQL Analytics Guide

**Month-End Close Reliability & Financial Performance Analytics**

> **Data:** fictional NovaBridge Industries; owner-described as synthetic. Figures describe a simulated extract.
> **Evidence labels:** Verified / Owner-stated / Assumption / Unresolved.

Related: [Data and cleaning](DATA_AND_CLEANING_METHODOLOGY.md) · [Financial metrics](FINANCIAL_METRICS.md)

---

## 1. Purpose

The SQL layer turns the cleaned CSV into a typed database, defines the reportable populations once (as views), and produces 72 result tables that feed the workbook, the dashboard and the analysis report. SQL outputs and views provide the **baseline** analytical results. The interactive dashboard computes dynamic filter selections in JavaScript from its embedded line-level payload and documented calculation logic, so a number shown for an arbitrary filter combination is not a stored SQL table row. independent validation independently compared the dashboard with pandas references in the tested filter and scenario states only (17 states); **not every possible filter combination has been independently tested**.

Scripts live in [`sql/analysis/`](../sql/analysis/) and are run by [`src/sql_analysis_pipeline.py`](../src/sql_analysis_pipeline.py) against DuckDB. Outputs are written to [`build/sql_results/`](../build/sql_results/) as CSV with a [`MANIFEST.json`](../build/sql_results/MANIFEST.json). The cross-check script is [`src/independent_crosscheck.py`](../src/independent_crosscheck.py).

## 2. Database structure

| Object | Type | Role |
|---|---|---|
| `stg_close_raw` | table | The cleaned CSV loaded as text, 152,682 rows, nothing converted |
| `fact_close` | table | Typed version of the staging table; one row per source extract record (including the 350 non-posting records); the only fact table |
| `dim_account` | table | 32 accounts: GL number, name, section, section order |
| 12 views | views | The reportable populations and scenario row sets (section 4) |
| 72 `out_*` tables | tables | One result table per output CSV (section 5) |

The database file is `build/fpa_analysis.duckdb`. It is a generated local file, not tracked by git, so it is rebuilt by running the pipeline rather than shipped.

**Grain.** One row of `fact_close` is one source extract record. The dataset contains 152,682 source extract records, including 350 non-posting subtotal/check records. These 350 records are not treated as ordinary posted journal lines. Actual, budget, forecast and prior-year amounts are four attributes of that line. A line can be missing any of them, which is why the populations differ in size.

## 3. Script organisation

Scripts run in numeric order. Each begins with a header describing its purpose.

| Script | Purpose | Main outputs |
|---|---|---|
| `01_dimensions_and_views` | Builds `dim_account`, `fact_close` typing, the reporting views, and the helper macros | views, macros |
| `02_grain_and_overview` | Proves the grain; summarises by period, section, entity, division and GL; checks dimension reliability and period coverage | `a0`–`a8` |
| `03_load_validation` | Compares database counts and totals to the cleaning QC | `val_load` |
| `04_budget_variance` | Variance, volatility, persistence, sign profile, bridge, sensitivities | `b1`–`b11` |
| `05_forecast_error` | Forecast error, attribution, bias, forecast versus budget | `c1`–`c8` |
| `06_prior_year` | Prior-year column and a true year-on-year comparison | `d1`–`d5` |
| `07_gross_profit` | Gross profit under three discount treatments | `e1`–`e6` |
| `08_cost_structure` | Cost by GL, concentration, mix, cost-to-revenue, salary per FTE | `f1`–`f7` |
| `09_trend_volatility` | Monthly series, MoM and YoY, seasonality, half-year growth, anomaly scan | `g1`–`g6` |
| `10_balance_sheet` | Balance-sheet coverage and spread (described, never added to P&L) | `h1`–`h6` |
| `11_dq_exposure_scenarios` | Scenarios for status, scale, sign and duplicates; exclusion waterfall | `i1`–`i10` |
| `99_analytical_validation` | Independent re-derivation of key figures; exclusion counts | `val_analytical`, `val_crosscheck`, `val_exclusion_counts` |

The count is 72 = 9 (`a`) + 11 (`b`) + 8 (`c`) + 5 (`d`) + 6 (`e`) + 7 (`f`) + 6 (`g`) + 6 (`h`) + 10 (`i`) + 4 (`val_*`).

## 4. Views and populations

Populations are defined once in `01_dimensions_and_views` so that every query uses the same rows. Row counts are from the database as built in SQL analysis and re-queried in documentation (read-only).

| View | Rows | Rule |
|---|---:|---|
| `v_close` | 152,682 | Every row, joined to `dim_account` (`LEFT JOIN dim_account USING (gl_account)`), with the eligibility flags |
| `v_pl_actual` | 58,340 | Reportable P&L: passes all exclusion gates, Posted only, income-statement section |
| `v_pl_actual_any_status` | 136,330 | Same gates but any journal status (58,340 Posted + 77,990 non-Posted) |
| `v_pl_budget` | 55,043 | Rows flagged `eligible_PL_variance` (reportable actual plus a budget amount) |
| `v_pl_forecast` | 54,851 | `eligible_PL_actual` rows with a forecast amount (a convention defined in the view; no project flag exists) |
| `v_pl_prior` | 54,923 | `eligible_PL_actual` rows with a prior-year amount (same convention) |
| `v_bs_actual` | 2,953 | Balance-sheet rows passing the same gates |

The remaining views (`v_var_scn`, `v_fc_scn`, `v_py_scn`, `v_gp_rows`, `v_dq_base`) expand the base populations into scenario row sets. The gap between `v_pl_actual_any_status` (136,330) and the union of the dashboard populations is explained in [DASHBOARD_USER_GUIDE.md](DASHBOARD_USER_GUIDE.md) and in risk 12 of [ASSUMPTIONS_LIMITATIONS_AND_RISKS.md](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md).

**Why views.** A population defined in one place cannot drift between queries. The independent validation audit re-derived the populations independently in pandas and matched them.

## 5. Reusable macros and helper tables

| Object | What it does |
|---|---|
| `safe_pct(num, den_net, den_abs)` | Returns a percentage only when |Net Budget| >= 50% x Gross Absolute Budget (absolute value of the net budget, compared with half the sum of absolute budgets); otherwise NULL (guards against near-zero denominators) |
| `sign_cat(a, b)` | Classifies a pair as `SAME_SIGN_NONZERO`, `OPPOSITE_SIGN_NONZERO`, `ZERO_INVOLVED` or `MISSING_OR_UNAVAILABLE` |
| `robust_z(x, med, mad)` | Median/MAD z-score, used for peer comparison and anomaly scans |
| `anomaly_class(z_amt, z_rows)` | Maps the amount and row-count robust z-scores to a class label |
| `scn_sign` | Four sign scenarios: all lines, same-sign only, opposite-sign only, zero-involved only |
| `gp_treatment` | Three gross-profit treatments (S1, S2, S3) |
| `gp_rowset` | Two row sets: all rows, and rows flagged all-non-negative |

The 50% threshold in `safe_pct` is a provisional rule (Assumption). Output `b11_budget_pct_sensitivity` shows how results move if it changes.

## 6. Query families, purpose and logic

Each family answers one business question. Results are aggregated before percentages are computed; percentages are never averaged across lines.

### A. Grain and overview (`a0`–`a8`)

| Table | Business purpose |
|---|---|
| `a0_grain_evidence` | Shows the record grain (no hidden aggregation) |
| `a1_pl_period_section` | Section totals by month |
| `a2_pl_entity_section` / `a3_pl_division_section` | Section totals by entity and division |
| `a4_pl_gl` | Totals by GL account |
| `a5_dimension_reliability` | How reliably each dimension is populated |
| `a6_period_coverage` / `a7_period_summary` | Which months are present and how complete they are |
| `a8_account_mapping_consistency` | Whether each GL maps to one name and section |

### B. Budget variance (`b1`–`b11`)

Population: `v_pl_budget` (55,043 lines). Variance = actual − budget, signs as recorded.

| Table | Business purpose |
|---|---|
| `b1_variance_section` | Variance by P&L section |
| `b2_variance_entity_gl` | Entity × GL cells, the unit for ranking |
| `b3_variance_division` / `b4_variance_monthly` | Variance by division and month |
| `b5_variance_volatility` / `b6_variance_persistence` | How variable, and how persistent, cell variances are |
| `b7_sign_category_profile` | Split into same-sign, opposite-sign, zero-involved lines |
| `b8_variance_bridge` | Reconciles section variances to the total |
| `b9_contribution_sensitivity` | How the top-cell ranking changes with the line population |
| `b10_top_cells_overlap` | Overlap of top cells across scenarios |
| `b11_budget_pct_sensitivity` | Effect of the percentage-guard threshold |

Verified headline: on same-sign lines revenue is 3.6% below budget and each cost section is 6.3%–6.4% above, in every month, entity, division and operating account (INS-03). This regularity is a property of the data; its cause is unknown.

### C. Forecast error (`c1`–`c8`)

Population: `v_pl_forecast` (54,851 lines). Measures are WAPE and bias (see the metrics document). The forecast has no version or as-of date, so no skill claim is made.

| Table | Business purpose |
|---|---|
| `c1_forecast_section` | WAPE and bias by section |
| `c2_error_attribution` | Share of absolute error from same-sign versus opposite-sign lines |
| `c3_forecast_entity` / `c4_forecast_quarter` | Error by entity and quarter |
| `c5_bias_persistence` | Whether bias keeps one direction |
| `c6_forecast_vs_budget` | Forecast error against budget error on the same lines |
| `c7_forecast_error_cells` | Largest error cells |
| `c8_profit_proxy_bias` | Bias in the result proxy |

Verified headline: opposite-sign lines (10%–13% of lines) carry 89%–91% of absolute error (INS-02).

### D. Prior year (`d1`–`d5`)

Population: `v_pl_prior` (54,923 lines).

| Table | Business purpose |
|---|---|
| `d1_vs_py_column` | Actual against the prior-year column recorded on each line |
| `d2_py_growth_spread` | Spread of line-level growth |
| `d3_true_yoy` | Year-on-year using actuals from the prior calendar year |
| `d4_py_column_reconciliation` | Whether the prior-year column agrees with real prior-year actuals |
| `d5_small_baseline` | Effect of small prior-year bases on percentages |

The prior-year column and true year-on-year are kept separate because they are not guaranteed to agree; `d4` shows the reconciliation.

### E. Gross profit (`e1`–`e6`)

Population: revenue and COGS rows of `v_pl_actual`. Three treatments of the discount account (GL 4190) are computed side by side:

| Scenario | Treatment of GL 4190 | Gross margin (all eligible rows) |
|---|---|---:|
| S1 `GP_S1_SIGNED_AS_RECORDED` | Used at its recorded sign | 54.2% |
| S2 `GP_S2_DISCOUNT_ABS` | Always reduces revenue (`−abs`) | 51.1% |
| S3 `GP_S3_EXCL_DISCOUNT` | Excluded | 54.8% |

No scenario is authoritative; the correct treatment depends on the unresolved sign convention. Tables `e2`–`e6` repeat the analysis by entity, against budget, as a bridge, and test unit-value equality and materiality.

### F. Cost structure (`f1`–`f7`)

| Table | Business purpose |
|---|---|
| `f1_cost_by_gl` | Cost by GL account |
| `f2_concentration` | Share, Pareto and HHI by GL, division, entity and cost centre |
| `f3_cost_mix_by_year` | Cost mix by year |
| `f4_cost_to_revenue` | Cost relative to revenue |
| `f5_persistent_cells` | Cells that are repeatedly high |
| `f6_salary_per_fte` / `f7_salary_implied_fte` | Salary rate and implied headcount |

The concentration base differs by cut: GL, division and entity use the cost base including D&A; cost centre uses PEOPLE + OPEX only. Verified: Materials (GL 5100) 36.8% of operating-cost activity, Consumer Durables 36.1% of the cost base, US01 25.8%. High share is descriptive and not called inefficiency.

### G. Trends and volatility (`g1`–`g6`)

Monthly series, month-over-month and year-over-year change, seasonality, half-year growth, entity growth and a robust-z anomaly scan. Anomalies are flags for review, not errors.

### H. Balance sheet (`h1`–`h6`)

Population: `v_bs_actual` (2,953 lines). Coverage, by-account detail, multi-line spread, period totals and volatility are described. `h6_bs_metrics_not_computed` records what was deliberately not computed (for example DSO, DPO and working capital), because the measurement basis and the unit of the balance-sheet amounts are unknown.

### I. Data-quality exposure and scenarios (`i1`–`i10`)

| Table | Business purpose |
|---|---|
| `i1_scenarios` | Headline under each scenario (status, scale, sign, duplicates) |
| `i2_factor_ranking` | Which assumption moves the headline most |
| `i3_variance_robustness` | Whether the variance pattern survives each scenario |
| `i4_undetermined_scale` | Rows whose scale stayed undetermined |
| `i5_restored_exposure` | Exposure from scale-restored rows |
| `i6_duplicate_exposure` / `i7_exact_row_matches` | Duplicate candidates and exact matches |
| `i8_flag_exposure` | Exposure by data-quality flag |
| `i9_exclusion_waterfall` | Row-by-row exclusion by gate |
| `i10_price_identity_independence` | Whether the price-identity scale check is independent of the amount it tests |

Verified: revenue is $202.65M (Posted only), $404.38M (excluding Rejected) and $471.58M (all statuses); status is the largest swing factor.

### Validation (`val_*`)

`val_load`, `val_exclusion_counts`, `val_analytical` and `val_crosscheck` compare the database against the cleaning QC and against an independent recomputation. They are the SQL layer's own checks and are separate from the independent validation audit.

## 7. Joins and aggregation rules

- The fact table joins to `dim_account` on `gl_account` with a LEFT JOIN, so a missing account never drops a row silently.
- Period spines (`CROSS JOIN` of entities and periods, then `LEFT JOIN`) are used where a zero month must appear as a zero rather than a missing row.
- Self-joins on the prior year (`period_year − 1`) and half-year are used for growth; the independent validation SQL module checked join fan-out.
- Aggregation sums amounts first, then divides. Percentages with a near-zero denominator are NULL (see `safe_pct`).
- No query adds balance-sheet rows to P&L totals.

## 8. Validation of the SQL layer

| Check | Result | Source |
|---|---|---|
| Database counts and totals against cleaning QC | Agreed | `val_load`, independent validation |
| Exclusion counts by gate | Agreed | `val_exclusion_counts`, independent validation |
| 72 output tables against their CSV files | 72 present with manifest | Independent validation file audit |
| Key totals against an independent pandas reference | Agreed within tolerance | Independent validation `F_I1` |
| Python cross-check of the SQL results | Passed | `independent_crosscheck.py` |

Details and the one historical failure are in QA_AND_VALIDATION_SUMMARY.md.

## 9. Running the SQL layer

The runnable sequence is in [HOW_TO_RUN.txt](../HOW_TO_RUN.txt). In short, the pipeline script loads the cleaned CSV, executes the scripts in order, exports the CSVs and writes the manifest. It was re-run in independent validation on Linux and reproduced the outputs. It has not been run on Windows or on a clean machine.

## 10. Limitations

- The population rules (Posted-only, scale restoration, guard threshold) are provisional; the sign convention, duplicate handling and consolidation are unresolved.
- Entity-level totals are not consolidated; intercompany eliminations are not available.
- The forecast has no version or date.
- The balance-sheet measurement basis is unknown.
- 4,996 non-Posted lines are in `v_pl_actual_any_status` but in no dashboard population.
- SQL was executed in DuckDB only; no other SQL engine was tested.
