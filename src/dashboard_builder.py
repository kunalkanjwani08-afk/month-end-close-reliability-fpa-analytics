"""Dashboard build script - exports the compact payload and assembles the standalone dashboard HTML.

Reads (read-only):  build/fpa_analysis.duckdb, build/sql_results/*.csv, docs/INSIGHT_REGISTER.md
Template:           src/dashboard_template.html   (contains the single placeholder  /*__PAYLOAD__*/null)
Writes:             dashboard/fpa_financial_analytics_dashboard.html  (+ payload_stats.json)

Nothing is cleaned, deduplicated, imputed, dropped or sign-flipped here: the 58,340 eligible P&L lines of
v_pl_actual are exported one-for-one. Aggregation happens in the browser.
Run:  python src/dashboard_builder.py
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "build/fpa_analysis.duckdb"
SQL_RESULTS = ROOT / "build" / "sql_results"
OUT = ROOT / "dashboard"
STATS_DIR = ROOT / "build" / "dashboard_qa"   # generated QA by-products (git-ignored)
TEMPLATE = ROOT / "src/dashboard_template.html"
REGISTER = ROOT / "docs/INSIGHT_REGISTER.md"
SEC_ORDER = ["REVENUE", "COGS", "PEOPLE", "OPEX", "D&A", "BELOW_EBITDA", "TAX"]
SIGNCAT = {"SAME_SIGN_NONZERO": 0, "OPPOSITE_SIGN_NONZERO": 1, "ZERO_INVOLVED": 2, "MISSING_OR_UNAVAILABLE": 3}
DUP = {"UNIQUE_DOCUMENT_NO": 0, "GROUP_ANCHOR": 0, "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN": 1,
       "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT": 2, "CANDIDATE_COPY_PARTIAL_AGREEMENT": 3}
SIGNFLAG = {"ALL_NON_NEGATIVE": 0, "ALL_NEGATIVE": 1, "SINGLE_COLUMN_SIGN_FLIP": 2, "MIXED_OTHER": 3}


def num(v):
    """CSV text -> number/None/str (no rounding)."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if re.fullmatch(r"-?\d+", v) else f
    except ValueError:
        return v


def csv_table(name: str, cols=None):
    with open(SQL_RESULTS / f"{name}.csv", newline="", encoding="utf-8") as fh:
        rd = csv.reader(fh)
        head = next(rd)
        idx = [head.index(c) for c in cols] if cols else list(range(len(head)))
        rows = [[num(r[i]) for i in idx] for r in rd]
    return {"c": [head[i] for i in idx], "r": rows}


def md_inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def md_block(text: str) -> str:
    out, lines, i = [], text.strip().split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].startswith("|"):
                tbl.append(lines[i]); i += 1
            rows = [[c.strip() for c in t.strip().strip("|").split("|")] for t in tbl if not re.fullmatch(r"\|[-| :]+\|", t.strip())]
            h = "".join(f"<th>{md_inline(c)}</th>" for c in rows[0])
            b = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f"<div class='tw'><table class='mini'><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>")
            continue
        if ln.strip():
            out.append(f"<p>{md_inline(ln.strip())}</p>")
        i += 1
    return "".join(out)


