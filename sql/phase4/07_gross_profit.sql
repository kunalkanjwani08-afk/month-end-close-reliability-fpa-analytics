-- =====================================================================================================
-- 07  Revenue, COGS and gross profit (analysis E)
-- Account classification (verified in 99): REVENUE = 4100 Product sales, 4110 Service and spares revenue,
--   4120 Freight recovered, 4190 Sales discounts and rebates.  COGS = 5100 Materials, 5110 Inbound freight,
--   5120 Purchase price variance, 5200 Direct labor, 5300 Factory overhead.
-- Why a RANGE and not one number: 4190 (discounts) is negative on ~58% of its lines and positive on the rest,
--   so the sign convention for the one contra-revenue account is undecided (R9). 5120 is mixed as well.
--   Gross profit is therefore shown under three explicit treatments of 4190. None is "the" answer.
--     GP_S1_SIGNED_AS_RECORDED  : revenue = 4100+4110+4120+4190 SIGNED AS REPORTED          (headline view; scale-adjusted amounts, signs as recorded)
--     GP_S2_DISCOUNT_ABS : revenue = 4100+4110+4120 - ABS(4190)  (discount always reduces revenue)
--     GP_S3_EXCL_DISCOUNT: revenue = 4100+4110+4120               (gross sales before discounts)
--   COGS = 5100..5300 signed as reported in all three.  Gross margin % = GP / Revenue (NULL if revenue <= 0).
-- Row sets: ROWS_ALL = every eligible P&L row (the headline view; signs exactly as recorded).
--   ROWS_ALL_NON_NEGATIVE = only rows whose sign_flag is ALL_NON_NEGATIVE (Phase 3 rule: at least one of the five amount
--   columns is available and none of the AVAILABLE ones is negative; missing amounts are ignored). It is NOT a "sign-consistent" population: rows whose available amounts are all negative (sign_flag
--   ALL_NEGATIVE, needs at least three available amounts), rows with a single-column sign flip (SINGLE_COLUMN_SIGN_FLIP) and other mixes (MIXED_OTHER) are all
--   outside it, as are rows with a missing sign_flag. Zero amounts count as non-negative, so a zero-involved row can be
--   inside it. A SENSITIVITY on the extract, not a correction.
-- =====================================================================================================

CREATE OR REPLACE TABLE gp_treatment AS
SELECT * FROM (VALUES ('GP_S1_SIGNED_AS_RECORDED', 1), ('GP_S2_DISCOUNT_ABS', 2), ('GP_S3_EXCL_DISCOUNT', 3)) AS t(treatment, treatment_order);

CREATE OR REPLACE TABLE gp_rowset AS
SELECT * FROM (VALUES ('ROWS_ALL', 1), ('ROWS_ALL_NON_NEGATIVE', 2)) AS t(rowset, rowset_order);

-- Revenue / COGS contribution of each eligible row under each treatment and row set
CREATE OR REPLACE VIEW v_gp_rows AS
SELECT r.rowset, t.treatment, v.row_id, v.entity_code, v.division, v.period_year, v.period_ym, v.section, v.gl_account,
       CASE WHEN v.section = 'REVENUE' THEN
            CASE t.treatment
                 WHEN 'GP_S1_SIGNED_AS_RECORDED'   THEN v.actual_usd_adj
                 WHEN 'GP_S2_DISCOUNT_ABS'  THEN CASE WHEN v.gl_account = 4190 THEN -abs(v.actual_usd_adj) ELSE v.actual_usd_adj END
                 WHEN 'GP_S3_EXCL_DISCOUNT' THEN CASE WHEN v.gl_account = 4190 THEN 0 ELSE v.actual_usd_adj END
            END END AS revenue,
       CASE WHEN v.section = 'COGS' THEN v.actual_usd_adj END AS cogs
