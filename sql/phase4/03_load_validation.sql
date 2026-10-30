-- =====================================================================================================
-- 03  Load and population validation  ->  out_val_load
-- Every row is a real rule with an EXPECTED value that does not come from the table being tested:
--   * constants copied from the Phase 3 cleaning report (qc_summary.json), or
--   * an identity that must hold between two independently built objects (stg vs fact, flag vs recompute).
-- status = PASS when |actual - expected| <= tolerance. A FAIL stops the pipeline (src/phase4_pipeline.py).
-- Columns: check_id, area, description, expected, actual, difference, tolerance, status
-- =====================================================================================================
CREATE OR REPLACE TABLE out_val_load AS
WITH raw_checks(check_id, area, description, expected, actual, tolerance) AS (
-- ---- rows, schema, keys ---------------------------------------------------------------------------
SELECT 'L01', 'load', 'stg_close_raw holds every source record (Phase 3 report: 152,682)', 152682, (SELECT count(*) FROM stg_close_raw), 0
UNION ALL SELECT 'L02', 'load', 'fact_close holds every source record', 152682, (SELECT count(*) FROM fact_close), 0
UNION ALL SELECT 'L03', 'load', 'stg_close_raw has the 192-column cleaned schema',
       192, (SELECT count(*) FROM information_schema.columns WHERE table_name = 'stg_close_raw'), 0
UNION ALL SELECT 'L04', 'load', 'fact_close has the 192-column cleaned schema',
       192, (SELECT count(*) FROM information_schema.columns WHERE table_name = 'fact_close'), 0
UNION ALL SELECT 'L05', 'keys', 'row_id is unique in fact_close (distinct = rows)', 152682, (SELECT count(DISTINCT row_id) FROM fact_close), 0
UNION ALL SELECT 'L06', 'keys', 'row_id has no NULL or blank value', 0, (SELECT count(*) FROM fact_close WHERE row_id IS NULL OR row_id = ''), 0
UNION ALL SELECT 'L07', 'keys', 'source_row_number is unique (traceability to the raw CSV line)', 152682, (SELECT count(DISTINCT source_row_number) FROM fact_close), 0
UNION ALL SELECT 'L08', 'keys', 'row_id sets of stg and fact are identical (rows not lost, added or re-keyed)',
       0, (SELECT count(*) FROM (SELECT row_id FROM stg_close_raw EXCEPT SELECT row_id FROM fact_close)) +
          (SELECT count(*) FROM (SELECT row_id FROM fact_close EXCEPT SELECT row_id FROM stg_close_raw)), 0
UNION ALL SELECT 'L09', 'duplicates', 'No two rows are identical in all 42 source fields (all rows are kept in the CSV; the same test is published as out_i7)',
       0, (SELECT coalesce(sum(c), 0) FROM (SELECT count(*) AS c FROM fact_close WHERE is_posting_row = 1 GROUP BY hash(concat_ws(chr(31), coalesce(document_no::VARCHAR, chr(0)), coalesce(source_system::VARCHAR, chr(0)), coalesce(user_id::VARCHAR, chr(0)), coalesce(line_text::VARCHAR, chr(0)), coalesce(notes::VARCHAR, chr(0)), coalesce(legal_entity_raw::VARCHAR, chr(0)), coalesce(entity_code_raw::VARCHAR, chr(0)), coalesce(gl_account_raw::VARCHAR, chr(0)), coalesce(account_name::VARCHAR, chr(0)), coalesce(account_group::VARCHAR, chr(0)), coalesce(fs_line::VARCHAR, chr(0)), coalesce(statement::VARCHAR, chr(0)), coalesce(cost_nature::VARCHAR, chr(0)), coalesce(division::VARCHAR, chr(0)), coalesce(country::VARCHAR, chr(0)), coalesce(currency_raw::VARCHAR, chr(0)), coalesce(region::VARCHAR, chr(0)), coalesce(cost_center_code::VARCHAR, chr(0)), coalesce(cost_center_name::VARCHAR, chr(0)), coalesce(cost_center_owner::VARCHAR, chr(0)), coalesce(fiscal_period_raw::VARCHAR, chr(0)), coalesce(fiscal_year_raw::VARCHAR, chr(0)), coalesce(posting_date_raw::VARCHAR, chr(0)), coalesce(extract_batch_raw::VARCHAR, chr(0)), coalesce(amount_local_raw::VARCHAR, chr(0)), coalesce(actual_usd_raw::VARCHAR, chr(0)), coalesce(budget_usd_raw::VARCHAR, chr(0)), coalesce(forecast_usd_raw::VARCHAR, chr(0)), coalesce(prior_year_usd_raw::VARCHAR, chr(0)), coalesce(fx_rate_raw::VARCHAR, chr(0)), coalesce(qty_raw::VARCHAR, chr(0)), coalesce(headcount_fte_raw::VARCHAR, chr(0)), coalesce(report_scale_raw::VARCHAR, chr(0)), coalesce(product_family::VARCHAR, chr(0)), coalesce(customer_segment::VARCHAR, chr(0)), coalesce(channel::VARCHAR, chr(0)), coalesce(uom::VARCHAR, chr(0)), coalesce(intercompany::VARCHAR, chr(0)), coalesce(accrual::VARCHAR, chr(0)), coalesce(elimination_status::VARCHAR, chr(0)), coalesce(approval_status::VARCHAR, chr(0)), coalesce(scenario_tag::VARCHAR, chr(0)))) HAVING count(*) > 1)), 0
-- ---- type conversion: nothing lost between staging text and typed fact --------------------------------
UNION ALL SELECT 'L10', 'types', 'actual_usd_parsed: non-blank text in stg = non-NULL typed value in fact',
       (SELECT count(*) FROM stg_close_raw WHERE actual_usd_parsed <> ''), (SELECT count(actual_usd_parsed) FROM fact_close), 0
UNION ALL SELECT 'L11', 'types', 'budget_usd_parsed: non-blank text in stg = non-NULL typed value in fact',
       (SELECT count(*) FROM stg_close_raw WHERE budget_usd_parsed <> ''), (SELECT count(budget_usd_parsed) FROM fact_close), 0
UNION ALL SELECT 'L12', 'types', 'forecast_usd_adj: non-blank text in stg = non-NULL typed value in fact',
       (SELECT count(*) FROM stg_close_raw WHERE forecast_usd_adj <> ''), (SELECT count(forecast_usd_adj) FROM fact_close), 0
UNION ALL SELECT 'L13', 'types', 'prior_year_usd_adj: non-blank text in stg = non-NULL typed value in fact',
       (SELECT count(*) FROM stg_close_raw WHERE prior_year_usd_adj <> ''), (SELECT count(prior_year_usd_adj) FROM fact_close), 0
UNION ALL SELECT 'L14', 'types', 'gl_account: non-blank text in stg = non-NULL typed value in fact',
       (SELECT count(*) FROM stg_close_raw WHERE gl_account <> ''), (SELECT count(gl_account) FROM fact_close), 0
UNION ALL SELECT 'L15', 'types', 'period_ym: non-blank text in stg = non-NULL value in fact',
       (SELECT count(*) FROM stg_close_raw WHERE period_ym <> ''), (SELECT count(period_ym) FROM fact_close), 0
UNION ALL SELECT 'L16', 'types', 'Amount text equals typed value for actual_usd_adj (max abs difference, USD)',
       0, coalesce((SELECT max(abs(s.actual_usd_adj::DOUBLE - f.actual_usd_adj)) FROM stg_close_raw s JOIN fact_close f USING (row_id)
                    WHERE s.actual_usd_adj <> ''), 0), 0.000001
UNION ALL SELECT 'L17', 'types', 'No infinite or NaN value in any of the 10 numeric amount columns', 0,
       (SELECT count(*) FROM fact_close WHERE isinf(amount_local_parsed) OR isnan(amount_local_parsed) OR isinf(actual_usd_parsed) OR isnan(actual_usd_parsed)
          OR isinf(budget_usd_parsed) OR isnan(budget_usd_parsed) OR isinf(forecast_usd_parsed) OR isnan(forecast_usd_parsed)
          OR isinf(prior_year_usd_parsed) OR isnan(prior_year_usd_parsed) OR isinf(amount_local_adj) OR isnan(amount_local_adj)
          OR isinf(actual_usd_adj) OR isnan(actual_usd_adj) OR isinf(budget_usd_adj) OR isnan(budget_usd_adj)
          OR isinf(forecast_usd_adj) OR isnan(forecast_usd_adj) OR isinf(prior_year_usd_adj) OR isnan(prior_year_usd_adj)), 0
-- ---- missingness of fields the analysis depends on --------------------------------------------------
UNION ALL SELECT 'L18', 'missingness', 'Eligibility flags and is_posting_row have no NULL (all four, all rows)', 0,
       (SELECT count(*) FROM fact_close WHERE eligible_PL_actual IS NULL OR eligible_PL_variance IS NULL OR eligible_BS_actual IS NULL OR is_posting_row IS NULL), 0
UNION ALL SELECT 'L19', 'missingness', 'Eligibility flags take only the values 0 and 1', 0,
       (SELECT count(*) FROM fact_close WHERE eligible_PL_actual NOT IN (0, 1) OR eligible_PL_variance NOT IN (0, 1) OR eligible_BS_actual NOT IN (0, 1)), 0
UNION ALL SELECT 'L20', 'missingness', 'Every eligible P&L row has entity, GL, period, section and an actual amount', 0,
       (SELECT count(*) FROM v_pl_actual WHERE entity_code IS NULL OR gl_account IS NULL OR period_ym IS NULL OR section IS NULL OR actual_usd_adj IS NULL), 0
-- ---- eligible populations versus the Phase 3 report ---------------------------------------------------
UNION ALL SELECT 'L21', 'population', 'P&L actual population (Phase 3 report: 58,340)', 58340, (SELECT count(*) FROM v_pl_actual), 0
UNION ALL SELECT 'L22', 'population', 'P&L variance population (Phase 3 report: 55,043)', 55043, (SELECT count(*) FROM v_pl_budget), 0
UNION ALL SELECT 'L23', 'population', 'Balance Sheet actual population (Phase 3 report: 2,953)', 2953, (SELECT count(*) FROM v_bs_actual), 0
UNION ALL SELECT 'L24', 'population', 'eligible_PL_variance = eligible_PL_actual AND budget present: rows that disagree', 0,
       (SELECT count(*) FROM fact_close WHERE eligible_PL_variance <> CASE WHEN eligible_PL_actual = 1 AND budget_usd_adj IS NOT NULL THEN 1 ELSE 0 END), 0
UNION ALL SELECT 'L25', 'population', 'P&L populations contain no Balance Sheet or non-P&L row', 0,
       (SELECT count(*) FROM v_pl_actual WHERE statement <> 'P&L' OR section = 'BALANCE_SHEET'), 0
UNION ALL SELECT 'L26', 'population', 'Balance Sheet population contains only Balance Sheet rows', 0,
       (SELECT count(*) FROM v_bs_actual WHERE statement = 'P&L' OR section <> 'BALANCE_SHEET'), 0
UNION ALL SELECT 'L27', 'population', 'Posted subset of the any-status P&L view equals the eligible P&L view (rows in one but not the other)', 0,
       (SELECT count(*) FROM (SELECT row_id FROM v_pl_actual_any_status WHERE status_group = 'Posted' EXCEPT SELECT row_id FROM v_pl_actual)) +
       (SELECT count(*) FROM (SELECT row_id FROM v_pl_actual EXCEPT SELECT row_id FROM v_pl_actual_any_status WHERE status_group = 'Posted')), 0
UNION ALL SELECT 'L28', 'population', 'Every eligible row has journal status Posted (provisional rule R6)', 0,
       (SELECT count(*) FROM v_pl_actual WHERE status_group <> 'Posted') + (SELECT count(*) FROM v_bs_actual WHERE status_group <> 'Posted'), 0
UNION ALL SELECT 'L29', 'population', 'Non-posting TOTAL/Subtotal/CHECK label rows (Phase 3: 350) are in no analytical population', 0,
       (SELECT count(*) FROM fact_close WHERE is_posting_row = 0 AND (eligible_PL_actual = 1 OR eligible_BS_actual = 1)), 0
UNION ALL SELECT 'L30', 'population', 'Non-posting rows in the file (Phase 3 report: 350)', 350, (SELECT count(*) FROM fact_close WHERE is_posting_row = 0), 0
UNION ALL SELECT 'L31', 'population', 'Entity codes present in eligible P&L rows (6 legal entities)', 6, (SELECT count(DISTINCT entity_code) FROM v_pl_actual), 0
UNION ALL SELECT 'L32', 'population', 'Calendar months present in eligible P&L rows (Jan 2023 - Dec 2025 = 36)', 36, (SELECT count(DISTINCT period_ym) FROM v_pl_actual), 0
-- ---- exclusion identity: eligible + all primary exclusion reasons = every row, per scope ------------------
UNION ALL SELECT 'L33', 'exclusion', 'P&L actual: eligible + sum of exclusion reasons = all rows',
       152682, (SELECT count(*) FROM fact_close WHERE eligible_PL_actual = 1) + (SELECT count(*) FROM fact_close WHERE excl_PL_actual <> 'ELIGIBLE'), 0
UNION ALL SELECT 'L34', 'exclusion', 'P&L variance: eligible + sum of exclusion reasons = all rows',
       152682, (SELECT count(*) FROM fact_close WHERE eligible_PL_variance = 1) + (SELECT count(*) FROM fact_close WHERE excl_PL_variance <> 'ELIGIBLE'), 0
UNION ALL SELECT 'L35', 'exclusion', 'Balance Sheet: eligible + sum of exclusion reasons = all rows',
       152682, (SELECT count(*) FROM fact_close WHERE eligible_BS_actual = 1) + (SELECT count(*) FROM fact_close WHERE excl_BS_actual <> 'ELIGIBLE'), 0
UNION ALL SELECT 'L36', 'exclusion', 'Eligible flag and the word ELIGIBLE in the reason column agree (rows that disagree, 3 scopes)', 0,
       (SELECT count(*) FROM fact_close WHERE (eligible_PL_actual = 1) <> (excl_PL_actual = 'ELIGIBLE'))
     + (SELECT count(*) FROM fact_close WHERE (eligible_PL_variance = 1) <> (excl_PL_variance = 'ELIGIBLE'))
     + (SELECT count(*) FROM fact_close WHERE (eligible_BS_actual = 1) <> (excl_BS_actual = 'ELIGIBLE')), 0
-- ---- scale, duplicates and sign: counts the report relies on ---------------------------------------------
UNION ALL SELECT 'L37', 'scale', 'Restored rows = HIGH + MEDIUM (Phase 3: 6,265)', 6265,
       (SELECT count(*) FROM fact_close WHERE is_posting_row = 1 AND scale_factor_applied IN (1000, 100000)), 0
UNION ALL SELECT 'L38', 'scale', 'Restorations at HIGH confidence (Phase 3: 1,814)', 1814,
       (SELECT count(*) FROM fact_close WHERE is_posting_row = 1 AND scale_factor_applied IN (1000, 100000) AND scale_confidence = 'HIGH'), 0
UNION ALL SELECT 'L39', 'scale', 'Restorations at MEDIUM confidence (Phase 3: 4,451)', 4451,
       (SELECT count(*) FROM fact_close WHERE is_posting_row = 1 AND scale_factor_applied IN (1000, 100000) AND scale_confidence = 'MEDIUM'), 0
UNION ALL SELECT 'L40', 'scale', 'Undetermined-scale posting rows (Phase 3: 73)', 73, (SELECT count(*) FROM fact_close WHERE scale_decision = 'UNDETERMINED'), 0
UNION ALL SELECT 'L41', 'scale', 'Undetermined rows carry no adjusted amount in any of the 5 columns (nothing guessed)', 0,
       (SELECT count(*) FROM fact_close WHERE scale_decision = 'UNDETERMINED' AND (actual_usd_adj IS NOT NULL OR budget_usd_adj IS NOT NULL
          OR forecast_usd_adj IS NOT NULL OR prior_year_usd_adj IS NOT NULL OR amount_local_adj IS NOT NULL)), 0
UNION ALL SELECT 'L42', 'scale', 'Rows where adjusted amount <> parsed amount x applied factor (relative 1e-9)', 0,
       (SELECT count(*) FROM fact_close WHERE actual_usd_adj IS NOT NULL AND actual_usd_parsed IS NOT NULL AND scale_factor_applied IS NOT NULL
          AND abs(actual_usd_adj - actual_usd_parsed * scale_factor_applied) > 1e-9 * greatest(1, abs(actual_usd_adj))), 0
UNION ALL SELECT 'L43', 'scale', 'Rows with no restoration have adjusted = parsed exactly (actual column)', 0,
       (SELECT count(*) FROM fact_close WHERE scale_factor_applied = 1 AND actual_usd_adj IS DISTINCT FROM actual_usd_parsed), 0
UNION ALL SELECT 'L44', 'duplicates', 'Duplicate tier GROUP_ANCHOR (Phase 3: 3,925)', 3925, (SELECT count(*) FROM fact_close WHERE dup_tier = 'GROUP_ANCHOR'), 0
UNION ALL SELECT 'L45', 'duplicates', 'Duplicate tier field-match same sign (Phase 3: 2,332)', 2332, (SELECT count(*) FROM fact_close WHERE dup_tier = 'DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN'), 0
UNION ALL SELECT 'L46', 'duplicates', 'Duplicate tier field-match sign conflict (Phase 3: 1,587)', 1587, (SELECT count(*) FROM fact_close WHERE dup_tier = 'DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT'), 0
UNION ALL SELECT 'L47', 'duplicates', 'Duplicate tier partial agreement (Phase 3: 11)', 11, (SELECT count(*) FROM fact_close WHERE dup_tier = 'CANDIDATE_COPY_PARTIAL_AGREEMENT'), 0
UNION ALL SELECT 'L48', 'duplicates', 'Every posting row has exactly one duplicate tier (Phase 3: 152,332)', 152332, (SELECT count(*) FROM fact_close WHERE is_posting_row = 1 AND dup_tier IS NOT NULL), 0
UNION ALL SELECT 'L49', 'dimension', 'GL account maps to exactly one account_group (GLs with more than one)', 0,
       (SELECT count(*) FROM (SELECT gl_account FROM fact_close WHERE gl_account IS NOT NULL AND is_posting_row = 1 GROUP BY gl_account HAVING count(DISTINCT account_group) > 1)), 0
UNION ALL SELECT 'L50', 'dimension', 'Every posting row with a GL has a section (account group is mapped)', 0,
       (SELECT count(*) FROM v_close WHERE is_posting_row = 1 AND gl_account IS NOT NULL AND section IS NULL), 0
UNION ALL SELECT 'L51', 'dimension', 'GL accounts in the master (Phase 1 data dictionary: 32 four-digit codes)', 32, (SELECT count(*) FROM dim_account), 0
UNION ALL SELECT 'L52', 'dimension', 'GL account maps to exactly one account_name (GLs with more than one populated name)', 0,
       (SELECT count(*) FROM out_a8_account_mapping_consistency WHERE n_names > 1), 0
UNION ALL SELECT 'L53', 'dimension', 'GL account maps to exactly one fs_line (GLs with more than one populated value)', 0,
       (SELECT count(*) FROM out_a8_account_mapping_consistency WHERE n_fs_lines > 1), 0
UNION ALL SELECT 'L54', 'dimension', 'GL account maps to exactly one statement (GLs with more than one populated value)', 0,
       (SELECT count(*) FROM out_a8_account_mapping_consistency WHERE n_statements > 1), 0
UNION ALL SELECT 'L55', 'dimension', 'No GL has a missing mapping attribute or any conflict (GLs whose mapping_status is not CONSISTENT)', 0,
       (SELECT count(*) FROM out_a8_account_mapping_consistency WHERE mapping_status IS DISTINCT FROM 'CONSISTENT'), 0
)
SELECT check_id, area, description, expected::DOUBLE AS expected, actual::DOUBLE AS actual, (actual - expected)::DOUBLE AS difference,
       tolerance::DOUBLE AS tolerance,
       CASE WHEN abs(actual - expected) <= tolerance THEN 'PASS' ELSE 'FAIL' END AS status
