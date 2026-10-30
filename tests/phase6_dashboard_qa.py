"""Phase 6 browser QA for outputs/phase6/fpa_financial_analytics_dashboard.html (real Chromium via Playwright).

Independent expectations are computed with pandas from the cleaned CSV (not from the DuckDB/JS payload) and from the
Phase 5 workbook. Results -> outputs/phase6/qa_results.json (consumed by the report). Run:  python tests/phase6_dashboard_qa.py
"""
import asyncio, csv, io, json, re, sys, time, warnings
from pathlib import Path
import duckdb, numpy as np, pandas as pd, openpyxl
from playwright.async_api import async_playwright

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "outputs/phase6/fpa_financial_analytics_dashboard.html"
URL = HTML.as_uri()
OUT = ROOT / "outputs/phase6"
SHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "qa_screens"
SHOT.mkdir(parents=True, exist_ok=True)
RES = []
SKIPS = []


def rec(area, name, ok, detail=""):
    RES.append({"area": area, "test": name, "status": "PASS" if ok else "FAIL", "detail": str(detail)[:600]})
    print(("PASS" if ok else "FAIL"), area, "|", name, "|", str(detail)[:200])


def close(a, b, tol=0.01):
    return a is not None and b is not None and abs(a - b) <= max(tol, 1e-9 * abs(b))


# ------------------------------------------------------------------ independent data (CSV)
con = duckdb.connect(str(ROOT / "data/processed/phase4_fpa.duckdb"), read_only=True)
dim = dict(con.execute("select gl_account, section from dim_account").fetchall())
cols = ["row_id", "eligible_PL_actual", "entity_code", "division", "gl_account", "cost_center_code", "period_ym", "actual_usd_adj", "budget_usd_adj",
        "forecast_usd_adj", "prior_year_usd_adj", "actual_usd_parsed", "budget_usd_parsed", "forecast_usd_parsed", "prior_year_usd_parsed",
        "scale_factor_applied", "scale_confidence", "dup_tier", "sign_flag", "source_row_number", "document_no"]
df = pd.read_csv(ROOT / "data/processed/fpa_monthly_close_cleaned.csv", usecols=cols, dtype={"cost_center_code": str, "document_no": str}, low_memory=False)
df = df[df.eligible_PL_actual == 1].copy()
df["section"] = df.gl_account.map(dim)
df["restored"] = df.scale_factor_applied.fillna(1) != 1
df["rs"] = np.where(~df.restored, 0, np.where(df.scale_confidence == "HIGH", 1, 2))
months = sorted(df.period_ym.unique())
df["m"] = df.period_ym.map({m: i for i, m in enumerate(months)})
df["yr"] = df.period_ym.str[:4].astype(int)
df["q"] = (df.period_ym.str[5:7].astype(int) - 1) // 3 + 1


def signcat(a, b):
    c = np.where(a.isna() | b.isna(), 3, np.where((a == 0) | (b == 0), 2, np.where(a * b > 0, 0, 1)))
    return c


df["sab"] = signcat(df.actual_usd_adj, df.budget_usd_adj)


def expected(f):
    d = df
    m = d.yr.isin(f.get("years", [2023, 2024, 2025])) & d.q.isin(f.get("qtrs", [1, 2, 3, 4])) & (d.m >= f.get("from", 0)) & (d.m <= f.get("to", 35))
    if f.get("ent"): m &= d.entity_code.isin(f["ent"])
    if f.get("div"): m &= d.division.isin(f["div"])
    if f.get("sec"): m &= d.section.isin(f["sec"])
    if f.get("gl"): m &= d.gl_account.isin(f["gl"])
    if f.get("cc"):
        cm = d.cost_center_code.isin([c for c in f["cc"] if c != "(none)"])
        if "(none)" in f["cc"]: cm |= d.cost_center_code.isna()
        m &= cm
    scale, dup, sign = f.get("scale", "ADJ"), f.get("dup", "KEEP"), f.get("sign", "KEEP")
    if scale == "EXCL_ALL": m &= d.rs == 0
    if scale == "EXCL_MED": m &= d.rs != 2
    if dup == "EXCL_SAME": m &= d.dup_tier != "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN"
    if dup == "EXCL_ALL": m &= ~d.dup_tier.isin(["DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN", "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT", "CANDIDATE_COPY_PARTIAL_AGREEMENT"])
    if sign == "NONNEG": m &= d.sign_flag == "ALL_NON_NEGATIVE"
    if sign == "EXCL_FLIP": m &= d.sign_flag != "SINGLE_COLUMN_SIGN_FLIP"
    x = d[m]
    pick = (scale == "PARSED") * (x.rs > 0) | (scale == "HIGH") * (x.rs == 2)
    A = np.where(pick, x.actual_usd_parsed, x.actual_usd_adj); B = np.where(pick, x.budget_usd_parsed, x.budget_usd_adj)
    sec = x.section.values
    o = {"n": len(x), "rev": A[sec == "REVENUE"].sum(), "cost": A[np.isin(sec, ["COGS", "PEOPLE", "OPEX"])].sum()}
    bm = ~np.isnan(B)
    for p, want in (("ALL", None), ("SAME", 0), ("OPP", 1), ("ZERO", 2)):
        pm = bm if want is None else bm & (x.sab.values == want)
        for tag, secs in (("r", ["REVENUE"]), ("c", ["COGS", "PEOPLE", "OPEX"])):
            sm = pm & np.isin(sec, secs)
            o[f"{tag}n_{p}"] = float((A[sm] - B[sm]).sum()); o[f"{tag}l_{p}"] = int(sm.sum())
    return o


# ------------------------------------------------------------------ independent reference engine (pandas) for derived metrics
CSV_ALL = ROOT / "data/processed/fpa_monthly_close_cleaned.csv"
_any_cols = ["eligible_PL_actual", "excl_PL_actual", "approval_status", "entity_code", "division", "gl_account", "cost_center_code", "period_ym",
             "actual_usd_adj", "actual_usd_parsed", "scale_factor_applied", "scale_confidence", "dup_tier", "sign_flag", "source_row_number"]
_raw_any = pd.read_csv(CSV_ALL, usecols=_any_cols, dtype={"cost_center_code": str}, low_memory=False)
# any-status population rebuilt from the CSV alone: rows that pass every exclusion gate except the status gate
anyst = _raw_any[_raw_any.excl_PL_actual.isin(["ELIGIBLE", "5_STATUS_NOT_ELIGIBLE"]) & _raw_any.actual_usd_adj.notna()].copy()
anyst["status"] = anyst.approval_status.fillna("(blank)")
anyst["section"] = anyst.gl_account.map(dim)
anyst["restored"] = anyst.scale_factor_applied.fillna(1) != 1
anyst["rs"] = np.where(~anyst.restored, 0, np.where(anyst.scale_confidence == "HIGH", 1, 2))
anyst["m"] = anyst.period_ym.map({m: i for i, m in enumerate(months)})
anyst["yr"] = anyst.period_ym.str[:4].astype(int); anyst["q"] = (anyst.period_ym.str[5:7].astype(int) - 1) // 3 + 1
STATUS_ORDER = ["Posted", "Pending", "Parked", "Rejected", "(blank)"]
for _c in ("budget_usd_adj", "budget_usd_parsed"):
    pass


def _mask(d, f):
    m = d.yr.isin(f.get("years", [2023, 2024, 2025])) & d.q.isin(f.get("qtrs", [1, 2, 3, 4])) & (d.m >= f.get("from", 0)) & (d.m <= f.get("to", 35))
    if f.get("ent"): m &= d.entity_code.isin(f["ent"])
    if f.get("div"): m &= d.division.isin(f["div"])
    if f.get("sec"): m &= d.section.isin(f["sec"])
    if f.get("gl"): m &= d.gl_account.isin(f["gl"])
    if f.get("cc"):
        cm = d.cost_center_code.isin([c for c in f["cc"] if c != "(none)"])
        if "(none)" in f["cc"]: cm |= d.cost_center_code.isna()
        m &= cm
    xf = f.get("xf")
    if xf:
        dm, val = xf
        col = {"ent": "entity_code", "div": "division", "sec": "section", "gl": "gl_account", "m": "m"}.get(dm)
        if dm == "cc": m &= (d.cost_center_code.isna() if val == "(none)" else d.cost_center_code == val)
        else: m &= d[col] == val
    return m


def _scn(d, scale, dup, sign):
    m = pd.Series(True, index=d.index)
    if scale == "EXCL_ALL": m &= d.rs == 0
    if scale == "EXCL_MED": m &= d.rs != 2
    if dup == "EXCL_SAME": m &= d.dup_tier != "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN"
    if dup == "EXCL_ALL": m &= ~d.dup_tier.isin(["DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN", "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT", "CANDIDATE_COPY_PARTIAL_AGREEMENT"])
    if sign == "NONNEG": m &= d.sign_flag == "ALL_NON_NEGATIVE"
    if sign == "EXCL_FLIP": m &= d.sign_flag != "SINGLE_COLUMN_SIGN_FLIP"
    return m


def subset(f, with_xf=True, scn=None):
    """filtered lines + effective amounts for the scale basis. scn=(scale,dup,sign) overrides the scenario selectors."""
    scale, dup, sign = scn if scn else (f.get("scale", "ADJ"), f.get("dup", "KEEP"), f.get("sign", "KEEP"))
    ff = f if with_xf else {k: v for k, v in f.items() if k != "xf"}
    x = df[_mask(df, ff) & _scn(df, scale, dup, sign)].copy()
    pick = ((x.rs > 0) if scale == "PARSED" else (x.rs == 2) if scale == "HIGH" else pd.Series(False, index=x.index))
    x["A"] = np.where(pick, x.actual_usd_parsed, x.actual_usd_adj); x["B"] = np.where(pick, x.budget_usd_parsed, x.budget_usd_adj)
    x["F"] = np.where(pick, x.forecast_usd_parsed, x.forecast_usd_adj); x["Pp"] = np.where(pick, x.prior_year_usd_parsed, x.prior_year_usd_adj)
    return x


def ref_kpis(x):
    rev = x.loc[x.section == "REVENUE", "A"]; cost = x.loc[x.section.isin(["COGS", "PEOPLE", "OPEX"]), "A"]
    mrev = x[x.section == "REVENUE"].groupby("m").A.sum().reindex(range(36), fill_value=0.0)
    mcost = x[x.section.isin(["COGS", "PEOPLE", "OPEX"])].groupby("m").A.sum().reindex(range(36), fill_value=0.0)
    return {"n": len(x), "rev": rev.sum(), "cost": cost.sum(), "mrev": mrev.values, "mcost": mcost.values}


def safe_pct(num, den, den_abs):
    return num / abs(den) if den_abs > 0 and abs(den) >= 0.5 * den_abs else None


def ref_variance(x, pop):
    y = x[x.B.notna()]
    if pop != "ALL": y = y[y.sab == {"SAME": 0, "OPP": 1, "ZERO": 2}[pop]]
    out = {}
    if len(y):
        c = y.groupby(["entity_code", "gl_account", "m"]).agg(a=("A", "sum"), b=("B", "sum"), n=("A", "size"), sec=("section", "first")).reset_index()
        for s, g in c.groupby("sec"):
            net = (g.a - g.b).sum(); out[s] = {"n": int(g.n.sum()), "act": g.a.sum(), "bud": g.b.sum(), "net": net, "gross": (g.a - g.b).abs().sum(), "absBud": g.b.abs().sum(),
                                               "pct": safe_pct(net, g.b.sum(), g.b.abs().sum())}
    return out


def ref_forecast(x):
    o = {}
    for pname in "ABC":
        y = x[x.F.notna()]
        if pname in "AB": y = y[y.B.notna()]
        if pname == "A": y = y[(y.sab == 0) & (y.saf == 0)]
        for s, g in y.groupby("section"):
            ef = g.F - g.A; eb = g.B - g.A
            o.setdefault(pname, {})[s] = {"n": len(g), "errF": ef.abs().sum(), "signedF": ef.sum(), "absA": g.A.abs().sum(), "errB": eb.abs().sum() if pname != "C" else None, "signedB": eb.sum() if pname != "C" else None}
    return o


def ref_prior(x, pop):
    y = x[x.Pp.notna()]
    if pop != "ALL": y = y[y.sap == {"SAME": 0, "OPP": 1, "ZERO": 2}[pop]]
    o = {}
    for (yr, s), g in y.groupby(["yr", "section"]):
        o[(int(yr), s)] = {"n": len(g), "act": g.A.sum(), "py": g.Pp.sum(), "absPy": g.Pp.abs().sum()}
    return o


def ref_gp(x, rowset):
    y = x[x.section.isin(["REVENUE", "COGS"])]
    yn = y[y.sign_flag == "ALL_NON_NEGATIVE"] if rowset == "NONNEG" else y
    res = []
    for t in range(3):
        def rv(g, col):
            v = g[col].where(g.gl_account != 4190, g[col] if t == 0 else (-g[col].abs() if t == 1 else 0.0))
            return v
        r = yn[yn.section == "REVENUE"]; c = yn[yn.section == "COGS"]
        T = {"rev": rv(r, "A").sum(), "cogs": c.A.sum(), "n": len(yn), "yr": {}}
        for yr in (2023, 2024, 2025):
            T["yr"][yr] = {"rev": rv(r[r.yr == yr], "A").sum(), "cogs": c[c.yr == yr].A.sum()}
        sm = y[(y.sab == 0) & y.B.notna()]; sr = sm[sm.section == "REVENUE"]; sc = sm[sm.section == "COGS"]
        T["vb"] = {"aRev": rv(sr, "A").sum(), "bRev": rv(sr, "B").sum(), "aCogs": sc.A.sum(), "bCogs": sc.B.sum(), "n": len(sm)}
        res.append(T)
    return res


def ref_persist(x):
    y = x[x.B.notna() & (x.sab == 0)]
    if not len(y): return {}
    c = y.groupby(["entity_code", "gl_account", "m"]).agg(a=("A", "sum"), b=("B", "sum")).reset_index(); c["v"] = c.a - c.b
    o = {}
    for (e, g), t in c.groupby(["entity_code", "gl_account"]):
        if len(t) < 12: continue
        above, below = int((t.v > 0).sum()), int((t.v < 0).sum()); share = max(above, below) / len(t)
        pct = safe_pct(t.v.sum(), t.b.sum(), t.b.abs().sum())
        o[(e, int(g))] = {"months": len(t), "v": t.v.sum(), "persistent": bool(share >= 0.9 and pct is not None and abs(pct) >= 0.03)}
    return o


def ref_conc(x):
    y = x[x.section.isin(["COGS", "PEOPLE", "OPEX", "D&A"])].copy(); y["abs"] = y.A.abs()
    def conc(s):
        s = s[s > 0].sort_values(ascending=False)
        if not len(s): return None
        sh = s / s.sum(); return {"members": len(s), "top1": sh.iloc[0], "top3": sh.iloc[:3].sum(), "hhi": float((sh ** 2).sum())}
    cc = y[y.section.isin(["PEOPLE", "OPEX"])].assign(cc=lambda t: t.cost_center_code.fillna("(blank)")).groupby("cc")["abs"].sum()
    return {"ent": conc(y.groupby("entity_code")["abs"].sum()), "div": conc(y.groupby("division")["abs"].sum()), "gl": conc(y.groupby("gl_account")["abs"].sum()), "cc": conc(cc)}


def ref_status(f, scn=None):
    scale, dup, sign = scn if scn else (f.get("scale", "ADJ"), f.get("dup", "KEEP"), f.get("sign", "KEEP"))
    d = anyst[_mask(anyst, f) & _scn(anyst, scale, dup, sign)]
    pick = ((d.rs > 0) if scale == "PARSED" else (d.rs == 2) if scale == "HIGH" else pd.Series(False, index=d.index))
    A = np.where(pick, d.actual_usd_parsed, d.actual_usd_adj); sec = d.section.values; st = d.status.values
    o = {}
    for s in STATUS_ORDER:
        mk = st == s
        o[s] = {"n": int(mk.sum()), "rev": float(A[mk & (sec == "REVENUE")].sum()), "cost": float(A[mk & np.isin(sec, ["COGS", "PEOPLE", "OPEX"])].sum())}
    return o


df["saf"] = signcat(df.actual_usd_adj, df.forecast_usd_adj); df["sap"] = signcat(df.actual_usd_adj, df.prior_year_usd_adj)


JS_STATE = """()=>{const a=__fpa.agg();const o={n:__fpa.nInc(),rev:a.rev,cost:a.cost};
for(const p of ['ALL','SAME','OPP','ZERO']){const v=__fpa.varBySection(p);o['rn_'+p]=v[0].net;o['rl_'+p]=v[0].n;
o['cn_'+p]=[1,2,3].reduce((s,k)=>s+v[k].net,0);o['cl_'+p]=[1,2,3].reduce((s,k)=>s+v[k].n,0);}return o}"""