FROM v_pl_actual v
JOIN gp_rowset r ON r.rowset = 'ROWS_ALL' OR (r.rowset = 'ROWS_ALL_NON_NEGATIVE' AND v.sign_flag = 'ALL_NON_NEGATIVE')
CROSS JOIN gp_treatment t
WHERE v.section IN ('REVENUE', 'COGS');

-- E1  Gross profit by treatment and row set, in total and by year
CREATE OR REPLACE TABLE out_e1_gross_profit AS
SELECT rowset, treatment, coalesce(period_year::VARCHAR, 'ALL YEARS') AS period, count(*) AS rows_in_scope,
       sum(revenue) AS revenue_usd, sum(cogs) AS cogs_usd, sum(revenue) - sum(cogs) AS gross_profit_usd,
       CASE WHEN sum(revenue) > 0 THEN (sum(revenue) - sum(cogs)) / sum(revenue) END AS gross_margin_pct
FROM v_gp_rows GROUP BY GROUPING SETS ((rowset, treatment, period_year), (rowset, treatment));

-- E2  Gross profit by entity (3 years), all treatments, all rows
CREATE OR REPLACE TABLE out_e2_gross_profit_entity AS
SELECT rowset, treatment, entity_code, sum(revenue) AS revenue_usd, sum(cogs) AS cogs_usd,
       sum(revenue) - sum(cogs) AS gross_profit_usd,
       CASE WHEN sum(revenue) > 0 THEN (sum(revenue) - sum(cogs)) / sum(revenue) END AS gross_margin_pct
FROM v_gp_rows GROUP BY rowset, treatment, entity_code;

-- E3  Gross profit versus budget on rows where actual and budget are both non-zero with the same sign (the only rows where the
--     comparison is arithmetically clean). Discount treatment S1/S2/S3 applied to both actual and budget.
CREATE OR REPLACE TABLE out_e3_gross_profit_vs_budget AS
WITH r AS (
    SELECT t.treatment, v.section,
           CASE t.treatment WHEN 'GP_S1_SIGNED_AS_RECORDED' THEN v.actual_usd_adj
                            WHEN 'GP_S2_DISCOUNT_ABS' THEN CASE WHEN v.gl_account = 4190 THEN -abs(v.actual_usd_adj) ELSE v.actual_usd_adj END
                            ELSE CASE WHEN v.gl_account = 4190 THEN 0 ELSE v.actual_usd_adj END END AS a,
           CASE t.treatment WHEN 'GP_S1_SIGNED_AS_RECORDED' THEN v.budget_usd_adj
                            WHEN 'GP_S2_DISCOUNT_ABS' THEN CASE WHEN v.gl_account = 4190 THEN -abs(v.budget_usd_adj) ELSE v.budget_usd_adj END
                            ELSE CASE WHEN v.gl_account = 4190 THEN 0 ELSE v.budget_usd_adj END END AS b
    FROM v_pl_budget v CROSS JOIN gp_treatment t
    WHERE v.section IN ('REVENUE', 'COGS') AND v.sign_cat_ab = 'SAME_SIGN_NONZERO')
SELECT treatment,
       sum(a) FILTER (WHERE section = 'REVENUE') AS actual_revenue_usd, sum(b) FILTER (WHERE section = 'REVENUE') AS budget_revenue_usd,
       sum(a) FILTER (WHERE section = 'COGS')    AS actual_cogs_usd,    sum(b) FILTER (WHERE section = 'COGS')    AS budget_cogs_usd,
       sum(a) FILTER (WHERE section = 'REVENUE') - sum(a) FILTER (WHERE section = 'COGS') AS actual_gp_usd,
       sum(b) FILTER (WHERE section = 'REVENUE') - sum(b) FILTER (WHERE section = 'COGS') AS budget_gp_usd,
       (sum(a) FILTER (WHERE section = 'REVENUE') - sum(a) FILTER (WHERE section = 'COGS'))
         - (sum(b) FILTER (WHERE section = 'REVENUE') - sum(b) FILTER (WHERE section = 'COGS')) AS gp_variance_usd,
       (sum(a) FILTER (WHERE section = 'REVENUE') - sum(a) FILTER (WHERE section = 'COGS')) / NULLIF(sum(a) FILTER (WHERE section = 'REVENUE'), 0) AS actual_gm_pct,
       (sum(b) FILTER (WHERE section = 'REVENUE') - sum(b) FILTER (WHERE section = 'COGS')) / NULLIF(sum(b) FILTER (WHERE section = 'REVENUE'), 0) AS budget_gm_pct
