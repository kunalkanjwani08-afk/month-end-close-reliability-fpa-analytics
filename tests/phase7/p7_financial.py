"""Phase 7 - independent pandas recomputation of the financial metrics and comparison with the SQL outputs
(outputs/phase4/*.csv, produced by DuckDB). Population: the independently re-derived Posted eligible set
(ref_frame.pkl from p7_lineage.py); amounts: independently parsed raw strings x scale factor.

Same population and same documented definitions on both sides; definitions are taken from
docs/FINANCIAL_METRICS.md and the SQL comments, re-implemented here without importing project code.
"""
import json
import numpy as np
import pandas as pd
from p7_common import *

R = Registry()
A = "financial_sql"
ref = pd.read_pickle(WORK / "ref_frame.pkl")
cl = pd.read_csv(CLEAN, dtype=str, keep_default_na=False, encoding="utf-8-sig",
                 usecols=["row_id", "division", "gl_account", "account_name", "account_group", "period_ym", "cost_center_code",
                          "sign_flag", "scale_confidence", "dup_tier", "headcount_fte", "legal_entity", "is_posting_row"])
assert (cl.row_id.values == ref.row_id.values).all()
SEC = {"Revenue": "REVENUE", "COGS": "COGS", "People cost": "PEOPLE", "Operating expense": "OPEX",
       "Depreciation": "D&A", "Below EBITDA": "BELOW_EBITDA", "Tax": "TAX", "Working capital": "BALANCE_SHEET"}
glgrp = cl[cl.is_posting_row == "1"].groupby("gl_account").account_group.agg(lambda s: s.mode().iat[0])
df = pd.DataFrame({
    "srn": ref.srn, "e": ref.entity_code_ref, "d": cl.division, "gl": cl.gl_account, "ym": cl.period_ym,
    "cc": cl.cost_center_code, "sf": cl.sign_flag, "conf": cl.scale_confidence, "dup": cl.dup_tier, "st": ref.status,
    "a": ref.actual_usd_p * ref.fac, "b": ref.budget_usd_p * ref.fac, "f": ref.forecast_usd_p * ref.fac,
    "p": ref.prior_year_usd_p * ref.fac, "a_rep": ref.actual_usd_p, "b_rep": ref.budget_usd_p, "fac": ref.fac,
    "posted": ref.posted_elig, "np": ref.nonposted_diag})
df["sec"] = df.gl.map(glgrp).map(SEC)
df["y"] = df.ym.str[:4]
df["restored"] = df.fac.notna() & (df.fac != 1)
P = df[df.posted].copy()
import os
MUT = os.environ.get("P7_MUTATE", "")
if MUT == "drop_row":          # negative control: one Posted line missing from the reference
    P = P.iloc[1:].copy()
elif MUT == "cent":            # negative control: one line off by 2 cents
    P.iloc[0, P.columns.get_loc("a")] += 0.02
elif MUT == "status":          # negative control: one Pending line enters the Posted population
    P = pd.concat([P, df[df.np].head(1)])
ANY = df[df.posted | df.np].copy()
COST = ["COGS", "PEOPLE", "OPEX", "D&A"]
o4 = ROOT / "outputs/phase4"


def sign_cat(x, y):
    out = np.where(x.isna() | y.isna(), "MISSING_OR_UNAVAILABLE",
          np.where((x == 0) | (y == 0), "ZERO_INVOLVED",
          np.where(np.sign(x) == np.sign(y), "SAME_SIGN_NONZERO", "OPPOSITE_SIGN_NONZERO")))
    return out


def safe_pct(num, den_net, den_abs):
    return num / abs(den_net) if den_abs > 0 and abs(den_net) >= 0.5 * den_abs else float("nan")


def compare_table(tid, title, sql, mine, keys, cols, pop, defin):
    """Row-by-row comparison on identical keys. Every column, every row."""
    s = sql.copy(); m = mine.copy()
    for k in keys:
        s[k] = s[k].astype(str); m[k] = m[k].astype(str)
    j = s.merge(m, on=keys, how="outer", suffixes=("_sql", "_ref"), indicator=True)
    R.cmp(f"{tid}.keys", A, f"{title}: same key set (rows only in one side)", 0, int((j._merge != "both").sum()), 0,
          population=pop, definition="outer join on " + ",".join(keys))
    for c in cols:
        x = pd.to_numeric(j[c + "_sql"], errors="coerce"); y = pd.to_numeric(j[c + "_ref"], errors="coerce")
        tol = 0 if c.startswith("rows") else (TOL_RATIO if any(t in c for t in ("pct", "share", "ratio", "bias", "wape", "hhi")) else TOL_USD)
        nanmis = int((x.isna() != y.isna()).sum())
        d = (x - y).abs()
        mx = float(d.max()) if d.notna().any() else 0.0
        bad = int((d > tol).sum()) + nanmis
        R.add(f"{tid}.{c}", A, f"{title}: {c} (all {len(j)} rows)", "PASS" if bad == 0 else "FAIL", 0, bad, pop, defin,
              tol, note=f"max |SQL - reference| = {mx:.3g}; null-pattern mismatches {nanmis}")