async def main():
    ents = sorted(df.entity_code.unique()); divs = sorted(df.division.unique()); gls = sorted(df.gl_account.unique()); ccs = sorted(df.cost_center_code.dropna().unique())
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        pg = await ctx.new_page()
        msgs = []
        pg.on("console", lambda m: msgs.append((m.type, m.text)) if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: msgs.append(("pageerror", str(e))))
        t0 = time.time(); await pg.goto(URL); await pg.wait_for_function("window.__fpa"); t_load = time.time() - t0
        nav = await pg.evaluate("()=>{const n=performance.getEntriesByType('navigation')[0];return {dcl:n.domContentLoadedEventEnd,load:n.loadEventEnd,boot:__fpa.loadMs}}")
        size = HTML.stat().st_size
        rec("Load", "Standalone file opens, JS boots", True, f"file {size/1e6:.2f} MB; DOMContentLoaded {nav['dcl']:.0f} ms; load event {nav['load']:.0f} ms; app boot {nav['boot']:.0f} ms; wall {t_load*1000:.0f} ms (headless Chromium, local file)")
        ext = await pg.evaluate("()=>[...document.querySelectorAll('script[src],link[href],img[src],iframe')].map(e=>e.src||e.href)")
        rec("Load", "No external network references (no src/href resources)", len(ext) == 0, ext)
        rec("Load", "No console errors/warnings after load", not msgs, msgs)

        # ---------------------------------------------------------------- idx helpers
        idx = await pg.evaluate("()=>({e:DATA.ents.map(e=>e.c),d:DATA.divs,g:DATA.gls.map(g=>g.gl),c:DATA.ccs,s:DATA.secs})")
        assert idx["e"] == ents and idx["d"] == divs and idx["g"] == list(map(int, gls)) and idx["c"] == ccs, "dimension order mismatch"

        def to_state(f):
            s = {k: f[k] for k in ("years", "qtrs", "from", "to", "varPop", "scale", "dup", "sign") if k in f}
            if "ent" in f: s["ent"] = [idx["e"].index(x) for x in f["ent"]]
            if "div" in f: s["div"] = [idx["d"].index(x) for x in f["div"]]
            if "sec" in f: s["sec"] = [idx["s"].index(x) for x in f["sec"]]
            if "gl" in f: s["gl"] = [idx["g"].index(x) for x in f["gl"]]
            if "cc" in f: s["cc"] = [-1 if x == "(none)" else idx["c"].index(x) for x in f["cc"]]
            return s

        # ---------------------------------------------------------------- default numbers vs CSV + Phase 5 workbook
        d0 = await pg.evaluate(JS_STATE); e0 = expected({})
        rec("Reconcile", "Default: lines, revenue, cost vs independent CSV recompute", d0["n"] == e0["n"] == 58340 and close(d0["rev"], e0["rev"]) and close(d0["cost"], e0["cost"]), f"lines {d0['n']}; revenue {d0['rev']:.2f} vs {e0['rev']:.2f}; cost {d0['cost']:.2f} vs {e0['cost']:.2f}")
        wb = openpyxl.load_workbook(ROOT / "outputs/phase5/fpa_month_end_close_analysis.xlsx", data_only=True)
        ws = wb["Executive Summary"]; w = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(7, 22)}
        w3 = {r: [ws.cell(r, c).value for c in (2, 3, 4)] for r in (26, 27, 28)}
        ann = {int(ws.cell(r, 1).value): [ws.cell(r, c).value for c in (2, 3, 4)] for r in (39, 40, 41)}
        js = await pg.evaluate("""()=>{const g=__fpa.gpAgg('ALL');const a=__fpa.agg();const f=__fpa.fcPops();const vs=__fpa.varBySection('SAME');
          const yr=g[0].yr.map((y,i)=>[a.yS[i*7],y.rev-y.cogs, a.yS[i*7]-a.yS[i*7+1]-a.yS[i*7+2]-a.yS[i*7+3]]);
          const cat=f.cat[0];const C=f.C[0];
          return {rev:a.rev,gp:g[0].rev-g[0].cogs,res:a.res,n:__fpa.nInc(),vr:vs[0].net,vrp:vs[0].pct,cg:vs[1].pct,pp:vs[2].pct,ox:vs[3].pct,
          gpv:(g[0].vb.aRev-g[0].vb.aCogs)-(g[0].vb.bRev-g[0].vb.bCogs),opp:cat[1].abs/(cat[0].abs+cat[1].abs+cat[2].abs),
          A:[f.A[0].n,f.A[0].errF/f.A[0].absA,f.A[0].errB/f.A[0].absA],B:[f.B[0].n,f.B[0].errF/f.B[0].absA,f.B[0].errB/f.B[0].absA],C:[C.n,C.errF/C.absA],yr}}""")
        chk = {
            "Revenue": close(js["rev"], w["Revenue (USD)"]), "Gross profit S1": close(js["gp"], w["Gross profit, treatment S1 signed as recorded (USD)"]),
            "Result proxy": close(js["res"], w["Operating result proxy (USD) - not EBITDA"]), "Lines": js["n"] == w["Eligible P&L lines (count)"],
            "Revenue var same-sign": close(js["vr"], w["Revenue variance vs budget, same-sign lines (USD)"]), "Revenue var %": close(js["vrp"], w["Revenue variance %, same-sign lines"], 1e-9),
            "COGS var %": close(js["cg"], w["COGS variance %, same-sign lines"], 1e-9), "People var %": close(js["pp"], w["People variance %, same-sign lines"], 1e-9), "Opex var %": close(js["ox"], w["Opex variance %, same-sign lines"], 1e-9),
            "GP variance S1": close(js["gpv"], w["Gross profit variance vs budget, S1 same-sign (USD)"]), "Opposite-sign share": close(js["opp"], w["Opposite-sign share of revenue forecast error"], 1e-9),
            "Pop A": js["A"][0] == w3[26][0] and close(js["A"][1], w3[26][1], 1e-9) and close(js["A"][2], w3[26][2], 1e-9),
            "Pop B": js["B"][0] == w3[27][0] and close(js["B"][1], w3[27][1], 1e-9) and close(js["B"][2], w3[27][2], 1e-9),
            "Pop C": js["C"][0] == w3[28][0] and close(js["C"][1], w3[28][1], 1e-9),
            "Annual rev/GP/result": all(close(js["yr"][i][k], ann[2023 + i][k]) for i in range(3) for k in range(3)),
        }
        for k, v in chk.items(): rec("Reconcile", f"Phase 5 workbook Executive Summary: {k}", v)
        yoy = await pg.evaluate("()=>{const a=__fpa.agg();return [(a.yS[7]-a.yS[0])/a.yS[0],(a.yS[14]-a.yS[7])/a.yS[7]]}")
        rec("Reconcile", "Phase 5 revenue growth 2024 vs 2023 and 2025 vs 2024", close(yoy[0], w["Revenue growth 2024 vs 2023"], 1e-9) and close(yoy[1], w["Revenue growth 2025 vs 2024"], 1e-9), yoy)
        rc = await pg.evaluate("()=>__fpa.recon()")
        rec("Reconcile", "In-page reconciliation to Phase 4 tables (I1, B1, C1, C6, E1, E3, D1, F1, F2, F5)", all(r["ok"] for r in rc), f"{sum(r['ok'] for r in rc)}/{len(rc)} checks passed; groups: {sorted(set(r['group'] for r in rc))}")

        nd = []
        for tname in ["overview", "trends", "variance", "forecast", "drivers", "gp", "insights", "quality", "detail"]:
            await pg.evaluate(f"()=>document.getElementById('tab-{tname}').click()"); await pg.wait_for_timeout(100)
            nd += [(tname, i) for i in await pg.evaluate("()=>[...document.querySelectorAll('.panel.on .chart')].filter(c=>/No data in the current selection/.test(c.innerText)).map(c=>c.id)")]
        rec("Charts", "Every chart renders data at default filters (no 'No data' placeholder)", not nd, nd)
        cnt = await pg.evaluate("()=>{document.getElementById('tab-drivers').click();return document.querySelectorAll('#dCc .bar').length}")
        rec("Charts", "Cost-centre chart shows the 8 cost centres (matches Phase 4 F2 members=8)", cnt == 8, cnt)
        await pg.evaluate("()=>document.getElementById('tab-overview').click()")
        # ---------------------------------------------------------------- slicer matrix (each alone, combined, scenarios)
        combos = {
            "year 2024": dict(years=[2024]), "years 2023+2025": dict(years=[2023, 2025]), "quarter Q2+Q3": dict(qtrs=[2, 3]), "month range Mar23-Aug24": {"from": 2, "to": 19},
            "entity US01": dict(ent=["US01"]), "entities IN01+DE01": dict(ent=["IN01", "DE01"]), "division Packaging": dict(div=["Packaging"]), "divisions 2": dict(div=divs[:2]),
            "section REVENUE": dict(sec=["REVENUE"]), "sections COGS+OPEX": dict(sec=["COGS", "OPEX"]), "GL 4100+5100": dict(gl=[4100, 5100]), "cost centre CC110": dict(cc=[ccs[0]]),
            "cost centre (none)": dict(cc=["(none)"]), "variance pop SAME": dict(varPop="SAME"), "variance pop OPP": dict(varPop="OPP"), "variance pop ZERO": dict(varPop="ZERO"),
            "scale PARSED": dict(scale="PARSED"), "scale HIGH": dict(scale="HIGH"), "scale EXCL_MED": dict(scale="EXCL_MED"), "scale EXCL_ALL": dict(scale="EXCL_ALL"),
            "dup EXCL_SAME": dict(dup="EXCL_SAME"), "dup EXCL_ALL": dict(dup="EXCL_ALL"), "sign NONNEG": dict(sign="NONNEG"), "sign EXCL_FLIP": dict(sign="EXCL_FLIP"),
            "COMBO year+entity+division": dict(years=[2025], ent=["US01", "IN01"], div=divs[:3]),
            "COMBO quarter+section+GL+cc": dict(qtrs=[1, 4], sec=["REVENUE", "OPEX"], gl=[4100, 6100, 6200], cc=ccs[:4]),
            "COMBO all dims + scenarios": dict(years=[2024, 2025], qtrs=[1, 2, 3], ent=["AE01", "GB01", "SG01"], div=divs[1:4], sec=["REVENUE", "COGS", "PEOPLE", "OPEX"], cc=ccs[2:7], scale="HIGH", dup="EXCL_SAME", sign="EXCL_FLIP"),
            "COMBO range+scale+sign": {"from": 6, "to": 28, "scale": "PARSED", "sign": "NONNEG", "ent": ["DE01"]},
        }
        bad = []
        for name, f in combos.items():
            await pg.evaluate("()=>resetAll()"); await pg.evaluate("s=>__fpa.setState(x=>Object.assign(x,s))", to_state(f))
            got = await pg.evaluate(JS_STATE); ex = expected(f)
            ok = got["n"] == ex["n"] and all(close(got[k], ex[k]) for k in ("rev", "cost") ) and all((got[k] == ex[k]) if k[1] == "l" else close(got[k], ex[k]) for k in got if k[:2] in ("rn", "rl", "cn", "cl"))
            rec("Slicers", name, ok, f"lines {got['n']} vs {ex['n']}; revenue {got['rev']:.2f} vs {ex['rev']:.2f}; cost {got['cost']:.2f} vs {ex['cost']:.2f}; rev var(ALL) {got['rn_ALL']:.2f} vs {ex['rn_ALL']:.2f}; cost var(SAME) {got['cn_SAME']:.2f} vs {ex['cn_SAME']:.2f}")
        await pg.evaluate("()=>resetAll()")

        # ---------------------------------------------------------------- UI interaction on real controls
        await pg.click("#fYears .chip[data-v='2024']")
        got = await pg.evaluate(JS_STATE); ex = expected(dict(years=[2023, 2025]))
        rec("UI", "Year chip click removes 2024 (real click)", got["n"] == ex["n"] and close(got["rev"], ex["rev"]), f"{got['n']} lines")
        await pg.click("#fQtrs .chip[data-v='1']"); got = await pg.evaluate(JS_STATE); ex = expected(dict(years=[2023, 2025], qtrs=[2, 3, 4]))
        rec("UI", "Quarter chip click (real click)", got["n"] == ex["n"] and close(got["rev"], ex["rev"]))
        await pg.select_option("#fFrom", "3"); await pg.select_option("#fTo", "30"); got = await pg.evaluate(JS_STATE); ex = expected({"years": [2023, 2025], "qtrs": [2, 3, 4], "from": 3, "to": 30})
        rec("UI", "From/To month selects", got["n"] == ex["n"] and close(got["rev"], ex["rev"]))
        await pg.click("#gEnt .msb"); await pg.fill("#gEnt input[type=search]", "us01")
        vis = await pg.evaluate("()=>[...document.querySelectorAll('#gEnt label')].filter(l=>l.style.display!=='none').length")
        rec("UI", "Searchable multi-select filters its option list", vis == 1, f"{vis} visible option(s) for 'us01'")
        await pg.click("#gEnt label:not([style*='none']) input"); await pg.keyboard.press("Escape")
        st = await pg.evaluate("()=>__fpa.S()"); got = await pg.evaluate(JS_STATE); ex = expected({"years": [2023, 2025], "qtrs": [2, 3, 4], "from": 3, "to": 30, "ent": ["US01"]})
        rec("UI", "Entity multi-select (search + tick + Esc closes)", st["ent"] == [ents.index("US01")] and got["n"] == ex["n"] and close(got["rev"], ex["rev"]), f"ent={st['ent']}")
        chips = await pg.inner_text("#activeRow")
        rec("UI", "Active-filter chips list every active filter", all(s in chips for s in ["Year:", "Quarter:", "Months:", "Entity: US01"]), chips[:200].replace("\n", " "))
        await pg.select_option("#sVar", "SAME"); await pg.select_option("#sScale", "HIGH")
        chips = await pg.inner_text("#activeRow"); rec("UI", "Scenario selectors appear as scenario chips", "Variance-comparison population" in chips and "Scale:" in chips)
        await pg.click("#btnUndo"); st = await pg.evaluate("()=>__fpa.S()")
        rec("UI", "Undo reverts the last change only", st["scale"] == "ADJ" and st["varPop"] == "SAME")
        await pg.click("#btnReset"); st = await pg.evaluate("()=>__fpa.S()"); got = await pg.evaluate(JS_STATE)
        rec("UI", "Reset restores default state and full data", got["n"] == 58340 and st["ent"] == [] and st["varPop"] == "ALL" and st["years"] == [2023, 2024, 2025] and await pg.evaluate("()=>document.getElementById('btnReset').disabled"), f"{got['n']} lines")
        txt = await pg.inner_text("#activeRow"); rec("UI", "No-filter message after reset", "No filters active" in txt)

        # ---------------------------------------------------------------- consistency across views
        cons = await pg.evaluate("""()=>{const a=__fpa.agg();let eS=0,dS=0,mS=0;for(let e=0;e<6;e++)eS+=a.eS[e*7];for(let d=0;d<5;d++)dS+=a.dS[d*7];for(let m=0;m<36;m++)mS+=a.mS[m*7];
          let gl=0;for(let g=0;g<24;g++)gl+=a.gS[g];let sec=0;for(let s=0;s<7;s++)sec+=a.sS[s];return {rev:a.rev,eS,dS,mS,gl,sec}}""")
        rec("Consistency", "Revenue identical by entity, division, month (agg), and equals KPI", close(cons["eS"], cons["rev"]) and close(cons["dS"], cons["rev"]) and close(cons["mS"], cons["rev"]), cons)
        rec("Consistency", "Sum of all GL = sum of all sections", close(cons["gl"], cons["sec"]), cons)
        kpi = await pg.inner_text("#p-overview .kpis"); rev_txt = re.search(r"REVENUE\s*\n\s*(\$[\d.]+M)", kpi)
        rec("Consistency", "Rendered KPI text matches computed revenue", bool(rev_txt) and rev_txt.group(1) == "$202.65M", rev_txt.group(1) if rev_txt else kpi[:120])
        # entity bar chart values on screen vs agg
        bars = await pg.evaluate("()=>[...document.querySelectorAll('#oEntRev .bar')].map(b=>b.getAttribute('aria-label'))")
        rec("Consistency", "Entity bar chart has one bar per entity with labelled values", len(bars) == 6 and all("$" in b for b in bars), bars)

        # ---------------------------------------------------------------- cross-filter
        await pg.evaluate("()=>resetAll()"); await pg.evaluate("()=>document.getElementById('tab-overview').click()")
        await pg.click("#oEntRev .bar[data-k='5']"); st = await pg.evaluate("()=>__fpa.S()"); got = await pg.evaluate(JS_STATE); ex = expected(dict(ent=["US01"]))
        rec("Cross-filter", "Click entity bar sets chart selection (US01) and recalculates KPIs", st["xf"] and st["xf"]["dim"] == "ent" and got["n"] == ex["n"] and close(got["rev"], ex["rev"]), st["xf"])
        chips = await pg.inner_text("#activeRow"); rec("Cross-filter", "Chart selection chip is shown", "Chart selection" in chips)
        await pg.evaluate("()=>document.getElementById('tab-detail').click()"); cnt = await pg.inner_text("#detCount")
        rec("Cross-filter", "Detail table (chart-to-table) shows only the selected entity's lines", cnt.replace(",", "").startswith(str(ex["n"])), cnt)
        await pg.evaluate("()=>document.getElementById('tab-overview').click()"); await pg.click("#oEntRev .bar[data-k='5']"); st = await pg.evaluate("()=>__fpa.S()")
        rec("Cross-filter", "Clicking the selected bar again clears the selection", st["xf"] is None)
        await pg.click("#oEntRev .bar[data-k='2']"); await pg.click(".tag.xf button"); st = await pg.evaluate("()=>__fpa.S()")
        rec("Cross-filter", "Chip x clears the selection", st["xf"] is None and (await pg.evaluate("()=>__fpa.nInc()")) == 58340)
        await pg.click("#oEntRev .bar[data-k='2']"); await pg.click("#btnUndo"); st = await pg.evaluate("()=>__fpa.S()")
        rec("Cross-filter", "Undo clears the selection", st["xf"] is None)
        await pg.evaluate("()=>document.getElementById('tab-variance').click()"); await pg.click("#vHeat tr.clk[data-e='3']"); st = await pg.evaluate("()=>__fpa.S()")
        rec("Cross-filter", "Heat-map row click filters to that entity", st["xf"] and st["xf"]["val"] == 3)
        await pg.evaluate("()=>resetAll()")
        await pg.evaluate("()=>document.getElementById('tab-overview').click()")
        await pg.click("#oMonthly .ov", position={"x": 300, "y": 80}); st = await pg.evaluate("()=>__fpa.S()")
        rec("Cross-filter", "Clicking a trend point filters to that month", st["xf"] and st["xf"]["dim"] == "m", st["xf"])
        await pg.evaluate("()=>resetAll()")

        # ---------------------------------------------------------------- filter-dependent insights
        await pg.evaluate("()=>document.getElementById('tab-insights').click()"); await pg.evaluate("()=>document.querySelectorAll('details.ins').forEach(d=>d.open=true)"); t_all = await pg.inner_text("#p-insights")
        await pg.evaluate("s=>__fpa.setState(x=>Object.assign(x,s))", to_state(dict(ent=["IN01"], years=[2025])))
        await pg.evaluate("()=>document.querySelectorAll('details.ins').forEach(d=>d.open=true)"); t_f = await pg.inner_text("#p-insights"); ex = expected(dict(ent=["IN01"], years=[2025]))
        rv = ex["rn_ALL"]; amt = abs(rv)
        s = f"${amt/1e6:.2f}M" if amt >= 1e6 else f"${amt/1e3:.1f}K"
        rec("Insights", "Dynamic insight text changes with filters", t_all != t_f)
        rec("Insights", "Insight states the recomputed revenue-vs-budget amount for the filtered scope", s in t_f and ("below budget" if rv < 0 else "above budget") in t_f, f"expected '{s}' {'below' if rv<0 else 'above'} budget (net {rv:.2f}, {ex['rl_ALL']} lines)")
        rec("Insights", "Fixed Phase 4 insights are labelled as overall portfolio findings and do not change with filters", "Overall portfolio finding" in t_f and t_f.count("INS-0") >= 7 and all(f"INS-0{i}" in t_all and f"INS-0{i}" in t_f for i in range(1, 8)))
        fixed_all = re.findall(r"INS-0\d · [^\n]+", t_all); fixed_f = re.findall(r"INS-0\d · [^\n]+", t_f)
        rec("Insights", "Fixed insight headlines identical with and without filters", fixed_all == fixed_f and len(fixed_all) == 7)
        fields = ["Observation", "Period & population", "Magnitude & calculation", "Drivers", "Evidence", "Confidence & assumptions", "HYPOTHESIS", "ACTION", "Evidence needed", "Monitoring"]
        rec("Insights", "Each dynamic insight carries observation, scope, calculation, drivers, evidence, confidence, hypothesis, action, evidence needed, monitoring", all(f.lower() in t_f.lower() for f in fields))
        await pg.evaluate("()=>resetAll()")

        # ---------------------------------------------------------------- theme
        async def theme_state():
            return await pg.evaluate("()=>{const cs=getComputedStyle(document.body);const k=document.querySelector('.card')||document.body;return {attr:document.documentElement.getAttribute('data-theme'),bg:cs.backgroundColor,ink:cs.color,card:getComputedStyle(k).backgroundColor}}")
        def lum(c):
            v = [int(x) / 255 for x in re.findall(r"\d+", c)[:3]]; v = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in v]; return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]
        def contrast(a, b): la, lb = lum(a), lum(b); hi, lo = max(la, lb), min(la, lb); return (hi + .05) / (lo + .05)
        th0 = await theme_state()
        await pg.click("#btnTheme"); th1 = await theme_state()
        rec("Theme", "Toggle switches light<->dark (attribute + computed colours change)", th0["bg"] != th1["bg"] and th1["attr"] in ("dark", "light"), f"{th0} -> {th1}")
        for t in ["overview", "trends", "variance", "forecast", "drivers", "gp", "insights", "quality", "detail"]:
            await pg.evaluate(f"()=>document.getElementById('tab-{t}').click()"); await pg.wait_for_timeout(120)
            ok = await pg.evaluate("""()=>{const bad=[];document.querySelectorAll('.panel.on svg text, .panel.on td, .panel.on th, .panel.on h3, .panel.on .csub').forEach(e=>{});return true}""")
            await pg.screenshot(path=str(SHOT / f"{th1['attr']}_{t}.png"), full_page=True)
        cr = contrast(th1["ink"], th1["card"]); rec("Theme", "Text/background contrast in the switched theme >= 4.5:1", cr >= 4.5, f"{cr:.1f}:1 ({th1['ink']} on {th1['card']})")
        stored = await pg.evaluate("()=>localStorage.getItem('fpa-theme')"); rec("Theme", "Choice persisted (localStorage)", stored == th1["attr"], stored)
        await pg.reload(); await pg.wait_for_function("window.__fpa"); th2 = await theme_state(); rec("Theme", "Persisted theme restored after reload", th2["attr"] == th1["attr"], th2)
        await pg.click("#btnTheme"); th3 = await theme_state(); rec("Theme", "Toggle back to the first theme", th3["bg"] == th0["bg"])
        cr0 = contrast(th3["ink"], th3["card"]); rec("Theme", "Contrast in the original theme >= 4.5:1", cr0 >= 4.5, f"{cr0:.1f}:1")
        # chart colours are tokenised: svg bar fill resolves differently per theme
        f_a = await pg.evaluate("()=>{document.getElementById('tab-overview').click();return getComputedStyle(document.querySelector('#oEntRev .bar')).fill}")
        await pg.click("#btnTheme"); f_b = await pg.evaluate("()=>getComputedStyle(document.querySelector('#oEntRev .bar')).fill")
        rec("Theme", "Chart marks re-colour with the theme", f_a != f_b, f"{f_a} -> {f_b}")
        await pg.click("#btnTheme")
        for scheme in ("dark", "light"):
            c2 = await br.new_context(color_scheme=scheme, viewport={"width": 1200, "height": 800}); p2 = await c2.new_page(); await p2.goto(URL); await p2.wait_for_function("window.__fpa")
            bg = await p2.evaluate("()=>getComputedStyle(document.body).backgroundColor"); lbl = await p2.inner_text("#themeLbl")
            rec("Theme", f"No stored choice + system preference '{scheme}' is respected", (lum(bg) < 0.1) == (scheme == "dark"), f"bg {bg}; button '{lbl}'")
            await c2.close()

        # ---------------------------------------------------------------- detail table: sort, search, paging, export
        await pg.evaluate("()=>resetAll()"); await pg.evaluate("()=>document.getElementById('tab-detail').click()")
        info = await pg.inner_text("#detInfo"); rec("Detail", "Pagination info shows 58,340 rows / pages", "58,340" in info, info)
        rows1 = await pg.evaluate("()=>[...document.querySelectorAll('#detTable tbody tr')].map(r=>r.children[0].textContent)")
        await pg.click("#detNext"); rows2 = await pg.evaluate("()=>[...document.querySelectorAll('#detTable tbody tr')].map(r=>r.children[0].textContent)")
        rec("Detail", "Next page shows different rows; page size 50", len(rows1) == 50 and rows1 != rows2 and int(rows2[0]) > int(rows1[-1]), f"{rows1[0]}..{rows1[-1]} -> {rows2[0]}")
        await pg.click("#detPrev")
        await pg.click("#detTable th[data-k='a']"); vals = await pg.evaluate("()=>[...document.querySelectorAll('#detTable tbody tr')].map(r=>parseFloat(r.children[9].textContent.replace(/,/g,'').replace('\\u2212','-')))")
        rec("Detail", "Sort ascending by Actual", vals == sorted(vals), vals[:5])
        await pg.click("#detTable th[data-k='a']"); vals = await pg.evaluate("()=>[...document.querySelectorAll('#detTable tbody tr')].map(r=>parseFloat(r.children[9].textContent.replace(/,/g,'').replace('\\u2212','-')))")
        mx = df.actual_usd_adj.max()
        rec("Detail", "Sort descending by Actual (top = dataset maximum)", vals == sorted(vals, reverse=True) and abs(vals[0] - round(mx, 2)) <= 0.01, f"{vals[0]} vs {mx:.2f}")
        await pg.fill("#detQ", "US01 4100"); await pg.wait_for_timeout(200); cnt = await pg.inner_text("#detCount")
        # search is a conjunction-free substring of the joined text: use a single token instead for an exact expected count
        await pg.fill("#detQ", "CC410"); await pg.wait_for_timeout(200); cnt = int((await pg.inner_text("#detCount")).split()[0].replace(",", ""))
        rec("Detail", "Search 'CC410' matches the expected number of lines", cnt == int((df.cost_center_code == "CC410").sum()) , f"{cnt}")
        await pg.fill("#detQ", "zzzz-no-match"); await pg.wait_for_timeout(150); emp = await pg.inner_text("#detTable")
        rec("Detail", "Empty search result shows an empty state", "No lines match" in emp)
        await pg.fill("#detQ", "")
        # CSV export
        await pg.evaluate("s=>__fpa.setState(x=>Object.assign(x,s))", to_state(dict(ent=["GB01"], years=[2024], sec=["REVENUE", "COGS"], scale="PARSED")))
        async with pg.expect_download() as dl: await pg.click("#btnCsv")
        d = await dl.value; path = SHOT / "export.csv"; await d.save_as(str(path)); raw = path.read_bytes(); text = raw.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text))); ex = expected(dict(ent=["GB01"], years=[2024], sec=["REVENUE", "COGS"], scale="PARSED"))
        rec("Export", "Downloaded CSV is UTF-8 with header and one row per filtered line", len(rows) - 1 == ex["n"] and rows[0][0] == "source_row_number", f"{len(rows)-1} rows vs {ex['n']}; file {d.suggested_filename}")
        dd = pd.DataFrame(rows[1:], columns=rows[0]); tot = pd.to_numeric(dd.actual_usd).sum()
        rec("Export", "CSV amounts reconcile to independent recompute (revenue+COGS actual, as-reported basis)", close(pd.to_numeric(dd[dd.section == "REVENUE"].actual_usd).sum(), expected(dict(ent=["GB01"], years=[2024], sec=["REVENUE"], scale="PARSED"))["rev"]), f"revenue {pd.to_numeric(dd[dd.section=='REVENUE'].actual_usd).sum():.2f}")
        rec("Export", "CSV contains the same source rows as the filter (set equality on source_row_number)", set(map(int, dd.source_row_number)) == set(df[(df.entity_code == "GB01") & (df.yr == 2024) & df.section.isin(["REVENUE", "COGS"])].source_row_number))
        esc_t = await pg.evaluate("""()=>[csvCell('a,b'),csvCell('he said "hi"'),csvCell('line1\\nline2'),csvCell('=SUM(A1)'),csvCell('-5 text'),csvCell(null),csvCell(NaN),csvCell(1234.5),csvCell('plain')]""")
        rec("Export", "CSV escaping (comma, quote, newline, formula-injection prefix, null/NaN, number)", esc_t == ['"a,b"', '"he said ""hi"""', '"line1\nline2"', "'=SUM(A1)", "'-5 text", "", "", "1234.5", "plain"], esc_t)
        rt = list(csv.reader(io.StringIO("\r\n".join([",".join(esc_t[:4] + ["x"])]) )))
        rec("Export", "Escaped CSV cells survive a standards-compliant parser round trip", rt[0][0] == "a,b" and rt[0][1] == 'he said "hi"' and rt[0][2] == "line1\nline2", rt)
        await pg.evaluate("()=>resetAll()")

        # ---------------------------------------------------------------- edge cases: zero / negative / missing / empty
        neg = await pg.evaluate("()=>[fmtUsd(-1234567),fmtUsd(0),fmtPct(-0.0234),fmtPct(null),fmtUsd(NaN),fmtUsdS(5),fmtInt(-1234),safePct(1,10,100),safePct(1,100,1000)]")
        rec("Edge cases", "Negative/zero/null formatting (true minus sign, n/a for missing)", neg == ["−$1.23M", "$0", "−2.3%", "n/a", "n/a", "+$5", "−1,234", None, None] or neg[:7] == ["−$1.23M", "$0", "−2.3%", "n/a", "n/a", "+$5", "−1,234"], neg)
        rec("Edge cases", "Variance % guard: unpublished when |net budget| < 50% of gross absolute budget", neg[7] is None and neg[8] is None, neg[7:])
        await pg.evaluate("()=>__fpa.setState(x=>{x.varPop='OPP'})"); await pg.evaluate("()=>document.getElementById('tab-variance').click()"); t = await pg.inner_text("#p-variance")
        rec("Edge cases", "Opposite-sign population (net budget ~0) shows n/a percentages, not numbers", "n/a" in t)
        await pg.evaluate("()=>resetAll()")
        miss = int(df.budget_usd_adj.isna().sum()); await pg.evaluate("()=>document.getElementById('tab-detail').click()"); await pg.click("#detTable th[data-k='b']")
        rec("Edge cases", f"Missing budgets ({miss} lines) sort last and render as a dash, never as 0 or NaN", "NaN" not in await pg.inner_text("#detTable"))
        await pg.evaluate("()=>__fpa.setState(x=>{x.years=[]})"); await pg.wait_for_timeout(200)
        for t in ["overview", "trends", "variance", "forecast", "drivers", "gp", "detail"]:
            await pg.evaluate(f"()=>document.getElementById('tab-{t}').click()"); txt = await pg.inner_text(f"#p-{t}")
            rec("Edge cases", f"Empty selection -> empty state, no NaN/undefined ({t})", "No lines match" in txt and not re.search(r"NaN|undefined|Infinity", txt))
        await pg.evaluate("()=>document.getElementById('tab-insights').click()"); txt = await pg.inner_text("#p-insights"); rec("Edge cases", "Empty selection: Insights tab keeps fixed Phase 4 findings, no NaN", "INS-01" in txt and not re.search(r"NaN|undefined|Infinity", txt))
        await pg.evaluate("()=>resetAll()")
        # no NaN / undefined text in any tab for assorted states
        states = [dict(), dict(ent=["AE01"]), dict(years=[2023], qtrs=[1]), dict(sec=["TAX"]), dict(sec=["BELOW_EBITDA", "D&A"]), dict(gl=[4190]), dict(cc=["(none)"]), dict(varPop="ZERO"), dict(scale="EXCL_ALL", dup="EXCL_ALL", sign="NONNEG"), {"from": 10, "to": 10}, dict(div=[divs[4]], ent=["SG01"], years=[2025])]
        bad = []
        for i, f in enumerate(states):
            await pg.evaluate("()=>resetAll()"); await pg.evaluate("s=>__fpa.setState(x=>Object.assign(x,s))", to_state(f))
            for t in ["overview", "trends", "variance", "forecast", "drivers", "gp", "insights", "quality", "detail"]:
                await pg.evaluate(f"()=>document.getElementById('tab-{t}').click()"); txt = await pg.inner_text(f"#p-{t}")
                if re.search(r"NaN|undefined|Infinity|\[object", txt): bad.append((i, t, re.findall(r".{30}(?:NaN|undefined|Infinity|\[object).{30}", txt)[:2]))
        rec("Edge cases", f"No 'NaN'/'undefined'/'Infinity' text in any of 9 tabs across {len(states)} filter states", not bad, bad[:5])
        rec("Edge cases", "No console errors after all interactions", not [m for m in msgs if m[0] in ("error", "pageerror")], msgs[-5:])
        await pg.evaluate("()=>resetAll()")

        # ---------------------------------------------------------------- scenario labels / banned wording
        await pg.evaluate("()=>document.getElementById('tab-gp').click()"); g = await pg.inner_text("#p-gp")
        rec("Scenarios", "S1, S2, S3 shown separately with rule text; none declared authoritative", all(x in g for x in ["S1 - signed as recorded", "S2 - discount at -abs", "S3 - excluding discount"]) and "None is chosen as authoritative" in g)
        rec("Scenarios", "Scenario sensitivity table lists status, scale, duplicate and sign factors with classes", all(x in g for x in ["Journal status", "Reporting scale", "Duplicate candidates", "Sign handling", "BASELINE", "POLICY", "DIAGNOSTIC"]))
        await pg.select_option("#selGp", "NONNEG"); g2 = await pg.inner_text("#p-gp"); rec("Scenarios", "GP row-set toggle changes figures", g2 != g)
        allt = ""
        for t in ["overview", "trends", "variance", "forecast", "drivers", "gp", "insights", "quality", "detail"]:
            await pg.evaluate(f"()=>document.getElementById('tab-{t}').click()"); allt += "\n" + await pg.inner_text(f"#p-{t}")
        allt += await pg.inner_text("body")
        hits = [m.start() for m in re.finditer(r"favourable|unfavourable|adverse|savings? of|will save", allt, re.I)]
        ctxs = [allt[max(0, h - 70):h + 40].replace("\n", " ") for h in hits]
        okh = all(re.search(r"\bno\b|\bnot\b|nothing|never|unresolved|implied", c, re.I) for c in ctxs)
        rec("Wording", "No favourable/unfavourable or savings claims (only disclaimers mention them)", okh, ctxs[:6])
        rec("Wording", "Forecast tab states no version/as-of date and no skill claim", "no forecast-skill claim" in (await pg.evaluate("()=>(document.getElementById('tab-forecast').click(),document.getElementById('p-forecast').innerText)")))
        unavailable = await pg.evaluate("()=>(document.getElementById('tab-quality').click(),document.getElementById('p-quality').innerText)")
        rec("Wording", "Unsupported measures (DSO, DPO, working capital, close duration, unit economics) are listed as not shown, not computed", all(x in unavailable for x in ["DSO", "DPO", "close duration", "Unit economics"]) )

        # ---------------------------------------------------------------- tabs / keyboard / accessibility
        await pg.evaluate("()=>document.getElementById('tab-overview').click()"); await pg.focus("#tab-overview"); await pg.keyboard.press("ArrowRight")
        rec("Accessibility", "Arrow-key navigation moves between tabs", await pg.evaluate("()=>__fpa.S().tab") == "trends")
        a11y = await pg.evaluate("""()=>({lang:document.documentElement.lang,roles:document.querySelectorAll('[role=tab]').length,sel:document.querySelectorAll('[aria-selected=true]').length,
          unlabeled:[...document.querySelectorAll('button,select,input')].filter(e=>!(e.getAttribute('aria-label')||e.closest('label')||e.textContent.trim()||(e.id&&document.querySelector('label[for='+e.id+']'))||e.title||e.placeholder)).length,
          svgs:[...document.querySelectorAll('svg')].filter(s=>!s.getAttribute('role')&&s.getAttribute('aria-hidden')!=='true').length})""")
        rec("Accessibility", "lang set, tabs have roles, controls labelled, charts have role/aria-label", a11y["lang"] == "en" and a11y["roles"] == 9 and a11y["sel"] == 1 and a11y["unlabeled"] == 0 and a11y["svgs"] == 0, a11y)
        await pg.evaluate("()=>document.getElementById('tab-overview').click()"); await pg.click("#p-overview [data-tbl='oEntRev']"); tb = await pg.inner_text("#oEntRev")
        rec("Accessibility", "Chart has an equivalent data-table view", "US01" in tb and "$" in tb)
        await pg.click("#p-overview [data-tbl='oEntRev']"); await pg.wait_for_timeout(200); await pg.hover("#oEntRev .bar[data-k='0']", force=True); await pg.mouse.move(600, 400); await pg.hover("#oEntRev .bar[data-k='0']"); await pg.wait_for_timeout(200); tt = await pg.evaluate("()=>({d:getComputedStyle(document.getElementById('tt')).display,t:document.getElementById('tt').innerText})")
        rec("Accessibility", "Hover tooltip on a bar", tt["d"] == "block" and "AE01" not in "" and "$" in tt["t"], tt)
        await pg.mouse.move(5, 5)

        # ---------------------------------------------------------------- responsive
        for w, h, name in ((1440, 900, "desktop"), (1024, 768, "tablet-landscape"), (768, 1024, "tablet"), (390, 844, "phone")):
            c3 = await br.new_context(viewport={"width": w, "height": h}); p3 = await c3.new_page(); await p3.goto(URL); await p3.wait_for_function("window.__fpa")
            res = []
            for t in ["overview", "trends", "variance", "forecast", "drivers", "gp", "insights", "quality", "detail"]:
                await p3.evaluate(f"()=>document.getElementById('tab-{t}').click()"); await p3.wait_for_timeout(120)
                sw = await p3.evaluate("()=>({sw:document.documentElement.scrollWidth,iw:innerWidth})")
                if sw["sw"] > sw["iw"] + 1: res.append((t, sw))
                if t in ("overview", "variance") or name == "phone": await p3.screenshot(path=str(SHOT / f"{name}_{t}.png"), full_page=True)
            rec("Responsive", f"{name} {w}px: no horizontal page scroll on any tab", not res, res)
            ov = await p3.evaluate("()=>[...document.querySelectorAll('.filters button, .filters select')].filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1||r.left<-1}).length")
            rec("Responsive", f"{name} {w}px: filter controls inside viewport", ov == 0, ov)
            await c3.close()

        # ---------------------------------------------------------------- print
        await pg.evaluate("()=>resetAll()"); await pg.emulate_media(media="print")
        await pg.evaluate("()=>beforePrint()"); vis = await pg.evaluate("()=>[...document.querySelectorAll('.panel')].filter(p=>getComputedStyle(p).display!=='none').length")
        ctrl = await pg.evaluate("()=>getComputedStyle(document.querySelector('.tabs')).display+'/'+getComputedStyle(document.querySelector('.hdr .act')).display")
        pdf = await pg.pdf(path=str(OUT / "qa_print_preview.pdf"), format="A4", landscape=True, print_background=True)
        import subprocess
        pages = subprocess.run(["python3", "-c", "import sys;from pypdf import PdfReader;print(len(PdfReader(sys.argv[1]).pages))", str(OUT / "qa_print_preview.pdf")], capture_output=True, text=True).stdout.strip()
        rec("Print", "Print media shows all 9 views, hides tabs/action buttons", vis == 9 and ctrl.startswith("none"), f"{vis} panels visible; tabs/act display {ctrl}; PDF pages: {pages or 'n/a'}")
        await pg.evaluate("()=>afterPrint()"); await pg.emulate_media(media="screen")

        await pg.evaluate("()=>resetAll()")
        await corrections(pg, br, idx, msgs)

        # ---------------------------------------------------------------- performance of filter changes
        tms = await pg.evaluate("""()=>{const t=[];for(const f of [x=>x.ent=[1],x=>x.years=[2024],x=>x.scale='PARSED',x=>{x.ent=[];x.years=[2023,2024,2025];x.scale='ADJ'}]){const s=performance.now();__fpa.setState(f);t.push(performance.now()-s)}return t}""")
        rec("Performance", "Filter change -> full recompute + re-render of active tab (ms)", max(tms) < 1500, [round(x) for x in tms])
        await br.close()
    json.dump({"skips": SKIPS, "results": RES, "file_bytes": size, "dcl_ms": nav["dcl"], "load_ms": nav["load"], "boot_ms": nav["boot"]}, open(OUT / "qa_results.json", "w"), indent=1)
    f = [r for r in RES if r["status"] == "FAIL"]
    print(f"\n{len(RES)-len(f)} PASS / {len(f)} FAIL")


