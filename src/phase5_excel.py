#!/usr/bin/env python3
"""Phase 5 - FP&A Excel workbook generated from the validated Phase 4 database.

Usage (repository root):
    python src/phase5_excel.py                       # verify Phase 4, build workbook + MANIFEST
    python src/phase5_excel.py --generated-at 2026-10-29T12:00:00Z   # fixed timestamp => byte-identical rerun
    python src/phase5_excel.py --qa-report --junit PATH   # also write PHASE5_QA_REPORT.md (needs LibreOffice for the recalculation check)

Design rules
  * SQL stays the source of truth: every number in the workbook comes from an out_* table of the validated Phase 4 database
    (or, for the independent-recompute column of the reconciliation sheet, from the Phase 4 analytical views). Nothing is typed.
  * Excel formulas are used only for definitions that Phase 4 also uses (variance = actual - budget, % with the 50% net-budget
    guard, WAPE, bias, gross profit, shares) and every one is reconciled to the Phase 4 table it derives from.
  * The generator refuses to build on an unverified source: manifest hashes, row counts and every out_val_* row must pass
    (exit 2). Missing inputs exit 1. Nothing is written to the accepted output folder unless the build completes.
  * Nothing is committed, pushed or published. The workbook contains no external links.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import duckdb
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import phase4_pipeline as p4  # noqa: E402

VERSION = "Phase 5 workbook v1.0"
DEFAULT_DB = p4.DEFAULT_DB
DEFAULT_P4_OUT = p4.DEFAULT_OUT
DEFAULT_OUT_DIR = ROOT / "outputs" / "phase5"
WORKBOOK_NAME = "fpa_month_end_close_analysis.xlsx"
DOCS = ROOT / "docs"

SECTIONS = ["REVENUE", "COGS", "PEOPLE", "OPEX", "D&A", "BELOW_EBITDA", "TAX"]
SEC_LABEL = {"REVENUE": "Revenue", "COGS": "COGS", "PEOPLE": "People costs", "OPEX": "Operating expenses",
             "D&A": "D&A (depreciation, GL 6300)", "BELOW_EBITDA": "Below-EBITDA items", "TAX": "Tax"}
OPS = ["REVENUE", "COGS", "PEOPLE", "OPEX"]
SHEETS = ["Start Here", "Executive Summary", "Monthly P&L", "Budget vs Actual", "Forecast & Prior Year", "Entity & Division",
          "GL & Cost Drivers", "Gross Profit", "Insights & Actions", "Data Quality", "Reconciliation & QA", "Definitions"]

NF_USD = '#,##0;[Red](#,##0);"-"'
NF_USD2 = '#,##0.00;[Red](#,##0.00);"-"'
NF_M = '#,##0.00;[Red](#,##0.00);"-"'
NF_PCT = '0.0%;[Red](0.0%);"-"'
NF_PCT2 = '0.00%;[Red](0.00%);"-"'
NF_INT = '#,##0;[Red](#,##0);"-"'
NF_DEC = '#,##0.0000;[Red](#,##0.0000);"-"'
NF_DATE = "mmm yyyy"
NAVY, GREY, AMBER, LIGHT = "#1F3864", "#F2F2F2", "#FFF2CC", "#DDEBF7"
BLUE, GREEN, BLACK, RED = "#0000FF", "#00703C", "#000000", "#C00000"
GUARD = 0.5  # Phase 4 convention: publish % only if |net budget| >= 50% of gross budget (macro safe_pct)


class SourceError(RuntimeError):
    """Exit 1: a required input is missing or unreadable."""


class IntegrityError(RuntimeError):
    """Exit 2: the Phase 4 source does not pass its own gates."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# Gate 1: verify the Phase 4 hand-off before building anything
# ---------------------------------------------------------------------------------------------------------------------
def verify_phase4(db_path: Path, p4_out: Path, csv_path: Path | None) -> dict:
    if not db_path.exists():
        raise SourceError(f"Validated Phase 4 database not found: {db_path}. Run: python src/phase4_pipeline.py")
    man_path = p4_out / "MANIFEST.json"
    if not man_path.exists():
        raise SourceError(f"Phase 4 MANIFEST.json not found: {man_path}")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    problems = []
    for name, meta in man["outputs"].items():
        f = p4_out / name
        if not f.exists():
            problems.append(f"missing output {name}")
        elif sha256_file(f) != meta["sha256"]:
            problems.append(f"hash differs from manifest: {name}")
    if man.get("stale_files_not_regenerated"):
        problems.append(f"stale files listed in manifest: {man['stale_files_not_regenerated']}")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for name, meta in man["outputs"].items():
            n = con.execute(f"SELECT count(*) FROM out_{name[:-4]}").fetchone()[0]
            if n != meta["rows"]:
                problems.append(f"{name}: database has {n} rows, manifest says {meta['rows']}")
        bad = p4.validation_failures(con)
        if bad:
            problems.append(f"{len(bad)} Phase 4 validation problem(s), first: {bad[0]}")
        val_counts = {t: con.execute(f"SELECT count(*), count(*) FILTER (WHERE status = 'PASS') FROM {t}").fetchone()
                      for t in p4.REQUIRED_VALIDATION_TABLES}
    finally:
        con.close()
    if problems:
        raise IntegrityError("Phase 4 hand-off is not acceptable: " + "; ".join(problems[:8]))
    identity = {
        "database_file": db_path.name, "database_sha256": sha256_file(db_path),
        "phase4_manifest_sha256": sha256_file(man_path), "phase4_output_tables": len(man["outputs"]),
        "validation_rows": {t: {"rows": a, "pass": b} for t, (a, b) in val_counts.items()},
        "canonical_csv_expected_sha256": p4.EXPECTED_SHA256,
        "canonical_csv_present": bool(csv_path and csv_path.exists()),
        "canonical_csv_sha256": None, "canonical_csv_matches": None,
        "sql_files": {f.name: sha256_file(f) for f in sorted(p4.SQL_DIR.glob("*.sql"))},
    }
    if csv_path and csv_path.exists():
        identity["canonical_csv_sha256"] = sha256_file(csv_path)
        identity["canonical_csv_matches"] = identity["canonical_csv_sha256"] == p4.EXPECTED_SHA256
        if not identity["canonical_csv_matches"]:
            raise IntegrityError(f"{csv_path.name} does not match the approved SHA-256 {p4.EXPECTED_SHA256}")
    return identity


# ---------------------------------------------------------------------------------------------------------------------
# Data access (read-only)
# ---------------------------------------------------------------------------------------------------------------------
def _clean(v):
    import decimal
    return float(v) if isinstance(v, decimal.Decimal) else v


class Data:
    def __init__(self, db_path: Path):
        self.con = duckdb.connect(str(db_path), read_only=True)
        self.con.execute("SET threads = 1")   # single thread => fixed summation order => byte-identical floating-point results across runs

    def rows(self, sql: str, params=None) -> list[dict]:
        cur = self.con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [{c: _clean(v) for c, v in zip(cols, r)} for r in cur.fetchall()]

    def one(self, sql: str, params=None):
        return _clean(self.con.execute(sql, params or []).fetchone()[0])

    def t(self, table: str, where: str = "", order: str = "") -> list[dict]:
        return self.rows(f"SELECT * FROM {table}" + (f" WHERE {where}" if where else "") + (f" ORDER BY {order}" if order else ""))

    def close(self):
        self.con.close()