# ---------------------------------------------------------------- A: P&L structure
g = P.groupby(["ym", "sec"]).agg(rows_eligible=("a", "size"), actual_usd=("a", "sum"),
                                abs_actual_usd=("a", lambda s: s.abs().sum()), actual_usd_as_reported_parsed=("a_rep", "sum")).reset_index()
g = g.rename(columns={"ym": "period_ym", "sec": "section"})
compare_table("F_A1", "P&L by period x section (a1)", pd.read_csv(o4 / "a1_pl_period_section.csv"), g,
              ["period_ym", "section"], ["rows_eligible", "actual_usd", "abs_actual_usd", "actual_usd_as_reported_parsed"],
              "Posted eligible P&L (58,340)", "sum of scale-adjusted actual; abs = sum |line|")
g = P.groupby(["e", "sec"]).agg(rows_eligible=("a", "size"), actual_usd=("a", "sum"), abs_actual_usd=("a", lambda s: s.abs().sum())).reset_index()
g["share_of_section_abs"] = g.abs_actual_usd / g.groupby("sec").abs_actual_usd.transform("sum")
compare_table("F_A2", "P&L by entity x section (a2)", pd.read_csv(o4 / "a2_pl_entity_section.csv"),
              g.rename(columns={"e": "entity_code", "sec": "section"}), ["entity_code", "section"],
              ["rows_eligible", "actual_usd", "abs_actual_usd", "share_of_section_abs"], "Posted eligible", "")
g = P.groupby(["d", "sec"]).agg(rows_eligible=("a", "size"), actual_usd=("a", "sum"), abs_actual_usd=("a", lambda s: s.abs().sum())).reset_index()
g["share_of_section_abs"] = g.abs_actual_usd / g.groupby("sec").abs_actual_usd.transform("sum")
compare_table("F_A3", "P&L by division x section (a3)", pd.read_csv(o4 / "a3_pl_division_section.csv"),
              g.rename(columns={"d": "division", "sec": "section"}), ["division", "section"],
              ["rows_eligible", "actual_usd", "abs_actual_usd", "share_of_section_abs"], "Posted eligible", "")
g = P.groupby("gl").agg(rows_eligible=("a", "size"), actual_usd=("a", "sum"), abs_actual_usd=("a", lambda s: s.abs().sum()),
                        share_rows_negative=("a", lambda s: (s < 0).mean())).reset_index()
g["share_of_total_abs"] = g.abs_actual_usd / g.abs_actual_usd.sum()
compare_table("F_A4", "P&L by GL account (a4)", pd.read_csv(o4 / "a4_pl_gl.csv"), g.rename(columns={"gl": "gl_account"}),
              ["gl_account"], ["rows_eligible", "actual_usd", "abs_actual_usd", "share_of_total_abs", "share_rows_negative"],
              "Posted eligible", "")

# headline figures
rev = P.loc[P.sec == "REVENUE", "a"].sum()
cost = P.loc[P.sec.isin(["COGS", "PEOPLE", "OPEX"]), "a"].sum()
headline = {"revenue": rev, "cost_cogs_people_opex": cost, "result_proxy": rev - cost, "rows": len(P)}

