# Financial Metrics and Methodology

**Month-End Close Reliability & Financial Performance Analytics**

> **Status (updated at Phase 9 publication, 30 Oct 2026):** published as part of the complete project. The owner decided to publish the whole project, including the dataset he describes as synthetic. Dataset provenance and redistribution rights remain **owner-stated and not independently verified**. Any wording below from Phase 8 that calls the release *blocked*, *draft* or *not approved* describes the Phase 8 state and is superseded by [PUBLICATION_DECISION.md](PUBLICATION_DECISION.md). No calculation, figure or finding was changed.
> **Data:** fictional NovaBridge Industries; owner-described as synthetic. Values are observed arithmetic on a simulated extract under provisional rules.
> **Evidence labels:** Verified / Owner-stated / Assumption / Unresolved.

Related: [SQL guide](SQL_ANALYTICS_GUIDE.md) · [Excel guide](EXCEL_FINANCIAL_ANALYSIS_GUIDE.md) · [Dashboard guide](DASHBOARD_USER_GUIDE.md) · [Risks](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md)

> **Note on the earlier definitions file.** [`docs/FINANCIAL_METRICS.md`](../docs/FINANCIAL_METRICS.md) is the Phase 1–3 candidate-rules document. It states that it contains no financial results and describes the variance percentage as plain `(actual − budget) / |budget|`. The Phase 4 SQL, the workbook and the dashboard apply a guarded percentage (section 5). This document describes what the delivered outputs actually compute. The older file is preserved unchanged.

---

## 1. Conventions that apply to every metric

| Convention | Rule | Status |
|---|---|---|
| Currency and scale | USD; amounts are the **scale-adjusted** values (`actual_usd_adj` and the matching budget, forecast and prior-year columns), with scale restoration provisional | Assumption (R7) |
| Signs | **As recorded.** No amount is flipped or repaired. Costs are positive magnitudes in the delivered outputs | Unresolved (R9) |
| Journal status | Reported population is **Posted only** | Assumption (R6) |
| Entities | Six real entities, taken one by one. No consolidation, no intercompany elimination | Unresolved (R12) |
| Duplicates | Duplicate candidates are retained | Unresolved (R11) |
| Aggregation | Sum amounts first, divide second. Percentages are never averaged across lines | Verified |
| Direction | Variance and error are arithmetic differences. No result is labelled favourable or unfavourable | Verified in outputs |
| P&L and balance sheet | Never added together | Owner-stated (R2) |

**Population shorthand** used below: *main* = 58,340 Posted-eligible P&L lines; *budget* = 55,043 lines with actual and budget; *forecast* = 54,851; *prior year* = 54,923; *any status* = 136,330.

Evidence for all values quoted: Phase 4 outputs, re-derived by the independent Phase 7 reference.

## 2. Revenue, COGS, People, Opex

| Item | Detail |
|---|---|
| Formula | Sum of `actual_usd_adj` for accounts mapped to the section in `dim_account` |
| Population | Main (58,340) |
| Filters | None at baseline; period, entity, division, section, GL and cost-centre filters in the dashboard |
| Source | `v_pl_actual`; tables `a1`–`a4`; workbook *Monthly P&L*; dashboard KPI cards |
| Baseline values | Revenue $202.65M; cost base (COGS + People + Opex) $176.33M |
| Interpretation | The recorded totals of the reportable population under the stated rules |
| Limitations | Provisional scale and Posted-only rules; signs as recorded (GL 4190 discounts and GL 5120 purchase price variance are sign-mixed); unconsolidated |
| Assumptions | R6, R7, R8 provisional; R9, R11, R12 unresolved |

Revenue accounts include 4100 product sales, 4110 service and spares, 4120 freight recovered and 4190 sales discounts and rebates. COGS accounts include 5100 materials, 5110 inbound freight, 5120 purchase price variance, 5200 direct labour and 5300 factory overhead.

## 3. Result proxy (not EBITDA)

| Item | Detail |
|---|---|
| Formula | Revenue − (COGS + People + Opex) |
| Population | Main |
| Source | Workbook *Monthly P&L*; dashboard KPI; `c8` for forecast bias on the proxy |
| Baseline value | $26.32M, which is 13.0% of revenue |
| Interpretation | A project-defined operating result indicator |
| Limitations | **Not EBITDA.** It excludes D&A, below-EBITDA items and tax, and is not a statutory or consolidated measure. Its sign and level depend on the unresolved sign convention |
| Assumptions | Same as section 2 |

13.0% is derived (26.32 ÷ 202.65 = 12.99%) and was recomputed in Phase 8.

## 4. Gross profit, scenarios S1, S2 and S3