def parse_register():
    txt = REGISTER.read_text(encoding="utf-8")
    ranking = []
    for m in re.finditer(r"^\| (\d+) \| (INS-\d+) \| (.+?) \| (\d) \| (\d) \| (\d) \| (\d) \| (\d+) \|$", txt, re.M):
        ranking.append({"rank": int(m[1]), "id": m[2], "title": m[3], "mat": int(m[4]), "per": int(m[5]), "conf": int(m[6]), "act": int(m[7]), "total": int(m[8])})
    ins = []
    for blk in re.split(r"^## (?=INS-\d+ - )", txt, flags=re.M)[1:]:
        head, _, body = blk.partition("\n")
        iid, _, title = head.partition(" - ")
        body = body.split("\n---")[0]
        fields = {}
        parts = re.split(r"^\*\*(\d+)\. ([^*]+?)\.\*\*", body, flags=re.M)
        for k in range(1, len(parts), 3):
            fields[int(parts[k])] = {"name": parts[k + 1].strip(), "html": md_block(parts[k + 2])}
        ins.append({"id": iid.strip(), "title": title.strip(), "fields": [fields[k] for k in sorted(fields)]})
    return ranking, ins


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET threads=1")

    acc = con.execute("select gl_account, any_value(account_name), any_value(account_group), section, section_order from v_pl_actual group by gl_account, section, section_order order by section_order, gl_account").fetchall()
    gls = [{"gl": a[0], "name": a[1], "group": a[2], "sec": a[3]} for a in acc]
    gl_ix = {g["gl"]: i for i, g in enumerate(gls)}
    ents = con.execute("select distinct entity_code, legal_entity from v_pl_actual order by 1").fetchall()
    divs = [r[0] for r in con.execute("select distinct division from v_pl_actual order by 1").fetchall()]
    ccs = [r[0] for r in con.execute("select distinct cost_center_code from v_pl_actual where cost_center_code is not null order by 1").fetchall()]
    months = [r[0] for r in con.execute("select distinct period_ym from v_pl_actual order by 1").fetchall()]
    e_ix = {e[0]: i for i, e in enumerate(ents)}
    d_ix = {d: i for i, d in enumerate(divs)}
    c_ix = {c: i for i, c in enumerate(ccs)}
    m_ix = {m: i for i, m in enumerate(months)}

    q = """select source_row_number, document_no, entity_code, division, gl_account, cost_center_code, period_ym,
        actual_usd_adj, budget_usd_adj, forecast_usd_adj, prior_year_usd_adj,
        actual_usd_parsed, budget_usd_parsed, forecast_usd_parsed, prior_year_usd_parsed,
        sign_cat_ab, sign_cat_af, sign_cat_ap, scale_factor_applied, scale_confidence, dup_tier, sign_flag, headcount_fte
        from v_pl_actual order by source_row_number"""
    R = {k: [] for k in "src doc e d g c m a b f p sab saf sap rs dp sg".split()}
    parsed, hc = {}, {}
    n = 0
    for r in con.execute(q).fetchall():
        (srn, doc, ent, div, gl, cc, ym, a, b, f, p, pa, pb, pf, pp, s1, s2, s3, sfa, sconf, dup, sgn, fte) = r
        R["src"].append(srn); R["doc"].append(doc)
        R["e"].append(e_ix[ent]); R["d"].append(d_ix[div]); R["g"].append(gl_ix[gl])
        R["c"].append(-1 if cc is None else c_ix[cc]); R["m"].append(m_ix[ym])
        R["a"].append(a); R["b"].append(b); R["f"].append(f); R["p"].append(p)
        R["sab"].append(SIGNCAT[s1]); R["saf"].append(SIGNCAT[s2]); R["sap"].append(SIGNCAT[s3])
        restored = (sfa if sfa is not None else 1) != 1
        R["rs"].append(0 if not restored else (1 if sconf == "HIGH" else 2))
        R["dp"].append(DUP[dup]); R["sg"].append(SIGNFLAG[sgn])
        if restored:
            parsed[n] = [pa, pb, pf, pp]
        elif (pa, pb, pf, pp) != (a, b, f, p):
            raise SystemExit(f"parsed != adjusted on unrestored row {srn}")
        if gl == 6100 and fte is not None and fte > 0:
            hc[n] = fte
        n += 1

    # Non-Posted lines of the any-status population (steps 1-4 and 6-8 of the exclusion precedence). Posted lines are
    # the main R arrays. Embedded at LINE grain so status diagnostics honour every filter and scenario.
    STATUS_IX = {"Pending": 1, "Parked": 2, "Rejected": 3, "(blank)": 4}
    X = {k: [] for k in "src st e d g c m a rs dp sg".split()}
    xparsed = {}
    xq = """select source_row_number, status_group, entity_code, division, gl_account, cost_center_code, period_ym,
        actual_usd_adj, actual_usd_parsed, scale_factor_applied, scale_confidence, dup_tier, sign_flag
        from v_pl_actual_any_status where status_group <> 'Posted' order by source_row_number"""
    xn = 0
    for srn, st, ent, div, gl, cc, ym, a, pa, sfa, sconf, dup, sgn in con.execute(xq).fetchall():
        X["src"].append(srn); X["st"].append(STATUS_IX[st]); X["e"].append(e_ix[ent]); X["d"].append(d_ix[div]); X["g"].append(gl_ix[gl])
        X["c"].append(-1 if cc is None else c_ix[cc]); X["m"].append(m_ix[ym]); X["a"].append(a)
        restored = (sfa if sfa is not None else 1) != 1
        X["rs"].append(0 if not restored else (1 if sconf == "HIGH" else 2)); X["dp"].append(DUP[dup]); X["sg"].append(SIGNFLAG[sgn])
        if restored:
            xparsed[xn] = pa
        elif pa != a:
            raise SystemExit(f"parsed != adjusted on unrestored non-Posted row {srn}")
        xn += 1

    ranking, ins = parse_register()
    ref = {k: csv_table(k) for k in [
        "b1_variance_section", "b6_variance_persistence", "b8_variance_bridge", "c1_forecast_section", "c6_forecast_vs_budget",
        "d1_vs_py_column", "d3_true_yoy", "e1_gross_profit", "e3_gross_profit_vs_budget", "e4_gp_variance_bridge", "f1_cost_by_gl",
        "f2_concentration", "f5_persistent_cells", "f6_salary_per_fte", "g1_monthly_series", "i1_scenarios", "i2_factor_ranking",
        "i3_variance_robustness", "i4_undetermined_scale", "i5_restored_exposure", "i6_duplicate_exposure", "i8_flag_exposure",
        "i9_exclusion_waterfall", "a6_period_coverage"]}
    # Excel workbook workbook cross-check values, read from its manifest if present
    excel_manifest = {}
    mf = ROOT / "excel" / "MANIFEST.json"
    if mf.exists():
        excel_manifest = json.loads(mf.read_text(encoding="utf-8"))

    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

    meta = {
        "csv_sha256": sha(ROOT / "data/processed/fpa_monthly_close_cleaned.csv"),
        "raw_sha256": sha(ROOT / "data/raw/fpa_monthly_close_raw_messy.csv"),
        "db_sha256": sha(DB),
        "xlsx_sha256": sha(ROOT / "excel" / "fpa_month_end_close_analysis.xlsx"),
        "rows_total_source": con.execute("select count(*) from fact_close").fetchone()[0],
        "rows_pl_eligible": n,
        "rows_budget": con.execute("select count(*) from v_pl_budget").fetchone()[0],
        "rows_any_status": con.execute("select count(*) from v_pl_actual_any_status").fetchone()[0],
        "rows_nonposted": xn,
        "excel_manifest_keys": sorted(excel_manifest.keys())[:20] if isinstance(excel_manifest, dict) else [],
    }
    payload = {
        "meta": meta,
        "ents": [{"c": e[0], "n": e[1]} for e in ents], "divs": divs, "ccs": ccs, "months": months, "gls": gls,
        "secs": SEC_ORDER,
        "R": R, "parsed": parsed, "hc": hc, "X": X, "xparsed": xparsed, "ref": ref, "rank": ranking, "ins": ins,
    }
    js = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    tpl = TEMPLATE.read_text(encoding="utf-8")
    css = (ROOT / "src/dashboard_style.css").read_text(encoding="utf-8")
    jsapp = (ROOT / "src/dashboard_core.js").read_text(encoding="utf-8") + "\n" + (ROOT / "src/dashboard_views.js").read_text(encoding="utf-8")
    assert "/*__PAYLOAD__*/" not in css + jsapp
    tpl = tpl.replace("/*__CSS__*/", css).replace("/*__JS__*/", jsapp.replace("</script", "<\\/script"))
    assert tpl.count("/*__PAYLOAD__*/null") == 1
    out = tpl.replace("/*__PAYLOAD__*/null", js.replace("</", "<\\/"))
    dest = OUT / "fpa_financial_analytics_dashboard.html"
    dest.write_text(out, encoding="utf-8")
    stats = {"html_bytes": dest.stat().st_size, "payload_bytes": len(js), "rows": n, "restored_rows": len(parsed), "fte_rows": len(hc), "nonposted_status_rows": xn, "nonposted_restored_rows": len(xparsed)}
    (STATS_DIR / "payload_stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(stats)


if __name__ == "__main__":
    main()
