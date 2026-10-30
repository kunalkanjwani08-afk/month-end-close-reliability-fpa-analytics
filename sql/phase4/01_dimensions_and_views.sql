-- =====================================================================================================
-- 01  Dimensions and analytical views
-- Input : fact_close (192 typed columns, 152,682 rows, one row = one journal line / posting or one
--         non-posting TOTAL/Subtotal/CHECK label row)  -- built by src/phase4_pipeline.py
-- Output: dim_account, v_close and the five analytical populations.
-- Money : *_usd_adj are the PROVISIONAL scale-adjusted USD amounts; *_usd_parsed are the AS-REPORTED
--         parsed amounts. They are never mixed in one measure. Currency unit = USD as reported.
-- Rules : P&L and Balance Sheet populations are separate views and are never added together.
-- =====================================================================================================

-- Guarded percentage: numerator / ABS(net denominator), returned only when the denominator is a meaningful
-- base, i.e. its absolute net is at least half of the sum of absolute components. When positive and negative
-- budget lines net each other out, the net budget is not a sensible base and a percentage would mislead
-- (project convention, tested for sensitivity in out_b9_contribution_sensitivity and out_b11_budget_pct_sensitivity).
-- Zero or missing denominators give NULL.
CREATE OR REPLACE MACRO safe_pct(num, den_net, den_abs) AS
    CASE WHEN den_abs > 0 AND abs(den_net) >= 0.5 * den_abs THEN num / abs(den_net) END;

-- Pairwise sign category of two amounts. Explicit, mutually exclusive categories replace the earlier binary
-- "product > 0" test, which put genuine opposite-sign pairs and zero-involved pairs into one bucket.
--   MISSING_OR_UNAVAILABLE : at least one amount is NULL (comparison not available)
--   ZERO_INVOLVED          : both amounts present and at least one equals 0 (both-zero and one-zero cases; no sign to compare)
--   SAME_SIGN_NONZERO      : both present, both non-zero, same sign (positive/positive or negative/negative)
--   OPPOSITE_SIGN_NONZERO  : both present, both non-zero, different signs
-- An opposite-sign pair is an observation, not a confirmed accounting error (credit notes, reversals and contra
-- accounts can legitimately differ in sign; the account-level sign convention is unresolved, R9).
CREATE OR REPLACE MACRO sign_cat(a, b) AS
    CASE WHEN a IS NULL OR b IS NULL THEN 'MISSING_OR_UNAVAILABLE'
         WHEN a = 0 OR b = 0         THEN 'ZERO_INVOLVED'
         WHEN sign(a) = sign(b)      THEN 'SAME_SIGN_NONZERO'
         ELSE 'OPPOSITE_SIGN_NONZERO' END;

-- Robust z-score (median / MAD). NULL - "not scorable" - when the MAD is 0 or any input is missing; callers must
-- report such observations as not scorable and must never treat NULL as "within range".
CREATE OR REPLACE MACRO robust_z(x, med, mad) AS
    CASE WHEN x IS NULL OR med IS NULL OR mad IS NULL OR mad = 0 THEN NULL ELSE (x - med) / (1.4826 * mad) END;

-- Anomaly class from the amount score and the row-count score (|z| >= 3 is a project convention, not a standard).
CREATE OR REPLACE MACRO anomaly_class(z_amt, z_rows) AS
    CASE WHEN z_amt IS NULL THEN 'not scorable (MAD = 0 or undefined)'
         WHEN abs(z_amt) >= 3 AND z_rows IS NULL THEN 'amount unusual, row-count score not available - review lines'
         WHEN abs(z_amt) >= 3 AND abs(z_rows) >= 3 THEN 'coverage-driven (row count also unusual)'
         WHEN abs(z_amt) >= 3 THEN 'amount unusual with normal row count - review lines'
         ELSE 'within range' END;