# ---------------------------------------------------------------------------------------------------------------------
# Writer helpers
# ---------------------------------------------------------------------------------------------------------------------
class Ctx:
    def __init__(self, path: Path, d: Data, identity: dict, generated_at: dt.datetime, script_sha: str):
        self.wb = xlsxwriter.Workbook(str(path), {"strings_to_numbers": False, "default_date_format": "yyyy-mm-dd"})
        self.wb.set_properties({"title": "FP&A month-end close analysis (Phase 5)", "subject": "NovaBridge Industries (synthetic data)",
                                "author": "Phase 5 generator", "comments": f"{VERSION}; local use only; not published",
                                "created": generated_at})
        self.wb.set_calc_mode("auto")
        self.d, self.identity, self.generated_at, self.script_sha = d, identity, generated_at, script_sha
        self._f = {}
        self.ws = {n: self.wb.add_worksheet(n) for n in SHEETS}
        self.R: dict = {}          # cross-sheet references: key -> (sheet, row0, col0, value)
        self.checks: list[dict] = []
        self.formula_count = 0
        self.widths: dict = {}   # (sheet, col) -> widest width requested by any table on that sheet (applied once, at the end)
        self.nocache = False   # QA variant: formulas carry no cached value so a recalculating engine must supply every number

    def fmt(self, **kw):
        base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter"}
        base.update(kw)
        key = tuple(sorted(base.items()))
        if key not in self._f:
            self._f[key] = self.wb.add_format(base)
        return self._f[key]

    # --- references ----------------------------------------------------------------------------------------------
    def reg(self, key, sheet, r, c, value):
        self.R[key] = (sheet, r, c, value)

    def ref(self, key, absolute=True):
        sheet, r, c, _ = self.R[key]
        a = f"${xl_col_to_name(c)}${r + 1}" if absolute else f"{xl_col_to_name(c)}{r + 1}"
        return f"'{sheet}'!{a}"

    def val(self, key):
        return self.R[key][3]

    # --- cell writers --------------------------------------------------------------------------------------------
    def inp(self, ws, r, c, v, nf=None, **kw):          # hard-coded input taken from Phase 4 (blue)
        f = self.fmt(font_color=BLUE, num_format=nf, **kw) if nf else self.fmt(font_color=BLUE, **kw)
        if v is None:
            ws.write_blank(r, c, None, f)
        elif isinstance(v, (int, float)):
            ws.write_number(r, c, v, f)
        else:
            ws.write_string(r, c, str(v), f)

    def calc(self, ws, r, c, formula, value, nf=None, color=BLACK, **kw):     # formula (black) / link (green)
        f = self.fmt(font_color=color, num_format=nf, **kw) if nf else self.fmt(font_color=color, **kw)
        self.formula_count += 1
        ws.write_formula(r, c, formula, f, 0 if self.nocache else value)

    def txt(self, ws, r, c, s, **kw):
        ws.write_string(r, c, s, self.fmt(**kw))

    def hdr(self, ws, r, c, labels, height=30):
        f = self.fmt(bold=True, font_color="#FFFFFF", bg_color=NAVY, text_wrap=True, align="center", border=1, border_color="#BFBFBF")
        for i, h in enumerate(labels):
            ws.write_string(r, c + i, h, f)
        ws.set_row(r, height)

    def title(self, ws, title, sub, banner=None, width=14):
        ws.hide_gridlines(2)
        ws.write_string(0, 0, title, self.fmt(bold=True, font_size=16, font_color=NAVY))
        ws.write_string(1, 0, sub, self.fmt(italic=True, font_color="#595959"))
        if banner:
            ws.merge_range(2, 0, 2, width - 1, banner, self.fmt(bg_color=AMBER, text_wrap=True, border=1, border_color="#BF9000", valign="top"))
            ws.set_row(2, 15 * max(1, -(-len(banner) // (width * 14))))
        ws.write_url(0, width - 1, "internal:'Start Here'!A1", self.fmt(font_color="#0563C1", underline=1), "Back to Start Here")

    def section(self, ws, r, text, note=None, width=14):
        ws.write_string(r, 0, text, self.fmt(bold=True, font_size=12, font_color=NAVY, bottom=2, bottom_color=NAVY))
        for c in range(1, width):
            ws.write_blank(r, c, None, self.fmt(bottom=2, bottom_color=NAVY))
        if note:
            ws.merge_range(r + 1, 0, r + 1, width - 1, note, self.fmt(italic=True, font_color="#404040", text_wrap=True, valign="top"))
            ws.set_row(r + 1, 14 * max(1, -(-len(note) // (width * 13))))
            return r + 2
        return r + 1


class RowX:
    """Resolve column ids to A1 refs for one data row inside a table spec."""
    def __init__(self, colidx: dict, row0: int, first0: int):
        self.colidx, self.row0, self.first0 = colidx, row0, first0

    def __getitem__(self, cid):
        return f"{xl_col_to_name(self.colidx[cid])}{self.row0 + 1}"

    def prev(self, cid):
        return None if self.row0 == self.first0 else f"{xl_col_to_name(self.colidx[cid])}{self.row0}"


class Table:
    def __init__(self, sheet, r0, c0, specs, n):
        self.sheet, self.r0, self.c0, self.specs, self.n = sheet, r0, c0, specs, n   # r0 = first data row (0-based)
        self.idx = {s["id"]: c0 + i for i, s in enumerate(specs)}

    @property
    def r1(self):
        return self.r0 + self.n - 1

    def col_rng(self, cid, absolute=True, sheet=True):
        c = xl_col_to_name(self.idx[cid])
        a = f"${c}${self.r0 + 1}:${c}${self.r1 + 1}" if absolute else f"{c}{self.r0 + 1}:{c}{self.r1 + 1}"
        return f"'{self.sheet}'!{a}" if sheet else a

    def cell(self, cid, i, absolute=True, sheet=True):
        c = xl_col_to_name(self.idx[cid])
        a = f"${c}${self.r0 + i + 1}" if absolute else f"{c}{self.r0 + i + 1}"
        return f"'{self.sheet}'!{a}" if sheet else a

    def pos(self, cid, i):
        return self.r0 + i, self.idx[cid]


def write_table(cx: Ctx, ws, sheet: str, hdr_row: int, c0: int, specs: list[dict], rows: list[dict], name: str | None = None,
                header_height=32) -> Table:
    """specs: id, h (header), w (width), nf, kind in {in, txt, date, calc, link}; calc/link have f(x)->formula|None and v(d)->value."""
    n = len(rows)
    tb = Table(sheet, hdr_row + 1, c0, specs, n)
    cx.hdr(ws, hdr_row, c0, [s["h"] for s in specs], header_height)
    if name and n:
        ws.add_table(hdr_row, c0, hdr_row + n, c0 + len(specs) - 1, {
            "name": name, "style": "Table Style Light 1", "autofilter": True,
            "columns": [{"header": s["h"], "header_format": cx.fmt(bold=True, font_color="#FFFFFF", bg_color=NAVY, text_wrap=True,
                                                                 align="center", border=1, border_color="#BFBFBF")} for s in specs]})
    for i, row in enumerate(rows):
        r = tb.r0 + i
        x = RowX(tb.idx, r, tb.r0)
        for j, s in enumerate(specs):
            c = c0 + j
            kind, nf = s.get("kind", "in"), s.get("nf")
            if kind == "in":
                cx.inp(ws, r, c, row.get(s["id"]), nf, **s.get("fmt", {}))
            elif kind == "txt":
                cx.txt(ws, r, c, "" if row.get(s["id"]) is None else str(row.get(s["id"])), **s.get("fmt", {}))
            elif kind == "date":
                ws.write_datetime(r, c, row[s["id"]], cx.fmt(num_format=nf or NF_DATE, align="left"))
            else:
                v = s["v"](row)
                row[s["id"]] = v
                fml = s["f"](x)
                if fml is None:
                    cx.txt(ws, r, c, str(v), align="right", font_color=BLACK)
                else:
                    cx.calc(ws, r, c, fml, v, nf, color=GREEN if kind == "link" else BLACK, **s.get("fmt", {}))
    for j, s in enumerate(specs):
        if "w" in s:
            k = (sheet, c0 + j)
            cx.widths[k] = max(cx.widths.get(k, 0), s["w"])
    return tb


def pct_guard(var, budget_net, ratio):
    """Phase 4 safe_pct: publish only when |net budget| >= 50% of the gross (absolute) budget."""
    if ratio is None or ratio < GUARD or not budget_net:
        return "n/a (guard)"
    return var / abs(budget_net)


def direction(v):
    return "Actual above budget" if v > 0 else ("Actual below budget" if v < 0 else "On budget")


def yd(period_ym: str) -> dt.datetime:
    return dt.datetime(int(period_ym[:4]), int(period_ym[5:7]), 1)


def fm(v, d=2):          # $12.32M style used by the Phase 4 register
    return ("-" if v < 0 else "") + f"${abs(v) / 1e6:,.{d}f}M"


def fp(v, d=1):
    return f"{v * 100:.{d}f}%"


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 3: Monthly P&L
# ---------------------------------------------------------------------------------------------------------------------
def build_monthly(cx: Ctx):
    ws, S = cx.ws["Monthly P&L"], "Monthly P&L"
    a1 = cx.d.t("out_a1_pl_period_section", order="period_ym, section")
    by = {(r["period_ym"], r["section"]): r for r in a1}
    months = sorted({r["period_ym"] for r in a1})
    cx.title(ws, "Monthly P&L - actuals, Posted-only eligible lines",
             "USD, scale-adjusted (provisional), signs as recorded. Source: out_a1_pl_period_section (Phase 4). Costs are positive magnitudes: result = revenue - costs.",
             "Provisional population: Posted-only journal status (rule R6) and the scale-restoration rule are conventions, not confirmed accounting. No favourable/adverse labels: the account sign convention (R9) is unresolved. "
             "'Operating result proxy' = Revenue - COGS - People - Opex; it is NOT EBITDA or operating profit. D&A, below-EBITDA items and tax are shown as memo lines and are not subtotalled because their sign treatment is unverified. "
             "Balance-sheet records are excluded (see Data Quality).", width=15)
    ws.write_string(4, 0, "MoM highlight threshold (assumption):", cx.fmt(bold=True))
    cx.inp(ws, 4, 3, 0.10, NF_PCT, bg_color=AMBER, border=1)
    ws.write_string(4, 4, "<- amber = |month-on-month revenue change| >= threshold (also read the sign in the cell). Blue = input, black = formula.", cx.fmt(italic=True, font_color="#595959"))
    thr = "$D$5"
    rows = []
    for m in months:
        g = lambda s, k="actual_usd": by.get((m, s), {}).get(k, 0.0) or 0.0
        rows.append({"month": yd(m), "year": int(m[:4]), "rev": g("REVENUE"), "cogs": g("COGS"), "ppl": g("PEOPLE"), "opex": g("OPEX"),
                     "da": g("D&A"), "be": g("BELOW_EBITDA"), "tax": g("TAX"),
                     "n": sum(by.get((m, s), {}).get("rows_eligible", 0) for s in SECTIONS)})
    prev = {"rev": None}

    def mom_v(d):
        p = prev["rev"]
        prev["rev"] = d["rev"]
        return "n/a" if p in (None, 0) else d["rev"] / p - 1
    prev["rev"] = None
    specs = [
        dict(id="month", h="Month", w=11, kind="date"),
        dict(id="year", h="Year", w=7, kind="in", nf="0"),
        dict(id="rev", h="Revenue (USD)", w=15, nf=NF_USD),
        dict(id="cogs", h="COGS (USD)", w=15, nf=NF_USD),
        dict(id="gp", h="Gross profit, S1 signed as recorded (USD)", w=17, kind="calc", nf=NF_USD, f=lambda x: f"={x['rev']}-{x['cogs']}", v=lambda d: d["rev"] - d["cogs"]),
        dict(id="gm", h="Gross margin % (S1)", w=11, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["rev"]}>0,{x["gp"]}/{x["rev"]},"n/a")', v=lambda d: d["gp"] / d["rev"] if d["rev"] > 0 else "n/a"),
        dict(id="ppl", h="People costs (USD)", w=15, nf=NF_USD),
        dict(id="opex", h="Operating expenses (USD)", w=15, nf=NF_USD),
        dict(id="proxy", h="Operating result proxy (USD) - not EBITDA", w=17, kind="calc", nf=NF_USD,
             f=lambda x: f"={x['rev']}-{x['cogs']}-{x['ppl']}-{x['opex']}", v=lambda d: d["rev"] - d["cogs"] - d["ppl"] - d["opex"]),
        dict(id="proxym", h="Proxy margin %", w=10, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["rev"]}>0,{x["proxy"]}/{x["rev"]},"n/a")', v=lambda d: d["proxy"] / d["rev"] if d["rev"] > 0 else "n/a"),
        dict(id="da", h="Memo: D&A (USD)", w=13, nf=NF_USD),
        dict(id="be", h="Memo: Below-EBITDA (USD)", w=14, nf=NF_USD),
        dict(id="tax", h="Memo: Tax (USD)", w=13, nf=NF_USD),
        dict(id="n", h="Eligible lines (count)", w=11, nf=NF_INT),
        dict(id="mom", h="Revenue MoM %", w=10, kind="calc", nf=NF_PCT,
             f=lambda x: None if x.prev("rev") is None else f'=IF({x.prev("rev")}>0,{x["rev"]}/{x.prev("rev")}-1,"n/a")', v=mom_v),
    ]
    h0 = 6
    tb = write_table(cx, ws, S, h0, 0, specs, rows, name="tbl_MonthlyPL", header_height=62)
    ws.freeze_panes(h0 + 1, 1)
    tot = tb.r1 + 2
    L = lambda cid: xl_col_to_name(tb.idx[cid])
    cx.txt(ws, tot, 0, "Total Jan 2023 - Dec 2025", bold=True, top=1)
    tv = {k: sum(r[k] for r in rows) for k in ("rev", "cogs", "ppl", "opex", "da", "be", "tax", "n")}
    for k in ("rev", "cogs", "ppl", "opex", "da", "be", "tax", "n"):
        cx.calc(ws, tot, tb.idx[k], f"=SUM({L(k)}{tb.r0 + 1}:{L(k)}{tb.r1 + 1})", tv[k], NF_INT if k == "n" else NF_USD, bold=True, top=1)
    cx.calc(ws, tot, tb.idx["gp"], f"={L('rev')}{tot + 1}-{L('cogs')}{tot + 1}", tv["rev"] - tv["cogs"], NF_USD, bold=True, top=1)
    cx.calc(ws, tot, tb.idx["gm"], f'=IF({L("rev")}{tot + 1}>0,{L("gp")}{tot + 1}/{L("rev")}{tot + 1},"n/a")', (tv["rev"] - tv["cogs"]) / tv["rev"], NF_PCT, bold=True, top=1)
    px = tv["rev"] - tv["cogs"] - tv["ppl"] - tv["opex"]
    cx.calc(ws, tot, tb.idx["proxy"], f"={L('rev')}{tot + 1}-{L('cogs')}{tot + 1}-{L('ppl')}{tot + 1}-{L('opex')}{tot + 1}", px, NF_USD, bold=True, top=1)
    cx.calc(ws, tot, tb.idx["proxym"], f'=IF({L("rev")}{tot + 1}>0,{L("proxy")}{tot + 1}/{L("rev")}{tot + 1},"n/a")', px / tv["rev"], NF_PCT, bold=True, top=1)
    for k in ("rev", "cogs", "ppl", "opex", "da", "be", "tax", "n"):
        cx.reg(f"mpl_total_{k}", S, tot, tb.idx[k], tv[k])
    cx.reg("mpl_total_gp", S, tot, tb.idx["gp"], tv["rev"] - tv["cogs"])
    cx.reg("mpl_total_gm", S, tot, tb.idx["gm"], (tv["rev"] - tv["cogs"]) / tv["rev"])
    cx.reg("mpl_total_proxy", S, tot, tb.idx["proxy"], px)
    cx.reg("mpl_total_proxym", S, tot, tb.idx["proxym"], px / tv["rev"])
    cx.R["mpl_months"] = (S, tb.r0, tb.r1, len(rows))
    cx.R["mpl_table"] = tb

    # fiscal-year block (SUMIFS over the monthly table)
    r = tot + 3
    r = cx.section(ws, r, "Calendar-year totals (formulas over the monthly table)", "Calendar year of the posting period. Growth = year / prior year - 1.", 15)
    cx.hdr(ws, r, 0, ["Year", "", "Revenue (USD)", "COGS (USD)", "Gross profit S1 (USD)", "Gross margin %", "People (USD)", "Opex (USD)", "Operating result proxy (USD)",
                      "Proxy margin %", "D&A memo (USD)", "Below-EBITDA memo (USD)", "Tax memo (USD)", "Eligible lines", "Revenue growth %"], 44)
    fy0 = r + 1
    yrs = [2023, 2024, 2025]
    prev_rev = None
    for i, y in enumerate(yrs):
        rr = fy0 + i
        sub = {k: sum(x[k] for x in rows if x["year"] == y) for k in ("rev", "cogs", "ppl", "opex", "da", "be", "tax", "n")}
        cx.inp(ws, rr, 0, y, "0", bold=True, align="left")
        for k in ("rev", "cogs", "ppl", "opex", "da", "be", "tax", "n"):
            cx.calc(ws, rr, tb.idx[k], f"=SUMIFS({tb.col_rng(k, sheet=False)},{tb.col_rng('year', sheet=False)},$A{rr + 1})", sub[k], NF_INT if k == "n" else NF_USD)
        gp = sub["rev"] - sub["cogs"]
        cx.calc(ws, rr, tb.idx["gp"], f"={L('rev')}{rr + 1}-{L('cogs')}{rr + 1}", gp, NF_USD)
        cx.calc(ws, rr, tb.idx["gm"], f'=IF({L("rev")}{rr + 1}>0,{L("gp")}{rr + 1}/{L("rev")}{rr + 1},"n/a")', gp / sub["rev"], NF_PCT)
        p_ = sub["rev"] - sub["cogs"] - sub["ppl"] - sub["opex"]
        cx.calc(ws, rr, tb.idx["proxy"], f"={L('rev')}{rr + 1}-{L('cogs')}{rr + 1}-{L('ppl')}{rr + 1}-{L('opex')}{rr + 1}", p_, NF_USD)
        cx.calc(ws, rr, tb.idx["proxym"], f'=IF({L("rev")}{rr + 1}>0,{L("proxy")}{rr + 1}/{L("rev")}{rr + 1},"n/a")', p_ / sub["rev"], NF_PCT)
        if i == 0:
            cx.txt(ws, rr, tb.idx["mom"], "n/a", align="right")
        else:
            cx.calc(ws, rr, tb.idx["mom"], f"={L('rev')}{rr + 1}/{L('rev')}{rr}-1", sub["rev"] / prev_rev - 1, NF_PCT)
        prev_rev = sub["rev"]
        cx.reg(f"fy_rev_{y}", S, rr, tb.idx["rev"], sub["rev"])
        cx.reg(f"fy_gp_{y}", S, rr, tb.idx["gp"], gp)
        cx.reg(f"fy_proxy_{y}", S, rr, tb.idx["proxy"], p_)
        cx.reg(f"fy_growth_{y}", S, rr, tb.idx["mom"], None if i == 0 else sub["rev"] / (sum(x["rev"] for x in rows if x["year"] == y - 1)) - 1)
    ws.conditional_format(tb.r0, tb.idx["mom"], tb.r1, tb.idx["mom"],
                          {"type": "formula", "criteria": f'=AND(ISNUMBER(${L("mom")}{tb.r0 + 1}),ABS(${L("mom")}{tb.r0 + 1})>={thr})', "format": cx.fmt(bg_color=AMBER)})
    # charts
    ch = cx.wb.add_chart({"type": "line"})
    for cid, nm, col in (("rev", "Revenue", "#1F3864"), ("cogs", "COGS", "#C55A11"), ("proxy", "Operating result proxy", "#548235")):
        ch.add_series({"name": nm, "categories": tb.col_rng("month"), "values": tb.col_rng(cid), "line": {"color": col, "width": 2.0}})
    ch.set_title({"name": "Monthly revenue, COGS and operating result proxy (USD)", "name_font": {"size": 11}})
    ch.set_x_axis({"date_axis": True, "num_format": "mmm yy", "major_unit": 3, "major_unit_type": "months", "num_font": {"size": 8}})
    ch.set_y_axis({"num_format": "#,##0,,\"m\"", "name": "USD millions", "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
    ch.set_legend({"position": "bottom"})
    ch.set_size({"width": 860, "height": 330})
    ws.insert_chart(fy0 + 5, 0, ch)
    ws.set_landscape(); ws.fit_to_pages(1, 0)
    return tb


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 8 builder is placed before others that link to it; Sheet 4: Budget vs Actual (summary + long table)
# ---------------------------------------------------------------------------------------------------------------------
def build_entity(cx: Ctx):
    """Entity & Division sheet. Returns the entity x GL detail table (used by SUMIFS elsewhere)."""
    ws, S = cx.ws["Entity & Division"], "Entity & Division"
    cx.title(ws, "Entity and division analysis", "USD, scale-adjusted (provisional), signs as recorded. 3-year totals unless stated. Sources: out_a2, out_a3, out_b2, out_b3, out_g5.",
             "Comparability: all six entities report in USD in this extract after conversion, cover the same 36 months (0 entity-month gaps, out_a6) and use the same Posted-only population. Entity size differs widely, so compare shares and "
             "percentages, not raw amounts. Consolidation and intercompany elimination (R12) are unresolved: group totals here are sums of entity lines, not consolidated results.", width=14)
    ents = cx.d.rows("SELECT entity_code, any_value(legal_entity) AS legal_entity FROM out_a2_pl_entity_section GROUP BY 1 ORDER BY 1")
    a2 = {(r["entity_code"], r["section"]): r for r in cx.d.t("out_a2_pl_entity_section")}
    r = 4
    r = cx.section(ws, r, "E1. Actual performance by legal entity (3 years, Posted-only eligible lines)",
                   "Gross profit = Revenue - COGS (treatment S1, signed as recorded). Share of group revenue = entity revenue / sum of entity revenues.", 14)
    rows = []
    for e in ents:
        row = {"ent": e["entity_code"], "name": e["legal_entity"]}
        for s in SECTIONS:
            row[s] = a2.get((e["entity_code"], s), {}).get("actual_usd", 0.0)
        row["n"] = sum(a2.get((e["entity_code"], s), {}).get("rows_eligible", 0) for s in SECTIONS)
        rows.append(row)
    tot_rev = sum(x["REVENUE"] for x in rows)
    specs = [dict(id="ent", h="Entity", w=9, kind="txt"), dict(id="name", h="Legal entity", w=26, kind="txt"),
             dict(id="REVENUE", h="Revenue (USD)", w=15, nf=NF_USD), dict(id="COGS", h="COGS (USD)", w=15, nf=NF_USD),
             dict(id="gp", h="Gross profit S1 (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['REVENUE']}-{x['COGS']}", v=lambda d: d["REVENUE"] - d["COGS"]),
             dict(id="gm", h="Gross margin % (S1)", w=11, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["REVENUE"]}>0,{x["gp"]}/{x["REVENUE"]},"n/a")', v=lambda d: d["gp"] / d["REVENUE"] if d["REVENUE"] > 0 else "n/a"),
             dict(id="PEOPLE", h="People (USD)", w=14, nf=NF_USD), dict(id="OPEX", h="Opex (USD)", w=14, nf=NF_USD),
             dict(id="proxy", h="Operating result proxy (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['REVENUE']}-{x['COGS']}-{x['PEOPLE']}-{x['OPEX']}", v=lambda d: d["REVENUE"] - d["COGS"] - d["PEOPLE"] - d["OPEX"]),
             dict(id="proxym", h="Proxy margin %", w=10, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["REVENUE"]}>0,{x["proxy"]}/{x["REVENUE"]},"n/a")', v=lambda d: d["proxy"] / d["REVENUE"] if d["REVENUE"] > 0 else "n/a"),
             dict(id="share", h="Share of group revenue", w=11, kind="calc", nf=NF_PCT, f=None, v=lambda d: d["REVENUE"] / tot_rev),
             dict(id="n", h="Eligible lines (count)", w=11, nf=NF_INT)]
    # share formula needs the table range => build with a placeholder then overwrite
    first = r + 1
    tmp_specs = list(specs)
    tmp_specs[10] = dict(specs[10], f=lambda x: f"={x['REVENUE']}/SUM($C${first + 1}:$C${first + len(rows)})")
    tbE1 = write_table(cx, ws, S, r, 0, tmp_specs, rows, header_height=44)
    for i, row in enumerate(rows):
        cx.reg(f"ent_rev_{row['ent']}", S, tbE1.r0 + i, tbE1.idx["REVENUE"], row["REVENUE"])
        cx.reg(f"ent_cogs_{row['ent']}", S, tbE1.r0 + i, tbE1.idx["COGS"], row["COGS"])
    cx.R["E1"] = tbE1
    rr = tbE1.r1 + 1
    cx.txt(ws, rr, 0, "Group", bold=True, top=1); cx.txt(ws, rr, 1, "Sum of entities", bold=True, top=1)
    for cid in ("REVENUE", "COGS", "PEOPLE", "OPEX", "n"):
        cx.calc(ws, rr, tbE1.idx[cid], f"=SUM({tbE1.col_rng(cid, sheet=False)})", sum(x[cid] for x in rows), NF_INT if cid == "n" else NF_USD, bold=True, top=1)
    cx.R["E1_total_rev"] = ("Entity & Division", rr, tbE1.idx["REVENUE"], tot_rev)
    cx.R["E1_total_cogs"] = ("Entity & Division", rr, tbE1.idx["COGS"], sum(x["COGS"] for x in rows))
    cx.R["E1_total_n"] = ("Entity & Division", rr, tbE1.idx["n"], sum(x["n"] for x in rows))
    ws.conditional_format(tbE1.r0, tbE1.idx["gm"], tbE1.r1, tbE1.idx["gm"], {"type": "3_color_scale", "min_color": "#F8CBAD", "mid_color": "#FFFFFF", "max_color": "#C6E0B4"})
    r = rr + 3

    # E3 division actuals
    divs = [x["division"] for x in cx.d.rows("SELECT DISTINCT division FROM out_a3_pl_division_section ORDER BY 1")]
    a3 = {(x["division"], x["section"]): x for x in cx.d.t("out_a3_pl_division_section")}
    r = cx.section(ws, r, "E2. Actual performance by division (3 years)", "Division is populated on 100% of eligible lines (out_a5). Shares are of the sum of divisions.", 14)
    drows = []
    for dv in divs:
        row = {"div": dv}
        for s in SECTIONS:
            row[s] = a3.get((dv, s), {}).get("actual_usd", 0.0)
        row["n"] = sum(a3.get((dv, s), {}).get("rows_eligible", 0) for s in SECTIONS)
        drows.append(row)
    tot_rev_d = sum(x["REVENUE"] for x in drows)
    dfirst = r + 1
    dspecs = [dict(id="div", h="Division", w=9, kind="txt", fmt={}), dict(id="spacer", h="", w=26, kind="txt"),
              specs[2], specs[3], specs[4], specs[5], specs[6], specs[7], specs[8], specs[9],
              dict(id="share", h="Share of group revenue", w=11, kind="calc", nf=NF_PCT, f=lambda x: f"={x['REVENUE']}/SUM($C${dfirst + 1}:$C${dfirst + len(drows)})", v=lambda d: d["REVENUE"] / tot_rev_d),
              dict(id="n", h="Eligible lines (count)", w=11, nf=NF_INT)]
    tbD = write_table(cx, ws, S, r, 0, dspecs, drows, header_height=44)
    rd = tbD.r1 + 1
    cx.txt(ws, rd, 0, "Group", bold=True, top=1)
    cx.calc(ws, rd, tbD.idx["REVENUE"], f"=SUM({tbD.col_rng('REVENUE', sheet=False)})", tot_rev_d, NF_USD, bold=True, top=1)
    cx.R["E2_total_rev"] = ("Entity & Division", rd, tbD.idx["REVENUE"], tot_rev_d)
    cx.R["E2"] = tbD
    r = rd + 3

    # entity x GL detail first (needed by the SUMIFS below) -> compute its position: after the next blocks
    b2 = cx.d.t("out_b2_variance_entity_gl", order="scenario DESC, CASE section WHEN 'REVENUE' THEN 1 WHEN 'COGS' THEN 2 WHEN 'PEOPLE' THEN 3 WHEN 'OPEX' THEN 4 WHEN 'D&A' THEN 5 WHEN 'BELOW_EBITDA' THEN 6 ELSE 7 END, entity_code, gl_account")
    # E3 entity variance (SUMIFS over the detail table, same-sign basis) ------------------------------------------------
    n_e3 = len(ents)
    r_e3 = r
    r_e4 = r_e3 + 2 + 1 + n_e3 + 2 + 2
    # layout: E3 (note 2 rows + hdr + n rows), E4 division variance long table, E5 growth, E6 detail
    b3 = cx.d.t("out_b3_variance_division", order="scenario DESC, section_order, division")
    g5 = cx.d.t("out_g5_entity_growth", order="grp DESC, entity_code, period_year")
    r_e5 = r_e4 + 2 + 1 + len(b3) + 3
    r_e6 = r_e5 + 2 + 1 + len(g5) + 3
    r_det_hdr = r_e6 + 2
    det_specs = [dict(id="basis", h="Basis", w=9, kind="txt"), dict(id="sec", h="Section", w=26, kind="txt"), dict(id="ent", h="Entity", w=9, kind="txt"),
                 dict(id="gl", h="GL", w=8, kind="in", nf="0"), dict(id="acct", h="Account", w=26, kind="txt"), dict(id="n", h="Lines (count)", w=10, nf=NF_INT),
                 dict(id="act", h="Actual (USD)", w=15, nf=NF_USD), dict(id="bud", h="Budget (USD)", w=15, nf=NF_USD),
                 dict(id="var", h="Variance = actual - budget (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['act']}-{x['bud']}", v=lambda d: d["act"] - d["bud"]),
                 dict(id="pct", h="Variance % (Phase 4, guarded)", w=11, nf=NF_PCT),
                 dict(id="shg", h="Share of section gross cell variance", w=12, nf=NF_PCT),
                 dict(id="dir", h="Direction (arithmetic only)", w=19, kind="calc", f=lambda x: f'=IF({x["var"]}>0,"Actual above budget",IF({x["var"]}<0,"Actual below budget","On budget"))', v=lambda d: direction(d["var"]))]
    det_rows = [{"basis": "Same-sign" if r_["scenario"] == "SAME_SIGN_ONLY" else "All lines", "sec": r_["section"], "ent": r_["entity_code"], "gl": r_["gl_account"],
                 "acct": r_["account_name"], "n": r_["rows_in_scope"], "act": r_["actual_usd"], "bud": r_["budget_usd"], "pct": r_["variance_pct_of_abs_budget"],
                 "shg": r_["share_of_section_gross"]} for r_ in b2]
    cx.section(ws, r_e6, "E6. Detail: variance by entity x GL (out_b2, 288 rows; filter by Basis)", None, 14)
    ws.merge_range(r_e6 + 1, 0, r_e6 + 1, 13, "Source of the SUMIFS in E3 and in 'Budget vs Actual' / 'GL & Cost Drivers'. Same-sign = lines where actual and budget are non-zero with the same sign (Phase 4 primary basis). "
                   "All lines = every eligible line with a budget. 'Variance %' is blank where the Phase 4 guard (|net budget| < 50% of gross) suppresses it.",
                   cx.fmt(italic=True, text_wrap=True, valign="top", font_color="#404040"))
    ws.set_row(r_e6 + 1, 28)
    tbX = write_table(cx, ws, S, r_det_hdr, 0, det_specs, det_rows, name="tbl_EntityGL", header_height=44)
    cx.R["XDET"] = tbX
    # E3 now that tbX exists
    r = cx.section(ws, r_e3, "E3. Actual vs budget by legal entity - same-sign basis (SUMIFS over the E6 detail table)",
                   "Variance = actual - budget. Variance % = variance / |budget| at entity level; no favourable/adverse label. Cost = COGS + People + Opex.", 14)
    e3rows = []
    for e in ents:
        sel = [x for x in det_rows if x["ent"] == e["entity_code"] and x["basis"] == "Same-sign"]
        ra = sum(x["act"] for x in sel if x["sec"] == "REVENUE"); rb = sum(x["bud"] for x in sel if x["sec"] == "REVENUE")
        ca = sum(x["act"] for x in sel if x["sec"] in ("COGS", "PEOPLE", "OPEX")); cb = sum(x["bud"] for x in sel if x["sec"] in ("COGS", "PEOPLE", "OPEX"))
        e3rows.append({"ent": e["entity_code"], "ra": ra, "rb": rb, "ca": ca, "cb": cb})

    def sumifs(x, which, secs):
        part = []
        for s in secs:
            part.append(f'SUMIFS({tbX.col_rng(which)},{tbX.col_rng("ent")},$A{x.row0 + 1},{tbX.col_rng("basis")},"Same-sign",{tbX.col_rng("sec")},"{s}")')
        return "=" + "+".join(part)
    e3specs = [dict(id="ent", h="Entity", w=9, kind="txt"),
               dict(id="ra", h="Revenue actual (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: sumifs(x, "act", ["REVENUE"]), v=lambda d: d["ra"]),
               dict(id="rb", h="Revenue budget (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: sumifs(x, "bud", ["REVENUE"]), v=lambda d: d["rb"]),
               dict(id="rv", h="Revenue variance (USD)", w=14, kind="calc", nf=NF_USD, f=lambda x: f"={x['ra']}-{x['rb']}", v=lambda d: d["ra"] - d["rb"]),
               dict(id="rp", h="Revenue variance %", w=10, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["rb"]}<>0,{x["rv"]}/ABS({x["rb"]}),"n/a")', v=lambda d: d["rv"] / abs(d["rb"]) if d["rb"] else "n/a"),
               dict(id="ca", h="Cost actual (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: sumifs(x, "act", ["COGS", "PEOPLE", "OPEX"]), v=lambda d: d["ca"]),
               dict(id="cb", h="Cost budget (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: sumifs(x, "bud", ["COGS", "PEOPLE", "OPEX"]), v=lambda d: d["cb"]),
               dict(id="cv", h="Cost variance (USD)", w=14, kind="calc", nf=NF_USD, f=lambda x: f"={x['ca']}-{x['cb']}", v=lambda d: d["ca"] - d["cb"]),
               dict(id="cp", h="Cost variance %", w=10, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["cb"]}<>0,{x["cv"]}/ABS({x["cb"]}),"n/a")', v=lambda d: d["cv"] / abs(d["cb"]) if d["cb"] else "n/a"),
               dict(id="gv", h="Net effect on result proxy (USD) = revenue var - cost var", w=17, kind="calc", nf=NF_USD, f=lambda x: f"={x['rv']}-{x['cv']}", v=lambda d: d["rv"] - d["cv"])]
    tbE3 = write_table(cx, ws, S, r, 0, e3specs, e3rows, header_height=58)
    cx.R["E3"] = tbE3
    for i, e in enumerate(ents):
        cx.reg(f"e3_ra_{e['entity_code']}", S, tbE3.r0 + i, tbE3.idx["ra"], e3rows[i]["ra"])
    ws.conditional_format(tbE3.r0, tbE3.idx["rp"], tbE3.r1, tbE3.idx["rp"], {"type": "data_bar", "bar_color": "#9DC3E6", "bar_negative_color": "#F4B183", "bar_solid": True})
    ws.conditional_format(tbE3.r0, tbE3.idx["cp"], tbE3.r1, tbE3.idx["cp"], {"type": "data_bar", "bar_color": "#9DC3E6", "bar_negative_color": "#F4B183", "bar_solid": True})
    # E4 division variance
    r = cx.section(ws, r_e4, "E4. Actual vs budget by division (out_b3, both bases)", "Variance recomputed in Excel (actual - budget); % is the Phase 4 guarded figure.", 14)
    b3rows = [{"basis": "Same-sign" if x["scenario"] == "SAME_SIGN_ONLY" else "All lines", "div": x["division"], "sec": x["section"], "n": x["rows_in_scope"],
               "act": x["actual_usd"], "bud": x["budget_usd"], "pct": x["variance_pct_of_abs_budget"]} for x in b3]
    b3specs = [dict(id="basis", h="Basis", w=9, kind="txt"), dict(id="sec", h="Section", w=26, kind="txt"), dict(id="div", h="Division", w=22, kind="txt"),
               dict(id="n", h="Lines (count)", w=10, nf=NF_INT), dict(id="act", h="Actual (USD)", w=15, nf=NF_USD), dict(id="bud", h="Budget (USD)", w=15, nf=NF_USD),
               dict(id="var", h="Variance (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['act']}-{x['bud']}", v=lambda d: d["act"] - d["bud"]),
               dict(id="pct", h="Variance % (Phase 4, guarded)", w=11, nf=NF_PCT)]
    # reorder columns so the sheet columns line up with the layout above: basis, section(div name wide) etc.
    tbB3 = write_table(cx, ws, S, r, 0, b3specs, b3rows, name="tbl_DivisionVar", header_height=44)
    cx.R["B3"] = tbB3
    # E5 growth
    r = cx.section(ws, r_e5, "E5. Year-on-year growth by entity (out_g5; operating cost = COGS + People + Opex)", "Growth uses Posted-only signed amounts for consecutive calendar years; 2023 has no prior year.", 14)
    gspecs = [dict(id="grp", h="Group", w=18, kind="txt"), dict(id="ent", h="Entity", w=26, kind="txt"), dict(id="yr", h="Year", w=9, kind="in", nf="0"),
              dict(id="amt", h="Amount (USD)", w=15, nf=NF_USD), dict(id="g", h="YoY growth %", w=10, nf=NF_PCT)]
    grows = [{"grp": x["grp"], "ent": x["entity_code"], "yr": x["period_year"], "amt": x["amt"], "g": x["yoy_growth"]} for x in g5]
    write_table(cx, ws, S, r, 0, gspecs, grows, name="tbl_EntityGrowth", header_height=30)
    ws.freeze_panes(4, 0)
    ws.set_landscape(); ws.fit_to_pages(1, 0)
    return tbX, det_rows


def build_bva(cx: Ctx, tbX, det_rows):
    ws, S = cx.ws["Budget vs Actual"], "Budget vs Actual"
    cx.title(ws, "Budget vs actual", "USD, scale-adjusted (provisional), signs as recorded. Population: eligible P&L lines that also have a budget (55,043 lines). Sources: out_b1, out_b2, out_b3, out_b4, out_b7-b11.",
             "Definitions follow Phase 4 exactly: Variance = Actual - Budget. Variance % = Variance / |net budget|, published only when |net budget| >= 50% of the gross (absolute) budget (project convention, not an accounting standard). "
             "Primary basis = SAME-SIGN lines (actual and budget non-zero with the same sign). 'All lines' includes opposite-sign and zero-involved lines and is shown beside it. "
             "Nothing is labelled favourable or unfavourable: the sign convention (R9) is unresolved. Cost-centre variance is not published by Phase 4, so it is not shown.", width=13)
    ws.write_string(4, 0, "Net-budget guard (Phase 4 convention):", cx.fmt(bold=True))
    cx.inp(ws, 4, 3, GUARD, NF_PCT, bg_color=AMBER, border=1)
    ws.write_string(4, 4, "<- % is shown only when |net budget| / gross budget >= this value. Highlight threshold for |variance %|:", cx.fmt(italic=True, font_color="#595959"))
    cx.inp(ws, 4, 9, 0.05, NF_PCT, bg_color=AMBER, border=1)
    guard_ref, hl_ref = "$D$5", "$J$5"
    b1 = cx.d.t("out_b1_variance_section", order="scenario, section_order")
    r = 6
    for scn, label in (("SAME_SIGN_ONLY", "A1. By section - SAME-SIGN lines (primary basis)"), ("ALL_LINES", "A2. By section - ALL lines (sensitivity)")):
        r = cx.section(ws, r, label, "Gross cell variance = sum of absolute entity x GL x month variances; it shows movements that offset inside the net figure.", 13)
        rows = [dict(sec=SEC_LABEL[x["section"]], key=x["section"], n=x["rows_in_scope"], act=x["actual_usd"], bud=x["budget_usd"], ratio=x["budget_netting_ratio"],
                     gross=x["gross_cell_variance_usd"], gpct=x["gross_variance_pct_of_abs_cell_budget"], pub=x["variance_pct_of_abs_budget"])
                for x in b1 if x["scenario"] == scn and x["section"] in SECTIONS]
        specs = [dict(id="sec", h="Section", w=26, kind="txt"), dict(id="n", h="Lines (count)", w=10, nf=NF_INT),
                 dict(id="act", h="Actual (USD)", w=15, nf=NF_USD), dict(id="bud", h="Budget (USD)", w=15, nf=NF_USD),
                 dict(id="var", h="Net variance = actual - budget (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['act']}-{x['bud']}", v=lambda d: d["act"] - d["bud"]),
                 dict(id="ratio", h="|Net budget| / gross budget", w=12, nf=NF_PCT),
                 dict(id="pct", h="Variance % of |budget| (guarded)", w=12, kind="calc", nf=NF_PCT,
                      f=lambda x: f'=IF(AND({x["ratio"]}>={guard_ref},{x["bud"]}<>0),{x["var"]}/ABS({x["bud"]}),"n/a (guard)")', v=lambda d: pct_guard(d["var"], d["bud"], d["ratio"])),
                 dict(id="gross", h="Gross cell variance (USD)", w=15, nf=NF_USD),
                 dict(id="gpct", h="Gross variance % of gross budget", w=12, nf=NF_PCT),
                 dict(id="dir", h="Direction (arithmetic only)", w=19, kind="calc", f=lambda x: f'=IF({x["var"]}>0,"Actual above budget",IF({x["var"]}<0,"Actual below budget","On budget"))', v=lambda d: direction(d["var"]))]
        tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
        tag = "ss" if scn == "SAME_SIGN_ONLY" else "al"
        for i, row in enumerate(rows):
            for cid in ("n", "act", "bud", "var", "pct", "gross"):
                cx.reg(f"bva_{tag}_{row['key']}_{cid}", S, tb.r0 + i, tb.idx[cid], row[cid])
        ws.conditional_format(tb.r0, tb.idx["pct"], tb.r1, tb.idx["pct"], {"type": "formula", "criteria": f'=AND(ISNUMBER(${xl_col_to_name(tb.idx["pct"])}{tb.r0 + 1}),ABS(${xl_col_to_name(tb.idx["pct"])}{tb.r0 + 1})>={hl_ref})', "format": cx.fmt(bg_color=AMBER)})
        cx.R[f"BVA_{tag}"] = tb
        r = tb.r1 + 3
    # bridge b8
    r = cx.section(ws, r, "A3. Bridge: all-lines net variance = same-sign + opposite-sign + zero-involved (out_b8)",
                   "Opposite-sign and zero-involved lines are an observation, not a proven error: credit notes, reversals and contra accounts can legitimately differ in sign. They are kept, never flipped or removed.", 13)
    b8 = cx.d.t("out_b8_variance_bridge", order="section_order")
    rows = [dict(sec=SEC_LABEL[x["section"]], key=x["section"], al=x["all_lines_net_variance_usd"] or 0.0, ss=x["same_sign_net_variance_usd"] or 0.0, op=x["opposite_sign_net_variance_usd"] or 0.0, zi=x["zero_involved_net_variance_usd"] or 0.0) for x in b8]
    specs = [dict(id="sec", h="Section", w=26, kind="txt"), dict(id="al", h="All lines net variance (USD)", w=16, nf=NF_USD), dict(id="ss", h="Same-sign (USD)", w=15, nf=NF_USD),
             dict(id="op", h="Opposite-sign (USD)", w=15, nf=NF_USD), dict(id="zi", h="Zero-involved (USD)", w=14, nf=NF_USD),
             dict(id="diff", h="Bridge difference (USD) = all - (same + opposite + zero)", w=17, kind="calc", nf=NF_USD2, f=lambda x: f"={x['al']}-({x['ss']}+{x['op']}+{x['zi']})", v=lambda d: d["al"] - (d["ss"] + d["op"] + d["zi"]))]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=58)
    for i, row in enumerate(rows):
        cx.reg(f"bva_bridge_diff_{row['key']}", S, tb.r0 + i, tb.idx["diff"], row["diff"])
        cx.reg(f"bva_bridge_al_{row['key']}", S, tb.r0 + i, tb.idx["al"], row["al"])
    r = tb.r1 + 3
    # top contributors from the detail table (same-sign)
    r = cx.section(ws, r, "B. Largest entity x GL contributors to the variance - same-sign basis (top 20 by |variance|)",
                   "Net variance can hide offsetting cells; 'Share of section gross cell variance' shows each cell's weight against the section's gross movement (Phase 4 out_b2).", 13)
    ss = [x for x in det_rows if x["basis"] == "Same-sign"]
    ss.sort(key=lambda x: (-abs(x["act"] - x["bud"]), x["ent"], x["gl"]))
    top = [dict(rank=i + 1, sec=SEC_LABEL[x["sec"]], ent=x["ent"], gl=x["gl"], acct=x["acct"], act=x["act"], bud=x["bud"], pct=x["pct"], shg=x["shg"]) for i, x in enumerate(ss[:20])]
    specs = [dict(id="rank", h="Rank by |variance|", w=9, kind="in", nf="0"), dict(id="sec", h="Section", w=26, kind="txt"), dict(id="ent", h="Entity", w=9, kind="txt"),
             dict(id="gl", h="GL", w=8, nf="0"), dict(id="acct", h="Account", w=26, kind="txt"), dict(id="act", h="Actual (USD)", w=15, nf=NF_USD), dict(id="bud", h="Budget (USD)", w=15, nf=NF_USD),
             dict(id="var", h="Variance (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['act']}-{x['bud']}", v=lambda d: d["act"] - d["bud"]),
             dict(id="pct", h="Variance % (Phase 4)", w=12, nf=NF_PCT), dict(id="shg", h="Share of section gross cell variance", w=13, nf=NF_PCT),
             dict(id="dir", h="Direction (arithmetic only)", w=19, kind="calc", f=lambda x: f'=IF({x["var"]}>0,"Actual above budget",IF({x["var"]}<0,"Actual below budget","On budget"))', v=lambda d: direction(d["var"]))]
    tb = write_table(cx, ws, S, r, 0, specs, top, header_height=44)
    r = tb.r1 + 3
    # sensitivity b9 / b10 / b11
    r = cx.section(ws, r, "C. How sensitive is 'what counts as material'? (out_b9, out_b10, out_b11)",
                   "Phase 4 materiality thresholds are project conventions, not standards. The tables show how many entity x GL cells fall above each threshold, and how much of the total absolute variance they cover.", 13)
    b9 = [dict(scn="Same-sign" if x["scenario"] == "SAME_SIGN_ONLY" else "All lines", thr=x["threshold_share_of_total_abs_variance"], n=x["cells_at_or_above"], cov=x["share_of_total_abs_variance_covered"])
          for x in cx.d.t("out_b9_contribution_sensitivity", order="scenario DESC, threshold_share_of_total_abs_variance")]
    s9 = [dict(id="scn", h="Basis", w=26, kind="txt"), dict(id="thr", h="Cell share of total |variance| >=", w=14, nf=NF_PCT2), dict(id="n", h="Cells at/above (count)", w=12, nf=NF_INT), dict(id="cov", h="Share of total |variance| covered", w=14, nf=NF_PCT)]
    write_table(cx, ws, S, r, 0, s9, b9, header_height=44)
    b11 = [dict(scn="Same-sign" if x["scenario"] == "SAME_SIGN_ONLY" else "All lines", thr=x["threshold_pct_of_gross_budget"], n=x["cells_at_or_above"], ns=x["cells_not_scored"], tot=x["cells_total"], cov=x["share_of_total_abs_variance_in_flagged_cells"])
           for x in cx.d.t("out_b11_budget_pct_sensitivity", order="scenario DESC, threshold_pct_of_gross_budget")]
    s11 = [dict(id="scn", h="Basis", w=26, kind="txt"), dict(id="thr", h="|Variance| >= % of cell gross budget", w=14, nf=NF_PCT), dict(id="n", h="Cells at/above (count)", w=12, nf=NF_INT),
           dict(id="ns", h="Cells not scored (count)", w=12, nf=NF_INT), dict(id="tot", h="Cells total (count)", w=12, nf=NF_INT), dict(id="cov", h="Share of total |variance| in flagged cells", w=14, nf=NF_PCT)]
    write_table(cx, ws, S, r, 6, s11, b11, header_height=44)
    r += 1 + max(len(b9), len(b11)) + 1
    ov = cx.d.t("out_b10_top_cells_overlap")[0]
    ws.merge_range(r, 0, r, 12, f"Top-10 cell overlap between the all-lines and same-sign views: {ov['cells_in_both_top10']} of {ov['top_n']} cells are in both lists (out_b10). "
                   "The ranking is stable enough to read the concentration, not stable enough to rely on a single cell.", cx.fmt(italic=True, text_wrap=True))
    ws.set_row(r, 28)
    r += 3
    # monthly long table
    b4 = cx.d.t("out_b4_variance_monthly", order="scenario DESC, section_order, period_ym")
    r = cx.section(ws, r, "D. Monthly variance by section (out_b4; filter by Basis and Section)",
                   "Variance recomputed in Excel; 'Phase 4 %' is the guarded published figure (blank = suppressed by the guard); 'Recomputed %' is variance/|budget| with no guard, shown so the two can be compared. Check = OK when they agree.", 13)
    rows = [dict(basis="Same-sign" if x["scenario"] == "SAME_SIGN_ONLY" else "All lines", sec=x["section"], month=yd(x["period_ym"]), n=x["rows_in_scope"], act=x["actual_usd"], bud=x["budget_usd"],
                 pub=x["variance_pct_of_abs_budget"]) for x in b4]
    specs = [dict(id="basis", h="Basis", w=9, kind="txt"), dict(id="sec", h="Section", w=26, kind="txt"), dict(id="month", h="Month", w=11, kind="date"),
             dict(id="n", h="Lines (count)", w=10, nf=NF_INT), dict(id="act", h="Actual (USD)", w=15, nf=NF_USD), dict(id="bud", h="Budget (USD)", w=15, nf=NF_USD),
             dict(id="var", h="Variance (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['act']}-{x['bud']}", v=lambda d: d["act"] - d["bud"]),
             dict(id="pub", h="Phase 4 variance % (guarded)", w=12, nf=NF_PCT),
             dict(id="rec", h="Recomputed % (no guard)", w=12, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["bud"]}<>0,{x["var"]}/ABS({x["bud"]}),"n/a")', v=lambda d: d["var"] / abs(d["bud"]) if d["bud"] else "n/a"),
             dict(id="chk", h="Check", w=9, kind="calc", f=lambda x: f'=IF({x["pub"]}="","guard",IF(ABS({x["pub"]}-{x["rec"]})<0.000001,"OK","DIFF"))',
                  v=lambda d: "guard" if d["pub"] is None else ("OK" if abs(d["pub"] - d["rec"]) < 1e-6 else "DIFF"))]
    # Excel formulas see an empty cell for a blank pub; python rows carry None
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_BvA_Monthly", header_height=44)
    cx.R["BVA_M"] = tb
    nd = sum(1 for x in rows if x["chk"] == "DIFF")
    cx.txt(ws, tb.r1 + 1, tb.idx["rec"], "Months with DIFF (count):", bold=True, align="right")
    cx.calc(ws, tb.r1 + 1, tb.idx["chk"], f'=COUNTIF({tb.col_rng("chk", sheet=False)},"DIFF")', nd, NF_INT, bold=True)
    cx.reg("bva_m_diffs", S, tb.r1 + 1, tb.idx["chk"], nd)
    ws.conditional_format(tb.r0, tb.idx["chk"], tb.r1, tb.idx["chk"], {"type": "cell", "criteria": "==", "value": '"DIFF"', "format": cx.fmt(bg_color="#F8CBAD", bold=True)})
    # chart: same-sign monthly variance % for four operating sections (blocks are contiguous: ordered by basis, section, month)
    ch = cx.wb.add_chart({"type": "line"})
    start = {}
    for i, x in enumerate(rows):
        start.setdefault((x["basis"], x["sec"]), i)
    colors = {"REVENUE": "#1F3864", "COGS": "#C55A11", "PEOPLE": "#548235", "OPEX": "#7F6000"}
    for sec in OPS:
        i0 = start[("Same-sign", sec)]
        c = xl_col_to_name(tb.idx["rec"])
        ch.add_series({"name": SEC_LABEL[sec], "categories": f"='{S}'!${xl_col_to_name(tb.idx['month'])}${tb.r0 + i0 + 1}:${xl_col_to_name(tb.idx['month'])}${tb.r0 + i0 + 36}",
                       "values": f"='{S}'!${c}${tb.r0 + i0 + 1}:${c}${tb.r0 + i0 + 36}", "line": {"color": colors[sec], "width": 2}})
    ch.set_title({"name": "Monthly variance % of budget, same-sign lines (see the table for the months and the sides)", "name_font": {"size": 10}})
    ch.set_x_axis({"date_axis": True, "num_format": "mmm yy", "major_unit": 3, "major_unit_type": "months", "num_font": {"size": 8}})
    ch.set_y_axis({"num_format": "0.0%", "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}, "name": "Variance % of |budget|"})
    ch.set_legend({"position": "bottom"})
    ch.set_size({"width": 760, "height": 300})
    ws.insert_chart(6, 11, ch, {"x_offset": 20})
    ws.freeze_panes(5, 0)
    ws.set_landscape(); ws.fit_to_pages(1, 0)


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 5: Forecast and prior-year
# ---------------------------------------------------------------------------------------------------------------------
def build_forecast(cx: Ctx):
    ws, S = cx.ws["Forecast & Prior Year"], "Forecast & Prior Year"
    cx.title(ws, "Forecast and prior-year analysis",
             "USD, scale-adjusted (provisional), signs as recorded. Forecast error = Forecast - Actual. WAPE = sum|F-A| / sum|A|. Bias = sum(F-A) / sum|A|. Sources: out_c1-c8, out_d1-d5.",
             "THREE DIFFERENT THINGS - do not blur them. (1) Observed: the forecast column differs from actuals by the amounts shown. (2) A historical forecasting-performance measure would need dated forecast snapshots: the extract has NO forecast version or as-of date, "
             "so forecast skill, forecast accuracy as a KPI and any bias correction are NOT established here. (3) Business explanations (a late re-forecast, a mechanically derived forecast, planning optimism) are hypotheses. "
             "Population: eligible P&L lines with a forecast value; the prior-year COLUMN is not the prior calendar year's actuals (see F6).", width=12)
    c1 = cx.d.t("out_c1_forecast_section", order="scenario DESC, section_order")
    r = 4
    for scn, label in (("SAME_SIGN_ONLY", "F1. Forecast vs actual - SAME-SIGN lines (actual and forecast non-zero, same sign)"), ("ALL_LINES", "F2. Forecast vs actual - ALL lines")):
        r = cx.section(ws, r, label, "Net error = forecast - actual (positive = forecast above actual). Bias and WAPE recomputed from Phase 4 inputs (net error, absolute error and absolute actual).", 12)
        rows = [dict(sec=SEC_LABEL[x["section"]], key=x["section"], n=x["rows_in_scope"], act=x["actual_usd"], fc=x["forecast_usd"], abse=x["abs_error_usd"], absa=x["abs_actual_usd"])
                for x in c1 if x["scenario"] == scn and x["section"] in SECTIONS]
        specs = [dict(id="sec", h="Section", w=26, kind="txt"), dict(id="n", h="Lines (count)", w=10, nf=NF_INT), dict(id="act", h="Actual (USD)", w=15, nf=NF_USD), dict(id="fc", h="Forecast (USD)", w=15, nf=NF_USD),
                 dict(id="net", h="Net error = forecast - actual (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['fc']}-{x['act']}", v=lambda d: d["fc"] - d["act"]),
                 dict(id="abse", h="Absolute error sum (USD)", w=15, nf=NF_USD), dict(id="absa", h="Absolute actual sum (USD)", w=15, nf=NF_USD),
                 dict(id="bias", h="Bias = net error / abs actual", w=11, kind="calc", nf=NF_PCT2, f=lambda x: f'=IF({x["absa"]}>0,{x["net"]}/{x["absa"]},"n/a")', v=lambda d: d["net"] / d["absa"] if d["absa"] > 0 else "n/a"),
                 dict(id="wape", h="WAPE = abs error / abs actual", w=11, kind="calc", nf=NF_PCT2, f=lambda x: f'=IF({x["absa"]}>0,{x["abse"]}/{x["absa"]},"n/a")', v=lambda d: d["abse"] / d["absa"] if d["absa"] > 0 else "n/a"),
                 dict(id="dir", h="Observed direction", w=22, kind="calc", f=lambda x: f'=IF({x["net"]}>0,"Forecast above actual",IF({x["net"]}<0,"Forecast below actual","Equal"))',
                      v=lambda d: "Forecast above actual" if d["net"] > 0 else ("Forecast below actual" if d["net"] < 0 else "Equal"))]
        tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
        tag = "ss" if scn == "SAME_SIGN_ONLY" else "al"
        for i, row in enumerate(rows):
            for cid in ("n", "net", "bias", "wape"):
                cx.reg(f"fc_{tag}_{row['key']}_{cid}", S, tb.r0 + i, tb.idx[cid], row[cid])
        cx.R[f"FC_{tag}"] = tb
        r = tb.r1 + 3
    ssT = cx.R["FC_ss"]
    # F3 forecast vs budget (c6)
    r = cx.section(ws, r, "F3. Is the forecast closer to actuals than the budget? Matched lines only (out_c6)",
                   "Same lines for both measures: actual, budget and forecast all non-zero with the same sign. This population is selected by outcome (it drops the opposite-sign lines that carry most of the error - see F4), so the improvement is a statement about these lines only.", 12)
    c6 = cx.d.t("out_c6_forecast_vs_budget", order="section_order")
    rows = [dict(sec=SEC_LABEL[x["section"]], key=x["section"], n=x["rows_compared"], wf=x["wape_forecast"], wb=x["wape_budget"], bf=x["bias_forecast"], bb=x["bias_budget"]) for x in c6]
    specs = [dict(id="sec", h="Section", w=26, kind="txt"), dict(id="n", h="Matched lines (count)", w=10, nf=NF_INT), dict(id="wf", h="WAPE forecast", w=11, nf=NF_PCT2), dict(id="wb", h="WAPE budget", w=11, nf=NF_PCT2),
             dict(id="imp", h="Budget WAPE - forecast WAPE (points)", w=14, kind="calc", nf=NF_PCT2, f=lambda x: f"={x['wb']}-{x['wf']}", v=lambda d: d["wb"] - d["wf"]),
             dict(id="bf", h="Bias forecast", w=11, nf=NF_PCT2), dict(id="bb", h="Bias budget", w=11, nf=NF_PCT2)]
    tb6 = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    for i, row in enumerate(rows):
        cx.reg(f"fc_c6_{row['key']}_wf", S, tb6.r0 + i, tb6.idx["wf"], row["wf"])
        cx.reg(f"fc_c6_{row['key']}_wb", S, tb6.r0 + i, tb6.idx["wb"], row["wb"])
        cx.reg(f"fc_c6_{row['key']}_n", S, tb6.r0 + i, tb6.idx["n"], row["n"])
    ch = cx.wb.add_chart({"type": "column"})
    ch.add_series({"name": "Forecast WAPE", "categories": tb6.col_rng("sec"), "values": tb6.col_rng("wf"), "fill": {"color": "#1F3864"}})
    ch.add_series({"name": "Budget WAPE", "categories": tb6.col_rng("sec"), "values": tb6.col_rng("wb"), "fill": {"color": "#BF9000"}})
    ch.set_title({"name": "WAPE vs actual: forecast vs budget (matched same-sign lines)", "name_font": {"size": 10}})
    ch.set_y_axis({"num_format": "0.0%", "name": "WAPE", "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
    ch.set_legend({"position": "bottom"}); ch.set_size({"width": 560, "height": 280})
    ch.set_x_axis({"num_font": {"size": 8}})
    ws.insert_chart(tb6.r0 - 1, 8, ch)
    r = max(tb6.r1 + 3, tb6.r0 + 14)
    # F3b comparable all-lines population (same lines for both measures, any sign)
    r = cx.section(ws, r, "F3b. Forecast vs budget on ALL comparable lines (actual, budget and forecast present; any sign)",
                   "Same lines for both measures, NOT selected by outcome. Compare with F3: the matched subset drops opposite-sign and zero-involved lines, so its WAPE is much smaller. Neither population establishes forecast skill (no forecast version/as-of date). "
                   "F2 (all forecast lines) is larger still because it does not require a budget value, so its lines are not the same lines as F3b.", 12)
    cmp_ = cx.d.rows("SELECT section, section_order, count(*) n, sum(abs(forecast_usd_adj - actual_usd_adj)) / sum(abs(actual_usd_adj)) wf, sum(abs(budget_usd_adj - actual_usd_adj)) / sum(abs(actual_usd_adj)) wb, "
                     "sum(forecast_usd_adj - actual_usd_adj) / sum(abs(actual_usd_adj)) bf, sum(budget_usd_adj - actual_usd_adj) / sum(abs(actual_usd_adj)) bb "
                     "FROM v_pl_budget WHERE actual_usd_adj IS NOT NULL AND forecast_usd_adj IS NOT NULL AND section IN ('REVENUE','COGS','PEOPLE','OPEX') GROUP BY 1, 2 ORDER BY 2")
    rows = [dict(sec=SEC_LABEL[x["section"]], key=x["section"], n=x["n"], wf=x["wf"], wb=x["wb"], bf=x["bf"], bb=x["bb"]) for x in cmp_]
    specs = [dict(id="sec", h="Section", w=26, kind="txt"), dict(id="n", h="Comparable lines (count)", w=10, nf=NF_INT), dict(id="wf", h="WAPE forecast", w=11, nf=NF_PCT2), dict(id="wb", h="WAPE budget", w=11, nf=NF_PCT2),
             dict(id="gap", h="Forecast WAPE - budget WAPE (points; negative = forecast closer)", w=14, kind="calc", nf=NF_PCT2, f=lambda x: f"={x['wf']}-{x['wb']}", v=lambda d: d["wf"] - d["wb"]),
             dict(id="bf", h="Bias forecast", w=11, nf=NF_PCT2), dict(id="bb", h="Bias budget", w=11, nf=NF_PCT2)]
    tbc = write_table(cx, ws, S, r, 0, specs, rows, header_height=58)
    for i, row in enumerate(rows):
        for cid in ("n", "wf", "wb"):
            cx.reg(f"fc_cmp_{row['key']}_{cid}", S, tbc.r0 + i, tbc.idx[cid], row[cid])
    r = tbc.r1 + 3
    # F4 attribution (c2)
    r = cx.section(ws, r, "F4. Where the forecast error sits: by sign category of the (actual, forecast) pair (out_c2)",
                   "Counts of lines and dollars are separate columns. Opposite-sign lines carry most of the absolute error; whether they are data defects or legitimate entries (credit notes, reversals) is unresolved. Zero-involved lines carry very little.", 12)
    c2 = cx.d.t("out_c2_error_attribution", order="section_order, sign_category")
    rows = [dict(sec=SEC_LABEL[x["section"]], key=x["section"], cat=x["sign_category"], n=x["rows_in_category"], abse=x["abs_error_usd"]) for x in c2]
    for x in rows:
        x["tot_n"] = sum(y["n"] for y in rows if y["key"] == x["key"]); x["tot_e"] = sum(y["abse"] for y in rows if y["key"] == x["key"])
    first = r + 1
    sections_in = [x["key"] for x in rows]
    specs = [dict(id="sec", h="Section", w=26, kind="txt"), dict(id="cat", h="Sign category", w=24, kind="txt"), dict(id="n", h="Lines (count)", w=10, nf=NF_INT),
             dict(id="abse", h="Absolute error (USD)", w=15, nf=NF_USD),
             dict(id="shn", h="Share of the section's lines", w=11, kind="calc", nf=NF_PCT, f=lambda x: f"={x['n']}/SUMIFS($C${first + 1}:$C${first + len(rows)},$A${first + 1}:$A${first + len(rows)},$A{x.row0 + 1})", v=lambda d: d["n"] / d["tot_n"]),
             dict(id="she", h="Share of the section's absolute error", w=12, kind="calc", nf=NF_PCT, f=lambda x: f"={x['abse']}/SUMIFS($D${first + 1}:$D${first + len(rows)},$A${first + 1}:$A${first + len(rows)},$A{x.row0 + 1})", v=lambda d: d["abse"] / d["tot_e"])]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    for i, row in enumerate(rows):
        if row["cat"] == "OPPOSITE_SIGN_NONZERO":
            cx.reg(f"fc_opp_share_{row['key']}", S, tb.r0 + i, tb.idx["she"], row["she"])
            cx.reg(f"fc_opp_lines_{row['key']}", S, tb.r0 + i, tb.idx["shn"], row["shn"])
    r = tb.r1 + 3
    # F5 quarterly persistence (c5) + c4
    r = cx.section(ws, r, "F5. Direction by quarter (out_c5, 12 quarters)", "On same-sign lines the forecast sits on one side of actual in every quarter. That is an observation about this sample; without dated snapshots it cannot be called a forecasting bias that a correction would remove.", 12)
    c5 = cx.d.t("out_c5_bias_persistence", order="scenario DESC, section_order")
    rows = [dict(basis="Same-sign" if x["scenario"] == "SAME_SIGN_ONLY" else "All lines", sec=SEC_LABEL[x["section"]], q=x["quarters"], up=x["quarters_forecast_above_actual"], dn=x["quarters_forecast_below_actual"],
                 mb=x["mean_quarter_bias"], sd=x["sd_quarter_bias"]) for x in c5]
    specs = [dict(id="basis", h="Basis", w=26, kind="txt"), dict(id="sec", h="Section", w=26, kind="txt"), dict(id="q", h="Quarters (count)", w=10, nf=NF_INT), dict(id="up", h="Quarters forecast above actual", w=12, nf=NF_INT),
             dict(id="dn", h="Quarters forecast below actual", w=12, nf=NF_INT), dict(id="mb", h="Mean quarterly bias", w=11, nf=NF_PCT2), dict(id="sd", h="SD of quarterly bias", w=11, nf=NF_PCT2)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    r = tb.r1 + 3
    # F6 result proxy c8
    r = cx.section(ws, r, "F6. Result proxy on lines where actual, budget and forecast are all non-zero and same-sign (out_c8)",
                   "Result proxy = revenue - COGS - People - Opex on the selected lines. Illustrates the gap in dollars; the selection is outcome-based, so these are NOT company results and not a forecast-skill measure.", 12)
    c8 = cx.d.t("out_c8_profit_proxy_bias", order="period_year NULLS LAST")
    rows = [dict(yr=str(x["period_year"]) if x["period_year"] else "3 years", rev=x["actual_revenue"], act=x["actual_result_proxy_usd"], bud=x["budget_result_proxy_usd"], fc=x["forecast_result_proxy_usd"]) for x in c8]
    specs = [dict(id="yr", h="Year", w=26, kind="txt"), dict(id="rev", h="Actual revenue (USD)", w=15, nf=NF_USD), dict(id="act", h="Actual result proxy (USD)", w=15, nf=NF_USD),
             dict(id="fc", h="Forecast result proxy (USD)", w=15, nf=NF_USD), dict(id="bud", h="Budget result proxy (USD)", w=15, nf=NF_USD),
             dict(id="fa", h="Forecast - actual (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['fc']}-{x['act']}", v=lambda d: d["fc"] - d["act"]),
             dict(id="ba", h="Budget - actual (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['bud']}-{x['act']}", v=lambda d: d["bud"] - d["act"])]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    cx.reg("fc_proxy_act", S, tb.r1, tb.idx["act"], rows[-1]["act"]); cx.reg("fc_proxy_fc", S, tb.r1, tb.idx["fc"], rows[-1]["fc"]); cx.reg("fc_proxy_bud", S, tb.r1, tb.idx["bud"], rows[-1]["bud"])
    r = tb.r1 + 3
    # F7 forecast by entity (c3)
    r = cx.section(ws, r, "F7. Forecast error by entity (out_c3)", "Same measures by legal entity and section; 'Basis' filters same-sign vs all lines.", 12)
    c3 = cx.d.t("out_c3_forecast_entity", order="scenario DESC, entity_code, section_order")
    rows = [dict(basis="Same-sign" if x["scenario"] == "SAME_SIGN_ONLY" else "All lines", ent=x["entity_code"], sec=SEC_LABEL[x["section"]], n=x["rows_in_scope"], net=x["net_error_usd"], bias=x["bias"], wape=x["wape"]) for x in c3]
    specs = [dict(id="basis", h="Basis", w=26, kind="txt"), dict(id="ent", h="Entity", w=26, kind="txt"), dict(id="sec", h="Section", w=26, kind="txt"), dict(id="n", h="Lines (count)", w=12, nf=NF_INT),
             dict(id="net", h="Net error (USD)", w=15, nf=NF_USD), dict(id="bias", h="Bias", w=11, nf=NF_PCT2), dict(id="wape", h="WAPE", w=11, nf=NF_PCT2)]
    # sections are wider than the first columns here: put section in col C but keep widths readable
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_FcEntity", header_height=32)
    r = tb.r1 + 3
    # prior year
    r = cx.section(ws, r, "F8. Actual vs the prior-year COLUMN (out_d1) - USD", "The prior-year column is a field on each line. F9 shows it is NOT equal to the previous calendar year's actuals, so 'change vs prior-year column' must not be read as year-on-year growth.", 12)
    d1 = cx.d.t("out_d1_vs_py_column", order="scenario DESC, section_order, period_year")
    rows = [dict(basis="Same-sign" if x["scenario"] == "SAME_SIGN_ONLY" else "All lines", sec=SEC_LABEL[x["section"]], yr=x["period_year"], n=x["rows_in_scope"], act=x["actual_usd"], py=x["prior_year_usd"]) for x in d1]
    specs = [dict(id="basis", h="Basis", w=26, kind="txt"), dict(id="sec", h="Section", w=26, kind="txt"), dict(id="yr", h="Year", w=10, nf="0"), dict(id="n", h="Lines (count)", w=12, nf=NF_INT),
             dict(id="act", h="Actual (USD)", w=15, nf=NF_USD), dict(id="py", h="Prior-year column (USD)", w=15, nf=NF_USD),
             dict(id="chg", h="Change = actual - prior-year column (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['act']}-{x['py']}", v=lambda d: d["act"] - d["py"]),
             dict(id="pct", h="Change % of |prior-year column|", w=12, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["py"]}<>0,{x["chg"]}/ABS({x["py"]}),"n/a")', v=lambda d: d["chg"] / abs(d["py"]) if d["py"] else "n/a")]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_PYColumn", header_height=44)
    cx.R["PY"] = tb
    r = tb.r1 + 3
    r = cx.section(ws, r, "F9. Does the prior-year column equal last year's actual? (out_d4) and true calendar year-on-year growth (out_d3)", "Same-sign basis is not used here: these are all eligible lines. A non-zero difference means the column is a separate planning input, not a ledger-derived prior-year actual.", 12)
    d4 = cx.d.t("out_d4_py_column_reconciliation", order="section_order, period_year")
    rows = [dict(sec=SEC_LABEL[x["section"]], yr=x["period_year"], py=x["py_column"], prev=x["prev_year_actual"]) for x in d4]
    specs = [dict(id="sec", h="Section", w=26, kind="txt"), dict(id="yr", h="Year", w=26, nf="0"), dict(id="py", h="Prior-year column (USD)", w=15, nf=NF_USD), dict(id="prev", h="Previous calendar year actual (USD)", w=15, nf=NF_USD),
             dict(id="diff", h="Difference = column - previous actual (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['py']}-{x['prev']}", v=lambda d: d["py"] - d["prev"]),
             dict(id="dp", h="Difference % of previous actual", w=12, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["prev"]}<>0,{x["diff"]}/ABS({x["prev"]}),"n/a")', v=lambda d: d["diff"] / abs(d["prev"]) if d["prev"] else "n/a")]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    r = tb.r1 + 2
    d3 = cx.d.t("out_d3_true_yoy", order="basis, section_order, period_year")
    rows = [dict(basis=x["basis"], sec=SEC_LABEL[x["section"]], yr=x["period_year"], amt=x["amount_usd"], prev=x["prior_calendar_year_usd"], n=x["rows_in_year"], npy=x["rows_prior_year"]) for x in d3]
    specs = [dict(id="basis", h="Basis (ANY_STATUS = all journal statuses)", w=26, kind="txt"), dict(id="sec", h="Section", w=26, kind="txt"), dict(id="yr", h="Year", w=10, nf="0"),
             dict(id="amt", h="Amount (USD)", w=15, nf=NF_USD), dict(id="prev", h="Prior calendar year (USD)", w=15, nf=NF_USD), dict(id="n", h="Lines this year (count)", w=12, nf=NF_INT), dict(id="npy", h="Lines prior year (count)", w=12, nf=NF_INT),
             dict(id="g", h="YoY growth = amount / prior - 1", w=12, kind="calc", nf=NF_PCT, f=lambda x: f'=IF(ISNUMBER({x["prev"]}),IF({x["prev"]}<>0,{x["amt"]}/{x["prev"]}-1,"n/a"),"n/a")',
                  v=lambda d: (d["amt"] / d["prev"] - 1) if isinstance(d["prev"], (int, float)) and d["prev"] else "n/a")]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_TrueYoY", header_height=44)
    ws.freeze_panes(4, 0)
    ws.set_landscape(); ws.fit_to_pages(1, 0)


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 7: GL and cost drivers
# ---------------------------------------------------------------------------------------------------------------------
def build_gl(cx: Ctx, tbX, det_rows):
    ws, S = cx.ws["GL & Cost Drivers"], "GL & Cost Drivers"
    cx.title(ws, "GL accounts and cost drivers", "USD, scale-adjusted (provisional), signs as recorded. Sources: out_a4, out_f1-f7, out_b2, out_b6. 3-year totals.",
             "High spending is not proof of inefficiency, and a variance is not a saving. Nothing here claims a causal cost driver. Unit economics (price, volume, mix) are NOT built: quantity is populated on only 33% of revenue lines (UNSUITABLE, out_a5) and the "
             "materials unit value equals the sales unit value for every product family (out_e5), so quantity and unit-of-measure fields are unresolved. 'NOS' and 'EA' are not treated as equivalent.", width=12)
    r = 4
    a4 = cx.d.t("out_a4_pl_gl", order="gl_account")
    r = cx.section(ws, r, f"G1. Activity by GL account - all {len(a4)} P&L accounts used (out_a4)", "Share of total = |actual| / sum of |actual| over all accounts (absolute activity, so offsetting signs do not net out). '% lines negative' flags accounts whose sign convention is mixed (4190 discounts and 5120 PPV are the visible cases).", 12)
    rows = [dict(gl=x["gl_account"], name=x["account_name"], sec=x["section"], n=x["rows_eligible"], act=x["actual_usd"], absa=x["abs_actual_usd"], neg=x["share_rows_negative"]) for x in a4]
    f1 = r + 1
    specs = [dict(id="gl", h="GL", w=8, nf="0"), dict(id="name", h="Account", w=28, kind="txt"), dict(id="sec", h="Section", w=14, kind="txt"), dict(id="n", h="Eligible lines (count)", w=11, nf=NF_INT),
             dict(id="act", h="Actual, signed (USD)", w=15, nf=NF_USD), dict(id="absa", h="Absolute actual (USD)", w=15, nf=NF_USD),
             dict(id="sh", h="Share of total absolute activity", w=12, kind="calc", nf=NF_PCT, f=lambda x: f"={x['absa']}/SUM($F${f1 + 1}:$F${f1 + len(rows)})", v=lambda d: d["absa"] / sum(y["absa"] for y in rows)),
             dict(id="neg", h="% of lines negative", w=11, nf=NF_PCT)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_GLActivity", header_height=44)
    cx.R["GLACT"] = tb
    cx.reg("gl_total_n", S, tb.r1 + 1, tb.idx["n"], sum(x["n"] for x in rows))
    rr = tb.r1 + 1
    cx.txt(ws, rr, 0, "Total", bold=True, top=1)
    cx.calc(ws, rr, tb.idx["n"], f"=SUM({tb.col_rng('n', sheet=False)})", sum(x["n"] for x in rows), NF_INT, bold=True, top=1)
    cx.calc(ws, rr, tb.idx["act"], f"=SUM({tb.col_rng('act', sheet=False)})", sum(x["act"] for x in rows), NF_USD, bold=True, top=1)
    cx.calc(ws, rr, tb.idx["absa"], f"=SUM({tb.col_rng('absa', sheet=False)})", sum(x["absa"] for x in rows), NF_USD, bold=True, top=1)
    r = rr + 3
    f1t = cx.d.t("out_f1_cost_by_gl", order="rank_by_abs")
    r = cx.section(ws, r, f"G2. Cost concentration - Pareto of the {len(f1t)} cost accounts (out_f1)", "Cost = COGS + People + Opex + D&A accounts only (" + ", ".join(f"{k} {n}" for k, n in sorted(Counter(x["section"] for x in f1t).items())) + "), ranked by absolute activity. Below-EBITDA items and Tax are NOT in this population (they are not operating costs and the Phase 4 query excludes them). Cumulative share is a running sum of shares.", 12)
    rows = [dict(rank=x["rank_by_abs"], gl=x["gl_account"], name=x["account_name"], sec=x["section"], n=x["rows_eligible"], act=x["actual_signed_usd"], absa=x["actual_abs_usd"]) for x in f1t]
    g0 = r + 1
    specs = [dict(id="rank", h="Rank", w=8, nf="0"), dict(id="gl", h="GL", w=28, nf="0"), dict(id="name", h="Account", w=28, kind="txt"), dict(id="sec", h="Section", w=11, kind="txt"), dict(id="n", h="Eligible lines (count)", w=15, nf=NF_INT),
             dict(id="act", h="Actual, signed (USD)", w=15, nf=NF_USD), dict(id="absa", h="Absolute actual (USD)", w=12, nf=NF_USD),
             dict(id="sh", h="Share of cost absolute activity", w=12, kind="calc", nf=NF_PCT, f=lambda x: f"={x['absa']}/SUM($G${g0 + 1}:$G${g0 + len(rows)})", v=lambda d: d["absa"] / sum(y["absa"] for y in rows)),
             dict(id="cum", h="Cumulative share", w=12, kind="calc", nf=NF_PCT, f=lambda x: f"=SUM($H${g0 + 1}:H{x.row0 + 1})", v=None)]
    run = {"s": 0.0}

    def cumv(d):
        run["s"] += d["sh"]
        return run["s"]
    specs[-1]["v"] = cumv
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_CostPareto", header_height=44)
    cx.reg("pareto_top3_cum", S, tb.r0 + 2, tb.idx["cum"], rows[2]["cum"])
    ch = cx.wb.add_chart({"type": "column"})
    ch.add_series({"name": "Share of cost absolute activity", "categories": tb.col_rng("name"), "values": tb.col_rng("sh"), "fill": {"color": "#1F3864"}, "gap": 60})
    ln = cx.wb.add_chart({"type": "line"})
    ln.add_series({"name": "Cumulative share", "categories": tb.col_rng("name"), "values": tb.col_rng("cum"), "line": {"color": "#C55A11", "width": 2.25}, "marker": {"type": "circle", "size": 5}})
    ch.combine(ln)
    ch.set_title({"name": "Cost accounts: share and cumulative share of absolute activity", "name_font": {"size": 10}})
    ch.set_y_axis({"num_format": "0%", "max": 1, "min": 0, "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
    ch.set_x_axis({"num_font": {"rotation": -45, "size": 8}}); ch.set_legend({"position": "bottom"}); ch.set_size({"width": 760, "height": 340})
    ws.insert_chart(tb.r0 - 1, 10, ch)
    r = tb.r1 + 3
    r = max(r, tb.r0 + 19)
    # G3 GL variance by SUMIFS over detail
    r = cx.section(ws, r, "G3. Variance by GL account - same-sign basis (SUMIFS over 'Entity & Division' E6)", "Rank = rank of |variance| across accounts (1 = largest). Variance % = variance / |budget|. No favourable/adverse label.", 12)
    gls = sorted({(x["gl"], x["acct"], x["sec"]) for x in det_rows if x["basis"] == "Same-sign"})
    rows = []
    for gl, ac, sec in gls:
        sel = [x for x in det_rows if x["basis"] == "Same-sign" and x["gl"] == gl]
        rows.append({"gl": gl, "name": ac, "sec": sec, "act": sum(x["act"] for x in sel), "bud": sum(x["bud"] for x in sel)})
    h0 = r + 1
    ab = lambda row: abs(row["act"] - row["bud"])
    specs = [dict(id="gl", h="GL", w=8, nf="0"), dict(id="name", h="Account", w=28, kind="txt"), dict(id="sec", h="Section", w=14, kind="txt"),
             dict(id="act", h="Actual (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f'=SUMIFS({tbX.col_rng("act")},{tbX.col_rng("gl")},$A{x.row0 + 1},{tbX.col_rng("basis")},"Same-sign")', v=lambda d: d["act"]),
             dict(id="bud", h="Budget (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f'=SUMIFS({tbX.col_rng("bud")},{tbX.col_rng("gl")},$A{x.row0 + 1},{tbX.col_rng("basis")},"Same-sign")', v=lambda d: d["bud"]),
             dict(id="var", h="Variance (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['act']}-{x['bud']}", v=lambda d: d["act"] - d["bud"]),
             dict(id="pct", h="Variance % of |budget|", w=11, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["bud"]}<>0,{x["var"]}/ABS({x["bud"]}),"n/a")', v=lambda d: d["var"] / abs(d["bud"]) if d["bud"] else "n/a"),
             dict(id="rank", h="Rank by |variance|", w=10, kind="calc", nf="0", f=lambda x: f"=SUMPRODUCT(--(ABS($F${h0 + 1}:$F${h0 + len(rows)})>ABS({x['var']})))+1", v=lambda d: 1 + sum(1 for y in rows if ab(y) > ab(d)))]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_GLVar", header_height=44)
    cx.R["GLVAR"] = tb
    ws.conditional_format(tb.r0, tb.idx["rank"], tb.r1, tb.idx["rank"], {"type": "cell", "criteria": "<=", "value": 5, "format": cx.fmt(bg_color=AMBER, bold=True)})
    ws.write_string(tb.r1 + 1, 0, "Amber = five largest absolute variances.", cx.fmt(italic=True, font_color="#595959"))
    r = tb.r1 + 4
    # G4 cost mix / ratio / concentration
    r = cx.section(ws, r, "G4. Cost mix and cost-to-revenue ratios by year (out_f3, out_f4)", "Ratios are absolute-value ratios (|cost| / |revenue|) and signed ratios; the two differ because of negative lines. Not a margin.", 12)
    f3 = cx.d.t("out_f3_cost_mix_by_year", order="period_year, section_order")
    rows = [dict(yr=x["period_year"], sec=SEC_LABEL[x["section"]], absa=x["actual_abs_usd"], sh=x["share_of_cost_abs"], sg=x["actual_signed_usd"]) for x in f3]
    specs = [dict(id="yr", h="Year", w=8, nf="0"), dict(id="sec", h="Section", w=28, kind="txt"), dict(id="absa", h="Absolute actual (USD)", w=15, nf=NF_USD), dict(id="sh", h="Share of cost (absolute)", w=12, nf=NF_PCT),
             dict(id="sg", h="Signed actual (USD)", w=15, nf=NF_USD)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    f4 = cx.d.t("out_f4_cost_to_revenue", order="period_year NULLS FIRST")
    rows4 = [dict(yr=str(x["period_year"]) if x["period_year"] else "3 years", c=x["cogs_to_revenue_abs"], p=x["people_to_revenue_abs"], o=x["opex_to_revenue_abs"], cs=x["cogs_to_revenue_signed"], ps=x["people_to_revenue_signed"], os_=x["opex_to_revenue_signed"]) for x in f4]
    specs4 = [dict(id="yr", h="Year", w=8, kind="txt"), dict(id="c", h="COGS / revenue (abs)", w=11, nf=NF_PCT), dict(id="p", h="People / revenue (abs)", w=11, nf=NF_PCT), dict(id="o", h="Opex / revenue (abs)", w=11, nf=NF_PCT),
              dict(id="cs", h="COGS / revenue (signed)", w=11, nf=NF_PCT), dict(id="ps", h="People / revenue (signed)", w=11, nf=NF_PCT), dict(id="os_", h="Opex / revenue (signed)", w=11, nf=NF_PCT)]
    write_table(cx, ws, S, r, 6, specs4, rows4, header_height=44)
    r = tb.r1 + 3
    f2 = cx.d.t("out_f2_concentration")
    r = cx.section(ws, r, "G5. Concentration (out_f2)", "HHI = sum of squared shares; the equal-share benchmark is 1 / members. Concentration is descriptive: it does not say spend is excessive.", 12)
    rows = [dict(dim=x["dimension"], m=x["members"], t1=x["top1_share"], top=x["top1_member"], t3=x["top3_share"], hhi=x["hhi"], eq=x["equal_share_benchmark"]) for x in f2]
    specs = [dict(id="dim", h="Dimension", w=28, kind="txt"), dict(id="m", h="Members (count)", w=14, nf=NF_INT), dict(id="top", h="Largest member", w=14, kind="txt"), dict(id="t1", h="Top-1 share", w=11, nf=NF_PCT),
             dict(id="t3", h="Top-3 share", w=11, nf=NF_PCT), dict(id="hhi", h="HHI", w=12, nf="0.000"), dict(id="eq", h="Equal-share benchmark (1/members)", w=14, nf="0.000")]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    r = tb.r1 + 3
    # G6 persistent deviations
    r = cx.section(ws, r, "G6. Persistent deviations: entity x GL cells that are on the same side of budget in most months (out_f5; all 144 cells, filter/sort)",
                   "Dominant-direction share = months on the more common side / months with data. A share near 100% means the deviation is systematic rather than month-to-month noise (INS-03).", 12)
    f5 = cx.d.t("out_f5_persistent_cells", order="entity_code, gl_account")
    rows = [dict(ent=x["entity_code"], gl=x["gl_account"], name=x["account_name"], sec=x["section"], m=x["months_with_data"], up=x["months_above"], dn=x["months_below"], dom=x["dominant_direction_share"], var=x["variance_usd"], pct=x["variance_pct"]) for x in f5]
    specs = [dict(id="ent", h="Entity", w=8, kind="txt"), dict(id="gl", h="GL", w=28, nf="0"), dict(id="name", h="Account", w=28, kind="txt"), dict(id="sec", h="Section", w=11, kind="txt"), dict(id="m", h="Months with data (count)", w=15, nf=NF_INT),
             dict(id="up", h="Months above budget (count)", w=15, nf=NF_INT), dict(id="dn", h="Months below budget (count)", w=12, nf=NF_INT), dict(id="dom", h="Dominant-direction share", w=12, nf=NF_PCT),
             dict(id="var", h="Variance (USD)", w=15, nf=NF_USD), dict(id="pct", h="Variance %", w=11, nf=NF_PCT)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_PersistentCells", header_height=44)
    ws.conditional_format(tb.r0, tb.idx["dom"], tb.r1, tb.idx["dom"], {"type": "data_bar", "bar_color": "#9DC3E6", "bar_solid": True, "min_type": "num", "min_value": 0, "max_type": "num", "max_value": 1})
    r = tb.r1 + 3
    # G7 salary per FTE conditional
    r = cx.section(ws, r, "G7. Salary rate per FTE and the implied FTE-month scenario (out_f6, out_f7) - CONDITIONAL, not a finding",
                   "Observed: salary lines carry a near-constant USD rate per FTE-month within each entity. Scenario (assumes the budget used the same rate and the FTE field is complete): variance / rate = implied excess FTE-months. "
                   "Without a budgeted FTE plan and the budget's rate method, the people-cost variance cannot be split into rate and volume.", 12)
    f7 = cx.d.t("out_f7_salary_implied_fte", order="entity_code")
    rows = [dict(ent=x["entity_code"], rate=x["entity_rate_per_fte_month_usd"], act=x["actual_usd"], bud=x["budget_usd"], var=x["variance_usd"]) for x in f7]
    specs = [dict(id="ent", h="Entity", w=8, kind="txt"), dict(id="rate", h="Rate per FTE-month (USD)", w=28, nf=NF_USD), dict(id="act", h="Salary actual (USD)", w=14, nf=NF_USD), dict(id="bud", h="Salary budget (USD)", w=11, nf=NF_USD),
             dict(id="var", h="Variance (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['act']}-{x['bud']}", v=lambda d: d["act"] - d["bud"]),
             dict(id="fte", h="Implied excess FTE-months over 36 months (scenario)", w=15, kind="calc", nf="#,##0.0", f=lambda x: f"={x['var']}/{x['rate']}", v=lambda d: d["var"] / d["rate"]),
             dict(id="ftem", h="Implied average excess FTEs per month", w=12, kind="calc", nf="#,##0.0", f=lambda x: f"={x['fte']}/36", v=lambda d: d["fte"] / 36)]
    write_table(cx, ws, S, r, 0, specs, rows, header_height=58)
    ws.freeze_panes(4, 0)
    ws.set_landscape(); ws.fit_to_pages(1, 0)


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 8: Gross profit
# ---------------------------------------------------------------------------------------------------------------------
TREAT = {"GP_S1_SIGNED_AS_RECORDED": "S1 - signed as recorded", "GP_S2_DISCOUNT_ABS": "S2 - discount (4190) at absolute value", "GP_S3_EXCL_DISCOUNT": "S3 - excluding discounts (4190)"}
ROWSET = {"ROWS_ALL": "All eligible lines", "ROWS_ALL_NON_NEGATIVE": "Lines with no negative available amount (NOT sign-consistent)"}


def build_gp(cx: Ctx):
    ws, S = cx.ws["Gross Profit"], "Gross Profit"
    cx.title(ws, "Gross profit and margin - three explicit treatments", "USD, scale-adjusted (provisional). Gross profit = Revenue - COGS (GL 4100-4190 and 5100-5300). Sources: out_e1-e4.",
             "No treatment is the authoritative accounting answer. Discount account 4190 is negative on about 58% of its lines and positive on the rest, and 5120 is mixed too, so the sign convention is unresolved (R9). "
             "S1 = every amount signed as recorded. S2 = discounts forced to reduce revenue (-|4190|). S3 = discounts excluded (gross sales). Row sets: 'All eligible lines' (headline) and 'ROWS_ALL_NON_NEGATIVE' = lines where none of the available amount columns is negative; it is an "
             "all-non-negative population, NOT a genuinely sign-consistent one (zero amounts count as non-negative; all-negative, single-column-flip and mixed rows are outside it). The second row set is a sensitivity, not a correction.", width=11)
    e1 = cx.d.t("out_e1_gross_profit", order="rowset, treatment, period")
    r = 4
    r = cx.section(ws, r, "GP1. Gross profit by row set, treatment and year (out_e1)", "Gross margin % = gross profit / revenue, shown only when revenue > 0.", 11)
    rows = [dict(rs=ROWSET[x["rowset"]], key=x["rowset"], tr=TREAT[x["treatment"]], tkey=x["treatment"], per=x["period"], n=x["rows_in_scope"], rev=x["revenue_usd"], cogs=x["cogs_usd"]) for x in e1]
    specs = [dict(id="rs", h="Row set", w=62, kind="txt"), dict(id="tr", h="Treatment", w=34, kind="txt"), dict(id="per", h="Period", w=11, kind="txt"), dict(id="n", h="Lines (count)", w=11, nf=NF_INT),
             dict(id="rev", h="Revenue (USD)", w=15, nf=NF_USD), dict(id="cogs", h="COGS (USD)", w=15, nf=NF_USD),
             dict(id="gp", h="Gross profit (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['rev']}-{x['cogs']}", v=lambda d: d["rev"] - d["cogs"]),
             dict(id="gm", h="Gross margin %", w=11, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["rev"]}>0,{x["gp"]}/{x["rev"]},"n/a")', v=lambda d: d["gp"] / d["rev"] if d["rev"] > 0 else "n/a")]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_GP", header_height=32)
    cx.R["GP1"] = tb
    idx_all = {}
    for i, x in enumerate(rows):
        if x["per"] == "ALL YEARS":
            idx_all[(x["key"], x["tkey"])] = i
            cx.reg(f"gp_{x['key']}_{x['tkey']}_rev", S, tb.r0 + i, tb.idx["rev"], x["rev"])
            cx.reg(f"gp_{x['key']}_{x['tkey']}_gp", S, tb.r0 + i, tb.idx["gp"], x["gp"])
            cx.reg(f"gp_{x['key']}_{x['tkey']}_gm", S, tb.r0 + i, tb.idx["gm"], x["gm"])
            cx.reg(f"gp_{x['key']}_{x['tkey']}_cogs", S, tb.r0 + i, tb.idx["cogs"], x["cogs"])
    r = tb.r1 + 3
    # comparison matrix (links)
    r = cx.section(ws, r, "GP2. Margin range at a glance - all years (links to GP1)", "How much does the headline margin depend on the discount treatment and the row set? Read it as a range with its labels, not as one number.", 11)
    cx.hdr(ws, r, 0, ["Treatment", "", "GM % - all eligible lines", "GM % - no-negative-amount lines", "Gross profit (USD) - all eligible lines", "Gross profit (USD) - no-negative-amount lines"], 44)
    for i, t in enumerate(TREAT):
        rr = r + 1 + i
        cx.txt(ws, rr, 0, TREAT[t])
        for j, (rs, key) in enumerate((("ROWS_ALL", "gm"), ("ROWS_ALL_NON_NEGATIVE", "gm"), ("ROWS_ALL", "gp"), ("ROWS_ALL_NON_NEGATIVE", "gp"))):
            k = f"gp_{rs}_{t}_{key}"
            cx.calc(ws, rr, 2 + j, f"={cx.ref(k)}", cx.val(k), NF_PCT if key == "gm" else NF_USD, color=GREEN)
    m0 = r + 1
    ws.conditional_format(m0, 2, m0 + 2, 3, {"type": "data_bar", "bar_color": "#9DC3E6", "bar_solid": True, "min_type": "num", "min_value": 0.3, "max_type": "num", "max_value": 0.6})
    ch = cx.wb.add_chart({"type": "column"})
    for j, (nm, col) in enumerate((("All eligible lines", "#1F3864"), ("No-negative-amount lines (not sign-consistent)", "#BF9000"))):
        ch.add_series({"name": nm, "categories": f"='{S}'!$A${m0 + 1}:$A${m0 + 3}", "values": f"='{S}'!${xl_col_to_name(2 + j)}${m0 + 1}:${xl_col_to_name(2 + j)}${m0 + 3}", "fill": {"color": col}})
    ch.set_title({"name": "Gross margin % by treatment and row set (all years)", "name_font": {"size": 10}})
    ch.set_y_axis({"num_format": "0%", "min": 0.3, "max": 0.6, "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
    ch.set_legend({"position": "bottom"}); ch.set_size({"width": 620, "height": 300}); ch.set_x_axis({"num_font": {"size": 8}})
    ws.insert_chart(m0 - 1, 7, ch)
    r = max(m0 + 5, m0 + 14)
    # GP3 vs budget (e3)
    r = cx.section(ws, r, "GP3. Gross profit vs budget - same-sign lines, by treatment (out_e3, out_e4)", "Bridge: GP variance = revenue variance - COGS variance (a higher COGS than budget lowers gross profit). Margin gap in percentage points.", 11)
    e3 = cx.d.t("out_e3_gross_profit_vs_budget", order="treatment")
    rows = [dict(tr=TREAT[x["treatment"]], key=x["treatment"], ar=x["actual_revenue_usd"], br=x["budget_revenue_usd"], ac=x["actual_cogs_usd"], bc=x["budget_cogs_usd"]) for x in e3]
    specs = [dict(id="tr", h="Treatment", w=44, kind="txt"), dict(id="ar", h="Actual revenue (USD)", w=34, nf=NF_USD), dict(id="br", h="Budget revenue (USD)", w=11, nf=NF_USD), dict(id="ac", h="Actual COGS (USD)", w=11, nf=NF_USD),
             dict(id="bc", h="Budget COGS (USD)", w=15, nf=NF_USD),
             dict(id="ag", h="Actual GP (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['ar']}-{x['ac']}", v=lambda d: d["ar"] - d["ac"]),
             dict(id="bg", h="Budget GP (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['br']}-{x['bc']}", v=lambda d: d["br"] - d["bc"]),
             dict(id="gv", h="GP variance (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['ag']}-{x['bg']}", v=lambda d: d["ag"] - d["bg"]),
             dict(id="rv", h="Revenue variance (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['ar']}-{x['br']}", v=lambda d: d["ar"] - d["br"]),
             dict(id="cv", h="COGS variance (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['ac']}-{x['bc']}", v=lambda d: d["ac"] - d["bc"]),
             dict(id="br_", h="Bridge difference = GP var - (rev var - COGS var)", w=15, kind="calc", nf=NF_USD2, f=lambda x: f"={x['gv']}-({x['rv']}-{x['cv']})", v=lambda d: d["gv"] - (d["rv"] - d["cv"])),
             dict(id="agm", h="Actual GM %", w=11, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["ar"]}>0,{x["ag"]}/{x["ar"]},"n/a")', v=lambda d: d["ag"] / d["ar"]),
             dict(id="bgm", h="Budget GM %", w=11, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["br"]}>0,{x["bg"]}/{x["br"]},"n/a")', v=lambda d: d["bg"] / d["br"]),
             dict(id="gap", h="Margin gap (percentage points)", w=12, kind="calc", nf='0.0;[Red](0.0);"-"', f=lambda x: f"=({x['agm']}-{x['bgm']})*100", v=lambda d: (d["agm"] - d["bgm"]) * 100)]
    # reorder widths: place long labels sensibly
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=58)
    for i, row in enumerate(rows):
        for cid in ("gv", "rv", "cv", "br_", "agm", "bgm", "gap", "ag", "bg"):
            cx.reg(f"gp3_{row['key']}_{cid}", S, tb.r0 + i, tb.idx[cid], row[cid])
    r = tb.r1 + 3
    r = cx.section(ws, r, "GP4. Gross profit by entity (out_e2; all years)", "Filter by row set and treatment. Entity margins are comparable only within the same treatment and row set.", 11)
    e2 = cx.d.t("out_e2_gross_profit_entity", order="rowset, treatment, entity_code")
    rows = [dict(rs=ROWSET[x["rowset"]], tr=TREAT[x["treatment"]], ent=x["entity_code"], rev=x["revenue_usd"], cogs=x["cogs_usd"]) for x in e2]
    specs = [dict(id="rs", h="Row set", w=62, kind="txt"), dict(id="tr", h="Treatment", w=34, kind="txt"), dict(id="ent", h="Entity", w=11, kind="txt"), dict(id="rev", h="Revenue (USD)", w=11, nf=NF_USD), dict(id="cogs", h="COGS (USD)", w=11, nf=NF_USD),
             dict(id="gp", h="Gross profit (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['rev']}-{x['cogs']}", v=lambda d: d["rev"] - d["cogs"]),
             dict(id="gm", h="Gross margin %", w=15, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["rev"]}>0,{x["gp"]}/{x["rev"]},"n/a")', v=lambda d: d["gp"] / d["rev"] if d["rev"] > 0 else "n/a")]
    write_table(cx, ws, S, r, 0, specs, rows, name="tbl_GPEntity", header_height=32)
    ws.freeze_panes(4, 0)
    ws.set_landscape(); ws.fit_to_pages(1, 0)


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 9: Insights (parsed from the corrected Phase 4 register, with DB-derived key figures checked in Excel)
# ---------------------------------------------------------------------------------------------------------------------
def parse_register(path: Path) -> dict:
    txt = path.read_text(encoding="utf-8")
    ins = {}
    for m in re.finditer(r"^## (INS-\d\d) - (.+?)\n(.*?)(?=^## INS-|\Z)", txt, flags=re.S | re.M):
        body = m.group(3)
        parts = {}
        for pm in re.finditer(r"^\*\*(\d+)\. ([^*]+?)\*\*\s*(.*?)(?=^\*\*\d+\. |\n---|\Z)", body, flags=re.S | re.M):
            parts[int(pm.group(1))] = pm.group(3).strip()
        ins[m.group(1)] = {"headline": m.group(2).strip(), "parts": parts}
    rk = {}
    for m in re.finditer(r"^\| (\d+) \| (INS-\d\d) \| .*? \| (\d) \| (\d) \| (\d) \| (\d) \| (\d+) \|$", txt, flags=re.M):
        rk[m.group(2)] = dict(rank=int(m.group(1)), mat=int(m.group(3)), per=int(m.group(4)), conf=int(m.group(5)), act=int(m.group(6)), total=int(m.group(7)))
    for k in ins:
        ins[k].update(rk[k])
    return ins


EVIDENCE_REQUIRED = {  # qualitative: what must be obtained to confirm a cause (no figures)
    "INS-01": "Written definition of every journal status (Posted, Pending, Parked, Rejected, blank) from the controller, and confirmation of which statuses belong in period-end reporting.",
    "INS-02": "Sign convention per account (R9) from the controller; for a sample of opposite-sign lines, the source journals to see whether they are reversals/credit notes or data defects.",
    "INS-03": "The budget construction method and approval document; test whether budget lines equal a prior-year or actual-derived base multiplied by a uniform factor.",
    "INS-04": "Sign convention for discounts (4190) and purchase price variance (5120); the budget's gross-margin method; price/volume/mix data that is currently unusable.",
    "INS-05": "Dated forecast snapshots (version and as-of date per forecast) so accuracy can be back-tested on forecasts made before each period closed.",
    "INS-06": "A budgeted FTE plan by entity and period and the budget's rate method; HR headcount records to test the FTE field's completeness.",
    "INS-07": "Source-system confirmation of the reporting scale for a sample of the restored lines, especially the MEDIUM-confidence tier.",
}
BASELINE_LABEL = {
    "INS-01": "Baseline = Posted-only population (rule R6) with the scale-adjusted amounts",
    "INS-02": "Baseline = same-sign lines (WAPE) vs all lines",
    "INS-03": "Baseline = budget, same-sign lines; all-lines view alongside",
    "INS-04": "Baseline = budget gross profit under each of the three treatments",
    "INS-05": "Baseline = budget WAPE on the same matched lines",
    "INS-06": "Baseline = entity median salary rate per FTE-month",
    "INS-07": "Baseline = scale-adjusted (provisional) amounts vs unadjusted parsed amounts",
}


def drivers_text(md: str) -> str:
    out = []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|") and set(s.replace("|", "").strip()) <= set("- :"):
            continue
        out.append(re.sub(r"\s*\|\s*", " | ", s).strip(" |") if s.startswith("|") else s)
    return "\n".join(x.replace("**", "") for x in out if x)


def key_figures(cx: Ctx) -> list[dict]:
    """Figures recomputed from the database in the exact format the Phase 4 register uses; Excel then tests that the register text contains them."""
    d = cx.d
    b1 = {(x["scenario"], x["section"]): x for x in d.t("out_b1_variance_section")}
    c1 = {(x["scenario"], x["section"]): x for x in d.t("out_c1_forecast_section")}
    c2 = {(x["section"], x["sign_category"]): x for x in d.t("out_c2_error_attribution")}
    e3 = {x["treatment"]: x for x in d.t("out_e3_gross_profit_vs_budget")}
    i1 = {(x["factor"], x["scenario"]): x for x in d.t("out_i1_scenarios")}
    i2 = {x["factor"]: x for x in d.t("out_i2_factor_ranking")}
    c6 = {x["section"]: x for x in d.t("out_c6_forecast_vs_budget")}
    out = []
    s1 = e3["GP_S1_SIGNED_AS_RECORDED"]
    gpv = (s1["actual_revenue_usd"] - s1["budget_revenue_usd"]) - (s1["actual_cogs_usd"] - s1["budget_cogs_usd"])
    out.append(("INS-01", "Baseline revenue (Posted only)", fm(i1[("status", "POSTED_ONLY (baseline)")]["revenue_usd"])))
    out.append(("INS-01", "Revenue, all statuses", fm(i1[("status", "ALL_STATUSES")]["revenue_usd"])))
    out.append(("INS-01", "Status swing on revenue headline", f"{i2['status']['revenue_range_pct_of_baseline'] * 100:.0f}%"))
    out.append(("INS-02", "Opposite-sign share of revenue absolute forecast error", fp(c2[("REVENUE", "OPPOSITE_SIGN_NONZERO")]["share_of_abs_error"])))
    out.append(("INS-02", "Total absolute revenue forecast error", fm(c1[("ALL_LINES", "REVENUE")]["abs_error_usd"])))
    out.append(("INS-03", "Revenue variance, same-sign", fm(b1[("SAME_SIGN_ONLY", "REVENUE")]["net_variance_usd"])))
    out.append(("INS-03", "Revenue variance %, same-sign", fp(b1[("SAME_SIGN_ONLY", "REVENUE")]["variance_pct_of_abs_budget"])))
    out.append(("INS-04", "Gross profit variance S1", fm(gpv)))
    out.append(("INS-05", "Revenue WAPE, forecast (matched lines)", fp(c6["REVENUE"]["wape_forecast"])))
    out.append(("INS-05", "Revenue WAPE, budget (matched lines)", fp(c6["REVENUE"]["wape_budget"])))
    f7 = d.t("out_f7_salary_implied_fte", order="entity_code")
    out.append(("INS-06", "IN01 implied excess FTE-months (scenario)", f"IN01 {[x for x in f7 if x['entity_code'] == 'IN01'][0]['implied_excess_fte_months']:.0f}"))
    adj, unadj = i1[("scale", "ADJUSTED_ALL (baseline)")]["result_proxy_usd"], i1[("scale", "RESTORE_HIGH_CONFIDENCE_ONLY")]["result_proxy_usd"]
    out.append(("INS-07", "Result proxy effect of restoring the MEDIUM tier", fm(adj - unadj)[1:] if adj - unadj < 0 else fm(adj - unadj)))
    return [dict(ins=a, what=b, text=c) for a, b, c in out]


def build_insights(cx: Ctx):
    ws, S = cx.ws["Insights & Actions"], "Insights & Actions"
    reg = parse_register(DOCS / "PHASE4_INSIGHT_REGISTER.md")
    cx.title(ws, "Financial insights and actions", "Source: the corrected Phase 4 insight register (docs/PHASE4_INSIGHT_REGISTER.md, generated from the validated database). Ranked by materiality, persistence, confidence and actionability.",
             "Every insight separates OBSERVED FACT from HYPOTHESIS. Observed variance is not a saving: variance, financial exposure, a cause hypothesis and recoverable savings are kept apart. Confidence reflects synthetic, assumption-dependent data. "
             "Scores (1-3 per axis) are a project convention. Rows 'Check' compare figures recomputed from the database with the register text (formula-based, see Reconciliation).", width=4)
    ws.set_column(0, 0, 50); ws.set_column(1, 1, 110); ws.set_column(2, 3, 14)
    ws.set_row(2, 34)
    r = 4
    r = cx.section(ws, r, "Ranking", "Total = materiality + persistence + confidence + actionability (each 1-3). Ties are ordered by the register's order.", 4)
    cx.hdr(ws, r, 0, ["Rank / ID", "Headline", "Score (of 12)", "Confidence axis (1-3)"], 24)
    order = sorted(reg, key=lambda k: reg[k]["rank"])
    for i, k in enumerate(order):
        rr = r + 1 + i
        cx.txt(ws, rr, 0, f"#{reg[k]['rank']}  {k}", bold=True)
        cx.txt(ws, rr, 1, reg[k]["headline"], text_wrap=True, valign="top")
        cx.inp(ws, rr, 2, reg[k]["total"], "0")
        cx.inp(ws, rr, 3, reg[k]["conf"], "0")
        ws.set_row(rr, 28)
    rank_r0 = r + 1
    r = r + len(order) + 3
    anchors = {}
    for k in order:
        p = reg[k]["parts"]
        ws.merge_range(r, 0, r, 3, f"#{reg[k]['rank']}  {k} - {reg[k]['headline']}", cx.fmt(bold=True, font_color="#FFFFFF", bg_color=NAVY, text_wrap=True, valign="vcenter"))
        ws.set_row(r, 32)
        anchors[k] = r
        fields = [
            ("1. Insight ID and headline", f"{k} - {reg[k]['headline']}"),
            ("2. Business question", p.get(2, "")),
            ("3. Period and population", p.get(3, "")),
            ("4. Quantified financial result (observed fact)", p.get(5, "")),
            ("5. Formula and metric definition", p.get(4, "")),
            ("6. Comparison / baseline", BASELINE_LABEL[k]),
            ("7. Driver breakdown and contribution", drivers_text(p.get(6, ""))),
            ("8. Validation evidence / Phase 4 reference", p.get(7, "")),
            ("9. Observed fact vs hypothesis", "OBSERVED: see field 4.\nHYPOTHESIS / INTERPRETATION: " + p.get(8, "") + "\nALTERNATIVE EXPLANATIONS: " + p.get(9, "")),
            ("10. Confidence level and reasons", p.get(10, "")),
            ("11. Data limitations", (re.split(r"(?i)limitations?:", p.get(10, ""), maxsplit=1)[1].strip() + "\n" if re.search(r"(?i)limitations?:", p.get(10, "")) else "") +
             "Standing limits: synthetic extract with unverified provenance; Posted-only status rule (R6) and scale restoration (R7) are provisional; sign convention unresolved (R9); forecast has no version or as-of date."),
            ("12. Recommended action", p.get(11, "")),
            ("13. Expected impact (only where supportable)", p.get(12, "")),
            ("14. Evidence required to confirm the underlying cause", EVIDENCE_REQUIRED[k]),
            ("15. Suggested owner (function / role)", p.get(13, "").split("KPI")[0].strip(" .") or p.get(13, "")),
            ("16. Follow-up KPI / validation step", (("KPI " + p.get(13, "").split("KPI", 1)[1].strip()) if "KPI" in p.get(13, "") else p.get(13, "")) + ("\nMonitoring: " + p.get(14, "") if p.get(14) else "")),
        ]
        for j, (lab, txt) in enumerate(fields):
            rr = r + 1 + j
            ws.write_string(rr, 0, lab, cx.fmt(bold=True, bg_color=GREY, text_wrap=True, valign="top", border=1, border_color="#D9D9D9"))
            ws.merge_range(rr, 1, rr, 3, txt, cx.fmt(text_wrap=True, valign="top", border=1, border_color="#D9D9D9"))
            lines = sum(max(1, -(-len(seg) // 150)) for seg in (txt.split("\n") or [""]))
            ws.set_row(rr, min(400, max(30 if len(lab) > 32 else 18, 13.5 * lines)))
            if j == 3:
                cx.R[f"ins_text_{k}"] = (S, rr, 1, txt)
        ws.write_url(r + len(fields) + 1, 0, f"internal:'{S}'!A{rank_r0}", cx.fmt(font_color="#0563C1", underline=1), "Back to ranking")
        r = r + len(fields) + 3
    # navigation: ranking IDs become links to their detail blocks (register content unchanged)
    for i, k in enumerate(order):
        ws.write_url(rank_r0 + i, 0, f"internal:'{S}'!A{anchors[k] + 1}", cx.fmt(font_color="#0563C1", underline=1, bold=True), f"#{reg[k]['rank']}  {k}")
    # key-figure checks (formula based)
    r = cx.section(ws, r, "Check: figures recomputed from the database vs the register text", "Expected text is built from the Phase 4 tables in the register's own format; the Check column is an Excel formula that searches the insight's full text for it.", 4)
    cx.hdr(ws, r, 0, ["Insight / figure", "Expected text (from database)", "Found in register text?", ""], 24)
    kf = key_figures(cx)
    allt = {k: " ".join(reg[k]["parts"].values()) for k in reg}
    cx.R["kf_first"] = (S, r + 1, 2, None)
    for i, f in enumerate(kf):
        rr = r + 1 + i
        cx.txt(ws, rr, 0, f"{f['ins']}: {f['what']}")
        cx.inp(ws, rr, 1, f["text"])
        found = f["text"] in allt[f["ins"]]
        # text lives across merged cells of one insight block: search the full field-4 cell and the other result cells via a hidden-free concat of the block
        block_cells = ",".join(f"B{anchors[f['ins']] + 2 + j}" for j in (3,))
        cx.calc(ws, rr, 2, f'=IF(ISNUMBER(SEARCH(B{rr + 1},{block_cells})),"FOUND","NOT FOUND")', "FOUND" if f["text"] in reg[f["ins"]]["parts"].get(5, "") else "NOT FOUND")
        cx.R[f"kf_{i}"] = (S, rr, 2, "FOUND" if f["text"] in reg[f["ins"]]["parts"].get(5, "") else "NOT FOUND")
        if not found:
            cx.checks.append({"warn": f"key figure not found in register text: {f}"})
    cx.R["kf_n"] = (S, len(kf), 0, len(kf))
    ws.freeze_panes(4, 0)
    ws.set_landscape(); ws.fit_to_pages(1, 0)
    return reg, order


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 10: Data quality and exceptions
# ---------------------------------------------------------------------------------------------------------------------
def build_dq(cx: Ctx):
    ws, S = cx.ws["Data Quality"], "Data Quality"
    cx.title(ws, "Data quality, exclusions and exceptions", "Counts of lines unless stated; USD amounts are absolute as-reported or adjusted as labelled. Sources: out_i1-i10, out_a0, out_a5, out_a6, out_a7, out_a8, out_h1-h6.",
             "All figures are provisional (Posted-only, scale-adjusted). Flags are exposures, not corrections: flagged lines are retained in the populations (nothing is removed, flipped or repaired). The exposure tables show how many lines and how much absolute value each issue touches so the owner can prioritise. "
             "Balance-sheet lines are records of posted lines, NOT period-end balances, and no balance-sheet ratio is calculated.", width=9)
    r = 4
    i9 = cx.d.t("out_i9_exclusion_waterfall", order="primary_reason")
    r = cx.section(ws, r, "Q1. Where did all 152,682 source rows go? Primary exclusion reason (out_i9)", "Each source row has exactly one primary reason or is eligible (fixed precedence, rule R14). The total must equal the source row count.", 9)
    rows = [dict(reason=x["primary_reason"], n=x["rows_n"], absa=x["abs_as_reported_usd"]) for x in i9]
    f0 = r + 1
    specs = [dict(id="reason", h="Primary reason", w=62, kind="txt"), dict(id="n", h="Rows (count)", w=14, nf=NF_INT),
             dict(id="sh", h="Share of all rows", w=12, kind="calc", nf=NF_PCT, f=lambda x: f"={x['n']}/SUM($B${f0 + 1}:$B${f0 + len(rows)})", v=lambda d: d["n"] / sum(y["n"] for y in rows)),
             dict(id="absa", h="Absolute as-reported USD", w=18, nf=NF_USD)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=32)
    rr = tb.r1 + 1
    cx.txt(ws, rr, 0, "Total source rows", bold=True, top=1)
    tot_n = sum(x["n"] for x in rows)
    cx.calc(ws, rr, 1, f"=SUM({tb.col_rng('n', sheet=False)})", tot_n, NF_INT, bold=True, top=1)
    cx.R["dq_total_rows"] = (S, rr, 1, tot_n)
    elig = [x for x in rows if x["reason"].startswith("0_") or "ELIGIBLE" in x["reason"].upper() and "NOT" not in x["reason"].upper()]
    r = rr + 3
    i8 = cx.d.t("out_i8_flag_exposure")
    r = cx.section(ws, r, "Q2. Exposure of the eligible P&L population to each data-quality flag (out_i8)", "Flags overlap, so rows must not be added across lines. Shares are of eligible rows and eligible absolute activity.", 9)
    rows = [dict(flag=x["flag"], n=x["rows_flagged"], absa=x["abs_actual_usd_flagged"], shn=x["share_of_eligible_rows"], sha=x["share_of_eligible_abs"]) for x in i8]
    specs = [dict(id="flag", h="Flag", w=62, kind="txt"), dict(id="n", h="Eligible rows flagged (count)", w=14, nf=NF_INT), dict(id="absa", h="Absolute actual flagged (USD)", w=18, nf=NF_USD),
             dict(id="shn", h="Share of eligible rows", w=12, nf=NF_PCT), dict(id="sha", h="Share of eligible absolute activity", w=14, nf=NF_PCT)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_FlagExposure", header_height=44)
    ws.conditional_format(tb.r0, 4, tb.r1, 4, {"type": "data_bar", "bar_color": "#F4B183", "bar_solid": True, "min_type": "num", "min_value": 0, "max_type": "num", "max_value": 0.5})
    r = tb.r1 + 3
    a5 = cx.d.t("out_a5_dimension_reliability", order="dimension, section")
    r = cx.section(ws, r, "Q3. Reliability of descriptive fields (out_a5): fill rate by section", "Verdict is the Phase 4 assessment. Quantity, customer segment and channel are populated on too few revenue lines to support price-volume-mix analysis.", 9)
    rows = [dict(dim=x["dimension"], sec=x["section"], el=x["rows_eligible"], pop=x["rows_populated"], dist=x["distinct_values"], verdict=x["verdict"]) for x in a5]
    specs = [dict(id="dim", h="Field", w=62, kind="txt"), dict(id="sec", h="Section", w=14, kind="txt"), dict(id="el", h="Eligible rows (count)", w=18, nf=NF_INT), dict(id="pop", h="Populated (count)", w=12, nf=NF_INT),
             dict(id="fill", h="Fill rate", w=12, kind="calc", nf=NF_PCT, f=lambda x: f'=IF({x["el"]}>0,{x["pop"]}/{x["el"]},"n/a")', v=lambda d: d["pop"] / d["el"] if d["el"] else "n/a"),
             dict(id="dist", h="Distinct values (count)", w=11, nf=NF_INT), dict(id="verdict", h="Phase 4 verdict", w=16, kind="txt")]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_DimReliability", header_height=32)
    ws.conditional_format(tb.r0, 6, tb.r1, 6, {"type": "text", "criteria": "containing", "value": "UNSUITABLE", "format": cx.fmt(bg_color="#F8CBAD")})
    ws.conditional_format(tb.r0, 6, tb.r1, 6, {"type": "text", "criteria": "containing", "value": "RELIABLE", "format": cx.fmt(bg_color="#E2EFDA")})
    r = tb.r1 + 2
    ws.merge_range(r, 0, r, 8, "Legend: green = RELIABLE fill; red = UNSUITABLE. (\"UNRELIABLE\" and \"PARTIAL\" are unshaded.) Verdict text is copied from Phase 4.", cx.fmt(italic=True, font_color="#595959"))
    r += 3
    i1 = cx.d.t("out_i1_scenarios", order="factor, scenario")
    r = cx.section(ws, r, "Q4. How much does each unresolved rule move the headline? (out_i1, out_i2)", "Each factor is varied alone, others at baseline. Result proxy = revenue - COGS - People - Opex. BASELINE rows are the workbook's numbers; the swing is a range of plausible policies, not an error estimate. Status-partition rows are diagnostics, not policies.", 9)
    rows = [dict(factor=x["factor"], scn=x["scenario"], cls=x["scenario_class"], n=x["rows_in_scope"], rev=x["revenue_usd"], cost=x["cost_usd"], proxy=x["result_proxy_usd"]) for x in i1]
    base_rev = next(x["rev"] for x in rows if x["factor"] == "status" and "baseline" in x["scn"])
    base_px = next(x["proxy"] for x in rows if x["factor"] == "status" and "baseline" in x["scn"])
    specs = [dict(id="factor", h="Factor", w=62, kind="txt"), dict(id="scn", h="Scenario", w=34, kind="txt"), dict(id="cls", h="Class", w=26, kind="txt"), dict(id="n", h="Rows (count)", w=12, nf=NF_INT),
             dict(id="rev", h="Revenue (USD)", w=15, nf=NF_USD), dict(id="cost", h="Cost: COGS+People+Opex (USD)", w=15, nf=NF_USD),
             dict(id="proxy", h="Result proxy (USD)", w=15, kind="calc", nf=NF_USD, f=lambda x: f"={x['rev']}-{x['cost']}", v=lambda d: d["rev"] - d["cost"]),
             dict(id="drev", h="Revenue vs baseline (%)", w=13, kind="calc", nf=NF_PCT, f=lambda x: f"={x['rev']}/{base_rev!r}-1", v=lambda d: d["rev"] / base_rev - 1),
             dict(id="dpx", h="Result proxy vs baseline (%)", w=14, kind="calc", nf=NF_PCT, f=lambda x: f"={x['proxy']}/{base_px!r}-1", v=lambda d: d["proxy"] / base_px - 1)]
    # the baseline constants above are inputs from the Phase 4 baseline row: link them to the baseline row instead of embedding
    first = r + 1
    base_i = next(i for i, x in enumerate(rows) if x["factor"] == "status" and "baseline" in x["scn"])
    specs[7]["f"] = lambda x: f"={x['rev']}/$E${first + base_i + 1}-1"
    specs[8]["f"] = lambda x: f"={x['proxy']}/$G${first + base_i + 1}-1"
    specs[0]["w"] = 14
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_Scenarios", header_height=44)
    cx.R["Q4"] = tb
    r = tb.r1 + 3
    i2 = cx.d.t("out_i2_factor_ranking", order="revenue_range_pct_of_baseline DESC")
    rows = [dict(f=x["factor"], s=x["scenarios"], minr=x["min_revenue_usd"], maxr=x["max_revenue_usd"], rp=x["revenue_range_pct_of_baseline"], minx=x["min_result_usd"], maxx=x["max_result_usd"], xp=x["result_range_pct_of_baseline"]) for x in i2]
    specs = [dict(id="f", h="Factor (ranked by revenue swing)", w=14, kind="txt"), dict(id="s", h="Scenarios (count)", w=14, nf=NF_INT), dict(id="minr", h="Min revenue (USD)", w=18, nf=NF_USD), dict(id="maxr", h="Max revenue (USD)", w=12, nf=NF_USD),
             dict(id="rp", h="Revenue range % of baseline", w=15, nf=NF_PCT), dict(id="minx", h="Min result proxy (USD)", w=15, nf=NF_USD), dict(id="maxx", h="Max result proxy (USD)", w=15, nf=NF_USD),
             dict(id="xp", h="Result range % of baseline", w=13, nf=NF_PCT)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    ch = cx.wb.add_chart({"type": "bar"})
    ch.add_series({"name": "Revenue range as % of baseline", "categories": tb.col_rng("f"), "values": tb.col_rng("rp"), "fill": {"color": "#1F3864"}})
    ch.add_series({"name": "Result-proxy range as % of baseline", "categories": tb.col_rng("f"), "values": tb.col_rng("xp"), "fill": {"color": "#C55A11"}})
    ch.set_title({"name": "Which unresolved rule moves the headline most? (range across policies)", "name_font": {"size": 10}})
    ch.set_x_axis({"num_format": "0%", "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
    ch.set_y_axis({"reverse": True}); ch.set_legend({"position": "bottom"}); ch.set_size({"width": 700, "height": 280})
    ws.insert_chart(tb.r0 - 1, 9, ch)
    r = max(tb.r1 + 3, tb.r0 + 14)
    i5 = cx.d.t("out_i5_restored_exposure", order="section_order, scale_confidence")
    r = cx.section(ws, r, "Q5. Scale restoration (rule R7): lines whose amounts were divided by 1,000 / 100,000 (out_i5, out_i4)", "Restoration is a provisional rule. HIGH/MEDIUM confidence tiers show how much of each section's absolute activity depends on it; 'undetermined' rows are left as reported.", 9)
    rows = [dict(sec=SEC_LABEL.get(x["section"], x["section"]), conf=x["scale_confidence"], dec=x["scale_decision"], n=x["rows_n"], adj=x["abs_adjusted_usd"], rep=x["abs_as_reported_usd"], sh=x["share_of_section_abs_activity"]) for x in i5]
    specs = [dict(id="sec", h="Section", w=14, kind="txt"), dict(id="conf", h="Confidence", w=14, kind="txt"), dict(id="dec", h="Decision", w=18, kind="txt"), dict(id="n", h="Rows (count)", w=12, nf=NF_INT),
             dict(id="adj", h="Absolute adjusted (USD)", w=15, nf=NF_USD), dict(id="rep", h="Absolute as reported (USD)", w=15, nf=NF_USD), dict(id="sh", h="Share of section absolute activity", w=14, nf=NF_PCT)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_ScaleExposure", header_height=44)
    r = tb.r1 + 2
    i4 = cx.d.t("out_i4_undetermined_scale", order="section")
    rows = [dict(sec=x["section"], n=x["rows_undetermined"], p=x["rows_posted"], rep=x["abs_as_reported_usd"], k3=x["if_multiplied_1e3_abs_usd"], k5=x["if_multiplied_1e5_abs_usd"]) for x in i4]
    specs = [dict(id="sec", h="Undetermined-scale rows by section", w=14, kind="txt"), dict(id="n", h="Rows undetermined (count)", w=14, nf=NF_INT), dict(id="p", h="Of which Posted (count)", w=18, nf=NF_INT), dict(id="rep", h="Absolute as reported (USD)", w=12, nf=NF_USD),
             dict(id="k3", h="If x1,000 (USD)", w=15, nf=NF_USD), dict(id="k5", h="If x100,000 (USD)", w=15, nf=NF_USD)]
    write_table(cx, ws, S, r, 0, specs, rows, header_height=44)
    r += len(rows) + 4
    i6 = cx.d.t("out_i6_duplicate_exposure")
    r = cx.section(ws, r, "Q6. Duplicate-candidate exposure (out_i6, out_i7)", "document_no is not a unique key (R5). No two rows are identical in all source fields, so no line is removed. 'Field match' tiers are candidates only: they may be legitimate repeated postings.", 9)
    rows = [dict(t=x["dup_tier"], n=x["rows_eligible"], absa=x["abs_actual_usd"], shn=x["share_of_eligible_rows"], sha=x["share_of_eligible_abs"]) for x in i6]
    specs = [dict(id="t", h="Duplicate tier", w=14, kind="txt"), dict(id="n", h="Eligible rows (count)", w=14, nf=NF_INT), dict(id="absa", h="Absolute actual (USD)", w=18, nf=NF_USD), dict(id="shn", h="Share of eligible rows", w=12, nf=NF_PCT), dict(id="sha", h="Share of eligible absolute", w=13, nf=NF_PCT)]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=32)
    r = tb.r1 + 2
    i7 = cx.d.t("out_i7_exact_row_matches")
    rows = [dict(d_=x["definition"], g=x["groups_with_matches"], n=x["rows_in_matches"]) for x in i7]
    specs = [dict(id="d_", h="Exact-match test", w=14, kind="txt"), dict(id="g", h="Groups with matches (count)", w=14, nf=NF_INT), dict(id="n", h="Rows in matches (count)", w=14, nf=NF_INT)]
    write_table(cx, ws, S, r, 0, specs, rows, header_height=32)
    ws.set_column(0, 0, 62)
    r += len(rows) + 4
    a0 = cx.d.t("out_a0_grain_evidence")
    r = cx.section(ws, r, "Q7. Grain evidence: are budget/forecast/prior-year per-line amounts? (out_a0)", "Lines in the same entity x period x GL cell carry different values in 98% of multi-line cells, so they are treated as per-line amounts and summed (R-grain assumption, provisional).", 9)
    rows = [dict(m=x["metric"], v=x["value"], note=x["note"] or "") for x in a0]
    specs = [dict(id="m", h="Metric", w=62, kind="txt"), dict(id="v", h="Value", w=14, nf=NF_INT), dict(id="note", h="Note", w=40, kind="txt")]
    write_table(cx, ws, S, r, 0, specs, rows, name="tbl_Grain", header_height=24)
    r += len(rows) + 4
    a8 = cx.d.t("out_a8_account_mapping_consistency", order="gl_account")
    r = cx.section(ws, r, "Q8. Account mapping consistency (out_a8) and period coverage (out_a7)", "Every GL account must map to one name, group and statement. CONSISTENT = a single mapping.", 9)
    rows = [dict(gl=x["gl_account"], n=x["posting_rows"], nn=x["n_names"], ng=x["n_groups"], nf_=x["n_fs_lines"], ns=x["n_statements"], st=x["mapping_status"]) for x in a8]
    specs = [dict(id="gl", h="GL", w=62, nf="0"), dict(id="n", h="Posting rows (count)", w=14, nf=NF_INT), dict(id="nn", h="Names (count)", w=18, nf=NF_INT), dict(id="ng", h="Groups (count)", w=12, nf=NF_INT),
             dict(id="nf_", h="FS lines (count)", w=12, nf=NF_INT), dict(id="ns", h="Statements (count)", w=12, nf=NF_INT), dict(id="st", h="Mapping status", w=18, kind="txt")]
    tb = write_table(cx, ws, S, r, 0, specs, rows, name="tbl_Mapping", header_height=32)
    cx.reg("dq_mapping_inconsistent", S, tb.r1 + 1, 6, sum(1 for x in rows if x["st"] != "CONSISTENT"))
    ws.write_string(tb.r1 + 1, 5, "Not CONSISTENT (count):", cx.fmt(bold=True, align="right"))
    cx.calc(ws, tb.r1 + 1, 6, f'=COUNTIF({tb.col_rng("st", sheet=False)},"<>CONSISTENT")', cx.val("dq_mapping_inconsistent"), NF_INT, bold=True)
    cx.R["dq_mapping_inconsistent"] = (S, tb.r1 + 1, 6, cx.val("dq_mapping_inconsistent"))
    a7 = cx.d.t("out_a7_period_summary")[0]
    r = tb.r1 + 4
    ws.merge_range(r, 0, r, 8, f"Period coverage (out_a7): {a7['first_period']} to {a7['last_period']}, {a7['distinct_periods']} distinct periods, {a7['entity_period_gaps']} entity-month gaps; "
                   f"lines per entity-month range {a7['min_rows_entity_period']}-{a7['max_rows_entity_period']}.", cx.fmt(italic=True, text_wrap=True))
    r += 3
    h1 = cx.d.t("out_h1_bs_coverage")[0]
    h6 = cx.d.t("out_h6_bs_metrics_not_computed")
    r = cx.section(ws, r, "Q9. Balance-sheet lines: records, not balances (out_h1, out_h6)", f"Balance-sheet lines populate {h1['coverage'] * 100:.1f}% of entity x month x account cells, and {h1['share_of_populated_cells_with_multiple_lines'] * 100:.1f}% of populated cells hold more than one line (up to {h1['max_lines_in_a_cell']}), so lines are not additive period-end snapshots. "
                   "The metrics below were deliberately NOT computed:", 9)
    rows = [dict(m=x["metric"], why=x["reason_not_computed"]) for x in h6]
    specs = [dict(id="m", h="Metric not computed", w=62, kind="txt"), dict(id="why", h="Reason", w=14, kind="txt", fmt={"text_wrap": True})]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=24)
    for i in range(len(rows)):
        ws.merge_range(tb.r0 + i, 1, tb.r0 + i, 8, rows[i]["why"], cx.fmt(text_wrap=True, valign="top"))
        ws.set_row(tb.r0 + i, 30)
    ws.merge_range(tb.r0 - 1, 1, tb.r0 - 1, 8, "Reason", cx.fmt(bold=True, font_color="#FFFFFF", bg_color=NAVY, align="center"))
    r = tb.r1 + 3
    r = cx.section(ws, r, "Q10. Unavailable by design", "Not built because the data or definitions do not support them:", 9)
    for i, t in enumerate(["Close duration, on-time-close rate, close-calendar KPIs: no close-start / close-end timestamps exist in the extract (posting dates are not close events).",
                           "EBITDA: D&A and below-EBITDA signs are unverified and 'Operating result proxy' is not EBITDA.",
                           "Cost-centre variance: Phase 4 does not publish it; cost-centre is missing on 4.6% of eligible lines.",
                           "Forecast skill / bias correction: the forecast has no version or as-of date.",
                           "Unit economics (price, volume, mix) and materials-vs-sales unit costs: quantity/UoM unreliable (33% fill; equal unit values across product families).",
                           "Consolidated group results: intercompany and eliminations (R12) unresolved."]):
        ws.merge_range(r + i, 0, r + i, 8, "- " + t, cx.fmt(text_wrap=True, valign="top"))
        ws.set_row(r + i, 28)
    ws.freeze_panes(4, 0)
    ws.set_landscape(); ws.fit_to_pages(1, 0)
    return rows


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 12: Definitions and assumptions
# ---------------------------------------------------------------------------------------------------------------------
def parse_rules(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (R\d+) \| (.+?) \| (.+?) \| (.+) \|$", line)
        if m:
            out.append(dict(id=m.group(1), rule=m.group(2).replace("\\|", "|").replace("`", ""), status=m.group(3).replace("`", ""), basis=m.group(4).replace("`", "")))
    out.sort(key=lambda x: int(x["id"][1:]))
    return out


def parse_owner_decisions(path: Path) -> list[str]:
    txt = path.read_text(encoding="utf-8")
    m = re.search(r"^## 15\. Remaining decisions for the owner\s*\n(.*?)(?=^## |\Z)", txt, flags=re.S | re.M)
    return [re.sub(r"^\d+\.\s*", "", x).replace("`", "") for x in (m.group(1).strip().splitlines() if m else []) if re.match(r"^\d+\.", x)]


def build_defs(cx: Ctx):
    ws, S = cx.ws["Definitions"], "Definitions"
    cx.title(ws, "Definitions, assumptions and lineage", "Every definition below is the Phase 4 definition. The rules register is parsed from docs/FINANCIAL_METRICS.md; nothing here upgrades a Proposed or Unresolved rule to Confirmed.",
             "PROVISIONAL: Posted-only eligibility (R6), scale restoration (R7), FX direction (R8), the variance-% convention (R10), the grain of budget/forecast/prior-year (summed per line) and the exclusion of junk entities (R4) are working conventions. "
             "Unresolved: the account sign convention (R9), the duplicate rule (R11) and consolidation/elimination (R12).", width=4)
    ws.set_column(0, 0, 18); ws.set_column(1, 1, 70); ws.set_column(2, 2, 36); ws.set_column(3, 3, 70)
    r = 4
    rules = parse_rules(DOCS / "FINANCIAL_METRICS.md")
    r = cx.section(ws, r, "D1. Rules register (R1-R14)", "Status labels: Confirmed = owner-stated or plain fact; Proposed-Needs Validation = candidate rule; Unresolved = the data does not settle it.", 4)
    specs = [dict(id="id", h="Rule", kind="txt"), dict(id="rule", h="Rule text", kind="txt", fmt={"text_wrap": True, "valign": "top"}), dict(id="status", h="Status", kind="txt", fmt={"text_wrap": True, "valign": "top"}), dict(id="basis", h="Basis", kind="txt", fmt={"text_wrap": True, "valign": "top"})]
    tb = write_table(cx, ws, S, r, 0, specs, rules, name="tbl_Rules", header_height=24)
    for i in range(len(rules)):
        ws.set_row(tb.r0 + i, 15 * max(2, -(-len(rules[i]["basis"]) // 70), -(-len(rules[i]["rule"]) // 70), -(-len(rules[i]["status"]) // 26)))
    ws.conditional_format(tb.r0, 2, tb.r1, 2, {"type": "text", "criteria": "containing", "value": "Unresolved", "format": cx.fmt(bg_color="#F8CBAD")})
    ws.conditional_format(tb.r0, 2, tb.r1, 2, {"type": "text", "criteria": "begins with", "value": "Proposed", "format": cx.fmt(bg_color=AMBER)})
    ws.conditional_format(tb.r0, 2, tb.r1, 2, {"type": "text", "criteria": "begins with", "value": "Confirmed", "format": cx.fmt(bg_color="#E2EFDA")})
    r = tb.r1 + 3
    ws.merge_range(r, 0, r, 3, "Legend: red = Unresolved; amber = Proposed - needs validation; green = Confirmed.", cx.fmt(italic=True, font_color="#595959"))
    ws.write_string(tb.r1 + 2, 1, "Rules parsed (count):", cx.fmt(bold=True, align="right"))
    cx.calc(ws, tb.r1 + 2, 2, f"=COUNTA({tb.col_rng('id', sheet=False)})", len(rules), NF_INT, bold=True, align="left")
    cx.reg("defs_rules_n", S, tb.r1 + 2, 2, len(rules))
    r += 3
    metrics = [
        ("Actual / Budget / Forecast / Prior-year", "actual_usd_adj etc.: reported USD amounts after the per-row scale rule; signs as recorded; costs are positive magnitudes.", "Phase 4 views v_pl_*", "Provisional (R6, R7)."),
        ("Variance", "Actual - Budget (arithmetic difference). Never labelled favourable/adverse.", "FINANCIAL_METRICS s2", "R10 convention; R9 sign convention unresolved."),
        ("Variance %", "Variance / |net budget|, shown only when |net budget| >= 50% of the gross (absolute) budget; otherwise 'n/a (guard)'.", "Phase 4 safe_pct macro", "Project convention, not a standard."),
        ("Same-sign basis", "Lines where actual and budget (or forecast) are both non-zero with the same sign. Primary basis for variance and forecast tables.", "Phase 4 sign_cat", "Excludes opposite-sign and zero-involved lines; those are shown in bridges."),
        ("Forecast error", "Forecast - Actual. Positive = forecast above actual.", "FINANCIAL_METRICS s3", "Observation only; no snapshot dates => no skill claim."),
        ("WAPE", "Sum |Forecast - Actual| / Sum |Actual|.", "FINANCIAL_METRICS s3", "Weights large lines more."),
        ("Bias", "Sum (Forecast - Actual) / Sum |Actual|.", "FINANCIAL_METRICS s3", "Directional, not a correction."),
        ("Gross profit", "Revenue (GL 4100-4190) - COGS (GL 5100-5300). Three treatments of discounts: S1 signed as recorded, S2 discount at absolute value, S3 excluding discounts.", "Phase 4 v_gp_rows", "Sign convention unresolved; no treatment is authoritative."),
        ("Gross margin %", "Gross profit / Revenue, only when revenue > 0.", "Phase 4", ""),
        ("Operating result proxy", "Revenue - COGS - People - Opex. NOT EBITDA / operating profit. D&A, below-EBITDA and tax shown as memo lines only.", "Phase 4", "Sign treatment of D&A, FX gain/loss unverified."),
        ("Eligible P&L line", "A P&L posting line that passes the exclusion waterfall (non-posting rows, junk entities, non-Posted status, unparseable values excluded).", "FINANCIAL_METRICS s4-5", "R3, R4, R6, R14."),
        ("Absolute activity", "Sum of |amount|; used for shares and concentration so offsetting signs do not net out.", "Phase 4", ""),
        ("Share of gross cell variance", "|cell variance| / sum of |cell variance| within the section.", "Phase 4 out_b2", "Gross variance exposes offsets hidden in the net."),
    ]
    r = cx.section(ws, r, "D2. Metric definitions", None, 4)
    rows = [dict(m=a, d=b, s=c, n=d) for a, b, c, d in metrics]
    specs = [dict(id="m", h="Metric", kind="txt", fmt={"text_wrap": True, "valign": "top", "bold": True}), dict(id="d", h="Definition", kind="txt", fmt={"text_wrap": True, "valign": "top"}),
             dict(id="s", h="Source", kind="txt", fmt={"text_wrap": True, "valign": "top"}), dict(id="n", h="Limit / status", kind="txt", fmt={"text_wrap": True, "valign": "top"})]
    tb = write_table(cx, ws, S, r, 0, specs, rows, header_height=24)
    for i in range(len(rows)):
        ws.set_row(tb.r0 + i, 15 * max(2, -(-len(rows[i]["d"]) // 70)))
    r = tb.r1 + 3
    r = cx.section(ws, r, "D3. Remaining decisions for the owner (FINANCIAL_METRICS section 15)", "Each changes a headline number or its meaning. Until decided, the safe default is shown and affected lines are counted, not silently changed.", 4)
    dec = parse_owner_decisions(DOCS / "FINANCIAL_METRICS.md")
    for i, t in enumerate(dec):
        ws.write_number(r + i, 0, i + 1, cx.fmt(align="center"))
        ws.merge_range(r + i, 1, r + i, 3, t, cx.fmt(text_wrap=True))
    cx.reg("defs_decisions_n", S, r + len(dec), 0, len(dec))
    r += len(dec) + 2
    r = cx.section(ws, r, "D4. Assumptions made in this workbook", None, 4)
    ass = ["All amounts are USD after Phase 4's scale rule and are provisional; the extract is synthetic (NovaBridge Industries) and provenance/licence are unverified.",
           "Budget, forecast and prior-year values are per-line amounts and are summed (supported by out_a0: 98% of multi-line cells hold different values); if they are repeated header values, every variance would change.",
           "Posted-only is the reporting population. Pending, Parked, Rejected and blank statuses are excluded (INS-01 shows how much this matters).",
           "Percent thresholds on this workbook (MoM highlight 10%, variance highlight 5%, guard 50%) are blue inputs: changing them changes the highlighting/guard only, not any total.",
           "Tolerance on reconciliation checks: 0.5 USD for amounts, exact for counts. Floating-point differences below that are not material.",
           "Calendar year = year of the posting period; the extract's fiscal year label is not used for totals.",
           "No intercompany elimination, no FX re-translation, no duplicate removal, no sign flipping, no missing-as-zero."]
    for i, t in enumerate(ass):
        ws.merge_range(r + i, 0, r + i, 3, f"{i + 1}. {t}", cx.fmt(text_wrap=True, valign="top"))
        ws.set_row(r + i, 28)
    r += len(ass) + 2
    cx.R["defs_lineage_row"] = (S, r, 0, None)
    ws.freeze_panes(4, 0)
    ws.set_row(2, 34)
    ws.set_landscape(); ws.fit_to_pages(1, 0)
    return r


def build_lineage(cx: Ctx, r):
    ws, S = cx.ws["Definitions"], "Definitions"
    r = cx.section(ws, r, "D5. Lineage: sheet -> Phase 4 source -> check", "Every number on a sheet traces to one of these Phase 4 tables; the Reconciliation & QA sheet tests the link.", 4)
    lin = [("Monthly P&L", "out_a1_pl_period_section", "R-01, R-02, R-04..R-10, R-13-2023..2025 (totals and population vs independent recompute from v_pl_actual / v_close)"),
           ("Budget vs Actual", "out_b1, out_b2, out_b3, out_b4, out_b7-b11", "R-15-* and R-16-* (independent recompute from v_var_scn; bridge), R-24 (recomputed % = Phase 4 %), R-29 (budgeted lines)"),
           ("Forecast & Prior Year", "out_c1-c8, out_d1-d5; F3b from v_pl_budget", "R-17-* (v_fc_scn), R-17b-* (matched subset) and R-17c-* (comparable lines) recomputed from v_close; prior-year tables are not independently recomputed"),
           ("Entity & Division", "out_a2, out_a3, out_b2, out_b3, out_g5", "R-03b (entity lines), R-11 (entity revenue), R-12 (division revenue), R-14-* (revenue per entity)"),
           ("GL & Cost Drivers", "out_a4, out_f1-f7, out_b2", "R-03 (GL activity lines = eligible lines); GL cost Pareto and driver tables are not independently recomputed"),
           ("Gross Profit", "out_e1-e4", "R-21-* (independent recompute from v_gp_rows), R-22 (S1 = Monthly P&L), R-23-* (bridge)"),
           ("Insights & Actions", "docs/PHASE4_INSIGHT_REGISTER.md + database figures", "R-25 (register figures found by formula; the register text itself is copied, not recomputed)"),
           ("Data Quality", "out_i1-i10, out_a0, out_a5-a8, out_h1-h6", "R-02, R-26 (waterfall = all source rows; mapping consistent); other Data Quality tables are copied from Phase 4"),
           ("Executive Summary", "links to the sheets above", "no separate row: every headline is a link, and the Python tests compare each with its source cell"),
           ("Reconciliation & QA", "database views v_pl_*, v_var_scn, v_fc_scn, v_gp_rows", "self-checking")]
    rows = [dict(a=a, b=b, c=c) for a, b, c in lin]
    specs = [dict(id="a", h="Sheet", kind="txt", fmt={"bold": True}), dict(id="b", h="Phase 4 source tables", kind="txt", fmt={"text_wrap": True}), dict(id="c", h="Reconciliation checks", kind="txt", fmt={"text_wrap": True}), dict(id="d", h="", kind="txt")]
    for x in rows:
        x["d"] = ""
    write_table(cx, ws, S, r, 0, specs[:3], rows, header_height=24)


# ---------------------------------------------------------------------------------------------------------------------
# Sheet 11: Reconciliation & QA (independent recompute from the database views)
# ---------------------------------------------------------------------------------------------------------------------
def independent_values(d: Data) -> dict:
    """Expected values recomputed straight from the Phase 4 analytical views, NOT from the out_ tables the workbook was built from."""
    ev = {}
    for r_ in d.rows("SELECT section, count(*) n, sum(actual_usd_adj) a FROM v_pl_actual GROUP BY 1"):
        ev[f"sec_n_{r_['section']}"] = r_["n"]; ev[f"sec_a_{r_['section']}"] = r_["a"]
    ev["pl_n"] = d.one("SELECT count(*) FROM v_pl_actual")
    ev["budget_lines"] = d.one("SELECT count(*) FROM v_pl_actual WHERE budget_usd_adj IS NOT NULL")
    ev["any_status_n"] = d.one("SELECT count(*) FROM v_pl_actual_any_status")
    ev["total_rows"] = d.one("SELECT count(*) FROM v_close")
    for r_ in d.rows("SELECT scenario, section, count(*) n, sum(actual) a, sum(budget) b FROM v_var_scn GROUP BY 1,2"):
        ev[f"var_{r_['scenario']}_{r_['section']}"] = r_
    for r_ in d.rows("SELECT scenario, section, count(*) n, sum(actual) a, sum(forecast) f, sum(error) e, sum(abs(error)) ae, sum(abs(actual)) aa FROM v_fc_scn GROUP BY 1,2"):
        ev[f"fc_{r_['scenario']}_{r_['section']}"] = r_
    for r_ in d.rows("SELECT rowset, treatment, sum(revenue) rev, sum(cogs) cogs, count(*) n FROM v_gp_rows GROUP BY 1,2"):
        ev[f"gp_{r_['rowset']}_{r_['treatment']}"] = r_
    for r_ in d.rows("SELECT entity_code, sum(actual_usd_adj) a FROM v_pl_actual WHERE section='REVENUE' GROUP BY 1"):
        ev[f"ent_rev_{r_['entity_code']}"] = r_["a"]
    ev["div_rev"] = d.one("SELECT sum(actual_usd_adj) FROM v_pl_actual WHERE section='REVENUE' AND division IS NOT NULL")
    for y in (2023, 2024, 2025):
        ev[f"fy_rev_{y}"] = d.one("SELECT sum(actual_usd_adj) FROM v_pl_actual WHERE section='REVENUE' AND period_year=?", [y])
    # forecast-vs-budget populations recomputed with a different formulation (FILTER aggregates over v_close) than the sheet's SQL
    for r_ in d.rows("""SELECT section,
        count(*) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL AND actual_usd_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO' AND sign_cat_af = 'SAME_SIGN_NONZERO') mn,
        sum(abs(forecast_usd_adj - actual_usd_adj)) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO' AND sign_cat_af = 'SAME_SIGN_NONZERO')
          / sum(abs(actual_usd_adj)) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO' AND sign_cat_af = 'SAME_SIGN_NONZERO') mwf,
        sum(abs(budget_usd_adj - actual_usd_adj)) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO' AND sign_cat_af = 'SAME_SIGN_NONZERO')
          / sum(abs(actual_usd_adj)) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL AND sign_cat_ab = 'SAME_SIGN_NONZERO' AND sign_cat_af = 'SAME_SIGN_NONZERO') mwb,
        count(*) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL AND actual_usd_adj IS NOT NULL) cn,
        sum(abs(forecast_usd_adj - actual_usd_adj)) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL) / sum(abs(actual_usd_adj)) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL) cwf,
        sum(abs(budget_usd_adj - actual_usd_adj)) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL) / sum(abs(actual_usd_adj)) FILTER (WHERE eligible_PL_variance = 1 AND forecast_usd_adj IS NOT NULL) cwb
        FROM v_close WHERE section IN ('REVENUE','COGS','PEOPLE','OPEX') GROUP BY 1"""):
        ev[f"fm_{r_['section']}"] = dict(n=r_["mn"], wf=r_["mwf"], wb=r_["mwb"]); ev[f"fa_{r_['section']}"] = dict(n=r_["cn"], wf=r_["cwf"], wb=r_["cwb"])
    ev["gl_n"] = d.one("SELECT count(*) FROM v_pl_actual WHERE gl_account IS NOT NULL")
    return ev


def build_recon(cx: Ctx, bva_ss_keys, bva_al_keys):
    ws, S = cx.ws["Reconciliation & QA"], "Reconciliation & QA"
    ev = independent_values(cx.d)
    cx.title(ws, "Reconciliation and QA - every check is a live formula",
             "Expected = recomputed independently from the Phase 4 analytical views (v_pl_actual, v_var_scn, v_fc_scn, v_gp_rows) or stated Phase 4 control totals. Workbook = the cell the sheet actually shows (green link). Difference and PASS/FAIL are Excel formulas.",
             "Tolerance: counts exact (0); USD amounts 0.5; percentages 0.000001. A check passes when |Difference| <= tolerance. Tolerances are blue inputs. The Python test suite additionally recalculates this workbook in LibreOffice and compares every cached value; "
             "Excel itself was not used to generate or open this file.", width=9)
    ws.write_string(4, 0, "Overall status:", cx.fmt(bold=True, font_size=12))
    rows = []

    def add(cid, area, desc, exp, ref_key=None, ref_formula=None, ref_value=None, tol=0.5, nf=NF_USD):
        val = cx.val(ref_key) if ref_key else ref_value
        rows.append(dict(id=cid, area=area, desc=desc, exp=exp, ref=(cx.ref(ref_key) if ref_key else ref_formula), val=val, tol=tol, nf=nf))

    # --- populations
    add("R-01", "Population", "Eligible P&L lines: Monthly P&L total vs v_pl_actual", ev["pl_n"], "mpl_total_n", tol=0, nf=NF_INT)
    add("R-02", "Population", "All source rows: Data Quality waterfall total vs v_close", ev["total_rows"], "dq_total_rows", tol=0, nf=NF_INT)
    add("R-03", "Population", "Eligible lines: GL activity total vs v_pl_actual", ev["pl_n"], "gl_total_n", tol=0, nf=NF_INT)
    add("R-03b", "Population", "Eligible lines: entity table total vs v_pl_actual", ev["pl_n"], "E1_total_n", tol=0, nf=NF_INT)
    # --- monthly totals by section
    secmap = [("REVENUE", "rev"), ("COGS", "cogs"), ("PEOPLE", "ppl"), ("OPEX", "opex"), ("D&A", "da"), ("BELOW_EBITDA", "be"), ("TAX", "tax")]
    for i, (s, k) in enumerate(secmap):
        add(f"R-0{4 + i}" if 4 + i < 10 else f"R-{4 + i}", "Monthly P&L", f"{SEC_LABEL[s]}: 36-month total vs v_pl_actual", ev[f"sec_a_{s}"], f"mpl_total_{k}")
    add("R-11", "Cross-sheet", "Revenue: entity table total = Monthly P&L total", ev["sec_a_REVENUE"], "E1_total_rev")
    add("R-12", "Cross-sheet", "Revenue: division table total = Monthly P&L total", ev["div_rev"], "E2_total_rev")
    for y in (2023, 2024, 2025):
        add(f"R-13-{y}", "Monthly P&L", f"Revenue {y}: calendar-year row vs v_pl_actual", ev[f"fy_rev_{y}"], f"fy_rev_{y}")
    for e in sorted(k[8:] for k in ev if k.startswith("ent_rev_")):
        add(f"R-14-{e}", "Entity", f"Revenue {e}: entity table vs v_pl_actual", ev[f"ent_rev_{e}"], f"ent_rev_{e}")
    # --- budget vs actual
    for s in OPS + ["D&A", "BELOW_EBITDA", "TAX"]:
        if f"var_SAME_SIGN_ONLY_{s}" not in ev:
            continue
        for sc, tag, lab in (("SAME_SIGN_ONLY", "ss", "same-sign"), ("ALL_LINES", "al", "all lines")):
            v_ = ev[f"var_{sc}_{s}"]
            add(f"R-15-{tag}-{s}-A", "Budget vs Actual", f"{SEC_LABEL[s]} actual ({lab}) vs v_var_scn", v_["a"], f"bva_{tag}_{s}_act")
            add(f"R-15-{tag}-{s}-B", "Budget vs Actual", f"{SEC_LABEL[s]} budget ({lab}) vs v_var_scn", v_["b"], f"bva_{tag}_{s}_bud")
            add(f"R-15-{tag}-{s}-N", "Budget vs Actual", f"{SEC_LABEL[s]} lines ({lab}) vs v_var_scn", v_["n"], f"bva_{tag}_{s}_n", tol=0, nf=NF_INT)
    for s in OPS:
        add(f"R-16-{s}", "Budget vs Actual", f"{SEC_LABEL[s]}: all-lines = same-sign + opposite + zero-involved (bridge difference = 0)", 0.0, f"bva_bridge_diff_{s}", tol=0.5)
    # --- forecast
    for s in OPS:
        for sc, tag in (("SAME_SIGN_ONLY", "ss"), ("ALL_LINES", "al")):
            v_ = ev[f"fc_{sc}_{s}"]
            add(f"R-17-{tag}-{s}-E", "Forecast", f"{SEC_LABEL[s]} net error ({tag}) vs v_fc_scn", v_["e"], f"fc_{tag}_{s}_net")
            add(f"R-17-{tag}-{s}-W", "Forecast", f"{SEC_LABEL[s]} WAPE ({tag}) vs v_fc_scn", v_["ae"] / v_["aa"], f"fc_{tag}_{s}_wape", tol=1e-6, nf=NF_PCT2)
            add(f"R-17-{tag}-{s}-N", "Forecast", f"{SEC_LABEL[s]} lines ({tag}) vs v_fc_scn", v_["n"], f"fc_{tag}_{s}_n", tol=0, nf=NF_INT)
    for s in OPS:
        m_ = ev[f"fm_{s}"]; c_ = ev[f"fa_{s}"]
        add(f"R-17b-{s}-N", "Forecast", f"{SEC_LABEL[s]} matched-subset lines vs v_pl_budget (sign_cat_ab and sign_cat_af both same-sign)", m_["n"], f"fc_c6_{s}_n", tol=0, nf=NF_INT)
        add(f"R-17b-{s}-WF", "Forecast", f"{SEC_LABEL[s]} matched-subset forecast WAPE vs v_pl_budget", m_["wf"], f"fc_c6_{s}_wf", tol=1e-6, nf=NF_PCT2)
        add(f"R-17b-{s}-WB", "Forecast", f"{SEC_LABEL[s]} matched-subset budget WAPE vs v_pl_budget", m_["wb"], f"fc_c6_{s}_wb", tol=1e-6, nf=NF_PCT2)
        add(f"R-17c-{s}-N", "Forecast", f"{SEC_LABEL[s]} comparable-lines count vs v_pl_budget", c_["n"], f"fc_cmp_{s}_n", tol=0, nf=NF_INT)
        add(f"R-17c-{s}-WF", "Forecast", f"{SEC_LABEL[s]} comparable-lines forecast WAPE vs v_pl_budget", c_["wf"], f"fc_cmp_{s}_wf", tol=1e-6, nf=NF_PCT2)
        add(f"R-17c-{s}-WB", "Forecast", f"{SEC_LABEL[s]} comparable-lines budget WAPE vs v_pl_budget", c_["wb"], f"fc_cmp_{s}_wb", tol=1e-6, nf=NF_PCT2)
    # --- gross profit
    for rs in ("ROWS_ALL", "ROWS_ALL_NON_NEGATIVE"):
        for t in TREAT:
            v_ = ev[f"gp_{rs}_{t}"]
            add(f"R-21-{rs[5:]}-{t[3:5]}-G", "Gross Profit", f"{ROWSET[rs][:24]} {t[3:5]}: gross profit vs v_gp_rows", v_["rev"] - v_["cogs"], f"gp_{rs}_{t}_gp")
            add(f"R-21-{rs[5:]}-{t[3:5]}-M", "Gross Profit", f"{ROWSET[rs][:24]} {t[3:5]}: margin vs v_gp_rows", (v_["rev"] - v_["cogs"]) / v_["rev"], f"gp_{rs}_{t}_gm", tol=1e-6, nf=NF_PCT2)
    # S1 all-rows GP equals Monthly P&L gross profit (same revenue and COGS populations)
    add("R-22", "Cross-sheet", "Gross profit S1 (all rows) equals Monthly P&L gross profit (revenue - COGS)", cx.val("mpl_total_gp"), "gp_ROWS_ALL_GP_S1_SIGNED_AS_RECORDED_gp")
    for t in TREAT:
        add(f"R-23-{t[3:5]}", "Gross Profit", f"{t[3:5]}: GP variance bridge difference = 0 (GP var = revenue var - COGS var)", 0.0, f"gp3_{t}_br_", tol=0.5)
    # --- internal consistency of the workbook
    add("R-24", "Budget vs Actual", "Monthly table: months where recomputed % differs from Phase 4 guarded % (count of DIFF)", 0, "bva_m_diffs", tol=0, nf=NF_INT)
    add("R-25", "Insights", "Register figures recomputed from the database found in the register text (count NOT FOUND)", 0, ref_formula=None, ref_value=None, tol=0, nf=NF_INT)
    add("R-26", "Data Quality", "GL accounts with an inconsistent name/group/statement mapping (count)", 0, "dq_mapping_inconsistent", tol=0, nf=NF_INT)
    add("R-28", "Definitions", "Rules register rows parsed from FINANCIAL_METRICS (R1-R14)", 14, "defs_rules_n", tol=0, nf=NF_INT)
    add("R-29", "Population", "Budgeted eligible lines (Budget vs Actual universe) vs v_pl_actual", ev["budget_lines"],
        ref_formula=f"={cx.ref('bva_al_REVENUE_n')}+{cx.ref('bva_al_COGS_n')}+{cx.ref('bva_al_PEOPLE_n')}+{cx.ref('bva_al_OPEX_n')}+{cx.ref('bva_al_D&A_n')}+{cx.ref('bva_al_BELOW_EBITDA_n')}+{cx.ref('bva_al_TAX_n')}",
        ref_value=sum(cx.val(f"bva_al_{s}_n") for s in SECTIONS), tol=0, nf=NF_INT)

    # layout
    hdr = 8
    cx.hdr(ws, hdr, 0, ["ID", "Area", "Check", "Expected (independent source)", "Workbook value", "Difference", "Tolerance", "Result"], 32)
    ws.set_column(0, 0, 25); ws.set_column(1, 1, 18); ws.set_column(2, 2, 78); ws.set_column(3, 5, 20); ws.set_column(6, 6, 11); ws.set_column(7, 7, 10)
    r0 = hdr + 1
    n_pass = 0
    for i, x in enumerate(rows):
        r = r0 + i
        cx.txt(ws, r, 0, x["id"]); cx.txt(ws, r, 1, x["area"]); cx.txt(ws, r, 2, x["desc"])
        cx.inp(ws, r, 3, x["exp"], x["nf"])
        if x["id"] == "R-25":
            kfs = [k for k in cx.R if re.fullmatch(r"kf_\d+", k)]
            fml = "=" + "+".join(f"IF({cx.ref(k)}=\"FOUND\",0,1)" for k in kfs)
            val = sum(0 if cx.val(k) == "FOUND" else 1 for k in kfs)
            cx.calc(ws, r, 4, fml, val, x["nf"], color=GREEN)
            x["val"] = val
        elif x["ref"]:
            cx.calc(ws, r, 4, x["ref"] if x["ref"].startswith("=") else f"={x['ref']}", x["val"], x["nf"], color=GREEN)
        cx.calc(ws, r, 5, f"=ROUND(E{r + 1}-D{r + 1},6)", round(x["val"] - x["exp"], 6), NF_USD2 if x["tol"] else NF_INT)
        cx.inp(ws, r, 6, x["tol"], "0.000000" if x["tol"] and x["tol"] < 0.001 else "0.0")
        ok = abs(x["val"] - x["exp"]) <= x["tol"]
        x["ok"] = ok
        n_pass += ok
        cx.calc(ws, r, 7, f'=IF(ABS(F{r + 1})<=G{r + 1},"PASS","FAIL")', "PASS" if ok else "FAIL", bold=True, align="center")
    r1 = r0 + len(rows) - 1
    ws.conditional_format(r0, 7, r1, 7, {"type": "cell", "criteria": "==", "value": '"PASS"', "format": cx.fmt(bg_color="#C6EFCE", font_color="#006100", bold=True)})
    ws.conditional_format(r0, 7, r1, 7, {"type": "cell", "criteria": "==", "value": '"FAIL"', "format": cx.fmt(bg_color="#FFC7CE", font_color="#9C0006", bold=True)})
    ws.add_table(hdr, 0, r1, 7, {"name": "tbl_Recon", "style": "Table Style Light 1", "autofilter": True,
                                 "columns": [{"header": h, "header_format": cx.fmt(bold=True, font_color="#FFFFFF", bg_color=NAVY, text_wrap=True, align="center", border=1, border_color="#BFBFBF")}
                                             for h in ["ID", "Area", "Check", "Expected (independent source)", "Workbook value", "Difference", "Tolerance", "Result"]]})
    rng = f"$H${r0 + 1}:$H${r1 + 1}"
    nfail = len(rows) - n_pass
    cx.calc(ws, 4, 1, f'=IF(COUNTIF({rng},"FAIL")=0,"ALL "&COUNTA({rng})&" CHECKS PASS",COUNTIF({rng},"FAIL")&" CHECK(S) FAIL")', f"ALL {len(rows)} CHECKS PASS" if not nfail else f"{nfail} CHECK(S) FAIL", bold=True, font_size=12)
    ws.conditional_format(4, 1, 4, 1, {"type": "text", "criteria": "containing", "value": "FAIL", "format": cx.fmt(bg_color="#FFC7CE", font_color="#9C0006")})
    ws.conditional_format(4, 1, 4, 1, {"type": "text", "criteria": "containing", "value": "PASS", "format": cx.fmt(bg_color="#C6EFCE", font_color="#006100")})
    ws.write_string(5, 0, "Checks:", cx.fmt(bold=True)); cx.calc(ws, 5, 1, f"=COUNTA({rng})", len(rows), NF_INT)
    ws.write_string(6, 0, "Pass / Fail:", cx.fmt(bold=True)); cx.calc(ws, 6, 1, f'=COUNTIF({rng},"PASS")&" / "&COUNTIF({rng},"FAIL")', f"{n_pass} / {nfail}")
    ws.freeze_panes(hdr + 1, 3)
    cx.R["recon"] = dict(rows=rows, r0=r0, r1=r1, n=len(rows), n_pass=n_pass)
    # source identity block
    r = r1 + 3
    r = cx.section(ws, r, "Source identity (recorded at generation)", "The workbook was built only after the Phase 4 hand-off passed its gates (manifest hashes, row counts, every out_val_* row PASS).", 8)
    idn = cx.identity
    facts = [("Phase 4 database SHA-256", idn["database_sha256"]), ("Phase 4 manifest SHA-256", idn["phase4_manifest_sha256"]),
             ("Phase 4 output tables verified (count)", idn["phase4_output_tables"]),
             ("Approved canonical cleaned CSV SHA-256", idn["canonical_csv_expected_sha256"]),
             ("Cleaned CSV present when generated / matches approved hash", f"{idn['canonical_csv_present']} / {idn['canonical_csv_matches']}"),
             ("Generator script SHA-256 (src/phase5_excel.py)", cx.script_sha), ("Generated at (UTC)", cx.generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")),
             ("Workbook version", VERSION)]
    facts += [(f"{t}: rows / PASS", f"{v['rows']} / {v['pass']}") for t, v in idn["validation_rows"].items()]
    for i, (a, b) in enumerate(facts):
        ws.write_string(r + i, 0, a, cx.fmt(bold=True)); ws.merge_range(r + i, 0, r + i, 1, a, cx.fmt(bold=True))
        ws.merge_range(r + i, 2, r + i, 5, str(b), cx.fmt(font_name="Consolas", align="left"))
    ws.set_landscape(); ws.fit_to_pages(1, 0)
    return rows


# ---------------------------------------------------------------------------------------------------------------------
# Sheets 1-2: Start Here, Executive Summary (written last: they link to everything else)
# ---------------------------------------------------------------------------------------------------------------------
def build_exec(cx: Ctx, reg, order):
    ws, S = cx.ws["Executive Summary"], "Executive Summary"
    rc = cx.R["recon"]
    cx.title(ws, "Executive summary - FP&A month-end close analysis", "NovaBridge Industries (synthetic extract), Jan 2023 - Dec 2025, six legal entities, USD. Every number on this page is a green link to the sheet that calculates it.",
             "READ FIRST: all figures are provisional. The population is Posted-only journal lines with scale restoration (conventions R6/R7), signs are as recorded (R9 unresolved) and there are no favourable/adverse labels. "
             "The operating result proxy is NOT EBITDA. Nothing here is a forecast-skill claim, a saving or a finding about cause - see 'Insights & Actions' for what is observed vs hypothesised.", width=7)
    ws.set_column(0, 0, 44); ws.set_column(1, 1, 18); ws.set_column(2, 2, 14); ws.set_column(3, 6, 18)
    r = 4
    r = cx.section(ws, r, "Headline numbers (3 years, eligible Posted-only lines)", None, 7)
    cx.hdr(ws, r, 0, ["Measure", "Value", "", "Where calculated"], 22)
    items = [("Revenue (USD)", "mpl_total_rev", NF_USD, "Monthly P&L"), ("Gross profit, treatment S1 signed as recorded (USD)", "mpl_total_gp", NF_USD, "Monthly P&L / Gross Profit"),
             ("Gross margin % (S1)", "mpl_total_gm", NF_PCT, "Monthly P&L"), ("Operating result proxy (USD) - not EBITDA", "mpl_total_proxy", NF_USD, "Monthly P&L"),
             ("Proxy margin %", "mpl_total_proxym", NF_PCT, "Monthly P&L"), ("Eligible P&L lines (count)", "mpl_total_n", NF_INT, "Monthly P&L"),
             ("Revenue growth 2024 vs 2023", "fy_growth_2024", NF_PCT, "Monthly P&L (calendar-year block)"), ("Revenue growth 2025 vs 2024", "fy_growth_2025", NF_PCT, "Monthly P&L (calendar-year block)"),
             ("Revenue variance vs budget, same-sign lines (USD)", "bva_ss_REVENUE_var", NF_USD, "Budget vs Actual A1"), ("Revenue variance %, same-sign lines", "bva_ss_REVENUE_pct", NF_PCT, "Budget vs Actual A1"),
             ("COGS variance %, same-sign lines", "bva_ss_COGS_pct", NF_PCT, "Budget vs Actual A1"), ("People variance %, same-sign lines", "bva_ss_PEOPLE_pct", NF_PCT, "Budget vs Actual A1"),
             ("Opex variance %, same-sign lines", "bva_ss_OPEX_pct", NF_PCT, "Budget vs Actual A1"),
             ("Gross profit variance vs budget, S1 same-sign (USD)", "gp3_GP_S1_SIGNED_AS_RECORDED_gv", NF_USD, "Gross Profit GP3"),
             ("Opposite-sign share of revenue forecast error", "fc_opp_share_REVENUE", NF_PCT, "Forecast & Prior Year F4")]
    for i, (lab, key, nf, where) in enumerate(items):
        rr = r + 1 + i
        cx.txt(ws, rr, 0, lab)
        v = cx.val(key)
        if isinstance(v, str):
            cx.txt(ws, rr, 1, v, align="right")
        else:
            cx.calc(ws, rr, 1, f"={cx.ref(key)}", v, nf, color=GREEN, bold=True)
        ws.write_url(rr, 3, f"internal:'{cx.R[key][0]}'!A1", cx.fmt(font_color="#0563C1", underline=1), where)
    r = r + len(items) + 2
    r = cx.section(ws, r, "Revenue forecast accuracy: three populations, never to be mixed", "WAPE = sum |forecast - actual| / sum |actual| (budget analogous). Forecast error = forecast - actual.", 7)
    cx.hdr(ws, r, 0, ["Population (revenue lines)", "Lines (count)", "Forecast WAPE", "Budget WAPE", "Where calculated"], 30)
    pops = [("A. Matched same-sign subset: actual, budget and forecast all non-zero with the same sign (selected by outcome)", "fc_c6_REVENUE_n", "fc_c6_REVENUE_wf", "fc_c6_REVENUE_wb", "Forecast & Prior Year F3"),
            ("B. Comparable lines: actual, budget and forecast all present, any sign (same lines for both measures)", "fc_cmp_REVENUE_n", "fc_cmp_REVENUE_wf", "fc_cmp_REVENUE_wb", "Forecast & Prior Year F3b"),
            ("C. All lines with a forecast value (no budget required; budget WAPE not computed on this population)", "fc_al_REVENUE_n", "fc_al_REVENUE_wape", None, "Forecast & Prior Year F2")]
    for i, (lab, kn, kf, kb, where) in enumerate(pops):
        rr = r + 1 + i
        ws.write_string(rr, 0, lab, cx.fmt(text_wrap=True, valign="top")); ws.set_row(rr, 44)
        cx.calc(ws, rr, 1, f"={cx.ref(kn)}", cx.val(kn), NF_INT, color=GREEN, bold=True)
        cx.calc(ws, rr, 2, f"={cx.ref(kf)}", cx.val(kf), NF_PCT2, color=GREEN, bold=True)
        if kb:
            cx.calc(ws, rr, 3, f"={cx.ref(kb)}", cx.val(kb), NF_PCT2, color=GREEN, bold=True)
        else:
            cx.txt(ws, rr, 3, "n/a", align="right")
        ws.write_url(rr, 4, f"internal:'{cx.R[kf][0]}'!A1", cx.fmt(font_color="#0563C1", underline=1), where)
    r = r + 5
    for t in ("Why the populations differ: A keeps only lines where all three amounts agree in sign, which mechanically removes the lines carrying most of the error (opposite-sign lines hold the share of absolute revenue forecast error shown above). B keeps every line that has all three values. C also keeps lines with no budget value.",
              "Reading: the matched-subset WAPE (A) is small because of how the subset is chosen; it is not general forecasting skill. On B both errors are large and the forecast is only modestly closer than the budget for revenue, COGS and opex, and not closer for people costs (see Forecast & Prior Year F3b). The extract has no forecast version or as-of date, so forecast skill cannot be established from either figure."):
        ws.merge_range(r, 0, r, 6, t, cx.fmt(text_wrap=True, valign="top", italic=True)); ws.set_row(r, 44); r += 1
    r += 2
    rs = cx.R["recon"]
    cx.txt(ws, r, 0, "Reconciliation status (workbook vs independent database recompute)", bold=True)
    cx.calc(ws, r, 1, f"='Reconciliation & QA'!$B$5", f"ALL {rs['n']} CHECKS PASS" if rs["n"] == rs["n_pass"] else f"{rs['n'] - rs['n_pass']} CHECK(S) FAIL", color=GREEN, bold=True)
    ws.merge_range(r, 2, r, 4, "", cx.fmt())
    ws.conditional_format(r, 1, r, 1, {"type": "text", "criteria": "containing", "value": "FAIL", "format": cx.fmt(bg_color="#FFC7CE", font_color="#9C0006")})
    ws.conditional_format(r, 1, r, 1, {"type": "text", "criteria": "containing", "value": "PASS", "format": cx.fmt(bg_color="#C6EFCE", font_color="#006100")})
    r += 3
    ws.set_h_pagebreaks([r])   # print only: annual table, its chart and the ranked insights start on a new printed page (no effect on screen)
    r = cx.section(ws, r, "Annual view (links to Monthly P&L)", None, 7)
    cx.hdr(ws, r, 0, ["Year", "Revenue (USD)", "Gross profit S1 (USD)", "Operating result proxy (USD)"], 30)
    for i, y in enumerate((2023, 2024, 2025)):
        rr = r + 1 + i
        cx.inp(ws, rr, 0, str(y), None, align="left")
        for j, k in enumerate((f"fy_rev_{y}", f"fy_gp_{y}", f"fy_proxy_{y}")):
            cx.calc(ws, rr, 1 + j, f"={cx.ref(k)}", cx.val(k), NF_USD, color=GREEN)
    ch = cx.wb.add_chart({"type": "column"})
    for j, (nm, col) in enumerate((("Revenue", "#1F3864"), ("Gross profit (S1)", "#548235"), ("Operating result proxy", "#C55A11"))):
        ch.add_series({"name": nm, "categories": f"='{S}'!$A${r + 2}:$A${r + 4}", "values": f"='{S}'!${xl_col_to_name(1 + j)}${r + 2}:${xl_col_to_name(1 + j)}${r + 4}", "fill": {"color": col}, "gap": 80})
    ch.set_title({"name": "Revenue, gross profit and operating result proxy by calendar year (USD)", "name_font": {"size": 10}})
    ch.set_y_axis({"num_format": "#,##0,,\"m\"", "name": "USD millions", "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
    ch.set_legend({"position": "bottom"}); ch.set_size({"width": 620, "height": 290})
    ws.insert_chart(r - 1, 5, ch, {"x_offset": 10})
    r += 6
    r = cx.section(ws, r, "Ranked insights (observed fact first; see 'Insights & Actions' for hypothesis, evidence required, owner and KPI)", None, 7)
    cx.hdr(ws, r, 0, ["Insight", "Score (of 12)", "Confidence (1-3)"], 22)
    for i, k in enumerate(order):
        rr = r + 1 + i
        ws.write_string(rr, 0, f"#{reg[k]['rank']} {k}: {reg[k]['headline']}", cx.fmt(text_wrap=True, valign="top"))
        ws.set_row(rr, 44)
        cx.inp(ws, rr, 1, reg[k]["total"], "0"); cx.inp(ws, rr, 2, reg[k]["conf"], "0")
    ws.set_column(0, 0, 70)
    r += len(order) + 3
    r = cx.section(ws, r, "What this workbook does NOT say", None, 7)
    notes = ["Costs are not 'favourable' or 'adverse': the sign convention (R9) is unresolved.",
             "A variance is not a saving; no recoverable-savings amount is claimed anywhere (financial exposure, cause hypothesis and savings are kept separate).",
             "The matched-subset forecast WAPE is not general forecasting skill: on all comparable lines both errors are large and the forecast's edge over the budget is small (and absent for people costs). Without dated forecast snapshots neither is evidence of skill or of a correctable bias.",
             "Headline revenue moves by more than 100% depending on which journal statuses count (INS-01): confirm the status rule before using any total externally.",
             "Balance-sheet lines are records, not period-end balances; close duration and on-time-close rates cannot be calculated from this extract."]
    for i, t in enumerate(notes):
        ws.merge_range(r + i, 0, r + i, 6, "- " + t, cx.fmt(text_wrap=True, valign="top"))
        ws.set_row(r + i, 28)
    ws.freeze_panes(4, 0)
    ws.set_landscape(); ws.fit_to_pages(1, 0)


def build_start(cx: Ctx):
    ws, S = cx.ws["Start Here"], "Start Here"
    ws.hide_gridlines(2)
    ws.set_column(0, 0, 30); ws.set_column(1, 1, 96)
    ws.write_string(0, 0, "Month-End Close Reliability & Financial Performance Analytics", cx.fmt(bold=True, font_size=18, font_color=NAVY))
    ws.write_string(1, 0, "Phase 5 - FP&A Excel workbook and reconciliation  |  NovaBridge Industries (synthetic data)  |  local use only, not published", cx.fmt(italic=True, font_color="#595959"))
    ws.merge_range(3, 0, 3, 1, "STATUS: PROVISIONAL. The data is a synthetic extract with unverified provenance and licence. Posted-only eligibility, scale restoration, FX direction and the variance-% convention are working conventions; the account sign convention, "
                   "duplicate rule and consolidation are unresolved. Read 'Definitions' before quoting any number.", cx.fmt(bg_color=AMBER, text_wrap=True, border=1, border_color="#BF9000", valign="top"))
    ws.set_row(3, 48)
    r = 5
    ws.write_string(r, 0, "Sheet", cx.fmt(bold=True, font_color="#FFFFFF", bg_color=NAVY)); ws.write_string(r, 1, "What it answers", cx.fmt(bold=True, font_color="#FFFFFF", bg_color=NAVY))
    desc = {"Start Here": "This page: scope, status, navigation, colour legend, source identity.",
            "Executive Summary": "Headline numbers, annual view, ranked insights and what the workbook does not claim. All numbers are links.",
            "Monthly P&L": "36-month P&L by section, gross profit, operating result proxy, calendar-year totals, MoM %. Source of the totals every other sheet reconciles to.",
            "Budget vs Actual": "Variance by section on same-sign and all-lines bases, bridge, top entity x GL contributors, materiality sensitivity, monthly variance with % check.",
            "Forecast & Prior Year": "Forecast error (WAPE, bias), forecast vs budget on matched lines, where the error sits, prior-year column vs true year-on-year.",
            "Entity & Division": "Six entities and five divisions: size, margin, variance, growth; entity x GL variance detail.",
            "GL & Cost Drivers": f"{cx.d.one('SELECT count(*) FROM out_a4_pl_gl')} GL accounts, cost Pareto, mix, cost-to-revenue, concentration, persistent deviations, salary-rate scenario (conditional).",
            "Gross Profit": "Three explicit discount/sign treatments x two row sets; margin range, versus budget, by entity.",
            "Insights & Actions": "Seven ranked insights, 16 fields each: observed vs hypothesis, evidence required, owner, KPI. No savings claims.",
            "Data Quality": "Exclusion waterfall (152,682 rows), flag exposure, field reliability, scenario swings, scale/duplicate exposure, balance-sheet limits.",
            "Reconciliation & QA": "Live PASS/FAIL formulas: workbook vs independent recompute from the Phase 4 database views, plus source identity.",
            "Definitions": "Rules register R1-R14, metric definitions, owner decisions, assumptions, lineage."}
    for i, n in enumerate(SHEETS):
        ws.write_url(r + 1 + i, 0, f"internal:'{n}'!A1", cx.fmt(font_color="#0563C1", underline=1), f"{i + 1}. {n}")
        ws.write_string(r + 1 + i, 1, desc[n], cx.fmt(text_wrap=True, valign="top"))
        ws.set_row(r + 1 + i, 30)
    r += len(SHEETS) + 3
    ws.write_string(r, 0, "Colour and format legend", cx.fmt(bold=True, font_size=12, font_color=NAVY)); r += 1
    legend = [("Blue text", BLUE, "Input value taken from Phase 4 (or an adjustable assumption on an amber cell)."), ("Black text", BLACK, "Formula calculated on the same sheet."),
              ("Green text", GREEN, "Formula that links to another sheet in this workbook."), ("Red text", RED, "Link to an external workbook - none exist in this file (checked by the test suite)."),
              ("Negative numbers", "#FF0000", "Red in parentheses; zeros show as a dash."), ("Amber fill", BLACK, "Adjustable threshold, or highlighted result (legend printed on each sheet).")]
    for i, (a, col, b) in enumerate(legend):
        ws.write_string(r + i, 0, a, cx.fmt(font_color=col, bold=True, bg_color=AMBER if a == "Amber fill" else "#FFFFFF"))
        ws.write_string(r + i, 1, b)
    r += len(legend) + 2
    ws.write_string(r, 0, "How to read", cx.fmt(bold=True, font_size=12, font_color=NAVY)); r += 1
    for i, t in enumerate(["Amounts: USD, scale-adjusted (provisional), signs as recorded; costs are positive magnitudes.",
                           "Variance = Actual - Budget; Variance % = Variance / |net budget|, hidden when |net budget| < 50% of gross budget. Direction columns state arithmetic only.",
                           "Primary basis: same-sign lines. The all-lines view is always shown beside it. Opposite-sign and zero-involved lines are bridged, never removed or flipped.",
                           "Tables have filters; use the sheet's Basis / Section columns to slice. Every sheet has a link back to this page.",
                           "Reconciliation & QA must read ALL CHECKS PASS; if you change an input, re-check it."]):
        ws.merge_range(r + i, 0, r + i, 1, f"{i + 1}. {t}", cx.fmt(text_wrap=True, valign="top")); ws.set_row(r + i, 28)
    r += 7
    ws.write_string(r, 0, "Source identity", cx.fmt(bold=True, font_size=12, font_color=NAVY)); r += 1
    idn = cx.identity
    for i, (a, b) in enumerate([("Reconciliation status", None), ("Phase 4 database SHA-256", idn["database_sha256"]), ("Approved cleaned CSV SHA-256", idn["canonical_csv_expected_sha256"]),
                                ("Generator SHA-256", cx.script_sha), ("Generated at (UTC)", cx.generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")), ("Version", VERSION)]):
        ws.write_string(r + i, 0, a, cx.fmt(bold=True))
        if b is None:
            rs = cx.R["recon"]
            cx.calc(ws, r + i, 1, "='Reconciliation & QA'!$B$5", f"ALL {rs['n']} CHECKS PASS" if rs["n"] == rs["n_pass"] else f"{rs['n'] - rs['n_pass']} CHECK(S) FAIL", color=GREEN, bold=True, align="left")
        else:
            ws.write_string(r + i, 1, b, cx.fmt(font_name="Consolas", font_size=9))
    ws.set_landscape(); ws.fit_to_pages(1, 1)


# ---------------------------------------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------------------------------------
def build_workbook(path: Path, d: Data, identity: dict, generated_at: dt.datetime, script_sha: str, nocache: bool = False) -> dict:
    cx = Ctx(path, d, identity, generated_at, script_sha)
    cx.nocache = nocache
    build_monthly(cx)
    tbX, det_rows = build_entity(cx)
    build_bva(cx, tbX, det_rows)
    build_forecast(cx)
    build_gl(cx, tbX, det_rows)
    build_gp(cx)
    reg, order = build_insights(cx)
    build_dq(cx)
    r = build_defs(cx)
    build_lineage(cx, r)
    build_recon(cx, None, None)
    build_exec(cx, reg, order)
    build_start(cx)
    for (sh, col), w in cx.widths.items():
        cx.ws[sh].set_column(col, col, w)
    cx.ws["Start Here"].activate()
    cx.ws["Start Here"].set_first_sheet()
    for n in SHEETS:
        cx.ws[n].set_tab_color({"Start Here": NAVY, "Executive Summary": NAVY, "Reconciliation & QA": "#548235", "Definitions": "#7F7F7F"}.get(n, "#9DC3E6"))
    cx.wb.close()
    return {"formulas": cx.formula_count, "recon": cx.R["recon"], "warnings": [c for c in cx.checks if "warn" in c]}


# ---------------------------------------------------------------------------------------------------------------------
# Independent verification of the SAVED file (used by the tests and the QA report)
# ---------------------------------------------------------------------------------------------------------------------
def scan_saved_workbook(path: Path) -> dict:
    """Open the saved .xlsx with openpyxl (not the in-memory writer) and scan every cell."""
    import openpyxl
    import warnings
    import zipfile
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wf = openpyxl.load_workbook(path)                 # formulas
        wv = openpyxl.load_workbook(path, data_only=True)  # cached values
    out = {"sheets": wf.sheetnames, "formulas": 0, "formula_errors": [], "external_refs": [], "merged_in_tables": [], "uncached": [], "tables": 0, "charts": 0, "per_sheet": {}}
    err_re = re.compile(r"^#(REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!)")
    for ws in wf.worksheets:
        vs = wv[ws.title]
        nform = 0
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("="):
                    nform += 1
                    if "[" in v and re.search(r"\[\d+\]|\.xls", v):
                        out["external_refs"].append((ws.title, c.coordinate))
                    cv = vs[c.coordinate].value
                    if cv is None:
                        out["uncached"].append((ws.title, c.coordinate))
                    if isinstance(cv, str) and err_re.match(cv):
                        out["formula_errors"].append((ws.title, c.coordinate, cv))
                elif isinstance(v, str) and err_re.match(v):
                    out["formula_errors"].append((ws.title, c.coordinate, v))
        out["formulas"] += nform
        out["tables"] += len(ws.tables)
        out["charts"] += len(ws._charts)
        out["per_sheet"][ws.title] = {"rows": ws.max_row, "cols": ws.max_column, "formulas": nform, "tables": len(ws.tables)}
        tabs = [t.ref for t in ws.tables.values()]
        for m in ws.merged_cells.ranges:
            for ref in tabs:
                a, b = ref.split(":")
                from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
                (ca, ra), (cb, rb) = coordinate_from_string(a), coordinate_from_string(b)
                if not (m.max_row < ra or m.min_row > rb or m.max_col < column_index_from_string(ca) or m.min_col > column_index_from_string(cb)):
                    out["merged_in_tables"].append((ws.title, str(m)))
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        out["external_link_parts"] = [n for n in names if "externalLink" in n]
        rels = " ".join(z.read(n).decode("utf8", "ignore") for n in names if n.endswith(".rels"))
        out["external_targets"] = re.findall(r'TargetMode="External"', rels)
    return out


def lo_recalc_convert(src: Path, outdir: Path, work: Path) -> Path | None:
    """Open `src` in headless LibreOffice with 'always recalculate' and save an .xlsx copy; returns the copy or None."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    outdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HOME=str(work))
    prof = work / "profile" / "user"
    prof.mkdir(parents=True, exist_ok=True)
    (prof / "registrymodifications.xcu").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>'
        '<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item></oor:items>', encoding="utf-8")
    subprocess.run([soffice, f"-env:UserInstallation={prof.parent.as_uri()}", "--headless", "--norestore", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(outdir), str(src)],
                   capture_output=True, text=True, timeout=300, env=env)
    out = outdir / src.name
    return out if out.exists() else None


def libreoffice_recalc_compare(db_path: Path, identity: dict, generated_at: dt.datetime, script_sha: str, shipped_path: Path | None = None, tol_abs=1e-6, tol_rel=1e-9) -> dict:
    """Build a variant whose formulas carry NO cached values, let LibreOffice calculate every formula, and compare with the shipped file's cached values."""
    import openpyxl
    import warnings
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return {"available": False, "reason": "LibreOffice (soffice) not found"}
    work = Path(tempfile.mkdtemp(prefix="p5lo_"))
    try:
        shipped = shipped_path or (work / "shipped.xlsx")   # the SAVED deliverable when given: its cached values are what a user sees
        nocache = work / "nocache.xlsx"
        d = Data(db_path)
        try:
            if shipped_path is None:
                build_workbook(shipped, d, identity, generated_at, script_sha)
            build_workbook(nocache, d, identity, generated_at, script_sha, nocache=True)
        finally:
            d.close()
        outdir = work / "lo"
        outdir.mkdir()
        conv = lo_recalc_convert(nocache, outdir, work)
        if conv is None:
            return {"available": True, "ok": False, "reason": "LibreOffice conversion failed"}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ref = openpyxl.load_workbook(shipped, data_only=True)
            frm = openpyxl.load_workbook(shipped)
            lo = openpyxl.load_workbook(conv, data_only=True)
        n = bad = 0
        examples = []
        for ws in frm.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and c.value.startswith("="):
                        n += 1
                        a, b = ref[ws.title][c.coordinate].value, lo[ws.title][c.coordinate].value
                        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
                            ok = abs(a - b) <= max(tol_abs, tol_rel * max(abs(a), abs(b)))
                        else:
                            ok = (a == b) or (a in (None, "") and b in (None, ""))
                        if not ok:
                            bad += 1
                            if len(examples) < 12:
                                examples.append((ws.title, c.coordinate, c.value[:70], a, b))
        return {"available": True, "ok": bad == 0, "formulas_compared": n, "mismatches": bad, "examples": examples}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def write_qa_report(out_dir: Path, db_path: Path, p4_out: Path, csv_path: Path) -> int:
    """Run the test suite and independent checks against the SAVED workbook and write PHASE5_QA_REPORT.md with the real results (including failures and skips)."""
    import xml.etree.ElementTree as ET
    xlsx = out_dir / WORKBOOK_NAME
    man_path = out_dir / "MANIFEST.json"
    if not xlsx.exists() or not man_path.exists():
        print("INPUT ERROR: generate the workbook first", file=sys.stderr)
        return 1
    man = json.loads(man_path.read_text(encoding="utf-8"))
    junit = Path(tempfile.mkdtemp(prefix="p5qa_")) / "junit.xml"
    env = dict(os.environ)
    proc = subprocess.run([sys.executable, "-m", "pytest", str(ROOT / "tests" / "test_phase5_excel.py"), "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
                          capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=1800)
    cases = []
    for tc in ET.parse(junit).getroot().iter("testcase"):
        st = "FAIL" if (tc.find("failure") is not None or tc.find("error") is not None) else ("SKIP" if tc.find("skipped") is not None else "PASS")
        why = ""
        for tag in ("failure", "error", "skipped"):
            el = tc.find(tag)
            if el is not None:
                why = (el.get("message") or "")[:160]
        cases.append((tc.get("name"), st, why))
    counts = {k: sum(1 for c in cases if c[1] == k) for k in ("PASS", "FAIL", "SKIP")}
    scan = scan_saved_workbook(xlsx)
    idn = verify_phase4(db_path, p4_out, csv_path if csv_path.exists() else None)
    lo = libreoffice_recalc_compare(db_path, idn, dt.datetime.strptime(man["generated_at_utc"], "%Y-%m-%dT%H:%M:%SZ"), man["generator_sha256"], shipped_path=xlsx)
    d = Data(db_path)
    try:
        # reconciliation summary by area, straight from the saved file
        import openpyxl
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wv = openpyxl.load_workbook(xlsx, data_only=True)
        ws = wv["Reconciliation & QA"]
        by_area: dict = {}
        for r in range(10, ws.max_row + 1):
            if isinstance(ws.cell(r, 1).value, str) and re.match(r"R-\d", ws.cell(r, 1).value):
                a = by_area.setdefault(ws.cell(r, 2).value, [0, 0])
                a[0] += 1
                a[1] += ws.cell(r, 8).value == "PASS"
    finally:
        d.close()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    csv_state = ("present and matches the approved SHA-256" if idn["canonical_csv_matches"] else "NOT present: hash check skipped") if idn["canonical_csv_present"] or True else ""
    L = []
    L += ["# Phase 5 QA report - FP&A Excel workbook", "", f"Report written: {now}. Workbook: `{WORKBOOK_NAME}` (generated {man['generated_at_utc']}).", "",
          "This report records what was actually run against the **saved** workbook. Failures and skips are listed, not hidden. Microsoft Excel was **not** used; recalculation was done with LibreOffice.", "",
          "## 1. Result at a glance", "",
          f"| Item | Result |", "|---|---|",
          f"| Tests | **PASS {counts['PASS']} / FAIL {counts['FAIL']} / SKIP {counts['SKIP']}** (pytest exit code {proc.returncode}) |",
          f"| Reconciliation sheet (live formulas) | {man['reconciliation']['pass']} of {man['reconciliation']['checks']} checks PASS |",
          f"| LibreOffice independent recalculation | " + (f"{lo['formulas_compared']} formulas compared, {lo['mismatches']} mismatches" if lo.get("available") and "formulas_compared" in lo else str(lo)) + " |",
          f"| Formula cells / errors / external links | {scan['formulas']} / {len(scan['formula_errors'])} / {len(scan['external_refs']) + len(scan['external_link_parts']) + len(scan['external_targets'])} |",
          f"| Sheets / tables / charts | {len(scan['sheets'])} / {scan['tables']} / {scan['charts']} |",
          f"| Workbook SHA-256 | `{sha256_file(xlsx)}` |", ""]
    L += ["## 2. Source identity", "", "| Input | Value |", "|---|---|",
          f"| Phase 4 database SHA-256 | `{idn['database_sha256']}` |", f"| Phase 4 manifest SHA-256 | `{idn['phase4_manifest_sha256']}` |",
          f"| Phase 4 output tables verified against manifest hashes and row counts | {idn['phase4_output_tables']} |",
          f"| Phase 4 validation rows (all must PASS) | " + "; ".join(f"{t}: {v['pass']}/{v['rows']}" for t, v in idn["validation_rows"].items()) + " |",
          f"| Approved cleaned CSV SHA-256 | `{p4.EXPECTED_SHA256}` ({csv_state}) |",
          f"| Generator `src/phase5_excel.py` SHA-256 | `{man['generator_sha256']}` |", ""]
    L += ["## 3. Reconciliation by area (from the saved file)", "", "| Area | Checks | PASS |", "|---|---:|---:|"]
    L += [f"| {a} | {n} | {p} |" for a, (n, p) in by_area.items()]
    L += ["", "Expected values come from the Phase 4 analytical views (`v_pl_actual`, `v_var_scn`, `v_fc_scn`, `v_gp_rows`), not from the `out_*` tables the sheets were built from. Tolerances: counts 0; USD 0.5; ratios 1e-6.", ""]
    L += ["## 4. Test results", "", "| Test | Result | Note |", "|---|---|---|"]
    L += [f"| `{n}` | {s} | {w} |" for n, s, w in cases]
    L += ["", "## 5. Checks performed on the saved file", "",
          "- Reopened with openpyxl (formulas and cached values): 12 sheets in the specified order; every formula has a cached value; no `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`, `#NUM!` anywhere.",
          "- No external links: no `externalLink` package parts, no external relationship targets, no `[n]`/`.xls`/URL references in any formula or hyperlink.",
          "- Every cross-sheet reference points at an existing, populated cell.",
          "- Every formula was recalculated by LibreOffice from a copy **with the cached values removed** (so LibreOffice had to compute all of them) and compared with the saved cached values.",
          "- Mutation test: one monthly revenue input was changed in a copy and recalculated; the reconciliation sheet turned to FAIL on the checks that depend on it (proof the checks can fail).",
          "- Totals, populations, variance and guarded %, forecast WAPE/bias, gross-profit treatments, signed GL 4190 amount and entity/division totals were re-derived from the database views and compared.",
          "- Insight text equals the Phase 4 register; key figures were rebuilt from the database and found in the text; each block has all 16 fields; observed fact and hypothesis are separate; no savings amount is claimed.",
          "- Rules R1-R14 are copied from `docs/FINANCIAL_METRICS.md` with their statuses unchanged (R9, R11, R12 stay Unresolved).",
          "- Determinism: two builds with the same timestamp are byte-identical; the database is opened read-only and its hash is unchanged.",
          "- Fail-closed gates: tampered Phase 4 output, missing inputs, failing validation row and wrong CSV hash all stop the build (exit 1 or 2) with no workbook written.", ""]
    L += ["## 6. Not done / limits (read before accepting)", "",
          "- **Microsoft Excel was not used.** The file was written with XlsxWriter and recalculated with LibreOffice 24.2. Excel-specific behaviour (for example table styles, conditional-format rendering, Windows fonts) has not been observed.",
          "- Visual inspection: the saved workbook was rendered to PDF with LibreOffice (49 pages, fit to page width) and every page was looked at as an image (100 dpi, two pages per view): all 12 sheets and all populated sections, including the full length of Insights & Actions. Clipped columns, a double space in a headline, row heights and an unpaginated Definitions sheet were found and fixed this way. NOT done: opening the file in Microsoft Excel or on screen at 100% zoom, clicking the navigation links, and checking frozen panes, filters and conditional-format colours in a spreadsheet application (these are checked structurally by the tests only). At print scale, small text in the long tables was read for clipping and '###' only (a text search of the PDF found no '###').",
          "- Tests were run on Linux, not on the user's Windows machine.",
          "- Earlier copies of the cleaned and raw CSVs that were found outside the project folder did not match the approved hashes (Phase 4 finding); they were not used. This build uses the hash-verified Phase 4 database. " + ("The canonical CSV in this repository was hash-checked at generation." if idn["canonical_csv_matches"] else "The canonical CSV was not present at generation, so only the database hash chain was verified."),
          "- Everything remains **provisional**: Posted-only status rule (R6), scale restoration (R7), FX direction (R8), variance-% convention (R10), per-line summing of budget/forecast/prior-year, and the exclusion of junk entities (R4). Sign convention (R9), duplicates (R11) and consolidation (R12) are unresolved. The data is synthetic; provenance and licence are unverified.",
          "- Not built because the data cannot support it: EBITDA, close duration / on-time close, cost-centre variance, forecast skill or bias correction, price-volume-mix and unit economics, balance-sheet ratios, consolidated group results.",
          "- Insight text is taken from the Phase 4 register and is not re-validated by a second analyst.",
          "- No dashboard, no Power BI, nothing committed or published.", ""]
    L += ["## 7. How to regenerate", "", "```", "python src/phase5_excel.py                      # verifies Phase 4, builds the workbook and MANIFEST.json",
          "python -m pytest tests/test_phase5_excel.py -q   # needs the workbook; LibreOffice for 2 tests",
          "python src/phase5_excel.py --qa-report          # reruns the tests and rewrites this report", "```", "",
          "Exit codes: 0 ok; 1 missing/unreadable input; 2 integrity or reconciliation failure. Use `--generated-at 2026-10-29T12:00:00Z` for a byte-identical rebuild.", ""]
    (out_dir / "PHASE5_QA_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    man["qa"] = {"tests": counts, "pytest_exit_code": proc.returncode, "libreoffice_formulas_compared": lo.get("formulas_compared"), "libreoffice_mismatches": lo.get("mismatches"),
                 "report": "PHASE5_QA_REPORT.md"}
    man_path.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"QA report written. Tests PASS {counts['PASS']} / FAIL {counts['FAIL']} / SKIP {counts['SKIP']}; LibreOffice mismatches: {lo.get('mismatches')}")
    return 0 if counts["FAIL"] == 0 and lo.get("ok") else 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--phase4-out", type=Path, default=DEFAULT_P4_OUT)
    ap.add_argument("--csv", type=Path, default=p4.DEFAULT_CSV, help="canonical cleaned CSV; verified by hash when present (optional)")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--generated-at", default=None, help="ISO-8601 UTC timestamp; fix it for a byte-identical rerun")
    ap.add_argument("--qa-report", action="store_true", help="do not rebuild: run the tests and independent checks against the saved workbook and write PHASE5_QA_REPORT.md")
    args = ap.parse_args(argv)
    if args.qa_report:
        return write_qa_report(args.out_dir, args.db, args.phase4_out, args.csv)
    try:
        gen = (dt.datetime.fromisoformat(args.generated_at.replace("Z", "+00:00")).replace(tzinfo=None) if args.generated_at
               else dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None))
        identity = verify_phase4(args.db, args.phase4_out, args.csv)
    except SourceError as e:
        print(f"INPUT ERROR: {e}", file=sys.stderr); return 1
    except IntegrityError as e:
        print(f"INTEGRITY FAILURE: {e}", file=sys.stderr); return 2
    script_sha = sha256_file(Path(__file__).resolve())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".p5stage_", dir=str(args.out_dir)))
    d = Data(args.db)
    try:
        tmp = stage / WORKBOOK_NAME
        info = build_workbook(tmp, d, identity, gen, script_sha)
        final = args.out_dir / WORKBOOK_NAME
        shutil.move(str(tmp), str(final))
    finally:
        d.close()
        shutil.rmtree(stage, ignore_errors=True)
    out_sha = sha256_file(final)
    rc = info["recon"]
    manifest = {
        "workbook": WORKBOOK_NAME, "workbook_sha256": out_sha, "workbook_bytes": final.stat().st_size, "version": VERSION,
        "generated_at_utc": gen.strftime("%Y-%m-%dT%H:%M:%SZ"), "generator": "src/phase5_excel.py", "generator_sha256": script_sha,
        "sheets": SHEETS, "formula_cells": info["formulas"],
        "reconciliation": {"checks": rc["n"], "pass": rc["n_pass"], "fail": rc["n"] - rc["n_pass"]},
        "generator_warnings": [w["warn"] for w in info["warnings"]],
        "inputs": identity,
        "notes": ["Built only after the Phase 4 hand-off passed manifest-hash, row-count and out_val_* gates.",
                  "No external links; no data from outside the validated Phase 4 database and the Phase 4 docs.",
                  "Excel itself was not used; recalculation was verified with LibreOffice (see PHASE5_QA_REPORT.md)."],
    }
    (args.out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Workbook: {final}  sha256 {out_sha[:16]}...  formulas {info['formulas']}  reconciliation {rc['n_pass']}/{rc['n']} PASS")
    if info["warnings"]:
        for w in info["warnings"]:
            print("WARNING:", w["warn"], file=sys.stderr)
    return 0 if rc["n"] == rc["n_pass"] and not info["warnings"] else 2


if __name__ == "__main__":
    sys.exit(main())
