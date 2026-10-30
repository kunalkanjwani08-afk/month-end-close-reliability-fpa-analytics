"""Excel workbook tests - they open the SAVED workbook (excel/fpa_month_end_close_analysis.xlsx), never the in-memory writer.

Run from the repository root:   python -m pytest tests/test_excel_workbook_builder.py -q
Prerequisite: python src/excel_workbook_builder.py has been run (the workbook and MANIFEST.json exist).

What is proven here, and what is not
  * Totals, populations, variance/% logic, forecast and gross-profit figures are re-derived from the SQL analysis DATABASE VIEWS in this
    file (independent of the out_* tables the workbook was built from) and compared with the saved file's cached values.
  * Every formula is recalculated by LibreOffice (a different calculation engine) from a copy that has no cached values; the
    results must equal the saved cached values. Microsoft Excel itself was NOT used.
  * A tamper test edits one input in a copy of the workbook, recalculates it, and requires the reconciliation sheet to FAIL,
    proving the PASS/FAIL formulas can fail.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import duckdb
import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import sql_analysis_pipeline as sqlp  # noqa: E402
import excel_workbook_builder as xlb  # noqa: E402

OUT = ROOT / "excel"
XLSX = OUT / xlb.WORKBOOK_NAME
MANIFEST = OUT / "MANIFEST.json"
DB = sqlp.DEFAULT_DB
CSV = sqlp.DEFAULT_CSV
FIXED = dt.datetime(2026, 10, 29, 12, 0, 0)

pytestmark = pytest.mark.skipif(not XLSX.exists(), reason="workbook not generated yet: run python src/excel_workbook_builder.py")
needs_lo = pytest.mark.skipif(not (shutil.which("soffice") or shutil.which("libreoffice")), reason="LibreOffice not available")
needs_csv = pytest.mark.skipif(not CSV.exists(), reason="canonical cleaned CSV not present (data/processed/)")


# ---------------------------------------------------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def wf():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return openpyxl.load_workbook(XLSX)


@pytest.fixture(scope="module")
def wv():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return openpyxl.load_workbook(XLSX, data_only=True)


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def scan():
    return xlb.scan_saved_workbook(XLSX)


def find_row(ws, col, text, start=1, exact=True):
    for r in range(start, ws.max_row + 1):
        v = ws.cell(r, col).value
        if isinstance(v, str) and ((v == text) if exact else (text in v)):
            return r
    raise AssertionError(f"'{text}' not found in column {col} of {ws.title}")


def header_map(ws, row):
    return {str(ws.cell(row, c).value): c for c in range(1, ws.max_column + 1) if ws.cell(row, c).value is not None}


def approx(a, b, rel=1e-9, ab=1e-6):
    return abs(a - b) <= max(ab, rel * max(abs(a), abs(b)))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# 1. structure
# ---------------------------------------------------------------------------------------------------------------------
def test_workbook_opens_and_has_the_twelve_sheets_in_order(wf):
    assert wf.sheetnames == xlb.SHEETS and len(wf.sheetnames) == 12


def test_every_sheet_has_content_and_a_title(wf):
    for ws in wf.worksheets:
        assert ws.max_row > 10 and ws.max_column >= 2, ws.title
        assert isinstance(ws["A1"].value, str) and len(ws["A1"].value) > 5, ws.title


def test_source_tables_present_with_expected_row_counts(scan, con):
    # table name -> (sheet, rows in the database source it is built from)
    expect = {"tbl_MonthlyPL": ("Monthly P&L", "SELECT count(DISTINCT period_ym) FROM out_a1_pl_period_section"),
              "tbl_EntityGL": ("Entity & Division", "SELECT count(*) FROM out_b2_variance_entity_gl"),
              "tbl_GLActivity": ("GL & Cost Drivers", "SELECT count(*) FROM out_a4_pl_gl"),
              "tbl_PersistentCells": ("GL & Cost Drivers", "SELECT count(*) FROM out_f5_persistent_cells"),
              "tbl_BvA_Monthly": ("Budget vs Actual", "SELECT count(*) FROM out_b4_variance_monthly"),
              "tbl_GP": ("Gross Profit", "SELECT count(*) FROM out_e1_gross_profit"),
              "tbl_GPEntity": ("Gross Profit", "SELECT count(*) FROM out_e2_gross_profit_entity"),
              "tbl_TrueYoY": ("Forecast & Prior Year", "SELECT count(*) FROM out_d3_true_yoy"),
              "tbl_FcEntity": ("Forecast & Prior Year", "SELECT count(*) FROM out_c3_forecast_entity"),
              "tbl_PYColumn": ("Forecast & Prior Year", "SELECT count(*) FROM out_d1_vs_py_column"),
              "tbl_Scenarios": ("Data Quality", "SELECT count(*) FROM out_i1_scenarios"),
              "tbl_FlagExposure": ("Data Quality", "SELECT count(*) FROM out_i8_flag_exposure"),
              "tbl_DimReliability": ("Data Quality", "SELECT count(*) FROM out_a5_dimension_reliability"),
              "tbl_Rules": ("Definitions", None)}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(XLSX)
    found = {}
    for ws in wb.worksheets:
        for t in ws.tables.values():
            name = t.name
            a, b = t.ref.split(":")
            found[name] = (ws.title, openpyxl.utils.cell.coordinate_from_string(b)[1] - openpyxl.utils.cell.coordinate_from_string(a)[1])
    for name, (sheet, sql) in expect.items():
        assert name in found and found[name][0] == sheet, f"table {name} missing on {sheet}"
        if sql:
            assert found[name][1] == con.execute(sql).fetchone()[0], f"{name}: data rows differ from the database"
    assert found["tbl_Rules"][1] == 14


def test_features_charts_tables_freeze_panes_filters(scan, wf):
    assert scan["tables"] >= 14
    assert scan["charts"] >= 7, "a few readable titled charts are required"
    for n in ("Monthly P&L", "Budget vs Actual", "Forecast & Prior Year", "Entity & Division", "GL & Cost Drivers", "Gross Profit", "Data Quality", "Reconciliation & QA", "Definitions", "Insights & Actions"):
        assert wf[n].freeze_panes, f"{n}: no freeze panes"
    assert scan["merged_in_tables"] == [], "merged cells inside data tables"
    for n in ("Monthly P&L", "Budget vs Actual", "Gross Profit"):
        assert len(wf[n].conditional_formatting) >= 1, f"{n}: conditional formatting missing"


def test_charts_have_titles(tmp_path):
    import zipfile
    with zipfile.ZipFile(XLSX) as z:
        charts = [n for n in z.namelist() if n.startswith("xl/charts/chart")]
        assert len(charts) >= 7
        for n in charts:
            assert b"<c:title>" in z.read(n), f"{n} has no title"


# ---------------------------------------------------------------------------------------------------------------------
# 2. formulas: present, sane, error-free, no external links
# ---------------------------------------------------------------------------------------------------------------------
def test_formulas_present_and_all_cached(scan):
    assert scan["formulas"] >= 3000
    assert scan["uncached"] == [], scan["uncached"][:5]
    for n in xlb.SHEETS:
        assert n in scan["per_sheet"]
    assert scan["per_sheet"]["Reconciliation & QA"]["formulas"] > 300


def test_no_formula_errors(scan):
    assert scan["formula_errors"] == [], scan["formula_errors"][:10]


def test_no_external_links_anywhere(scan, wf):
    assert scan["external_refs"] == [] and scan["external_link_parts"] == [] and scan["external_targets"] == []
    assert not wf._external_links
    # hyperlinks must all be internal
    for ws in wf.worksheets:
        for h in ws._hyperlinks:
            assert not h.target or not re.match(r"^(https?|file|ftp):", str(h.target)), (ws.title, h.target)
    for ws in wf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    assert not re.search(r"https?://|file:|\.xls|\[\d+\]", c.value), (ws.title, c.coordinate)


def test_cross_sheet_references_resolve_to_populated_cells(wf):
    ref_re = re.compile(r"'([^']+)'!\$?([A-Z]{1,3})\$?(\d+)(?![\d:])")
    bad, n = [], 0
    for ws in wf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    for sh, col, r in ref_re.findall(c.value):
                        n += 1
                        if sh not in wf.sheetnames:
                            bad.append((ws.title, c.coordinate, "no sheet " + sh))
                        elif wf[sh][f"{col}{r}"].value is None:
                            bad.append((ws.title, c.coordinate, f"{sh}!{col}{r} is empty"))
    assert n >= 100 and bad == [], bad[:10]


def test_range_references_stay_inside_their_tables(wf):
    # every SUMIFS/SUM range over a column must start and end at data rows, not at headers/blank space
    rng_re = re.compile(r"(?:'([^']+)'!)?\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?(\d+)")
    for ws in wf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("=") and ":" in c.value:
                    for sh, c1, r1, c2, r2 in rng_re.findall(c.value):
                        t = wf[sh] if sh else ws
                        assert c1 == c2 and int(r2) >= int(r1)
                        cells = [t[f"{c1}{i}"].value for i in range(int(r1), int(r2) + 1)]
                        assert int(r2) <= t.max_row and any(v is not None for v in cells), (ws.title, c.coordinate, c.value[:80])
                        assert cells[0] is not None and cells[-1] is not None, (ws.title, c.coordinate, "range starts or ends on an empty cell")


@needs_lo
def test_every_formula_recalculates_identically_in_libreoffice():
    idn = xlb.verify_sql_analysis(DB, sqlp.DEFAULT_OUT, None)
    res = xlb.libreoffice_recalc_compare(DB, idn, FIXED, xlb.sha256_file(ROOT / "src" / "excel_workbook_builder.py"), shipped_path=XLSX)
    assert res["available"], res
    assert res["formulas_compared"] >= 3000
    assert res["ok"], res["examples"]


@needs_lo
def test_reconciliation_fails_when_a_number_is_tampered(tmp_path, wf):
    """Mutation test: change one input in a copy, recalculate, and the reconciliation sheet must say FAIL."""
    ws = wf["Monthly P&L"]
    hr = find_row(ws, 1, "Month")
    col = header_map(ws, hr)["Revenue (USD)"]
    cell = ws.cell(hr + 1, col)
    assert isinstance(cell.value, (int, float))
    cell.value = cell.value + 1000.0
    bad = tmp_path / "tampered.xlsx"
    wf.save(bad)
    work = tmp_path / "w"
    work.mkdir()
    out = xlb.lo_recalc_convert(bad, tmp_path / "lo", work)
    assert out is not None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t = openpyxl.load_workbook(out, data_only=True)
    status = t["Reconciliation & QA"]["B5"].value
    assert "FAIL" in str(status), status
    results = [t["Reconciliation & QA"].cell(r, 8).value for r in range(10, 123)]
    assert results.count("FAIL") >= 2, "tampering one month must break the 36-month revenue total and the 2023 revenue row"
    failed_ids = [t["Reconciliation & QA"].cell(r, 1).value for r in range(10, 123) if t["Reconciliation & QA"].cell(r, 8).value == "FAIL"]
    assert "R-04" in failed_ids and "R-13-2023" in failed_ids, failed_ids


# ---------------------------------------------------------------------------------------------------------------------
# 3. reconciliation sheet
# ---------------------------------------------------------------------------------------------------------------------
def test_reconciliation_sheet_all_checks_pass_and_are_real_comparisons(wf, wv):
    sv, sf = wv["Reconciliation & QA"], wf["Reconciliation & QA"]
    hr = find_row(sf, 1, "ID")
    hm = header_map(sf, hr)
    assert list(hm)[:8] == ["ID", "Area", "Check", "Expected (independent source)", "Workbook value", "Difference", "Tolerance", "Result"]
    rows = [r for r in range(hr + 1, sf.max_row + 1) if isinstance(sf.cell(r, 1).value, str) and re.match(r"R-\d", sf.cell(r, 1).value)]
    assert len(rows) >= 100
    ids = [sf.cell(r, 1).value for r in rows]
    assert len(ids) == len(set(ids)), "duplicate check ids"
    for r in rows:
        exp, wbk, diff, tol, res = (sf.cell(r, c).value for c in (4, 5, 6, 7, 8))
        assert isinstance(exp, (int, float)) and not isinstance(exp, bool), f"row {r}: expected must be a hard number from the independent source"
        assert isinstance(wbk, str) and wbk.startswith("="), f"row {r}: workbook value must be a live link"
        assert diff == f"=ROUND(E{r}-D{r},6)"
        assert isinstance(tol, (int, float))
        assert res == f'=IF(ABS(F{r})<={"G"}{r},"PASS","FAIL")'
        assert sv.cell(r, 8).value == "PASS", (sf.cell(r, 1).value, sv.cell(r, 3).value, sv.cell(r, 4).value, sv.cell(r, 5).value)
    assert sv["B5"].value == f"ALL {len(rows)} CHECKS PASS"
    for area in ("Population", "Monthly P&L", "Budget vs Actual", "Forecast", "Gross Profit", "Cross-sheet", "Entity", "Insights", "Data Quality", "Definitions"):
        assert any(sv.cell(r, 2).value == area for r in rows), area


def test_summary_and_exec_status_link_to_reconciliation(wv):
    s = wv["Reconciliation & QA"]["B5"].value
    assert wv["Executive Summary"]["B25"].value == s or any(wv["Executive Summary"].cell(r, 2).value == s for r in range(1, 40))
    assert any(wv["Start Here"].cell(r, 2).value == s for r in range(1, 60))


# ---------------------------------------------------------------------------------------------------------------------
# 4. numbers vs SQL (independent of the out_* tables)
# ---------------------------------------------------------------------------------------------------------------------
def monthly_total_row(wv):
    ws = wv["Monthly P&L"]
    hr = find_row(ws, 1, "Month")
    tr = find_row(ws, 1, "Total Jan 2023 - Dec 2025", start=hr)
    return ws, hr, tr, header_map(ws, hr)


def test_populations_match_sql(wv, con):
    ws, hr, tr, hm = monthly_total_row(wv)
    assert ws.cell(tr, hm["Eligible lines (count)"]).value == con.execute("SELECT count(*) FROM v_pl_actual").fetchone()[0] == 58340
    dq = wv["Data Quality"]
    r = find_row(dq, 1, "Total source rows")
    assert dq.cell(r, 2).value == con.execute("SELECT count(*) FROM v_close").fetchone()[0] == 152682
    bva = wv["Budget vs Actual"]
    # budgeted universe = sum of A2 (all lines) rows
    hr2 = find_row(bva, 1, "A2. By section - ALL lines (sensitivity)")
    hdr = find_row(bva, 1, "Section", start=hr2)
    n = sum(bva.cell(hdr + i, 2).value for i in range(1, 8))
    assert n == con.execute("SELECT count(*) FROM v_pl_actual WHERE budget_usd_adj IS NOT NULL").fetchone()[0] == 55043


def test_monthly_totals_match_sql_by_section(wv, con):
    ws, hr, tr, hm = monthly_total_row(wv)
    exp = dict(con.execute("SELECT section, sum(actual_usd_adj) FROM v_pl_actual GROUP BY 1").fetchall())
    cols = {"REVENUE": "Revenue (USD)", "COGS": "COGS (USD)", "PEOPLE": "People costs (USD)", "OPEX": "Operating expenses (USD)", "D&A": "Memo: D&A (USD)",
            "BELOW_EBITDA": "Memo: Below-EBITDA (USD)", "TAX": "Memo: Tax (USD)"}
    for sec, h in cols.items():
        assert approx(ws.cell(tr, hm[h]).value, exp[sec], ab=0.01), sec
    rev, cogs = exp["REVENUE"], exp["COGS"]
    assert approx(ws.cell(tr, hm["Gross profit, S1 signed as recorded (USD)"]).value, rev - cogs, ab=0.01)
    assert approx(ws.cell(tr, hm["Operating result proxy (USD) - not EBITDA"]).value, rev - cogs - exp["PEOPLE"] - exp["OPEX"], ab=0.01)


def test_monthly_rows_match_sql_month_by_month(wv, con):
    ws, hr, tr, hm = monthly_total_row(wv)
    exp = {(r[0], r[1]): r[2] for r in con.execute("SELECT period_ym, section, sum(actual_usd_adj) FROM v_pl_actual GROUP BY 1,2").fetchall()}
    n = 0
    for r in range(hr + 1, tr - 1):
        d = ws.cell(r, 1).value
        if not isinstance(d, dt.datetime):
            continue
        ym = d.strftime("%Y-%m")
        assert approx(ws.cell(r, hm["Revenue (USD)"]).value, exp[(ym, "REVENUE")], ab=0.01), ym
        assert approx(ws.cell(r, hm["COGS (USD)"]).value, exp[(ym, "COGS")], ab=0.01), ym
        n += 1
    assert n == 36


def test_signs_are_as_recorded_not_flipped(wv, con):
    # GL 4190 (discounts) is mixed-sign: the workbook's signed total must equal the signed SQL total, not the absolute value
    ws = wv["GL & Cost Drivers"]
    hr = find_row(ws, 1, "GL")
    r = next(i for i in range(hr + 1, hr + 30) if ws.cell(i, 1).value in (4190, "4190"))
    hm = header_map(ws, hr)
    signed = ws.cell(r, hm["Actual, signed (USD)"]).value
    sql = con.execute("SELECT sum(actual_usd_adj) FROM v_pl_actual WHERE gl_account = 4190").fetchone()[0]
    assert approx(signed, sql, ab=0.01)
    assert not approx(signed, con.execute("SELECT sum(abs(actual_usd_adj)) FROM v_pl_actual WHERE gl_account = 4190").fetchone()[0], ab=0.01)


def test_entity_and_division_totals_equal_monthly_total(wv):
    ws, hr, tr, hm = monthly_total_row(wv)
    rev = ws.cell(tr, hm["Revenue (USD)"]).value
    ed = wv["Entity & Division"]
    for label in ("Group",):
        rows = [r for r in range(1, ed.max_row + 1) if ed.cell(r, 1).value == label and isinstance(ed.cell(r, 3).value, (int, float))]
        assert len(rows) == 2, rows       # entity total and division total
        for r in rows:
            assert approx(ed.cell(r, 3).value, rev, ab=0.01)


def test_variance_and_percent_formulas_and_guard(wf, wv, con):
    f, v = wf["Budget vs Actual"], wv["Budget vs Actual"]
    h = find_row(f, 1, "A1. By section - SAME-SIGN lines (primary basis)")
    hdr = find_row(f, 1, "Section", start=h)
    hm = header_map(f, hdr)
    b1 = {r[0]: r for r in con.execute("SELECT section, actual_usd, budget_usd, budget_netting_ratio, variance_pct_of_abs_budget, net_variance_usd FROM out_b1_variance_section WHERE scenario='SAME_SIGN_ONLY'").fetchall()}
    secmap = {v_: k for k, v_ in xlb.SEC_LABEL.items()}
    checked_pct = checked_guard = 0
    for i in range(1, 8):
        r = hdr + i
        sec = secmap[f.cell(r, 1).value]
        var_f = f.cell(r, hm["Net variance = actual - budget (USD)"]).value
        assert var_f == f"=C{r}-D{r}"                         # variance = actual - budget
        pct_f = f.cell(r, hm["Variance % of |budget| (guarded)"]).value
        assert "ABS(" in pct_f and "$D$5" in pct_f           # |budget| denominator + guard threshold cell
        act, bud, ratio, pub, var_sql = b1[sec][1:]
        assert approx(v.cell(r, 3).value, act, ab=0.01) and approx(v.cell(r, 4).value, bud, ab=0.01)
        assert approx(v.cell(r, 5).value, act - bud, ab=0.01) and approx(var_sql, act - bud, ab=0.01)
        shown = v.cell(r, hm["Variance % of |budget| (guarded)"]).value
        if ratio >= 0.5:
            assert approx(shown, (act - bud) / abs(bud), rel=1e-9, ab=1e-12)
            if pub is not None:
                assert approx(shown, pub, rel=1e-9, ab=1e-12)
                checked_pct += 1
        else:
            assert shown == "n/a (guard)" and pub is None   # guard suppresses the % exactly where SQL analysis does
            checked_guard += 1
    assert checked_pct >= 4
    assert f["D5"].value == 0.5 and f["D5"].font.color.rgb.endswith("0000FF")  # guard is a blue input


def test_guard_cases_exist_and_are_suppressed_in_the_monthly_table(wv, con):
    ws = wv["Budget vs Actual"]
    hr = find_row(ws, 1, "Basis", start=find_row(ws, 1, "D. Monthly variance by section (out_b4; filter by Basis and Section)"))
    hm = header_map(ws, hr)
    n_guard = n_ok = 0
    for r in range(hr + 1, hr + 1 + con.execute("SELECT count(*) FROM out_b4_variance_monthly").fetchone()[0]):
        chk = ws.cell(r, hm["Check"]).value
        assert chk in ("OK", "guard"), (r, chk)
        n_guard += chk == "guard"
        n_ok += chk == "OK"
    assert n_ok > 100
    assert con.execute("SELECT count(*) FROM out_b4_variance_monthly WHERE variance_pct_of_abs_budget IS NULL").fetchone()[0] == n_guard


def test_bridge_difference_is_zero_everywhere(wv):
    ws = wv["Budget vs Actual"]
    hr = find_row(ws, 1, "Section", start=find_row(ws, 1, "A3. Bridge: all-lines net variance = same-sign + opposite-sign + zero-involved (out_b8)"))
    hm = header_map(ws, hr)
    col = [c for h, c in hm.items() if h.startswith("Bridge difference")][0]
    vals = [ws.cell(hr + i, col).value for i in range(1, 8)]
    assert all(abs(x) < 0.5 for x in vals)


def test_forecast_figures_match_sql(wv, con):
    ws = wv["Forecast & Prior Year"]
    exp = {(r[0], r[1]): r for r in con.execute("SELECT scenario, section, count(*), sum(error), sum(abs(error)), sum(abs(actual)) FROM v_fc_scn GROUP BY 1,2").fetchall()}
    h = find_row(ws, 1, "F1. Forecast vs actual - SAME-SIGN lines (actual and forecast non-zero, same sign)")
    hdr = find_row(ws, 1, "Section", start=h)
    hm = header_map(ws, hdr)
    secmap = {v_: k for k, v_ in xlb.SEC_LABEL.items()}
    for i in range(1, 8):
        r = hdr + i
        sec = secmap[ws.cell(r, 1).value]
        if ("SAME_SIGN_ONLY", sec) not in exp:
            continue
        n, net, ae, aa = exp[("SAME_SIGN_ONLY", sec)][2:]
        assert ws.cell(r, hm["Lines (count)"]).value == n
        assert approx(ws.cell(r, hm["Net error = forecast - actual (USD)"]).value, net, ab=0.01)
        assert approx(ws.cell(r, hm["WAPE = abs error / abs actual"]).value, ae / aa, ab=1e-9)
        assert approx(ws.cell(r, hm["Bias = net error / abs actual"]).value, net / aa, ab=1e-9)


def test_gross_profit_treatments_match_sql_and_row_set_is_not_called_sign_consistent(wv, wf, con):
    ws = wv["Gross Profit"]
    exp = {(r[0], r[1]): (r[2], r[3]) for r in con.execute("SELECT rowset, treatment, sum(revenue), sum(cogs) FROM v_gp_rows GROUP BY 1,2").fetchall()}
    hr = find_row(ws, 1, "Row set")
    hm = header_map(ws, hr)
    got = {}
    for r in range(hr + 1, hr + 1 + con.execute("SELECT count(*) FROM out_e1_gross_profit").fetchone()[0]):
        if ws.cell(r, hm["Period"]).value == "ALL YEARS":
            got[(ws.cell(r, 1).value, ws.cell(r, 2).value)] = ws.cell(r, hm["Gross profit (USD)"]).value
    assert len(got) == 6
    for (rs, t), (rev, cogs) in exp.items():
        label = (xlb.ROWSET[rs], xlb.TREAT[t])
        assert approx(got[label], rev - cogs, ab=0.01), label
    for row in wf["Gross Profit"].iter_rows():
        for c in row:
            if isinstance(c.value, str) and "sign-consistent" in c.value.lower():
                assert "not" in c.value.lower(), c.value     # the row set is only ever described as 'NOT sign-consistent'
    assert any("ROWS_ALL_NON_NEGATIVE" in str(c.value) or "NOT sign-consistent" in str(c.value) for row in wf["Gross Profit"].iter_rows() for c in row if isinstance(c.value, str))
    assert len({round(v) for v in got.values()}) == 6                    # all three treatments x two row sets are visibly different numbers


# ---------------------------------------------------------------------------------------------------------------------
# 5. insights
# ---------------------------------------------------------------------------------------------------------------------
def test_insight_blocks_have_all_16_fields_and_match_the_register(wv):
    reg = xlb.parse_register(ROOT / "docs" / "INSIGHT_REGISTER.md")
    assert len(reg) == 7
    ws = wv["Insights & Actions"]
    labels = ["1. Insight ID and headline", "2. Business question", "3. Period and population", "4. Quantified financial result (observed fact)", "5. Formula and metric definition",
              "6. Comparison / baseline", "7. Driver breakdown and contribution", "8. Validation evidence / SQL analysis reference", "9. Observed fact vs hypothesis",
              "10. Confidence level and reasons", "11. Data limitations", "12. Recommended action", "13. Expected impact (only where supportable)",
              "14. Evidence required to confirm the underlying cause", "15. Suggested owner (function / role)", "16. Follow-up KPI / validation step"]
    starts = [r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == labels[0]]
    assert len(starts) == 7
    ranks = []
    for s in starts:
        for j, lab in enumerate(labels):
            assert ws.cell(s + j, 1).value == lab
            txt = ws.cell(s + j, 2).value
            assert isinstance(txt, str) and len(txt.strip()) > 10, (lab, s)
        iid = ws.cell(s, 2).value[:6]
        assert ws.cell(s + 3, 2).value == reg[iid]["parts"][5], f"{iid}: observed result differs from the register"
        assert ws.cell(s + 11, 2).value == reg[iid]["parts"][11]
        ranks.append((reg[iid]["rank"], iid))
        # observed vs hypothesis separated, no savings claim
        assert "OBSERVED" in ws.cell(s + 8, 2).value and "HYPOTHESIS" in ws.cell(s + 8, 2).value
        assert not re.search(r"(?i)\bsavings? of \$|will save|recoverable savings? of", ws.cell(s + 12, 2).value), iid
    assert [r for r, _ in ranks] == [1, 2, 3, 4, 5, 6, 7], "insights must be ranked 1..7 in order"


def test_insight_amounts_are_recomputed_from_the_database(wv, wf, con):
    """Key figures are rebuilt here from the database views/tables, formatted like the register, and must appear in the saved insight text;
    the sheet's own FOUND formulas must say so too."""
    ws = wv["Insights & Actions"]
    text = {}
    for r in range(1, ws.max_row + 1):
        if ws.cell(r, 1).value == "4. Quantified financial result (observed fact)":
            text[ws.cell(r - 3, 2).value[:6]] = ws.cell(r, 2).value
    m = lambda x: ("-" if x < 0 else "") + f"${abs(x) / 1e6:,.2f}M"
    # INS-01 status scenarios
    rev = dict(con.execute("SELECT scenario, revenue_usd FROM out_i1_scenarios WHERE factor='status'").fetchall())
    for k in ("POSTED_ONLY (baseline)", "ALL_EXCEPT_REJECTED", "ALL_STATUSES"):
        assert f"{abs(rev[k]) / 1e6:,.2f}M" in text["INS-01"], k
    base = con.execute("SELECT sum(actual_usd_adj) FROM v_pl_actual WHERE section='REVENUE'").fetchone()[0]
    assert abs(base - rev["POSTED_ONLY (baseline)"]) < 1e-3
    # INS-03 same-sign variances straight from v_var_scn
    exp = {r[0]: r[1:] for r in con.execute("SELECT section, sum(actual)-sum(budget), sum(budget) FROM v_var_scn WHERE scenario='SAME_SIGN_ONLY' GROUP BY 1").fetchall()}
    for sec, lab in (("REVENUE", "Revenue"), ("COGS", "COGS"), ("PEOPLE", "people"), ("OPEX", "opex")):
        var, bud = exp[sec]
        pct = var / abs(bud) * 100
        assert f"{lab} {m(var)} ({pct:+.1f}%)" in text["INS-03"], (sec, m(var), pct)
    # INS-04 GP variance by treatment
    gp = {r[0]: r[1] for r in con.execute("SELECT treatment, (actual_revenue_usd - actual_cogs_usd) - (budget_revenue_usd - budget_cogs_usd) FROM out_e3_gross_profit_vs_budget").fetchall()}
    assert f"{m(gp['GP_S1_SIGNED_AS_RECORDED'])} (S1)" in text["INS-04"] and f"{m(gp['GP_S2_DISCOUNT_ABS'])} (S2)" in text["INS-04"] and f"{m(gp['GP_S3_EXCL_DISCOUNT'])} (S3)" in text["INS-04"]
    # INS-05 WAPE from v_fc_scn / matched lines table
    c6 = con.execute("SELECT wape_forecast, wape_budget FROM out_c6_forecast_vs_budget WHERE section='REVENUE'").fetchone()
    assert f"revenue WAPE: forecast {c6[0] * 100:.1f}% vs budget {c6[1] * 100:.1f}%" in text["INS-05"]
    cmp_ = con.execute("SELECT count(*), sum(abs(forecast_usd_adj-actual_usd_adj))/sum(abs(actual_usd_adj)), sum(abs(budget_usd_adj-actual_usd_adj))/sum(abs(actual_usd_adj)) "
                       "FROM v_pl_budget WHERE actual_usd_adj IS NOT NULL AND forecast_usd_adj IS NOT NULL AND section='REVENUE'").fetchone()
    assert f"revenue {cmp_[1] * 100:.1f}% vs {cmp_[2] * 100:.1f}% ({cmp_[0]:,} lines)" in text["INS-05"]
    # INS-06 implied FTE-months
    for ent, fte in con.execute("SELECT entity_code, implied_excess_fte_months FROM out_f7_salary_implied_fte").fetchall():
        assert f"{ent} {fte:.0f}" in text["INS-06"], ent
    # INS-07 scale restoration effect on the result proxy
    sc = dict(con.execute("SELECT scenario, result_proxy_usd FROM out_i1_scenarios WHERE factor='scale'").fetchall())
    assert f"${abs(sc['ADJUSTED_ALL (baseline)'] - sc['RESTORE_HIGH_CONFIDENCE_ONLY']) / 1e6:.2f}M" in text["INS-07"]
    # sheet-internal formula checks
    fs = wf["Insights & Actions"]
    r0 = find_row(fs, 1, "Insight / figure")
    n = 0
    for r in range(r0 + 1, fs.max_row + 1):
        f = fs.cell(r, 3).value
        if isinstance(f, str) and f.startswith("=IF(ISNUMBER(SEARCH("):
            assert ws.cell(r, 3).value == "FOUND", ws.cell(r, 1).value
            n += 1
    assert n >= 12


