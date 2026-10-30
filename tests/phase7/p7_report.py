"""Phase 7 - assemble deliverables from the check registries: qa_results.json, three Excel workbooks, the file manifest
and PHASE7_QA_REPORT.md. Counts are derived from the registries; nothing is hard-coded except prose and the issue log."""
import json, platform, subprocess, datetime as dt
from collections import Counter, OrderedDict
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from p7_common import *

AREAS = OrderedDict([("lineage", "Data lineage & record reconciliation"), ("financial_sql", "Independent financial recomputation vs SQL"),
                     ("sql", "SQL layer (canonical DuckDB, read-only)"), ("excel", "Phase 5 Excel workbook"),
                     ("dashboard", "Phase 6 dashboard (browser)"), ("assumptions", "Project assumptions & disclosure"),
                     ("pipeline", "Python/SQL/Excel re-runs & reproducibility"), ("security", "Security, privacy & publication")])
checks = []
for k in AREAS:
    f = WORK / f"checks_{k}.json"
    if f.exists():
        for r in json.loads(f.read_text()):
            r["area_name"] = AREAS[k]; checks.append(r)
cnt = Counter(r["status"] for r in checks)
by_area = OrderedDict((AREAS[k], Counter(r["status"] for r in checks if r["area"] == k)) for k in AREAS)

