-- =====================================================================================================
-- 02  Grain evidence and financial performance overview (analysis A)
-- Populations : v_pl_actual (P&L, eligible, PROVISIONAL Posted-only), v_bs_actual kept separate (file 10)
-- Measure     : actual_usd_adj (scale-adjusted, provisional). USD as reported. P&L is signed AS REPORTED
--               (account sign convention R9 is unresolved, so no favourable/adverse labels here).
-- =====================================================================================================

-- A0  Grain evidence: what one row is. For every multi-row entity x period x GL cell and each amount field the
--     pattern of populated values is classified (COUNT(DISTINCT) ignores NULL, so populated rows are counted too):
--       ALL_POPULATED_EQUAL          every row populated, one distinct value
--       MULTIPLE_POPULATED_DIFFERENT two or more distinct populated values (missing rows may also exist)
--       ONE_VALUE_PLUS_MISSING       some rows populated with a single distinct value, the rest missing
--       ALL_MISSING                  no populated row
--     This pattern evidence shows how often lines carry different amounts; by itself it is NOT proof that amounts
--     are additive. Additivity rests on the business meaning (one row = one posting) and on the reconciliations in 99.
CREATE OR REPLACE TABLE out_a0_grain_evidence AS
WITH cells AS (
    SELECT entity_code, period_ym, gl_account, count(*) AS n_rows,
           count(budget_usd_adj) AS p_budget,     count(DISTINCT budget_usd_adj) AS d_budget,
           count(forecast_usd_adj) AS p_forecast, count(DISTINCT forecast_usd_adj) AS d_forecast,
           count(prior_year_usd_adj) AS p_py,     count(DISTINCT prior_year_usd_adj) AS d_py,
           count(actual_usd_adj) AS p_actual,     count(DISTINCT actual_usd_adj) AS d_actual
    FROM v_pl_actual GROUP BY ALL),
pat AS (
    SELECT 'budget' AS fld, n_rows, p_budget AS p, d_budget AS d FROM cells WHERE n_rows > 1
    UNION ALL SELECT 'forecast', n_rows, p_forecast, d_forecast FROM cells WHERE n_rows > 1
    UNION ALL SELECT 'prior year', n_rows, p_py, d_py FROM cells WHERE n_rows > 1
    UNION ALL SELECT 'actual', n_rows, p_actual, d_actual FROM cells WHERE n_rows > 1),
cls AS (
    SELECT fld, CASE WHEN p = 0 THEN 'ALL_MISSING'
                     WHEN d > 1 THEN 'MULTIPLE_POPULATED_DIFFERENT'
                     WHEN p = n_rows THEN 'ALL_POPULATED_EQUAL'
                     ELSE 'ONE_VALUE_PLUS_MISSING' END AS pattern
    FROM pat),
pats(pattern) AS (VALUES ('ALL_POPULATED_EQUAL'), ('MULTIPLE_POPULATED_DIFFERENT'), ('ONE_VALUE_PLUS_MISSING'), ('ALL_MISSING')),
flds(fld) AS (VALUES ('budget'), ('forecast'), ('prior year'), ('actual'))
SELECT 'cells (entity x period x GL) with >=1 eligible row'                      AS metric, count(*)::DOUBLE AS value, '' AS note FROM cells
UNION ALL SELECT 'cells with >1 eligible row',                                    count(*) FILTER (WHERE n_rows > 1), '' FROM cells
UNION ALL SELECT 'multi-row cells: ' || f.fld || ' - ' || p.pattern,
                 (SELECT count(*) FROM cls c WHERE c.fld = f.fld AND c.pattern = p.pattern)::DOUBLE,
                 CASE WHEN p.pattern = 'MULTIPLE_POPULATED_DIFFERENT' THEN 'lines in the same cell carry different values, so values are per-line amounts and are summed as separate amounts'
                      WHEN p.pattern = 'ALL_POPULATED_EQUAL' THEN 'identical values on every line would instead suggest a repeated cell-level figure'
                      ELSE '' END
         FROM flds f CROSS JOIN pats p
