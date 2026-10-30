-- =====================================================================================================
-- 09  Trend, volatility and persistence (analysis G)
-- Two bases are always shown, because the choice changes the story (see 06, D3):
--   POSTED   : eligible rows (provisional Posted-only rule), signed as reported
--   ANY_ABS  : all journal statuses, ABSOLUTE amounts - a volume proxy that does not depend on sign errors
--              or on which ~43% of lines happen to be Posted. It is a sensitivity basis, not a P&L.
-- An outlier is a reason to look, not an error. Anomalies are checked against record coverage (row counts).
-- =====================================================================================================

-- G1  Monthly series by section on both bases
CREATE OR REPLACE TABLE out_g1_monthly_series AS
WITH p AS (SELECT period_ym, section, section_order, sum(actual_usd_adj) AS posted_signed_usd, sum(abs(actual_usd_adj)) AS posted_abs_usd, count(*) AS posted_rows
           FROM v_pl_actual GROUP BY ALL),
a AS (SELECT period_ym, section, sum(abs(actual_usd_adj)) AS any_abs_usd, sum(actual_usd_adj) AS any_signed_usd, count(*) AS any_rows
      FROM v_pl_actual_any_status GROUP BY ALL)
SELECT * FROM p FULL JOIN a USING (period_ym, section);

-- G2  Month-on-month and year-on-year change for the ANY_ABS and POSTED series
CREATE OR REPLACE TABLE out_g2_mom_yoy AS
WITH s AS (
    SELECT period_ym, section, section_order, 'ANY_ABS' AS basis, any_abs_usd AS amt FROM out_g1_monthly_series
    UNION ALL SELECT period_ym, section, section_order, 'POSTED_SIGNED', posted_signed_usd FROM out_g1_monthly_series)
SELECT period_ym, section, section_order, basis, amt,
       safe_pct(amt - lag(amt, 1) OVER w, lag(amt, 1) OVER w, abs(lag(amt, 1) OVER w)) AS mom_change,
       safe_pct(amt - lag(amt, 12) OVER w, lag(amt, 12) OVER w, abs(lag(amt, 12) OVER w)) AS yoy_change
FROM s WINDOW w AS (PARTITION BY section, basis ORDER BY period_ym);

-- G3  Seasonality: calendar-month index (month average / overall month average), ANY_ABS basis, 3 years pooled
CREATE OR REPLACE TABLE out_g3_seasonality AS
WITH m AS (SELECT section, section_order, substr(period_ym, 6, 2)::INTEGER AS cal_month, avg(any_abs_usd) AS avg_amt
           FROM out_g1_monthly_series GROUP BY ALL)
SELECT section, section_order, cal_month, avg_amt, avg_amt / avg(avg_amt) OVER (PARTITION BY section) AS seasonal_index
FROM m;

-- G4  Half-year year-on-year growth on both bases (tests the "growth slowed in 2025" reading)
CREATE OR REPLACE TABLE out_g4_halfyear_growth AS
WITH h AS (
    SELECT section, section_order, period_ym[1:4]::INTEGER AS y, CASE WHEN substr(period_ym, 6, 2)::INTEGER <= 6 THEN 'H1' ELSE 'H2' END AS half,
           sum(any_abs_usd) AS any_abs, sum(posted_signed_usd) AS posted_signed
    FROM out_g1_monthly_series GROUP BY ALL)
SELECT c.section, c.section_order, c.half, c.y,
       c.any_abs, c.any_abs / p.any_abs - 1 AS yoy_any_abs,
       c.posted_signed, safe_pct(c.posted_signed - p.posted_signed, p.posted_signed, abs(p.posted_signed)) AS yoy_posted_signed
FROM h c JOIN h p ON p.section = c.section AND p.half = c.half AND p.y = c.y - 1;

-- G5  Entity-level year-on-year growth (ANY_ABS) for revenue and operating costs: is any entity different?
CREATE OR REPLACE TABLE out_g5_entity_growth AS
WITH e AS (
    SELECT entity_code, period_year, CASE WHEN section = 'REVENUE' THEN 'REVENUE' ELSE 'OPERATING COST' END AS grp,
           sum(abs(actual_usd_adj)) AS amt
    FROM v_pl_actual_any_status WHERE section IN ('REVENUE', 'COGS', 'PEOPLE', 'OPEX', 'D&A') GROUP BY ALL)
SELECT c.entity_code, c.grp, c.period_year, c.amt, c.amt / p.amt - 1 AS yoy_growth
FROM e c JOIN e p ON p.entity_code = c.entity_code AND p.grp = c.grp AND p.period_year = c.period_year - 1;

-- G6  Anomaly scan on entity x section monthly series (ANY_ABS): seasonally adjusted ratio, robust z (median/MAD),
--     then a COVERAGE CHECK: is the month unusual because there were unusually many/few journal lines?
CREATE OR REPLACE TABLE out_g6_anomaly_scan AS
WITH e AS (
    SELECT entity_code, section, period_ym, substr(period_ym, 6, 2)::INTEGER AS cal_month,
           sum(abs(actual_usd_adj)) AS amt, count(*) AS n_rows
    FROM v_pl_actual_any_status WHERE section IN ('REVENUE', 'COGS', 'PEOPLE', 'OPEX') GROUP BY ALL),
s AS (SELECT *, ln(amt / avg(amt) OVER (PARTITION BY entity_code, section, cal_month)) AS ln_seas_ratio,
             ln(n_rows::DOUBLE / avg(n_rows) OVER (PARTITION BY entity_code, section, cal_month)) AS ln_rows_ratio
      FROM e),
c AS (SELECT entity_code, section, median(ln_seas_ratio) AS med_a, median(ln_rows_ratio) AS med_r FROM s GROUP BY entity_code, section),
d AS (SELECT s.*, c.med_a, c.med_r FROM s JOIN c USING (entity_code, section)),
k AS (SELECT entity_code, section, median(abs(ln_seas_ratio - med_a)) AS mad_a, median(abs(ln_rows_ratio - med_r)) AS mad_r FROM d GROUP BY entity_code, section)
SELECT d.entity_code, d.section, d.period_ym, d.amt, d.n_rows, d.ln_seas_ratio, d.ln_rows_ratio,
       robust_z(d.ln_seas_ratio, d.med_a, k.mad_a) AS robust_z_amount,
       robust_z(d.ln_rows_ratio, d.med_r, k.mad_r) AS robust_z_rows,
       -- MAD = 0 (a constant series) leaves the score undefined: such months are reported as NOT SCORABLE, never as "within range"
       anomaly_class(robust_z(d.ln_seas_ratio, d.med_a, k.mad_a), robust_z(d.ln_rows_ratio, d.med_r, k.mad_r)) AS anomaly_class
FROM d JOIN k USING (entity_code, section);

