-- =====================================================================================================
-- 99  Analytical validation  ->  out_val_analytical
-- Every published table is re-derived a second way, straight from fact_close (not through the views the analysis
-- used), and compared. Each row: expected (independent recomputation), actual (published output), tolerance.
-- Money tolerance 0.01 USD (sums of up to ~60k doubles); ratios 1e-9; counts exact.
-- Runs LAST (file 99) so that every out_* table already exists.
-- =====================================================================================================
CREATE OR REPLACE TABLE out_val_analytical AS
WITH
-- independent re-derivation base: P&L actual population straight from the raw eligibility flag
p AS (
    SELECT f.row_id, f.entity_code, f.gl_account, f.period_ym, f.period_year, f.division,
           f.actual_usd_adj AS a, f.budget_usd_adj AS b, f.forecast_usd_adj AS fc, f.prior_year_usd_adj AS py,
           CASE f.account_group WHEN 'Revenue' THEN 'REVENUE' WHEN 'COGS' THEN 'COGS' WHEN 'People cost' THEN 'PEOPLE'
                WHEN 'Operating expense' THEN 'OPEX' WHEN 'Depreciation' THEN 'D&A' WHEN 'Below EBITDA' THEN 'BELOW_EBITDA'
                WHEN 'Tax' THEN 'TAX' END AS sec
    FROM fact_close f WHERE f.eligible_PL_actual = 1),
