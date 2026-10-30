-- =====================================================================================================
-- 04  Actual versus budget (analysis B)
-- Population : v_pl_budget  = eligible P&L rows with actual AND budget present (55,043 rows)
-- Definitions: Variance = Actual - Budget (signed, USD, provisional scale-adjusted amounts)
--              Variance % = Variance / ABS(Budget total)   (project convention R10, NOT an accounting
--              standard). Budget total of 0 or NULL -> NULL percentage, never 0 or infinity.
-- Scenarios  : ALL_LINES          every line in the population. Amounts are the PROVISIONAL scale-adjusted USD amounts
--                                  with signs exactly as recorded (renamed from AS_REPORTED: the amounts are not the
--                                  unadjusted parsed ones)
--              SAME_SIGN_ONLY     lines where actual and budget are both non-zero and have the same sign
--              OPPOSITE_SIGN_ONLY lines where actual and budget are both non-zero and have opposite signs
--              ZERO_INVOLVED_ONLY lines where actual or budget (or both) equals 0 - no sign to compare
--              (a fifth category, MISSING_OR_UNAVAILABLE, is empty here because the population requires both amounts.)
--              These are SENSITIVITIES. Signs are never flipped or repaired (R9 unresolved) and an opposite-sign line
--              is NOT classified as an error: credit notes, reversals and contra accounts can legitimately differ.
--              ALL_LINES = SAME_SIGN_ONLY + OPPOSITE_SIGN_ONLY + ZERO_INVOLVED_ONLY exactly (bridge in out_b8).
-- Direction  : no row is labelled favourable/adverse. 'Actual above budget' is arithmetic only.
-- =====================================================================================================

CREATE OR REPLACE TABLE scn_sign AS
SELECT * FROM (VALUES ('ALL_LINES', 1, NULL), ('SAME_SIGN_ONLY', 2, 'SAME_SIGN_NONZERO'),
                      ('OPPOSITE_SIGN_ONLY', 3, 'OPPOSITE_SIGN_NONZERO'), ('ZERO_INVOLVED_ONLY', 4, 'ZERO_INVOLVED'))
       AS t(scenario, scenario_order, sign_category);

-- Row set for the scenarios: one copy of each variance row per scenario it belongs to.
CREATE OR REPLACE VIEW v_var_scn AS
SELECT s.scenario, v.row_id, v.entity_code, v.division, v.gl_account, v.account_name, v.section, v.section_order,
       v.period_ym, v.period_year, v.period_month,
       v.actual_usd_adj AS actual, v.budget_usd_adj AS budget,
       v.actual_usd_adj - v.budget_usd_adj AS variance,
       v.sign_cat_ab
FROM v_pl_budget v
JOIN scn_sign s ON s.scenario = 'ALL_LINES' OR s.sign_category = v.sign_cat_ab;

-- B1  Variance by section and scenario. Net AND gross (gross = sum of absolute cell variances, where a
--     cell = entity x GL x period) so offsetting cells cannot hide a large underlying movement.
CREATE OR REPLACE TABLE out_b1_variance_section AS
WITH cell AS (
    SELECT scenario, section, section_order, entity_code, gl_account, period_ym,
           sum(actual) AS actual, sum(budget) AS budget, sum(variance) AS variance, count(*) AS n
    FROM v_var_scn GROUP BY ALL)
SELECT scenario, section, section_order, sum(n) AS rows_in_scope,
       sum(actual) AS actual_usd, sum(budget) AS budget_usd, sum(variance) AS net_variance_usd,
       sum(abs(variance)) AS gross_cell_variance_usd,
       safe_pct(sum(variance), sum(budget), sum(abs(budget))) AS variance_pct_of_abs_budget,
       abs(sum(budget)) / NULLIF(sum(abs(budget)), 0)         AS budget_netting_ratio,
       sum(abs(variance)) / NULLIF(sum(abs(budget)), 0)       AS gross_variance_pct_of_abs_cell_budget