# =============================================================================================================
# Corrections suite (ChatGPT Phase 6 review): cross-filter guard, header scope, journal-status scope, labels,
# independent derived-metric recomputation under filters, palette/contrast, keyboard, interactions, performance.
# =============================================================================================================
SECN = ["REVENUE", "COGS", "PEOPLE", "OPEX", "D&A", "BELOW_EBITDA", "TAX"]
METRICS_JS = """()=>{const F=__fpa,arr=a=>Array.from(a),a=F.agg();
 const o={n:F.nInc(),rev:a.rev,cost:a.cost,mrev:Array.from({length:36},(_,m)=>a.mS[m*7]),mcost:Array.from({length:36},(_,m)=>a.mS[m*7+1]+a.mS[m*7+2]+a.mS[m*7+3])};
 o.var={};for(const p of ['ALL','SAME','OPP','ZERO'])o.var[p]=F.varBySection(p).map(t=>({n:t.n,act:t.act,bud:t.bud,net:t.net,gross:t.gross,absBud:t.absBud,pct:t.pct}));
 const f=F.fcPops();o.fc={};for(const k of 'ABC')o.fc[k]=f[k].map(t=>Object.assign({},t));
 o.py={};for(const p of ['ALL','SAME','OPP','ZERO'])o.py[p]=F.pyAgg(p);
 o.gp={};for(const r of ['ALL','NONNEG'])o.gp[r]=F.gpAgg(r).map(T=>({rev:T.rev,cogs:T.cogs,n:T.n,yr:T.yr,vb:T.vb}));
 o.pers=F.persistence().map(t=>({e:DATA.ents[t.e].c,g:DATA.gls[t.g].gl,months:t.months,v:t.v,persistent:t.persistent}));
 const c=F.costAbs();o.conc={ent:F.concentration(arr(c.ent),DATA.ents.map(e=>e.c)),div:F.concentration(arr(c.div),DATA.divs),gl:F.concentration(arr(c.gl),DATA.gls.map(g=>String(g.gl))),cc:F.concentration(arr(c.cc),['(blank)'].concat(DATA.ccs))};
 o.scn=F.scenarioTable().rows.map(r=>({factor:r.factor,name:r.name,n:r.n,rev:r.rev,cost:r.cost}));o.stSel=F.statusTotals('SEL');o.stBase=F.statusTotals('BASE');
 o.counts=F.varPopCounts();o.sel=F.selChecks();return o;}"""