| Item | Detail |
|---|---|
| Formula | Gross profit = Revenue − COGS. Gross margin % = Gross profit ÷ Revenue, null if revenue ≤ 0 |
| Treatments of GL 4190 (discounts) | **S1** signed as recorded: revenue = 4100 + 4110 + 4120 + 4190 · **S2** discount always reduces revenue: 4190 enters as −\|4190\| · **S3** discount excluded: 4100 + 4110 + 4120. COGS is signed as recorded in all three |
| Row sets | *All eligible rows*; and *all-non-negative rows* only (a sensitivity: it is not a "sign-consistent" population) |
| Population | Revenue and COGS rows of the main population |
| Source | `e1`–`e6`, `v_gp_rows`; workbook *Gross Profit*; dashboard *Gross Profit & Scenarios* |
| Results (all eligible rows) | Gross margin 54.2% (S1), 51.1% (S2), 54.8% (S3) |
| Versus budget | On same-sign lines gross profit is $12.3M below budget: 57% from revenue below budget, 43% from COGS above (INS-04) |
| Interpretation | A range. **No scenario is authoritative**; the right treatment depends on the unresolved convention for the only contra-revenue account |
| Limitations | Unit-value equality between 4100 and 5100 (NOS versus EA) is unverified; no price-volume-mix |
| Assumptions | R9 unresolved |

## 5. Budget variance and variance %

| Item | Detail |
|---|---|
| Variance | `Actual − Budget` (positive means actual above budget; arithmetic only) |
| Variance % | `Variance ÷ \|net budget\|`, returned **only when \|net budget\| ≥ 50% of the gross (sum of absolute) budget**; otherwise null. Zero or missing denominator gives null, never 0 or infinity |
| Population | Budget (55,043 lines), split into same-sign, opposite-sign and zero-involved lines |
| Source | `b1`–`b11`; workbook *Budget vs Actual*; dashboard *Budget & Variance*; macros `safe_pct`, `sign_cat` |
| Result | Same-sign lines: revenue 3.6% below budget, each cost section 6.3%–6.4% above budget, in all 36 months, six entities, five divisions and every one of the 20 operating accounts (INS-03) |
| Interpretation | The regularity is a property of the data. Whether it reflects how the budget was built is unknown (Low confidence) |
| Limitations | The 50% guard is a project convention: a percentage is shown only when |Net Budget| >= 50% x Gross Absolute Budget. Budget, forecast and prior year sit on each source extract record; summing them per line is an assumption. Opposite-sign lines have a near-zero net budget, so their percentage is hidden |
| Assumptions | R10 provisional. `b11` shows the sensitivity to the guard |

**Sign categories** (`sign_cat`): `SAME_SIGN_NONZERO`, `OPPOSITE_SIGN_NONZERO`, `ZERO_INVOLVED`, `MISSING_OR_UNAVAILABLE`. An opposite-sign pair is an observation, not a confirmed error (credit notes, reversals and contra accounts can legitimately differ in sign).

## 6. Forecast error, WAPE and bias

| Item | Detail |
|---|---|
| Forecast error | `Forecast − Actual` (positive means forecast above actual) |
| WAPE | `Σ\|Forecast − Actual\| ÷ Σ\|Actual\|` |
| Bias | `Σ(Forecast − Actual) ÷ Σ\|Actual\|` |
| Population | Forecast (54,851 lines); matched lines (actual, budget and forecast present) for forecast-versus-budget comparisons |
| Source | `c1`–`c8`; workbook *Forecast & Prior Year*; dashboard *Forecast & Prior-Year* |
| Why WAPE | MAPE is undefined for zero actuals and distorted by tiny and opposite-sign lines |
| Result | Opposite-sign lines (10% to 13% of lines) carry 89% to 91% of absolute forecast error (INS-02) |
| Interpretation | A comparison of two columns |
| Limitations | The extract has **no forecast version, as-of date or snapshot**. It cannot be said whether the forecast preceded the period. **No statement is made about forecast skill or accuracy in general.** WAPE weights large lines and hides which lines are wrong, hence the cell tables |
| Assumptions | Forecast values are per-line amounts that can be summed |

## 7. Prior-year comparison and year-over-year

| Item | Detail |
|---|---|
| Prior-year column | `Actual − PY` and `(Actual − PY) ÷ \|PY total\|`, guarded as in section 5, using the `prior_year_usd_adj` value on each line |
| True year-over-year | Actuals of the previous calendar year inside the extract (Jan 2023 to Dec 2025); 2023 has no earlier actuals, so the 2023 prior-year column cannot be verified |
| Population | Prior year (54,923 lines) |
| Source | `d1`–`d5`; dashboard *Year summary with true year-over-year* |
| Result | Revenue grew 14.8% in 2024 and 0.9% in 2025 against the prior calendar year (Phase 6 reconciliation to the workbook) |
| Limitations | The prior-year column and the true prior year are different things and are not guaranteed to agree (`d4`). Small baselines inflate percentages (`d5`) |

## 8. Concentration, Pareto and HHI