FROM cell GROUP BY scenario, section, section_order;

-- B2  Entity x GL contributions (3-year totals) with contribution to the section net variance, only when
--     the section net is large enough (>= 5% of the section gross) for a share to be meaningful.
CREATE OR REPLACE TABLE out_b2_variance_entity_gl AS
WITH c AS (
    SELECT scenario, section, section_order, entity_code, gl_account, any_value(account_name) AS account_name,
           count(*) AS rows_in_scope, sum(actual) AS actual_usd, sum(budget) AS budget_usd, sum(variance) AS variance_usd,
           sum(abs(budget)) AS abs_budget_usd
    FROM v_var_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL),
t AS (
    SELECT *, sum(variance_usd) OVER (PARTITION BY scenario, section) AS section_net,
           sum(abs(variance_usd)) OVER (PARTITION BY scenario, section) AS section_gross_cells
    FROM c)
SELECT scenario, section, entity_code, gl_account, account_name, rows_in_scope, actual_usd, budget_usd, variance_usd,
       safe_pct(variance_usd, budget_usd, abs_budget_usd) AS variance_pct_of_abs_budget,
       abs(variance_usd) / NULLIF(section_gross_cells, 0) AS share_of_section_gross,
       CASE WHEN abs(section_net) >= 0.05 * section_gross_cells THEN variance_usd / section_net END AS share_of_section_net,
       CASE WHEN abs(section_net) >= 0.05 * section_gross_cells THEN 'net share meaningful'
            ELSE 'net share suppressed (section net < 5% of gross: offsetting cells)' END AS net_share_note,
       rank() OVER (PARTITION BY scenario, section ORDER BY abs(variance_usd) DESC) AS rank_abs_in_section
FROM t;

-- B3  Division x section
CREATE OR REPLACE TABLE out_b3_variance_division AS
SELECT scenario, division, section, section_order, count(*) AS rows_in_scope, sum(actual) AS actual_usd,
       sum(budget) AS budget_usd, sum(variance) AS variance_usd,
       safe_pct(sum(variance), sum(budget), sum(abs(budget))) AS variance_pct_of_abs_budget
FROM v_var_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL;

-- B4  Monthly variance by section and scenario
CREATE OR REPLACE TABLE out_b4_variance_monthly AS
SELECT scenario, period_ym, section, section_order, count(*) AS rows_in_scope, sum(actual) AS actual_usd,
       sum(budget) AS budget_usd, sum(variance) AS variance_usd,
       safe_pct(sum(variance), sum(budget), sum(abs(budget))) AS variance_pct_of_abs_budget
FROM v_var_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL;

-- B5  How volatile is the monthly variance %, and does the volatility survive the sign control?
CREATE OR REPLACE TABLE out_b5_variance_volatility AS
SELECT scenario, section, section_order, count(*) AS months,
       avg(variance_pct_of_abs_budget) AS mean_pct, stddev_samp(variance_pct_of_abs_budget) AS sd_pct,
       min(variance_pct_of_abs_budget) AS min_pct, max(variance_pct_of_abs_budget) AS max_pct,
       count(*) FILTER (WHERE variance_usd > 0) AS months_actual_above_budget,
       count(*) FILTER (WHERE variance_usd < 0) AS months_actual_below_budget
FROM out_b4_variance_monthly GROUP BY ALL;

-- B6  Persistence: in how many of the 36 months is the sign of the section variance the same,
--     by entity and by division, on the same-sign sensitivity (the stable view) and as reported.
CREATE OR REPLACE TABLE out_b6_variance_persistence AS
WITH m AS (
    SELECT scenario, 'entity' AS dim, entity_code AS member, section, section_order, period_ym,
           sum(variance) AS variance, sum(budget) AS budget
    FROM v_var_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL
    UNION ALL
    SELECT scenario, 'division', division, section, section_order, period_ym, sum(variance), sum(budget)
    FROM v_var_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL
    UNION ALL
    SELECT scenario, 'gl_account', gl_account::VARCHAR, section, section_order, period_ym, sum(variance), sum(budget)
    FROM v_var_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL)