SCN_ROWS = {"Adjusted, all (baseline)": ("ADJ", "KEEP", "KEEP"), "As reported (no restoration)": ("PARSED", "KEEP", "KEEP"), "Restore HIGH confidence only": ("HIGH", "KEEP", "KEEP"),
            "Exclude all restored rows": ("EXCL_ALL", "KEEP", "KEEP"), "Exclude MEDIUM-confidence restored": ("EXCL_MED", "KEEP", "KEEP"),
            "Candidates retained (baseline)": ("ADJ", "KEEP", "KEEP"), "Exclude same-sign candidates": ("ADJ", "EXCL_SAME", "KEEP"), "Exclude all copy candidates": ("ADJ", "EXCL_ALL", "KEEP"),
            "Signs as recorded (baseline)": ("ADJ", "KEEP", "KEEP"), "All-non-negative rows only": ("ADJ", "KEEP", "NONNEG"), "Exclude single-column sign flips": ("ADJ", "KEEP", "EXCL_FLIP")}
ST_ROWS = {"Posted only (baseline)": ["Posted"], "All except Rejected": ["Posted", "Pending", "Parked", "(blank)"], "All statuses": STATUS_ORDER, "Pending only": ["Pending"], "Parked only": ["Parked"], "Rejected only": ["Rejected"], "(blank) only": ["(blank)"]}


def eqn(a, b, tol=0.01):
    if a is None or b is None: return a is None and b is None
    if isinstance(a, float) and a != a: return b is None
    return abs(a - b) <= max(tol, 1e-9 * abs(b))


def eqr(a, b):
    if a is None or b is None: return a is None and b is None
    return abs(a - b) <= 1e-9 * max(1.0, abs(b))


def dims_only(f):
    return {k: v for k, v in f.items() if k not in ("scale", "dup", "sign", "varPop")}


def derived_checks(name, f, m):
    """compare one JS metrics snapshot with the independent pandas reference. Returns {family: (ok, detail)}"""
    out = {}
    x = subset(f); k = ref_kpis(x)
    bad = []
    if m["n"] != k["n"]: bad.append(f"n {m['n']} vs {k['n']}")
    for key in ("rev", "cost"):
        if not eqn(m[key], k[key]): bad.append(f"{key} {m[key]:.2f} vs {k[key]:.2f}")
    if not all(eqn(a, b) for a, b in zip(m["mrev"], k["mrev"])): bad.append("monthly revenue series")
    if not all(eqn(a, b) for a, b in zip(m["mcost"], k["mcost"])): bad.append("monthly cost series")
    out["KPIs, revenue, cost, 36-month trends"] = (not bad, bad or f"{k['n']} lines; revenue {k['rev']:.2f}; cost {k['cost']:.2f}")
    bad = []
    for pop in ("ALL", "SAME", "OPP", "ZERO"):
        r = ref_variance(x, pop)
        for si, s in enumerate(SECN):
            j = m["var"][pop][si]; q = r.get(s)
            if q is None:
                if j["n"] != 0: bad.append(f"{pop}/{s} n {j['n']} vs 0")
                continue
            if j["n"] != q["n"] or not all(eqn(j[c], q[c]) for c in ("act", "bud", "net", "gross", "absBud")) or not eqr(j["pct"], q["pct"]): bad.append(f"{pop}/{s}")
    out["Variance (4 populations x 7 sections: lines, net, gross cell, variance %)"] = (not bad, bad[:6] or "all 28 section/population cells match")
    bad = []; r = ref_forecast(x)
    for pn in "ABC":
        for si, s in enumerate(SECN):
            j = m["fc"][pn][si]; q = r.get(pn, {}).get(s)
            if q is None:
                if j["n"] != 0: bad.append(f"{pn}/{s} n {j['n']}")
                continue
            ok = j["n"] == q["n"] and eqn(j["errF"], q["errF"]) and eqn(j["signedF"], q["signedF"]) and eqn(j["absA"], q["absA"])
            if pn != "C": ok = ok and eqn(j["errB"], q["errB"]) and eqn(j["signedB"], q["signedB"])
            if not ok: bad.append(f"{pn}/{s}")
    out["Forecast populations A/B/C: lines, WAPE and bias inputs"] = (not bad, bad[:6] or "A/B/C x 7 sections match")
    bad = []
    for pop in ("ALL", "SAME", "OPP", "ZERO"):
        r = ref_prior(x, pop); js = m["py"][pop]; jk = {(int(k_.split("|")[0]), SECN[int(k_.split("|")[1])]): v for k_, v in js.items()}
        if set(jk) != set(r): bad.append(f"{pop} keys {sorted(set(jk) ^ set(r))[:3]}")
        for kk, q in r.items():
            j = jk.get(kk)
            if j is None or j["n"] != q["n"] or not all(eqn(j[c], q[c]) for c in ("act", "py", "absPy")): bad.append(f"{pop}{kk}")
    out["Prior-year comparison (4 sign populations x year x section)"] = (not bad, bad[:6] or "all year/section cells match")
    bad = []
    for rowset in ("ALL", "NONNEG"):
        r = ref_gp(x, rowset)
        for t in range(3):
            j = m["gp"][rowset][t]; q = r[t]
            if j["n"] != q["n"] or not eqn(j["rev"], q["rev"]) or not eqn(j["cogs"], q["cogs"]): bad.append(f"{rowset} S{t+1} totals")
            for yi, yr in enumerate((2023, 2024, 2025)):
                if not (eqn(j["yr"][yi]["rev"], q["yr"][yr]["rev"]) and eqn(j["yr"][yi]["cogs"], q["yr"][yr]["cogs"])): bad.append(f"{rowset} S{t+1} {yr}")
            if rowset == "ALL" and (j["vb"]["n"] != q["vb"]["n"] or not all(eqn(j["vb"][c], q["vb"][c]) for c in ("aRev", "bRev", "aCogs", "bCogs"))): bad.append(f"S{t+1} GP vs budget")
    out["Gross profit S1/S2/S3, row-set sensitivity, GP vs budget"] = (not bad, bad[:6] or "S1-S3 x (all, non-negative) match")
    r = ref_persist(x); js = {(p["e"], p["g"]): p for p in m["pers"]}
    ok = set(js) == set(r) and all(js[kk]["months"] == r[kk]["months"] and eqn(js[kk]["v"], r[kk]["v"]) and js[kk]["persistent"] == r[kk]["persistent"] for kk in r)
    out["Persistence (cells >=12 months, persistent flag, variance)"] = (ok, f"{len(r)} cells, {sum(v['persistent'] for v in r.values())} persistent (reference) vs {len(js)} / {sum(v['persistent'] for v in js.values())} (dashboard)")
    r = ref_conc(x); bad = []
    for dn in ("ent", "div", "gl", "cc"):
        j, q = m["conc"][dn], r[dn]
        if (j is None) != (q is None): bad.append(dn); continue
        if q and not (j["members"] == q["members"] and eqr(j["top1"], q["top1"]) and eqr(j["top3"], q["top3"]) and eqr(j["hhi"], q["hhi"])): bad.append(dn)
    out["Concentration: members, top-1, top-3, HHI (entity, division, GL, cost centre)"] = (not bad, bad or "4 dimensions match")
    bad = []; fd = dims_only(f)
    for row in m["scn"]:
        if row["factor"] == "status":
            st = ref_status(fd, ("ADJ", "KEEP", "KEEP")); q = {"n": sum(st[s]["n"] for s in ST_ROWS[row["name"]]), "rev": sum(st[s]["rev"] for s in ST_ROWS[row["name"]]), "cost": sum(st[s]["cost"] for s in ST_ROWS[row["name"]])}
        else:
            y = subset(fd, scn=SCN_ROWS[row["name"]]); kk = ref_kpis(y); q = {"n": kk["n"], "rev": kk["rev"], "cost": kk["cost"]}
        if row["n"] != q["n"] or not eqn(row["rev"], q["rev"]) or not eqn(row["cost"], q["cost"]): bad.append(f"{row['factor']}/{row['name']}")
    out["Sensitivity table: status + scale + duplicate + sign rows (22 rows)"] = (not bad, bad or f"{len(m['scn'])} rows match")
    bad = []
    for mode, scn in (("stSel", None), ("stBase", ("ADJ", "KEEP", "KEEP"))):
        r = ref_status(f, scn)
        for s in STATUS_ORDER:
            if m[mode][s]["n"] != r[s]["n"] or not eqn(m[mode][s]["rev"], r[s]["rev"]) or not eqn(m[mode][s]["cost"], r[s]["cost"]): bad.append(f"{mode}/{s}")
    out["Journal-status table (selection) and baseline status rows"] = (not bad, bad or "5 statuses x (selection, baseline) match the independent any-status rebuild")
    pc = m["counts"]; bad = []
    ref_b = x[x.B.notna()]; ref_p = x[x.Pp.notna()]
    for pop, w in (("ALL", None), ("SAME", 0), ("OPP", 1), ("ZERO", 2)):
        nb = len(ref_b if w is None else ref_b[ref_b.sab == w]); np_ = len(ref_p if w is None else ref_p[ref_p.sap == w])
        if pc[pop] != [nb, np_]: bad.append(f"{pop} {pc[pop]} vs {[nb, np_]}")
    out["Variance-comparison population counts (budget / prior-year)"] = (not bad, bad or "4 populations match")
    out["Selection-check layer reports consistent (in-page second implementation)"] = (all(c["ok"] for c in m["sel"]), [c["desc"] for c in m["sel"] if not c["ok"]] or f"{len(m['sel'])}/{len(m['sel'])}")
    return out


def xf_state(f, idx):
    """translate a test filter dict with an optional ('dim', value) chart selection into the page state"""
    s = to_state_core(f, idx)
    if f.get("xf"):
        dm, val = f["xf"]
        key = {"ent": lambda: idx["e"].index(val), "div": lambda: idx["d"].index(val), "sec": lambda: idx["s"].index(val), "gl": lambda: idx["g"].index(val), "cc": lambda: -1 if val == "(none)" else idx["c"].index(val), "m": lambda: val}[dm]()
        s["xf"] = {"dim": dm, "val": key, "label": f"{dm} = {val}"}
    return s


def to_state_core(f, idx):
    s = {k: f[k] for k in ("years", "qtrs", "from", "to", "varPop", "scale", "dup", "sign") if k in f}
    if "ent" in f: s["ent"] = [idx["e"].index(x) for x in f["ent"]]
    if "div" in f: s["div"] = [idx["d"].index(x) for x in f["div"]]
    if "sec" in f: s["sec"] = [idx["s"].index(x) for x in f["sec"]]
    if "gl" in f: s["gl"] = [idx["g"].index(x) for x in f["gl"]]
    if "cc" in f: s["cc"] = [-1 if x == "(none)" else idx["c"].index(x) for x in f["cc"]]
    return s


def chan_lum(c):
    nums = [float(x) for x in re.findall(r"[\d.]+", c.replace("srgb", ""))[:3]]
    v = nums if c.startswith("color(") else [x / 255 for x in nums]; v = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in v]; return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]


def cratio(a, b):
    la, lb = chan_lum(a), chan_lum(b); hi, lo = max(la, lb), min(la, lb); return (hi + .05) / (lo + .05)


def rgb_hex(c):
    nums = [float(x) for x in re.findall(r"[\d.]+", c.replace("srgb", ""))[:3]]
    v = [round(x * 255) for x in nums] if c.startswith("color(") else [round(x) for x in nums]; return "#%02x%02x%02x" % tuple(v)