FROM r GROUP BY treatment;

-- E4  GP variance decomposition (S3 view: no discount ambiguity): revenue shortfall + COGS overrun = GP gap.
--     Reconciliation identity: gp_variance = revenue_variance - cogs_variance.
CREATE OR REPLACE TABLE out_e4_gp_variance_bridge AS
SELECT treatment, actual_revenue_usd - budget_revenue_usd AS revenue_variance_usd,
       actual_cogs_usd - budget_cogs_usd AS cogs_variance_usd, gp_variance_usd,
       gp_variance_usd - ((actual_revenue_usd - budget_revenue_usd) - (actual_cogs_usd - budget_cogs_usd)) AS bridge_difference_usd
FROM out_e3_gross_profit_vs_budget;

-- E5  Why unit margins by product family are NOT computed: on the quantity-bearing accounts the value per unit of
--     MATERIALS (5100) equals the value per unit of PRODUCT SALES (4100) for every family, i.e. a zero
--     unit margin that is economically implausible. The identity is a data property, not a margin.
--     (Only rows with a populated, non-zero qty, a product family and a decided scale.)
CREATE OR REPLACE TABLE out_e5_unit_value_equality AS
WITH u AS (
    SELECT product_family, gl_account, count(*) AS rows_used,
           sum(abs(actual_usd_adj)) / sum(abs(qty)) AS value_per_unit_usd,
           median(abs(actual_usd_adj) / abs(qty)) AS median_value_per_unit_usd
    FROM v_pl_actual WHERE gl_account IN (4100, 5100) AND qty IS NOT NULL AND qty <> 0 AND product_family IS NOT NULL
    GROUP BY product_family, gl_account)
SELECT s.product_family, s.rows_used AS sales_rows, m.rows_used AS materials_rows,
       s.median_value_per_unit_usd AS median_sales_value_per_unit, m.median_value_per_unit_usd AS median_materials_value_per_unit,
       m.median_value_per_unit_usd / s.median_value_per_unit_usd - 1 AS materials_vs_sales_unit_value_diff
FROM u s JOIN u m ON s.product_family = m.product_family AND s.gl_account = 4100 AND m.gl_account = 5100;

-- E6  Materials cost as a share of product sales by product family and year (absolute-magnitude basis, since
--     signs are unreliable). A cost-structure indicator, NOT a margin (see E5).
CREATE OR REPLACE TABLE out_e6_material_to_sales AS
SELECT CASE WHEN grouping(product_family) = 1 THEN 'ALL FAMILIES' ELSE coalesce(product_family, '(blank)') END AS product_family,
       CASE WHEN grouping(period_year) = 1 THEN 'ALL YEARS' ELSE period_year::VARCHAR END AS period,
       sum(abs(actual_usd_adj)) FILTER (WHERE gl_account = 5100) AS materials_abs_usd,
       sum(abs(actual_usd_adj)) FILTER (WHERE gl_account = 4100) AS product_sales_abs_usd,
       sum(abs(actual_usd_adj)) FILTER (WHERE gl_account = 5100) / NULLIF(sum(abs(actual_usd_adj)) FILTER (WHERE gl_account = 4100), 0) AS materials_to_sales_ratio
FROM v_pl_actual WHERE gl_account IN (4100, 5100)
GROUP BY ROLLUP (product_family, period_year);