UNION ALL SELECT 'eligible P&L rows',                                              (SELECT count(*) FROM v_pl_actual), ''
UNION ALL SELECT 'distinct document_no among eligible P&L rows',                   (SELECT count(DISTINCT document_no) FROM v_pl_actual),
                 'document_no is not a unique line key (R5)'
UNION ALL SELECT 'non-posting (TOTAL/Subtotal/CHECK) rows still in the canonical CSV', (SELECT count(*) FROM fact_close WHERE is_posting_row = 0),
                 'kept for traceability, excluded from every population'
UNION ALL SELECT 'non-posting rows inside any analytical population',              (SELECT count(*) FROM (
                     SELECT row_id FROM v_pl_actual WHERE is_posting_row = 0 UNION ALL SELECT row_id FROM v_bs_actual WHERE is_posting_row = 0)), 'must be 0';

-- A8  Account master consistency: dim_account takes one representative value per GL (min), so each GL is checked to
--     have exactly one populated value for name, account group, FS line and statement over ALL posting rows (not only
--     eligible ones). Distinct counts ignore NULL, so NULL counts are shown; a conflict is surfaced, never concealed.
CREATE OR REPLACE TABLE out_a8_account_mapping_consistency AS
SELECT gl_account, count(*) AS posting_rows,
       count(DISTINCT account_name)  AS n_names,  count(*) FILTER (WHERE account_name IS NULL)  AS null_names,
       count(DISTINCT account_group) AS n_groups, count(*) FILTER (WHERE account_group IS NULL) AS null_groups,
       count(DISTINCT fs_line)       AS n_fs_lines, count(*) FILTER (WHERE fs_line IS NULL)     AS null_fs_lines,
       count(DISTINCT statement)     AS n_statements, count(*) FILTER (WHERE statement IS NULL) AS null_statements,
       CASE WHEN count(DISTINCT account_name) > 1 OR count(DISTINCT account_group) > 1
              OR count(DISTINCT fs_line) > 1 OR count(DISTINCT statement) > 1 THEN 'CONFLICT'
            WHEN count(DISTINCT account_name) = 0 OR count(DISTINCT account_group) = 0
              OR count(DISTINCT fs_line) = 0 OR count(DISTINCT statement) = 0 THEN 'ATTRIBUTE_MISSING'
            WHEN count(*) FILTER (WHERE account_name IS NULL OR account_group IS NULL OR fs_line IS NULL OR statement IS NULL) > 0 THEN 'CONSISTENT_WITH_NULL_ROWS'
            ELSE 'CONSISTENT' END AS mapping_status
FROM fact_close WHERE is_posting_row = 1 AND gl_account IS NOT NULL GROUP BY gl_account;

-- A1  P&L by period and section (signed as reported; row counts; also gross magnitude)
CREATE OR REPLACE TABLE out_a1_pl_period_section AS
SELECT period_ym, section, count(*) AS rows_eligible,
       sum(actual_usd_adj)      AS actual_usd,
       sum(abs(actual_usd_adj)) AS abs_actual_usd,
       sum(actual_usd_parsed)   AS actual_usd_as_reported_parsed
FROM v_pl_actual GROUP BY period_ym, section;

-- A2  P&L by legal entity and section (3-year totals) with share of the section total
CREATE OR REPLACE TABLE out_a2_pl_entity_section AS
SELECT entity_code, any_value(legal_entity) AS legal_entity, section, count(*) AS rows_eligible,
       sum(actual_usd_adj) AS actual_usd,
       sum(abs(actual_usd_adj)) AS abs_actual_usd,
       sum(abs(actual_usd_adj)) / sum(sum(abs(actual_usd_adj))) OVER (PARTITION BY section) AS share_of_section_abs
FROM v_pl_actual GROUP BY entity_code, section;

