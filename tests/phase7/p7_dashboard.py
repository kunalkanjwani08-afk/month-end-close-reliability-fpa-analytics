"""Phase 7 - independent dashboard tests (headless Chromium via Playwright, against the delivered HTML file).

Reference values come from the pandas reference lines (ref_lines.pkl), never from the dashboard. Dashboard values
are read from (a) the rendered DOM, (b) the CSV the dashboard exports for the current selection (every line, full
precision) and (c) the dashboard's own aggregate functions - (c) is the thing under test, not the reference.
Filters are driven through the real UI controls where practical (year chips, entity list, selects, chart bars,
Reset, Undo, theme); the remaining combinations use the dashboard's state hook, which calls the same mutate()
path as the controls.
"""
import csv, io, json, re, time
import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright
from p7_common import *

R = Registry()
A = "dashboard"
EV = OUT / "evidence" / "dashboard"
EV.mkdir(parents=True, exist_ok=True)
L = pd.read_pickle(WORK / "ref_lines.pkl")
cl = pd.read_csv(CLEAN, dtype=str, keep_default_na=False, encoding="utf-8-sig", usecols=["dup_tier", "sign_flag", "scale_confidence"])
L["dup"] = cl.dup_tier.values; L["sf"] = cl.sign_flag.values; L["conf"] = cl.scale_confidence.values
DUPT = {"DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN", "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT", "CANDIDATE_COPY_PARTIAL_AGREEMENT"}
SECS = ["REVENUE", "COGS", "PEOPLE", "OPEX", "D&A", "BELOW_EBITDA", "TAX"]


