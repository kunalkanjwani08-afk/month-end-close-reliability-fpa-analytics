"""Phase 7 - turn the isolated re-run evidence (cleaner re-run, full pipeline re-run, regression of the corrected
instructions, Phase 2 workbook comparison, negative controls) into registry checks."""
import json, re, sys, hashlib
from pathlib import Path
import openpyxl
from p7_common import *

R = Registry()
A = "pipeline"
SP = Path("/tmp/claude-0/-home-claude/0e9b127f-3684-54d9-aef1-b8f704472daf/scratchpad")
J = lambda p: json.loads(Path(p).read_text()) if Path(p).exists() else None

# ---- cleaner re-run on a copy of the raw file
cr = J(SP / "p7_rerun/cleaner_run.json")
if cr:
    out = SP / "p7_rerun/out"
    R.cmp("PY01", A, "Cleaner re-run (copy of raw) exits 0", 0, cr["exit"], 0, note=json.dumps(cr))
    R.cmp("PY02", A, "Cleaner re-run output CSV byte-identical to canonical cleaned CSV (SHA-256)", 1,
          int(sha256(out / "fpa_monthly_close_cleaned.csv") == CLEAN_SHA), 0, note="deterministic cleaning")
    R.cmp("PY03", A, "Raw input copy unchanged after cleaner run", 1, int(sha256(SP / "p7_rerun/in/fpa_monthly_close_raw_messy.csv") == RAW_SHA), 0)
    log = (SP / "p7_rerun/cleaner_stdout.log").read_text(errors="ignore")
    m = re.search(r"Validation: (\d+) in-memory \+ (\d+) read-back checks, (\d+) FAILED", log)
    R.cmp("PY04", A, "Cleaner's own validation + read-back checks failed (self-reported, re-run)", 0, int(m.group(3)) if m else -1, 0,
          note=m.group(0) if m else "summary line not found")
    R.add("PY05", A, "Cleaner runtime and peak memory (this container, one run)", "INFO", None, cr["seconds"], note=f"max RSS {cr['max_rss_mb']} MB")
    R.cmp("PY06", A, "Cleaner audit CSV byte-identical between delivered QC report and re-run", 1,
          int("280bf9a15951211cc557bc2501077fcae55f54a53fafb8143e6e5a916b132da0" in (out / "QC_Report.txt").read_text()), 0)
    # review workbook: content equality (not bytes: the file embeds run timestamps / paths)
    X = openpyxl.load_workbook(out / "fpa_monthly_close_cleaned.xlsx", read_only=True)
    R.add("PY07", A, "Re-run review workbook bytes differ from delivered (embedded timestamp/paths) - content compared in PY08", "INFO",
          "270edc6b...", sha256(out / "fpa_monthly_close_cleaned.xlsx")[:8] + "...")
else:
    R.add("PY01", A, "Cleaner re-run", "NOT TESTED", note="no run record")
cx = J(WORK / "cleaned_xlsx_vs_csv.json")
if cx:
    R.cmp("PY08", A, "Phase 2 review workbook 'Cleaned_Data' (77 fields) == canonical CSV values, every row and shared column", 0,
          cx["cell_mismatches"], 0, note=f"rows {cx['rows_compared']}, cols {cx['xlsx_cols']} of {cx['csv_cols']}, date cells normalised {cx['date_cells_normalised']}")
    R.cmp("PY09", A, "Review workbook columns all exist in the 192-column CSV (subset, not a different schema)", 0, len(cx["cols_not_in_csv"]), 0)
    R.cmp("PY10", A, "Review workbook row count == CSV row count", 0, cx["leftover_rows"], 0)

# ---- full pipeline re-run in an isolated copy
L = SP / "p7_rerun_logs"
steps = {p.stem: J(p) for p in sorted(L.glob("*.json"))}
for name, s in steps.items():
    if not s: continue
    if name == "03_pytest_phase4_phase5":   # evaluated in PR.03.detail (one defect -> one FAIL)
        R.add(f"PR.{name}", A, f"Isolated re-run step {name}: exit code recorded (assessed in PR.03.detail)", "INFO", 0, s["exit"],
              note=f"{s['seconds']} s, peak {s['max_rss_mb']} MB")
        continue
    R.add(f"PR.{name}", A, f"Isolated re-run step {name}: exit 0", "PASS" if s["exit"] == 0 else "FAIL", 0, s["exit"], tolerance=0,
          note=f"{s['seconds']} s, peak {s['max_rss_mb']} MB")
t3 = (L / "03_pytest_phase4_phase5.log").read_text(errors="ignore") if (L / "03_pytest_phase4_phase5.log").exists() else ""
m = re.search(r"PASS: (\d+)\s+FAIL: (\d+)\s+SKIP: (\d+)", t3)
if m:
    R.add("PR.03.detail", A, "Documented step 4 (pytest tests) right after a DB rebuild, ORIGINAL instructions (before the ISS-02 correction): PASS/FAIL/SKIP", "FAIL" if int(m.group(2)) else "PASS",
          "0 FAIL", f"{m.group(1)} PASS / {m.group(2)} FAIL / {m.group(3)} SKIP",
          note="FAILED: test_lineage_and_source_identity_recorded, test_manifest_matches_the_saved_workbook_and_inputs - DB SHA-256 changed on rebuild (ISS-02)")