-- A3  P&L by division and section
CREATE OR REPLACE TABLE out_a3_pl_division_section AS
SELECT division, section, count(*) AS rows_eligible,
       sum(actual_usd_adj) AS actual_usd,
       sum(abs(actual_usd_adj)) AS abs_actual_usd,
       sum(abs(actual_usd_adj)) / sum(sum(abs(actual_usd_adj))) OVER (PARTITION BY section) AS share_of_section_abs
FROM v_pl_actual GROUP BY division, section;

-- A4  P&L by GL account (3-year totals, share of total absolute activity)
CREATE OR REPLACE TABLE out_a4_pl_gl AS
SELECT gl_account, account_name, account_group, fs_line, section, count(*) AS rows_eligible,
       sum(actual_usd_adj) AS actual_usd,
       sum(abs(actual_usd_adj)) AS abs_actual_usd,
       sum(abs(actual_usd_adj)) / sum(sum(abs(actual_usd_adj))) OVER () AS share_of_total_abs,
       avg(CASE WHEN actual_usd_adj < 0 THEN 1.0 ELSE 0.0 END) AS share_rows_negative
FROM v_pl_actual GROUP BY ALL;

-- A5  Dimension reliability on the eligible P&L rows: fill rate by section (blank is never invented)
CREATE OR REPLACE TABLE out_a5_dimension_reliability AS
WITH u AS (
    SELECT section, 'division' AS dimension, division AS v FROM v_pl_actual
    UNION ALL SELECT section, 'region',           region           FROM v_pl_actual
    UNION ALL SELECT section, 'cost_center_code', cost_center_code FROM v_pl_actual
    UNION ALL SELECT section, 'product_family',   product_family   FROM v_pl_actual
    UNION ALL SELECT section, 'customer_segment', customer_segment FROM v_pl_actual
    UNION ALL SELECT section, 'channel',          channel          FROM v_pl_actual
    UNION ALL SELECT section, 'uom',              uom              FROM v_pl_actual
    UNION ALL SELECT section, 'qty (numeric)',    CASE WHEN qty IS NOT NULL THEN 'x' END FROM v_pl_actual)
SELECT dimension, section, count(*) AS rows_eligible, count(v) AS rows_populated,
       count(v)::DOUBLE / count(*) AS fill_rate,
       count(DISTINCT v) AS distinct_values,
       CASE WHEN count(v)::DOUBLE / count(*) >= 0.99 THEN 'RELIABLE'
            WHEN count(v)::DOUBLE / count(*) >= 0.80 THEN 'USABLE WITH BLANK BUCKET'
            WHEN count(v) = 0                         THEN 'NOT POPULATED'
            ELSE 'UNSUITABLE' END AS verdict
FROM u GROUP BY dimension, section;

-- A6  Period coverage: eligible P&L rows per entity and period, and any entity-period gap
CREATE OR REPLACE TABLE out_a6_period_coverage AS
WITH spine AS (
    SELECT e.entity_code, p.period_ym FROM (SELECT DISTINCT entity_code FROM v_pl_actual) e
    CROSS JOIN (SELECT DISTINCT period_ym FROM fact_close WHERE period_ym IS NOT NULL) p)
SELECT s.entity_code, s.period_ym, count(v.row_id) AS rows_eligible,
       count(DISTINCT v.gl_account) AS gl_accounts_present
FROM spine s LEFT JOIN v_pl_actual v USING (entity_code, period_ym) GROUP BY ALL;

-- A7  Time series completeness summary
CREATE OR REPLACE TABLE out_a7_period_summary AS
SELECT (SELECT min(period_ym) FROM fact_close)                        AS first_period,
       (SELECT max(period_ym) FROM fact_close)                        AS last_period,
       (SELECT count(DISTINCT period_ym) FROM fact_close)             AS distinct_periods,
       (SELECT count(*) FROM out_a6_period_coverage WHERE rows_eligible = 0) AS entity_period_gaps,
       (SELECT min(rows_eligible) FROM out_a6_period_coverage)        AS min_rows_entity_period,
       (SELECT max(rows_eligible) FROM out_a6_period_coverage)        AS max_rows_entity_period;