def test_forecast_claims_are_not_overstated(wf):
    ws = wf["Forecast & Prior Year"]
    banner = ws["A3"].value
    assert "NO forecast version or as-of date" in banner and "NOT established" in banner
    ins = wf["Insights & Actions"]
    blob = " ".join(str(c.value) for row in ins.iter_rows() for c in row if isinstance(c.value, str))
    assert not re.search(r"(?i)bias correction (can|will) remove|forecast accuracy improved|forecasting skill (is|was) demonstrated", blob)
    assert "dated forecast snapshots" in blob or "Dated forecast snapshots" in blob


# ---------------------------------------------------------------------------------------------------------------------
# 6. assumptions, labels, definitions, lineage
# ---------------------------------------------------------------------------------------------------------------------
def all_strings(wb):
    return [(ws.title, c.coordinate, c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if isinstance(c.value, str) and not c.value.startswith("=")]


def test_provisional_labels_everywhere(wf):
    assert "PROVISIONAL" in wf["Start Here"]["A4"].value
    for n in ("Monthly P&L", "Budget vs Actual", "Forecast & Prior Year", "Entity & Division", "GL & Cost Drivers", "Gross Profit", "Insights & Actions", "Data Quality", "Executive Summary", "Definitions"):
        sub = wf[n]["A2"].value or ""
        banner = wf[n]["A3"].value or ""
        assert re.search(r"(?i)provisional|scale-adjusted|unresolved|no treatment|high spending|observed", sub + banner), n
    assert "Scale-adjusted" in wf["Monthly P&L"]["A2"].value or "scale-adjusted" in wf["Monthly P&L"]["A2"].value


def test_unresolved_rules_are_preserved_verbatim(wv):
    ws = wv["Definitions"]
    doc = (ROOT / "docs" / "FINANCIAL_METRICS.md").read_text(encoding="utf-8")
    hr = find_row(ws, 1, "Rule")
    got = {ws.cell(r, 1).value: ws.cell(r, 3).value for r in range(hr + 1, hr + 15)}
    assert list(got) == [f"R{i}" for i in range(1, 15)]
    for rid, status in got.items():
        m = re.search(rf"^\| {rid} \| .+? \| (.+?) \| .+ \|$", doc, flags=re.M)
        assert m.group(1).replace("`", "") == status, rid
    for rid in ("R9", "R11", "R12"):
        assert got[rid].startswith("Unresolved"), rid
    assert got["R6"].startswith("Proposed") and got["R10"].startswith("Proposed")


def test_no_forbidden_labels_or_invented_metrics(wf):
    strings = all_strings(wf)
    for sh, coord, s in strings:
        low = s.strip().lower()
        assert low not in ("favourable", "favorable", "unfavourable", "unfavorable", "adverse"), (sh, coord)
        assert not re.match(r"^(ebitda|on-?time close|close duration|days to close)\b", low), (sh, coord, s)
    # every header that mentions EBITDA must carry the 'not EBITDA' / 'Below-EBITDA' qualification
    for sh, coord, s in strings:
        if "EBITDA" in s and len(s) < 60:
            assert "not EBITDA" in s or "Below-EBITDA" in s or "BELOW_EBITDA" in s or "below-EBITDA" in s, (sh, coord, s)
    # direction columns are arithmetic only
    dirs = {s for _, _, s in strings if s.startswith("Actual above") or s.startswith("Actual below") or s == "On budget"}
    assert dirs <= {"Actual above budget", "Actual below budget", "On budget"}


def test_no_unit_economics_or_balance_sheet_balances(wf):
    blob = " ".join(s for _, _, s in all_strings(wf))
    assert "NOT built" in blob and "not period-end balances" in blob.lower()
    assert not re.search(r"(?i)\b(price[- ]volume[- ]mix analysis|revenue per unit|cost per unit)\b(?!.*not)", " ".join(s for sh, _, s in all_strings(wf) if sh in ("Monthly P&L", "GL & Cost Drivers") and len(s) < 60))
    assert "NOS" in blob and "EA" in blob   # the unit-of-measure caution names both units and does not equate them


def test_lineage_and_source_identity_recorded(wv, con):
    ws = wv["Reconciliation & QA"]
    r = find_row(ws, 1, "Source identity (recorded at generation)")
    facts = {ws.cell(i, 1).value: ws.cell(i, 3).value for i in range(r + 2, r + 20) if ws.cell(i, 1).value}
    assert facts["SQL analysis database SHA-256"] == sha(DB)
    assert facts["SQL analysis manifest SHA-256"] == sha(sqlp.DEFAULT_OUT / "MANIFEST.json")
    assert facts["Approved canonical cleaned CSV SHA-256"] == sqlp.EXPECTED_SHA256
    assert re.fullmatch(r"[0-9a-f]{64}", facts["Generator script SHA-256 (src/excel_workbook_builder.py)"])
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", facts["Generated at (UTC)"])
    for t in sqlp.REQUIRED_VALIDATION_TABLES:
        n, ok = con.execute(f"SELECT count(*), count(*) FILTER (WHERE status='PASS') FROM {t}").fetchone()
        assert facts[f"{t}: rows / PASS"] == f"{n} / {ok}" and n == ok
    d = wv["Definitions"]
    lin = find_row(d, 1, "D5. Lineage: sheet -> SQL analysis source -> check")
    names = {d.cell(r, 1).value for r in range(lin + 3, lin + 14)}
    assert set(xlb.SHEETS[1:-1]) <= names, set(xlb.SHEETS[1:-1]) - names


# ---------------------------------------------------------------------------------------------------------------------
# 7. design conventions
# ---------------------------------------------------------------------------------------------------------------------
def rgb(c):
    return (c.font.color.rgb if c.font and c.font.color and c.font.color.type == "rgb" else None) or ""


def test_colour_convention_blue_inputs_black_formulas_green_links(wf):
    ws = wf["Monthly P&L"]
    hr = find_row(ws, 1, "Month")
    hm = header_map(ws, hr)
    r = hr + 1
    assert rgb(ws.cell(r, hm["Revenue (USD)"])).endswith("0000FF")                                                   # input from SQL analysis
    assert rgb(ws.cell(r, hm["Gross profit, S1 signed as recorded (USD)"])).endswith("000000")                   # same-sheet formula
    assert rgb(wf["Executive Summary"]["B7"]).endswith("00703C")                                                      # cross-sheet link
    assert wf["Executive Summary"]["B7"].value.startswith("='Monthly P&L'!")
    assert not any(rgb(c).endswith("C00000") and isinstance(c.value, str) and c.value.startswith("=") for ws_ in wf.worksheets for row in ws_.iter_rows() for c in row), "red = external link: none allowed"
    # every cross-sheet formula that is a pure link must be green
    for ws_ in wf.worksheets:
        for row in ws_.iter_rows():
            for c in row:
                if isinstance(c.value, str) and re.fullmatch(r"='[^']+'!\$?[A-Z]+\$?\d+", c.value) and ws_.title not in ("Start Here",):
                    assert rgb(c).endswith("00703C"), (ws_.title, c.coordinate)


def test_number_formats_negatives_red_in_parentheses_zero_dash(wf):
    ws = wf["Monthly P&L"]
    hr = find_row(ws, 1, "Month")
    hm = header_map(ws, hr)
    nf = ws.cell(hr + 1, hm["Revenue (USD)"]).number_format
    assert "[Red](" in nf and '"-"' in nf
    assert "0.0%" in ws.cell(hr + 1, hm["Gross margin % (S1)"]).number_format


def test_tab_navigation_links_back_to_start(wf):
    for n in xlb.SHEETS[1:]:
        links = [h for h in wf[n]._hyperlinks]
        assert any("Start Here" in (h.location or "") for h in links), n


# ---------------------------------------------------------------------------------------------------------------------
# 8. generator behaviour: determinism, fail-closed gates, inputs untouched, manifest
# ---------------------------------------------------------------------------------------------------------------------
def test_generator_is_deterministic_and_does_not_touch_the_database(tmp_path):
    db_before = sha(DB)
    outs = []
    for i in range(2):
        d = tmp_path / f"o{i}"
        rc = xlb.main(["--out-dir", str(d), "--generated-at", "2026-10-29T12:00:00Z", "--csv", str(tmp_path / "nonexistent.csv")])
        assert rc == 0
        outs.append(sha(d / xlb.WORKBOOK_NAME))
        assert not [x for x in d.iterdir() if x.name.startswith(".p5stage_")], "staging folder left behind"
    assert outs[0] == outs[1], "same inputs and timestamp must give a byte-identical workbook"
    assert sha(DB) == db_before, "the generator must open the database read-only"


def test_generator_fails_closed_on_a_tampered_sql_output(tmp_path):
    sql_out_tmp = tmp_path / "sqlp"
    shutil.copytree(sqlp.DEFAULT_OUT, sql_out_tmp)
    victim = sorted(sql_out_tmp.glob("a1_*.csv"))[0]
    victim.write_text(victim.read_text(encoding="utf-8") + "\nTAMPERED\n", encoding="utf-8")
    out = tmp_path / "out"
    rc = xlb.main(["--sql-results-dir", str(sql_out_tmp), "--out-dir", str(out), "--csv", str(tmp_path / "x.csv")])
    assert rc == 2 and not (out / xlb.WORKBOOK_NAME).exists()
    with pytest.raises(xlb.IntegrityError):
        xlb.verify_sql_analysis(DB, sql_out_tmp, None)


def test_generator_exit_1_on_missing_inputs(tmp_path):
    assert xlb.main(["--db", str(tmp_path / "missing.duckdb"), "--out-dir", str(tmp_path / "o")]) == 1
    assert xlb.main(["--sql-results-dir", str(tmp_path / "nope"), "--out-dir", str(tmp_path / "o")]) == 1


def test_generator_refuses_failing_sql_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlp, "validation_failures", lambda con: [("out_val_load", "L01", "FAIL")])
    with pytest.raises(xlb.IntegrityError):
        xlb.verify_sql_analysis(DB, sqlp.DEFAULT_OUT, None)


