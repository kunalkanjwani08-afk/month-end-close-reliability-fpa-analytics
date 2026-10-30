-- =====================================================================================================
-- 05  Actual versus forecast (analysis C)
-- Population : v_pl_forecast = eligible P&L rows with a forecast amount (project convention, see 01)
-- Definitions: forecast error      = Forecast - Actual   (positive = forecast ABOVE actual)
--              bias                = SUM(Forecast - Actual) / SUM(ABS(Actual))
--              WAPE                = SUM(ABS(Forecast - Actual)) / SUM(ABS(Actual))
--              WAPE is used because MAPE is undefined for zero actuals and distorted by the opposite-sign
--              and tiny lines that exist in this extract. WAPE weights large lines more (strength) and
--              hides which lines are wrong (limit - hence the cell tables below).
-- Limitation : the extract has NO forecast version, as-of date or snapshot. Whether a forecast was made
--              before or after the period closed is unknown, so these are COMPARISONS of two columns,
--              not a validated forecast-accuracy assessment. The scenarios mirror 04 (ALL_LINES = scale-adjusted amounts, signs as
--              recorded; SAME_SIGN_ONLY; OPPOSITE_SIGN_ONLY; ZERO_INVOLVED_ONLY; see sign_cat in 01).
-- =====================================================================================================

CREATE OR REPLACE VIEW v_fc_scn AS
SELECT s.scenario, v.row_id, v.entity_code, v.division, v.gl_account, v.account_name, v.section, v.section_order,
       v.period_ym, v.period_year, v.period_quarter,
       v.actual_usd_adj AS actual, v.forecast_usd_adj AS forecast,
       v.forecast_usd_adj - v.actual_usd_adj AS error, v.sign_cat_af
FROM v_pl_forecast v
JOIN scn_sign s ON s.scenario = 'ALL_LINES' OR s.sign_category = v.sign_cat_af;

-- C1  Forecast error by section and scenario
CREATE OR REPLACE TABLE out_c1_forecast_section AS
SELECT scenario, section, section_order, count(*) AS rows_in_scope,
       sum(actual) AS actual_usd, sum(forecast) AS forecast_usd, sum(error) AS net_error_usd,
       sum(abs(error)) AS abs_error_usd, sum(abs(actual)) AS abs_actual_usd,
       sum(error) / NULLIF(sum(abs(actual)), 0)      AS bias,
       sum(abs(error)) / NULLIF(sum(abs(actual)), 0) AS wape
FROM v_fc_scn GROUP BY ALL;

-- C2  Where does the error come from? Share of lines versus share of absolute error, by sign category of
--     (actual, forecast). An opposite-sign line is an observation, not a proven defect.
CREATE OR REPLACE TABLE out_c2_error_attribution AS
SELECT section, section_order, sign_cat_af AS sign_category,
       count(*) AS rows_in_category,
       count(*)::DOUBLE / sum(count(*)) OVER (PARTITION BY section) AS share_of_rows,
       sum(abs(error)) AS abs_error_usd,
       sum(abs(error)) / NULLIF(sum(sum(abs(error))) OVER (PARTITION BY section), 0) AS share_of_abs_error,
       sum(abs(actual)) AS abs_actual_usd
FROM v_fc_scn WHERE scenario = 'ALL_LINES' GROUP BY section, section_order, sign_cat_af;

-- C3  Entity x section forecast error (both scenarios)
CREATE OR REPLACE TABLE out_c3_forecast_entity AS
SELECT scenario, entity_code, section, section_order, count(*) AS rows_in_scope,
       sum(error) / NULLIF(sum(abs(actual)), 0) AS bias, sum(abs(error)) / NULLIF(sum(abs(actual)), 0) AS wape,
       sum(error) AS net_error_usd
FROM v_fc_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL;

-- C4  Trend of forecast error by quarter (does accuracy improve or deteriorate?)
CREATE OR REPLACE TABLE out_c4_forecast_quarter AS
SELECT scenario, period_quarter, section, section_order, count(*) AS rows_in_scope,
       sum(error) / NULLIF(sum(abs(actual)), 0) AS bias, sum(abs(error)) / NULLIF(sum(abs(actual)), 0) AS wape,
       sum(error) AS net_error_usd
FROM v_fc_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') AND section IN ('REVENUE', 'COGS', 'PEOPLE', 'OPEX') GROUP BY ALL;