SELECT scenario, dim, member, section, section_order, count(*) AS months_with_data,
       count(*) FILTER (WHERE variance > 0) AS months_above_budget,
       count(*) FILTER (WHERE variance < 0) AS months_below_budget,
       greatest(count(*) FILTER (WHERE variance > 0), count(*) FILTER (WHERE variance < 0))::DOUBLE / count(*) AS share_months_dominant_direction,
       safe_pct(sum(variance), sum(budget), sum(abs(budget))) AS variance_pct_of_abs_budget
FROM m GROUP BY ALL;

-- B7  Profile of the sign categories: where they are, how large, and what they do to the variance.
--     One row per section x GL x sign category (ALL_LINES basis); shares are within the GL.
CREATE OR REPLACE TABLE out_b7_sign_category_profile AS
SELECT section, section_order, gl_account, any_value(account_name) AS account_name, sign_cat_ab AS sign_category,
       count(*) AS rows_in_category,
       count(*)::DOUBLE / sum(count(*)) OVER (PARTITION BY gl_account) AS share_of_gl_rows,
       sum(abs(actual)) / NULLIF(sum(sum(abs(actual))) OVER (PARTITION BY gl_account), 0) AS share_of_gl_abs_actual,
       sum(variance) AS variance_usd,
       sum(abs(variance)) / NULLIF(sum(sum(abs(variance))) OVER (PARTITION BY gl_account), 0) AS share_of_gl_row_abs_variance
FROM v_var_scn WHERE scenario = 'ALL_LINES' GROUP BY section, section_order, gl_account, sign_cat_ab;

-- B8  Bridge: ALL_LINES net variance = SAME_SIGN + OPPOSITE_SIGN + ZERO_INVOLVED (reconciliation identity)
CREATE OR REPLACE TABLE out_b8_variance_bridge AS
SELECT section, section_order,
       max(net_variance_usd) FILTER (WHERE scenario = 'ALL_LINES')          AS all_lines_net_variance_usd,
       max(net_variance_usd) FILTER (WHERE scenario = 'SAME_SIGN_ONLY')     AS same_sign_net_variance_usd,
       max(net_variance_usd) FILTER (WHERE scenario = 'OPPOSITE_SIGN_ONLY') AS opposite_sign_net_variance_usd,
       max(net_variance_usd) FILTER (WHERE scenario = 'ZERO_INVOLVED_ONLY') AS zero_involved_net_variance_usd,
       max(net_variance_usd) FILTER (WHERE scenario = 'ALL_LINES')
         - coalesce(max(net_variance_usd) FILTER (WHERE scenario = 'SAME_SIGN_ONLY'), 0)
         - coalesce(max(net_variance_usd) FILTER (WHERE scenario = 'OPPOSITE_SIGN_ONLY'), 0)
         - coalesce(max(net_variance_usd) FILTER (WHERE scenario = 'ZERO_INVOLVED_ONLY'), 0) AS bridge_difference_usd
FROM out_b1_variance_section GROUP BY section, section_order;

-- B9  Contribution sensitivity (renamed from "materiality"): how many entity x GL cells each contribute at least a
--     given SHARE OF THE TOTAL ABSOLUTE CELL VARIANCE of the scenario (all P&L sections together)? The thresholds are
--     shares of total variance, NOT percentages of budget and NOT accounting materiality standards; they are project
--     analytical conventions. The budget-percentage view is the separate table out_b11_budget_pct_sensitivity.
CREATE OR REPLACE TABLE out_b9_contribution_sensitivity AS
WITH c AS (
    SELECT scenario, entity_code, gl_account, sum(variance) AS v FROM v_var_scn
    WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL),