def test_wrong_csv_hash_is_refused(tmp_path):
    bad = tmp_path / "wrong.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(xlb.IntegrityError):
        xlb.verify_sql_analysis(DB, sqlp.DEFAULT_OUT, bad)


@needs_csv
def test_canonical_csv_and_raw_csv_unchanged():
    assert sha(CSV) == sqlp.EXPECTED_SHA256
    raw = ROOT / "data" / "raw" / "fpa_monthly_close_raw_messy.csv"
    if raw.exists():
        assert sha(raw) == "a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff"


def test_manifest_matches_the_saved_workbook_and_inputs(wv):
    assert MANIFEST.exists()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["workbook_sha256"] == sha(XLSX) and m["workbook_bytes"] == XLSX.stat().st_size
    assert m["sheets"] == xlb.SHEETS and m["generator_sha256"] == sha(ROOT / "src" / "excel_workbook_builder.py")
    assert m["inputs"]["database_sha256"] == sha(DB)
    assert m["reconciliation"]["fail"] == 0 and m["reconciliation"]["checks"] == m["reconciliation"]["pass"]
    assert m["generator_warnings"] == []
    s = wv["Reconciliation & QA"]["B5"].value
    assert s == f"ALL {m['reconciliation']['checks']} CHECKS PASS"
    assert m["formula_cells"] == xlb.scan_saved_workbook(XLSX)["formulas"]