ISSUES = [
 dict(id="ISS-01", severity="Medium", category="Reproducibility / documentation", status="Corrected (documentation) and regression-tested",
      title="Documented command to regenerate the cleaned CSV writes it to the wrong folder",
      evidence="HOW_TO_RUN step 0 said 'python src\\clean_fpa_monthly_close.py'. Without --output-dir the script writes to <Downloads>\\fpa_monthly_close_cleaned\\ (src/clean_fpa_monthly_close.py resolve_output_dir), but the pipeline reads data\\processed\\ (src/phase4_pipeline.py DEFAULT_CSV).",
      root_cause="The cleaner's default output folder was designed for the stand-alone Phase 2 run; the repository instructions did not add the folder argument.",
      correction="HOW_TO_RUN.txt step 0 now reads 'python src\\clean_fpa_monthly_close.py --output-dir data\\processed'. Original kept in evidence/originals_before_correction/.",
      regression="Fresh copy without cleaned CSV and DB: corrected command -> SHA-256 c184b677... in data/processed, pipeline exit 0, tests pass (checks RG.*).",
      impact="Another analyst following the instructions would get 'missing input' from the pipeline. No financial figure affected."),
 dict(id="ISS-02", severity="Medium", category="Reproducibility / test design", status="Corrected (documentation); code unchanged",
      title="Following the documented order after a database rebuild produces 2 failing Phase 5 tests",
      evidence="Isolated re-run: step 2 rebuilt phase4_fpa.duckdb (SHA-256 changed although all 72 output CSVs and both documents are byte-identical); step 4 'pytest tests' then gave 123 PASS / 2 FAIL (Phase 5 tests compare the DB hash recorded in the workbook). After step 5 regenerated the workbook the Phase 5 tests passed.",
      root_cause="A DuckDB database file is not byte-reproducible between builds; the workbook manifest uses the file hash as the database identity.",
      correction="HOW_TO_RUN step 4 now says to run 'pytest tests --ignore=tests\\test_phase5_excel.py' after a rebuild and to run the Phase 5 tests in step 5. Longer-term (not applied): fingerprint the DB by its output-table hashes instead of the file hash.",
      regression="Corrected sequence in a fresh copy: all steps exit 0 (checks RG.*).", impact="False test failures; no figure affected."),
 dict(id="ISS-03", severity="Low", category="Privacy / publication readiness", status="Open - action before publication",
      title="QC files record build-machine paths",
      evidence="data/processed/QC_Report.txt and qc_summary.json contain /mnt/user-data/uploads/... and /tmp/claude-0/.../scratchpad/... paths. .gitignore excludes data/processed/*.csv only, so these two files would be committed.",
      root_cause="The cleaner writes absolute input/output paths into its reports.", correction="Before publishing: regenerate from the repository with relative paths or redact the path lines. Not applied in Phase 7 (would change approved Phase 2 outputs; no accuracy impact).",
      regression="n/a", impact="Machine-specific information only; no credentials or personal data found."),
 dict(id="ISS-04", severity="Low", category="Reproducibility", status="Open (accepted)",
      title="Phase 6 QA suite finds the palette validator through a machine-specific path",
      evidence="tests/phase6_dashboard_qa.py globs /tmp/claude-0/bundled-skills/...; on another machine that one check is reported as SKIP.",
      root_cause="External helper script not vendored into the repository.", correction="Vendor the validator or document the SKIP. Not applied.", regression="n/a", impact="One colour-palette check not reproducible elsewhere."),
 dict(id="ISS-05", severity="Low", category="Reproducibility", status="Open - NOT TESTED",
      title="No clean-machine install was performed; installed numpy differs from the pin",
      evidence="requirements.txt pins numpy==2.4.6; the QA container has numpy 2.5.3 (other pins match). All re-runs used the existing environment. Nothing has been run on Windows.",
      root_cause="Environment constraint.", correction="Run 'python -m venv .venv; pip install -r requirements.txt; pip check' and the HOW_TO_RUN steps on the Windows laptop.", regression="n/a", impact="Unknown until run."),
 dict(id="ISS-06", severity="Accepted limitation (publication blocker)", category="Provenance / licence", status="BLOCKED - owner decision",
      title="Synthetic status, provenance and redistribution rights of the dataset are unverified",
      evidence="docs/DATA_PROVENANCE.md; the raw CSV has been tracked by git since Stage 0 (commit 1d601c0) and the repository has a GitHub remote; the dashboard embeds 136,330 journal lines (58,340 with document numbers). Repository visibility was not checked in Phase 7.",
      root_cause="No licence or source document exists.", correction="Owner to document origin/licence, confirm the GitHub repository is private, and decide whether raw data, cleaned data, workbook and dashboard may be redistributed.", regression="n/a", impact="Publication must wait."),
 dict(id="ISS-07", severity="Accepted limitation", category="Population rule", status="Disclosed",
      title="Posted-only rule (R6) is provisional; only 58,340 of 152,682 rows (38.2%) are reported",
      evidence="Independent re-derivation matches row-by-row (L47); 82,986 rows excluded by status; status mix is uniform across entities (possible generated noise). Status scenarios move revenue from $202.6M (Posted) to $471.6M (all statuses).", root_cause="Owner decision pending", correction="Owner to confirm treatment of Pending/Parked/blank.", regression="n/a", impact="Headline totals depend on this rule; disclosed everywhere (AS01)."),
 dict(id="ISS-08", severity="Accepted limitation", category="Scale restoration", status="Disclosed",
      title="Scale restoration (6,265 rows: 1,814 HIGH, 4,451 MEDIUM) is provisional; 73 rows undetermined",
      evidence="Counts verified (L32-L35); in the Posted population 2,374 restored rows. Result proxy: adjusted $26.32M vs as-reported $25.51M vs HIGH-only $29.44M (F_I1).", root_cause="report_scale labels unreliable", correction="Owner to confirm the rule.", regression="n/a", impact="Disclosed; dashboard scale selector shows the range."),
 dict(id="ISS-09", severity="Accepted limitation", category="Sign convention", status="Disclosed",
      title="Account sign convention (R9) unresolved; no favourable/unfavourable labels", evidence="AS02; GL 4190 discounts negative on 58% of lines.", root_cause="Data", correction="Owner decision", regression="n/a", impact="Variances are shown as actual - budget only."),
 dict(id="ISS-10", severity="Accepted limitation", category="FX", status="Disclosed",
      title="2,517 zero FX rates and missing rates unresolved; USD columns used as reported", evidence="D08/D08b, AS05; no metric converts local currency.", root_cause="Data", correction="Owner decision", regression="n/a", impact="None on reported USD figures."),
 dict(id="ISS-11", severity="Accepted limitation", category="Duplicates", status="Disclosed",
      title="3,930 duplicate-candidate rows (incl. 1,587 sign-conflict) retained, none deleted", evidence="D06/D07; exclusion scenarios in F_I1.", root_cause="No confirmed duplicate rule", correction="Owner decision", regression="n/a", impact="Up to $1.6M revenue sensitivity, disclosed."),
 dict(id="ISS-12", severity="Accepted limitation", category="Forecast", status="Disclosed",
      title="Forecast has no version / as-of date: no forecast-skill claim", evidence="AS06", root_cause="Data", correction="n/a", regression="n/a", impact="WAPE/bias shown descriptively only."),
 dict(id="ISS-13", severity="Accepted limitation", category="Gross profit", status="Disclosed",
      title="Gross-profit discount treatment unresolved: S1, S2, S3 kept separate", evidence="F_E1, F_E2 (three distinct values), X35-X36", root_cause="Data", correction="n/a", regression="n/a", impact="Disclosed as a range."),
 dict(id="ISS-14", severity="Accepted limitation", category="Balance sheet / KPIs", status="Disclosed",
      title="Balance-sheet basis not established; DSO, DPO, working capital, close duration not computed", evidence="AS08-AS10; outputs/phase4/h6_bs_metrics_not_computed.csv", root_cause="Data", correction="n/a", regression="n/a", impact="None (correctly not computed)."),
 dict(id="ISS-15", severity="Accepted limitation", category="Units", status="Disclosed",
      title="NOS vs EA unit equivalence unverified; no unit economics built", evidence="AS11, AS20", root_cause="Data", correction="n/a", regression="n/a", impact="None."),
 dict(id="ISS-16", severity="Accepted limitation", category="Parsing", status="Evidence supports current reading",
      title="About 9,100-9,300 amounts per column look like 'n,nnn' (thousands or 3-decimal comma)", evidence="L22, L23: 7,563 testable actuals; 6,940 fit the thousands reading via local/FX within 2% or 1 USD, 0 fit the decimal reading.", root_cause="Mixed source formats", correction="None needed", regression="n/a", impact="Low residual risk."),
 dict(id="ISS-18", severity="Low", category="Documentation / dashboard scope", status="Open - documentation",
      title="4,996 status-excluded lines are in no dashboard view",
      evidence="Non-Posted lines that also have no actual amount (4,958) or an undetermined scale (38) fail the documented any-status gates, so neither payload contains them (waterfall W32-W33). They are counted in the Phase 4 waterfall and the workbook's Data Quality sheet.",
      root_cause="Intended by the documented population definition; not stated on the dashboard's status view.", correction="Add one sentence to the dashboard status note / README in the documentation phase. Not applied (no redesign in Phase 7).",
      regression="n/a", impact="A reader could assume the status diagnostic covers all 82,986 status exclusions."),
 dict(id="ISS-17", severity="Low", category="File inventory", status="Open - housekeeping",
      title="A different file with the raw file's name exists in the owner's Downloads folder",
      evidence="Downloads\\fpa_monthly_close_raw_messy.csv: 51,675,512 bytes, SHA-256 845b78d8..., same 152,682 rows but different formatting/whitespace (149,469 rows differ). The approved raw is 51,938,535 bytes, a0e6edde.... The cleaner searches the Downloads folder by default; its integrity gate refuses the wrong file.",
      root_cause="An earlier copy (probably re-saved by another tool).", correction="Rename or archive the Downloads copy so it cannot be mistaken for the source.", regression="n/a", impact="None while the integrity gate is kept on."),
]