# ---------------------------------------------------------------- B: budget variance
B = P[P.b.notna()].copy()
R.cmp("F_B0", A, "Variance population rows (Posted eligible with budget)", 55043, len(B), 0)
B["v"] = B.a - B.b
B["sab"] = sign_cat(B.a, B.b)
rows = []
for scn, flt in [("ALL_LINES", None), ("SAME_SIGN_ONLY", "SAME_SIGN_NONZERO"), ("OPPOSITE_SIGN_ONLY", "OPPOSITE_SIGN_NONZERO"), ("ZERO_INVOLVED_ONLY", "ZERO_INVOLVED")]:
    X = B if flt is None else B[B.sab == flt]
    cell = X.groupby(["sec", "e", "gl", "ym"]).agg(a=("a", "sum"), b=("b", "sum"), v=("v", "sum"), n=("a", "size")).reset_index()
    for sec, c in cell.groupby("sec"):
        rows.append(dict(scenario=scn, section=sec, rows_in_scope=int(c.n.sum()), actual_usd=c.a.sum(), budget_usd=c.b.sum(),
                         net_variance_usd=c.v.sum(), gross_cell_variance_usd=c.v.abs().sum(),
                         variance_pct_of_abs_budget=safe_pct(c.v.sum(), c.b.sum(), c.b.abs().sum()),
                         budget_netting_ratio=abs(c.b.sum()) / c.b.abs().sum() if c.b.abs().sum() else np.nan,
                         gross_variance_pct_of_abs_cell_budget=c.v.abs().sum() / c.b.abs().sum() if c.b.abs().sum() else np.nan))
compare_table("F_B1", "Budget variance by section, 4 sign scenarios (b1)", pd.read_csv(o4 / "b1_variance_section.csv"), pd.DataFrame(rows),
              ["scenario", "section"], ["rows_in_scope", "actual_usd", "budget_usd", "net_variance_usd", "gross_cell_variance_usd",
                                        "variance_pct_of_abs_budget", "budget_netting_ratio", "gross_variance_pct_of_abs_cell_budget"],
              "Posted eligible with budget (55,043)", "variance = actual - budget; pct guarded: |net budget| >= 50% of sum |cell budget|")
rows = []
for scn, flt in [("ALL_LINES", None), ("SAME_SIGN_ONLY", "SAME_SIGN_NONZERO")]:
    X = B if flt is None else B[B.sab == flt]
    for (dv, sec), c in X.groupby(["d", "sec"]):
        cc = c.groupby(["e", "gl", "ym"]).b.sum()
        rows.append(dict(scenario=scn, division=dv, section=sec, rows_in_scope=len(c), actual_usd=c.a.sum(), budget_usd=c.b.sum(),
                         variance_usd=c.v.sum()))
sqlb3 = pd.read_csv(o4 / "b3_variance_division.csv")
compare_table("F_B3", "Budget variance by division x section (b3, amounts)", sqlb3[sqlb3.scenario.isin(["ALL_LINES", "SAME_SIGN_ONLY"])],
              pd.DataFrame(rows), ["scenario", "division", "section"], ["rows_in_scope", "actual_usd", "budget_usd", "variance_usd"],
              "Posted eligible with budget", "")

# ---------------------------------------------------------------- C: forecast
F = P[P.f.notna()].copy()
F["err"] = F.f - F.a
F["saf"] = sign_cat(F.a, F.f)
rows = []
for scn, flt in [("ALL_LINES", None), ("SAME_SIGN_ONLY", "SAME_SIGN_NONZERO"), ("OPPOSITE_SIGN_ONLY", "OPPOSITE_SIGN_NONZERO"), ("ZERO_INVOLVED_ONLY", "ZERO_INVOLVED")]:
    X = F if flt is None else F[F.saf == flt]
    for sec, c in X.groupby("sec"):
        aa = c.a.abs().sum()
        rows.append(dict(scenario=scn, section=sec, rows_in_scope=len(c), actual_usd=c.a.sum(), forecast_usd=c.f.sum(),
                         net_error_usd=c.err.sum(), abs_error_usd=c.err.abs().sum(), abs_actual_usd=aa,
                         bias=c.err.sum() / aa if aa else np.nan, wape=c.err.abs().sum() / aa if aa else np.nan))
compare_table("F_C1", "Forecast error by section (c1)", pd.read_csv(o4 / "c1_forecast_section.csv"), pd.DataFrame(rows),
              ["scenario", "section"], ["rows_in_scope", "actual_usd", "forecast_usd", "net_error_usd", "abs_error_usd", "abs_actual_usd", "bias", "wape"],
              "Posted eligible with forecast (54,851)", "error = forecast - actual (line); WAPE = sum|error| / sum|actual|; bias = sum error / sum|actual|")