def test_generator_script_hash_in_workbook_equals_current_script(wv):
    ws = wv["Reconciliation & QA"]
    r = find_row(ws, 1, "Generator script SHA-256 (src/excel_workbook_builder.py)")
    assert ws.cell(r, 3).value == sha(ROOT / "src" / "excel_workbook_builder.py"), "workbook is stale: regenerate after editing the generator"


# ---------------------------------------------------------------------------------------------------------------------
# 7. Excel workbook review round: population clarity, account counts, wording, navigation
# ---------------------------------------------------------------------------------------------------------------------
def test_executive_summary_separates_the_three_forecast_populations(wv, con):
    ws = wv["Executive Summary"]
    r0 = find_row(ws, 1, "Population (revenue lines)")
    rows = {ws.cell(r0 + i, 1).value[0]: [ws.cell(r0 + i, c).value for c in (2, 3, 4)] for i in (1, 2, 3)}
    assert set(rows) == {"A", "B", "C"}
    a = con.execute("SELECT rows_compared, wape_forecast, wape_budget FROM out_c6_forecast_vs_budget WHERE section='REVENUE'").fetchone()
    b = con.execute("SELECT count(*), sum(abs(forecast_usd_adj-actual_usd_adj))/sum(abs(actual_usd_adj)), sum(abs(budget_usd_adj-actual_usd_adj))/sum(abs(actual_usd_adj)) "
                    "FROM v_pl_budget WHERE actual_usd_adj IS NOT NULL AND forecast_usd_adj IS NOT NULL AND section='REVENUE'").fetchone()
    c = con.execute("SELECT count(*), sum(abs(error))/sum(abs(actual)) FROM v_fc_scn WHERE scenario='ALL_LINES' AND section='REVENUE'").fetchone()
    assert rows["A"][0] == a[0] and approx(rows["A"][1], a[1]) and approx(rows["A"][2], a[2])
    assert rows["B"][0] == b[0] and approx(rows["B"][1], b[1]) and approx(rows["B"][2], b[2])
    assert rows["C"][0] == c[0] and approx(rows["C"][1], c[1]) and rows["C"][2] == "n/a"
    assert len({rows["A"][0], rows["B"][0], rows["C"][0]}) == 3          # three different populations, three different sample sizes
    blob = " ".join(str(c_.value) for row in ws.iter_rows() for c_ in row if isinstance(c_.value, str))
    assert "not general forecasting skill" in blob and "no forecast version or as-of date" in blob