checks(check_id, area, description, expected, actual, tolerance) AS (
-- ---- A: overview totals --------------------------------------------------------------------------
SELECT 'A01', 'overview', 'Sum of out_a1 (period x section) actual = eligible P&L actual total', (SELECT sum(a) FROM p), (SELECT sum(actual_usd) FROM out_a1_pl_period_section), 0.01
UNION ALL SELECT 'A02', 'overview', 'out_a1 rows_eligible total = 58,340', 58340, (SELECT sum(rows_eligible) FROM out_a1_pl_period_section), 0
UNION ALL SELECT 'A03', 'overview', 'out_a2 (entity x section) total = out_a1 total', (SELECT sum(actual_usd) FROM out_a1_pl_period_section), (SELECT sum(actual_usd) FROM out_a2_pl_entity_section), 0.01
UNION ALL SELECT 'A04', 'overview', 'out_a3 (division x section) total = out_a1 total', (SELECT sum(actual_usd) FROM out_a1_pl_period_section), (SELECT sum(actual_usd) FROM out_a3_pl_division_section), 0.01
UNION ALL SELECT 'A05', 'overview', 'out_a4 (GL) total = out_a1 total', (SELECT sum(actual_usd) FROM out_a1_pl_period_section), (SELECT sum(actual_usd) FROM out_a4_pl_gl), 0.01
UNION ALL SELECT 'A06', 'overview', 'Revenue section: out_a1 = independent recomputation from fact_close',
       (SELECT sum(a) FROM p WHERE sec = 'REVENUE'), (SELECT sum(actual_usd) FROM out_a1_pl_period_section WHERE section = 'REVENUE'), 0.01
UNION ALL SELECT 'A07', 'overview', 'COGS section: out_a1 = independent recomputation',
       (SELECT sum(a) FROM p WHERE sec = 'COGS'), (SELECT sum(actual_usd) FROM out_a1_pl_period_section WHERE section = 'COGS'), 0.01
UNION ALL SELECT 'A08', 'overview', 'Entity x section cell (US01, revenue): out_a2 = independent recomputation',
       (SELECT sum(a) FROM p WHERE sec = 'REVENUE' AND entity_code = 'US01'), (SELECT actual_usd FROM out_a2_pl_entity_section WHERE section = 'REVENUE' AND entity_code = 'US01'), 0.01
UNION ALL SELECT 'A09', 'overview', 'Absolute activity: out_a1 abs total = independent sum of |actual|', (SELECT sum(abs(a)) FROM p), (SELECT sum(abs_actual_usd) FROM out_a1_pl_period_section), 0.01
UNION ALL SELECT 'A10', 'overview', 'Coverage grid: rows in out_a6 sum to the eligible population', 58340, (SELECT sum(rows_eligible) FROM out_a6_period_coverage), 0
UNION ALL SELECT 'A11', 'overview', 'Entity-periods without any eligible row (gaps) - published count equals recount',
       (SELECT 216 - count(*) FROM (SELECT DISTINCT entity_code, period_ym FROM p)), (SELECT entity_period_gaps FROM out_a7_period_summary), 0
-- ---- B: budget variance ---------------------------------------------------------------------------
UNION ALL SELECT 'B01', 'variance', 'Revenue variance (as reported) = sum(actual) - sum(budget) recomputed on eligible-with-budget rows',
       (SELECT sum(a) - sum(b) FROM p WHERE sec = 'REVENUE' AND b IS NOT NULL), (SELECT net_variance_usd FROM out_b1_variance_section WHERE scenario = 'ALL_LINES' AND section = 'REVENUE'), 0.01
UNION ALL SELECT 'B02', 'variance', 'COGS variance (as reported) recomputed',
       (SELECT sum(a) - sum(b) FROM p WHERE sec = 'COGS' AND b IS NOT NULL), (SELECT net_variance_usd FROM out_b1_variance_section WHERE scenario = 'ALL_LINES' AND section = 'COGS'), 0.01
UNION ALL SELECT 'B03', 'variance', 'PEOPLE variance (as reported) recomputed',
       (SELECT sum(a) - sum(b) FROM p WHERE sec = 'PEOPLE' AND b IS NOT NULL), (SELECT net_variance_usd FROM out_b1_variance_section WHERE scenario = 'ALL_LINES' AND section = 'PEOPLE'), 0.01
UNION ALL SELECT 'B04', 'variance', 'OPEX variance (as reported) recomputed',
       (SELECT sum(a) - sum(b) FROM p WHERE sec = 'OPEX' AND b IS NOT NULL), (SELECT net_variance_usd FROM out_b1_variance_section WHERE scenario = 'ALL_LINES' AND section = 'OPEX'), 0.01
UNION ALL SELECT 'B05', 'variance', 'Revenue variance, same-sign non-zero lines only, recomputed (actual and budget both non-zero, same sign)',
       (SELECT sum(a) - sum(b) FROM p WHERE sec = 'REVENUE' AND b IS NOT NULL AND a <> 0 AND b <> 0 AND sign(a) = sign(b)), (SELECT net_variance_usd FROM out_b1_variance_section WHERE scenario = 'SAME_SIGN_ONLY' AND section = 'REVENUE'), 0.01
UNION ALL SELECT 'B06', 'variance', 'Variance population rows (as reported, P&L sections) = 55,043',
       55043, (SELECT sum(rows_in_scope) FROM out_b1_variance_section WHERE scenario = 'ALL_LINES'), 0
UNION ALL SELECT 'B07', 'variance', 'Sign categories partition the population: same-sign + opposite-sign + zero-involved lines = all lines',
       (SELECT sum(rows_in_scope) FROM out_b1_variance_section WHERE scenario = 'ALL_LINES'),
       (SELECT sum(rows_in_scope) FROM out_b1_variance_section WHERE scenario IN ('SAME_SIGN_ONLY', 'OPPOSITE_SIGN_ONLY', 'ZERO_INVOLVED_ONLY')), 0
UNION ALL SELECT 'B08', 'variance', 'Bridge: all-lines variance = same-sign + opposite-sign + zero-involved variance (largest abs difference over sections)', 0, (SELECT max(abs(bridge_difference_usd)) FROM out_b8_variance_bridge), 0.01
UNION ALL SELECT 'B09', 'variance', 'Monthly variance sums (out_b4) = section variance (out_b1), as reported, all sections',
       (SELECT sum(net_variance_usd) FROM out_b1_variance_section WHERE scenario = 'ALL_LINES'), (SELECT sum(variance_usd) FROM out_b4_variance_monthly WHERE scenario = 'ALL_LINES'), 0.01
UNION ALL SELECT 'B10', 'variance', 'Entity x GL variance sums (out_b2) = section variance (out_b1), as reported',
       (SELECT sum(net_variance_usd) FROM out_b1_variance_section WHERE scenario = 'ALL_LINES'), (SELECT sum(variance_usd) FROM out_b2_variance_entity_gl WHERE scenario = 'ALL_LINES'), 0.01
UNION ALL SELECT 'B11', 'variance', 'Division variance sums (out_b3) = section variance (out_b1), as reported',
       (SELECT sum(net_variance_usd) FROM out_b1_variance_section WHERE scenario = 'ALL_LINES'), (SELECT sum(variance_usd) FROM out_b3_variance_division WHERE scenario = 'ALL_LINES'), 0.01
UNION ALL SELECT 'B12', 'variance', 'Published % = variance / ABS(net budget) wherever the guard allows one (max abs recomputation error)', 0,
       (SELECT coalesce(max(abs(variance_pct_of_abs_budget - net_variance_usd / abs(budget_usd))), 0) FROM out_b1_variance_section WHERE variance_pct_of_abs_budget IS NOT NULL), 1e-9
UNION ALL SELECT 'B13', 'variance', 'Net-budget guard: a % is published exactly when |net budget| >= 50% of gross budget (rows where the two disagree)', 0,
       (SELECT count(*) FROM out_b1_variance_section WHERE (variance_pct_of_abs_budget IS NOT NULL) <> (budget_netting_ratio >= 0.5)), 0
UNION ALL SELECT 'B14', 'variance', 'Gross variance >= |net variance| for every section/scenario (rows violating the triangle inequality)', 0,
       (SELECT count(*) FROM out_b1_variance_section WHERE gross_cell_variance_usd + 0.01 < abs(net_variance_usd)), 0
-- ---- C: forecast -----------------------------------------------------------------------------------
UNION ALL SELECT 'C01', 'forecast', 'Revenue forecast error (forecast - actual) recomputed, as reported',
       (SELECT sum(fc) - sum(a) FROM p WHERE sec = 'REVENUE' AND fc IS NOT NULL), (SELECT net_error_usd FROM out_c1_forecast_section WHERE scenario = 'ALL_LINES' AND section = 'REVENUE'), 0.01
UNION ALL SELECT 'C02', 'forecast', 'Revenue WAPE recomputed = sum|F-A| / sum|A|',
       (SELECT sum(abs(fc - a)) / sum(abs(a)) FROM p WHERE sec = 'REVENUE' AND fc IS NOT NULL), (SELECT wape FROM out_c1_forecast_section WHERE scenario = 'ALL_LINES' AND section = 'REVENUE'), 1e-9
UNION ALL SELECT 'C03', 'forecast', 'Revenue bias recomputed = sum(F-A) / sum|A|',
       (SELECT (sum(fc) - sum(a)) / sum(abs(a)) FROM p WHERE sec = 'REVENUE' AND fc IS NOT NULL), (SELECT bias FROM out_c1_forecast_section WHERE scenario = 'ALL_LINES' AND section = 'REVENUE'), 1e-9
UNION ALL SELECT 'C04', 'forecast', 'OPEX WAPE recomputed, same-sign non-zero lines only (F and A both non-zero, same sign)',
       (SELECT sum(abs(fc - a)) / sum(abs(a)) FROM p WHERE sec = 'OPEX' AND fc IS NOT NULL AND a <> 0 AND fc <> 0 AND sign(a) = sign(fc)), (SELECT wape FROM out_c1_forecast_section WHERE scenario = 'SAME_SIGN_ONLY' AND section = 'OPEX'), 1e-9
UNION ALL SELECT 'C05', 'forecast', 'Forecast population rows (as reported, 4 sections + others) equals eligible rows with forecast present',
       (SELECT count(*) FROM p WHERE fc IS NOT NULL AND sec IN ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')),
       (SELECT sum(rows_in_scope) FROM out_c1_forecast_section WHERE scenario = 'ALL_LINES' AND section IN ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')), 0
UNION ALL SELECT 'C06', 'forecast', 'Error attribution: absolute error summed over the sign categories = total absolute error (revenue)',
       (SELECT abs_error_usd FROM out_c1_forecast_section WHERE scenario = 'ALL_LINES' AND section = 'REVENUE'),
       (SELECT sum(abs_error_usd) FROM out_c2_error_attribution WHERE section = 'REVENUE'), 0.01
UNION ALL SELECT 'C07', 'forecast', 'Category shares of absolute error and of rows each sum to 1 per section (largest deviation)', 0,
       (SELECT max(greatest(abs(e - 1), abs(r - 1))) FROM (SELECT section, sum(share_of_abs_error) AS e, sum(share_of_rows) AS r FROM out_c2_error_attribution GROUP BY section)), 1e-9
UNION ALL SELECT 'C09', 'forecast', 'Opposite-sign share of absolute revenue forecast error recomputed independently from fact_close',
       (SELECT sum(abs(fc - a)) FILTER (WHERE a <> 0 AND fc <> 0 AND sign(a) <> sign(fc)) / sum(abs(fc - a)) FROM p WHERE sec = 'REVENUE' AND fc IS NOT NULL),
       (SELECT share_of_abs_error FROM out_c2_error_attribution WHERE section = 'REVENUE' AND sign_category = 'OPPOSITE_SIGN_NONZERO'), 1e-9
UNION ALL SELECT 'C08', 'forecast', 'Profit proxy 2024 forecast - actual = published difference',
       (SELECT forecast_result_proxy_usd - actual_result_proxy_usd FROM out_c8_profit_proxy_bias WHERE period_year = 2024), (SELECT forecast_minus_actual_usd FROM out_c8_profit_proxy_bias WHERE period_year = 2024), 0.01
-- ---- D: prior year ---------------------------------------------------------------------------------
UNION ALL SELECT 'D01', 'prior_year', 'Revenue change vs PY column (as reported) = sum(actual) - sum(PY) recomputed',
       (SELECT sum(a) - sum(py) FROM p WHERE sec = 'REVENUE' AND py IS NOT NULL), (SELECT sum(change_usd) FROM out_d1_vs_py_column WHERE scenario = 'ALL_LINES' AND section = 'REVENUE'), 0.01
UNION ALL SELECT 'D02', 'prior_year', 'Revenue true YoY 2024 (posted signed) recomputed = sum(2024) / sum(2023) - 1',
       (SELECT sum(a) FILTER (WHERE period_year = 2024) / sum(a) FILTER (WHERE period_year = 2023) - 1 FROM p WHERE sec = 'REVENUE'),
       (SELECT yoy_growth FROM out_d3_true_yoy WHERE basis = 'POSTED_SIGNED' AND section = 'REVENUE' AND period_year = 2024), 1e-9
UNION ALL SELECT 'D03', 'prior_year', 'Revenue true YoY 2024 (any status, absolute) recomputed independently from fact_close',
       (SELECT sum(abs(actual_usd_adj)) FILTER (WHERE period_year = 2024) / sum(abs(actual_usd_adj)) FILTER (WHERE period_year = 2023) - 1
          FROM fact_close WHERE is_posting_row = 1 AND flag_junk_entity = 0 AND flag_entity_unresolved = 0 AND statement = 'P&L'
            AND flag_period_unparsed = 0 AND actual_usd_adj IS NOT NULL AND account_group = 'Revenue'),
       (SELECT yoy_growth FROM out_d3_true_yoy WHERE basis = 'ANY_STATUS_ABS' AND section = 'REVENUE' AND period_year = 2024), 1e-9
UNION ALL SELECT 'D04', 'prior_year', '2023 has no prior calendar year inside the file: YoY must be NULL for 2023 (violations)', 0,
       (SELECT count(*) FROM out_d3_true_yoy WHERE period_year = 2023 AND yoy_growth IS NOT NULL), 0
UNION ALL SELECT 'D05', 'prior_year', 'PY reconciliation row (revenue, 2024): py_column - previous-year actual = published difference',
       (SELECT sum(py) FILTER (WHERE period_year = 2024) - sum(a) FILTER (WHERE period_year = 2023) FROM p WHERE sec = 'REVENUE'),
       (SELECT difference_usd FROM out_d4_py_column_reconciliation WHERE section = 'REVENUE' AND period_year = 2024), 0.01
-- ---- E: gross profit -------------------------------------------------------------------------------
UNION ALL SELECT 'E01', 'gross_profit', 'GP bridge: gp variance = revenue variance - COGS variance (largest abs difference)', 0, (SELECT max(abs(bridge_difference_usd)) FROM out_e4_gp_variance_bridge), 0.01
UNION ALL SELECT 'E02', 'gross_profit', 'GP (S1, all rows, all years) = revenue - COGS recomputed',
       (SELECT sum(a) FILTER (WHERE sec = 'REVENUE') - sum(a) FILTER (WHERE sec = 'COGS') FROM p),
       (SELECT gross_profit_usd FROM out_e1_gross_profit WHERE rowset = 'ROWS_ALL' AND treatment = 'GP_S1_SIGNED_AS_RECORDED' AND period = 'ALL YEARS'), 0.01
UNION ALL SELECT 'E03', 'gross_profit', 'GP (S3, excluding discount GL 4190) recomputed',
       (SELECT sum(a) FILTER (WHERE sec = 'REVENUE' AND gl_account <> 4190) - sum(a) FILTER (WHERE sec = 'COGS') FROM p),
       (SELECT gross_profit_usd FROM out_e1_gross_profit WHERE rowset = 'ROWS_ALL' AND treatment = 'GP_S3_EXCL_DISCOUNT' AND period = 'ALL YEARS'), 0.01
UNION ALL SELECT 'E04', 'gross_profit', 'GP by year sums to GP all years (S1, all rows)',
       (SELECT gross_profit_usd FROM out_e1_gross_profit WHERE rowset = 'ROWS_ALL' AND treatment = 'GP_S1_SIGNED_AS_RECORDED' AND period = 'ALL YEARS'),
       (SELECT sum(gross_profit_usd) FROM out_e1_gross_profit WHERE rowset = 'ROWS_ALL' AND treatment = 'GP_S1_SIGNED_AS_RECORDED' AND period <> 'ALL YEARS'), 0.01
UNION ALL SELECT 'E05', 'gross_profit', 'GP by entity sums to GP all years (S1, all rows)',
       (SELECT gross_profit_usd FROM out_e1_gross_profit WHERE rowset = 'ROWS_ALL' AND treatment = 'GP_S1_SIGNED_AS_RECORDED' AND period = 'ALL YEARS'),
       (SELECT sum(gross_profit_usd) FROM out_e2_gross_profit_entity WHERE rowset = 'ROWS_ALL' AND treatment = 'GP_S1_SIGNED_AS_RECORDED'), 0.01
UNION ALL SELECT 'E06', 'gross_profit', 'Discount GL 4190 is in the revenue section (classification check: GLs 4100/4110/4120/4190 = Revenue)', 4,
       (SELECT count(*) FROM dim_account WHERE section = 'REVENUE' AND gl_account IN (4100, 4110, 4120, 4190)), 0
-- ---- F: cost structure ---------------------------------------------------------------------------------
UNION ALL SELECT 'F01', 'cost', 'Cost-by-GL shares sum to 1', 1, (SELECT sum(share_of_cost_abs) FROM out_f1_cost_by_gl), 1e-9
UNION ALL SELECT 'F02', 'cost', 'Cumulative share of the last-ranked GL = 1', 1, (SELECT max(cumulative_share) FROM out_f1_cost_by_gl), 1e-9
UNION ALL SELECT 'F03', 'cost', 'Cost base absolute total = independent sum over COGS/PEOPLE/OPEX/D&A',
       (SELECT sum(abs(a)) FROM p WHERE sec IN ('COGS', 'PEOPLE', 'OPEX', 'D&A')), (SELECT sum(actual_abs_usd) FROM out_f1_cost_by_gl), 0.01
UNION ALL SELECT 'F04', 'cost', 'Cost mix shares sum to 1 in each year (largest deviation)', 0, (SELECT max(abs(s - 1)) FROM (SELECT period_year, sum(share_of_cost_abs) AS s FROM out_f3_cost_mix_by_year GROUP BY 1)), 1e-9
UNION ALL SELECT 'F05', 'cost', 'HHI between 1/N and 1 for every dimension (violations)', 0, (SELECT count(*) FROM out_f2_concentration WHERE hhi < equal_share_benchmark - 1e-12 OR hhi > 1 + 1e-12), 0
-- ---- G: trend ----------------------------------------------------------------------------------------
UNION ALL SELECT 'G01', 'trend', 'Monthly posted-signed series total = overview total (all sections)', (SELECT sum(a) FROM p), (SELECT sum(posted_signed_usd) FROM out_g1_monthly_series), 0.01
UNION ALL SELECT 'G02', 'trend', 'Monthly series rows = 36 periods x 7 sections (eligible)', (SELECT count(*) FROM (SELECT DISTINCT period_ym, sec FROM p)), (SELECT count(*) FROM out_g1_monthly_series WHERE posted_rows > 0), 0
UNION ALL SELECT 'G03', 'trend', 'Any-status absolute revenue series total recomputed independently',
       (SELECT sum(abs(actual_usd_adj)) FROM fact_close WHERE is_posting_row = 1 AND flag_junk_entity = 0 AND flag_entity_unresolved = 0 AND statement = 'P&L'
            AND flag_period_unparsed = 0 AND actual_usd_adj IS NOT NULL AND account_group = 'Revenue'),
       (SELECT sum(any_abs_usd) FROM out_g1_monthly_series WHERE section = 'REVENUE'), 0.01
UNION ALL SELECT 'G04', 'trend', 'Seasonal index averages to 1 within each section (largest deviation)', 0, (SELECT max(abs(m - 1)) FROM (SELECT section, avg(seasonal_index) AS m FROM out_g3_seasonality GROUP BY 1)), 1e-9
-- ---- H: balance sheet -------------------------------------------------------------------------------
UNION ALL SELECT 'H01', 'balance_sheet', 'Balance-sheet line count in out_h2 = eligible BS population (2,953)', 2953, (SELECT sum(lines) FROM out_h2_bs_by_account), 0
UNION ALL SELECT 'H02', 'balance_sheet', 'out_h4 period totals add to out_h2 totals (signed lines)', (SELECT sum(signed_sum_of_lines_usd_not_a_balance) FROM out_h2_bs_by_account), (SELECT sum(signed_line_total_usd) FROM out_h4_bs_period_totals), 0.01
UNION ALL SELECT 'H03', 'balance_sheet', 'Balance-sheet total recomputed from fact_close',
       (SELECT sum(actual_usd_adj) FROM fact_close WHERE eligible_BS_actual = 1), (SELECT sum(signed_sum_of_lines_usd_not_a_balance) FROM out_h2_bs_by_account), 0.01
-- ---- I: exposure scenarios ----------------------------------------------------------------------------
UNION ALL SELECT 'I01', 'exposure', 'All baseline scenarios coincide (largest spread of revenue across the four factor baselines)', 0,
       (SELECT max(revenue_usd) - min(revenue_usd) FROM out_i1_scenarios WHERE scenario LIKE '%(baseline)%'), 0.01
UNION ALL SELECT 'I02', 'exposure', 'Baseline revenue = overview revenue total (a1) - scenario table ties to the published base',
       (SELECT sum(actual_usd) FROM out_a1_pl_period_section WHERE section = 'REVENUE'), (SELECT revenue_usd FROM out_i1_scenarios WHERE scenario = 'POSTED_ONLY (baseline)'), 0.01
UNION ALL SELECT 'I03', 'exposure', 'Single-status scenarios partition the any-status population (rows)',
       (SELECT rows_in_scope FROM out_i1_scenarios WHERE scenario = 'ALL_STATUSES'),
       (SELECT sum(rows_in_scope) FROM out_i1_scenarios WHERE scenario IN ('POSTED_ONLY (baseline)', 'PENDING_ONLY', 'PARKED_ONLY', 'REJECTED_ONLY', 'BLANK_ONLY')), 0
UNION ALL SELECT 'I04', 'exposure', 'Single-status scenarios partition the any-status revenue (USD)',
       (SELECT revenue_usd FROM out_i1_scenarios WHERE scenario = 'ALL_STATUSES'),
       (SELECT sum(revenue_usd) FROM out_i1_scenarios WHERE scenario IN ('POSTED_ONLY (baseline)', 'PENDING_ONLY', 'PARKED_ONLY', 'REJECTED_ONLY', 'BLANK_ONLY')), 0.01
UNION ALL SELECT 'I05', 'exposure', 'Any-status P&L row count recomputed independently = 136,330',
       (SELECT count(*) FROM fact_close WHERE is_posting_row = 1 AND flag_junk_entity = 0 AND flag_entity_unresolved = 0 AND statement = 'P&L' AND flag_period_unparsed = 0 AND actual_usd_adj IS NOT NULL),
       (SELECT rows_in_scope FROM out_i1_scenarios WHERE scenario = 'ALL_STATUSES'), 0
UNION ALL SELECT 'I06', 'exposure', 'As-reported (unrestored) revenue = independent sum of actual_usd_parsed on Posted eligible rows',
       (SELECT sum(actual_usd_parsed) FROM fact_close WHERE eligible_PL_actual = 1 AND account_group = 'Revenue'), (SELECT revenue_usd FROM out_i1_scenarios WHERE scenario = 'AS_REPORTED_PARSED (no restoration)'), 0.01
UNION ALL SELECT 'I07', 'exposure', 'Restoring only HIGH confidence + restoring MEDIUM = adjusted baseline: revenue difference = MEDIUM-restored revenue uplift',
       (SELECT sum(actual_usd_adj - actual_usd_parsed) FROM fact_close WHERE eligible_PL_actual = 1 AND account_group = 'Revenue' AND scale_factor_applied IN (1000, 100000) AND scale_confidence <> 'HIGH'),
       (SELECT (SELECT revenue_usd FROM out_i1_scenarios WHERE scenario = 'ADJUSTED_ALL (baseline)') - (SELECT revenue_usd FROM out_i1_scenarios WHERE scenario = 'RESTORE_HIGH_CONFIDENCE_ONLY')), 0.01
UNION ALL SELECT 'I08', 'exposure', 'Variance robustness: baseline revenue variance (i3) = as-reported revenue variance (b1)',
       (SELECT net_variance_usd FROM out_b1_variance_section WHERE scenario = 'ALL_LINES' AND section = 'REVENUE'),
       (SELECT net_variance_usd FROM out_i3_variance_robustness WHERE scenario LIKE 'baseline%' AND section = 'REVENUE'), 0.01
UNION ALL SELECT 'I09', 'exposure', 'Exclusion waterfall rows add to every row of the file', 152682, (SELECT sum(rows_n) FROM out_i9_exclusion_waterfall), 0
UNION ALL SELECT 'I10', 'exposure', 'Duplicate exposure rows add to the eligible population', 58340, (SELECT sum(rows_eligible) FROM out_i6_duplicate_exposure), 0
UNION ALL SELECT 'I11', 'exposure', 'Restored-exposure rows add to restored eligible P&L rows (independent count)',
       (SELECT count(*) FROM fact_close WHERE eligible_PL_actual = 1 AND scale_factor_applied IN (1000, 100000)), (SELECT sum(rows_n) FROM out_i5_restored_exposure), 0
UNION ALL SELECT 'I12', 'exposure', 'Undetermined-scale rows by section add to 73 (posting rows) plus none for non-posting',
       73, (SELECT sum(rows_undetermined) FROM out_i4_undetermined_scale), 0
UNION ALL SELECT 'I13', 'exposure', 'Factor ranking uses only BASELINE and POLICY_SCENARIO rows: scenario count of the status factor = 3 (posted, all-except-rejected, all statuses)',
       3, (SELECT scenarios FROM out_i2_factor_ranking WHERE factor = 'status'), 0
UNION ALL SELECT 'I14', 'exposure', 'Every scenario row carries a valid scenario_class (rows outside BASELINE / POLICY_SCENARIO / STATUS_PARTITION_DIAGNOSTIC)', 0,
       (SELECT count(*) FROM out_i1_scenarios WHERE scenario_class IS NULL OR scenario_class NOT IN ('BASELINE', 'POLICY_SCENARIO', 'STATUS_PARTITION_DIAGNOSTIC')), 0
UNION ALL SELECT 'I15', 'exposure', 'Exactly one BASELINE scenario per factor (factors whose count differs from 1)', 0,
       (SELECT count(*) FROM (SELECT factor FROM out_i1_scenarios WHERE scenario_class = 'BASELINE' GROUP BY factor HAVING count(*) <> 1)), 0
-- ---- S: sign categories (budget / forecast / prior year populations) ------------------------------------------------
UNION ALL SELECT 'S01', 'sign_category', 'Budget population: SAME + OPPOSITE + ZERO_INVOLVED + MISSING lines = variance population (55,043)', 55043,
       (SELECT count(*) FROM v_pl_budget WHERE sign_cat_ab IN ('SAME_SIGN_NONZERO', 'OPPOSITE_SIGN_NONZERO', 'ZERO_INVOLVED', 'MISSING_OR_UNAVAILABLE')), 0
UNION ALL SELECT 'S02', 'sign_category', 'Budget population: zero-involved lines recounted from fact_close (actual or budget = 0)',
       (SELECT count(*) FROM p WHERE b IS NOT NULL AND (a = 0 OR b = 0)), (SELECT count(*) FROM v_pl_budget WHERE sign_cat_ab = 'ZERO_INVOLVED'), 0
UNION ALL SELECT 'S03', 'sign_category', 'Budget population: opposite-sign non-zero lines recounted from fact_close',
       (SELECT count(*) FROM p WHERE b IS NOT NULL AND a <> 0 AND b <> 0 AND sign(a) <> sign(b)), (SELECT count(*) FROM v_pl_budget WHERE sign_cat_ab = 'OPPOSITE_SIGN_NONZERO'), 0
UNION ALL SELECT 'S04', 'sign_category', 'Forecast population: the four categories cover every line (lines outside the four)', 0,
       (SELECT count(*) FROM v_pl_forecast WHERE sign_cat_af NOT IN ('SAME_SIGN_NONZERO', 'OPPOSITE_SIGN_NONZERO', 'ZERO_INVOLVED', 'MISSING_OR_UNAVAILABLE')), 0
UNION ALL SELECT 'S05', 'sign_category', 'Prior-year population: SAME + OPPOSITE + ZERO_INVOLVED lines = population (no line is MISSING by construction)',
       (SELECT count(*) FROM v_pl_prior), (SELECT count(*) FROM v_pl_prior WHERE sign_cat_ap IN ('SAME_SIGN_NONZERO', 'OPPOSITE_SIGN_NONZERO', 'ZERO_INVOLVED')), 0
UNION ALL SELECT 'S06', 'sign_category', 'out_c2: rows over categories = forecast population rows (four operating + other sections)',
       (SELECT count(*) FROM v_pl_forecast), (SELECT sum(rows_in_category) FROM out_c2_error_attribution), 0
-- ---- structural guards -------------------------------------------------------------------------------------------------
UNION ALL SELECT 'F06', 'cost', 'Top-3 concentration share is built from exactly three members per dimension (dimensions where it is not)', 0,
       (SELECT count(*) FROM out_f2_concentration WHERE members >= 3 AND top3_members <> 3), 0
UNION ALL SELECT 'G05', 'trend', 'Anomaly scan: every month has a class; months classed "not scorable" are reported, not hidden (months with NULL class)', 0,
       (SELECT count(*) FROM out_g6_anomaly_scan WHERE anomaly_class IS NULL), 0
UNION ALL SELECT 'B15', 'variance', 'Contribution sensitivity (b9) at the lowest threshold covers no more than 100% of total absolute variance (violations)', 0,
       (SELECT count(*) FROM out_b9_contribution_sensitivity WHERE share_of_total_abs_variance_covered > 1 + 1e-9), 0
UNION ALL SELECT 'B16', 'variance', 'Budget-percentage sensitivity (b11): scored + unscored cells = all cells per scenario and threshold (violations)', 0,
       (SELECT count(*) FROM out_b11_budget_pct_sensitivity WHERE cells_total < cells_at_or_above + cells_not_scored), 0
UNION ALL SELECT 'B17', 'variance', 'Top-10 overlap uses exactly ten cells per scenario (cells_in_both_top10 <= 10)', 0,
       (SELECT count(*) FROM out_b10_top_cells_overlap WHERE cells_in_both_top10 > 10), 0
UNION ALL SELECT 'B18', 'variance', 'out_b7 sign-category profile: rows over categories = ALL_LINES rows in out_b1 (all sections)', (SELECT sum(rows_in_scope) FROM out_b1_variance_section WHERE scenario = 'ALL_LINES'),
       (SELECT sum(rows_in_category) FROM out_b7_sign_category_profile), 0
UNION ALL SELECT 'B19', 'variance', 'out_b7 sign-category profile: net variance over categories = ALL_LINES net variance in out_b1', (SELECT sum(net_variance_usd) FROM out_b1_variance_section WHERE scenario = 'ALL_LINES'),
       (SELECT sum(variance_usd) FROM out_b7_sign_category_profile), 0.01
UNION ALL SELECT 'B20', 'variance', 'out_b7 sign-category profile: row shares sum to 1 for every GL account (accounts where they do not)', 0,
       (SELECT count(*) FROM (SELECT gl_account FROM out_b7_sign_category_profile GROUP BY gl_account HAVING abs(sum(share_of_gl_rows) - 1) > 1e-9)), 0
)
SELECT check_id, area, description, expected::DOUBLE AS expected, actual::DOUBLE AS actual, (actual - expected)::DOUBLE AS difference,
       tolerance::DOUBLE AS tolerance,
       CASE WHEN abs(actual - expected) <= tolerance THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_id;