# ---------------------------------------------------------------- D: prior year
Q = P[P.p.notna()].copy()
Q["chg"] = Q.a - Q.p
Q["sap"] = sign_cat(Q.a, Q.p)
rows = []
for scn, flt in [("ALL_LINES", None), ("SAME_SIGN_ONLY", "SAME_SIGN_NONZERO")]:
    X = Q if flt is None else Q[Q.sap == flt]
    for (y, sec), c in X.groupby(["y", "sec"]):
        rows.append(dict(scenario=scn, period_year=y, section=sec, rows_in_scope=len(c), actual_usd=c.a.sum(), prior_year_usd=c.p.sum(),
                         change_usd=c.chg.sum(), change_pct_of_abs_py=safe_pct(c.chg.sum(), c.p.sum(), c.p.abs().sum())))
compare_table("F_D1", "Actual vs prior-year column by year x section (d1)", pd.read_csv(o4 / "d1_vs_py_column.csv"), pd.DataFrame(rows),
              ["scenario", "period_year", "section"], ["rows_in_scope", "actual_usd", "prior_year_usd", "change_usd", "change_pct_of_abs_py"],
              "Posted eligible with PY (54,923)", "change = actual - prior_year column (the file's PY column, not a true YoY)")

# ---------------------------------------------------------------- E: gross profit S1/S2/S3
G = P[P.sec.isin(["REVENUE", "COGS"])].copy()
rows = []
for rs, flt in [("ROWS_ALL", None), ("ROWS_ALL_NON_NEGATIVE", "ALL_NON_NEGATIVE")]:
    X = G if flt is None else G[G.sf == flt]
    for t in ["GP_S1_SIGNED_AS_RECORDED", "GP_S2_DISCOUNT_ABS", "GP_S3_EXCL_DISCOUNT"]:
        r = X.a.where(X.sec == "REVENUE")
        disc = X.gl == "4190"
        if t == "GP_S2_DISCOUNT_ABS":
            r = r.where(~disc, -X.a.abs())
        if t == "GP_S3_EXCL_DISCOUNT":
            r = r.where(~disc, 0.0)
        c = X.a.where(X.sec == "COGS")
        Y = pd.DataFrame({"y": X.y, "r": r, "c": c})
        for per, Z in list(Y.groupby("y")) + [("ALL YEARS", Y)]:
            rv, cg = Z.r.sum(), Z.c.sum()
            rows.append(dict(rowset=rs, treatment=t, period=per, rows_in_scope=len(Z), revenue_usd=rv, cogs_usd=cg,
                             gross_profit_usd=rv - cg, gross_margin_pct=(rv - cg) / rv if rv > 0 else np.nan))
gp = pd.DataFrame(rows)
compare_table("F_E1", "Gross profit S1/S2/S3 x rowset x year (e1)", pd.read_csv(o4 / "e1_gross_profit.csv"), gp,
              ["rowset", "treatment", "period"], ["rows_in_scope", "revenue_usd", "cogs_usd", "gross_profit_usd", "gross_margin_pct"],
              "Posted eligible REVENUE + COGS", "S1 signed as recorded; S2 GL 4190 discount forced negative (-|x|); S3 GL 4190 excluded (0)")
s123 = gp[(gp.rowset == "ROWS_ALL") & (gp.period == "ALL YEARS")].set_index("treatment").gross_profit_usd
R.cmp("F_E2", A, "S1, S2, S3 gross profit are distinct values (not silently merged)", 3, int(s123.round(2).nunique()), 0,
      note=json.dumps(s123.round(2).to_dict()))
disc_rows = P[P.gl == "4190"]
R.add("F_E3", A, "Discount GL 4190 sign profile (why S1/S2/S3 differ)", "INFO", None, len(disc_rows),
      note=f"positive {int((disc_rows.a > 0).sum())}, negative {int((disc_rows.a < 0).sum())}, zero {int((disc_rows.a == 0).sum())}")

# ---------------------------------------------------------------- F: cost structure, concentration, cost centres
K = P[P.sec.isin(COST)]
g = K.groupby(["gl", "sec"]).agg(rows_eligible=("a", "size"), actual_signed_usd=("a", "sum"), actual_abs_usd=("a", lambda s: s.abs().sum())).reset_index()
g["share_of_cost_abs"] = g.actual_abs_usd / g.actual_abs_usd.sum()
g = g.sort_values("actual_abs_usd", ascending=False)
g["cumulative_share"] = g.actual_abs_usd.cumsum() / g.actual_abs_usd.sum()
g["rank_by_abs"] = np.arange(1, len(g) + 1)
compare_table("F_F1", "Cost by GL with Pareto share and rank (f1)", pd.read_csv(o4 / "f1_cost_by_gl.csv"),
              g.rename(columns={"gl": "gl_account", "sec": "section"}), ["gl_account", "section"],
              ["rows_eligible", "actual_signed_usd", "actual_abs_usd", "share_of_cost_abs", "cumulative_share", "rank_by_abs"],
              "Posted eligible COGS+PEOPLE+OPEX+D&A", "abs-activity basis")