-- C5  Persistence of bias: quarters (of 12) in which the section bias has the same direction (same-sign view)
CREATE OR REPLACE TABLE out_c5_bias_persistence AS
SELECT scenario, section, section_order, count(*) AS quarters,
       count(*) FILTER (WHERE bias > 0) AS quarters_forecast_above_actual,
       count(*) FILTER (WHERE bias < 0) AS quarters_forecast_below_actual,
       avg(bias) AS mean_quarter_bias, stddev_samp(bias) AS sd_quarter_bias
FROM out_c4_forecast_quarter GROUP BY ALL;

-- C6  Forecast versus budget as predictors of actual, on rows where actual, budget and forecast are all present
--     and all three signs agree (so both errors are measured on the same rows)
CREATE OR REPLACE TABLE out_c6_forecast_vs_budget AS
SELECT section, section_order, count(*) AS rows_compared,
       sum(abs(forecast_usd_adj - actual_usd_adj)) / sum(abs(actual_usd_adj)) AS wape_forecast,
       sum(abs(budget_usd_adj   - actual_usd_adj)) / sum(abs(actual_usd_adj)) AS wape_budget,
       sum(forecast_usd_adj - actual_usd_adj) / sum(abs(actual_usd_adj)) AS bias_forecast,
       sum(budget_usd_adj   - actual_usd_adj) / sum(abs(actual_usd_adj)) AS bias_budget
FROM v_pl_budget
WHERE forecast_usd_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO' AND sign_cat_af = 'SAME_SIGN_NONZERO'
GROUP BY section, section_order;

-- C7  Entity x GL cells with unusually large forecast error (same-sign view; robust z of the cell WAPE
--     against all cells with >= 20 rows; flagged for review, an outlier is not an error)
CREATE OR REPLACE TABLE out_c7_forecast_error_cells AS
WITH c AS (
    SELECT entity_code, gl_account, any_value(account_name) AS account_name, count(*) AS n,
           sum(error) AS net_error, sum(abs(error)) AS abs_error, sum(abs(actual)) AS abs_actual,
           sum(abs(error)) / NULLIF(sum(abs(actual)), 0) AS wape, sum(error) / NULLIF(sum(abs(actual)), 0) AS bias
    FROM v_fc_scn WHERE scenario = 'SAME_SIGN_ONLY' GROUP BY entity_code, gl_account HAVING count(*) >= 20),
m AS (SELECT median(wape) AS med, median(abs(wape - (SELECT median(wape) FROM c))) AS mad FROM c)
SELECT c.*, robust_z(c.wape, m.med, m.mad) AS robust_z_wape,
       CASE WHEN robust_z(c.wape, m.med, m.mad) IS NULL THEN 'not scorable (MAD = 0 or undefined)'
            WHEN abs(robust_z(c.wape, m.med, m.mad)) >= 3 THEN 'flag for review'
            ELSE 'within range' END AS z_status,
       row_number() OVER (ORDER BY abs(net_error) DESC, entity_code, gl_account) AS rank_abs_net_error
FROM c CROSS JOIN m;

-- C8  Forecast-implied profit proxy bias on rows where actual, budget and forecast signs all agree.
--     Proxy = REVENUE - COGS - PEOPLE - OPEX under the positive-magnitude cost convention (R9 unresolved).
CREATE OR REPLACE TABLE out_c8_profit_proxy_bias AS
WITH r AS (
    SELECT section, period_year, actual_usd_adj AS a, budget_usd_adj AS b, forecast_usd_adj AS f
    FROM v_pl_budget WHERE forecast_usd_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO' AND sign_cat_af = 'SAME_SIGN_NONZERO'
      AND section IN ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')),
y AS (
    SELECT period_year,
           sum(a) FILTER (WHERE section = 'REVENUE') - sum(a) FILTER (WHERE section <> 'REVENUE') AS actual_result,
           sum(b) FILTER (WHERE section = 'REVENUE') - sum(b) FILTER (WHERE section <> 'REVENUE') AS budget_result,
           sum(f) FILTER (WHERE section = 'REVENUE') - sum(f) FILTER (WHERE section <> 'REVENUE') AS forecast_result,
           sum(a) FILTER (WHERE section = 'REVENUE') AS actual_revenue
    FROM r GROUP BY period_year)
SELECT period_year, actual_revenue, actual_result AS actual_result_proxy_usd, budget_result AS budget_result_proxy_usd,
       forecast_result AS forecast_result_proxy_usd,
       forecast_result - actual_result AS forecast_minus_actual_usd,
       budget_result - actual_result   AS budget_minus_actual_usd
FROM y
UNION ALL
SELECT NULL, sum(actual_revenue), sum(actual_result), sum(budget_result), sum(forecast_result),
       sum(forecast_result - actual_result), sum(budget_result - actual_result) FROM y;
