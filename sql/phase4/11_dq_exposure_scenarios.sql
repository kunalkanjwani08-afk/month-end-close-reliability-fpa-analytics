-- =====================================================================================================
-- 11  Data-quality exposure and sensitivity scenarios (analysis I)
-- Purpose : show how far each UNRESOLVED assumption can move the headline figures. Scenarios are
--           sensitivities. None is presented as the official answer; the baseline is the provisional
--           project rule (Posted-only, scale-adjusted, duplicates retained, signs as reported).
-- Headline metrics (USD, provisional, signed as reported, positive-magnitude cost convention):
--   revenue = REVENUE section; cost = COGS + PEOPLE + OPEX; result_proxy = revenue - cost.
--   (D&A, below-EBITDA and tax are outside the proxy.) It is a proxy, not a reported operating profit.
-- Base population: P&L rows passing every gate EXCEPT the journal-status gate (v_pl_actual_any_status).
-- =====================================================================================================

CREATE OR REPLACE VIEW v_dq_base AS
SELECT row_id, entity_code, section, gl_account, status_group, scale_decision, scale_confidence,
       coalesce(scale_factor_applied, 1) <> 1 AS restored, dup_tier, sign_flag,
       actual_usd_adj AS amt_adj, actual_usd_parsed AS amt_parsed,
       budget_usd_adj AS bud_adj, budget_usd_parsed AS bud_parsed, sign_cat_ab
FROM v_pl_actual_any_status;

-- I1  Scenario table for the headline metrics. Each block = one scenario of one factor.
--     scenario_class separates what each row IS:
--       BASELINE                   the provisional project rule for the factor (Posted-only, adjusted, candidates retained, signs as recorded)
--       POLICY_SCENARIO            an explicit, comparable reporting-policy alternative (what a different rule would give)
--       STATUS_PARTITION_DIAGNOSTIC one journal status on its own; the five statuses partition the any-status population
--                                  (validated in 99: I03/I04). These are diagnostics, NOT alternative reporting policies.
CREATE OR REPLACE TABLE out_i1_scenarios AS
WITH s AS (
    -- factor 1: journal status (provisional Posted-only rule R6). Statuses are separate, never silently merged.
              SELECT 'status' AS factor, 'POSTED_ONLY (baseline)' AS scenario, 'BASELINE' AS scenario_class, section, amt_adj AS amt FROM v_dq_base WHERE status_group = 'Posted'
    UNION ALL SELECT 'status', 'PENDING_ONLY',  'STATUS_PARTITION_DIAGNOSTIC', section, amt_adj FROM v_dq_base WHERE status_group = 'Pending'
    UNION ALL SELECT 'status', 'PARKED_ONLY',   'STATUS_PARTITION_DIAGNOSTIC', section, amt_adj FROM v_dq_base WHERE status_group = 'Parked'
    UNION ALL SELECT 'status', 'REJECTED_ONLY', 'STATUS_PARTITION_DIAGNOSTIC', section, amt_adj FROM v_dq_base WHERE status_group = 'Rejected'
    UNION ALL SELECT 'status', 'BLANK_ONLY',    'STATUS_PARTITION_DIAGNOSTIC', section, amt_adj FROM v_dq_base WHERE status_group = '(blank)'
    UNION ALL SELECT 'status', 'ALL_EXCEPT_REJECTED', 'POLICY_SCENARIO', section, amt_adj FROM v_dq_base WHERE status_group <> 'Rejected'
    UNION ALL SELECT 'status', 'ALL_STATUSES',  'POLICY_SCENARIO', section, amt_adj FROM v_dq_base
    -- factor 2: reporting scale (baseline population = Posted rows)
    UNION ALL SELECT 'scale', 'ADJUSTED_ALL (baseline)', 'BASELINE', section, amt_adj FROM v_dq_base WHERE status_group = 'Posted'
    UNION ALL SELECT 'scale', 'AS_REPORTED_PARSED (no restoration)', 'POLICY_SCENARIO', section, amt_parsed FROM v_dq_base WHERE status_group = 'Posted'
    UNION ALL SELECT 'scale', 'RESTORE_HIGH_CONFIDENCE_ONLY', 'POLICY_SCENARIO', section,
               CASE WHEN restored AND scale_confidence <> 'HIGH' THEN amt_parsed ELSE amt_adj END FROM v_dq_base WHERE status_group = 'Posted'
    UNION ALL SELECT 'scale', 'EXCLUDE_ALL_RESTORED_ROWS', 'POLICY_SCENARIO', section, amt_adj FROM v_dq_base WHERE status_group = 'Posted' AND NOT restored
    UNION ALL SELECT 'scale', 'EXCLUDE_MEDIUM_CONFIDENCE_RESTORED', 'POLICY_SCENARIO', section, amt_adj FROM v_dq_base
               WHERE status_group = 'Posted' AND NOT (restored AND scale_confidence <> 'HIGH')
    -- factor 3: duplicate candidates (baseline population = Posted rows). Candidates are NOT confirmed duplicates.
    UNION ALL SELECT 'duplicates', 'CANDIDATES_RETAINED (baseline)', 'BASELINE', section, amt_adj FROM v_dq_base WHERE status_group = 'Posted'
    UNION ALL SELECT 'duplicates', 'EXCLUDE_SAME_SIGN_CANDIDATES', 'POLICY_SCENARIO', section, amt_adj FROM v_dq_base
               WHERE status_group = 'Posted' AND dup_tier <> 'DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN'
    UNION ALL SELECT 'duplicates', 'EXCLUDE_ALL_COPY_CANDIDATES', 'POLICY_SCENARIO', section, amt_adj FROM v_dq_base
               WHERE status_group = 'Posted' AND dup_tier NOT IN ('DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN', 'DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT', 'CANDIDATE_COPY_PARTIAL_AGREEMENT')
    -- factor 4: sign handling (baseline population = Posted rows). Signs are never flipped, only rows are filtered.
    UNION ALL SELECT 'sign', 'ALL_ROWS_SIGNS_AS_RECORDED (baseline)', 'BASELINE', section, amt_adj FROM v_dq_base WHERE status_group = 'Posted'
    UNION ALL SELECT 'sign', 'ALL_NON_NEGATIVE_ROWS_ONLY', 'POLICY_SCENARIO', section, amt_adj FROM v_dq_base WHERE status_group = 'Posted' AND sign_flag = 'ALL_NON_NEGATIVE'
    UNION ALL SELECT 'sign', 'EXCLUDE_SINGLE_COLUMN_SIGN_FLIPS', 'POLICY_SCENARIO', section, amt_adj FROM v_dq_base WHERE status_group = 'Posted' AND sign_flag <> 'SINGLE_COLUMN_SIGN_FLIP')