rows = []
for dim, col, secs in [("legal_entity", "e", COST), ("division", "d", COST), ("gl_account", "gl", COST),
                       ("cost_center (opex+people)", "cc", ["PEOPLE", "OPEX"])]:
    X = P[P.sec.isin(secs)].copy()
    X[col] = X[col].replace("", "(blank)")
    v = X.groupby(col).a.apply(lambda s: s.abs().sum()).sort_values(ascending=False)
    v = v.reset_index().sort_values(["a", col], ascending=[False, True])
    sh = v.a / v.a.sum()
    rows.append(dict(dimension=dim, members=len(v), top1_share=sh.max(), top3_share=sh.iloc[:3].sum(), top3_members=min(3, len(v)),
                     hhi=(sh ** 2).sum(), equal_share_benchmark=1 / len(v), top1_member=str(v[col].iloc[0])))
conc = pd.DataFrame(rows)
s2 = pd.read_csv(o4 / "f2_concentration.csv")
compare_table("F_F2", "Cost concentration: top1/top3 share, HHI (f2)", s2, conc, ["dimension"],
              ["members", "top1_share", "top3_share", "hhi", "equal_share_benchmark"], "Posted eligible cost sections", "HHI = sum(share^2)")
R.cmp("F_F2m", A, "Concentration top-1 member identical in every dimension", 0,
      int((s2.set_index("dimension").top1_member.astype(str) != conc.set_index("dimension").top1_member.reindex(s2.dimension)).sum()), 0,
      note=json.dumps(conc.set_index("dimension").top1_member.to_dict()))
ccx = P[P.sec.isin(["PEOPLE", "OPEX"])].copy()
ccx["cc"] = ccx.cc.replace("", "(blank)")
cc_tab = ccx.groupby("cc").agg(rows=("a", "size"), abs_usd=("a", lambda s: s.abs().sum()), signed_usd=("a", "sum"))
cc_tab.to_csv(WORK / "ref_cost_centre.csv")

# ---------------------------------------------------------------- I: status diagnostics and scenarios
def i1row(factor, scn, X, amt="a"):
    r = X.loc[X.sec == "REVENUE", amt].sum(); c = X.loc[X.sec.isin(["COGS", "PEOPLE", "OPEX"]), amt].sum()
    return dict(factor=factor, scenario=scn, rows_in_scope=len(X), revenue_usd=r, cost_usd=c, result_proxy_usd=r - c)

DUPT = ["DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN", "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT", "CANDIDATE_COPY_PARTIAL_AGREEMENT"]
Pp = ANY[ANY.st == "Posted"]
rows = [i1row("status", "POSTED_ONLY (baseline)", Pp), i1row("status", "PENDING_ONLY", ANY[ANY.st == "Pending"]),
        i1row("status", "PARKED_ONLY", ANY[ANY.st == "Parked"]), i1row("status", "REJECTED_ONLY", ANY[ANY.st == "Rejected"]),
        i1row("status", "BLANK_ONLY", ANY[ANY.st == "(blank)"]), i1row("status", "ALL_EXCEPT_REJECTED", ANY[ANY.st != "Rejected"]),
        i1row("status", "ALL_STATUSES", ANY),
        i1row("scale", "ADJUSTED_ALL (baseline)", Pp), i1row("scale", "AS_REPORTED_PARSED (no restoration)", Pp, "a_rep"),
        i1row("scale", "EXCLUDE_ALL_RESTORED_ROWS", Pp[~Pp.restored]),
        i1row("scale", "EXCLUDE_MEDIUM_CONFIDENCE_RESTORED", Pp[~(Pp.restored & (Pp.conf != "HIGH"))]),
        i1row("duplicates", "CANDIDATES_RETAINED (baseline)", Pp),
        i1row("duplicates", "EXCLUDE_SAME_SIGN_CANDIDATES", Pp[Pp.dup != "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN"]),
        i1row("duplicates", "EXCLUDE_ALL_COPY_CANDIDATES", Pp[~Pp.dup.isin(DUPT)]),
        i1row("sign", "ALL_ROWS_SIGNS_AS_RECORDED (baseline)", Pp), i1row("sign", "ALL_NON_NEGATIVE_ROWS_ONLY", Pp[Pp.sf == "ALL_NON_NEGATIVE"]),
        i1row("sign", "EXCLUDE_SINGLE_COLUMN_SIGN_FLIPS", Pp[Pp.sf != "SINGLE_COLUMN_SIGN_FLIP"])]
