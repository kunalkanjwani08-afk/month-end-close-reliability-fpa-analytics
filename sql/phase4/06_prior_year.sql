-- =====================================================================================================
-- 06  Actual versus prior year (analysis D)
-- Two different things are called "prior year" and are kept apart:
--   (1) the PRIOR_YEAR_USD COLUMN on each line (what the source system says last year was), and
--   (2) the dataset's OWN actuals of the previous calendar year (what the extract can verify).
-- Percent change = (Actual - PY) / ABS(PY total), guarded by safe_pct (01). The extract starts in
-- 2023-01, so 2023 has no earlier actuals inside the file: the 2023 prior-year column cannot be verified.
-- =====================================================================================================

CREATE OR REPLACE VIEW v_py_scn AS
SELECT s.scenario, v.row_id, v.entity_code, v.division, v.gl_account, v.section, v.section_order, v.period_ym,
       v.period_year, v.period_month, v.actual_usd_adj AS actual, v.prior_year_usd_adj AS py,
       v.actual_usd_adj - v.prior_year_usd_adj AS change, v.sign_cat_ap
FROM v_pl_prior v
JOIN scn_sign s ON s.scenario = 'ALL_LINES' OR s.sign_category = v.sign_cat_ap;

-- D1  Actual versus the prior-year COLUMN by year and section
CREATE OR REPLACE TABLE out_d1_vs_py_column AS
SELECT scenario, period_year, section, section_order, count(*) AS rows_in_scope, sum(actual) AS actual_usd, sum(py) AS prior_year_usd,
       sum(change) AS change_usd, safe_pct(sum(change), sum(py), sum(abs(py))) AS change_pct_of_abs_py
FROM v_py_scn WHERE scenario IN ('ALL_LINES', 'SAME_SIGN_ONLY') GROUP BY ALL;

-- D2  Is the implied growth uniform? Spread of the implied growth across entities, divisions and GLs
--     (same-sign view; 3-year totals)
CREATE OR REPLACE TABLE out_d2_py_growth_spread AS
WITH g AS (
    SELECT 'entity' AS dim, entity_code AS member, section, sum(change) / sum(py) AS growth, count(*) AS n FROM v_py_scn WHERE scenario = 'SAME_SIGN_ONLY' GROUP BY ALL
    UNION ALL SELECT 'division', division, section, sum(change) / sum(py), count(*) FROM v_py_scn WHERE scenario = 'SAME_SIGN_ONLY' GROUP BY ALL
    UNION ALL SELECT 'gl_account', gl_account::VARCHAR, section, sum(change) / sum(py), count(*) FROM v_py_scn WHERE scenario = 'SAME_SIGN_ONLY' GROUP BY ALL)
SELECT dim, count(*) AS members, min(growth) AS min_growth, max(growth) AS max_growth, avg(growth) AS mean_growth,
       stddev_samp(growth) AS sd_growth
FROM g WHERE n >= 100 GROUP BY dim;

-- D3  What the extract itself can verify: actual year-on-year growth from the dataset's own actuals, on three
--     bases (the choice of basis changes the answer, which is itself a finding).
--       POSTED_SIGNED : eligible (Posted-only) rows, signed as reported
--       ANY_STATUS_ABS: all statuses, absolute amounts (volume proxy that does not depend on sign errors)
--       ANY_STATUS_SIGNED: all statuses, signed as reported
CREATE OR REPLACE TABLE out_d3_true_yoy AS
WITH b AS (
    SELECT 'POSTED_SIGNED' AS basis, section, section_order, period_year, sum(actual_usd_adj) AS amt, count(*) AS n FROM v_pl_actual GROUP BY ALL
    UNION ALL SELECT 'ANY_STATUS_ABS', section, section_order, period_year, sum(abs(actual_usd_adj)), count(*) FROM v_pl_actual_any_status GROUP BY ALL
    UNION ALL SELECT 'ANY_STATUS_SIGNED', section, section_order, period_year, sum(actual_usd_adj), count(*) FROM v_pl_actual_any_status GROUP BY ALL)
SELECT c.basis, c.section, c.section_order, c.period_year, c.amt AS amount_usd, p.amt AS prior_calendar_year_usd,
       c.n AS rows_in_year, p.n AS rows_prior_year,
       safe_pct(c.amt - p.amt, p.amt, abs(p.amt)) AS yoy_growth
FROM b c LEFT JOIN b p ON p.basis = c.basis AND p.section = c.section AND p.period_year = c.period_year - 1;

-- D4  Does the prior-year COLUMN reconcile with the dataset's own previous-year actuals?
--     Same population on both sides (Posted-only eligible rows), revenue and each cost section, per year.
CREATE OR REPLACE TABLE out_d4_py_column_reconciliation AS
WITH col AS (SELECT section, section_order, period_year, sum(prior_year_usd_adj) AS py_column FROM v_pl_prior GROUP BY ALL),
act AS (SELECT section, period_year + 1 AS period_year, sum(actual_usd_adj) AS prev_year_actual FROM v_pl_actual GROUP BY ALL)
SELECT c.section, c.section_order, c.period_year, c.py_column, a.prev_year_actual,
       c.py_column - a.prev_year_actual AS difference_usd,
       c.py_column / NULLIF(a.prev_year_actual, 0) - 1 AS difference_pct
FROM col c JOIN act a USING (section, period_year);

-- D5  Small-baseline growth warning: entity x GL x month cells where the baseline is tiny so that a growth
--     percentage is not informative. Baseline smaller than 5% of the median cell baseline of the same GL.
CREATE OR REPLACE TABLE out_d5_small_baseline AS
WITH c AS (
    SELECT entity_code, gl_account, period_ym, sum(actual) AS actual, sum(py) AS py
    FROM v_py_scn WHERE scenario = 'ALL_LINES' GROUP BY ALL),
m AS (SELECT *, median(abs(py)) OVER (PARTITION BY gl_account) AS med_abs_py FROM c)
SELECT count(*) AS cells,
       count(*) FILTER (WHERE abs(py) < 0.05 * med_abs_py) AS cells_with_small_baseline,
       count(*) FILTER (WHERE abs(py) < 0.05 * med_abs_py AND abs(actual - py) / NULLIF(abs(py), 0) > 1) AS small_baseline_cells_showing_over_100pct_change,
       count(*) FILTER (WHERE abs(py) >= 0.05 * med_abs_py AND abs(actual - py) / NULLIF(abs(py), 0) > 1) AS normal_baseline_cells_over_100pct_change
FROM m;