SELECT factor, scenario, scenario_class, count(*) AS rows_in_scope,
       sum(amt) FILTER (WHERE section = 'REVENUE') AS revenue_usd,
       sum(amt) FILTER (WHERE section IN ('COGS', 'PEOPLE', 'OPEX')) AS cost_usd,
       sum(amt) FILTER (WHERE section = 'REVENUE') - sum(amt) FILTER (WHERE section IN ('COGS', 'PEOPLE', 'OPEX')) AS result_proxy_usd
FROM s GROUP BY factor, scenario, scenario_class;

-- I2  Which assumption moves the headline most? Range of each metric across the BASELINE and POLICY_SCENARIO rows of
--     a factor (status partition diagnostics are excluded: a single-status bucket is not an alternative reporting
--     policy), relative to the factor's baseline. The ranges answer "how far can this unresolved assumption move the
--     headline under the policies defined here"; they are sensitivities, not estimates of error.
CREATE OR REPLACE TABLE out_i2_factor_ranking AS
WITH b AS (SELECT factor, revenue_usd AS b_rev, cost_usd AS b_cost, result_proxy_usd AS b_res FROM out_i1_scenarios WHERE scenario_class = 'BASELINE')
SELECT s.factor, count(*) AS scenarios,
       min(s.revenue_usd) AS min_revenue_usd, max(s.revenue_usd) AS max_revenue_usd,
       (max(s.revenue_usd) - min(s.revenue_usd)) / abs(any_value(b.b_rev)) AS revenue_range_pct_of_baseline,
       min(s.result_proxy_usd) AS min_result_usd, max(s.result_proxy_usd) AS max_result_usd,
       (max(s.result_proxy_usd) - min(s.result_proxy_usd)) / abs(any_value(b.b_res)) AS result_range_pct_of_baseline