t5 = (L / "05_pytest_phase5.log").read_text(errors="ignore") if (L / "05_pytest_phase5.log").exists() else ""
m = re.search(r"PASS: (\d+)\s+FAIL: (\d+)\s+SKIP: (\d+)", t5)
if m:
    R.add("PR.05.detail", A, "Phase 5 tests after the workbook is regenerated: PASS/FAIL/SKIP", "PASS" if int(m.group(2)) == 0 else "FAIL",
          "0 FAIL", f"{m.group(1)} PASS / {m.group(2)} FAIL / {m.group(3)} SKIP")
C = SP / "p7_repo_copy"
if (C / "data/processed/phase4_fpa.duckdb").exists():
    R.add("PR.db", A, "Rebuilt DuckDB SHA-256 differs from canonical (file not byte-reproducible; content checked via outputs)", "INFO",
          "00e74376...", sha256(C / "data/processed/phase4_fpa.duckdb")[:8] + "...")
# rebuilt dashboard vs delivered: identical except the embedded provenance hashes
nh = C / "outputs/phase6/fpa_financial_analytics_dashboard.html"
if nh.exists():
    a = HTML.read_text(encoding="utf-8"); b = nh.read_text(encoding="utf-8")
    norm = lambda t: re.sub(r'"(db|xlsx)_sha256":"[0-9a-f]{64}"', '"X":"H"', t)
    R.cmp("PR.html", A, "Rebuilt dashboard HTML identical to delivered apart from the embedded DB/workbook hashes", 1, int(norm(a) == norm(b)), 0,
          note="byte-identical: " + str(a == b))
nx = C / "outputs/phase5/fpa_month_end_close_analysis.xlsx"
if nx.exists():
    o = openpyxl.load_workbook(XLSX, data_only=True); n = openpyxl.load_workbook(nx, data_only=True)
    diff = []
    for ws in o.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v2 = n[ws.title][c.coordinate].value
                if c.value != v2 and not (isinstance(c.value, float) and isinstance(v2, float) and abs(c.value - v2) <= 1e-9 * max(1, abs(c.value))):
                    diff.append((ws.title, c.coordinate, str(c.value), str(v2)))
    meta = lambda v: bool(re.fullmatch(r"[0-9a-f]{64}", v) or re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:]+Z?", v))
    other = [d for d in diff if not (meta(d[2]) and meta(d[3]))]
    R.cmp("PR.xlsx", A, "Rebuilt Phase 5 workbook: cell values identical to delivered except recorded hashes/timestamps", 0, len(other), 0,
          note=f"{len(diff)} differing cells in total, all SHA-256/timestamp metadata: " + json.dumps([(d[0], d[1], d[2][:16], d[3][:16]) for d in diff][:8]) + " | other: " + json.dumps(other[:5]))
p6 = C / "outputs/phase6/qa_results.json"
if p6.exists() and (L / "08_phase6_qa.json").exists():
    q = json.loads(p6.read_text()); from collections import Counter
    c = Counter(r["status"] for r in q["results"])
    R.add("PR.p6qa", A, "Phase 6 QA suite re-run in the copy (existing suite, not independent): PASS/FAIL/SKIP",
          "PASS" if c.get("FAIL", 0) == 0 else "FAIL", "0 FAIL", f"{c.get('PASS', 0)} PASS / {c.get('FAIL', 0)} FAIL / {len(q.get('skips', []))} SKIP",
          note="; ".join(f"{r['area']}: {r['test']}" for r in q["results"] if r["status"] == "FAIL")[:600])
nc = C / "outputs/phase6/negative_controls.json"
if nc.exists() and (L / "09_phase6_negative_controls.json").exists():
    n = json.loads(nc.read_text())
    R.cmp("PR.p6nc", A, "Phase 6 negative controls re-run: re-introduced defects detected", len(n), sum(1 for x in n if x["defect_detected_by_check"]), 0)
# ---- regression of the corrected HOW_TO_RUN (fresh copy without cleaned CSV / DB)
G = SP / "p7_regression_logs"
if (G / "06_pytest_phase5.json").exists():
    for p in sorted(G.glob("0*.json")):
        s = J(p)
        R.add(f"RG.{p.stem}", A, f"Corrected-instructions regression step {p.stem}: exit 0", "PASS" if s["exit"] == 0 else "FAIL", 0, s["exit"],
              note=f"{s['seconds']} s, peak {s['max_rss_mb']} MB")
    sh = (G / "01_clean_sha.txt").read_text().split()[0] if (G / "01_clean_sha.txt").exists() else ""
    R.cmp("RG.sha", A, "Corrected step 0 writes the canonical cleaned CSV into data/processed (SHA-256 match)", 1, int(sh == CLEAN_SHA), 0)
else:
    R.add("RG", A, "Regression of corrected instructions", "NOT TESTED", note="regression run not finished")
# ---- negative controls of the independent reference itself
for m in ["drop_row", "cent", "status"]:
    f = WORK / f"checks_financial_sql_mutant_{m}.json"
    if f.exists():
        rows = json.loads(f.read_text())
        nf = sum(1 for r in rows if r["status"] == "FAIL")
        R.add(f"NC.{m}", A, f"Negative control '{m}': deliberately corrupted reference must produce FAILs", "PASS" if nf > 0 else "FAIL",
              ">0 FAIL", nf)
R.add("ENV.clean_machine", A, "Clean-machine reproduction (fresh OS + pip install -r requirements.txt)", "NOT TESTED",
      note="Re-runs used this container's existing Python 3.13.16 / pandas 3.0.5 / numpy 2.5.3 (pinned 2.4.6) / duckdb 2.0.0 / openpyxl 3.1.5 / pytest 9.2.0; no venv install, no Windows run")
R.save("pipeline")