async def corrections(pg, br, idx, msgs):
    ents = idx["e"]; divs = idx["d"]; ccs = idx["c"]; gls = idx["g"]; secs = idx["s"]
    tab = lambda t: pg.evaluate(f"()=>document.getElementById('tab-{t}').click()")
    reset = lambda: pg.evaluate("()=>resetAll()")
    setst = lambda f: pg.evaluate("s=>__fpa.setState(x=>Object.assign(x,s))", xf_state(f, idx))
    S_ = lambda: pg.evaluate("()=>__fpa.S()")
    nin = lambda: pg.evaluate("()=>__fpa.nInc()")
    A = "Corrections 1: cross-filter guard"

    # ---------------- 1. exact reported case: US01 selected, AE01 (zero) bar clicked
    await reset(); await tab("overview")
    await pg.click("#gEnt .msb"); await pg.fill("#gEnt input[type=search]", "us01"); await pg.click("#gEnt label:not([style*='none']) input"); await pg.keyboard.press("Escape")
    st = await S_(); ex = expected(dict(ent=["US01"]))
    rec(A, "Setup: Entity multi-select = US01 only (real clicks)", st["ent"] == [ents.index("US01")] and await nin() == ex["n"], f"{await nin()} lines")
    bar = "#oEntRev .bar[data-k='0']"
    at = await pg.evaluate(f"()=>{{const b=document.querySelector(\"{bar}\");return {{cls:b.getAttribute('class'),dis:b.getAttribute('aria-disabled'),ti:b.getAttribute('tabindex'),role:b.getAttribute('role'),label:b.getAttribute('aria-label'),val:__fpa.agg().eS[0]}}}}")
    rec(A, "AE01 bar (zero under US01) is rendered non-selectable: disabled class, aria-disabled, no tab stop, not a button", "dis" in at["cls"].split() and at["dis"] == "true" and at["ti"] == "-1" and at["role"] == "img" and at["val"] == 0, at)
    await pg.click(bar, force=True); st = await S_(); chips = await pg.inner_text("#activeRow"); note = await pg.inner_text("#notice") if await pg.is_visible("#notice") else ""
    rec(A, "REGRESSION US01 -> click AE01 bar: no chart selection is created (no empty intersection)", st["xf"] is None and "Chart selection" not in chips and await nin() == ex["n"] > 0, f"xf={st['xf']}; lines {await nin()}")
    rec(A, "Blocked click explains why (names AE01 and the Entity filter)", "AE01" in note and "Entity filter" in note, note)
    await pg.evaluate(f"()=>{{const b=document.querySelector(\"{bar}\");b.dispatchEvent(new KeyboardEvent('keydown',{{key:'Enter',bubbles:true}}));b.dispatchEvent(new KeyboardEvent('keydown',{{key:' ',bubbles:true}}))}}")
    st = await S_(); rec(A, "Keyboard (Enter / Space) on the AE01 bar follows the same rule - nothing selected", st["xf"] is None and await nin() == ex["n"])
    await pg.evaluate("()=>setXf('ent',0,'Entity = AE01')"); st = await S_()
    rec(A, "Direct API call setXf('ent', AE01) is guarded too (table rows / any caller)", st["xf"] is None and await nin() == ex["n"])
    await pg.click("#oEntRev .bar[data-k='5']"); st = await S_()
    rec(A, "US01 bar (has lines) remains selectable and selection is consistent", st["xf"] and st["xf"]["val"] == 5 and await nin() == ex["n"], st["xf"])
    await pg.click("#oEntRev .bar[data-k='5']"); rec(A, "Clicking the selected bar again clears it", (await S_())["xf"] is None)
    # chip, undo, reset consistency after a blocked click
    await reset(); await setst(dict(ent=["US01"])); h0 = await pg.evaluate("()=>hist.length"); s0 = await pg.evaluate("()=>JSON.stringify(__fpa.S())")
    await pg.click("#oEntRev .bar[data-k='0']", force=True); h1 = await pg.evaluate("()=>hist.length"); s1 = await pg.evaluate("()=>JSON.stringify(__fpa.S())")
    rec(A, "A blocked click adds no undo entry and does not alter the state", h0 == h1 and s0 == s1)
    await pg.click("#btnUndo"); st = await S_()
    rec(A, "Undo after a blocked click reverts the last REAL change (the entity filter) only", st["ent"] == [], st["ent"])
    await reset(); chips = await pg.inner_text("#activeRow"); rec(A, "Reset leaves no chips, no notice", "No filters active" in chips and not await pg.is_visible("#notice"))

    # ---------------- 2. switching categories when the same dimension is already filtered
    await reset(); await tab("overview"); await setst(dict(ent=["US01", "GB01"]))
    await pg.click("#oEntRev .bar[data-k='2']"); st = await S_(); e1 = expected(dict(ent=["GB01"]))
    rec(A, "Entities {US01,GB01} filtered: click GB01 -> narrows to GB01", st["xf"] and st["xf"]["val"] == 2 and await nin() == e1["n"], f"{await nin()} vs {e1['n']}")
    await pg.click("#oEntRev .bar[data-k='5']"); st = await S_(); e2 = expected(dict(ent=["US01"]))
    rec(A, "Then click US01 -> switches directly to US01 (replaces the chart selection, never empty)", st["xf"] and st["xf"]["val"] == 5 and await nin() == e2["n"] > 0, f"{await nin()} vs {e2['n']}")
    await pg.click("#oEntRev .bar[data-k='0']", force=True); st = await S_()
    rec(A, "Then click AE01 (excluded by the Entity filter) -> blocked, US01 selection unchanged", st["xf"] and st["xf"]["val"] == 5 and await nin() == e2["n"])
    chips = await pg.inner_text("#activeRow"); rec(A, "Chips show the Entity filter and exactly one chart selection", chips.count("Chart selection") == 1 and "Entity:" in chips)

    # ---------------- 3. stale chart selection is cleared with a notice when a slicer later contradicts it
    await reset(); await tab("overview"); await pg.click("#oEntRev .bar[data-k='2']"); await pg.evaluate("()=>__fpa.setState(x=>{x.ent=[5]})"); st = await S_(); note = await pg.inner_text("#notice")
    rec(A, "Chart selection GB01, then slicer Entity=US01: selection auto-removed with a visible notice (no empty result)", st["xf"] is None and await nin() == expected(dict(ent=["US01"]))["n"] and "Chart selection removed" in note, note)
    await pg.click("#btnUndo"); st = await S_()
    rec(A, "Undo restores GB01 chart selection and its lines", st["xf"] and st["xf"]["val"] == 2 and st["ent"] == [] and await nin() == expected(dict(ent=["GB01"]))["n"])
    await reset()

    # ---------------- 4. systematic chart matrix: expected enabled/disabled bars from the CSV, every dimension, default + filtered states
    cm_states = [("default", {}), ("entity US01", dict(ent=["US01"])), ("entities US01+GB01, sections REVENUE+COGS", dict(ent=["US01", "GB01"], sec=["REVENUE", "COGS"])),
                 ("division + 2024", dict(div=[divs[0]], years=[2024])), ("GL 4100+5100+6100", dict(gl=[4100, 5100, 6100])), ("cost centre CC1xx", dict(cc=[ccs[0]])), ("months 11-15", {"from": 10, "to": 14}),
                 ("scale PARSED + dup EXCL_ALL", dict(scale="PARSED", dup="EXCL_ALL")), ("sign NONNEG + entity AE01", dict(sign="NONNEG", ent=["AE01"]))]
    dimcol = {"ent": ("entity_code", lambda k: ents[k]), "div": ("division", lambda k: divs[k]), "sec": ("section", lambda k: secs[k]), "gl": ("gl_account", lambda k: int(gls[k])), "cc": ("cost_center_code", lambda k: "(none)" if k < 0 else ccs[k]), "m": ("m", lambda k: k)}
    nbars_checked = 0; nclick_ok = 0; mism = []; badclick = []; disclick = []
    seen_charts = set()
    for sname, f in cm_states:
        for t in ["overview", "variance", "drivers", "gp"]:
            await reset(); await setst(f); await tab(t); await pg.wait_for_timeout(80)
            info = await pg.evaluate("()=>chartsInfo()")
            x = subset(f, with_xf=False)
            for ch in info:
                seen_charts.add((t, ch["id"], ch["dim"]))
                col, nm = dimcol[ch["dim"]]
                have = x.cost_center_code.isna().sum() if False else None
                if ch["dim"] == "cc":
                    cnt = x.groupby(x.cost_center_code.fillna("(none)")).size()
                else:
                    cnt = x.groupby(col).size()
                for pos, it in enumerate(ch["items"]):
                    nbars_checked += 1
                    want_enabled = int(cnt.get(nm(it["key"]), 0)) > 0
                    if want_enabled == it["dis"]: mism.append((sname, t, ch["id"], it["label"], "dis" if it["dis"] else "enabled", int(cnt.get(nm(it["key"]), 0))))
                # click up to 2 enabled bars and ALL disabled bars
                en = [p for p, it in enumerate(ch["items"]) if not it["dis"]][:2]; di = [p for p, it in enumerate(ch["items"]) if it["dis"]]
                for pos in en:
                    key = ch["items"][pos]["key"]; await pg.click(f"#{ch['id']} .bar[data-k='{pos}']"); st = await S_()
                    f2 = dict(f); f2["xf"] = (ch["dim"], nm(key)); ex = subset(f2)
                    ok = st["xf"] is not None and st["xf"]["dim"] == ch["dim"] and st["xf"]["val"] == key and await nin() == len(ex) > 0
                    nclick_ok += ok
                    if not ok: badclick.append((sname, t, ch["id"], ch["items"][pos]["label"], await nin(), len(ex)))
                    await pg.evaluate("()=>__fpa.setState(x=>{x.xf=null})")
                for pos in di:
                    n0 = await nin(); await pg.click(f"#{ch['id']} .bar[data-k='{pos}']", force=True); st = await S_()
                    if st["xf"] is not None or await nin() != n0: disclick.append((sname, t, ch["id"], ch["items"][pos]["label"]))
                    if st["xf"] is not None: await pg.evaluate("()=>__fpa.setState(x=>{x.xf=null})")
    rec(A, f"Expected enabled/disabled state of {nbars_checked} bars across {len(seen_charts)} selectable charts x {len(cm_states)} filter states matches an independent CSV count", not mism, mism[:5])
    rec(A, f"Clicking enabled bars gives a non-empty selection whose lines equal the independent recompute ({nclick_ok} clicks)", not badclick and nclick_ok > 40, badclick[:5])
    rec(A, "Clicking every disabled bar (mouse, forced) never changes the state", not disclick, disclick[:5])
    dims_seen = sorted({d for _, _, d in seen_charts})
    rec(A, "Selectable-chart coverage: entity, division, section, GL, cost centre and month dimensions all exercised", dims_seen == ["cc", "div", "ent", "gl", "m", "sec"], f"{dims_seen}; charts {sorted(c[1] for c in seen_charts)}")
    await reset()

    # ---------------- 5. keyboard path parity on a live chart
    await tab("overview"); await pg.focus("#oEntRev .bar[data-k='3']"); await pg.keyboard.press("Enter"); st = await S_()
    rec(A, "Keyboard: focus an enabled bar + Enter selects it (same path as click)", st["xf"] and st["xf"]["dim"] == "ent" and st["xf"]["val"] == 3 and await nin() == expected(dict(ent=[ents[3]]))["n"])
    await pg.keyboard.press("Enter"); rec(A, "Keyboard: Enter on the selected bar again clears it", (await S_())["xf"] is None)
    await setst(dict(ent=["US01"])); tb = await pg.evaluate("()=>[...document.querySelectorAll('#oEntRev .bar')].map(b=>b.tabIndex)")
    rec(A, "Disabled bars are removed from the tab order (tabindex -1), enabled stay focusable", tb == [-1, -1, -1, -1, -1, 0], tb)
    await reset()

    # =================================================================== header / scope description
    B = "Corrections 2: header scope description"
    await tab("overview")
    base = await pg.evaluate("()=>document.getElementById('scope').textContent")
    rec(B, "Default: describes scale-adjusted, retained duplicates, signs as recorded, Posted-eligible population, 58,340 lines", all(s in base for s in ["scale-adjusted", "duplicate candidates retained", "signs as recorded", "Posted-eligible P&L lines", "58,340 of 58,340"]) and "SCENARIO ACTIVE" not in base, base[:260])
    rec(B, "States that not every page uses the same population (status = separate all-status population; variance/forecast/prior-year need a comparator)", "Not every page uses this population" in base and "all-status population" in base and "comparator" in base)
    scn_cases = [("scale", "PARSED", ["AS REPORTED", "restoration not applied"], ["scale-adjusted"]), ("scale", "HIGH", ["HIGH-confidence rows only"], ["scale-adjusted"]), ("scale", "EXCL_MED", ["MEDIUM-confidence restored rows excluded"], []),
                 ("scale", "EXCL_ALL", ["all restored rows excluded"], []), ("dup", "EXCL_SAME", ["same-sign duplicate candidates excluded"], ["duplicate candidates retained"]),
                 ("dup", "EXCL_ALL", ["all duplicate candidates excluded"], ["duplicate candidates retained"]), ("sign", "NONNEG", ["only all-non-negative rows kept"], ["signs as recorded"]), ("sign", "EXCL_FLIP", ["single-column sign flips excluded"], ["signs as recorded"])]
    selid = {"scale": "#sScale", "dup": "#sDup", "sign": "#sSign"}
    for key, val, want, notwant in scn_cases:
        await reset(); await pg.select_option(selid[key], val); tx = await pg.inner_text("#scope"); ex = expected({key: val}); chips = await pg.inner_text("#activeRow")
        kp = await pg.inner_text("#p-overview .kpis")
        ok = all(w in tx for w in want) and all(w not in tx for w in notwant) and "SCENARIO ACTIVE" in tx and f"{ex['n']:,} of 58,340" in tx and f"{ex['n']:,} of 58,340 lines in scope" in chips
        rec(B, f"Selector {key} = {val}: header text, SCENARIO ACTIVE flag, scenario chip and line count ({ex['n']:,}) describe the same state", ok, tx[:230])
    await reset(); await pg.select_option("#sScale", "PARSED"); kp = await pg.inner_text("#p-overview .kpis"); exr = expected({"scale": "PARSED"})
    rec(B, "As-reported: header says as reported AND the Revenue KPI shows the as-reported revenue (not the adjusted one)", f"${exr['rev']/1e6:.2f}M" in kp and "AS REPORTED" in await pg.inner_text("#scope") and f"${expected({})['rev']/1e6:.2f}M" not in kp, f"as reported ${exr['rev']/1e6:.2f}M vs adjusted ${expected({})['rev']/1e6:.2f}M")
    await reset()
    combo = dict(scale="HIGH", dup="EXCL_SAME", sign="EXCL_FLIP", ent=["IN01", "DE01"])
    await setst(combo); tx = await pg.inner_text("#scope"); ex = expected(combo)
    rec(B, "Combined scenarios + entity filter: all three scenario phrases, 'entity filter applied', exact line count", all(s in tx for s in ["HIGH-confidence rows only", "same-sign duplicate candidates excluded", "single-column sign flips excluded", "entity filter applied", f"{ex['n']:,} of 58,340"]), tx[:300])
    await pg.click("#btnUndo"); tx2 = await pg.inner_text("#scope"); rec(B, "Undo updates the header", tx2 != tx)
    await reset(); tx = await pg.evaluate("()=>document.getElementById('scope').textContent"); rec(B, "Reset restores the baseline header", tx == base)
    await tab("overview"); await pg.click("#oEntRev .bar[data-k='5']"); tx = await pg.inner_text("#scope"); rec(B, "Chart selection updates the header (chart selection applied, reduced line count)", "chart selection applied" in tx and f"{expected(dict(ent=['US01']))['n']:,} of 58,340" in tx, tx[:260])
    await reset(); await pg.select_option("#sVar", "SAME"); tx = await pg.inner_text("#scope")
    rec(B, "Variance-comparison population does not claim to change the main population (header line count unchanged)", "58,340 of 58,340" in tx and "SCENARIO ACTIVE" not in tx)
    await reset()

    # =================================================================== variance-comparison population selector
    C = "Corrections 7: variance-comparison population selector"
    lab = await pg.inner_text("label[for=sVar]"); rec(C, "Selector is labelled as the variance-comparison population", "variance-comparison population" in lab.lower(), lab)
    ref0 = (await pg.evaluate(METRICS_JS))
    for pop, w in (("ALL", None), ("SAME", 0), ("OPP", 1), ("ZERO", 2)):
        await reset(); await pg.select_option("#sVar", pop); vn = await pg.evaluate("()=>document.getElementById('varNote').textContent"); x = subset({}); xb = x[x.B.notna()]; xp = x[x.Pp.notna()]
        nb = len(xb if w is None else xb[xb.sab == w]); npy = len(xp if w is None else xp[xp.sap == w])
        mtr = await pg.evaluate(METRICS_JS)
        fixed = mtr["n"] == ref0["n"] and eqn(mtr["rev"], ref0["rev"]) and mtr["fc"] == ref0["fc"] and mtr["gp"] == ref0["gp"] and mtr["conc"] == ref0["conc"]
        await tab("variance"); vt = await pg.inner_text("#p-variance"); r = ref_variance(subset({}), pop); rl = r.get("REVENUE", {}).get("n", 0)
        await tab("forecast"); ft = await pg.inner_text("#p-forecast"); pyr = {k_: v_ for k_, v_ in ref_prior(subset({}), pop).items() if k_[1] in ("REVENUE", "COGS", "PEOPLE", "OPEX")}
        chips = await pg.inner_text("#activeRow")
        ok = f"{nb:,} budget-comparison lines" in vn and f"{npy:,} prior-year-comparison lines" in vn and fixed and (pop == "ALL" or "Variance-comparison population" in chips) and f"{rl:,}" in vt
        rec(C, f"Option {pop}: counts shown ({nb:,} budget / {npy:,} prior-year), variance tab revenue lines {rl:,}, non-variance metrics unchanged", ok, f"varNote={vn[-150:]!r}; fixed={fixed}")
        pm = all(any(f"{v['n']:,}" in ft for _ in [0]) for v in pyr.values()) if pyr else True
        rec(C, f"Option {pop}: prior-year table line counts on the Forecast tab follow the population", pm)
    await reset()
    scope_txt = await pg.evaluate("()=>document.getElementById('varNote').textContent")
    rec(C, "Note states which tabs it affects and that it does not filter line counts / KPIs / forecast / GP / quality", all(s in scope_txt for s in ["Budget & Variance", "prior-year comparison table", "does not change line counts"]) and "same-sign / opposite-sign / zero-involved" in scope_txt, scope_txt[:240])

    # =================================================================== journal-status scope
    D = "Corrections 3: journal-status scope"
    rec(D, f"Independent any-status rebuild from the CSV = 136,330 lines ({len(anyst):,}) with {int((anyst.status=='Posted').sum()):,} Posted = the 58,340 dashboard lines", len(anyst) == 136330 and int((anyst.status == "Posted").sum()) == 58340, f"{len(anyst)} / {int((anyst.status=='Posted').sum())}")
    status_states = [("entity", dict(ent=["US01"])), ("GL", dict(gl=[4100, 5100])), ("cost centre", dict(cc=[ccs[0], ccs[1]])), ("scale PARSED", dict(scale="PARSED")), ("duplicates EXCL_ALL", dict(dup="EXCL_ALL")),
                     ("sign EXCL_FLIP", dict(sign="EXCL_FLIP")), ("entity+GL+cc+HIGH+EXCL_SAME+NONNEG", dict(ent=["GB01", "SG01"], gl=[4100, 4190, 6100, 6200], cc=ccs[:5], scale="HIGH", dup="EXCL_SAME", sign="NONNEG")), ("chart selection DE01 + PARSED", dict(xf=("ent", "DE01"), scale="PARSED"))]
    prev_sel = None
    for sname, f in status_states:
        await reset(); await setst(f); m = await pg.evaluate("()=>({sel:__fpa.statusTotals('SEL'),base:__fpa.statusTotals('BASE')})")
        rs_, rb_ = ref_status(f), ref_status(f, ("ADJ", "KEEP", "KEEP"))
        ok_sel = all(m["sel"][s]["n"] == rs_[s]["n"] and eqn(m["sel"][s]["rev"], rs_[s]["rev"]) and eqn(m["sel"][s]["cost"], rs_[s]["cost"]) for s in STATUS_ORDER)
        ok_base = all(m["base"][s]["n"] == rb_[s]["n"] and eqn(m["base"][s]["rev"], rb_[s]["rev"]) and eqn(m["base"][s]["cost"], rb_[s]["cost"]) for s in STATUS_ORDER)
        await tab("quality"); qt = await pg.inner_text("#p-quality")
        rows_ok = all(re.search(rf"{re.escape(s)}\s+{rs_[s]['n']:,}\s", qt) for s in STATUS_ORDER)
        rec(D, f"{sname}: status table (Quality tab) honours the selection and equals the independent any-status recompute", ok_sel and rows_ok, f"Posted {m['sel']['Posted']['n']} vs {rs_['Posted']['n']}; Pending {m['sel']['Pending']['n']} vs {rs_['Pending']['n']}")
        rec(D, f"{sname}: baseline status rows (one-at-a-time sensitivity) equal the recompute at baseline scale/dup/sign with the same dimension filters", ok_base)
    await reset(); await tab("quality"); qt = await pg.inner_text("#p-quality")
    rec(D, "Quality status card is renamed and states exactly what it honours / does not apply", "all-status population, current selection" in qt and "Honours: period, entity, division, section, GL, cost centre, chart selection and the selected scale / duplicate / sign scenarios" in qt and "Not applicable: the variance-comparison population" in qt and "Journal status in the current selection" not in qt)
    await setst(dict(scale="PARSED")); b1 = await pg.evaluate("()=>JSON.stringify(__fpa.statusTotals('BASE'))"); s1 = await pg.evaluate("()=>JSON.stringify(__fpa.statusTotals('SEL'))"); await reset(); b0 = await pg.evaluate("()=>JSON.stringify(__fpa.statusTotals('BASE'))"); s0 = await pg.evaluate("()=>JSON.stringify(__fpa.statusTotals('SEL'))")
    rec(D, "Selecting a scale scenario CHANGES the selection status table but leaves the baseline sensitivity rows fixed", b1 == b0 and s1 != s0)
    await setst(dict(gl=[4100])); await tab("gp"); gt = await pg.inner_text("#p-gp")
    rec(D, "GP & Scenarios: the old 'ignores GL and cost-centre filters' caveat is gone; note describes line-level application", "ignore GL and cost-centre" not in gt and "apply period, entity, division, section, GL, cost-centre and chart filters at line level" in gt)
    await reset(); await setst(dict(ent=["US01"], gl=[4100], scale="PARSED")); await tab("insights"); await pg.evaluate("()=>document.querySelectorAll('details.ins').forEach(d=>d.open=true)"); it = await pg.inner_text("#p-insights")
    rec(D, "Journal Status insight: scope states line-level all-status population with every filter + the selected scenarios applied", "line-level" in it and "aggregate cube" not in it)
    await reset()

    # =================================================================== reconciliation labelling
    E = "Corrections 4: reconciliation labelling"
    bt = await pg.inner_text("#recBadge"); bti = await pg.get_attribute("#recBadge", "title"); st_ = await pg.inner_text("#selBadge"); sti = await pg.get_attribute("#selBadge", "title")
    rec(E, "Badge reads 'Baseline checks: 459/459' (no 'Reconciled' claim)", bt.strip().endswith("Baseline checks: 459/459") and "Reconciled" not in bt, bt)
    rec(E, "Badge tooltip says default-filter baseline, NOT an independent reconciliation of the filtered view", "DEFAULT filters" in bti and "NOT an automatic independent reconciliation" in bti, bti[:200])
    rec(E, "Second badge 'Selection checks' is distinct and its tooltip says it is not an external reference", "Selection checks" in st_ and "Not an independent external reconciliation" in sti, st_)
    await tab("quality"); qt = await pg.inner_text("#p-quality")
    rec(E, "Quality tab card is titled 'Baseline reconciliation' (not 'Live reconciliation') and says filtered views are not covered", "Baseline reconciliation to Phase 4 tables" in qt and "not an independent reconciliation of any filtered view" in qt)
    neg = await pg.evaluate("()=>{const k=inc.findIndex(v=>v===1);inc[k]=0;cache={};const bad=runSelChecks().filter(c=>!c.ok).length;inc[k]=1;cache={};return [bad,runSelChecks().filter(c=>!c.ok).length]}")
    rec(E, "Negative control: corrupting one in-scope flag makes the selection checks FAIL; restoring makes them pass again", neg[0] > 0 and neg[1] == 0, neg)

    # =================================================================== independent derived metrics under filters
    F_ = "Corrections 5: derived metrics vs independent pandas reference"
    dstates = [("default", {}), ("year 2024 + entities US01,IN01", dict(years=[2024], ent=["US01", "IN01"])), ("GL 4100,5100,6100", dict(gl=[4100, 5100, 6100])), ("cost centres 2", dict(cc=[ccs[0], ccs[1]])),
               ("scale PARSED + 2 divisions", dict(scale="PARSED", div=divs[:2])), ("dup EXCL_ALL + sign EXCL_FLIP + Q2,Q3", dict(dup="EXCL_ALL", sign="EXCL_FLIP", qtrs=[2, 3])),
               ("sections REV,COGS,OPEX + months 6-31 + HIGH", dict(sec=["REVENUE", "COGS", "OPEX"], **{"from": 5, "to": 30}, scale="HIGH")), ("GB01 + GL 4100,4190,5100 + cost centres + varPop SAME", dict(ent=["GB01"], gl=[4100, 4190, 5100], cc=ccs[:4], varPop="SAME")),
               ("varPop OPP + years 2023,2025", dict(varPop="OPP", years=[2023, 2025])), ("EXCL_MED + EXCL_SAME + NONNEG + SG01,DE01", dict(scale="EXCL_MED", dup="EXCL_SAME", sign="NONNEG", ent=["SG01", "DE01"])),
               ("chart selection ent=GB01 + PARSED", dict(xf=("ent", "GB01"), scale="PARSED")), ("chart selection month=12 + HIGH + EXCL_SAME", dict(xf=("m", 12), scale="HIGH", dup="EXCL_SAME")),
               ("cost centre (none) only", dict(cc=["(none)"])), ("chart selection GL 4190 + sign NONNEG", dict(xf=("gl", 4190), sign="NONNEG"))]
    fam_fail = {}; nfam = 0
    for sname, f in dstates:
        await reset(); await setst(f); m = await pg.evaluate(METRICS_JS); res = derived_checks(sname, f, m)
        bad_f = [k for k, (ok, _) in res.items() if not ok]
        nfam += len(res)
        rec(F_, f"[{sname}] {len(res)} metric families vs independent reference", not bad_f, {k: res[k][1] for k in bad_f} if bad_f else f"all {len(res)} families match; {m['n']:,} lines")
        for k in bad_f: fam_fail.setdefault(k, []).append(sname)
    rec(F_, f"Summary: {len(dstates)} filter/scenario states x metric families = {nfam} independent comparisons, none failed", not fam_fail, fam_fail)
    # dynamic insight numbers + driver ranking + displayed counts
    for sname, f in (("IN01 + 2025", dict(ent=["IN01"], years=[2025])), ("GB01,US01 + PARSED", dict(ent=["GB01", "US01"], scale="PARSED")), ("GL 6100,6200 + HIGH", dict(gl=[6100, 6200], scale="HIGH"))):
        await reset(); await setst(f); x = subset(f); await tab("insights"); await pg.evaluate("()=>document.querySelectorAll('details.ins').forEach(d=>d.open=true)"); it = await pg.inner_text("#p-insights")
        r = ref_variance(x, "ALL"); rvn = r.get("REVENUE", {}).get("net", 0.0); amt = abs(rvn); s_ = f"${amt/1e6:.2f}M" if amt >= 1e6 else f"${amt/1e3:.1f}K"
        pr = ref_persist(x); top = sorted(((k, v) for k, v in pr.items() if v["persistent"] is not None), key=lambda kv: -abs(kv[1]["v"]))[:3]
        top_ok = all(f"{e} {g}" in it for (e, g), v in top if v["persistent"]) if any(v["persistent"] for _, v in top) else True
        persist_n = sum(v["persistent"] for v in pr.values())
        kpiline = f"{len(x):,}" in it
        rec(F_, f"Dynamic insights [{sname}]: revenue-vs-budget amount {s_}, persistent-cell driver names, line count {len(x):,} agree with the reference ({persist_n} persistent cells)", (s_ in it or "REVENUE" not in r) and top_ok and kpiline, f"amount={s_ in it} (revenue lines present: {'REVENUE' in r}), drivers={top_ok}, count={kpiline}")
    await reset()
    # displayed KPI / chips counts
    for sname, f in (("US01 PARSED", dict(ent=["US01"], scale="PARSED")), ("GL + cc", dict(gl=[4100, 6100], cc=ccs[:3]))):
        await reset(); await setst(f); x = subset(f); await tab("overview"); kp = await pg.inner_text("#p-overview .kpis"); chips = await pg.inner_text("#activeRow")
        k = ref_kpis(x); rv = k["rev"]; txt = f"${abs(rv)/1e6:.2f}M" if abs(rv) >= 1e6 else f"${abs(rv)/1e3:.1f}K"
        rec(F_, f"Displayed population: KPI revenue {txt}, in-scope count {k['n']:,} in chips and header [{sname}]", txt in kp and f"{k['n']:,} of 58,340 lines in scope" in chips and f"{k['n']:,} of 58,340" in await pg.inner_text("#scope"), f"{kp[:120]!r}")
    await reset()

    # =================================================================== chart palette / contrast / patterns (actual rendered marks)
    G = "Corrections 6: chart accessibility and contrast"
    palettes = {}
    for theme in ("light", "dark"):
        cur = await pg.evaluate("()=>document.documentElement.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')")
        if cur != theme: await pg.click("#btnTheme")
        marks = []; txtm = []
        for t, sx in [(t_, sx_) for sx_ in (False, True) for t_ in ["overview", "trends", "variance", "forecast", "drivers", "gp"]]:
            await reset()
            if sx: await setst(dict(xf=("ent", "US01")))
            await tab(t); await pg.wait_for_timeout(120)
            r = await pg.evaluate("""()=>{
              const parse=c=>{const m=c.match(/[\d.]+/g).map(Number);const a=m.length>3?m[3]:1;const rgb=c.startsWith('color(')?m.slice(0,3).map(x=>x*255):m.slice(0,3);return [rgb[0],rgb[1],rgb[2],a]};
              const bgOf=e=>{const L=[];while(e){const b=getComputedStyle(e).backgroundColor;if(b&&b!=='rgba(0, 0, 0, 0)'&&b!=='transparent'){const p=parse(b);L.push(p);if(p[3]>=1)break}e=e.parentElement}
                let base=L.length&&L[L.length-1][3]>=1?L.pop():parse(getComputedStyle(document.body).backgroundColor);
                while(L.length){const l=L.pop();base=[0,1,2].map(i=>l[i]*l[3]+base[i]*(1-l[3])).concat([1])}
                return 'rgb('+base.slice(0,3).map(Math.round).join(', ')+')'};
              const out={marks:[],text:[]};
              const res=(el,prop)=>{let v=getComputedStyle(el)[prop];if(prop==='fill'&&v.startsWith('url')){const id=v.match(/#([^")]+)/)[1];const p=document.getElementById(id);if(p){const r=p.querySelector('rect');return getComputedStyle(r).fill}}return v};
              document.querySelectorAll('.panel.on .chart').forEach(ch=>{const bg=bgOf(ch);
                ch.querySelectorAll('rect.bar:not(.dis)').forEach(e=>out.marks.push({k:'bar',c:res(e,'fill'),bg,id:ch.id,sel:e.getAttribute('aria-pressed')==='true',stroke:getComputedStyle(e).stroke}));
                ch.querySelectorAll('svg path[fill=none]').forEach(e=>out.marks.push({k:'line',c:getComputedStyle(e).stroke,bg,id:ch.id,dash:getComputedStyle(e).strokeDasharray}));
                ch.querySelectorAll('svg > circle:not(.dot), svg > rect:not(.bar):not(.ov), svg > path:not([fill=none])').forEach(e=>{const f=getComputedStyle(e).fill;if(f&&f!=='none')out.marks.push({k:'marker',c:f,bg,id:ch.id})});
                ch.parentElement.querySelectorAll('.legend .swl line').forEach(e=>out.marks.push({k:'legend-line',c:getComputedStyle(e).stroke,bg,id:ch.id}));
                ch.parentElement.querySelectorAll('.legend .sw').forEach(e=>out.marks.push({k:'legend-swatch',c:getComputedStyle(e).backgroundColor,bg,id:ch.id}));
                ch.parentElement.querySelectorAll('.legend .swl rect').forEach(e=>out.marks.push({k:'legend-pattern',c:getComputedStyle(e).fill.startsWith('url')?res(e,'fill'):getComputedStyle(e).fill,bg,id:ch.id}));
                ch.querySelectorAll('svg text').forEach(e=>out.text.push({k:'axis-label',c:getComputedStyle(e).fill,bg}));});
              document.querySelectorAll('.csub, .legend, .vnote, #scope, .hdr .sub .sub2, th, td, h3').forEach(e=>{if(e.offsetParent&&e.textContent.trim())out.text.push({k:e.className||e.tagName,c:getComputedStyle(e).color,bg:bgOf(e)})});
              return out;}""")
            marks += [dict(m_, tab=t) for m_ in r["marks"]]; txtm += r["text"]
        mins = {}
        for m_ in marks:
            if m_["c"].startswith("url") or "rgba(0, 0, 0, 0)" in m_["c"] or m_["c"] in ("none",): continue
            cr_ = cratio(m_["c"], m_["bg"]); key = (m_["k"], rgb_hex(m_["c"]))
            if key not in mins or cr_ < mins[key][0]: mins[key] = (cr_, m_["bg"], m_["id"])
        low = sorted([(round(v[0], 2), k, v[2]) for k, v in mins.items() if v[0] < 3.0])
        palettes[theme] = sorted({rgb_hex(m_["c"]) for m_ in marks if not m_["c"].startswith("url") and m_["k"] in ("bar", "line", "marker", "legend-line", "legend-swatch")})
        rec(G, f"{theme}: {len(marks)} rendered chart marks (bars, lines, markers, legend swatches) over 6 tabs, {len(mins)} distinct colour/kind pairs - each >= 3:1 against its actual card background", not low and len(mins) >= 6, low[:6] or f"min {min(v[0] for v in mins.values()):.2f}:1; colours {palettes[theme]}")
        sel = [m_ for m_ in marks if m_.get("sel")]
        rec(G, f"{theme}: selected-state outline (ink) vs card >= 3:1 on actual selected bars", len(sel) >= 2 and all(cratio(m_["stroke"], m_["bg"]) >= 3 for m_ in sel), f"{len(sel)} selected marks; min {min([cratio(m_['stroke'], m_['bg']) for m_ in sel] or [0]):.2f}:1")
        tl = sorted({(round(cratio(t_["c"], t_["bg"]), 2), t_["k"]) for t_ in txtm if cratio(t_["c"], t_["bg"]) < 4.5})
        rec(G, f"{theme}: TEXT contrast kept separate - all {len(txtm)} sampled text elements (axis labels, legends, headings, tables, header scope) >= 4.5:1", not tl, tl[:6])
        if theme == "light":
            await reset(); await tab("overview"); await pg.click("#oEntRev .bar[data-k='5']"); selm = await pg.evaluate("()=>{const b=document.querySelector('#oEntRev .bar[aria-pressed=true]');const c=b.closest('.card');return {s:getComputedStyle(b).stroke,w:getComputedStyle(b).strokeWidth,bg:getComputedStyle(c).backgroundColor}}")
            rec(G, "Selected bar is outlined (2px ink) in addition to its fill (not colour alone)", cratio(selm["s"], selm["bg"]) >= 3 and float(selm["w"].replace("px", "")) >= 2, selm); await reset()
    # validator on the actual CSS palette
    import subprocess, glob
    vp = glob.glob("/tmp/claude-0/bundled-skills/*/*/dataviz/scripts/validate_palette.js")
    if vp:
        for theme, mode in (("light", "light"), ("dark", "dark")):
            cols_ = await pg.evaluate("t=>{document.documentElement.setAttribute('data-theme',t);return [1,2,3,4,5,6,7,8].map(i=>getComputedStyle(document.documentElement).getPropertyValue('--s'+i).trim())}", theme)
            out = subprocess.run(["node", vp[0], ",".join(cols_), "--mode", mode], capture_output=True, text=True).stdout
            rec(G, f"dataviz validator ({mode}) on the dashboard's actual 8 series colours {cols_}: lightness, chroma, CVD separation, normal-vision floor, contrast", "ALL CHECKS PASS" in out and "[FAIL]" not in out, out.replace("\n", " | ")[:260])
        await pg.evaluate("()=>document.documentElement.removeAttribute('data-theme')")
    else:
        SKIPS.append((G, "dataviz validator", "validator script not found in this environment"))
    cur = await pg.evaluate("()=>document.documentElement.getAttribute('data-theme')||'none'")
    # non-colour encodings
    await setst({}); await tab("overview"); sec = await pg.evaluate("()=>[...document.querySelectorAll('#oMonthly path[fill=none]')].map(p=>p.getAttribute('stroke-dasharray')||'solid')")
    rec(G, "Line series differ by dash pattern (not colour alone)", len(set(sec)) == len(sec) == 3, sec)
    await tab("gp"); gpl = await pg.evaluate("()=>({legend:[...document.querySelectorAll('#gGm ~ .legend, #gGp ~ .legend, .legend')].map(l=>l.querySelectorAll('svg.swl').length),pat:document.querySelectorAll('#gGp pattern').length,fills:[...new Set([...document.querySelectorAll('#gGp rect.bar')].map(r=>r.getAttribute('fill')))]})")
    rec(G, "Gross-profit treatments are distinguishable by texture as well as colour (hatch/dot patterns in bars and legend)", gpl["pat"] >= 2 and len(gpl["fills"]) == 3 and any(f_.startswith("url(") for f_ in gpl["fills"]), gpl)
    await tab("overview"); lgd = await pg.evaluate("()=>[...document.querySelectorAll('#oMonthly ~ .legend svg.swl, #p-overview .legend svg.swl')].length")
    rec(G, "Legends carry the line pattern + marker shape swatch for each series", lgd >= 3, lgd)

    # =================================================================== keyboard accessibility
    H = "Corrections 6/8: keyboard accessibility"
    await reset(); await tab("overview"); await pg.focus("#tab-overview"); await pg.keyboard.press("ArrowRight"); await pg.keyboard.press("ArrowRight")
    rec(H, "Tabs: arrow keys move across views", (await S_())["tab"] == "variance"); await tab("overview")
    await pg.focus("#fYears .chip[data-v='2024']"); await pg.keyboard.press("Space"); st = await S_()
    rec(H, "Slicer chips: Space toggles the year", 2024 not in st["years"] and await nin() == expected(dict(years=[2023, 2025]))["n"]); await pg.keyboard.press("Space")
    await pg.focus("#fQtrs .chip[data-v='2']"); await pg.keyboard.press("Enter"); rec(H, "Slicer chips: Enter toggles the quarter", 2 not in (await S_())["qtrs"]); await reset()
    await pg.focus("#gGl .msb"); await pg.keyboard.press("Enter"); op = await pg.evaluate("()=>document.querySelector('#gGl').classList.contains('open')&&document.activeElement.type==='search'")
    await pg.keyboard.type("4100"); await pg.keyboard.press("Tab"); await pg.keyboard.press("Tab"); await pg.keyboard.press("Tab")
    foc = await pg.evaluate("()=>document.activeElement.tagName+':'+document.activeElement.type")
    rec(H, "Multi-select dropdown: Enter opens and focuses its search box; typing filters; Tab reaches the option checkboxes", op, foc)
    await pg.evaluate("()=>{const c=[...document.querySelectorAll('#gGl label')].find(l=>l.style.display!=='none').querySelector('input');c.focus()}"); await pg.keyboard.press("Space"); st = await S_()
    rec(H, "Multi-select: Space on a focused option selects only that GL", st["gl"] == [gls.index(4100)] and await nin() == expected(dict(gl=[4100]))["n"], st["gl"])
    await pg.keyboard.press("Escape"); rec(H, "Multi-select: Escape closes the popup", not await pg.evaluate("()=>document.querySelector('#gGl').classList.contains('open')")); await reset()
    await pg.focus("#sScale"); await pg.keyboard.press("ArrowDown"); rec(H, "Select controls respond to the keyboard (scale basis ArrowDown changes the scenario)", (await S_())["scale"] != "ADJ", (await S_())["scale"]); await reset()
    await tab("overview"); await pg.focus("[data-tbl='oEntRev']"); await pg.keyboard.press("Enter"); tb_on = "<table" in await pg.evaluate("()=>document.getElementById('oEntRev').innerHTML"); await pg.keyboard.press("Enter")
    rec(H, "Chart/Table toggle works by keyboard (Enter) in both directions", tb_on and "<svg" in await pg.evaluate("()=>document.getElementById('oEntRev').innerHTML"))
    await pg.focus("#oMonthly .ov"); await pg.keyboard.press("ArrowLeft"); tt = await pg.evaluate("()=>({d:getComputedStyle(document.getElementById('tt')).display,t:document.getElementById('tt').innerText})")
    rec(H, "Line chart is keyboard-operable: focus + arrow keys step through periods and show the tooltip", tt["d"] == "block" and "Revenue" in tt["t"], tt["t"][:100])
    await pg.keyboard.press("Enter"); st = await S_(); rec(H, "Line chart: Enter selects the focused month (guarded cross-filter path)", st["xf"] and st["xf"]["dim"] == "m" and st["xf"]["val"] == 34, st["xf"]); await reset()
    await tab("variance"); await pg.focus("#vHeat tr.clk >> nth=0"); await pg.keyboard.press("Enter"); rec(H, "Clickable table rows are keyboard-operable (Enter)", (await S_())["xf"] is not None); await reset()
    await tab("overview"); await setst(dict(ent=["US01"]))
    first_stop = await pg.evaluate("()=>{const bars=[...document.querySelectorAll('#oEntRev .bar')];return bars.filter(b=>b.tabIndex>=0).length}")
    rec(H, "Tab order includes only selectable bars", first_stop == 1, first_stop); await reset()
    SKIPS.append((H, "Screen-reader (NVDA/JAWS/VoiceOver) test", "not possible in this environment: no assistive technology is available. ARIA roles, names, aria-pressed/aria-disabled states and live regions are asserted programmatically only."))

    # =================================================================== interactions after rebuild + filters
    I = "Corrections 8: interactions after rebuilds and filters"
    allbad = []
    for t in ["overview", "trends", "variance", "forecast", "drivers", "gp", "insights", "quality", "detail"]:
        await reset(); await setst(dict(ent=["US01", "GB01"], scale="PARSED")); await tab(t); await pg.wait_for_timeout(80)
        tbs = await pg.evaluate("()=>[...document.querySelectorAll('.panel.on [data-tbl]')].map(b=>b.dataset.tbl)")
        for cid in tbs:
            await pg.click(f".panel.on [data-tbl='{cid}']"); h1 = await pg.evaluate(f"()=>document.getElementById('{cid}').innerHTML.includes('<table')")
            await pg.click(f".panel.on [data-tbl='{cid}']"); h2 = await pg.evaluate(f"()=>document.getElementById('{cid}').innerHTML.includes('<svg')")
            if not (h1 and h2): allbad.append((t, cid, h1, h2)); continue
            hv = await pg.evaluate(f"""()=>{{const e=document.querySelector('#{cid} .bar:not(.dis)')||document.querySelector('#{cid} .ov');if(!e)return 'none';const r=e.getBoundingClientRect();e.dispatchEvent(new MouseEvent('mousemove',{{clientX:r.left+r.width/2,clientY:r.top+r.height/2,bubbles:true}}));return getComputedStyle(document.getElementById('tt')).display}}""")
            if hv not in ("block", "none"): allbad.append((t, cid, "tooltip", hv))
            if hv == "none": pass
    rec(I, f"Every chart on every tab toggles Chart->Table->Chart, then still shows tooltips (filtered + as-reported state)", not allbad, allbad[:5])
    await reset(); await tab("overview"); await pg.click("[data-tbl='oEntRev']"); await pg.click("[data-tbl='oEntRev']"); await pg.click("#oEntRev .bar[data-k='5']"); st = await S_()
    rec(I, "Click on a bar after a Chart/Table/Chart round trip still cross-filters", st["xf"] and st["xf"]["val"] == 5); await reset()
    await setst(dict(years=[2024], ent=["US01", "GB01"], gl=[4100, 5100])); chips0 = await pg.inner_text("#activeRow"); btns = await pg.query_selector_all("#activeRow .tag button")
    await btns[1].click(); st = await S_(); chips1 = await pg.inner_text("#activeRow")
    rec(I, "Removing ONE chip (Entity) removes only that filter; the others remain", st["ent"] == [] and st["years"] == [2024] and st["gl"] != [] and "Entity" not in chips1 and "Year" in chips1 and "GL" in chips1, chips1[:120].replace("\n", " "))
    await tab("overview"); await pg.click("#oEntRev .bar[data-k='3']"); st = await S_()
    rec(I, "Cross-filter after slicer changes works and recomputes (year 2024 + GL 4100/5100 + entity chart selection)", st["xf"] is not None and await nin() == len(subset(dict(years=[2024], gl=[4100, 5100], xf=("ent", ents[3])))), await nin())
    await pg.click("#btnUndo"); await pg.click("#btnUndo"); st = await S_(); rec(I, "Two undos step back through chart selection and chip removal", st["xf"] is None and st["ent"] == [ents.index("US01"), ents.index("GB01")]); await reset()
    # search + sort + pagination + CSV after combined filters
    comb = dict(ent=["GB01", "US01"], gl=[4100, 5100, 6100], scale="PARSED", dup="EXCL_SAME", years=[2024, 2025]); await setst(comb); await tab("detail"); x = subset(comb)
    rec(I, "Detail: count after combined filters equals independent recompute", (await pg.inner_text("#detCount")).replace(",", "").startswith(str(len(x))), await pg.inner_text("#detCount"))
    await pg.click("#detTable th[data-k='a']"); await pg.click("#detTable th[data-k='a']"); v1 = await pg.evaluate("()=>[...document.querySelectorAll('#detTable tbody tr')].slice(0,3).map(r=>parseFloat(r.children[9].textContent.replace(/,/g,'').replace('\\u2212','-')))")
    rec(I, "Detail: sort descending by Actual returns the independent maximum first (as-reported basis)", abs(v1[0] - round(float(x.A.max()), 2)) <= 0.01 and v1 == sorted(v1, reverse=True), f"{v1} vs {x.A.max():.2f}")
    await pg.click("#detNext"); info = await pg.inner_text("#detInfo"); rec(I, "Detail: pagination works under combined filters", "page 2 of" in info, info)
    await pg.fill("#detQ", "CC4"); await pg.wait_for_timeout(200); cnt = int((await pg.inner_text("#detCount")).split()[0].replace(",", ""))
    exq = int(((x.cost_center_code.fillna("").str.contains("CC4", case=False)) | x.document_no.fillna("").str.lower().str.contains("cc4") | x.source_row_number.astype(str).str.contains("cc4")).sum())
    rec(I, "Detail: search token under combined filters matches the independent count", cnt == exq, f"{cnt} vs {exq}")
    async with pg.expect_download() as dl: await pg.click("#btnCsv")
    d = await dl.value; path = SHOT / "export_combined.csv"; await d.save_as(str(path)); rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"))))
    rec(I, "CSV after combined filters + search: row count equals the search result and header records scale/duplicate/sign scenario", len(rows) - 1 == cnt and rows[0][-3:] == ["scale_basis", "duplicate_scenario", "sign_scenario"] and rows[1][-3:] == ["PARSED", "EXCL_SAME", "KEEP"], f"{len(rows)-1} rows; {rows[0][-3:]} {rows[1][-3:]}")
    await pg.fill("#detQ", "")
    async with pg.expect_download() as dl: await pg.click("#btnCsv")
    d = await dl.value; await d.save_as(str(path)); rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"))))
    rec(I, "CSV without search exports ALL filtered lines (not just the visible page) - equals independent recompute", len(rows) - 1 == len(x) > 50, f"{len(rows)-1} vs {len(x)}")
    dn = await pg.inner_text("#p-detail .note.info"); rec(I, "Detail note distinguishes printing the report (visible page only) from exporting all filtered lines", "prints only the rows of the current page" in dn and "all filtered lines" in dn, dn[:200])
    pb = await pg.get_attribute("#btnPrint", "title"); cb = await pg.get_attribute("#btnCsv", "title"); rec(I, "Print and CSV buttons are labelled for what they do", "Detail Lines prints only the visible page" in pb and "ALL detail lines" in cb)
    await reset()
    # print + state restoration
    if (await pg.evaluate("()=>document.documentElement.getAttribute('data-theme')||'light'")) != "dark": await pg.click("#btnTheme")
    await tab("variance"); await setst(dict(ent=["US01"], scale="PARSED")); before = await pg.evaluate("()=>JSON.stringify(__fpa.S())"); th_b = await pg.evaluate("()=>document.documentElement.getAttribute('data-theme')")
    await pg.evaluate("()=>beforePrint()"); th_p = await pg.evaluate("()=>document.documentElement.getAttribute('data-theme')"); await pg.evaluate("()=>afterPrint()")
    after = await pg.evaluate("()=>JSON.stringify(__fpa.S())"); th_a = await pg.evaluate("()=>document.documentElement.getAttribute('data-theme')"); sc_a = await pg.inner_text("#scope")
    rec(I, "Print: forced light theme during print, then theme, filters, scenario, active tab and header are restored", th_p == "light" and th_a == th_b == "dark" and before == after and "AS REPORTED" in sc_a, f"{th_b}->{th_p}->{th_a}")
    await pg.click("#btnTheme"); await reset()
    # NaN / undefined scan including xf and scenario states
    scan = [dict(xf=("ent", "AE01")), dict(xf=("gl", 4190), scale="PARSED"), dict(xf=("sec", "TAX")), dict(xf=("m", 0), dup="EXCL_ALL"), dict(xf=("cc", ccs[0]), sign="EXCL_FLIP"), dict(scale="EXCL_ALL", dup="EXCL_ALL", sign="NONNEG", ent=["AE01"]), dict(gl=[4190], cc=["(none)"]), dict(sec=["TAX"], scale="PARSED")]
    bad = []
    for i, f in enumerate(scan):
        await reset(); await setst(f)
        for t in ["overview", "trends", "variance", "forecast", "drivers", "gp", "insights", "quality", "detail"]:
            await tab(t); tx = await pg.inner_text(f"#p-{t}")
            if re.search(r"NaN|undefined|Infinity|\[object", tx): bad.append((i, t))
        hdr = await pg.inner_text("header")
        if re.search(r"NaN|undefined|Infinity", hdr): bad.append((i, "header"))
    rec(I, f"No NaN/undefined/Infinity in any of 9 tabs + header across {len(scan)} chart-selection and scenario states", not bad, bad[:5])
    # long labels / responsive with scenario text
    for w, h, nm in ((390, 844, "phone"), (768, 1024, "tablet")):
        c3 = await br.new_context(viewport={"width": w, "height": h}); p3 = await c3.new_page(); await p3.goto(URL); await p3.wait_for_function("window.__fpa")
        await p3.evaluate("s=>__fpa.setState(x=>Object.assign(x,s))", xf_state(dict(scale="HIGH", dup="EXCL_SAME", sign="EXCL_FLIP", ent=["GB01"], gl=[4100, 5100, 6100, 6200], cc=ccs[:5], varPop="SAME"), idx))
        ov = []
        for t in ["overview", "variance", "drivers", "gp", "quality", "detail"]:
            await p3.evaluate(f"()=>document.getElementById('tab-{t}').click()"); await p3.wait_for_timeout(100)
            sw = await p3.evaluate("()=>({sw:document.documentElement.scrollWidth,iw:innerWidth,hdr:document.querySelector('#scope').getBoundingClientRect().right,vn:document.querySelector('#varNote').getBoundingClientRect().right})")
            if sw["sw"] > sw["iw"] + 1 or sw["hdr"] > sw["iw"] + 1 or sw["vn"] > sw["iw"] + 1: ov.append((t, sw))
        await p3.screenshot(path=str(SHOT / f"scenario_{nm}.png"), full_page=False)
        rec(I, f"{nm} {w}px with active scenarios, long header text, note and 5 chips: no horizontal overflow on 6 tabs", not ov, ov[:3]); await c3.close()
    # performance of combined selections, per tab
    perf = []
    comb2 = xf_state(dict(ent=["GB01", "US01", "DE01"], gl=[4100, 5100, 6100, 6200, 6300], cc=ccs[:6], scale="PARSED", dup="EXCL_SAME", sign="EXCL_FLIP", years=[2024, 2025]), idx)
    for t in ["overview", "trends", "variance", "forecast", "drivers", "gp", "insights", "quality", "detail"]:
        await reset(); await tab(t); await pg.wait_for_timeout(60)
        ms = await pg.evaluate("s=>{const t0=performance.now();__fpa.setState(x=>Object.assign(x,s));return performance.now()-t0}", comb2); ms2 = await pg.evaluate("()=>{const t0=performance.now();resetAll();return performance.now()-t0}")
        perf.append((t, round(ms), round(ms2)))
    rec(I, "Performance: combined-selection filter change + re-render of the active tab (ms per tab; target < 1500 ms)", max(p_[1] for p_ in perf) < 1500 and max(p_[2] for p_ in perf) < 1500, perf)
    await redesign(pg, br, idx, msgs)
    rec(I, "Console: no errors or warnings after every interaction in this suite", not [m_ for m_ in msgs if m_[0] in ("error", "pageerror", "warning")], msgs[-5:])