FROM raw_checks ORDER BY check_id;

-- Exclusion reasons by scope against the Phase 3 report (8 reasons x 3 scopes). Mismatches are listed, not summed away.
CREATE OR REPLACE TABLE out_val_exclusion_counts AS
WITH expected(scope, reason, expected_rows) AS (VALUES
 ('PL_actual', '5_STATUS_NOT_ELIGIBLE', 82986), ('PL_actual', 'ELIGIBLE', 58340), ('PL_actual', '4_OUT_OF_SCOPE_STATEMENT', 7125),
 ('PL_actual', '7_AMOUNT_MISSING', 3637), ('PL_actual', '1_NON_POSTING_ROW', 350), ('PL_actual', '2_JUNK_ENTITY', 204),
 ('PL_actual', '8_SCALE_UNDECIDABLE', 24), ('PL_actual', '3_ENTITY_UNRESOLVABLE', 16),
 ('PL_variance', '5_STATUS_NOT_ELIGIBLE', 82986), ('PL_variance', 'ELIGIBLE', 55043), ('PL_variance', '4_OUT_OF_SCOPE_STATEMENT', 7125),
 ('PL_variance', '7_AMOUNT_MISSING', 6937), ('PL_variance', '1_NON_POSTING_ROW', 350), ('PL_variance', '2_JUNK_ENTITY', 204),
 ('PL_variance', '8_SCALE_UNDECIDABLE', 21), ('PL_variance', '3_ENTITY_UNRESOLVABLE', 16),
 ('BS_actual', '4_OUT_OF_SCOPE_STATEMENT', 144987), ('BS_actual', '5_STATUS_NOT_ELIGIBLE', 3989), ('BS_actual', 'ELIGIBLE', 2953),
 ('BS_actual', '1_NON_POSTING_ROW', 350), ('BS_actual', '2_JUNK_ENTITY', 204), ('BS_actual', '7_AMOUNT_MISSING', 182),
 ('BS_actual', '3_ENTITY_UNRESOLVABLE', 16), ('BS_actual', '8_SCALE_UNDECIDABLE', 1)),
actual AS (
    SELECT 'PL_actual' AS scope, excl_PL_actual AS reason, count(*) AS actual_rows FROM fact_close GROUP BY 2
    UNION ALL SELECT 'PL_variance', excl_PL_variance, count(*) FROM fact_close GROUP BY 2
    UNION ALL SELECT 'BS_actual', excl_BS_actual, count(*) FROM fact_close GROUP BY 2)
SELECT coalesce(e.scope, a.scope) AS scope, coalesce(e.reason, a.reason) AS reason, e.expected_rows, a.actual_rows,
       coalesce(a.actual_rows, 0) - coalesce(e.expected_rows, 0) AS difference,
       CASE WHEN e.expected_rows IS NOT DISTINCT FROM a.actual_rows THEN 'PASS' ELSE 'FAIL' END AS status
FROM expected e FULL JOIN actual a ON e.scope = a.scope AND e.reason = a.reason;
