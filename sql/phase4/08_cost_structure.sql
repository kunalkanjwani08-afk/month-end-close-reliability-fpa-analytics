-- =====================================================================================================
-- 08  Cost structure, concentration and drivers (analysis F)
-- Cost base : operating cost sections COGS, PEOPLE, OPEX, D&A (eligible P&L rows). BELOW_EBITDA and TAX are
--             shown separately. Shares use the ABSOLUTE-magnitude basis (gross activity), because signed
--             sums are distorted by sign-opposed lines (see 04); signed totals are shown beside them.
-- High spend is NOT called inefficient: a cost is only judged against a driver (FTE, quantity, budget).
-- =====================================================================================================

-- F1  Cost base by GL account: signed total, absolute total, share and cumulative share
CREATE OR REPLACE TABLE out_f1_cost_by_gl AS
WITH c AS (
    SELECT gl_account, any_value(account_name) AS account_name, section, section_order, count(*) AS rows_eligible,
           sum(actual_usd_adj) AS actual_signed_usd, sum(abs(actual_usd_adj)) AS actual_abs_usd
    FROM v_pl_actual WHERE section IN ('COGS', 'PEOPLE', 'OPEX', 'D&A') GROUP BY gl_account, section, section_order)
SELECT *, actual_abs_usd / sum(actual_abs_usd) OVER () AS share_of_cost_abs,
       sum(actual_abs_usd) OVER (ORDER BY actual_abs_usd DESC) / sum(actual_abs_usd) OVER () AS cumulative_share,
       rank() OVER (ORDER BY actual_abs_usd DESC) AS rank_by_abs
FROM c;

-- F2  Concentration: top-1 / top-3 share and Herfindahl index (HHI, 0-1) by dimension, with the equal-share
--     benchmark 1/N so a high share is read against the number of members
CREATE OR REPLACE TABLE out_f2_concentration AS
WITH base AS (
    SELECT 'legal_entity' AS dimension, entity_code AS member, sum(abs(actual_usd_adj)) AS v FROM v_pl_actual WHERE section IN ('COGS','PEOPLE','OPEX','D&A') GROUP BY ALL
    UNION ALL SELECT 'division', division, sum(abs(actual_usd_adj)) FROM v_pl_actual WHERE section IN ('COGS','PEOPLE','OPEX','D&A') GROUP BY ALL
    UNION ALL SELECT 'gl_account', gl_account::VARCHAR, sum(abs(actual_usd_adj)) FROM v_pl_actual WHERE section IN ('COGS','PEOPLE','OPEX','D&A') GROUP BY ALL
    UNION ALL SELECT 'cost_center (opex+people)', coalesce(cost_center_code, '(blank)'), sum(abs(actual_usd_adj)) FROM v_pl_actual WHERE section IN ('PEOPLE','OPEX') GROUP BY ALL),
-- row_number() with a deterministic tie-break: the top-three share contains EXACTLY three members (rank() would add tied members)
s AS (SELECT *, v / sum(v) OVER (PARTITION BY dimension) AS share, row_number() OVER (PARTITION BY dimension ORDER BY v DESC, member) AS rk FROM base)
SELECT dimension, count(*) AS members, max(share) AS top1_share, sum(share) FILTER (WHERE rk <= 3) AS top3_share,
       count(*) FILTER (WHERE rk <= 3) AS top3_members,
       sum(share * share) AS hhi, 1.0 / count(*) AS equal_share_benchmark,
       max(member) FILTER (WHERE rk = 1) AS top1_member
FROM s GROUP BY dimension;

-- F3  Expense mix by year: section share of the operating cost base
CREATE OR REPLACE TABLE out_f3_cost_mix_by_year AS
SELECT period_year, section, section_order, sum(abs(actual_usd_adj)) AS actual_abs_usd,
       sum(abs(actual_usd_adj)) / sum(sum(abs(actual_usd_adj))) OVER (PARTITION BY period_year) AS share_of_cost_abs,
       sum(actual_usd_adj) AS actual_signed_usd
FROM v_pl_actual WHERE section IN ('COGS', 'PEOPLE', 'OPEX', 'D&A') GROUP BY period_year, section, section_order;