| Item | Detail |
|---|---|
| Share | Member's absolute actual ÷ total absolute actual for the dimension |
| Top-1 and top-3 share | Largest and three largest shares (exactly three members, deterministic tie-break) |
| Pareto | Cost accounts ranked by absolute activity with cumulative share (`f1`) |
| HHI | `Σ share²` (0 to 1), read against an equal-share benchmark `1 ÷ N` |
| Cost base | GL account, division and entity use COGS + People + Opex + D&A; **cost centre uses People + Opex only** |
| Population | Main |
| Source | `f1`–`f5`; workbook *GL & Cost Drivers*; dashboard *Drivers & Concentration* |
| Results | Materials (GL 5100) 36.8% of operating-cost activity against a 5.9% equal-share benchmark; Consumer Durables 36.1% of the cost base across five divisions; US01 25.8% across six entities |
| Interpretation | Descriptive. **High share is not called inefficiency**: a cost is judged only against a driver (FTE, quantity, budget) |
| Limitations | Absolute basis hides sign effects; the cost base differs by cut |

**Other cost metrics.** Cost-to-revenue by year (`f4`, absolute and signed side by side); cost mix by year (`f3`); persistent one-sided deviations (`f5`: entity × GL cells whose actual is on the same side of budget in at least 90% of months and whose three-year variance is at least 3% of budget; a reason to investigate, not a cause). Salary per FTE (`f6`, GL 6100, populated on about 93% of salary lines) and the implied FTE-months (`f7`) are a **hypothesis only**: they apply the entity median rate to the budget variance. No savings are claimed.

## 9. Trend, volatility and anomaly scan

| Item | Detail |
|---|---|
| Month-over-month and year-over-year | Change in the monthly total against the previous month, and against the same month a year earlier |
| Robust z-score | `(x − median) ÷ (1.4826 × MAD)`; null when MAD is 0 or an input is missing, and then reported as "not scorable" |
| Anomaly class | \|z\| ≥ 3 is a project convention; classes separate amount-driven from coverage-driven (row count also unusual) |
| Source | `g1`–`g6`; `b5`, `b6` |
| Interpretation | A flag to review lines, not an error |

## 10. Journal-status diagnostics

| Item | Detail |
|---|---|
| Definition | The same eligibility gates as the main population, with the status gate removed (`v_pl_actual_any_status`, 136,330 lines: 58,340 Posted + 77,990 non-Posted) |
| Results | Revenue is $202.65M on Posted only, $404.38M excluding Rejected, and $471.58M on all statuses; the result proxy is $26.32M, $49.16M and $53.88M (INS-01) |
| Interpretation | The journal-status rule is the largest swing factor among status, scale, sign and duplicates |
| Limitations | The statuses are almost uniformly distributed across entities (Posted about 43%), which a real posting workflow would rarely produce. Whether blank means unposted is unresolved. 4,996 non-Posted lines are outside every diagnostic (ISS-18) |

## 11. Scale sensitivity and data-quality exposure

| Item | Detail |
|---|---|
| Scale restoration | HIGH confidence: price-identity test against GL 4100 and 5100 with inferred list prices. MEDIUM confidence: peer comparison by robust z-score. Undetermined rows (73 in the cleaned file) stay blank and are excluded; 62 of them have gate 8 as their first failing gate, the rest fail an earlier gate |
| Rows restored | 6,265 rows in the cleaned file (1,814 HIGH, 4,451 MEDIUM). In the dashboard payload, 2,374 are Posted-eligible and 3,220 are non-Posted |
| Scenarios | As reported; restore HIGH only; exclude MEDIUM; exclude all restored |
| Results | Across the scale scenarios the result proxy ranges from $25.51M to $29.44M (INS-07). Scale, sign and duplicate handling move revenue by 4%, 19% and 1% of the baseline respectively (INS-01) |
| Source | `i1`–`i10`; dashboard scenario selectors |
| Limitations | The scale rule itself is unresolved; the price identity is an inference, not an observed price list |

## 12. Metrics deliberately not produced

| Not produced | Reason |
|---|---|
| Favourable or unfavourable labels | The sign convention is unresolved |
| General forecast-accuracy or skill statement | No forecast version or as-of date |
| An authoritative gross-profit figure | Three treatments of GL 4190 are all plausible |
| EBITDA | Needs D&A and below-EBITDA treatment and a validated sign convention |
| DSO, DPO, working capital | Balance-sheet measurement basis (opening, closing or movement) is unknown |
| Month-end close duration or on-time close rate | The extract contains no close timestamps |
| Consolidated group results | Intercompany eliminations are unavailable |
| Cost-centre variance, price-volume-mix, unit economics | Not supported by the data |

## 13. Where each metric is reproduced

| Metric | SQL | Workbook sheet | Dashboard tab |
|---|---|---|---|
| Revenue, cost base, result proxy | `a1`–`a4`, `v_pl_actual` | Monthly P&L | Executive Overview |
| Budget variance | `b1`–`b11` | Budget vs Actual | Budget & Variance |
| Forecast error | `c1`–`c8` | Forecast & Prior Year | Forecast & Prior-Year |
| Prior year | `d1`–`d5` | Forecast & Prior Year | Forecast & Prior-Year; Trends |
| Gross profit | `e1`–`e6` | Gross Profit | Gross Profit & Scenarios |
| Concentration, cost | `f1`–`f7` | GL & Cost Drivers | Drivers & Concentration |
| Trends | `g1`–`g6` | Monthly P&L | Trends & Performance |
| Status and scenarios | `i1`–`i10` | Data Quality | Data Quality & Methodology |
