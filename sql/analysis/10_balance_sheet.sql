-- =====================================================================================================
-- 10  Balance Sheet statement lines - measurement basis UNRESOLVED (analysis H) - kept completely separate from the P&L (rule R2)
-- Population : v_bs_actual = eligible Balance Sheet lines (Posted-only provisional rule, 2,953 rows)
-- The extract does not say whether a Balance Sheet line is an opening balance, closing balance or a
-- movement, and several lines exist for the same entity x account x period. This file therefore
-- DESCRIBES coverage and behaviour and tests whether the lines behave like point-in-time balances.
-- Balances are NEVER summed across periods. Nothing here is a working-capital metric.
-- =====================================================================================================

-- H1  Coverage: entity x account x period cells with at least one eligible line
CREATE OR REPLACE TABLE out_h1_bs_coverage AS
WITH spine AS (
    SELECT e.entity_code, a.gl_account, p.period_ym
    FROM (SELECT DISTINCT entity_code FROM v_bs_actual) e
    CROSS JOIN (SELECT gl_account FROM dim_account WHERE section = 'BALANCE_SHEET') a
    CROSS JOIN (SELECT DISTINCT period_ym FROM fact_close WHERE period_ym IS NOT NULL) p),
c AS (SELECT s.entity_code, s.gl_account, s.period_ym, count(v.row_id) AS lines FROM spine s
      LEFT JOIN v_bs_actual v USING (entity_code, gl_account, period_ym) GROUP BY ALL)
SELECT count(*) AS cells_possible, count(*) FILTER (WHERE lines > 0) AS cells_with_a_line,
       count(*) FILTER (WHERE lines > 0)::DOUBLE / count(*) AS coverage,
       count(*) FILTER (WHERE lines > 1) AS cells_with_multiple_lines,
       count(*) FILTER (WHERE lines > 1)::DOUBLE / NULLIF(count(*) FILTER (WHERE lines > 0), 0) AS share_of_populated_cells_with_multiple_lines,
       max(lines) AS max_lines_in_a_cell
FROM c;

-- H2  Magnitude and sign by account
CREATE OR REPLACE TABLE out_h2_bs_by_account AS
SELECT gl_account, any_value(account_name) AS account_name, count(*) AS lines,
       median(abs(actual_usd_adj)) AS median_abs_usd, quantile_cont(abs(actual_usd_adj), 0.95) AS p95_abs_usd,
       avg(CASE WHEN actual_usd_adj < 0 THEN 1.0 ELSE 0.0 END) AS share_lines_negative,
       sum(actual_usd_adj) AS signed_sum_of_lines_usd_not_a_balance
FROM v_bs_actual GROUP BY gl_account;

-- H3  Do multiple lines in one cell look like repeated snapshots of the same balance? (max/min magnitude ratio)
CREATE OR REPLACE TABLE out_h3_bs_multi_line_spread AS
WITH c AS (SELECT entity_code, gl_account, period_ym, count(*) AS lines, max(abs(actual_usd_adj)) AS mx, min(abs(actual_usd_adj)) AS mn
           FROM v_bs_actual GROUP BY ALL HAVING count(*) > 1)
SELECT lines, count(*) AS cells, median(mx / NULLIF(mn, 0)) AS median_max_over_min,
       count(*) FILTER (WHERE mx / NULLIF(mn, 0) <= 1.05)::DOUBLE / count(*) AS share_cells_within_5pct
FROM c GROUP BY lines;

-- H4  Per-period line totals by account (measurement basis unresolved: not asserted to be period-end balances) (descriptive, per period, never cumulated) and their month-on-month
--     coefficient of variation - a plausibility test for "balance" behaviour
CREATE OR REPLACE TABLE out_h4_bs_period_totals AS
SELECT period_ym, gl_account, any_value(account_name) AS account_name, count(*) AS lines, sum(actual_usd_adj) AS signed_line_total_usd
FROM v_bs_actual GROUP BY period_ym, gl_account;

CREATE OR REPLACE TABLE out_h5_bs_volatility AS
WITH t AS (SELECT gl_account, period_ym, signed_line_total_usd,
                  signed_line_total_usd / NULLIF(lag(signed_line_total_usd) OVER (PARTITION BY gl_account ORDER BY period_ym), 0) - 1 AS mom_change
           FROM out_h4_bs_period_totals)
SELECT gl_account, count(*) AS periods, avg(signed_line_total_usd) AS mean_total_usd,
       stddev_samp(signed_line_total_usd) / NULLIF(abs(avg(signed_line_total_usd)), 0) AS coefficient_of_variation,
       median(abs(mom_change)) AS median_abs_mom_change, max(abs(mom_change)) AS max_abs_mom_change,
       count(*) FILTER (WHERE signed_line_total_usd < 0) AS periods_with_negative_total
FROM t GROUP BY gl_account;

-- H6  Metrics deliberately NOT computed, and why (so the omission is visible, not silent)
CREATE OR REPLACE TABLE out_h6_bs_metrics_not_computed AS
SELECT * FROM (VALUES
 ('Working capital', 'Needs reliable closing balances for receivables, inventory, payables and an asset/liability sign mapping. Lines per cell are not additive snapshots (H3) and sign convention is unresolved.'),
 ('DSO', 'Needs closing trade receivables (1200) and credit sales for the same period plus an averaging convention. Credit sales are not separable from cash sales in the extract.'),
 ('DPO', 'Needs closing trade payables (2100) and purchases/COGS on a stated basis. 2100 (and 1200) each show a negative period total and month-on-month swings far beyond a plausible balance (H5), so the balance is not reliable.'),
 ('Inventory turnover', 'Needs average inventory (1300) from opening and closing balances. Opening/closing status of lines is unknown.'),
 ('Cash conversion cycle', 'Depends on DSO, DPO and inventory days; none can be supported.'),
 ('Balance movement (change in receivables etc.)', 'Needs a consistent opening/closing definition and one line per cell; most populated cells have several lines whose sizes differ widely (H1, H3).'),
 ('Intercompany balance reconciliation', 'Counterparty entity is not in the extract; elimination status is mostly blank (R12 unresolved).')
) AS t(metric, reason_not_computed);