-- Account dimension. min() is only a representative pick: the GL -> name / group / FS line / statement mappings are
-- verified to be 1:1 by out_a8_account_mapping_consistency and checks L49, L52-L55 (03_load_validation.sql); a conflict
-- fails the load validation instead of being hidden by min().
CREATE OR REPLACE TABLE dim_account AS
SELECT gl_account,
       min(account_name)  AS account_name,
       min(account_group) AS account_group,
       min(fs_line)       AS fs_line,
       min(statement)     AS statement,
       CASE min(account_group)
            WHEN 'Revenue'           THEN 'REVENUE'
            WHEN 'COGS'              THEN 'COGS'
            WHEN 'People cost'       THEN 'PEOPLE'
            WHEN 'Operating expense' THEN 'OPEX'
            WHEN 'Depreciation'      THEN 'D&A'
            WHEN 'Below EBITDA'      THEN 'BELOW_EBITDA'
            WHEN 'Tax'               THEN 'TAX'
            WHEN 'Working capital'   THEN 'BALANCE_SHEET'
       END AS section,
       CASE min(account_group)
            WHEN 'Revenue' THEN 1 WHEN 'COGS' THEN 2 WHEN 'People cost' THEN 3 WHEN 'Operating expense' THEN 4
            WHEN 'Depreciation' THEN 5 WHEN 'Below EBITDA' THEN 6 WHEN 'Tax' THEN 7 WHEN 'Working capital' THEN 8
       END AS section_order
FROM fact_close
WHERE is_posting_row = 1 AND gl_account IS NOT NULL
GROUP BY gl_account;

-- One analytical view over all rows with derived reporting fields. Nothing in fact_close is altered.
CREATE OR REPLACE VIEW v_close AS
SELECT c.*,
       d.section, d.section_order,
       make_date(c.period_year::INTEGER, c.period_month::INTEGER, 1)               AS period_start,
       c.period_year::VARCHAR || '-Q' || ((c.period_month + 2) // 3)::VARCHAR      AS period_quarter,
       coalesce(c.approval_status, '(blank)')                                      AS status_group,
       -- pairwise sign category of the scale-adjusted USD amounts (see sign_cat above): actual vs budget / forecast / prior year
       sign_cat(c.actual_usd_adj, c.budget_usd_adj)     AS sign_cat_ab,
       sign_cat(c.actual_usd_adj, c.forecast_usd_adj)   AS sign_cat_af,
       sign_cat(c.actual_usd_adj, c.prior_year_usd_adj) AS sign_cat_ap
FROM fact_close c
LEFT JOIN dim_account d USING (gl_account);

-- ---- Analytical populations (the project's own eligibility flags, verified in 03_load_validation.sql) ------
-- P&L actual: Posted-only PROVISIONAL rule R6, entity resolved, not junk, period parsed, actual present,
--             scale decided, statement = P&L.
CREATE OR REPLACE VIEW v_pl_actual AS SELECT * FROM v_close WHERE eligible_PL_actual = 1;

-- P&L variance vs budget: eligible_PL_actual AND budget present (verified equivalence).
CREATE OR REPLACE VIEW v_pl_budget AS SELECT * FROM v_close WHERE eligible_PL_variance = 1;

-- P&L vs forecast / vs prior year: no project flag exists, so the population is defined here as
-- eligible_PL_actual AND the comparison column present (documented convention).
CREATE OR REPLACE VIEW v_pl_forecast AS
SELECT * FROM v_close WHERE eligible_PL_actual = 1 AND forecast_usd_adj IS NOT NULL;
CREATE OR REPLACE VIEW v_pl_prior AS
SELECT * FROM v_close WHERE eligible_PL_actual = 1 AND prior_year_usd_adj IS NOT NULL;

-- Balance Sheet statement lines - measurement basis UNRESOLVED (opening balance, closing balance or movement is not
-- established by the data). NEVER summed across periods and never mixed with P&L flows.
CREATE OR REPLACE VIEW v_bs_actual AS SELECT * FROM v_close WHERE eligible_BS_actual = 1;

-- P&L actual population WITHOUT the journal-status gate (steps 1-4 and 6-8 of the exclusion precedence
-- applied, step 5 removed). Used only for the status scenario analysis.
CREATE OR REPLACE VIEW v_pl_actual_any_status AS
SELECT * FROM v_close
WHERE is_posting_row = 1 AND flag_junk_entity = 0 AND flag_entity_unresolved = 0 AND statement = 'P&L'
  AND flag_period_unparsed = 0 AND actual_usd_adj IS NOT NULL;