def test_gl_headings_agree_with_the_database(wv, con):
    ws = wv["GL & Cost Drivers"]
    n_acc = con.execute("SELECT count(*) FROM out_a4_pl_gl").fetchone()[0]
    r1 = find_row(ws, 1, "G1.", exact=False)
    assert f"all {n_acc} P&L accounts" in ws.cell(r1, 1).value
    first = r1 + 3
    gl = [ws.cell(r, 1).value for r in range(first, first + 60) if isinstance(ws.cell(r, 1).value, (int, float))]
    assert len(set(gl[:n_acc])) == n_acc and gl[:n_acc] == sorted(gl[:n_acc])
    r2 = find_row(ws, 1, "G2.", exact=False)
    secs = dict(con.execute("SELECT section, count(*) FROM out_f1_cost_by_gl GROUP BY 1").fetchall())
    n_cost = sum(secs.values())
    assert f"{n_cost} cost accounts" in ws.cell(r2, 1).value
    note = " ".join(str(ws.cell(r2 + 1, c).value or "") for c in range(1, 4)) + str(ws.cell(r2, 1).value)
    assert set(secs) == {"COGS", "PEOPLE", "OPEX", "D&A"}
    assert "Below-EBITDA items and Tax are NOT in this population" in note and "COGS + People + Opex + D&A accounts only" in note
    assert "21 " not in ws.cell(r1, 1).value


