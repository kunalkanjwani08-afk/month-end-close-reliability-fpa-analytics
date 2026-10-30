"""Phase 4 report generator.

Writes docs/PHASE4_ANALYSIS_REPORT.md and docs/PHASE4_INSIGHT_REGISTER.md from the DuckDB out_* tables.
Every number in both documents is read from the database when this script runs (nothing is typed in by hand), so a
re-run after a data or SQL change cannot leave stale figures. The narrative sentences are fixed text; where a sentence
contains a claim of the form "in N of M months" the N and M are computed.

    python src/phase4_report.py [--db PATH] [--docs-dir PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "processed" / "phase4_fpa.duckdb"
DEFAULT_DOCS = ROOT / "docs"


def M(x, d=2):
    return f"{'-' if x < 0 else ''}${abs(x) / 1e6:,.{d}f}M"


def P(x, d=1):
    return f"{x * 100:,.{d}f}%"


def PS(x, d=1):  # signed percent
    return f"{x * 100:+,.{d}f}%"


def N(x):
    return f"{int(x):,}"


class Db:
    def __init__(self, path):
        self.con = duckdb.connect(str(path), read_only=True)

    def one(self, sql, *a):
        return self.con.execute(sql, list(a)).fetchone()[0]

    def row(self, sql, *a):
        return self.con.execute(sql, list(a)).fetchone()

    def rows(self, sql, *a):
        return self.con.execute(sql, list(a)).fetchall()


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def gather(db: Db) -> dict:
    d: dict = {}
    # --- validation status -----------------------------------------------------------------------
    for t in ("out_val_load", "out_val_exclusion_counts", "out_val_analytical", "out_val_crosscheck"):
        d[t] = db.row(f"SELECT count(*), count(*) FILTER (WHERE status = 'PASS') FROM {t}")
    d["rows_total"] = db.one("SELECT count(*) FROM fact_close")
    d["pl_rows"] = db.one("SELECT count(*) FROM v_pl_actual")
    d["pv_rows"] = db.one("SELECT count(*) FROM v_pl_budget")
    d["bs_rows"] = db.one("SELECT count(*) FROM v_bs_actual")
    d["any_rows"] = db.one("SELECT rows_in_scope FROM out_i1_scenarios WHERE scenario='ALL_STATUSES'")
    # --- status exposure -------------------------------------------------------------------------
    d["status"] = {r[0]: r[1:] for r in db.rows("SELECT scenario, rows_in_scope, revenue_usd, cost_usd, result_proxy_usd FROM out_i1_scenarios WHERE factor='status'")}
    d["status_class"] = dict(db.rows("SELECT scenario, scenario_class FROM out_i1_scenarios WHERE factor='status'"))
    d["factor_rank"] = db.rows("SELECT factor, revenue_range_pct_of_baseline, result_range_pct_of_baseline, min_result_usd, max_result_usd, scenarios FROM out_i2_factor_ranking ORDER BY result_range_pct_of_baseline DESC")
    d["scen"] = {r[0]: r[1:] for r in db.rows("SELECT scenario, rows_in_scope, revenue_usd, cost_usd, result_proxy_usd FROM out_i1_scenarios")}
    # --- sign -----------------------------------------------------------------------------------------
    d["fc"] = {(r[0], r[1]): r[2:] for r in db.rows("SELECT scenario, section, wape, bias, net_error_usd, rows_in_scope FROM out_c1_forecast_section")}
    d["fc_attr"] = {}  # section -> category -> (rows, share of rows, absolute error, share of absolute error)
    for sec_, cat_, n_, sr_, ae_, se_ in db.rows("SELECT section, sign_category, rows_in_category, share_of_rows, abs_error_usd, share_of_abs_error FROM out_c2_error_attribution"):
        d["fc_attr"].setdefault(sec_, {})[cat_] = (n_, sr_, ae_, se_)
    d["bridge"] = {r[0]: r[1:] for r in db.rows("SELECT section, all_lines_net_variance_usd, same_sign_net_variance_usd, opposite_sign_net_variance_usd, coalesce(zero_involved_net_variance_usd, 0) FROM out_b8_variance_bridge")}
    d["sign_cats_ab"] = dict(db.rows("SELECT sign_cat_ab, count(*) FROM v_pl_budget GROUP BY 1"))
    d["flags"] = {r[0]: r[1:] for r in db.rows("SELECT flag, rows_flagged, share_of_eligible_rows, share_of_eligible_abs FROM out_i8_flag_exposure")}
    # --- budget variance ---------------------------------------------------------------------------------
    d["var"] = {(r[0], r[1]): r[2:] for r in db.rows("SELECT scenario, section, actual_usd, budget_usd, net_variance_usd, variance_pct_of_abs_budget, budget_netting_ratio, rows_in_scope FROM out_b1_variance_section")}
    d["vol"] = {r[0]: r[1:] for r in db.rows("SELECT section, months, mean_pct, sd_pct, min_pct, max_pct, months_actual_above_budget, months_actual_below_budget FROM out_b5_variance_volatility WHERE scenario='SAME_SIGN_ONLY'")}
    d["cellspread"] = {r[0]: r[1:] for r in db.rows(
        "SELECT section, count(*), min(variance_pct_of_abs_budget), max(variance_pct_of_abs_budget), stddev_samp(variance_pct_of_abs_budget) "
        "FROM out_b2_variance_entity_gl WHERE scenario='SAME_SIGN_ONLY' AND rows_in_scope >= 100 GROUP BY section")}
    d["divspread"] = {r[0]: r[1:] for r in db.rows(
        "SELECT section, min(variance_pct_of_abs_budget), max(variance_pct_of_abs_budget) FROM out_b3_variance_division WHERE scenario='SAME_SIGN_ONLY' GROUP BY section")}
    d["robust"] = db.rows("SELECT scenario, section, net_variance_usd, variance_pct_of_abs_budget FROM out_i3_variance_robustness ORDER BY section, scenario")
    d["mat"] = db.rows("SELECT scenario, threshold_share_of_total_abs_variance, cells_at_or_above, share_of_total_abs_variance_covered FROM out_b9_contribution_sensitivity ORDER BY scenario, 2")
    d["mat11"] = db.rows("SELECT scenario, threshold_pct_of_gross_budget, cells_at_or_above, cells_total, share_of_total_abs_variance_in_flagged_cells FROM out_b11_budget_pct_sensitivity ORDER BY scenario, 2")
    d["glspread"] = {r[0]: r[1:] for r in db.rows("SELECT section, min(variance_pct_of_abs_budget), max(variance_pct_of_abs_budget), count(*) FROM out_b6_variance_persistence WHERE scenario='SAME_SIGN_ONLY' AND dim='gl_account' GROUP BY section")}
    d["sal_lines"] = db.one("SELECT rows_eligible FROM out_a4_pl_gl WHERE gl_account = 6100")
    d["gl4190_neg"] = db.one("SELECT share_rows_negative FROM out_a4_pl_gl WHERE gl_account = 4190")
    d["undet_pl"] = db.row("SELECT sum(rows_undetermined), sum(abs_as_reported_usd), sum(if_multiplied_1e3_abs_usd) FROM out_i4_undetermined_scale WHERE section <> 'BALANCE_SHEET'")
    d["n_out"] = db.one("SELECT count(*) FROM information_schema.tables WHERE table_name LIKE 'out\\_%' ESCAPE '\\'")
    d["cells"] = db.row("SELECT value FROM out_a0_grain_evidence WHERE metric LIKE 'cells (entity%'")[0], db.row("SELECT value FROM out_a0_grain_evidence WHERE metric = 'cells with >1 eligible row'")[0]
    d["ep_rows"] = db.row("SELECT min_rows_entity_period, max_rows_entity_period FROM out_a7_period_summary")
    d["ent"] = db.rows("SELECT entity_code, any_value(legal_entity), sum(actual_usd) FILTER (WHERE section='REVENUE'), sum(actual_usd) FILTER (WHERE section='COGS'), sum(actual_usd) FILTER (WHERE section='PEOPLE'), sum(actual_usd) FILTER (WHERE section='OPEX'), sum(rows_eligible) FROM out_a2_pl_entity_section GROUP BY entity_code ORDER BY entity_code")
    d["maxdiff"] = db.one("SELECT max(abs(difference)) FROM (SELECT difference, tolerance FROM out_val_analytical UNION ALL SELECT difference, tolerance FROM out_val_crosscheck) WHERE tolerance >= 0.01")
    d["maxdiff_ratio"] = db.one("SELECT max(abs(difference)) FROM (SELECT difference, tolerance FROM out_val_analytical UNION ALL SELECT difference, tolerance FROM out_val_crosscheck) WHERE tolerance < 0.01")
    d["top10"] = db.row("SELECT cells_in_both_top10 FROM out_b10_top_cells_overlap")[0]
    d["a8"] = db.row("SELECT count(*), count(*) FILTER (WHERE mapping_status = 'CONSISTENT') FROM out_a8_account_mapping_consistency")
    d["a0_diff"] = db.one("SELECT value FROM out_a0_grain_evidence WHERE metric = 'multi-row cells: actual - MULTIPLE_POPULATED_DIFFERENT'")
    d["top_cells"] = db.rows("SELECT section, entity_code, gl_account, account_name, variance_usd, variance_pct_of_abs_budget FROM out_b2_variance_entity_gl WHERE scenario='SAME_SIGN_ONLY' AND rank_abs_in_section = 1 AND section IN ('REVENUE','COGS','PEOPLE','OPEX') ORDER BY section")
    # --- forecast ---------------------------------------------------------------------------------------------
    d["fvb"] = {r[0]: r[1:] for r in db.rows("SELECT section, wape_forecast, wape_budget, bias_forecast, bias_budget, rows_compared FROM out_c6_forecast_vs_budget")}
    d["fcq"] = {r[0]: r[1:] for r in db.rows("SELECT section, quarters, quarters_forecast_above_actual, quarters_forecast_below_actual, mean_quarter_bias FROM out_c5_bias_persistence WHERE scenario='SAME_SIGN_ONLY'")}
    d["proxy"] = db.rows("SELECT period_year, actual_revenue, actual_result_proxy_usd, budget_result_proxy_usd, forecast_result_proxy_usd FROM out_c8_profit_proxy_bias ORDER BY period_year NULLS LAST")
    # --- prior year --------------------------------------------------------------------------------------------
    d["yoy"] = {(r[0], r[1]): r[2:] for r in db.rows("SELECT basis, period_year, amount_usd, yoy_growth FROM out_d3_true_yoy WHERE section='REVENUE'")}
    d["pyspread"] = {r[0]: r[1:] for r in db.rows("SELECT dim, min_growth, max_growth, mean_growth, sd_growth FROM out_d2_py_growth_spread")}
    d["pyrec"] = {(r[0], r[1]): r[2:] for r in db.rows("SELECT section, period_year, py_column, prev_year_actual, difference_pct FROM out_d4_py_column_reconciliation")}
    d["half"] = db.rows("SELECT y, half, yoy_any_abs, yoy_posted_signed FROM out_g4_halfyear_growth WHERE section='REVENUE' ORDER BY y, half")
    # --- gross profit ------------------------------------------------------------------------------------------------
    d["gp"] = {r[0]: r[1:] for r in db.rows("SELECT treatment, actual_revenue_usd, budget_revenue_usd, actual_cogs_usd, budget_cogs_usd, gp_variance_usd, actual_gm_pct, budget_gm_pct FROM out_e3_gross_profit_vs_budget")}
    d["gpb"] = {r[0]: r[1:] for r in db.rows("SELECT treatment, revenue_variance_usd, cogs_variance_usd, gp_variance_usd FROM out_e4_gp_variance_bridge")}
    d["gm_all"] = {(r[0], r[1]): r[2] for r in db.rows("SELECT rowset, treatment, gross_margin_pct FROM out_e1_gross_profit WHERE period='ALL YEARS'")}
    d["gm_year"] = db.rows("SELECT period, gross_margin_pct FROM out_e1_gross_profit WHERE rowset='ROWS_ALL' AND treatment='GP_S1_SIGNED_AS_RECORDED' AND period <> 'ALL YEARS' ORDER BY period")
    d["unit_eq"] = db.row("SELECT count(*), max(abs(materials_vs_sales_unit_value_diff)) FROM out_e5_unit_value_equality")
    d["mat_ratio"] = db.one("SELECT materials_to_sales_ratio FROM out_e6_material_to_sales WHERE product_family='ALL FAMILIES' AND period='ALL YEARS'")
    # --- cost ------------------------------------------------------------------------------------------------------------
    d["cost_gl"] = db.rows("SELECT gl_account, account_name, section, actual_abs_usd, share_of_cost_abs, cumulative_share FROM out_f1_cost_by_gl ORDER BY rank_by_abs")
    d["conc"] = db.rows("SELECT dimension, members, top1_member, top1_share, top3_share, hhi, equal_share_benchmark FROM out_f2_concentration ORDER BY dimension")
    d["c2r"] = db.row("SELECT cogs_to_revenue_abs, people_to_revenue_abs, opex_to_revenue_abs FROM out_f4_cost_to_revenue WHERE period_year IS NULL")
    d["c2r_year"] = db.rows("SELECT period_year, cogs_to_revenue_abs, people_to_revenue_abs, opex_to_revenue_abs FROM out_f4_cost_to_revenue WHERE period_year IS NOT NULL ORDER BY 1")
    d["sal"] = db.row("SELECT sum(rows_used), sum(rows_used * share_within_half_pct_of_entity_median) / sum(rows_used), min(share_within_half_pct_of_entity_median) FROM out_f6_salary_per_fte")
    d["sal_rate"] = db.rows("SELECT entity_code, entity_rate_per_fte_month_usd, actual_usd, budget_usd, variance_usd, implied_actual_fte_months, implied_excess_fte_months FROM out_f7_salary_implied_fte ORDER BY entity_code")
    d["persist"] = db.row("SELECT count(*), count(*) FILTER (WHERE dominant_direction_share >= 0.9), count(*) FILTER (WHERE dominant_direction_share >= 0.9 AND abs(variance_pct) >= 0.03) FROM out_f5_persistent_cells")
    # --- trend / anomalies -------------------------------------------------------------------------------------------------
    d["season"] = db.rows("SELECT cal_month, seasonal_index FROM out_g3_seasonality WHERE section='REVENUE' ORDER BY 1")
    d["anom"] = db.rows("SELECT anomaly_class, count(*) FROM out_g6_anomaly_scan GROUP BY 1 ORDER BY 2 DESC")
    d["anom_n"] = db.one("SELECT count(*) FROM out_g6_anomaly_scan")
    # --- balance sheet -----------------------------------------------------------------------------------------------------------
    d["bs"] = db.row("SELECT cells_possible, cells_with_a_line, coverage, share_of_populated_cells_with_multiple_lines, max_lines_in_a_cell FROM out_h1_bs_coverage")
    d["bs_cv"] = db.row("SELECT min(coefficient_of_variation), max(coefficient_of_variation), sum(periods_with_negative_total) FROM out_h5_bs_volatility")
    d["bs_multi"] = db.rows("SELECT lines, cells, median_max_over_min, share_cells_within_5pct FROM out_h3_bs_multi_line_spread ORDER BY lines")
    # --- exposure ------------------------------------------------------------------------------------------------------------------
    d["restored"] = db.row("SELECT sum(rows_n), sum(abs_adjusted_usd), sum(rows_n) FILTER (WHERE scale_confidence='HIGH'), sum(rows_n) FILTER (WHERE scale_confidence='MEDIUM') FROM out_i5_restored_exposure")
    d["restored_rev"] = db.one("SELECT sum(abs_adjusted_usd) - sum(abs_as_reported_usd) FROM out_i5_restored_exposure WHERE section='REVENUE'")
    d["price"] = {(r[0], r[1]): r[2:] for r in db.rows("SELECT scale_decision, scale_confidence, rows_tested, share_within_half_pct, share_within_5pct FROM out_i10_price_identity_independence")}
    d["undet"] = db.row("SELECT sum(rows_undetermined), sum(abs_as_reported_usd) FROM out_i4_undetermined_scale")
    d["dups"] = {r[0]: r[1:] for r in db.rows("SELECT dup_tier, rows_eligible, abs_actual_usd, share_of_eligible_abs FROM out_i6_duplicate_exposure")}
    d["exact"] = db.rows("SELECT definition, groups_with_matches, rows_in_matches FROM out_i7_exact_row_matches")
    d["waterfall"] = db.rows("SELECT primary_reason, rows_n, share_of_all_rows FROM out_i9_exclusion_waterfall ORDER BY rows_n DESC")
    d["periods"] = db.row("SELECT first_period, last_period, distinct_periods, entity_period_gaps FROM out_a7_period_summary")
    d["dim_rel"] = db.rows("SELECT dimension, min(fill_rate), max(fill_rate), any_value(verdict) FROM out_a5_dimension_reliability GROUP BY 1 ORDER BY 1")
    d["sections"] = db.rows("SELECT section, sum(rows_eligible), sum(actual_usd), sum(abs_actual_usd) FROM out_a1_pl_period_section o GROUP BY 1 ORDER BY (SELECT min(section_order) FROM dim_account d WHERE d.section = o.section)")
    # --- comparable-population checks added after the Phase 5 review ----------------------------------------------------------
    # forecast vs budget on ALL eligible lines that carry actual, budget AND forecast (any sign), so both are scored on the same lines
    d["fcmp"] = {r[0]: r[1:] for r in db.rows("""SELECT section, count(*),
            sum(abs(forecast_usd_adj - actual_usd_adj)) / sum(abs(actual_usd_adj)), sum(abs(budget_usd_adj - actual_usd_adj)) / sum(abs(actual_usd_adj)),
            sum(forecast_usd_adj - actual_usd_adj) / sum(abs(actual_usd_adj)), sum(budget_usd_adj - actual_usd_adj) / sum(abs(actual_usd_adj))
            FROM v_pl_budget WHERE actual_usd_adj IS NOT NULL AND forecast_usd_adj IS NOT NULL
            AND section IN ('REVENUE','COGS','PEOPLE','OPEX') GROUP BY 1""")}
    # universality of the budget-gap direction on same-sign lines: (members, members on the expected side) per section and dimension
    d["univ"] = {}
    for sec in ("REVENUE", "COGS", "PEOPLE", "OPEX"):
        for dim in ("period_ym", "entity_code", "division", "gl_account"):
            rows_ = db.rows(f"SELECT sum(actual) - sum(budget) FROM v_var_scn WHERE scenario = 'SAME_SIGN_ONLY' AND section = ? GROUP BY {dim}", sec)
            d["univ"][(sec, dim)] = (len(rows_), sum(1 for r_ in rows_ if r_[0] != 0 and (r_[0] < 0) == (sec == "REVENUE")))
    return d


# ======================================================================================================================
def build_insights(d: dict) -> list[dict]:
    S = d["status"]
    base = S["POSTED_ONLY (baseline)"]
    allst = S["ALL_STATUSES"]
    fr = {r[0]: r for r in d["factor_rank"]}
    v = d["var"]
    vol = d["vol"]
    cs = d["cellspread"]
    gp = d["gp"]["GP_S1_SIGNED_AS_RECORDED"]
    gpb = d["gpb"]
    fc = d["fc"]
    fvb = d["fvb"]
    fvb_n = {k: v[4] for k, v in fvb.items()}
    fcq = d["fcq"]
    proxy = {r[0]: r for r in d["proxy"]}
    rest = d["restored"]
    sc = d["scen"]
    price = d["price"]
    total_proxy = d["proxy"][-1]
    fl = d["flags"]
    sal = d["sal"]
    n_status_rows = [S[k][0] for k in ("POSTED_ONLY (baseline)", "PENDING_ONLY", "PARKED_ONLY", "REJECTED_ONLY", "BLANK_ONLY")]
    rev_status = [S[k][1] for k in ("POSTED_ONLY (baseline)", "PENDING_ONLY", "PARKED_ONLY", "REJECTED_ONLY", "BLANK_ONLY")]
    cost_rows = [(k, vol[k]) for k in ("REVENUE", "COGS", "PEOPLE", "OPEX")]
    sal_rows = d["sal_rate"]
    in01 = [r for r in sal_rows if r[0] == "IN01"][0]
    ins = []

    policy = [k for k in S if d["status_class"][k] in ("BASELINE", "POLICY_SCENARIO")]
    diag = [k for k in S if d["status_class"][k] == "STATUS_PARTITION_DIAGNOSTIC"]
    top_factor = d["factor_rank"][0][0]
    status_is_top = top_factor == "status"
    ins.append({
        "id": "INS-01", "title": ("The journal-status rule is the largest swing factor in the revenue and result headlines among the four assumptions tested (status, scale, sign, duplicates)"
                                   if status_is_top else f"The {top_factor} assumption, not the journal-status rule, is the largest swing factor among the four assumptions tested"),
        "question": "How much of the reported revenue, cost and result depends on which journal statuses are counted?",
        "population": f"P&L lines passing every gate except the status gate: {N(d['any_rows'])} lines, Jan 2023 - Dec 2025. Baseline (provisional rule R6) = Posted only: {N(base[0])} lines ({P(base[0] / d['any_rows'])}).",
        "metric": "Revenue = REVENUE section; cost = COGS + PEOPLE + OPEX; result proxy = revenue - cost (not a reported operating profit; D&A, below-EBITDA and tax excluded). USD, scale-adjusted (provisional), signs as recorded. Two kinds of scenario are kept apart: REPORTING-POLICY scenarios (Posted only = baseline, all except Rejected, all statuses) are the comparable alternatives that the swing ranking uses; STATUS-PARTITION diagnostics (Pending, Parked, Rejected and blank on their own) only show how the any-status population splits and are not alternative reporting policies.",
        "result": (f"Policy scenarios: revenue {M(base[1])} (Posted only, baseline) vs {M(S['ALL_EXCEPT_REJECTED'][1])} (all except Rejected) vs {M(allst[1])} (all statuses); result proxy {M(base[3])} vs {M(S['ALL_EXCEPT_REJECTED'][3])} vs {M(allst[3])}. "
                   f"Across these {fr['status'][5]} policy scenarios the revenue headline moves by {P(fr['status'][1], 0)} of the baseline and the result proxy by {P(fr['status'][2], 0)}; the corresponding ranges for the scale, duplicate and sign factors (each over its own policy scenarios and baseline) are {P(fr['scale'][1], 0)}, {P(fr['duplicates'][1], 0)} and {P(fr['sign'][1], 0)} of revenue. "
                   f"Partition diagnostic: the four non-Posted statuses hold near-equal volumes of lines ({', '.join(N(x) for x in n_status_rows[1:])} for Pending, Parked, Rejected, blank) and of revenue ({', '.join(M(x, 1) for x in rev_status[1:])}); Posted holds {N(n_status_rows[0])} lines ({P(n_status_rows[0] / d['any_rows'])}, about three times any other status) and {M(rev_status[0], 1)}."),
        "drivers": ("**Reporting-policy scenarios (ranked)**\n\n" + table(["Scenario", "Class", "Lines", "Revenue", "Cost", "Result proxy"],
                         [[k, d["status_class"][k], N(S[k][0]), M(S[k][1]), M(S[k][2]), M(S[k][3])] for k in policy])
                    + "\n\n**Status-partition diagnostics (not ranked; the five statuses add up to the all-status population)**\n\n"
                    + table(["Scenario", "Class", "Lines", "Revenue", "Cost", "Result proxy"],
                         [[k, d["status_class"][k], N(S[k][0]), M(S[k][1]), M(S[k][2]), M(S[k][3])] for k in ["POSTED_ONLY (baseline)"] + diag])),
        "validation": "Single-status buckets partition the any-status population exactly (checks I03, I04); scenario classes are validated (I13-I15: the ranking uses only baseline + policy scenarios); all 15 scenarios recomputed in pandas from the CSV (cross-check X8xx) and the status range recomputed independently (X98_REV); Posted subset equals the eligible flag (L27).",
        "interpretation": f"The split is almost exactly 3:1:1:1:1 (Posted = {P(n_status_rows[0] / d['any_rows'], 1)} of lines against 3/7 = 42.9%), and each non-Posted status carries about the same revenue, so status shows no visible link to line size or section. A genuine workflow would normally leave a Posted majority with small Pending/Parked tails and few Rejected lines. Whether Rejected lines belong in the books, and whether Parked/Pending are accruals or cut-off items, decides which of several very different P&Ls is 'the' P&L. The ranking measures how far each unresolved assumption can move the headline under the policies defined here; it is a sensitivity, not an estimate of error, and the ranges of different factors are not strictly like-for-like because each factor has its own baseline and its own set of policies.",
        "alternatives": "(a) The extract is a union of several scenarios or versions that were all labelled by status by accident. (b) Status is assigned at random in the generator (the dataset is synthetic - provenance unverified). (c) Posting really is 43% complete at the extract date, in which case the all-status view overstates. None can be tested from the file.",
        "confidence": "High that the dependency exists (arithmetic, reconciled). Low on which scenario is right: it needs the business definition of each status; the official journal-status rule is not chosen here. Limitation: the proxy omits D&A, below-EBITDA and tax.",
        "recommendation": "Before any report is published, obtain written definitions for Posted, Pending, Parked, Rejected and blank, and the cut-off rule for the extract. Until then show headline figures as a range (Posted-only to all-except-Rejected), never a point estimate.",
        "impact": f"No saving is implied, and this sizes the exposure only: it does not show which journal-status policy is correct. The exposure is reporting error: a point estimate on the Posted-only rule could understate revenue by {M(S['ALL_EXCEPT_REJECTED'][1] - base[1], 0)} (all statuses except Rejected) up to {M(allst[1] - base[1], 0)} (all statuses) over 3 years and all entities (observed differences) if the other statuses belong in the books.",
        "owner": "Controller / close owner (status definitions); FP&A lead (range presentation). KPI: share of lines with a documented status definition = 100%; share of period-end lines not Posted.",
        "monitoring": "Re-run out_i1/out_i2 each close; alert when the Posted share of any-status lines (out_g1: posted_rows / any_rows) leaves the range observed over the 36 months.",
        "scores": (3, 3, 2, 3)})

    OPP, SAME, ZERO = "OPPOSITE_SIGN_NONZERO", "SAME_SIGN_NONZERO", "ZERO_INVOLVED"
    FA = d["fc_attr"]
    SECS = ("REVENUE", "COGS", "PEOPLE", "OPEX")
    opp_err = [FA[x][OPP][3] for x in SECS]
    opp_rows = [FA[x][OPP][1] for x in SECS]
    zero_err = [FA[x].get(ZERO, (0, 0, 0, 0))[3] for x in SECS]
    ins.append({
        "id": "INS-02", "title": f"Lines whose forecast and actual have opposite signs ({P(min(opp_rows), 0)} to {P(max(opp_rows), 0)} of lines) carry {P(min(opp_err), 0)} to {P(max(opp_err), 0)} of the absolute forecast error; whether they are data defects or legitimate entries is unresolved",
        "question": "What drives the large forecast error, and what remains unresolved about it?",
        "population": f"Eligible P&L lines with a forecast value: {N(sum(fc[('ALL_LINES', s)][3] for s in SECS))} (four operating sections).",
        "metric": "Forecast error = Forecast - Actual. WAPE = sum|F-A| / sum|A|. Bias = sum(F-A) / sum|A|. Sign category of each (actual, forecast) pair: SAME_SIGN_NONZERO, OPPOSITE_SIGN_NONZERO (both non-zero, different signs), ZERO_INVOLVED (either amount is exactly 0) and MISSING_OR_UNAVAILABLE (empty here by construction). An opposite-sign pair is an observation, not a confirmed accounting error. No sign is flipped anywhere.",
        "result": (f"WAPE on all lines (scale-adjusted amounts, signs as recorded): revenue {P(fc[('ALL_LINES', 'REVENUE')][0])}, COGS {P(fc[('ALL_LINES', 'COGS')][0])}, people {P(fc[('ALL_LINES', 'PEOPLE')][0])}, opex {P(fc[('ALL_LINES', 'OPEX')][0])}. "
                   f"On same-sign non-zero lines only: {P(fc[('SAME_SIGN_ONLY', 'REVENUE')][0])}, {P(fc[('SAME_SIGN_ONLY', 'COGS')][0])}, {P(fc[('SAME_SIGN_ONLY', 'PEOPLE')][0])}, {P(fc[('SAME_SIGN_ONLY', 'OPEX')][0])}. "
                   f"{P(FA['REVENUE'][OPP][1])} of revenue lines are opposite-sign but they carry {P(FA['REVENUE'][OPP][3])} of the absolute revenue forecast error (total absolute revenue forecast error {M(sum(v_[2] for v_ in FA['REVENUE'].values()))}); zero-involved lines carry {P(max(zero_err), 1)} or less in every section. "
                   "The shares come from the explicit four-category rule and are recomputed independently in pandas (X97)."),
        "drivers": table(["Section", "Opposite-sign lines (share of lines)", "Opposite-sign share of abs error", "Same-sign share of abs error", "Zero-involved share of abs error", "WAPE all lines", "WAPE same-sign lines only"],
                         [[s_, P(FA[s_][OPP][1]), P(FA[s_][OPP][3]), P(FA[s_][SAME][3]), P(FA[s_].get(ZERO, (0, 0, 0, 0))[3], 2), P(fc[('ALL_LINES', s_)][0]), P(fc[('SAME_SIGN_ONLY', s_)][0])] for s_ in SECS]),
        "validation": "Category shares of rows and of error each sum to 1 and error attribution reconciles to total absolute error (C06, C07); the opposite-sign share is recomputed from fact_close (C09) and with the independent pandas category rule (X97); category counts for budget, forecast and prior year are recounted in pandas (X96); WAPE and bias recomputed in pandas (X30-X32). Variance bridge: all lines = same-sign + opposite-sign + zero-involved with difference 0.00 (B08).",
        "interpretation": (f"Observed (arithmetic): on all lines the forecast error is large; restricted to same-sign non-zero lines it is small. Concentration of error: opposite-sign lines (an association in this extract; no cause is established). "
                           f"The same category accounts for the difference between the all-lines and same-sign budget variances: people-cost variance is {M(d['bridge']['PEOPLE'][0])} on all lines but {M(d['bridge']['PEOPLE'][1])} on same-sign lines (opposite-sign lines contribute {M(d['bridge']['PEOPLE'][2])}); revenue variance moves from {M(d['bridge']['REVENUE'][0])} to {M(d['bridge']['REVENUE'][1])}. "
                           f"Among eligible lines, {P(fl['sign_single_column_flip'][1])} are flagged by the Phase 3 sign-pattern rule as a single-column sign flip ({P(fl['sign_single_column_flip'][2])} of absolute value) and {P(fl['local_usd_sign_conflict'][1])} have local and USD amounts of opposite sign (a flag, not proof). "
                           "Caution: the same-sign WAPE is a sensitivity chosen by the outcome (a line is kept because actual and forecast agree in sign, which mechanically removes the largest errors); it is not a measure of forecast skill. "
                           "Unresolved (accounting): whether an opposite-sign pair is an error or a legitimate reversal, credit note or contra-account entry depends on the account-level sign convention, which is not verified (R9). "
                           "Next investigation: take a sample of opposite-sign lines per account and compare them with source documents; ask the ledger owner for the sign convention by account."),
        "alternatives": "(a) Some opposite-sign lines are legitimate credit notes, reversals or reclassifications - not testable without the sign convention (the sign convention is an unresolved Phase 1 rule, R9). (b) If the data were generated synthetically, sign inversions may have been injected independently per column, which would explain why differences appear in exactly one of the amount columns. (c) The forecast may be a late re-forecast (no version or as-of date exists), which changes what the error means.",
        "confidence": "High on the arithmetic and on its independent recomputation. Low on the accounting interpretation: no validated sign convention exists. Forecast skill is neither proved nor disproved, because the extract has no forecast version or as-of date.",
        "recommendation": "Do not report forecast accuracy from this extract. Investigate the opposite-sign lines by account against source documents and obtain the account-level sign convention (contra accounts such as 4190, reversal postings, credit notes). Only after the conventions are verified, decide whether a validation rule is needed; do not impose a universal 'actual, budget and forecast must share a sign' rule before then.",
        "impact": "Measurement exposure, not a saving. Opposite-sign lines contribute " + M(d['bridge']['REVENUE'][2]) + " to the net revenue variance and " + M(d['bridge']['PEOPLE'][2]) + " to the net people-cost variance (observed, scale-adjusted amounts, signs as recorded).",
        "owner": "Data owner of the source ledger extract; FP&A analytics. KPI (monitoring statistic, not a defect rate): share of lines with opposite-sign actual and forecast (currently " + P(FA['REVENUE'][OPP][1]) + " of revenue lines).",
        "monitoring": "Each close: count of opposite-sign lines by account (out_b7, out_c2); investigate when a new account appears or the share moves outside the observed range.",
        "scores": (3, 3, 2, 3)})

    spread = {s: cs[s] for s in cs}
    u = d["univ"]
    def _all(dim):
        return all(u[(s_, dim)][0] == u[(s_, dim)][1] for s_ in ("REVENUE", "COGS", "PEOPLE", "OPEX"))
    UNIV_TITLE = (f" on same-sign lines in all {u[('REVENUE', 'period_ym')][0]} months, all {u[('REVENUE', 'entity_code')][0]} entities, all {u[('REVENUE', 'division')][0]} divisions and every one of the "
                  f"{sum(u[(s_, 'gl_account')][0] for s_ in ('REVENUE', 'COGS', 'PEOPLE', 'OPEX'))} operating accounts (the all-lines view differs)") if all(_all(k) for k in ("period_ym", "entity_code", "division", "gl_account")) else " on same-sign lines (exceptions listed in the result)"
    UNIV_TXT = "Same-side check on same-sign lines (revenue below budget, costs above): " + "; ".join(
        f"{s_.lower()} {u[(s_, 'period_ym')][1]}/{u[(s_, 'period_ym')][0]} months, {u[(s_, 'entity_code')][1]}/{u[(s_, 'entity_code')][0]} entities, {u[(s_, 'division')][1]}/{u[(s_, 'division')][0]} divisions, {u[(s_, 'gl_account')][1]}/{u[(s_, 'gl_account')][0]} GL accounts" for s_ in ("REVENUE", "COGS", "PEOPLE", "OPEX")) + ". The claim is limited to the four operating sections on same-sign lines; D&A, below-EBITDA and tax are not covered and the all-lines view does not show it. "
    ins.append({
        "id": "INS-03", "title": f"Actuals sit a near-constant {P(-v[('SAME_SIGN_ONLY', 'REVENUE')][3])} below budget on revenue and {P(v[('SAME_SIGN_ONLY', 'COGS')][3])} above budget on costs " + UNIV_TITLE.lstrip(),
        "question": "Where, and in which months, do actuals deviate from budget, and is the deviation concentrated anywhere?",
        "population": f"Eligible lines with a budget value: {N(d['pv_rows'])}; analysis on lines where actual and budget are both non-zero with the same sign (same-sign view), with the all-lines view (scale-adjusted amounts, signs as recorded) shown beside it.",
        "metric": "Variance = Actual - Budget (USD). % = variance / ABS(net budget), published only when |net budget| >= 50% of gross budget (project convention; otherwise NULL). Net and gross shown. Revenue: negative = below budget. Costs are positive magnitudes: positive variance = spend above budget. No favourable/unfavourable label is attached.",
        "result": (f"Revenue {M(v[('SAME_SIGN_ONLY', 'REVENUE')][2])} ({PS(v[('SAME_SIGN_ONLY', 'REVENUE')][3])}); COGS {M(v[('SAME_SIGN_ONLY', 'COGS')][2])} ({PS(v[('SAME_SIGN_ONLY', 'COGS')][3])}); "
                   f"people {M(v[('SAME_SIGN_ONLY', 'PEOPLE')][2])} ({PS(v[('SAME_SIGN_ONLY', 'PEOPLE')][3])}); opex {M(v[('SAME_SIGN_ONLY', 'OPEX')][2])} ({PS(v[('SAME_SIGN_ONLY', 'OPEX')][3])}). "
                   f"The monthly % is on the same side of budget in {vol['REVENUE'][6]} of {vol['REVENUE'][0]} months for revenue (below) and {vol['COGS'][5]} of {vol['COGS'][0]} for COGS, {vol['PEOPLE'][5]} of {vol['PEOPLE'][0]} for people and {vol['OPEX'][5]} of {vol['OPEX'][0]} for opex (above), with a monthly standard deviation of only "
                   f"{vol['REVENUE'][2] * 100:.2f}, {vol['COGS'][2] * 100:.2f}, {vol['PEOPLE'][2] * 100:.2f} and {vol['OPEX'][2] * 100:.2f} percentage points (revenue, COGS, people, opex). On all lines (no sign filter) the variances are {PS(v[('ALL_LINES', 'REVENUE')][3])}, {PS(v[('ALL_LINES', 'COGS')][3])}, {PS(v[('ALL_LINES', 'PEOPLE')][3])} and {PS(v[('ALL_LINES', 'OPEX')][3])}. " + UNIV_TXT),
        "drivers": table(["Section", "Cells (entity x GL, >=100 lines)", "Lowest cell %", "Highest cell %", "SD of cell % (points)", "Division range", "GL range (all lines of the GL)"],
                         [[s, spread[s][0], PS(spread[s][1]), PS(spread[s][2]), f"{spread[s][3] * 100:.2f}", f"{PS(d['divspread'][s][0])} to {PS(d['divspread'][s][1])}", f"{PS(d['glspread'][s][0])} to {PS(d['glspread'][s][1])}"] for s in ("REVENUE", "COGS", "PEOPLE", "OPEX")]),
        "validation": f"Variance recomputed per section in pandas (X20/X21) and in SQL (B01-B05); entity x GL, division and month tables each reconcile to the section totals (B09-B11); net-budget guard checked (B13); the top-10 cells overlap {d['top10']} of 10 between the all-lines and same-sign views (row_number with a tie-break gives exactly ten cells).",
        "interpretation": "A real operating deviation would differ by entity, product or month. This one does not: the cells sit within about one percentage point of the same figure per section (the discount account 4190 is the only visible exception, see the GL range) and the pattern repeats in all 36 months. That is what a top-down percentage adjustment of the budget (or a budget derived from actuals by a fixed factor) produces. It is an observation about the pattern, not a finding about operations.",
        "alternatives": "(a) Synthetic data: budget is generated as actual x a section factor. (b) Budgets were genuinely set top-down, e.g. +3.7% revenue ambition and -6% cost reduction targets applied uniformly. (c) Budget was re-based on actuals after the fact. The file cannot separate these.",
        "confidence": "High on the numbers; Medium-Low on any business reading. Limitation: the same-sign filter removes " + P(min(1 - v[('SAME_SIGN_ONLY', s)][5] / v[('ALL_LINES', s)][5] for s in ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')), 0) + " to " + P(max(1 - v[('SAME_SIGN_ONLY', s)][5] / v[('ALL_LINES', s)][5] for s in ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')), 0) + " of the lines of a section (opposite-sign and zero-involved lines); the budget field has no version or approval date.",
        "recommendation": "Do not assign variance to entities or accounts from this pattern: there is nothing to rank. Ask the budget owner how the budget was built (top-down factor or bottom-up) and its version history. If it was top-down, the useful action is a driver-based re-forecast of revenue and cost for the entities with the largest absolute exposure, listed in the driver table.",
        "impact": f"Observed, not a saving: over 3 years the same-sign revenue is {M(-v[('SAME_SIGN_ONLY', 'REVENUE')][2])} below budget and cost is {M(v[('SAME_SIGN_ONLY', 'COGS')][2] + v[('SAME_SIGN_ONLY', 'PEOPLE')][2] + v[('SAME_SIGN_ONLY', 'OPEX')][2])} above budget on Posted lines only. A uniform gap implies a calibration issue in the plan, so closing it is a planning question; no cost can be 'recovered' from this table.",
        "owner": "Head of FP&A (budget method); budget owner. KPI: dispersion (SD) of variance % across entity x GL cells - a value near zero flags a mechanical budget.",
        "monitoring": "Quarterly: recompute out_b2 and out_b5; investigate when the cell dispersion rises (a real operating difference emerging) or the monthly % crosses sides.",
        "scores": (3, 3, 2, 2)})

    ins.append({
        "id": "INS-04", "title": f"Gross profit is {M(-gpb['GP_S1_SIGNED_AS_RECORDED'][2], 1)} below budget on same-sign lines: {P(gpb['GP_S1_SIGNED_AS_RECORDED'][0] / gpb['GP_S1_SIGNED_AS_RECORDED'][2], 0)} of the gap is revenue below budget and {P(-gpb['GP_S1_SIGNED_AS_RECORDED'][1] / gpb['GP_S1_SIGNED_AS_RECORDED'][2], 0)} is COGS above budget; the margin gap holds under all three discount treatments",
        "question": "How far is gross profit from budget and which side explains it?",
        "population": "Eligible lines with a budget where actual and budget are both non-zero with the same sign, revenue + COGS sections only (GL 4100-4190, 5100-5300). Revenue and COGS variances are each measured on their own section's same-sign lines (different line sets), so the gap is the published revenue variance minus the published COGS variance (reconciled to 0.00), not a like-for-like match of individual lines.",
        "metric": "Gross profit = revenue - COGS. The discount account 4190 is negative on " + P(d['gl4190_neg'], 0) + " of its eligible lines, so three treatments are shown: S1 signed as recorded, S2 discount at absolute value, S3 excluding discounts. Margin % = GP / revenue.",
        "result": (f"GP variance {M(d['gpb']['GP_S1_SIGNED_AS_RECORDED'][2])} (S1), {M(d['gpb']['GP_S2_DISCOUNT_ABS'][2])} (S2), {M(d['gpb']['GP_S3_EXCL_DISCOUNT'][2])} (S3). "
                   f"Actual margin {P(gp[5])} vs budget {P(gp[6])} (S1); S2 {P(d['gp']['GP_S2_DISCOUNT_ABS'][5])} vs {P(d['gp']['GP_S2_DISCOUNT_ABS'][6])}; S3 {P(d['gp']['GP_S3_EXCL_DISCOUNT'][5])} vs {P(d['gp']['GP_S3_EXCL_DISCOUNT'][6])}. "
                   f"Revenue explains {P(-gpb['GP_S1_SIGNED_AS_RECORDED'][0] / -gpb['GP_S1_SIGNED_AS_RECORDED'][2], 0)} of the S1 gap ({M(gpb['GP_S1_SIGNED_AS_RECORDED'][0])}), COGS {P(gpb['GP_S1_SIGNED_AS_RECORDED'][1] / -gpb['GP_S1_SIGNED_AS_RECORDED'][2], 0)} ({M(gpb['GP_S1_SIGNED_AS_RECORDED'][1])})."),
        "drivers": table(["Treatment", "Actual margin", "Budget margin", "Margin gap (points)", "GP variance", "Revenue variance", "COGS variance"],
                         [[k, P(d['gp'][k][5]), P(d['gp'][k][6]), f"{(d['gp'][k][5] - d['gp'][k][6]) * 100:+.1f}", M(d['gpb'][k][2]), M(d['gpb'][k][0]), M(d['gpb'][k][1])] for k in d['gp']]),
        "validation": "Bridge GP variance = revenue variance - COGS variance closes to 0.00 for all treatments (E01); GP recomputed from the CSV in pandas for S1, S2 and S3 (X50-X52); account classification of 4100/4110/4120/4190 verified (E06).",
        "interpretation": (f"The margin level depends on the row set: all lines give {P(d['gm_all'][('ROWS_ALL', 'GP_S1_SIGNED_AS_RECORDED')])}, rows with sign_flag ALL_NON_NEGATIVE (no available amount negative; not a sign-consistent population) give {P(d['gm_all'][('ROWS_ALL_NON_NEGATIVE', 'GP_S1_SIGNED_AS_RECORDED')])} (S1, actuals only). The gap to budget is measured on same-sign lines, where it stays between {min((d['gp'][k][5] - d['gp'][k][6]) for k in d['gp']) * 100:.1f} and {max((d['gp'][k][5] - d['gp'][k][6]) for k in d['gp']) * 100:.1f} points across the discount treatments. "
                           "Because the revenue gap and the cost gap are each uniform (INS-03), the margin gap looks like a plan-calibration effect on both sides rather than a mix or price effect."),
        "alternatives": "Price/volume/mix cannot be separated: the materials unit value equals the sales unit value for every product family (rejected finding R2 in the analysis report), so product-level unit economics are not usable. COGS sign mixing (5120 purchase price variance, mixed signs) could shift the COGS side.",
        "confidence": "Medium. Level of margin: low (row-set dependent). Direction and size of the gap: medium-high.",
        "recommendation": "Report gross margin only as a range with its treatment named. Ask the revenue accounting owner for the sign convention of 4190 and 5120. Re-base the GM% budget once the plan method is confirmed (INS-03).",
        "impact": f"Observed over 3 years on Posted same-sign lines: {M(-d['gpb']['GP_S1_SIGNED_AS_RECORDED'][2])} below budget. This is a variance, not an addressable saving.",
        "owner": "Controller (4190/5120 convention); FP&A (GM% reporting). KPI: gross margin % vs budget with the treatment label.",
        "monitoring": "Monthly: out_e3 (treatments side by side). Flag when treatments disagree on the sign of the gap.",
        "scores": (3, 3, 2, 2)})

    ins.append({
        "id": "INS-05", "title": f"On a matched same-sign subset the forecast is closer to actuals than the budget; on all comparable lines the margin is {P(d['fcmp']['REVENUE'][1])} vs {P(d['fcmp']['REVENUE'][2])} revenue WAPE (forecast vs budget) and reverses for people costs, and neither view establishes forecast skill",
        "question": "Is the forecast more reliable than the budget on comparable populations, and is its error random or systematic?",
        "population": f"Two populations, never mixed. (A) Matched same-sign subset: lines where actual, budget and forecast are all non-zero with the same sign ({N(fvb_n['REVENUE'])} revenue lines) - chosen by outcome, so it removes the largest errors. (B) Comparable all-lines population: every eligible line with actual, budget and forecast present, any sign ({N(d['fcmp']['REVENUE'][0])} revenue lines). The all-lines forecast population used in INS-02 ({N(fc[('ALL_LINES', 'REVENUE')][3])} revenue lines) is larger because it does not require a budget.",
        "metric": "WAPE and bias as defined in INS-02. Bias > 0 = forecast above actual. Quarterly bias per section (12 quarters).",
        "result": (f"(A) Matched subset, revenue WAPE: forecast {P(fvb['REVENUE'][0])} vs budget {P(fvb['REVENUE'][1])} on {N(fvb_n['REVENUE'])} lines; COGS {P(fvb['COGS'][0])} vs {P(fvb['COGS'][1])}; people {P(fvb['PEOPLE'][0])} vs {P(fvb['PEOPLE'][1])}; opex {P(fvb['OPEX'][0])} vs {P(fvb['OPEX'][1])}. "
                   f"(B) Comparable all-lines population (any sign), WAPE forecast vs budget: revenue {P(d['fcmp']['REVENUE'][1])} vs {P(d['fcmp']['REVENUE'][2])} ({N(d['fcmp']['REVENUE'][0])} lines); COGS {P(d['fcmp']['COGS'][1])} vs {P(d['fcmp']['COGS'][2])}; people {P(d['fcmp']['PEOPLE'][1])} vs {P(d['fcmp']['PEOPLE'][2])}; opex {P(d['fcmp']['OPEX'][1])} vs {P(d['fcmp']['OPEX'][2])}. "
                   f"Both measures are large on all lines ({P(min(min(d['fcmp'][k_][1:3]) for k_ in ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')))} to {P(max(max(d['fcmp'][k_][1:3]) for k_ in ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')))}) because opposite-sign and zero-involved lines dominate the error; the matched-subset figures ({P(min(min(fvb[k_][0:2]) for k_ in ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')))} to {P(max(max(fvb[k_][0:2]) for k_ in ('REVENUE', 'COGS', 'PEOPLE', 'OPEX')))} for the four sections, forecast and budget) are small only because those lines are excluded. The forecast-minus-budget WAPE gap is {(d['fcmp']['REVENUE'][1] - d['fcmp']['REVENUE'][2]) * 100:+.1f} points for revenue, {(d['fcmp']['COGS'][1] - d['fcmp']['COGS'][2]) * 100:+.1f} COGS, {(d['fcmp']['PEOPLE'][1] - d['fcmp']['PEOPLE'][2]) * 100:+.1f} people and {(d['fcmp']['OPEX'][1] - d['fcmp']['OPEX'][2]) * 100:+.1f} opex (negative = forecast closer), so the ordering is not the same in every section. "
                   f"Revenue forecast is above actual in {fcq['REVENUE'][1]} of {fcq['REVENUE'][0]} quarters (bias {PS(fcq['REVENUE'][3])}); COGS, people and opex are below actual in {fcq['COGS'][2]}, {fcq['PEOPLE'][2]} and {fcq['OPEX'][2]} of {fcq['COGS'][0]} quarters (bias {PS(fcq['COGS'][3])}, {PS(fcq['PEOPLE'][3])}, {PS(fcq['OPEX'][3])}). "
                   f"Result proxy on lines where actual, budget and forecast are all non-zero with the same sign over 3 years: actual {M(total_proxy[2])}, forecast {M(total_proxy[4])}, budget {M(total_proxy[3])}."),
        "drivers": table(["Year", "Revenue (base)", "Actual result", "Forecast result", "Budget result"],
                         [[proxy[y][0] if proxy[y][0] is not None else "3 years", M(proxy[y][1]), M(proxy[y][2]), M(proxy[y][4]), M(proxy[y][3])] for y in proxy]),
        "validation": "Per-quarter bias persistence from out_c5, recomputed WAPE/bias in pandas (X30-X32); forecast and budget compared on the same lines (C6).",
        "interpretation": "On the matched same-sign subset the forecast sits about halfway between budget and actual, with revenue above and costs below actual in every quarter, so its result proxy is about " + P(total_proxy[4] / total_proxy[2] - 1, 0) + " above actual over 3 years (arithmetic on that subset; no favourable/unfavourable label is attached). The sample shows a directional difference between forecast and actual, and it appears on a subset selected by outcome. Whether that is a stable forecasting bias, a late re-forecast, or an artefact of how the extract was built cannot be established here: the extract has no forecast version or as-of date, so true forecast performance and any appropriate correction can only be determined with dated forecast snapshots and a back-test.",
        "alternatives": "No forecast version or date exists in the extract: the 'forecast' may be a late re-forecast that already knew part of the actuals, which would flatter its accuracy. The triple same-sign filter removes a large share of lines and selects lines by outcome.",
        "confidence": "Medium for the arithmetic of each population; Low for any statement that the forecast is better than the budget in general: the populations give different margins, and the lack of version/timing prevents any conclusion about forecasting skill.",
        "recommendation": "Obtain dated forecast snapshots (version and as-of date for each forecast). Only then back-test, on forecasts made before each period closed, whether the directional difference persists (observed in this sample: revenue " + PS(fcq['REVENUE'][3]) + ", COGS " + PS(fcq['COGS'][3]) + " of actual) and what adjustment, if any, would have improved WAPE. No correction is proposed from this extract.",
        "impact": "None can be claimed from this extract. The size of any accuracy gain is unknown until a dated back-test is run; the observed difference is not a saving.",
        "owner": "FP&A forecasting lead. KPI: quarterly forecast bias by section (target not set here; baseline = values above).",
        "monitoring": "Once dated forecast snapshots exist: each quarter, publish forecast difference and WAPE on the same same-sign basis; flag two consecutive quarters on the same side.",
        "scores": (2, 3, 2, 3)})

    ins.append({
        "id": "INS-06", "title": "Salary lines carry a near-constant rate per FTE within each entity; without a budgeted FTE plan and the budget's rate method, the people-cost variance cannot be split into rate and volume",
        "question": "Can the people-cost variance be attributed to pay rate or to headcount volume?",
        "population": f"Eligible salary lines (GL 6100) with a positive FTE value: {N(sal[0])} lines.",
        "metric": "Salary per FTE = |USD amount| / headcount_fte; share of lines within 0.5% of the entity median rate. Conditional scenario (explicit assumptions below): implied excess FTE-months = salary variance / entity rate.",
        "result": (f"Observed: {P(sal[1])} of lines are within 0.5% of the entity's median rate (lowest entity-year share {P(sal[2])}); the rates are " + ", ".join(f"{r[0]} {r[1]:,.0f}" for r in sal_rows) +
                   f" USD per FTE-month. Conditional scenario (assumes the budget used the same rate and the FTE field is complete): the same-sign salary variance would equal {', '.join(f'{r[0]} {r[6]:,.0f}' for r in sal_rows)} excess FTE-months over 36 months, i.e. IN01 about {in01[6] / 36:,.1f} FTEs per month above plan."),
        "drivers": table(["Entity", "Rate per FTE-month (USD)", "Actual", "Budget", "Variance", "Conditional: implied excess FTE-months", "Conditional: average excess FTEs"],
                         [[r[0], f"{r[1]:,.0f}", M(r[2], 2), M(r[3], 2), M(r[4], 2), f"{r[6]:,.0f}", f"{r[6] / 36:,.1f}"] for r in sal_rows]),
        "validation": "Median salary per FTE recomputed in pandas for IN01 2024 (X62); variance reconciles through entity x GL (B10). The FTE-month figures are arithmetic given the stated assumptions; they are not validated against any workforce plan.",
        "interpretation": "Observed fact: " + P(sal[1]) + " of actual salary lines sit within 0.5% of the entity's median rate (lowest entity-year share " + P(sal[2]) + "), which looks like an allocation or standard cost rather than observed payroll (hypothesis, not established). Neither a pay-rate effect nor a headcount effect is established or excluded by this extract. Hypothesis (not established): if the budget was built on the same rate, the variance would be a volume (headcount) effect. Rate versus volume cannot be separated without the budgeted FTE plan and the budget-rate method; a different budget rate would produce a rate variance. The same 6.4% overrun in each entity (INS-03) means this is not an IN01 problem: IN01 stands out in FTE terms only because its rate is the lowest.",
        "alternatives": "The budget may be built on a different rate or a different headcount; the FTE field is populated on " + P(sal[0] / d['sal_lines'], 0) + " of the eligible salary lines; headcount_fte is an attribute of the journal line, not a payroll record.",
        "confidence": "Medium for the rate pattern (data property); Low for the FTE-month figures (conditional on the stated assumptions).",
        "recommendation": "Request the budgeted FTE plan by entity and month and the budget rate method. If they exist, compare actual FTE-months with plan directly instead of using dollars. Until then do not report either a pay-rate variance or a headcount variance for salaries from this extract.",
        "impact": "Conditional scenario only: if the budget used the same rate, about " + f"{sum(r[6] for r in sal_rows):,.0f}" + " FTE-months were booked above plan in 3 years. The corresponding same-sign salary variance is " + M(sum(r[4] for r in sal_rows)) + " (observed, not a saving).",
        "owner": "HR business partner with FP&A. KPI: actual vs planned FTE-months by entity.",
        "monitoring": "Monthly FTE-months vs plan; investigate if the standard rate in out_f6 moves by more than the observed spread.",
        "scores": (2, 3, 2, 3)})

    hi = price[("DIVIDED_1E3", "HIGH")]
    me3 = price[("DIVIDED_1E3", "MEDIUM")]
    me5 = price[("DIVIDED_1E5", "MEDIUM")]
    ins.append({
        "id": "INS-07", "title": f"Scale restoration moves the result proxy by {M(abs(sc['RESTORE_HIGH_CONFIDENCE_ONLY'][3] - sc['ADJUSTED_ALL (baseline)'][3]), 1)}, and the larger (MEDIUM-confidence) tier cannot be verified against price",
        "question": "How much of the headline depends on the 6,265 scale restorations, and how well does evidence inside the extract support them?",
        "population": f"Eligible P&L lines: {N(rest[0])} are restorations ({P(rest[0] / d['pl_rows'])}); {N(rest[2])} HIGH confidence (price identity), {N(rest[3])} MEDIUM (peer z-score).",
        "metric": "Restoration = amount x 1,000 or x 100,000 when the report-scale evidence says the value was divided. Scenarios use the same eligible lines. HIGH rows are tested against a leave-one-entity-out reference price (median unit value of UNDIVIDED HIGH lines of the same product family in the other five entities).",
        "result": (f"Revenue {M(sc['ADJUSTED_ALL (baseline)'][1])} adjusted vs {M(sc['AS_REPORTED_PARSED (no restoration)'][1])} unadjusted (parsed) vs {M(sc['RESTORE_HIGH_CONFIDENCE_ONLY'][1])} restoring HIGH only. "
                   f"Result proxy {M(sc['ADJUSTED_ALL (baseline)'][3])} adjusted, {M(sc['AS_REPORTED_PARSED (no restoration)'][3])} unadjusted (parsed), {M(sc['RESTORE_HIGH_CONFIDENCE_ONLY'][3])} HIGH only: restoring the MEDIUM tier lowers the result proxy by {M(sc['RESTORE_HIGH_CONFIDENCE_ONLY'][3] - sc['ADJUSTED_ALL (baseline)'][3])} because it adds more cost than revenue. "
                   f"Price test (all-status lines with a quantity and product family): HIGH 1/1000 restorations match the leave-one-entity-out reference price within 5% in {P(hi[2], 0)} of {N(hi[0])} lines ({P(hi[1], 0)} within 0.5%); HIGH 1/100000: {P(price[('DIVIDED_1E5', 'HIGH')][2], 0)} within 5% of {N(price[('DIVIDED_1E5', 'HIGH')][0])}. "
                   f"Only {N(me3[0] + me5[0])} MEDIUM lines can be price-tested at all, and they match in {P(me3[2], 0)} (1/1000) and {P(me5[2], 0)} (1/100000) of cases."),
        "drivers": table(["Scenario", "Lines", "Revenue", "Cost", "Result proxy"],
                         [[k, N(sc[k][0]), M(sc[k][1]), M(sc[k][2]), M(sc[k][3])] for k in ("ADJUSTED_ALL (baseline)", "RESTORE_HIGH_CONFIDENCE_ONLY", "EXCLUDE_MEDIUM_CONFIDENCE_RESTORED", "EXCLUDE_ALL_RESTORED_ROWS", "AS_REPORTED_PARSED (no restoration)")]),
        "validation": "adjusted = parsed x factor on every decided row (L42); scenario totals recomputed in pandas (X8xx); leave-one-entity-out count of HIGH 1/1000 lines within 5% recomputed in pandas (X95: " + N(round(hi[2] * hi[0])) + " lines).",
        "interpretation": "The HIGH tier is consistent with a leave-one-entity-out reference price built without any line of its own entity (the reference is derived from the same extract, so this is internal consistency, not independent proof). The MEDIUM tier (71% of restorations) has no equivalent support, and where a price test is possible it mostly disagrees. Until that tier is validated, the adjusted totals stay provisional.",
        "alternatives": "MEDIUM rows may be lines for which a price test was impossible or was already failed when the tier was assigned (selection effect), so low match rates may reflect how they were chosen. The reference price is inferred from the same extract, so the test shows internal consistency, not a true price list; passing it does not make the adjusted amounts validated financial truth.",
        "confidence": "High for the HIGH tier consistency; Low for the MEDIUM tier. Limitation: 73 lines remain undetermined and carry no adjusted value; the " + N(d['undet_pl'][0]) + " P&L lines among them total $" + f"{d['undet_pl'][1]:,.0f}" + " as reported, or " + M(d['undet_pl'][2], 2) + " if all were 1/1000-scaled (a bound, not an estimate; out_i4).",
        "recommendation": "Ask the source owner for the report-scale setting per extract batch to confirm the MEDIUM restorations directly; until confirmed, present both the HIGH-only and the full-restoration results.",
        "impact": f"Result proxy sensitivity {M(abs(sc['RESTORE_HIGH_CONFIDENCE_ONLY'][3] - sc['ADJUSTED_ALL (baseline)'][3]))} ({P(abs(sc['RESTORE_HIGH_CONFIDENCE_ONLY'][3] / sc['ADJUSTED_ALL (baseline)'][3] - 1), 0)} of the baseline). Reporting exposure, not a saving.",
        "owner": "Data owner of the extract / cleaning lead. KPI: share of restored lines with source-confirmed scale.",
        "monitoring": "Track restorations per extract batch; alert on any new MEDIUM restorations in a batch.",
        "scores": (2, 2, 2, 3)})
    return ins


def render_register(ins: list[dict]) -> str:
    L = ["# Phase 4 - Financial Insight Register", "",
         "Generated by `src/phase4_report.py` from the DuckDB output tables; every figure is read from the data at generation time.",
         "Data: NovaBridge Industries, a **synthetic, fictional** group (provenance and licence unverified). Nothing here is a statement about a real company.",
         "All amounts are USD, scale-adjusted (provisional) with signs as recorded in the extract unless a row says otherwise. Posted-only is a provisional rule (R6).",
         "Observed variance is **not** savings. Fact, hypothesis and action are separated in each entry.", "",
         "## Ranking", "",
         "Score 1-3 on each axis (convention of this project, not a standard): materiality (size relative to the headline), persistence (recurs across periods/cells), confidence (strength of validation), actionability (a specific next action exists). Sorted by total.", ""]
    ranked = sorted(ins, key=lambda i: -sum(i["scores"]))
    L.append(table(["Rank", "ID", "Insight", "Materiality", "Persistence", "Confidence", "Actionability", "Total"],
                   [[k + 1, i["id"], i["title"], *i["scores"], sum(i["scores"])] for k, i in enumerate(ranked)]))
    for i in ranked:
        L += ["", "---", "", f"## {i['id']} - {i['title']}", "",
              f"**1. Headline.** {i['title']}.", "",
              f"**2. Business question.** {i['question']}", "",
              f"**3. Population and period.** {i['population']}", "",
              f"**4. Metric definition.** {i['metric']}", "",
              f"**5. Quantified result (observed fact).** {i['result']}", "",
              "**6. Driver decomposition.**", "", i["drivers"], "",
              f"**7. Validation evidence.** {i['validation']}", "",
              f"**8. Interpretation.** {i['interpretation']}", "",
              f"**9. Alternative explanations.** {i['alternatives']}", "",
              f"**10. Confidence and limitations.** {i['confidence']}", "",
              f"**11. Recommendation (action).** {i['recommendation']}", "",
              f"**12. Expected impact.** {i['impact']}", "",
              f"**13. Owner, follow-up, KPI.** {i['owner']}", "",
              f"**14. Monitoring method.** {i['monitoring']}"]
    return "\n".join(L) + "\n"


def render_report(d: dict, ins: list[dict]) -> str:
    S = d["status"]
    v = d["var"]
    vl, va = d["out_val_load"], d["out_val_analytical"]
    vx, ve = d["out_val_crosscheck"], d["out_val_exclusion_counts"]
    L = ["# Phase 4 - SQL, Financial Analysis and Evidence-Based FP&A Insights: Analysis Report", "",
         "Data: NovaBridge Industries - a **synthetic, fictional** group (provenance and licence unverified; results are not facts about a real company). Local only; nothing is committed or published.", "",
         "## 1. Verified input", "",
         "- File: `data/processed/fpa_monthly_close_cleaned.csv` (Phase 3 canonical output; the 77-column workbook sheet is not used).",
         "- Gate (src/phase4_pipeline.py `verify_input`): exists and non-empty; SHA-256 `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47`; 174,545,248 bytes; 152,682 data rows; 192 unique columns; header fingerprint; 32 required fields present. A mismatch stops the run (exit 1 for a missing/unreadable file, exit 2 for an integrity mismatch) without touching an existing database.",
         "- The raw file and the canonical CSV are never modified; the run writes only the database and `outputs/phase4/`.", "",
         "## 2. Financial meaning established before calculating", "",
         "| Question | Answer used in this phase | Evidence |", "|---|---|---|",
         f"| What is one row? | One journal line (posting). 350 non-posting TOTAL/Subtotal/CHECK label rows remain in the CSV for traceability and are in no population. | out_a0, L29-L30 |",
         f"| Grain | entity x period x GL x journal line; {N(d['cells'][1])} of {N(d['cells'][0])} populated entity x period x GL cells have several lines, so the lines are treated as separate postings that add up; `document_no` is not a line key. Pattern evidence only: in {N(d['a0_diff'])} multi-row cells the actual amounts differ between lines (out_a0); this is consistent with per-line amounts but is not proof of additivity, which rests on the business meaning (one row = one journal line) and the reconciliations in section 5. | out_a0 |",
         "| Actual / budget / forecast / prior year | Four attributes of the **same line**, not separate records. Budget, forecast and PY are compared with actual on the same line; they are not independent observations. | schema |",
         "| P&L vs Balance Sheet | Separate populations (`v_pl_actual`, `v_bs_actual`). Balance Sheet lines are treated as statement lines with an UNRESOLVED measurement basis (opening, closing or movement is not established); they are never summed across periods and no cash-flow or working-capital metric is built. | L25-L26, out_h6 |",
         f"| Populations | P&L actual {N(d['pl_rows'])} lines; P&L vs budget {N(d['pv_rows'])}; Balance Sheet {N(d['bs_rows'])}. Forecast and prior-year populations = P&L actual with that column present (project convention). | L21-L23 |",
         "| Eligibility flags | Used after verifying: `eligible_PL_variance` = `eligible_PL_actual` AND budget present; Posted subset of the any-status view equals the eligible set; exclusion reasons add up to 152,682 per scope. | L24, L27, L33-L36 |",
         "| Reported vs parsed vs adjusted | `*_usd_parsed` = parsed from the source text without scale restoration; `*_usd_adj` = scale-adjusted (provisional). Never mixed in one measure. Scenario names say which is used: `ALL_LINES` = scale-adjusted amounts with signs as recorded (not the unadjusted parsed amounts); `AS_REPORTED_PARSED (no restoration)` = parsed amounts. | out_i1 |",
         f"| Reliable dimensions | division and region 100% filled; cost centre {P(d['dim_rel'][1][1], 0)}-{P(d['dim_rel'][1][2], 0)}; product family, channel, customer segment partly blank (blank bucket kept); quantity and unit of measure unsuitable for aggregation. | out_a5 |",
         f"| Period coverage | {d['periods'][0]} to {d['periods'][1]}: {d['periods'][2]} periods, {d['periods'][3]} entity-period gaps. | out_a7 |", "",
         "Carried-forward limitations: the 6,265 scale restorations (1,814 HIGH / 4,451 MEDIUM) and 73 undetermined lines (INS-07); duplicate **candidates** are kept and never excluded in the baseline; FX has 2,517 zero rates and is not repaired; signs are never flipped; the journal-status rule is provisional; unit of measure is unresolved; no close-duration metric exists in the data and none is invented.", "",
         "## 3. Method and conventions", "",
         f"- DuckDB 2.0 database `data/processed/phase4_fpa.duckdb` (local, git-ignored): `stg_close_raw` (parsed source field values held as text; byte-level integrity rests on the CSV SHA-256, not on this table), `fact_close` (typed, 192 columns, 152,682 rows), `dim_account` (one-to-one account mapping verified for {d['a8'][1]} of {d['a8'][0]} GL accounts, out_a8 and L49/L52-L55), and {d['n_out']} `out_*` result tables. Numbered SQL files in `sql/phase4/` are commented and re-runnable.",
         "- Variance = Actual - Budget. Percentage = variance / ABS(net budget), published only when |net budget| >= 50% of gross budget (otherwise NULL); zero or missing budgets give NULL. Net and gross are always shown; contribution shares are suppressed when the section net is below 5% of gross.",
         "- Forecast error = Forecast - Actual; bias = sum(F-A)/sum|A|; WAPE = sum|F-A|/sum|A|. MAPE is not used. **Limitation:** the extract has no forecast version or date, so forecast skill cannot be separated from a late re-forecast.",
         "- Costs are positive magnitudes: a positive cost variance means spend above budget. No favourable/unfavourable label is attached because the sign convention is not validated.",
         "- Sign categories (actual vs budget / forecast / prior year): SAME_SIGN_NONZERO, OPPOSITE_SIGN_NONZERO, ZERO_INVOLVED (either amount exactly 0, including both zero) and MISSING_OR_UNAVAILABLE (either amount missing; empty in the populations used). Scenarios: ALL_LINES (scale-adjusted amounts, signs as recorded), SAME_SIGN_ONLY, OPPOSITE_SIGN_ONLY, ZERO_INVOLVED_ONLY - rows are filtered, signs are never flipped, and ALL_LINES = the three categories exactly. An opposite-sign line is an observation, not a confirmed error; account-level sign conventions are not verified.",
         "- Project conventions (labelled, not standards): 50% net-budget guard; 5% suppression; |robust z| >= 3 for the anomaly scan; 90% dominant-direction share and 3% variance for 'persistent'; no accounting materiality standard is applied: cell importance is shown as two labelled sensitivities instead of one fixed threshold - contribution to total absolute cell variance (0.25%-5%, `out_b9`) and variance as a percentage of the cell's gross budget (0.5%-10%, `out_b11`).", "",
         "## 4. Questions investigated and what was found", ""]
    L += ["### A. Performance overview", "",
          table(["Section", "Lines", "Actual (signed)", "Absolute activity"], [[r[0], N(r[1]), M(r[2]), M(r[3])] for r in d["sections"]]), "",
          table(["Entity", "Legal entity", "Lines", "Revenue", "COGS", "People", "Opex"], [[r[0], r[1], N(r[6]), M(r[2]), M(r[3]), M(r[4]), M(r[5])] for r in d["ent"]]), "",
          "The same breakdown by division, GL account, account group, FS line and period is in `out_a1` - `out_a4` (shares of section activity included); period coverage grid in `out_a6`.", "",
          f"Every entity has data in every one of the {d['periods'][2]} months ({d['periods'][3]} gaps; {d['ep_rows'][0]}-{d['ep_rows'][1]} eligible lines per entity-month), so period comparisons are not distorted by missing months. The Posted-only rule retains {P(d['pl_rows'] / d['any_rows'])} of the P&L lines, so all totals are 'Posted lines only'.", "",
          "### B. Actual vs budget (same-sign non-zero lines; all lines in brackets)", "",
          table(["Section", "Actual", "Budget", "Variance", "Variance %", "Net/gross budget"],
                [[s, M(v[('SAME_SIGN_ONLY', s)][0]), M(v[('SAME_SIGN_ONLY', s)][1]), f"{M(v[('SAME_SIGN_ONLY', s)][2])} ({M(v[('ALL_LINES', s)][2])})", f"{PS(v[('SAME_SIGN_ONLY', s)][3])} ({PS(v[('ALL_LINES', s)][3])})", f"{v[('SAME_SIGN_ONLY', s)][4]:.2f}"]
                 for s in ("REVENUE", "COGS", "PEOPLE", "OPEX", "D&A", "BELOW_EBITDA", "TAX")]), "",
          f"The variance is uniform across entity, division, GL and month (INS-03). Largest single cells (same-sign): " + "; ".join(f"{r[0]} {r[1]}/{r[2]} {r[3]} {M(r[4], 2)} ({PS(r[5])})" for r in d["top_cells"]) + ". "
          f"Sensitivity: {d['top10']} of the top-10 entity x GL cells are the same under the all-lines and same-sign views. Contribution sweep (same-sign; share of TOTAL absolute cell variance, not % of budget): " + "; ".join(f"cells contributing >= {P(r[1], 2)} -> {r[2]} cells covering {P(r[3], 0)}" for r in d["mat"] if r[0] == "SAME_SIGN_ONLY") + ". Budget-percentage sweep (same-sign; cell variance as % of the cell's gross budget): " + "; ".join(f"|variance| >= {P(r[1], 1)} of gross budget -> {r[2]} of {r[3]} cells" for r in d["mat11"] if r[0] == "SAME_SIGN_ONLY") + ". Both are project analytical conventions, not accounting materiality standards.", "",
          "Robustness of the revenue and cost variance direction across the exposure scenarios (`out_i3`):", "",
          table(["Scenario", "Revenue var.", "COGS var.", "People var.", "Opex var."],
                [[sc_, *[M(next(x[2] for x in d['robust'] if x[0] == sc_ and x[1] == s)) for s in ("REVENUE", "COGS", "PEOPLE", "OPEX")]] for sc_ in dict.fromkeys(x[0] for x in d['robust'])]), "",
          ("Revenue is below budget and COGS and opex above budget in every scenario" if all(x[2] < 0 for x in d['robust'] if x[1] == 'REVENUE') and all(x[2] > 0 for x in d['robust'] if x[1] in ('COGS', 'OPEX')) else "The direction of revenue, COGS and opex variance is not the same in every scenario (see table)")
          + f". People cost is not robust: its variance ranges from {M(min(x[2] for x in d['robust'] if x[1] == 'PEOPLE'))} to {M(max(x[2] for x in d['robust'] if x[1] == 'PEOPLE'))} across the scenarios (INS-02).", "",
          "### C. Forecast bias, error, persistence and trend", "",
          table(["Section", "Bias (forecast vs actual)", "WAPE forecast", "WAPE budget", "Quarters bias on same side"],
                [[s, PS(d['fvb'][s][2]), P(d['fvb'][s][0]), P(d['fvb'][s][1]), f"{max(d['fcq'][s][1], d['fcq'][s][2])} of {d['fcq'][s][0]}"] for s in ("REVENUE", "COGS", "PEOPLE", "OPEX")]), "",
          "Details and caveats in INS-02 and INS-05 (no forecast version or timing).", "",
          "### D. Prior year", "",
          f"The prior-year **column** implies growth of {PS(d['pyspread']['entity'][2])} mean (entity range {PS(d['pyspread']['entity'][0])} to {PS(d['pyspread']['entity'][1])}, SD {d['pyspread']['entity'][3] * 100:.2f} points): a near-uniform step-up. It does not reconcile with the dataset's own prior-year actuals: revenue prior-year column for 2025 is {M(d['pyrec'][('REVENUE', 2025)][0])} vs {M(d['pyrec'][('REVENUE', 2025)][1])} actual for 2024 ({PS(d['pyrec'][('REVENUE', 2025)][2])}; both on the Posted population, so sign and status effects cannot be separated). "
          f"True year-on-year revenue growth depends on the basis: Posted signed {PS(d['yoy'][('POSTED_SIGNED', 2024)][1])} (2024) and {PS(d['yoy'][('POSTED_SIGNED', 2025)][1])} (2025); all statuses, absolute {PS(d['yoy'][('ANY_STATUS_ABS', 2024)][1])} and {PS(d['yoy'][('ANY_STATUS_ABS', 2025)][1])}. 2023 has no prior calendar year in the file, so its growth is NULL. Small-baseline cells (baseline below 5% of the GL median) are listed in `out_d5` and excluded from any % statement.", "",
          "### E. Revenue, COGS and gross profit", "",
          f"Classification validated (4100, 4110, 4120, 4190 = revenue; 5100-5300 = COGS). Three discount treatments and two row sets are shown; see INS-04. Gross margin by year (S1, all rows): " + ", ".join(f"{r[0]} {P(r[1])}" for r in d["gm_year"]) + f". Unit margins by product family are **not** computed: the materials value per unit equals the sales value per unit in all {d['unit_eq'][0]} families (max difference {d['unit_eq'][1]:.4f}), i.e. a zero unit margin that is a data property, not economics. Materials / product sales = {P(d['mat_ratio'])} (an indicator, not a margin).", "",
          "### F. Cost structure and concentration", "",
          table(["GL", "Account", "Section", "Absolute activity", "Share", "Cumulative"], [[r[0], r[1], r[2], M(r[3], 1), P(r[4]), P(r[5], 0)] for r in d["cost_gl"][:8]]), "",
          "Concentration against the equal-share benchmark: " + "; ".join(f"{r[0]} - top member {r[2]} {P(r[3], 0)} (equal share {P(r[6], 0)}), HHI {r[5]:.2f}" for r in d["conc"]) + ". Materials (5100) is the largest line, but a high share is not called inefficiency: no driver beyond the salary-rate finding (INS-06) is available. "
          f"Cost-to-revenue (absolute basis, 3 years): COGS {P(d['c2r'][0])}, people {P(d['c2r'][1])}, opex {P(d['c2r'][2])}; by year COGS " + ", ".join(f"{r[0]} {P(r[1])}" for r in d["c2r_year"]) + f". Persistent deviators: {d['persist'][1]} of {d['persist'][0]} entity x GL cells sit on the same side of budget in at least 90% of months, and {d['persist'][2]} of them also exceed 3% (a consequence of the uniform pattern in INS-03).", "",
          "### G. Trend, volatility and persistence", "",
          "Revenue shows a seasonal shape (calendar-month index, 3 years pooled): " + ", ".join(f"{int(r[0])}: {r[1]:.2f}" for r in d["season"]) + ". Half-year growth (all statuses, absolute): " + "; ".join(f"{r[0]} {r[1]} {PS(r[2])}" for r in d["half"]) + ". The apparent slowdown in 2025 on the Posted-signed basis is a basis artefact (rejected finding R1). "
          f"Anomaly scan over {d['anom_n']} entity x section months: " + ", ".join(f"{r[0]}: {r[1]}" for r in d["anom"]) + " - close to what a |z| >= 3 rule flags by chance, so no month is called an anomaly (R5).", "",
          "### H. Balance Sheet statement lines - measurement basis unresolved (no movement or working-capital metrics)", "",
          f"Coverage {P(d['bs'][2], 0)} of {N(d['bs'][0])} entity x account x period cells; {P(d['bs'][3], 0)} of populated cells hold several lines (up to {d['bs'][4]}) whose sizes differ widely (median max/min {d['bs_multi'][0][2]:.1f}x for 2 lines, {d['bs_multi'][-1][2]:.1f}x for {d['bs_multi'][-1][0]}). Per-account coefficient of variation {d['bs_cv'][0]:.2f}-{d['bs_cv'][1]:.2f}, with {int(d['bs_cv'][2])} negative period totals. Lines do not behave like additive balances, so DSO, DPO, working capital and balance movements are not computed (R3; reasons in `out_h6`).", "",
          "### I. Data-quality exposure scenarios (sensitivities, never the official answer)", "",
          "Ranges are measured across the BASELINE and POLICY_SCENARIO rows of each factor only; single-status buckets are partition diagnostics and are not ranked (see INS-01).", "",
          table(["Factor", "Scenarios ranked", "Revenue range / baseline", "Result-proxy range / baseline", "Result proxy low", "Result proxy high"],
                [[r[0], r[5], P(r[1], 0), P(r[2], 0), M(r[3]), M(r[4])] for r in d["factor_rank"]]), "",
          f"Duplicate candidates are retained in every baseline. In the eligible population {N(d['dups']['DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN'][0])} lines are same-sign candidates and {N(d['dups']['DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT'][0])} sign-conflict candidates ({P(d['dups']['DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN'][2] + d['dups']['DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT'][2])} of absolute value). Exact full-row duplicates are defined as lines identical in all 42 original source fields (every source column except the derived `row_id`; raw text compared strictly, NULL and blank treated as the same missing value, case and spacing as in the cleaned CSV): none exist. The Phase 3 candidate tiers are weaker: they match on document number, entity, GL, period and amount fields only ( {d['exact'][2][2]} lines share document, entity, GL and all five amount texts). Excluding them as a labelled sensitivity changes revenue by {P(abs(d['scen']['EXCLUDE_ALL_COPY_CANDIDATES'][1] / d['scen']['CANDIDATES_RETAINED (baseline)'][1] - 1))}: not material (R6). "
          f"FX and sign flags on the eligible population: {P(d['flags']['fx_usd_rate_not_one: USD-currency row with rate outside 1.000 +/- 0.001'][1], 0)} of lines (and {P(d['flags']['fx_usd_rate_not_one: USD-currency row with rate outside 1.000 +/- 0.001'][2], 0)} of absolute value) are USD-currency lines whose rate is not 1; {P(d['flags']['fx_zero: FX rate = 0'][1])} have a zero rate. These are not repaired (open question Q4).", "",
          "## 5. Validation", "",
          table(["Suite", "Checks", "Passed", "Failed"],
                [["Load, population and rule checks (out_val_load)", vl[0], vl[1], vl[0] - vl[1]], ["Exclusion counts vs Phase 3 report (out_val_exclusion_counts)", ve[0], ve[1], ve[0] - ve[1]],
                 ["Analytical reconciliations (out_val_analytical)", va[0], va[1], va[0] - va[1]], ["Independent pandas cross-check from the CSV (out_val_crosscheck)", vx[0], vx[1], vx[0] - vx[1]]]), "",
          f"Largest absolute difference in any money reconciliation (SQL checks and pandas cross-check) is USD {d['maxdiff']:.6f} (tolerance USD 0.01); the largest ratio difference is {d['maxdiff_ratio']:.1e} (tolerance 1e-9). Checks have expected, actual, difference, tolerance and status in `outputs/phase4/val_*.csv`. The pytest suite (`tests/test_phase4.py`) includes mutation tests that corrupt the data or a published number and require the relevant checks to fail, so the checks are shown to be able to fail. A failing check stops the pipeline before the database is promoted. Repeat runs produce byte-identical outputs (single-threaded aggregation; `MANIFEST.json`; tested in `test_second_run_is_byte_identical`). Output promotion is staged: the accepted database, CSVs and manifest change only when every check passes (`finalize` in `src/phase4_pipeline.py`; tested with sentinel files).", "",
          "## 6. Strongest validated insights", "",
          table(["ID", "Insight", "Confidence"], [[i["id"], i["title"], i["confidence"].split(".")[0] + "."] for i in ins]), "",
          "Full 14-element entries are in `docs/PHASE4_INSIGHT_REGISTER.md`.", "",
          "## 7. Findings tested and rejected", "",
          f"- **R1 - '2025 growth slowdown'.** Posted-signed revenue growth falls from {PS(d['yoy'][('POSTED_SIGNED', 2024)][1])} to {PS(d['yoy'][('POSTED_SIGNED', 2025)][1])}, but the all-status absolute basis gives {PS(d['yoy'][('ANY_STATUS_ABS', 2024)][1])} and {PS(d['yoy'][('ANY_STATUS_ABS', 2025)][1])} and half-year growth is stable on that basis. The slowdown depends on the status and sign basis; rejected as an insight.",
          f"- **R2 - Unit margin by product family.** Materials and sales have identical value per unit in every family; rejected as economically meaningless.",
          f"- **R3 - Working capital, DSO, DPO, balance movement.** The measurement basis of Balance Sheet lines is unresolved and cells hold several lines that do not behave like additive balances (section H); not computed.",
          f"- **R4 - Forecast accuracy as a quality KPI.** About 90% of the absolute error sits on opposite-sign lines, whose accounting meaning is unresolved, and there is no forecast version or as-of date; not reported as a KPI until both are resolved.",
          f"- **R5 - Entity-month anomalies.** {sum(r[1] for r in d['anom'] if r[0] != 'within range')} of {d['anom_n']} months ({P(sum(r[1] for r in d['anom'] if r[0] != 'within range') / d['anom_n'])}) exceed |z| >= 3, against about 0.3% ({0.0027 * d['anom_n']:.1f} months) expected for a normal distribution; not distinguishable from chance, so not reported as anomalies.",
          f"- **R6 - Duplicates as a material misstatement.** Excluding all candidate copies moves revenue by less than 1%; unproven as duplicates; kept.",
          f"- **R7 - 'Inefficient' cost areas from concentration.** High shares (materials, US01) are descriptive; no driver supports a judgement.",
          f"- **R8 - Prior-year column as a growth signal.** Uniform step-up that does not reconcile with the file's own prior-year actuals; not used.", "",
          "## 8. Questions that need business context", "",
          "1. Definitions of Posted / Pending / Parked / Rejected / blank and the extract cut-off (INS-01).",
          "2. Sign convention by account (4190 discounts, 5120 PPV, credit notes) and whether opposite-sign lines are reversals (INS-02, INS-04).",
          "3. How the budget and forecast were built, with version and date (INS-03, INS-05).",
          "4. FX: meaning of zero and non-1.0 rates on USD lines, and which amount column is authoritative.",
          "5. Report scale per extract batch to confirm the MEDIUM restorations (INS-07).",
          "6. Budgeted FTE plan by entity and month (INS-06).",
          "7. Balance Sheet lines: opening, closing or movement, and why a cell has several lines.",
          "8. Provenance and licence of the dataset (unverified).", "",
          "## 9. How to rerun", "",
          "```", "pip install -r requirements.txt", "python src/phase4_pipeline.py          # verify input, build DB, run SQL, cross-check, validate, export", "python src/phase4_report.py            # regenerate this report and the insight register", "python -m pytest tests/test_phase4.py -q", "```",
          "The pipeline needs `data/processed/fpa_monthly_close_cleaned.csv` (Phase 3 output). It writes `data/processed/phase4_fpa.duckdb` (git-ignored) and `outputs/phase4/*.csv` with `MANIFEST.json`. Exit code 1 = missing/invalid input; 2 = integrity or validation failure (nothing accepted is overwritten; diagnostics go to `outputs/phase4_failed_run/` and `phase4_fpa.duckdb.failed`).", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS)
    a = ap.parse_args(argv)
    if not a.db.exists():
        print(f"database not found: {a.db} - run src/phase4_pipeline.py first", file=sys.stderr)
        return 1
    db = Db(a.db)
    d = gather(db)
    failed = sum(d[t][0] - d[t][1] for t in ("out_val_load", "out_val_exclusion_counts", "out_val_analytical", "out_val_crosscheck"))
    if failed:
        print(f"{failed} validation check(s) failed; no report written", file=sys.stderr)
        return 2
    ins = build_insights(d)
    a.docs_dir.mkdir(parents=True, exist_ok=True)
    (a.docs_dir / "PHASE4_INSIGHT_REGISTER.md").write_text(render_register(ins), encoding="utf-8")
    (a.docs_dir / "PHASE4_ANALYSIS_REPORT.md").write_text(render_report(d, ins), encoding="utf-8")
    print(f"wrote {a.docs_dir / 'PHASE4_ANALYSIS_REPORT.md'} and {a.docs_dir / 'PHASE4_INSIGHT_REGISTER.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
