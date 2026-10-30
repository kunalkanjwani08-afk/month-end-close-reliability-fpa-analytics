"""Phase 4 independent cross-check.

Recomputes the material Phase 4 aggregates with pandas, straight from the canonical cleaned CSV, and compares them
with the tables produced by the DuckDB SQL (out_* tables). No SQL view or SQL logic is reused: populations and
metrics are re-implemented from the documented definitions, so an error in a SQL join, filter or window cannot
cancel itself out.

Used by src/phase4_pipeline.py (step 3b) and by tests/test_phase4.py. Can be run on its own:
    python src/phase4_crosscheck.py [--csv PATH] [--db PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "processed" / "fpa_monthly_close_cleaned.csv"
DEFAULT_DB = ROOT / "data" / "processed" / "phase4_fpa.duckdb"

USECOLS = [
    "row_id", "is_posting_row", "eligible_PL_actual", "eligible_PL_variance", "eligible_BS_actual", "account_group",
    "entity_code", "gl_account", "period_year", "period_ym", "approval_status", "scale_factor_applied",
    "scale_confidence", "scale_decision", "dup_tier", "sign_flag", "statement", "flag_junk_entity",
    "flag_entity_unresolved", "flag_period_unparsed", "actual_usd_parsed", "actual_usd_adj", "budget_usd_adj",
    "forecast_usd_adj", "prior_year_usd_adj", "qty", "product_family", "headcount_fte",
]
NUM_COLS = ["actual_usd_parsed", "actual_usd_adj", "budget_usd_adj", "forecast_usd_adj", "prior_year_usd_adj",
            "qty", "headcount_fte", "scale_factor_applied"]
INT_COLS = ["is_posting_row", "eligible_PL_actual", "eligible_PL_variance", "eligible_BS_actual", "flag_junk_entity",
            "flag_entity_unresolved", "flag_period_unparsed", "period_year"]
SECTION = {"Revenue": "REVENUE", "COGS": "COGS", "People cost": "PEOPLE", "Operating expense": "OPEX",
           "Depreciation": "D&A", "Below EBITDA": "BELOW_EBITDA", "Tax": "TAX", "Working capital": "BALANCE_SHEET"}
COST = ["COGS", "PEOPLE", "OPEX"]


def load_frame(csv_path: Path) -> pd.DataFrame:
    # keep_default_na=False: text such as "NA" or "null" must not be turned into missing by accident
    df = pd.read_csv(csv_path, usecols=USECOLS, dtype=str, keep_default_na=False, na_values=[""], low_memory=False)
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="raise")
    for c in INT_COLS:
        df[c] = pd.to_numeric(df[c], errors="raise").astype("Int64")
    df["section"] = df["account_group"].map(SECTION)
    df["status_group"] = df["approval_status"].fillna("(blank)")
    return df


def sign_category(a: pd.Series, b: pd.Series) -> pd.Series:
    """Independent pandas implementation of the four sign categories (mirrors the documented rule, not the SQL macro).

    MISSING_OR_UNAVAILABLE: either amount missing | ZERO_INVOLVED: both present and at least one is exactly 0 |
    SAME_SIGN_NONZERO / OPPOSITE_SIGN_NONZERO: both non-zero, same / different sign.
    """
    a = pd.Series(a, dtype="float64")
    b = pd.Series(b, dtype="float64", index=a.index)
    out = np.where(a.isna() | b.isna(), "MISSING_OR_UNAVAILABLE",
                   np.where((a == 0) | (b == 0), "ZERO_INVOLVED",
                            np.where(np.sign(a) == np.sign(b), "SAME_SIGN_NONZERO", "OPPOSITE_SIGN_NONZERO")))
    return pd.Series(out, index=a.index, dtype="object")


def assert_unique_ids(rows: list[dict]) -> None:
    """Every cross-check must carry its own stable identifier (a truncated or shared id hides which check failed)."""
    ids = [r["check_id"] for r in rows]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"cross-check identifiers are not unique: {dup}")


def _sql1(con, query: str):
    return con.execute(query).fetchone()[0]


def run_crosscheck(csv_path: Path, con: duckdb.DuckDBPyConnection) -> list[dict]:
    df = load_frame(csv_path)
    res: list[dict] = []

    def add(cid: str, desc: str, py, sql, tol: float):
        py = float(py) if py is not None and not pd.isna(py) else float("nan")
        sql = float(sql) if sql is not None else float("nan")
        diff = sql - py
        ok = (np.isnan(py) and np.isnan(sql)) or (not np.isnan(diff) and abs(diff) <= tol)
        res.append({"check_id": cid, "description": desc, "pandas_value": py, "sql_value": sql,
                    "difference": diff, "tolerance": tol, "status": "PASS" if ok else "FAIL"})

    # ---- populations rebuilt from the documented rules -----------------------------------------------------------------
    pl = df[df.eligible_PL_actual == 1]
    anyst = df[(df.is_posting_row == 1) & (df.flag_junk_entity == 0) & (df.flag_entity_unresolved == 0) &
               (df.statement == "P&L") & (df.flag_period_unparsed == 0) & df.actual_usd_adj.notna()]
    posted_rule = anyst[anyst.status_group == "Posted"]
    add("X01", "Eligible P&L rows (flag) vs rows rebuilt from rules (posted + same gates)", len(posted_rule),
        _sql1(con, "SELECT count(*) FROM v_pl_actual"), 0)
    add("X02", "Eligible P&L row set equals the rebuilt set (rows in one only)", 0,
        len(set(pl.row_id) ^ set(posted_rule.row_id)), 0)
    add("X03", "Any-status P&L rows", len(anyst), _sql1(con, "SELECT rows_in_scope FROM out_i1_scenarios WHERE scenario='ALL_STATUSES'"), 0)

    # ---- A: totals by section ---------------------------------------------------------------------------------------
    for sec in ["REVENUE", "COGS", "PEOPLE", "OPEX", "D&A", "BELOW_EBITDA", "TAX"]:
        add(f"X10_{sec}", f"Actual total {sec} (eligible, adjusted)", pl.loc[pl.section == sec, "actual_usd_adj"].sum(),
            _sql1(con, f"SELECT sum(actual_usd) FROM out_a1_pl_period_section WHERE section='{sec}'"), 0.01)
    add("X11", "Entity x section: US01 revenue", pl[(pl.section == "REVENUE") & (pl.entity_code == "US01")].actual_usd_adj.sum(),
        _sql1(con, "SELECT actual_usd FROM out_a2_pl_entity_section WHERE section='REVENUE' AND entity_code='US01'"), 0.01)

    # ---- B: budget variance -----------------------------------------------------------------------------------------
    pv = pl[pl.budget_usd_adj.notna()]
    for sec in ["REVENUE", "COGS", "PEOPLE", "OPEX"]:
        s = pv[pv.section == sec]
        add(f"X20_{sec}", f"Net variance as reported {sec} (actual - budget)", (s.actual_usd_adj - s.budget_usd_adj).sum(),
            _sql1(con, f"SELECT net_variance_usd FROM out_b1_variance_section WHERE scenario='ALL_LINES' AND section='{sec}'"), 0.01)
        sa = s[sign_category(s.actual_usd_adj, s.budget_usd_adj) == "SAME_SIGN_NONZERO"]
        add(f"X21_{sec}", f"Net variance, same-sign rows only, {sec}", (sa.actual_usd_adj - sa.budget_usd_adj).sum(),
            _sql1(con, f"SELECT net_variance_usd FROM out_b1_variance_section WHERE scenario='SAME_SIGN_ONLY' AND section='{sec}'"), 0.01)
    r = pv[(pv.section == "REVENUE") & (sign_category(pv.actual_usd_adj, pv.budget_usd_adj) == "SAME_SIGN_NONZERO")]
    add("X22", "Revenue variance % (same-sign) = variance / |net budget|",
        (r.actual_usd_adj - r.budget_usd_adj).sum() / abs(r.budget_usd_adj.sum()),
        _sql1(con, "SELECT variance_pct_of_abs_budget FROM out_b1_variance_section WHERE scenario='SAME_SIGN_ONLY' AND section='REVENUE'"), 1e-9)
    add("X23", "Variance population rows (eligible with budget)", len(pv), _sql1(con, "SELECT count(*) FROM v_pl_budget"), 0)

    # ---- C: forecast ------------------------------------------------------------------------------------------------
    pf = pl[pl.forecast_usd_adj.notna()]
    rv = pf[pf.section == "REVENUE"]
    add("X30", "Revenue forecast WAPE (as reported)", (rv.forecast_usd_adj - rv.actual_usd_adj).abs().sum() / rv.actual_usd_adj.abs().sum(),
        _sql1(con, "SELECT wape FROM out_c1_forecast_section WHERE scenario='ALL_LINES' AND section='REVENUE'"), 1e-9)
    add("X31", "Revenue forecast bias (as reported)", (rv.forecast_usd_adj - rv.actual_usd_adj).sum() / rv.actual_usd_adj.abs().sum(),
        _sql1(con, "SELECT bias FROM out_c1_forecast_section WHERE scenario='ALL_LINES' AND section='REVENUE'"), 1e-9)
    ox = pf[(pf.section == "OPEX") & (sign_category(pf.actual_usd_adj, pf.forecast_usd_adj) == "SAME_SIGN_NONZERO")]
    add("X32", "OPEX forecast WAPE (same-sign)", (ox.forecast_usd_adj - ox.actual_usd_adj).abs().sum() / ox.actual_usd_adj.abs().sum(),
        _sql1(con, "SELECT wape FROM out_c1_forecast_section WHERE scenario='SAME_SIGN_ONLY' AND section='OPEX'"), 1e-9)

    # ---- D: prior year ----------------------------------------------------------------------------------------------
    pp = pl[pl.prior_year_usd_adj.notna() & (pl.section == "REVENUE")]
    add("X40", "Revenue change vs prior-year column (as reported)", (pp.actual_usd_adj - pp.prior_year_usd_adj).sum(),
        _sql1(con, "SELECT sum(change_usd) FROM out_d1_vs_py_column WHERE scenario='ALL_LINES' AND section='REVENUE'"), 0.01)
    rev_p = pl[pl.section == "REVENUE"].groupby("period_year").actual_usd_adj.sum()
    rev_a = anyst[anyst.section == "REVENUE"].assign(a=lambda d: d.actual_usd_adj.abs()).groupby("period_year").a.sum()
    for y in (2024, 2025):
        add(f"X41_{y}", f"Revenue true YoY {y} (posted, signed)", rev_p[y] / rev_p[y - 1] - 1,
            _sql1(con, f"SELECT yoy_growth FROM out_d3_true_yoy WHERE basis='POSTED_SIGNED' AND section='REVENUE' AND period_year={y}"), 1e-9)
        add(f"X42_{y}", f"Revenue true YoY {y} (any status, absolute)", rev_a[y] / rev_a[y - 1] - 1,
            _sql1(con, f"SELECT yoy_growth FROM out_d3_true_yoy WHERE basis='ANY_STATUS_ABS' AND section='REVENUE' AND period_year={y}"), 1e-9)

    # ---- E: gross profit ----------------------------------------------------------------------------------------------
    rev = pl[pl.section == "REVENUE"]
    cogs = pl[pl.section == "COGS"]
    add("X50", "Gross profit S1 (signed as recorded), all years", rev.actual_usd_adj.sum() - cogs.actual_usd_adj.sum(),
        _sql1(con, "SELECT gross_profit_usd FROM out_e1_gross_profit WHERE rowset='ROWS_ALL' AND treatment='GP_S1_SIGNED_AS_RECORDED' AND period='ALL YEARS'"), 0.01)
    add("X51", "Gross profit S2 (discount at absolute value), all years",
        rev.loc[rev.gl_account != "4190", "actual_usd_adj"].sum() - rev.loc[rev.gl_account == "4190", "actual_usd_adj"].abs().sum() - cogs.actual_usd_adj.sum(),
        _sql1(con, "SELECT gross_profit_usd FROM out_e1_gross_profit WHERE rowset='ROWS_ALL' AND treatment='GP_S2_DISCOUNT_ABS' AND period='ALL YEARS'"), 0.01)
    sc = pl[pl.sign_flag == "ALL_NON_NEGATIVE"]
    add("X52", "Gross profit S3, rows with sign_flag ALL_NON_NEGATIVE only (not a sign-consistent population)",
        sc[(sc.section == "REVENUE") & (sc.gl_account != "4190")].actual_usd_adj.sum() - sc[sc.section == "COGS"].actual_usd_adj.sum(),
        _sql1(con, "SELECT gross_profit_usd FROM out_e1_gross_profit WHERE rowset='ROWS_ALL_NON_NEGATIVE' AND treatment='GP_S3_EXCL_DISCOUNT' AND period='ALL YEARS'"), 0.01)

    # ---- F: cost ------------------------------------------------------------------------------------------------------
    cb = pl[pl.section.isin(["COGS", "PEOPLE", "OPEX", "D&A"])]
    add("X60", "Cost base absolute total", cb.actual_usd_adj.abs().sum(), _sql1(con, "SELECT sum(actual_abs_usd) FROM out_f1_cost_by_gl"), 0.01)
    top = cb.groupby("gl_account").actual_usd_adj.apply(lambda s: s.abs().sum()).sort_values(ascending=False)
    add("X61", "Largest cost GL share of the cost base", top.iloc[0] / top.sum(), _sql1(con, "SELECT max(share_of_cost_abs) FROM out_f1_cost_by_gl"), 1e-9)
    sal = pl[(pl.gl_account == "6100") & (pl.headcount_fte > 0) & (pl.entity_code == "IN01") & (pl.period_year == 2024)]
    add("X62", "Salary per FTE median, IN01 2024", (sal.actual_usd_adj.abs() / sal.headcount_fte).median(),
        _sql1(con, "SELECT median_per_fte_usd FROM out_f6_salary_per_fte WHERE entity_code='IN01' AND period_year=2024"), 1e-6)

    # ---- H: balance sheet -------------------------------------------------------------------------------------------
    bs = df[df.eligible_BS_actual == 1]
    add("X70", "Balance Sheet eligible lines", len(bs), _sql1(con, "SELECT sum(lines) FROM out_h2_bs_by_account"), 0)
    add("X71", "Balance Sheet signed line total (not a balance)", bs.actual_usd_adj.sum(),
        _sql1(con, "SELECT sum(signed_sum_of_lines_usd_not_a_balance) FROM out_h2_bs_by_account"), 0.01)

    # ---- I: every exposure scenario ----------------------------------------------------------------------------------
    def metrics(frame: pd.DataFrame, col: str = "actual_usd_adj"):
        r_ = frame.loc[frame.section == "REVENUE", col].sum()
        c_ = frame.loc[frame.section.isin(COST), col].sum()
        return r_, c_, r_ - c_, len(frame)

    restored = anyst.scale_factor_applied.isin([1000, 100000])
    posted = anyst[anyst.status_group == "Posted"]
    prest = posted.scale_factor_applied.isin([1000, 100000])
    tier_copy = ["DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN", "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT", "CANDIDATE_COPY_PARTIAL_AGREEMENT"]
    high_only = posted.assign(v=np.where(prest & (posted.scale_confidence != "HIGH"), posted.actual_usd_parsed, posted.actual_usd_adj))
    scen = {
        "POSTED_ONLY (baseline)": metrics(posted),
        "PENDING_ONLY": metrics(anyst[anyst.status_group == "Pending"]),
        "PARKED_ONLY": metrics(anyst[anyst.status_group == "Parked"]),
        "REJECTED_ONLY": metrics(anyst[anyst.status_group == "Rejected"]),
        "BLANK_ONLY": metrics(anyst[anyst.status_group == "(blank)"]),
        "ALL_EXCEPT_REJECTED": metrics(anyst[anyst.status_group != "Rejected"]),
        "ALL_STATUSES": metrics(anyst),
        "AS_REPORTED_PARSED (no restoration)": metrics(posted, "actual_usd_parsed"),
        "RESTORE_HIGH_CONFIDENCE_ONLY": metrics(high_only, "v"),
        "EXCLUDE_ALL_RESTORED_ROWS": metrics(posted[~prest]),
        "EXCLUDE_MEDIUM_CONFIDENCE_RESTORED": metrics(posted[~(prest & (posted.scale_confidence != "HIGH"))]),
        "EXCLUDE_SAME_SIGN_CANDIDATES": metrics(posted[posted.dup_tier != "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN"]),
        "EXCLUDE_ALL_COPY_CANDIDATES": metrics(posted[~posted.dup_tier.isin(tier_copy)]),
        "ALL_NON_NEGATIVE_ROWS_ONLY": metrics(posted[posted.sign_flag == "ALL_NON_NEGATIVE"]),
        "EXCLUDE_SINGLE_COLUMN_SIGN_FLIPS": metrics(posted[posted.sign_flag != "SINGLE_COLUMN_SIGN_FLIP"]),
    }
    for i, (name, (r_, c_, res_, n_)) in enumerate(scen.items(), 1):
        row = con.execute(
            "SELECT revenue_usd, cost_usd, result_proxy_usd, rows_in_scope FROM out_i1_scenarios WHERE scenario = ? "
            "ORDER BY factor LIMIT 1", [name]).fetchone()
        add(f"X8{i:02d}_rev", f"Scenario revenue: {name}", r_, row[0], 0.01)
        add(f"X8{i:02d}_cost", f"Scenario cost: {name}", c_, row[1], 0.01)
        add(f"X8{i:02d}_res", f"Scenario result proxy: {name}", res_, row[2], 0.01)
        add(f"X8{i:02d}_n", f"Scenario rows: {name}", n_, row[3], 0)
    # duplicate and restored exposure counts inside the eligible population
    for k, tier in enumerate(["UNIQUE_DOCUMENT_NO", "GROUP_ANCHOR", "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN", "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT"], 1):
        add(f"X90_{k:02d}", f"Eligible rows in duplicate tier {tier}", (pl.dup_tier == tier).sum(),
            _sql1(con, f"SELECT coalesce(sum(rows_eligible),0) FROM out_i6_duplicate_exposure WHERE dup_tier='{tier}'"), 0)
    for conf in ["HIGH", "MEDIUM"]:
        add(f"X91_{conf}", f"Eligible restored rows, {conf} confidence",
            ((pl.scale_factor_applied.isin([1000, 100000])) & (pl.scale_confidence == conf)).sum(),
            _sql1(con, f"SELECT coalesce(sum(rows_n),0) FROM out_i5_restored_exposure WHERE scale_confidence='{conf}'"), 0)

    # ---- I10: leave-one-entity-out price identity, HIGH-confidence 1/1000 restorations -------------------------------
    pb = anyst[anyst.gl_account.isin(["4100", "5100"]) & anyst.product_family.notna() & anyst.qty.notna() & (anyst.qty != 0) &
               anyst.scale_decision.isin(["UNDIVIDED", "DIVIDED_1E3", "DIVIDED_1E5"])].copy()
    pb["u"] = pb.actual_usd_adj.abs() / pb.qty.abs()
    ref_rows = pb[(pb.scale_decision == "UNDIVIDED") & (pb.scale_confidence == "HIGH")]
    t = pb[(pb.scale_decision == "DIVIDED_1E3") & (pb.scale_confidence == "HIGH")]
    hit = 0
    cache: dict = {}
    for fam, ent, u in zip(t.product_family, t.entity_code, t.u):
        key = (fam, ent)
        if key not in cache:
            cache[key] = ref_rows[(ref_rows.product_family == fam) & (ref_rows.entity_code != ent)].u.median()
        hit += int(abs(u / cache[key] - 1) <= 0.05)
    add("X95", "Price-identity LOO test: HIGH 1/1000 restorations within 5% of other-entity price (rows)", hit,
        _sql1(con, "SELECT rows_within_5pct_of_reference FROM out_i10_price_identity_independence WHERE scale_decision='DIVIDED_1E3' AND scale_confidence='HIGH'"), 0)
    # ---- sign categories: counts rebuilt with the independent pandas rule ------------------------------------------------
    for tag, frame, col, view, vcol in [("AB", pv, "budget_usd_adj", "v_pl_budget", "sign_cat_ab"),
                                        ("AF", pf, "forecast_usd_adj", "v_pl_forecast", "sign_cat_af"),
                                        ("AP", pl[pl.prior_year_usd_adj.notna()], "prior_year_usd_adj", "v_pl_prior", "sign_cat_ap")]:
        cats = sign_category(frame.actual_usd_adj, frame[col])
        for cat in ["SAME_SIGN_NONZERO", "OPPOSITE_SIGN_NONZERO", "ZERO_INVOLVED", "MISSING_OR_UNAVAILABLE"]:
            add(f"X96_{tag}_{cat[:4]}", f"Sign category {cat}: lines, actual vs {col.split('_')[0]}", (cats == cat).sum(),
                _sql1(con, f"SELECT count(*) FROM {view} WHERE {vcol} = '{cat}'"), 0)
    # opposite-sign lines' share of the absolute forecast error (the INS-02 headline), per section
    pfa = pf.assign(cat=sign_category(pf.actual_usd_adj, pf.forecast_usd_adj), err=(pf.forecast_usd_adj - pf.actual_usd_adj).abs())
    for sec in ["REVENUE", "COGS", "PEOPLE", "OPEX"]:
        g = pfa[pfa.section == sec]
        add(f"X97_{sec}", f"Share of absolute forecast error from OPPOSITE_SIGN_NONZERO lines, {sec}",
            g.loc[g.cat == "OPPOSITE_SIGN_NONZERO", "err"].sum() / g.err.sum(),
            _sql1(con, f"SELECT share_of_abs_error FROM out_c2_error_attribution WHERE section='{sec}' AND sign_category='OPPOSITE_SIGN_NONZERO'"), 1e-9)
    # status factor range across comparable policy scenarios only (single-status diagnostics excluded)
    pol = [scen["POSTED_ONLY (baseline)"], scen["ALL_EXCEPT_REJECTED"], scen["ALL_STATUSES"]]
    rev_pol = [m_[0] for m_ in pol]
    add("X98_REV", "Status factor: revenue range across baseline + policy scenarios as % of baseline",
        (max(rev_pol) - min(rev_pol)) / abs(rev_pol[0]),
        _sql1(con, "SELECT revenue_range_pct_of_baseline FROM out_i2_factor_ranking WHERE factor='status'"), 1e-9)
    # contribution sensitivity (b9) and budget-percentage sensitivity (b11) recounted from the line data
    cell = pv.assign(v=pv.actual_usd_adj - pv.budget_usd_adj, ab=pv.budget_usd_adj.abs()).groupby(["entity_code", "gl_account"]).agg(v=("v", "sum"), gross_b=("ab", "sum"))
    share = cell.v.abs() / cell.v.abs().sum()
    add("X99_B9", "Cells contributing >= 1% of total absolute cell variance (ALL_LINES)", (share >= 0.01).sum(),
        _sql1(con, "SELECT cells_at_or_above FROM out_b9_contribution_sensitivity WHERE scenario='ALL_LINES' AND threshold_share_of_total_abs_variance=0.01"), 0)
    pct = cell.v.abs() / cell.gross_b.where(cell.gross_b != 0)
    add("X99_B11", "Cells with |variance| >= 2% of the cell's gross budget (ALL_LINES)", (pct >= 0.02).sum(),
        _sql1(con, "SELECT cells_at_or_above FROM out_b11_budget_pct_sensitivity WHERE scenario='ALL_LINES' AND threshold_pct_of_gross_budget=0.02"), 0)

    assert_unique_ids(res)
    add("X00", "Cross-check identifiers are unique (distinct ids = number of checks before this one)", len(res), len({r["check_id"] for r in res}), 0)
    assert_unique_ids(res)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    a = ap.parse_args(argv)
    con = duckdb.connect(str(a.db), read_only=True)
    res = run_crosscheck(a.csv, con)
    bad = [r for r in res if r["status"] != "PASS"]
    for r in bad:
        print("FAIL", r)
    print(f"{len(res) - len(bad)} of {len(res)} cross-checks agree")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