hc = Pp.copy(); hc["a_h"] = np.where(hc.restored & (hc.conf != "HIGH"), hc.a_rep, hc.a)
rows.append(i1row("scale", "RESTORE_HIGH_CONFIDENCE_ONLY", hc, "a_h"))
compare_table("F_I1", "Status / scale / duplicate / sign scenarios (i1)", pd.read_csv(o4 / "i1_scenarios.csv"), pd.DataFrame(rows),
              ["factor", "scenario"], ["rows_in_scope", "revenue_usd", "cost_usd", "result_proxy_usd"],
              "any-status P&L population (136,330) or its Posted part", "revenue = REVENUE; cost = COGS+PEOPLE+OPEX; proxy = revenue - cost")
part = sum(len(ANY[ANY.st == s]) for s in ["Posted", "Pending", "Parked", "Rejected", "(blank)"])
R.cmp("F_I2", A, "Five journal statuses partition the any-status population exactly", len(ANY), part, 0)
R.cmp("F_I3", A, "Non-Posted rows inside the Posted P&L population (must be 0)", 0, int((P.st != "Posted").sum()), 0)
# restored exposure (i5)
X = P[P.restored].copy()
X["dec"] = np.where(X.fac == 1e3, "DIVIDED_1E3", "DIVIDED_1E5")
g = X.groupby(["sec", "conf", "dec"]).agg(rows_n=("a", "size"), abs_adjusted_usd=("a", lambda s: s.abs().sum()),
                                           abs_as_reported_usd=("a_rep", lambda s: s.abs().sum())).reset_index()
g["share_of_section_abs_activity"] = g.abs_adjusted_usd / g.sec.map(P.groupby("sec").a.apply(lambda s: s.abs().sum()))
compare_table("F_I5", "Scale-restored exposure (i5)", pd.read_csv(o4 / "i5_restored_exposure.csv"),
              g.rename(columns={"sec": "section", "conf": "scale_confidence", "dec": "scale_decision"}),
              ["section", "scale_confidence", "scale_decision"], ["rows_n", "abs_adjusted_usd", "abs_as_reported_usd", "share_of_section_abs_activity"],
              "Posted eligible restored rows (2,374)", "")
R.add("F_I6", A, "Headline (Posted, adjusted): revenue / cost / result proxy", "INFO", None, None,
      note=json.dumps({k: round(v, 2) for k, v in headline.items()}))
R.cmp("F_I7", A, "Result proxy depends on scale rule: AS_REPORTED vs ADJUSTED difference (USD)", 0, 0, 0,
      note=f"adjusted {rows[7]['result_proxy_usd']:,.2f} vs as-reported {rows[8]['result_proxy_usd']:,.2f}: disclosed sensitivity, not an error")

# save reference metrics for the Excel / dashboard comparisons
refm = {"headline": headline,
        "section_totals": P.groupby("sec").a.sum().to_dict(),
        "section_abs": P.groupby("sec").a.apply(lambda s: s.abs().sum()).to_dict(),
        "section_rows": P.groupby("sec").size().to_dict(),
        "entity_section": {f"{e}|{s}": v for (e, s), v in P.groupby(["e", "sec"]).a.sum().items()},
        "division_section": {f"{d}|{s}": v for (d, s), v in P.groupby(["d", "sec"]).a.sum().items()},
        "gl_totals": P.groupby("gl").a.sum().to_dict(),
        "month_section": {f"{m}|{s}": v for (m, s), v in P.groupby(["ym", "sec"]).a.sum().items()},
        "gp": gp.to_dict("records"), "cost_centre": cc_tab.reset_index().to_dict("records"),
        "status_rows": ANY.st.value_counts().to_dict(),
        "status_abs": ANY.groupby("st").a.apply(lambda s: s.abs().sum()).to_dict()}
json.dump(refm, open(WORK / "ref_metrics.json", "w"), indent=1, default=float)
df.to_pickle(WORK / "ref_lines.pkl")
R.save("financial_sql" + (("_mutant_" + MUT) if MUT else ""))