def test_start_here_account_count_is_derived(wv, con):
    n_acc = con.execute("SELECT count(*) FROM out_a4_pl_gl").fetchone()[0]
    ws = wv["Start Here"]
    blob = " ".join(str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str))
    assert f"{n_acc} GL accounts" in blob and "21 GL accounts" not in blob


def test_comparable_population_table_and_reconciliation_checks_exist(wv, con):
    ws = wv["Forecast & Prior Year"]
    r0 = find_row(ws, 1, "F3b.", exact=False)
    hm = header_map(ws, r0 + 2)
    assert "Comparable lines (count)" in hm and any("negative = forecast closer" in h for h in hm)
    rec = wv["Reconciliation & QA"]
    ids = [rec.cell(r, 1).value for r in range(1, rec.max_row + 1)]
    for s in ("REVENUE", "COGS", "PEOPLE", "OPEX"):
        for k in ("R-17b-%s-N", "R-17b-%s-WF", "R-17b-%s-WB", "R-17c-%s-N", "R-17c-%s-WF", "R-17c-%s-WB"):
            assert k % s in ids, k % s


def test_insight_register_wording_is_evidence_bounded(wv):
    ws = wv["Insights & Actions"]
    blob = " ".join(str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str))
    assert not re.search(r"(?i)revenue shortfall|cost overrun|always on the optimistic|never move from a standard|in every month, entity and division", blob)
    assert "Driver category: opposite-sign" not in blob
    assert "same-sign lines in all 36 months, all 6 entities, all 5 divisions" in blob
    assert "does not show which journal-status policy is correct" in blob
    assert "Neither a pay-rate effect nor a headcount effect is established or excluded" in blob
    assert "not general for every section" not in blob