-- F4  Cost-to-revenue ratios by year (absolute basis and signed basis side by side)
CREATE OR REPLACE TABLE out_f4_cost_to_revenue AS
SELECT period_year,
       sum(abs(actual_usd_adj)) FILTER (WHERE section = 'COGS')   / sum(abs(actual_usd_adj)) FILTER (WHERE section = 'REVENUE') AS cogs_to_revenue_abs,
       sum(abs(actual_usd_adj)) FILTER (WHERE section = 'PEOPLE') / sum(abs(actual_usd_adj)) FILTER (WHERE section = 'REVENUE') AS people_to_revenue_abs,
       sum(abs(actual_usd_adj)) FILTER (WHERE section = 'OPEX')   / sum(abs(actual_usd_adj)) FILTER (WHERE section = 'REVENUE') AS opex_to_revenue_abs,
       sum(actual_usd_adj) FILTER (WHERE section = 'COGS')   / sum(actual_usd_adj) FILTER (WHERE section = 'REVENUE') AS cogs_to_revenue_signed,
       sum(actual_usd_adj) FILTER (WHERE section = 'PEOPLE') / sum(actual_usd_adj) FILTER (WHERE section = 'REVENUE') AS people_to_revenue_signed,
       sum(actual_usd_adj) FILTER (WHERE section = 'OPEX')   / sum(actual_usd_adj) FILTER (WHERE section = 'REVENUE') AS opex_to_revenue_signed
FROM v_pl_actual GROUP BY ROLLUP (period_year);

-- F5  Persistent deviators: entity x GL cells whose actual sits on the SAME side of budget in >= 90% of the months
--     they appear (same-sign view) and whose 3-year variance is at least 3% of budget. Persistence is a reason
--     to investigate, not a cause.
CREATE OR REPLACE TABLE out_f5_persistent_cells AS
WITH m AS (
    SELECT entity_code, gl_account, any_value(account_name) AS account_name, section, period_ym,
           sum(variance) AS variance, sum(budget) AS budget
    FROM v_var_scn WHERE scenario = 'SAME_SIGN_ONLY' GROUP BY entity_code, gl_account, section, period_ym)
SELECT entity_code, gl_account, any_value(account_name) AS account_name, section, count(*) AS months_with_data,
       count(*) FILTER (WHERE variance > 0) AS months_above, count(*) FILTER (WHERE variance < 0) AS months_below,
       greatest(count(*) FILTER (WHERE variance > 0), count(*) FILTER (WHERE variance < 0))::DOUBLE / count(*) AS dominant_direction_share,
       sum(variance) AS variance_usd, safe_pct(sum(variance), sum(budget), sum(abs(budget))) AS variance_pct
FROM m GROUP BY entity_code, gl_account, section HAVING count(*) >= 12;

-- F6  Salary driver test (GL 6100 Salaries). headcount_fte is populated on ~93% of salary lines and nowhere
--     else with enough coverage. Salary per FTE by entity and year, and the share of lines within 0.5% of the
--     entity median rate: a rate that never moves is a standard/allocated rate, not observed payroll.
CREATE OR REPLACE TABLE out_f6_salary_per_fte AS
WITH r AS (
    SELECT entity_code, period_year, abs(actual_usd_adj) / headcount_fte AS per_fte
    FROM v_pl_actual WHERE gl_account = 6100 AND headcount_fte > 0),
med AS (SELECT entity_code, median(per_fte) AS entity_median FROM r GROUP BY entity_code)
SELECT r.entity_code, r.period_year, count(*) AS rows_used, median(r.per_fte) AS median_per_fte_usd,
       min(r.per_fte) AS min_per_fte_usd, max(r.per_fte) AS max_per_fte_usd,
       avg(CASE WHEN abs(r.per_fte / m.entity_median - 1) <= 0.005 THEN 1.0 ELSE 0.0 END) AS share_within_half_pct_of_entity_median
FROM r JOIN med m USING (entity_code) GROUP BY r.entity_code, r.period_year;

-- F7  What the salary result implies for the 6100 budget variance IF the budget used the same rate
--     (hypothesis, not observed): implied FTE-months = amount / entity median rate.
CREATE OR REPLACE TABLE out_f7_salary_implied_fte AS
WITH med AS (SELECT entity_code, median(abs(actual_usd_adj) / headcount_fte) AS rate FROM v_pl_actual WHERE gl_account = 6100 AND headcount_fte > 0 GROUP BY entity_code)
SELECT v.entity_code, m.rate AS entity_rate_per_fte_month_usd, sum(v.actual) AS actual_usd, sum(v.budget) AS budget_usd,
       sum(v.actual) / m.rate AS implied_actual_fte_months, sum(v.budget) / m.rate AS implied_budget_fte_months,
       (sum(v.actual) - sum(v.budget)) / m.rate AS implied_excess_fte_months, sum(v.variance) AS variance_usd
FROM v_var_scn v JOIN med m USING (entity_code)
WHERE v.scenario = 'SAME_SIGN_ONLY' AND v.gl_account = 6100 GROUP BY v.entity_code, m.rate;