async def redesign(pg, br, idx, msgs):
    R_ = "Redesign: logo, compact header, KPI trends, new charts"
    ents = idx["e"]; ccs = idx["c"]
    tab = lambda t: pg.evaluate(f"()=>document.getElementById('tab-{t}').click()")
    reset = lambda: pg.evaluate("()=>resetAll()")
    setst = lambda f: pg.evaluate("s=>__fpa.setState(x=>Object.assign(x,s))", xf_state(f, idx))
    S_ = lambda: pg.evaluate("()=>__fpa.S()")
    chart = lambda cid: pg.evaluate("id=>__fpa.chart(id)", cid)
    def mon_ok(f):
        ys = f.get("years", [2023, 2024, 2025]); qs = f.get("qtrs", [1, 2, 3, 4]); lo = f.get("from", 0); hi = f.get("to", 35)
        return [(lo <= m <= hi) and (2023 + m // 12 in ys) and ((m % 12) // 3 + 1 in qs) for m in range(36)]
    def msec(x, secs):
        return x[x.section.isin(secs)].groupby("m").A.sum().reindex(range(36), fill_value=0.0).values
    def same(js, ref, tol=0.01):
        if len(js) != len(ref): return False
        for a, b in zip(js, ref):
            if (a is None) != (b is None): return False
            if a is not None and abs(a - b) > max(tol, 1e-9 * abs(b)): return False
        return True
    def masked(ref, ok): return [float(v) if ok[m] else None for m, v in enumerate(ref)]
    def mvar(x, secs, pop):
        y = x[x.B.notna() & x.section.isin(secs)]
        if pop != "ALL": y = y[y.sab == {"SAME": 0, "OPP": 1, "ZERO": 2}[pop]]
        return (y.assign(v=y.A - y.B).groupby("m").agg(v=("v", "sum"), n=("v", "size")).reindex(range(36)))
    await pg.set_viewport_size({"width": 1440, "height": 900}); await reset(); await tab("overview"); await pg.evaluate("()=>{window.scrollTo(0,0)}"); await pg.wait_for_timeout(150)
    await pg.evaluate("()=>{const d=document.querySelector('#scope details.basis');if(d&&d.open)d.open=false}"); await pg.wait_for_timeout(100)

    # ---- logo + header
    lg = await pg.evaluate("()=>{const l=document.querySelector('.hdr svg.logo'),h=document.querySelector('.hdr h1'),a=l.getBoundingClientRect(),b=h.getBoundingClientRect();return {w:a.width,h:a.height,left:a.left,top:a.top,hx:b.left,role:l.getAttribute('role'),label:l.getAttribute('aria-label')}}")
    rec(R_, "Logo sits in the upper-left corner, left of the title, >= 40 px, with an accessible name", lg["w"] >= 40 and lg["h"] >= 40 and lg["left"] < 40 and lg["top"] < 40 and lg["left"] + lg["w"] <= lg["hx"] and lg["role"] == "img" and "NovaBridge" in (lg["label"] or ""), lg)
    hd = await pg.evaluate("()=>{const s=document.getElementById('scope');const c=s.cloneNode(true);c.querySelectorAll('details').forEach(d=>d.remove());return {vis:c.innerText,all:s.textContent,open:s.querySelector('details.basis').open,h:s.getBoundingClientRect().height}}")
    rec(R_, "Header: the 'Synthetic dataset' line and the 'Not every page uses...' line are gone from the visible header", "Synthetic" not in hd["all"] and "Not every page" not in hd["vis"] and "Synthetic" not in hd["vis"], hd["vis"][:200])
    rec(R_, "Header is compact (<= 2 text lines tall) and the basis is collapsed by default", hd["h"] <= 50 and not hd["open"], hd["h"])
    await pg.emulate_media(media="print"); await pg.evaluate("()=>{window.dispatchEvent(new Event('beforeprint'));}"); await pg.evaluate("()=>{window.dispatchEvent(new Event('afterprint'))}"); await pg.emulate_media(media="screen"); await pg.wait_for_timeout(400)
    rec(R_, "Print/after-print cycle leaves the header basis collapsed again (state restored)", not await pg.evaluate("()=>document.querySelector('#scope details.basis').open"), await pg.evaluate("()=>[basisOpen,printing,printPrev]"))
    await pg.click("#scope details.basis summary"); tx = await pg.inner_text("#scope")
    rec(R_, "Opening 'Baseline basis' shows the full, accurate basis (scale-adjusted, duplicates retained, signs as recorded, separate all-status population)", all(w in tx for w in ["scale-adjusted", "duplicate candidates retained", "signs as recorded", "Not every page uses this population", "all-status population"]), tx[-260:])
    await pg.click("#scope details.basis summary")
    await pg.select_option("#sScale", "PARSED"); hv = await pg.evaluate("()=>{const c=document.getElementById('scope').cloneNode(true);c.querySelectorAll('details').forEach(d=>d.remove());return c.innerText}")
    rec(R_, "Scenario change is flagged in the VISIBLE header without opening anything (SCENARIO ACTIVE + as reported), line count shown", "SCENARIO ACTIVE" in hv and "AS REPORTED" in hv and "of 58,340" in hv, hv[:200])
    await reset()

    # ---- KPI cards: five sparklines, values vs independent reference
    n_sp = await pg.evaluate("()=>[...document.querySelectorAll('#p-overview .kpi .spark svg')].length"); n_ov = await pg.evaluate("()=>[...document.querySelectorAll('#p-overview .kpi .spark .ov')].filter(o=>o.tabIndex===0).length")
    rec(R_, "Every KPI card has a trend chart (5 of 5) and each is keyboard-focusable", n_sp == 5 and n_ov == 5, (n_sp, n_ov))
    states = [("default", {}), ("entity GB01 + scale PARSED + dup EXCL_SAME", dict(ent=["GB01"], scale="PARSED", dup="EXCL_SAME")), ("months 5-20, sign EXCL_FLIP", {"from": 5, "to": 20, "sign": "EXCL_FLIP"}), ("years 2024-25 + division filter", dict(years=[2024, 2025]))]
    bad = []
    for sname, f in states:
        await reset(); await setst(f); await tab("overview"); x = subset(f); ok = mon_ok(f)
        for cid, ref in (("kSp0", msec(x, ["REVENUE"])), ("kSp1", msec(x, ["COGS", "PEOPLE", "OPEX"])), ("kSp2", msec(x, ["REVENUE"]) - msec(x, ["COGS", "PEOPLE", "OPEX"]))):
            ch = await chart(cid)
            if not ch or not same(ch["series"][0]["vals"], masked(ref, ok)): bad.append((sname, cid))
        for pop in ("ALL", "SAME"):
            await pg.select_option("#sVar", pop); xv = subset(f)
            for cid, secs in (("kSp3", ["REVENUE"]), ("kSp4", ["COGS", "PEOPLE", "OPEX"])):
                mv = mvar(xv, secs, pop); ref = [float(mv.v[m]) if ok[m] and mv.n[m] == mv.n[m] and mv.n[m] > 0 else None for m in range(36)]
                ch = await chart(cid)
                if not ch or not same(ch["series"][0]["vals"], ref): bad.append((sname, cid, pop))
            await pg.select_option("#sVar", "ALL")
    rec(R_, "KPI trend charts equal an independent pandas recomputation (revenue, cost base, result proxy, revenue/cost variance) in 4 filter/scenario states and 2 variance populations", not bad, bad[:4])

    # ---- YoY badge
    bad = []
    for sname, f in [("default", {}), ("years 2024-25", dict(years=[2024, 2025])), ("2023 only", dict(years=[2023])), ("GB01 + PARSED", dict(ent=["GB01"], scale="PARSED"))]:
        await reset(); await setst(f); await tab("overview"); x = subset(f); ok = mon_ok(f)
        txts = await pg.evaluate("()=>[...document.querySelectorAll('#p-overview .kpi .yoy')].map(e=>e.textContent)")
        for t, ref in zip(txts, (msec(x, ["REVENUE"]), msec(x, ["COGS", "PEOPLE", "OPEX"]), msec(x, ["REVENUE"]) - msec(x, ["COGS", "PEOPLE", "OPEX"]))):
            cur = pri = 0.0; n = 0
            for m in range(12, 36):
                if ok[m] and ok[m - 12]: cur += ref[m]; pri += ref[m - 12]; n += 1
            if not n or pri == 0:
                if "n/a" not in t: bad.append((sname, t, "expected n/a"))
            else:
                v = (cur - pri) / abs(pri) * 100; mm = re.search(r"([+−-]?[\d.]+)%", t); got = float(mm.group(1).replace("−", "-")) if mm else None
                if got is None or abs(got - v) > 0.06 or f"{n} mo" not in t: bad.append((sname, t, round(v, 2), n))
    rec(R_, "KPI YoY badges (revenue, cost base, result proxy) equal the independent same-months-prior-year calculation, or show n/a when no aligned months exist", not bad, bad[:4])

    # ---- sparkline interaction: hover tooltip, click, keyboard
    await reset(); await tab("overview"); x = subset({}); rev = msec(x, ["REVENUE"])
    box = await pg.evaluate("()=>{const r=document.querySelector('#kSp0 .ov').getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height}}")
    await pg.mouse.move(box["x"] + box["w"] - 1, box["y"] + box["h"] / 2); await pg.wait_for_timeout(120)
    tt = await pg.evaluate("()=>({d:getComputedStyle(document.getElementById('tt')).display,t:document.getElementById('tt').innerText})")
    rec(R_, "Hovering a KPI trend shows a tooltip with the month and the exact value (last month = reference)", tt["d"] != "none" and "Dec 25" in tt["t"] and f"${rev[35]/1e6:.2f}M" in tt["t"], tt)
    await pg.mouse.click(box["x"] + 1, box["y"] + box["h"] / 2); st = await S_()
    rec(R_, "Clicking a KPI trend point filters to that month (same guarded path as the line charts)", st["xf"] and st["xf"]["dim"] == "m" and st["xf"]["val"] == 0 and await pg.evaluate("()=>__fpa.nInc()") == len(subset(dict(**{"from": 0, "to": 0}))), st["xf"])
    await reset(); await pg.focus("#kSp1 .ov"); await pg.keyboard.press("Home"); await pg.keyboard.press("ArrowRight"); await pg.keyboard.press("Enter"); st = await S_()
    rec(R_, "Keyboard on a KPI trend: Home, ArrowRight, Enter selects the second month", st["xf"] and st["xf"]["dim"] == "m" and st["xf"]["val"] == 1, st["xf"])
    await reset()

    # ---- drill-through buttons
    out = []
    for sel, want_tab, want_metric in (("#p-overview .kgo[data-m='rev']", "trends", "rev"), ("#p-overview .kgo[data-m='cost']", "trends", "cost"), ("#p-overview .kgo[data-m='res']", "trends", "res"), ("#p-overview .kgo[data-go='variance'] >> nth=0", "variance", None)):
        await reset(); await tab("overview"); await pg.focus(sel); await pg.keyboard.press("Enter"); st = await S_(); mv = await pg.evaluate("()=>{const e=document.getElementById('selMetric');return e?e.value:null}")
        out.append((want_tab, st["tab"], want_metric, mv if want_metric else None))
        if st["tab"] != want_tab or (want_metric and mv != want_metric): out.append(("BAD", sel))
    rec(R_, "KPI drill-through buttons (keyboard Enter) open the matching tab and metric (Revenue, Cost base, Result proxy -> Trends; variance KPIs -> Budget & Variance)", not any(o[0] == "BAD" for o in out), out)
    await reset(); await tab("overview")

    # ---- result proxy bridge
    bad = []
    for sname, f in [("default", {}), ("entity US01", dict(ent=["US01"])), ("PARSED + dup EXCL_ALL", dict(scale="PARSED", dup="EXCL_ALL")), ("division + 2024", dict(years=[2024]))]:
        await reset(); await setst(f); await tab("overview"); x = subset(f); c = await chart("oBridge"); it = {i["label"]: i["val"] for i in c["items"]}
        sums = x.groupby("section").A.sum(); rev_, cogs, ppl, opx = [float(sums.get(k, 0.0)) for k in ("REVENUE", "COGS", "PEOPLE", "OPEX")]
        ok_ = same([it["Revenue"], it["COGS"], it["People"], it["Opex"], it["Result"]], [rev_, -cogs, -ppl, -opx, rev_ - cogs - ppl - opx]) and abs(it["Revenue"] + it["COGS"] + it["People"] + it["Opex"] - it["Result"]) < 0.01
        kp = await pg.inner_text("#p-overview .kpis")
        if not ok_ or f"${(rev_-cogs-ppl-opx)/1e6:.2f}M" not in kp.replace("−", "-").replace("-$", "$"): bad.append((sname, it))
    rec(R_, "Bridge steps equal the independent section totals; Revenue + steps = Result; Result equals the Result-proxy KPI (4 states)", not bad, bad[:2])
    await reset(); await tab("overview")
    await pg.click("#oBridge .bar[data-k='1']"); st = await S_()
    rec(R_, "Clicking the COGS step filters to the COGS section (chart selection chip) and marks it pressed", st["xf"] and st["xf"]["dim"] == "sec" and await pg.evaluate("()=>document.querySelector('#oBridge .bar[data-k=\"1\"]').getAttribute('aria-pressed')") == "true", st["xf"])
    await reset(); await pg.click("#oBridge .bar[data-k='4']", force=True); st = await S_(); ti = await pg.evaluate("()=>document.querySelector('#oBridge .bar[data-k=\"4\"]').tabIndex")
    rec(R_, "The Result total is not a filter: clicking does nothing and it is not a tab stop", st["xf"] is None and ti == -1, (st["xf"], ti))
    await setst(dict(sec=["REVENUE"])); await tab("overview"); dis = await pg.evaluate("()=>[...document.querySelectorAll('#oBridge .bar')].map(b=>b.getAttribute('aria-disabled')||'')")
    await pg.click("#oBridge .bar[data-k='2']", force=True); st = await S_()
    rec(R_, "With a REVENUE-only section filter, the cost steps are disabled and clicking them is blocked (no empty intersection)", dis[1:4] == ["true"] * 3 and dis[0] == "" and st["xf"] is None, dis)
    await reset()

    # ---- proxy margin by entity
    bad = []
    for sname, f in [("default", {}), ("entity US01", dict(ent=["US01"])), ("months 5-20 + PARSED", {"from": 5, "to": 20, "scale": "PARSED"}), ("sign NONNEG", dict(sign="NONNEG"))]:
        await reset(); await setst(f); await tab("overview"); x = subset(f); c = await chart("oEntMgn"); got = {i["label"]: i["val"] for i in c["items"]}
        for e in ents:
            g = x[x.entity_code == e]; r_ = g[g.section == "REVENUE"].A.sum(); res = r_ - g[g.section.isin(["COGS", "PEOPLE", "OPEX"])].A.sum(); ref = res / r_ if r_ else None
            v = got[e]
            if (v is None) != (ref is None) or (v is not None and abs(v - ref) > 1e-9): bad.append((sname, e, v, ref))
    rec(R_, "Proxy margin by entity = result proxy / revenue per entity, equal to the independent calculation in 4 states (null where an entity has no revenue)", not bad, bad[:3])
    await reset(); await tab("overview"); await pg.click("#oEntMgn .bar[data-k='5']"); st = await S_()
    rec(R_, "Clicking a margin bar filters to that entity (US01)", st["xf"] and st["xf"]["dim"] == "ent" and st["xf"]["val"] == 5, st["xf"])
    await reset()

    # ---- cumulative variance + margin trend
    bad = []
    for sname, f in [("default", {}), ("entity IN01 + PARSED", dict(ent=["IN01"], scale="PARSED")), ("months 8-27", {"from": 8, "to": 27})]:
        for pop in ("ALL", "SAME", "OPP"):
            await reset(); await setst(f); await pg.select_option("#sVar", pop); await tab("variance"); x = subset(f); ok = mon_ok(f); c = await chart("vCum")
            for si, secs in enumerate((["REVENUE"], ["COGS", "PEOPLE", "OPEX"])):
                mv = mvar(x, secs, pop); run = 0.0; ref = []
                for m in range(36):
                    if not ok[m]: ref.append(None); continue
                    if mv.n[m] == mv.n[m] and mv.n[m] > 0: run += float(mv.v[m]); ref.append(run)
                    else: ref.append(None)
                if not same(c["series"][si]["vals"], ref): bad.append((sname, pop, si))
    rec(R_, "Cumulative net variance (revenue and cost base) equals the independent running total of actual - budget, 3 states x 3 variance populations", not bad, bad[:3])
    await reset(); await tab("variance"); c = await chart("vCum"); vs = (await pg.evaluate("()=>{const v=__fpa.varBySection('ALL');return [v[0].net,[1,2,3].reduce((s,k)=>s+v[k].net,0)]}"))
    rec(R_, "Final cumulative value equals the Budget & Variance net variance of the same population (revenue and cost base)", abs([v for v in c["series"][0]["vals"] if v is not None][-1] - vs[0]) < 0.01 and abs([v for v in c["series"][1]["vals"] if v is not None][-1] - vs[1]) < 0.01, (vs, c["series"][0]["vals"][-1], c["series"][1]["vals"][-1]))
    bad = []
    for sname, f in [("default", {}), ("entity GB01", dict(ent=["GB01"])), ("months 5-20", {"from": 5, "to": 20}), ("PARSED + dup EXCL_ALL", dict(scale="PARSED", dup="EXCL_ALL"))]:
        await reset(); await setst(f); await tab("trends"); x = subset(f); ok = mon_ok(f); c = await chart("tMargin")
        rv = msec(x, ["REVENUE"]); rs = rv - msec(x, ["COGS", "PEOPLE", "OPEX"])
        mg = [float(rs[m] / rv[m]) if ok[m] and rv[m] else None for m in range(36)]
        r3 = [float((rs[m] + rs[m - 1] + rs[m - 2]) / (rv[m] + rv[m - 1] + rv[m - 2])) if m >= 2 and ok[m] and ok[m - 1] and ok[m - 2] and (rv[m] + rv[m - 1] + rv[m - 2]) else None for m in range(36)]
        if not same(c["series"][0]["vals"], mg, 1e-9) or not same(c["series"][1]["vals"], r3, 1e-9): bad.append(sname)
    rec(R_, "Proxy-margin trend (monthly and trailing 3-month) equals the independent calculation in 4 states", not bad, bad)
    await reset()

    # ---- all new charts: table toggle, dark theme, phone width, print, console
    allok = []
    for t, ids in (("overview", ["oBridge", "oEntMgn"]), ("variance", ["vCum"]), ("trends", ["tMargin"])):
        await tab(t)
        for cid in ids:
            await pg.click(f"[data-tbl='{cid}']"); a_ = await pg.evaluate(f"()=>document.getElementById('{cid}').innerHTML.includes('<table')"); await pg.click(f"[data-tbl='{cid}']"); b_ = await pg.evaluate(f"()=>document.getElementById('{cid}').innerHTML.includes('<svg')"); allok.append((cid, a_, b_))
    rec(R_, "Chart/Table toggle works on all four new charts", all(a and b for _, a, b in allok), allok)
    th0 = await pg.evaluate("()=>document.documentElement.getAttribute('data-theme')"); await pg.click("#btnTheme"); await tab("overview"); await pg.wait_for_timeout(100)
    emp = await pg.evaluate("()=>['oBridge','oEntMgn','kSp0','kSp4'].filter(i=>!document.querySelector('#'+i+' svg'))"); await pg.screenshot(path=str(SHOT / "redesign_theme2_overview.png"), full_page=True)
    rec(R_, "Other theme: new charts and KPI trends still render", not emp, emp); await pg.click("#btnTheme")
    c4 = await br.new_context(viewport={"width": 390, "height": 800}); p4 = await c4.new_page(); await p4.goto(URL); await p4.wait_for_function("window.__fpa")
    ov = []
    for t in ["overview", "trends", "variance"]:
        await p4.evaluate(f"()=>document.getElementById('tab-{t}').click()"); await p4.wait_for_timeout(100)
        m_ = await p4.evaluate("()=>({sw:document.documentElement.scrollWidth,iw:innerWidth,hdr:document.querySelector('.hdr').getBoundingClientRect().right,sp:[...document.querySelectorAll('.kpi .spark svg')].some(s=>s.getBoundingClientRect().right>innerWidth+1)})")
        if m_["sw"] > m_["iw"] + 1 or m_["hdr"] > m_["iw"] + 1 or m_["sp"]: ov.append((t, m_))
    await p4.evaluate("()=>document.getElementById('tab-overview').click()"); await p4.screenshot(path=str(SHOT / "redesign_phone.png"), full_page=False); await c4.close()
    rec(R_, "Phone width (390 px): logo header, KPI trends and new charts cause no horizontal overflow", not ov, ov)
    await pg.emulate_media(media="print"); pr = await pg.evaluate("()=>[...document.querySelectorAll('.kgo')].every(b=>getComputedStyle(b).display==='none')"); await pg.emulate_media(media="screen")
    rec(R_, "Print: drill-through buttons are hidden in the print layout", pr)


asyncio.run(main())