def test_universal_claim_counts_are_true_in_the_database(con):
    for sec, below in (("REVENUE", True), ("COGS", False), ("PEOPLE", False), ("OPEX", False)):
        for dim in ("period_ym", "entity_code", "division", "gl_account"):
            vals = [r[0] for r in con.execute(f"SELECT sum(actual)-sum(budget) FROM v_var_scn WHERE scenario='SAME_SIGN_ONLY' AND section=? GROUP BY {dim}", [sec]).fetchall()]
            assert vals and all((v < 0) == below and v != 0 for v in vals), (sec, dim)


def test_insight_ranking_links_to_detail_blocks(wf):
    ws = wf["Insights & Actions"]
    links = [(c.coordinate, c.hyperlink.location) for row in ws.iter_rows(min_row=5, max_row=16) for c in row if c.hyperlink is not None]
    assert len(links) >= 7
    back = [c for row in ws.iter_rows() for c in row if c.hyperlink is not None and c.value == "Back to ranking"]
    assert len(back) == 7


def test_gp_components_reconcile_to_the_stated_gap(con):
    v = {r[0]: r[1:] for r in con.execute("SELECT section, sum(actual)-sum(budget) FROM v_var_scn WHERE scenario='SAME_SIGN_ONLY' AND section IN ('REVENUE','COGS') GROUP BY 1").fetchall()}
    gap = v["REVENUE"][0] - v["COGS"][0]
    s1 = con.execute("SELECT (actual_revenue_usd-actual_cogs_usd)-(budget_revenue_usd-budget_cogs_usd) FROM out_e3_gross_profit_vs_budget WHERE treatment='GP_S1_SIGNED_AS_RECORDED'").fetchone()[0]
    assert abs(gap - s1) < 0.5
    assert abs(v["REVENUE"][0] / gap - 0.57) < 0.01 and abs(-v["COGS"][0] / gap - 0.43) < 0.01