t AS (SELECT *, abs(v) / sum(abs(v)) OVER (PARTITION BY scenario) AS share_of_total_abs_variance FROM c),
th AS (SELECT unnest([0.0025, 0.005, 0.01, 0.02, 0.05]) AS threshold_share_of_total_abs_variance)
SELECT scenario, threshold_share_of_total_abs_variance, count(*) FILTER (WHERE share_of_total_abs_variance >= threshold_share_of_total_abs_variance) AS cells_at_or_above,
       sum(share_of_total_abs_variance) FILTER (WHERE share_of_total_abs_variance >= threshold_share_of_total_abs_variance) AS share_of_total_abs_variance_covered
FROM t CROSS JOIN th GROUP BY scenario, threshold_share_of_total_abs_variance;

-- B10 Overlap of the top-10 cells (largest absolute net cell variance) between ALL_LINES and SAME_SIGN_ONLY.
--     row_number() with a deterministic tie-break gives exactly ten cells per scenario (rank() could return more).
CREATE OR REPLACE TABLE out_b10_top_cells_overlap AS
WITH r AS (
    SELECT scenario, entity_code, gl_account, sum(variance) AS v,
           row_number() OVER (PARTITION BY scenario ORDER BY abs(sum(variance)) DESC, entity_code, gl_account) AS rk
    FROM v_var_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY scenario, entity_code, gl_account)
SELECT 10 AS top_n,
       (SELECT count(*) FROM r a JOIN r b USING (entity_code, gl_account)
        WHERE a.scenario = 'ALL_LINES' AND b.scenario = 'SAME_SIGN_ONLY' AND a.rk <= 10 AND b.rk <= 10) AS cells_in_both_top10,
       (SELECT string_agg(entity_code || '/' || gl_account::VARCHAR, ', ' ORDER BY rk) FROM r WHERE scenario = 'ALL_LINES' AND rk <= 10) AS top10_all_lines,
       (SELECT string_agg(entity_code || '/' || gl_account::VARCHAR, ', ' ORDER BY rk) FROM r WHERE scenario = 'SAME_SIGN_ONLY' AND rk <= 10) AS top10_same_sign;

-- B11 Budget-percentage sensitivity: entity x GL cells (3-year totals) whose variance is at least a given PERCENTAGE OF
--     THE CELL'S ABSOLUTE BUDGET. Denominator = sum of absolute budget lines of the cell (gross budget), so positive and
--     negative budget lines cannot cancel; a cell with zero or missing gross budget is not scored (cells_not_scored).
--     Also shows the share of total absolute variance sitting in the flagged cells. Project analytical conventions,
--     not accounting materiality standards.
CREATE OR REPLACE TABLE out_b11_budget_pct_sensitivity AS
WITH c AS (
    SELECT scenario, entity_code, gl_account, sum(variance) AS v, sum(abs(budget)) AS gross_budget
    FROM v_var_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL),
t AS (SELECT *, abs(v) / NULLIF(gross_budget, 0) AS pct_of_gross_budget,
             abs(v) / sum(abs(v)) OVER (PARTITION BY scenario) AS share_of_total_abs_variance FROM c),
th AS (SELECT unnest([0.005, 0.01, 0.02, 0.05, 0.10]) AS threshold_pct_of_gross_budget)
SELECT scenario, threshold_pct_of_gross_budget,
       count(*) FILTER (WHERE pct_of_gross_budget >= threshold_pct_of_gross_budget) AS cells_at_or_above,
       count(*) FILTER (WHERE pct_of_gross_budget IS NULL) AS cells_not_scored,
       count(*) AS cells_total,
       sum(share_of_total_abs_variance) FILTER (WHERE pct_of_gross_budget >= threshold_pct_of_gross_budget) AS share_of_total_abs_variance_in_flagged_cells
FROM t CROSS JOIN th GROUP BY scenario, threshold_pct_of_gross_budget;