FROM out_i1_scenarios s JOIN b USING (factor) WHERE s.scenario_class IN ('BASELINE', 'POLICY_SCENARIO') GROUP BY s.factor;

-- I3  Budget-variance conclusion under the same factors: is "revenue below budget and costs above budget" robust?
CREATE OR REPLACE TABLE out_i3_variance_robustness AS
WITH s AS (
              SELECT 'baseline (Posted, scale-adjusted, signs as recorded)' AS scenario, section, amt_adj AS a, bud_adj AS b FROM v_dq_base WHERE status_group = 'Posted' AND bud_adj IS NOT NULL
    UNION ALL SELECT 'all statuses', section, amt_adj, bud_adj FROM v_dq_base WHERE bud_adj IS NOT NULL
    UNION ALL SELECT 'parsed amounts, no scale restoration', section, amt_parsed, bud_parsed FROM v_dq_base WHERE status_group = 'Posted' AND bud_parsed IS NOT NULL
    UNION ALL SELECT 'exclude restored rows', section, amt_adj, bud_adj FROM v_dq_base WHERE status_group = 'Posted' AND bud_adj IS NOT NULL AND NOT restored
    UNION ALL SELECT 'exclude duplicate candidates', section, amt_adj, bud_adj FROM v_dq_base WHERE status_group = 'Posted' AND bud_adj IS NOT NULL
               AND dup_tier NOT IN ('DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN', 'DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT', 'CANDIDATE_COPY_PARTIAL_AGREEMENT')
    UNION ALL SELECT 'same-sign rows only', section, amt_adj, bud_adj FROM v_dq_base WHERE status_group = 'Posted' AND bud_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO'
    UNION ALL SELECT 'all statuses + same-sign rows only', section, amt_adj, bud_adj FROM v_dq_base WHERE bud_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO')
SELECT scenario, section, count(*) AS rows_in_scope, sum(a) AS actual_usd, sum(b) AS budget_usd, sum(a - b) AS net_variance_usd,
       safe_pct(sum(a - b), sum(b), sum(abs(b))) AS variance_pct_of_abs_budget
FROM s WHERE section IN ('REVENUE', 'COGS', 'PEOPLE', 'OPEX') GROUP BY scenario, section;

-- I4  UNDETERMINED scale: records left unresolved (every adjusted amount is blank). Exposure is a BOUND, not an estimate.
CREATE OR REPLACE TABLE out_i4_undetermined_scale AS
SELECT section, count(*) AS rows_undetermined,
       count(*) FILTER (WHERE status_group = 'Posted') AS rows_posted,
       sum(abs(actual_usd_parsed)) AS abs_as_reported_usd,
       sum(abs(actual_usd_parsed)) * 1000   AS if_multiplied_1e3_abs_usd,
       sum(abs(actual_usd_parsed)) * 100000 AS if_multiplied_1e5_abs_usd,
       max(abs(actual_usd_parsed)) AS largest_as_reported_usd
FROM v_close WHERE scale_decision = 'UNDETERMINED' GROUP BY section;

-- I5  Restored rows: how much of the eligible P&L rests on a scale restoration, by confidence
CREATE OR REPLACE TABLE out_i5_restored_exposure AS
WITH r AS (
    SELECT section, section_order, coalesce(scale_confidence, '') AS conf, scale_decision, count(*) AS rows_n,
           sum(abs(actual_usd_adj)) AS abs_adj, sum(abs(actual_usd_parsed)) AS abs_parsed
    FROM v_pl_actual WHERE coalesce(scale_factor_applied, 1) <> 1 GROUP BY ALL),
t AS (SELECT section, sum(abs(actual_usd_adj)) AS abs_total FROM v_pl_actual GROUP BY section)
SELECT r.section, r.section_order, r.conf AS scale_confidence, r.scale_decision, r.rows_n, r.abs_adj AS abs_adjusted_usd,
       r.abs_parsed AS abs_as_reported_usd, r.abs_adj / t.abs_total AS share_of_section_abs_activity
FROM r JOIN t USING (section);

-- I6  Duplicate categories and their weight in the eligible P&L population (rows are all kept)
CREATE OR REPLACE TABLE out_i6_duplicate_exposure AS
SELECT dup_tier, count(*) AS rows_eligible, sum(abs(actual_usd_adj)) AS abs_actual_usd,
       sum(abs(actual_usd_adj)) / sum(sum(abs(actual_usd_adj))) OVER () AS share_of_eligible_abs,
       count(*)::DOUBLE / sum(count(*)) OVER () AS share_of_eligible_rows
FROM v_pl_actual GROUP BY dup_tier;

-- I7  Exact full-row matches: identical in ALL 42 original source fields (everything except row_id) - and with the
--     extract batch ignored. The Phase 3 candidates match only on document, GL, period and amounts.
CREATE OR REPLACE TABLE out_i7_exact_row_matches AS
WITH h AS (
    SELECT row_id,
           hash(concat_ws(chr(31), coalesce(document_no::VARCHAR, chr(0)), coalesce(source_system::VARCHAR, chr(0)), coalesce(user_id::VARCHAR, chr(0)), coalesce(line_text::VARCHAR, chr(0)), coalesce(notes::VARCHAR, chr(0)), coalesce(legal_entity_raw::VARCHAR, chr(0)), coalesce(entity_code_raw::VARCHAR, chr(0)), coalesce(gl_account_raw::VARCHAR, chr(0)), coalesce(account_name::VARCHAR, chr(0)), coalesce(account_group::VARCHAR, chr(0)), coalesce(fs_line::VARCHAR, chr(0)), coalesce(statement::VARCHAR, chr(0)), coalesce(cost_nature::VARCHAR, chr(0)), coalesce(division::VARCHAR, chr(0)), coalesce(country::VARCHAR, chr(0)), coalesce(currency_raw::VARCHAR, chr(0)), coalesce(region::VARCHAR, chr(0)), coalesce(cost_center_code::VARCHAR, chr(0)), coalesce(cost_center_name::VARCHAR, chr(0)), coalesce(cost_center_owner::VARCHAR, chr(0)), coalesce(fiscal_period_raw::VARCHAR, chr(0)), coalesce(fiscal_year_raw::VARCHAR, chr(0)), coalesce(posting_date_raw::VARCHAR, chr(0)), coalesce(extract_batch_raw::VARCHAR, chr(0)), coalesce(amount_local_raw::VARCHAR, chr(0)), coalesce(actual_usd_raw::VARCHAR, chr(0)), coalesce(budget_usd_raw::VARCHAR, chr(0)), coalesce(forecast_usd_raw::VARCHAR, chr(0)), coalesce(prior_year_usd_raw::VARCHAR, chr(0)), coalesce(fx_rate_raw::VARCHAR, chr(0)), coalesce(qty_raw::VARCHAR, chr(0)), coalesce(headcount_fte_raw::VARCHAR, chr(0)), coalesce(report_scale_raw::VARCHAR, chr(0)), coalesce(product_family::VARCHAR, chr(0)), coalesce(customer_segment::VARCHAR, chr(0)), coalesce(channel::VARCHAR, chr(0)), coalesce(uom::VARCHAR, chr(0)), coalesce(intercompany::VARCHAR, chr(0)), coalesce(accrual::VARCHAR, chr(0)), coalesce(elimination_status::VARCHAR, chr(0)), coalesce(approval_status::VARCHAR, chr(0)), coalesce(scenario_tag::VARCHAR, chr(0)))) AS h_all42,
           hash(concat_ws(chr(31), coalesce(document_no::VARCHAR, chr(0)), coalesce(source_system::VARCHAR, chr(0)), coalesce(user_id::VARCHAR, chr(0)), coalesce(line_text::VARCHAR, chr(0)), coalesce(notes::VARCHAR, chr(0)), coalesce(legal_entity_raw::VARCHAR, chr(0)), coalesce(entity_code_raw::VARCHAR, chr(0)), coalesce(gl_account_raw::VARCHAR, chr(0)), coalesce(account_name::VARCHAR, chr(0)), coalesce(account_group::VARCHAR, chr(0)), coalesce(fs_line::VARCHAR, chr(0)), coalesce(statement::VARCHAR, chr(0)), coalesce(cost_nature::VARCHAR, chr(0)), coalesce(division::VARCHAR, chr(0)), coalesce(country::VARCHAR, chr(0)), coalesce(currency_raw::VARCHAR, chr(0)), coalesce(region::VARCHAR, chr(0)), coalesce(cost_center_code::VARCHAR, chr(0)), coalesce(cost_center_name::VARCHAR, chr(0)), coalesce(cost_center_owner::VARCHAR, chr(0)), coalesce(fiscal_period_raw::VARCHAR, chr(0)), coalesce(fiscal_year_raw::VARCHAR, chr(0)), coalesce(posting_date_raw::VARCHAR, chr(0)), coalesce(amount_local_raw::VARCHAR, chr(0)), coalesce(actual_usd_raw::VARCHAR, chr(0)), coalesce(budget_usd_raw::VARCHAR, chr(0)), coalesce(forecast_usd_raw::VARCHAR, chr(0)), coalesce(prior_year_usd_raw::VARCHAR, chr(0)), coalesce(fx_rate_raw::VARCHAR, chr(0)), coalesce(qty_raw::VARCHAR, chr(0)), coalesce(headcount_fte_raw::VARCHAR, chr(0)), coalesce(report_scale_raw::VARCHAR, chr(0)), coalesce(product_family::VARCHAR, chr(0)), coalesce(customer_segment::VARCHAR, chr(0)), coalesce(channel::VARCHAR, chr(0)), coalesce(uom::VARCHAR, chr(0)), coalesce(intercompany::VARCHAR, chr(0)), coalesce(accrual::VARCHAR, chr(0)), coalesce(elimination_status::VARCHAR, chr(0)), coalesce(approval_status::VARCHAR, chr(0)), coalesce(scenario_tag::VARCHAR, chr(0)))) AS h_no_batch,
           hash(concat_ws(chr(31), coalesce(document_no::VARCHAR, chr(0)), coalesce(entity_code_raw::VARCHAR, chr(0)), coalesce(gl_account_raw::VARCHAR, chr(0)), coalesce(amount_local_raw::VARCHAR, chr(0)), coalesce(actual_usd_raw::VARCHAR, chr(0)), coalesce(budget_usd_raw::VARCHAR, chr(0)), coalesce(forecast_usd_raw::VARCHAR, chr(0)), coalesce(prior_year_usd_raw::VARCHAR, chr(0)))) AS h_doc_amounts_text
    FROM fact_close WHERE is_posting_row = 1)
SELECT 'identical in all 42 source fields (row_id ignored)' AS definition,
       (SELECT count(*) FROM (SELECT h_all42 FROM h GROUP BY h_all42 HAVING count(*) > 1)) AS groups_with_matches,
       (SELECT coalesce(sum(c), 0) FROM (SELECT count(*) AS c FROM h GROUP BY h_all42 HAVING count(*) > 1)) AS rows_in_matches
UNION ALL SELECT 'identical in 41 fields (row_id and extract batch ignored)',
       (SELECT count(*) FROM (SELECT h_no_batch FROM h GROUP BY h_no_batch HAVING count(*) > 1)),
       (SELECT coalesce(sum(c), 0) FROM (SELECT count(*) AS c FROM h GROUP BY h_no_batch HAVING count(*) > 1))
UNION ALL SELECT 'same document_no + entity + GL + the five amount texts (strict text equality, no tolerance)',
       (SELECT count(*) FROM (SELECT h_doc_amounts_text FROM h GROUP BY h_doc_amounts_text HAVING count(*) > 1)),
       (SELECT coalesce(sum(c), 0) FROM (SELECT count(*) AS c FROM h GROUP BY h_doc_amounts_text HAVING count(*) > 1));

-- I8  Flag exposure on the eligible P&L population (rows and absolute actual USD). Flags overlap.
CREATE OR REPLACE TABLE out_i8_flag_exposure AS
SELECT flag, count(*) FILTER (WHERE on_ = 1) AS rows_flagged, sum(abs(amt)) FILTER (WHERE on_ = 1) AS abs_actual_usd_flagged,
       count(*) FILTER (WHERE on_ = 1)::DOUBLE / count(*) AS share_of_eligible_rows,
       sum(abs(amt)) FILTER (WHERE on_ = 1) / sum(abs(amt)) AS share_of_eligible_abs
FROM (
              SELECT 'fx_zero: FX rate = 0' AS flag, flag_fx_zero AS on_, actual_usd_adj AS amt FROM v_pl_actual
    UNION ALL SELECT 'fx_missing: FX rate missing', flag_fx_missing, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'usd_row_local_neq_usd: USD-currency row where local differs from USD', flag_usd_row_local_neq_usd, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'fx_usd_rate_not_one: USD-currency row with rate outside 1.000 +/- 0.001', flag_fx_usd_rate_not_one, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'local_usd_sign_conflict', flag_local_usd_sign_conflict, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'sign_single_column_flip', flag_sign_single_column_flip, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'sign_all_negative', flag_sign_all_negative, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'scale_restored', flag_scale_restored, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'scale_label_contradicted', flag_scale_label_contradicted, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'magnitude_outlier', flag_magnitude_outlier, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'dup_candidate_partial_agreement (flag_dup_candidate; tier CANDIDATE_COPY_PARTIAL_AGREEMENT)', flag_dup_candidate, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'dup_tier_field_match (same-sign or sign-conflict candidate copies)', CASE WHEN dup_tier IN ('DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN','DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT') THEN 1 ELSE 0 END, actual_usd_adj FROM v_pl_actual
    UNION ALL SELECT 'cost_center_missing', flag_cost_center_missing, actual_usd_adj FROM v_pl_actual
) GROUP BY flag;

-- I9  Row accounting: every one of the 152,682 rows has exactly one primary exclusion reason or is eligible
--     (P&L actual scope). Amounts are as reported (parsed) because adjusted amounts can be blank.
CREATE OR REPLACE TABLE out_i9_exclusion_waterfall AS
SELECT excl_PL_actual AS primary_reason, count(*) AS rows_n, count(*)::DOUBLE / sum(count(*)) OVER () AS share_of_all_rows,
       sum(abs(actual_usd_parsed)) AS abs_as_reported_usd
FROM fact_close GROUP BY excl_PL_actual;

-- I10 Is the price identity independent of each row it tests? Leave-one-ENTITY-out test.
--     For each product family the reference unit value is the median over the OTHER five entities, using only rows
--     classified UNDIVIDED with HIGH confidence. Restored (HIGH) rows are then compared with a reference that was
--     built without any row of their own entity.
--     Two tolerances are shown: 0.5% and 5% (restored 1E5 amounts carry few significant digits, so rounding alone can exceed 0.5%).
--     MEDIUM-confidence restorations are mostly not price-testable (no quantity/product), so low match shares there mean 'not testable', not 'wrong'.
--     What this shows: the test does not rely on the tested row or its entity. What it does NOT show: that the
--     reference unit value is a true price - it is inferred from this same extract, so it is a CONSISTENCY test.
CREATE OR REPLACE TABLE out_i10_price_identity_independence AS
WITH base AS (
    SELECT row_id, entity_code, product_family, scale_decision, scale_confidence,
           abs(actual_usd_adj) / abs(qty) AS unit_adj
    FROM v_pl_actual_any_status
    WHERE gl_account IN (4100, 5100) AND product_family IS NOT NULL AND qty IS NOT NULL AND qty <> 0
      AND scale_decision IN ('UNDIVIDED', 'DIVIDED_1E3', 'DIVIDED_1E5')),
loo AS (
    SELECT f.product_family, e.entity_code,
           (SELECT median(b.unit_adj) FROM base b WHERE b.product_family = f.product_family AND b.entity_code <> e.entity_code
              AND b.scale_decision = 'UNDIVIDED' AND b.scale_confidence = 'HIGH') AS ref_unit
    FROM (SELECT DISTINCT product_family FROM base) f CROSS JOIN (SELECT DISTINCT entity_code FROM base) e)
SELECT b.scale_decision, b.scale_confidence, count(*) AS rows_tested,
       count(*) FILTER (WHERE abs(b.unit_adj / l.ref_unit - 1) <= 0.005) AS rows_within_half_pct_of_reference,
       count(*) FILTER (WHERE abs(b.unit_adj / l.ref_unit - 1) <= 0.005)::DOUBLE / count(*) AS share_within_half_pct,
       count(*) FILTER (WHERE abs(b.unit_adj / l.ref_unit - 1) <= 0.05) AS rows_within_5pct_of_reference,
       count(*) FILTER (WHERE abs(b.unit_adj / l.ref_unit - 1) <= 0.05)::DOUBLE / count(*) AS share_within_5pct
FROM base b JOIN loo l USING (product_family, entity_code) GROUP BY b.scale_decision, b.scale_confidence;