def ref_state(st, meta):
    """Independent pandas evaluation of a dashboard state (indices are decoded with the payload's own lists)."""
    months = meta["months"]
    X = L[L.posted | L.np].copy()
    mi = X.ym.map({m: i for i, m in enumerate(months)})
    yrs = set(st["years"]); q = set(st["qtrs"])
    keep = X.ym.str[:4].astype(int).isin(yrs) & ((X.ym.str[5:7].astype(int) + 2) // 3).isin(q) & mi.between(st["from"], st["to"])
    if st["ent"]: keep &= X.e.isin({meta["ents"][i]["c"] for i in st["ent"]})
    if st["div"]: keep &= X.d.isin({meta["divs"][i] for i in st["div"]})
    if st["sec"]: keep &= X.sec.isin({meta["secs"][i] for i in st["sec"]})
    if st["gl"]: keep &= X.gl.isin({str(meta["gls"][i]["gl"]) for i in st["gl"]})
    if st["cc"]: keep &= X.cc.isin({meta["ccs"][i] for i in st["cc"]})
    xf = st.get("xf")
    if xf:
        dim, val = xf["dim"], xf["val"]
        col = {"ent": ("e", lambda v: meta["ents"][v]["c"]), "div": ("d", lambda v: meta["divs"][v]), "sec": ("sec", lambda v: meta["secs"][v]),
               "gl": ("gl", lambda v: str(meta["gls"][v]["gl"])), "cc": ("cc", lambda v: meta["ccs"][v]), "m": ("ym", lambda v: months[v])}[dim]
        keep &= X[col[0]] == col[1](val)
    X = X[keep]
    rest = X.fac.notna() & (X.fac != 1)
    a = X.a.copy(); b = X.b.copy()
    if st["scale"] == "PARSED":
        a = X.a_rep; b = X.b_rep
    elif st["scale"] == "HIGH":
        m = rest & (X.conf != "HIGH"); a = a.where(~m, X.a_rep); b = b.where(~m, X.b_rep)
    sp = pd.Series(True, index=X.index)
    if st["scale"] == "EXCL_MED": sp &= ~(rest & (X.conf != "HIGH"))
    if st["scale"] == "EXCL_ALL": sp &= ~rest
    if st["dup"] == "EXCL_SAME": sp &= X.dup != "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN"
    if st["dup"] == "EXCL_ALL": sp &= ~X.dup.isin(DUPT)
    if st["sign"] == "NONNEG": sp &= X.sf == "ALL_NON_NEGATIVE"
    if st["sign"] == "EXCL_FLIP": sp &= X.sf != "SINGLE_COLUMN_SIGN_FLIP"
    X = X.assign(A=a, B=b)[sp]
    Pp = X[X.posted]
    out = {"n": len(Pp), "srn": set(Pp.srn), "rev": Pp.loc[Pp.sec == "REVENUE", "A"].sum(),
           "cost": Pp.loc[Pp.sec.isin(["COGS", "PEOPLE", "OPEX"]), "A"].sum()}
    out["res"] = out["rev"] - out["cost"]
    out["sec"] = {s: Pp.loc[Pp.sec == s, "A"].sum() for s in SECS}
    # variance by section (lines with budget, population by sign category of actual vs budget)
    V = Pp[Pp.B.notna()].copy()
    sc = np.where((V.A == 0) | (V.B == 0), "ZERO", np.where(np.sign(V.A) == np.sign(V.B), "SAME", "OPP"))
    if st["varPop"] != "ALL": V = V[sc == st["varPop"]]
    out["var"] = {}
    for s in ["REVENUE", "COGS", "PEOPLE", "OPEX"]:
        c = V[V.sec == s].groupby(["e", "gl", "ym"]).agg(a=("A", "sum"), b=("B", "sum"), n=("A", "size"))
        net = c.a.sum() - c.b.sum(); bn = c.b.sum(); ba = c.b.abs().sum()
        out["var"][s] = {"n": int(c.n.sum()), "act": c.a.sum(), "bud": bn, "net": net, "gross": (c.a - c.b).abs().sum(),
                         "pct": (net / abs(bn)) if (ba > 0 and abs(bn) >= 0.5 * ba) else None}
    out["status"] = {k: {"n": int((X.st == k).sum()), "rev": X.loc[(X.st == k) & (X.sec == "REVENUE"), "A"].sum(),
                         "cost": X.loc[(X.st == k) & X.sec.isin(["COGS", "PEOPLE", "OPEX"]), "A"].sum()}
                     for k in ["Posted", "Pending", "Parked", "Rejected", "(blank)"]}
    return out


def money(txt):
    m = re.search(r"([−-])?\$([\d,]+(?:\.\d+)?)([KMB])?", txt)
    if not m: return None
    v = float(m.group(2).replace(",", "")) * {None: 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(3)]
    return -v if m.group(1) else v


console, failed = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    page.on("console", lambda m: console.append((m.type, m.text)) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: console.append(("pageerror", str(e))))
    page.on("requestfailed", lambda r: failed.append(r.url))
    reqs = []
    page.on("request", lambda r: reqs.append(r.url))
    t0 = time.time()
    page.goto(HTML.as_uri())
    page.wait_for_function("window.__fpa && document.querySelector('#recBadge') && !/…/.test(document.querySelector('#recBadge').textContent)", timeout=120000)
    R.add("UI00", A, "Dashboard boot time (headless Chromium, local file, one run)", "INFO", None, round(time.time() - t0, 2))
    meta = page.evaluate("({months: DATA.months, ents: DATA.ents, divs: DATA.divs, secs: DATA.secs, gls: DATA.gls, ccs: DATA.ccs})")
    ext = [u for u in reqs if not u.startswith("file:") and not u.startswith("data:") and not u.startswith("blob:")]
    R.cmp("UI01", A, "Network requests to anything other than the local file (standalone requirement)", 0, len(ext), 0, note=json.dumps(ext[:5]))

    def reset():
        if page.is_enabled("#btnReset"):
            page.click("#btnReset"); page.wait_for_timeout(100)

    def state():
        return page.evaluate("JSON.parse(JSON.stringify(__fpa.S()))")

    def dash_values():
        return page.evaluate("""() => { const a = __fpa.agg(), st = __fpa.S(), vs = __fpa.varBySection(st.varPop), s = __fpa.statusTotals();
            return { n: __fpa.nInc(), rev: a.rev, cost: a.cost, res: a.res, sS: Array.from(a.sS),
                     var: vs.slice(0, 4).map(t => ({ n: t.n, act: t.act, bud: t.bud, net: t.net, pct: t.pct == null ? null : t.pct, gross: t.gross })),
                     status: s, kv: Array.from(document.querySelectorAll('#p-overview .kpi .kv')).map(e => e.textContent),
                     ks: Array.from(document.querySelectorAll('#p-overview .kpi .ks')).map(e => e.textContent),
                     scope: document.querySelector('#scope').textContent, txt: document.querySelector('#p-overview').innerText }; }""")

    def export_rows():
        with page.expect_download(timeout=60000) as d:
            page.click("#btnCsv")
        p = d.value.path()
        txt = open(p, encoding="utf-8-sig").read()
        return list(csv.DictReader(io.StringIO(txt)))

    def verify(tag, label, ui_driven):
        st = state(); ref = ref_state(st, meta); dv = dash_values()
        pop = f"{label} | {'UI-driven' if ui_driven else 'state hook'}"
        R.cmp(f"{tag}.n", A, f"[{label}] Posted lines in scope", ref["n"], dv["n"], 0, population=pop)
        for k in ["rev", "cost", "res"]:
            R.cmp(f"{tag}.{k}", A, f"[{label}] {k} (dashboard engine, full precision)", ref[k], dv[k], TOL_USD, population=pop)
        for i, s in enumerate(SECS):
            R.cmp(f"{tag}.sec.{s}", A, f"[{label}] section total {s}", ref["sec"][s], dv["sS"][i], TOL_USD, population=pop)
        for i, s in enumerate(["REVENUE", "COGS", "PEOPLE", "OPEX"]):
            r, d = ref["var"][s], dv["var"][i]
            ok = r["n"] == d["n"] and all(abs(r[k] - d[k]) <= TOL_USD for k in ["act", "bud", "net", "gross"]) and \
                 ((r["pct"] is None and d["pct"] is None) or (r["pct"] is not None and d["pct"] is not None and abs(r["pct"] - d["pct"]) <= TOL_RATIO))
            R.add(f"{tag}.var.{s}", A, f"[{label}] budget variance {s} (lines, actual, budget, net, gross cell var, guarded %)",
                  "PASS" if ok else "FAIL", json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}),
                  json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}), pop, "variance = actual - budget; cells = entity x GL x month", "0.01 USD / 1e-9")
        okst = all(ref["status"][k]["n"] == dv["status"][k]["n"] and abs(ref["status"][k]["rev"] - dv["status"][k]["rev"]) <= TOL_USD
                   and abs(ref["status"][k]["cost"] - dv["status"][k]["cost"]) <= TOL_USD for k in ref["status"])
        R.add(f"{tag}.status", A, f"[{label}] journal-status diagnostic: lines, revenue, cost for Posted/Pending/Parked/Rejected/blank",
              "PASS" if okst else "FAIL", json.dumps({k: v["n"] for k, v in ref["status"].items()}),
              json.dumps({k: v["n"] for k, v in dv["status"].items()}), pop)
        # DOM: KPI cards (display precision) and the 'Full:' revenue line (whole dollars)
        if ref["n"]:
            full = [t for t in dv["ks"] if t.startswith("Full:")]
            fv = money(full[0]) if full else None
            R.cmp(f"{tag}.dom.full", A, f"[{label}] DOM 'Full:' revenue (rounded to whole USD)", round(ref["rev"]), fv, 0.5, population=pop)
            for i, k in enumerate(["rev", "cost", "res"]):
                v = money(dv["kv"][i]); unit = 1e9 if abs(ref[k]) >= 1e9 else 1e6 if abs(ref[k]) >= 1e6 else 1e3 if abs(ref[k]) >= 1e3 else 1
                tol = {1e9: 0.005e9, 1e6: 0.005e6, 1e3: 50, 1: 0.5}[unit]
                R.cmp(f"{tag}.dom.{k}", A, f"[{label}] DOM KPI card {k} '{dv['kv'][i]}' (display precision)", ref[k], v, tol, population=pop)
            bad = [w for w in ["NaN", "undefined", "Infinity", "[object"] if w in dv["txt"]]
            R.cmp(f"{tag}.dom.junk", A, f"[{label}] Overview text contains no NaN/undefined/Infinity", 0, len(bad), 0, note=",".join(bad))
            rows = export_rows()
            srn = {int(r["source_row_number"]) for r in rows}
            R.cmp(f"{tag}.csv.rows", A, f"[{label}] CSV export: line count", ref["n"], len(rows), 0, population=pop)
            R.cmp(f"{tag}.csv.set", A, f"[{label}] CSV export: source_row_number set == reference set", 0, len(srn ^ ref["srn"]), 0)
            ex = pd.DataFrame(rows)
            ex["actual_usd"] = pd.to_numeric(ex.actual_usd)
            for s in ["REVENUE", "COGS", "PEOPLE", "OPEX"]:
                R.cmp(f"{tag}.csv.{s}", A, f"[{label}] CSV export: sum of actual_usd, {s}", ref["sec"][s],
                      float(ex.loc[ex.section == s, "actual_usd"].sum()), TOL_USD)
        else:
            R.cmp(f"{tag}.empty", A, f"[{label}] empty selection shows the no-data state", 1,
                  int("No lines match" in dv["txt"]), 0, population=pop)
        return st, ref, dv

    # ---- S0 default
    page.screenshot(path=str(EV / "s0_default.png"), full_page=False)
    st0, ref0, dv0 = verify("D00", "default (all filters)", True)
    R.cmp("D00.base", A, "Default scope = 58,340 Posted lines", 58340, dv0["n"], 0)
    # ---- S1 year chips via UI: deselect 2023 and 2025
    page.click("#fYears .chip[data-v='2023']"); page.click("#fYears .chip[data-v='2025']")
    verify("D01", "year 2024 (chips)", True)
    page.screenshot(path=str(EV / "s1_year2024.png"))
    # ---- undo restores the previous state
    page.click("#btnUndo")
    R.cmp("D01.undo", A, "Undo after deselecting 2025 restores years [2024, 2025]", 1,
          int(sorted(state()["years"]) == [2024, 2025]), 0)
    page.click("#btnReset")
    R.cmp("D01.reset", A, "Reset restores the full default state", 1,
          int({k: v for k, v in state().items() if k != "tab"} == {k: v for k, v in st0.items() if k != "tab"}), 0)
    # ---- S2 entity list via UI (first tick selects only that entity)
    ie = [i for i, e in enumerate(meta["ents"]) if e["c"] == "IN01"][0]
    page.click("#gEnt .msb"); page.click(f"#gEnt .plist input[value='{ie}']"); page.keyboard.press("Escape")
    verify("D02", "entity IN01 (list)", True)
    reset()
    # ---- S3 scale select via UI
    page.select_option("#sScale", "PARSED")
    verify("D03", "scale AS REPORTED (select)", True)
    sc = page.text_content("#scope")
    R.cmp("D03.scope", A, "Header flags non-baseline scale basis (SCENARIO ACTIVE / AS REPORTED)", 1,
          int(("SCENARIO" in sc.upper()) or ("AS REPORTED" in sc.upper())), 0, note=sc[:200])
    reset()
    # ---- S4 cross-filter: click the US01 bar in 'Revenue by entity'
    iu = [i for i, e in enumerate(meta["ents"]) if e["c"] == "US01"][0]
    bar = page.locator(f"#oEntRev rect.bar[data-k='{iu}']")
    if bar.count():
        bar.first.click()
        st = state()
        R.cmp("D04.xf", A, "Clicking the US01 bar sets a cross-filter on entity US01", 1,
              int(bool(st.get("xf")) and st["xf"]["dim"] == "ent" and st["xf"]["val"] == iu), 0, note=json.dumps(st.get("xf")))
        verify("D04", "cross-filter US01 (chart click)", True)
        reset()
        R.cmp("D04.clear", A, "Reset clears the cross-filter", 1, int(state().get("xf") in (None, {})), 0)
    else:
        R.add("D04", A, "Cross-filter by chart click", "BLOCKED", note="bar element not found")
    # ---- state-hook combinations (same mutate() path as the controls)
    def setst(js):
        page.evaluate(f"__fpa.setState(s => {{ {js} }})"); page.wait_for_timeout(150)
    sec_ix = {s: i for i, s in enumerate(meta["secs"])}
    gl_ix = {str(g["gl"]): i for i, g in enumerate(meta["gls"])}
    combos = [
        ("D05", "cost-only selection: section OPEX", f"s.sec=[{sec_ix['OPEX']}];"),
        ("D06", "revenue-only selection: section REVENUE", f"s.sec=[{sec_ix['REVENUE']}];"),
        ("D07", "2025 + US01,DE01 + Medical Devices", f"s.years=[2025]; s.ent=[{iu},{[i for i,e in enumerate(meta['ents']) if e['c']=='DE01'][0]}]; s.div=[{meta['divs'].index('Medical Devices')}];"),
        ("D08", "single cost centre (first in list)", "s.cc=[0];"),
        ("D09", "GL 4190 discounts only", f"s.gl=[{gl_ix['4190']}];"),
        ("D10", "Q1 only, months 6..20", "s.qtrs=[1]; s.from=6; s.to=20;"),
        ("D11", "scale HIGH + duplicates EXCL_ALL + sign NONNEG", "s.scale='HIGH'; s.dup='EXCL_ALL'; s.sign='NONNEG';"),
        ("D12", "scale EXCL_MED + dup EXCL_SAME + sign EXCL_FLIP + same-sign variance", "s.scale='EXCL_MED'; s.dup='EXCL_SAME'; s.sign='EXCL_FLIP'; s.varPop='SAME';"),
        ("D13", "scale EXCL_ALL + opposite-sign variance + IN01", f"s.scale='EXCL_ALL'; s.varPop='OPP'; s.ent=[{ie}];"),
        ("D14", "near-zero account: GL 7200 FX gain/loss", f"s.gl=[{gl_ix['7200']}];"),
        ("D15", "empty selection: Q1 only and months Apr-Jun 2023", "s.qtrs=[1]; s.from=3; s.to=5;"),
        ("D16", "zero-involved variance population", "s.varPop='ZERO';"),
    ]
    for tag, label, js in combos:
        reset(); setst(js)
        st, ref, dv = verify(tag, label, False)
        if tag == "D05":
            t = dv["txt"]
            R.cmp("D05.margin", A, "Cost-only selection: revenue shows $0 and proxy margin is not computed (n/a)", 1,
                  int(("Proxy margin n/a" in t) and abs(dv["rev"]) < 1e-9), 0, note=re.sub(r"\s+", " ", t[:600]))
            obs = page.evaluate("document.querySelector('#oObs') ? document.querySelector('#oObs').innerText : ''")
            (EV / "costonly_observations.txt").write_text(obs, encoding="utf-8")
            bad = [w for w in ["margin of", "% margin", "revenue grew", "revenue fell"] if w in obs.lower()]
            R.cmp("D05.obs", A, "Cost-only selection: 'What stands out' makes no revenue/margin claim", 0, len(bad), 0, note=obs[:400])
            page.screenshot(path=str(EV / "s5_cost_only.png"))
        if tag == "D06":
            obs = page.evaluate("document.querySelector('#oObs') ? document.querySelector('#oObs').innerText : ''")
            (EV / "revenueonly_observations.txt").write_text(obs, encoding="utf-8")
        if tag == "D15":
            page.screenshot(path=str(EV / "s15_empty.png"))
            R.cmp("D15.zero", A, "Empty selection: 0 Posted lines in scope", 0, dv["n"], 0)
    reset()
    # ---- detail table pagination
    page.evaluate("document.querySelector('#tabs [data-tab=detail], #tabs button:nth-child(9)').click()")
    page.wait_for_timeout(400)
    rows_vis = page.locator("#p-detail tbody tr").count()
    R.add("UI10", A, "Detail tab renders a paginated table (rows on first page)", "PASS" if 0 < rows_vis < 58340 else "FAIL", None, rows_vis)
    nxt = page.locator("#p-detail button:has-text('Next')")
    if nxt.count():
        first = page.locator("#p-detail tbody tr").first.inner_text()
        nxt.first.click(); page.wait_for_timeout(200)
        R.cmp("UI11", A, "Detail pagination 'Next' shows a different page", 1, int(page.locator("#p-detail tbody tr").first.inner_text() != first), 0)
    else:
        R.add("UI11", A, "Detail pagination 'Next' control", "NOT TESTED", note="no 'Next' button found by text")
    reset()
    # ---- theme
    t1 = page.evaluate("document.documentElement.getAttribute('data-theme')")
    bg1 = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.click("#btnTheme"); page.wait_for_timeout(200)
    t2 = page.evaluate("document.documentElement.getAttribute('data-theme')")
    bg2 = page.evaluate("getComputedStyle(document.body).backgroundColor")
    R.cmp("UI20", A, "Theme toggle changes data-theme and page background", 1, int(t1 != t2 and bg1 != bg2), 0, note=f"{t1}/{bg1} -> {t2}/{bg2}")
    page.screenshot(path=str(EV / "theme_toggled.png"))
    page.click("#btnTheme")
    # ---- keyboard focus indicator
    page.keyboard.press("Tab"); page.keyboard.press("Tab")
    foc = page.evaluate("""() => { const e = document.activeElement; const cs = getComputedStyle(e);
        return { tag: e.tagName, id: e.id, outline: cs.outlineStyle + ' ' + cs.outlineWidth, shadow: cs.boxShadow }; }""")
    R.cmp("UI21", A, "Keyboard Tab moves focus to a control with a visible focus style (outline or box-shadow)", 1,
          int(foc["tag"] != "BODY" and (not foc["outline"].startswith("none") or foc["shadow"] not in ("none", ""))), 0, note=json.dumps(foc))
    # ---- print media
    page.emulate_media(media="print")
    hidden = page.evaluate("Array.from(document.querySelectorAll('.hide-print')).filter(e => getComputedStyle(e).display !== 'none').length")
    R.cmp("UI22", A, "Print media hides interactive-only controls (.hide-print)", 0, hidden, 0)
    page.pdf(path=str(EV / "print_preview_phase7.pdf"), format="A4")
    R.cmp("UI23", A, "Print/PDF generated (Chromium print-to-PDF)", 1, int((EV / "print_preview_phase7.pdf").stat().st_size > 10000), 0)
    page.emulate_media(media="screen")
    # ---- responsive widths
    for w, h in [(390, 844), (768, 1024), (1024, 768), (1920, 1080)]:
        page.set_viewport_size({"width": w, "height": h}); page.wait_for_timeout(300)
        ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        R.cmp(f"UI3{w}", A, f"No horizontal page overflow at {w}px width", 0, max(0, ov), 0)
        page.screenshot(path=str(EV / f"width_{w}.png"))
    # ---- console
    errs = [c for c in console if c[0] in ("error", "pageerror")]
    R.cmp("UI40", A, "Browser console errors / uncaught page errors during the whole session", 0, len(errs), 0, note=json.dumps(errs[:5]))
    R.cmp("UI41", A, "Failed resource requests", 0, len(failed), 0, note=json.dumps(failed[:5]))
    R.add("UI42", A, "Console warnings (informational)", "INFO", None, len([c for c in console if c[0] == "warning"]))
    br.close()

R.add("UI50", A, "Firefox / Safari (WebKit) rendering", "NOT TESTED", note="only Chromium is installed in this environment")
R.add("UI51", A, "Screen reader / assistive technology", "NOT TESTED", note="no assistive technology available; ARIA attributes are not a substitute")
R.add("UI52", A, "Physical printer output", "NOT TESTED", note="print-media emulation and Chromium PDF only")
R.save("dashboard")