ISSUES.sort(key=lambda d: d["id"])
# ------------------------------------------------------------------ qa_results.json
env = {"python": platform.python_version(), "platform": platform.platform()}
for mod in ["pandas", "numpy", "duckdb", "openpyxl", "pytest", "playwright"]:
    try:
        from importlib.metadata import version; env[mod] = version(mod)
    except Exception: env[mod] = "n/a"
try:
    env["chromium"] = subprocess.run(["python3", "-c", "from playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n b=p.chromium.launch(); print(b.version); b.close()"], capture_output=True, text=True, timeout=60).stdout.strip()
except Exception: env["chromium"] = "n/a"
env["libreoffice"] = subprocess.run(["soffice", "--version"], capture_output=True, text=True).stdout.strip()
INPUTS = OrderedDict([("raw CSV", RAW), ("cleaned CSV (canonical)", CLEAN), ("DuckDB", DB), ("Phase 5 workbook", XLSX), ("Phase 6 dashboard", HTML)])
inputs = [{"role": k, "path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha256(p)} for k, p in INPUTS.items()]
inputs.append({"role": "Phase 2 review workbook (owner's Downloads / master zip)", "path": "fpa_monthly_close_cleaned.xlsx", "bytes": 67381749,
               "sha256": "270edc6b33ae74c46513b4529f6a6e314854c28a898c81f0877c0ac311bb3db6"})
summary = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "counts": {k: cnt.get(k, 0) for k in ["PASS", "FAIL", "BLOCKED", "NOT TESTED", "INFO"]},
           "by_area": {a: dict(c) for a, c in by_area.items()}, "issues_by_severity": dict(Counter(i["severity"] for i in ISSUES)),
           "environment": env, "authoritative_inputs": inputs}
(OUT / "qa_results.json").write_text(json.dumps({"summary": summary, "checks": checks, "issues": ISSUES}, indent=1, default=str), encoding="utf-8")

# ------------------------------------------------------------------ Excel helpers
HF = Font(name="Arial", bold=True, color="FFFFFF"); BF = Font(name="Arial", size=10); TF = Font(name="Arial", bold=True, size=13)
FILL = PatternFill("solid", fgColor="1F3864"); PASSF = PatternFill("solid", fgColor="E2EFDA"); FAILF = PatternFill("solid", fgColor="F8CBAD")
OTHF = PatternFill("solid", fgColor="FFF2CC")


def sheet(wb, name, title, df, widths=None, status_col=None, num_cols=(), note=None):
    ws = wb.create_sheet(name)
    ws["A1"] = title; ws["A1"].font = TF
    r0 = 3
    if note:
        ws["A2"] = note; ws["A2"].font = Font(name="Arial", italic=True, size=9)
    for j, c in enumerate(df.columns, 1):
        x = ws.cell(r0, j, c); x.font = HF; x.fill = FILL; x.alignment = Alignment(wrap_text=True, vertical="top")
    for i, row in enumerate(df.itertuples(index=False), r0 + 1):
        for j, v in enumerate(row, 1):
            if isinstance(v, float) and v != v: v = None
            if isinstance(v, (dict, list, set)): v = json.dumps(v, default=str)
            if isinstance(v, str):   # spreadsheet error tokens quoted in text would read as errors: use a full-width hash
                for tok in ("#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!"):
                    v = v.replace(tok, "\uff03" + tok[1:])
            x = ws.cell(i, j, v); x.font = BF; x.alignment = Alignment(wrap_text=True, vertical="top")
            if isinstance(v, str) and v[:1] in ("=", "+", "@"):
                x.data_type = "s"   # literal text, not a formula
            if df.columns[j - 1] in num_cols and isinstance(v, (int, float)):
                x.number_format = "#,##0.00;(#,##0.00);-" if isinstance(v, float) else "#,##0"
        if status_col:
            s = row[list(df.columns).index(status_col)]
            ws.cell(i, list(df.columns).index(status_col) + 1).fill = PASSF if s == "PASS" else FAILF if s == "FAIL" else OTHF
    for j, c in enumerate(df.columns, 1):
        ws.column_dimensions[get_column_letter(j)].width = (widths or {}).get(c, min(60, max(12, len(str(c)) + 2)))
    ws.freeze_panes = ws.cell(r0 + 1, 1)
    ws.auto_filter.ref = f"A{r0}:{get_column_letter(df.shape[1])}{r0 + len(df)}"
    return ws


def checks_df(rows):
    d = pd.DataFrame(rows)
    cols = ["id", "area_name", "check", "population", "definition", "expected", "actual", "abs_diff", "rel_diff", "tolerance", "status", "note", "evidence"]
    d = d.reindex(columns=cols)
    for c in ["expected", "actual", "tolerance"]:
        d[c] = d[c].map(lambda v: v if isinstance(v, (int, float)) or v is None else str(v))
    return d.rename(columns={"area_name": "area", "note": "explanation / evidence note"})


def summary_sheet(wb, rows, title):
    ws = wb.active; ws.title = "Summary"
    ws["A1"] = title; ws["A1"].font = TF
    ws["A2"] = "Counts are live formulas over the 'Checks' sheet (COUNTIF on the status column). INFO rows are observations, not tests."; ws["A2"].font = Font(name="Arial", italic=True, size=9)
    ws["A4"] = "Status"; ws["B4"] = "Checks"
    for c in ("A4", "B4"): ws[c].font = HF; ws[c].fill = FILL
    n = len(rows) + 3
    for i, s in enumerate(["PASS", "FAIL", "BLOCKED", "NOT TESTED", "INFO"], 5):
        ws.cell(i, 1, s).font = BF
        ws.cell(i, 2, f'=COUNTIF(Checks!$K$4:$K${n},A{i})').font = BF
    ws.cell(10, 1, "Total").font = Font(name="Arial", bold=True); ws.cell(10, 2, "=SUM(B5:B9)").font = Font(name="Arial", bold=True)
    ws.column_dimensions["A"].width = 18; ws.column_dimensions["B"].width = 12
    return ws


def recheck_cols(ws, nrows):
    """Live re-check of numeric rows: |actual - expected| and PASS/FAIL against the numeric tolerance."""
    ws.cell(3, 14, "Recheck |diff| (formula)").font = HF; ws.cell(3, 14).fill = FILL
    ws.cell(3, 15, "Recheck status (formula)").font = HF; ws.cell(3, 15).fill = FILL
    for i in range(4, 4 + nrows):
        ws.cell(i, 14, f'=IF(AND(ISNUMBER(F{i}),ISNUMBER(G{i})),ABS(G{i}-F{i}),"")').font = BF
        ws.cell(i, 15, f'=IF(AND(ISNUMBER(N{i}),ISNUMBER(J{i})),IF(N{i}<=J{i},"PASS","FAIL"),"n/a")').font = BF
        ws.cell(i, 14).number_format = "#,##0.000000"
    ws.column_dimensions["N"].width = 16; ws.column_dimensions["O"].width = 14


W = {"check": 60, "population": 28, "definition": 40, "explanation / evidence note": 70, "expected": 18, "actual": 18, "area": 22, "evidence": 26}

# ------------------------------------------------------------------ DATA_LINEAGE_RECONCILIATION.xlsx
wb = Workbook()
lin = [r for r in checks if r["area"] in ("lineage",)]
summary_sheet(wb, lin, "Data lineage and record-count reconciliation - Phase 7")
d = checks_df(lin); ws = sheet(wb, "Checks", "Lineage checks (independent re-derivation from the raw file)", d, W, "status", ("expected", "actual"))
recheck_cols(ws, len(d))
wf = pd.read_csv(WORK / "waterfall.csv")
sheet(wb, "Waterfall", "Record-count waterfall: raw -> cleaned -> eligibility -> Phase 6 populations", wf,
      {"stage": 70, "identification": 60, "note": 22}, None, ("records",),
      note="Each step is reproducible from the cleaned CSV with the expression in 'identification'; the reasons were re-derived independently from the raw values (check L47).")
g = pd.read_csv(WORK / "gap_16352_breakdown.csv").rename(columns={"row_0": "reason (first failing gate, status gate ignored)"})
sheet(wb, "Gap_16352", "Why 16,352 cleaned rows are in no Phase 6 population", g, {"reason (first failing gate, status gate ignored)": 50}, None,
      ("Posted", "non-Posted", "All"), note="Posted+non-Posted rows that fail a non-status gate. 0 unexplained rows (check P05).")
for s, t in [("pl_actual", "P&L actual"), ("pl_variance", "P&L variance (actual and budget)"), ("bs_actual", "Balance Sheet actual")]:
    e = pd.read_csv(WORK / f"exclusions_{s}.csv").rename(columns={"Unnamed: 0": "primary reason"})
    e.columns = ["primary reason", "rows"]
    ws = sheet(wb, f"Excl_{s}", f"Primary exclusion reasons - {t} (sum must be 152,682)", e, {"primary reason": 40}, None, ("rows",))
    k = len(e) + 4
    ws.cell(k, 1, "Total (formula)").font = Font(name="Arial", bold=True); ws.cell(k, 2, f"=SUM(B4:B{k - 1})").font = Font(name="Arial", bold=True)
rp = pd.read_csv(WORK / "raw_preservation.csv")
sheet(wb, "Raw_preservation", "Raw column -> cleaned column: rows whose value differs (raw-value columns must be 0)", rp, {"note": 30}, None, ("rows_differing",))
af = pd.read_csv(WORK / "amount_format_counts.csv").rename(columns={"Unnamed: 0": "format class (independent parser)"})
sheet(wb, "Amount_formats", "Raw amount formats found by the independent parser (rows)", af, {"format class (independent parser)": 32}, None, tuple(af.columns[1:]))
wb.save(OUT / "DATA_LINEAGE_RECONCILIATION.xlsx")

# ------------------------------------------------------------------ FINANCIAL_RECONCILIATION.xlsx
wb = Workbook()
fin = [r for r in checks if r["area"] in ("financial_sql", "sql", "excel", "dashboard")]
summary_sheet(wb, fin, "Financial reconciliation - independent pandas reference vs SQL, Excel and dashboard")
d = checks_df(fin); ws = sheet(wb, "Checks", "All financial comparisons (same population, same documented definition on both sides)", d, W, "status", ("expected", "actual"),
                              note="Tolerance: money 0.01 USD (one cent); ratios 1e-9; counts exact; dashboard display values at display precision. Table comparisons count the rows outside tolerance (expected 0).")
recheck_cols(ws, len(d))
ref = json.load(open(WORK / "ref_metrics.json"))
hd = pd.DataFrame([{"metric": k, "value": v} for k, v in ref["headline"].items()])
sheet(wb, "Reference_headline", "Independent reference: headline (Posted eligible, scale-adjusted, USD)", hd, {"metric": 30}, None, ("value",),
      note="revenue = REVENUE section; cost = COGS + PEOPLE + OPEX; result proxy = revenue - cost (not EBITDA).")
gp = pd.DataFrame(ref["gp"])
sheet(wb, "Reference_GP", "Independent reference: gross profit S1 / S2 / S3", gp, {"treatment": 30, "rowset": 26}, None,
      ("revenue_usd", "cogs_usd", "gross_profit_usd", "rows_in_scope"))
cc = pd.DataFrame(ref["cost_centre"])
sheet(wb, "Reference_CostCentre", "Independent reference: people + opex by cost centre", cc, {}, None, ("abs_usd", "signed_usd", "rows"))
st = pd.DataFrame([{"status": k, "lines": ref["status_rows"][k], "abs_actual_usd": ref["status_abs"][k]} for k in ref["status_rows"]])
sheet(wb, "Reference_Status", "Independent reference: journal status diagnostic (any-status P&L population, 136,330 lines)", st, {}, None, ("lines", "abs_actual_usd"))
wb.save(OUT / "FINANCIAL_RECONCILIATION.xlsx")

# ------------------------------------------------------------------ ISSUE_LOG.xlsx
wb = Workbook(); ws = wb.active; ws.title = "Issues"
il = pd.DataFrame(ISSUES)[["id", "severity", "category", "status", "title", "evidence", "root_cause", "correction", "regression", "impact"]]
wb.remove(ws)
sheet(wb, "Issues", "Phase 7 issue log (severity per the acceptance criteria)", il,
      {"title": 45, "evidence": 70, "root_cause": 40, "correction": 55, "regression": 40, "impact": 35, "status": 26, "severity": 22, "category": 22})
nf = [r for r in checks if r["status"] in ("FAIL", "BLOCKED", "NOT TESTED")]
sheet(wb, "Not_passed_checks", "Every check that did not PASS (FAIL / BLOCKED / NOT TESTED)", checks_df(nf) if nf else pd.DataFrame({"none": []}), W, "status")
wb.save(OUT / "ISSUE_LOG.xlsx")

# ------------------------------------------------------------------ file manifest
lines = ["# Phase 7 file manifest (SHA-256). Authoritative inputs first, then every project file, then Phase 7 outputs.", ""]
lines.append("## Authoritative inputs")
for i in inputs:
    lines.append(f"{i['sha256']}  {i['bytes']:>12}  {i['path']}  [{i['role']}]")
lines += ["", "## Project files (excluding .git, caches and outputs/phase7)"]
for p in sorted(ROOT.rglob("*")):
    rel = p.relative_to(ROOT)
    if p.is_file() and not (set(rel.parts) & {".git", "__pycache__", ".pytest_cache"}) and not str(rel).startswith("outputs/phase7") and "qa_screens" not in str(rel):
        lines.append(f"{sha256(p)}  {p.stat().st_size:>12}  {rel}")
lines += ["", "## Phase 7 outputs (this manifest excluded; the report is hashed after it is written)"]
for p in sorted(OUT.rglob("*")):
    rel = p.relative_to(ROOT)
    if p.is_file() and p.name not in ("file_manifest_sha256.txt", "PHASE7_QA_REPORT.md") and "/work/" not in str(rel) and not p.suffix == ".pkl":
        lines.append(f"{sha256(p)}  {p.stat().st_size:>12}  {rel}")
(OUT / "file_manifest_sha256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
json.dump({"summary": summary}, open(WORK / "summary_for_report.json", "w"), indent=1, default=str)
print(json.dumps(summary["counts"]), json.dumps({a: dict(c) for a, c in by_area.items()}))
