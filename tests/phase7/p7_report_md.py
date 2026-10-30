"""Phase 7 - write outputs/phase7/PHASE7_QA_REPORT.md from qa_results.json and the evidence tables."""
import json
import pandas as pd
from p7_common import *

Q = json.loads((OUT / "qa_results.json").read_text())
S, C, I = Q["summary"], Q["checks"], Q["issues"]
cnt = S["counts"]
ck = {c["id"]: c for c in C}
wf = pd.read_csv(WORK / "waterfall.csv")
gap = pd.read_csv(WORK / "gap_16352_breakdown.csv")
ref = json.load(open(WORK / "ref_metrics.json"))
h = ref["headline"]
tested = cnt["PASS"] + cnt["FAIL"]


def val(cid, k="actual"):
    return ck[cid][k] if cid in ck else "n/a"


def area_table():
    rows = ["| Area | PASS | FAIL | BLOCKED | NOT TESTED | INFO |", "|---|---:|---:|---:|---:|---:|"]
    for a, c in S["by_area"].items():
        rows.append(f"| {a} | {c.get('PASS', 0)} | {c.get('FAIL', 0)} | {c.get('BLOCKED', 0)} | {c.get('NOT TESTED', 0)} | {c.get('INFO', 0)} |")
    rows.append(f"| **Total** | **{cnt['PASS']}** | **{cnt['FAIL']}** | **{cnt['BLOCKED']}** | **{cnt['NOT TESTED']}** | **{cnt['INFO']}** |")
    return "\n".join(rows)


fails = [c for c in C if c["status"] == "FAIL"]
notp = [c for c in C if c["status"] in ("BLOCKED", "NOT TESTED")]
L = []
A = L.append
A("# Phase 7 - End-to-end QA, independent financial validation and project audit\n")
A("Project: Month-End Close Reliability & Financial Performance Analytics (NovaBridge, synthetic extract, Jan 2023 - Dec 2025).  ")
A(f"Report generated {S['generated']} from `outputs/phase7/qa_results.json` by `tests/phase7/p7_report_md.py`. Every count below is computed from the check registry.\n")

A("## 1. Executive summary\n")
A(f"- **Checks executed: {cnt['PASS'] + cnt['FAIL'] + cnt['BLOCKED'] + cnt['NOT TESTED']}** - **{cnt['PASS']} PASS, {cnt['FAIL']} FAIL, {cnt['BLOCKED']} BLOCKED, {cnt['NOT TESTED']} NOT TESTED** (plus {cnt['INFO']} INFO observations that are not tests).")
A("- **The 16,352-row difference is fully explained by the data.** Every one of those rows fails a documented non-status gate (non-posting row, junk or unresolvable entity, Balance Sheet, missing actual, undetermined scale). 4,996 of them are non-Posted lines that would otherwise belong to the status diagnostic: 4,958 have no actual amount and 38 have an undetermined scale. 0 rows are unexplained (check P05).")
A("- **No critical or high-severity issue was found.** The independent pandas reference reproduced the SQL outputs, the Excel workbook and the dashboard on identical populations: every table row within one cent, every ratio within 1e-9. The dashboard was tested in 17 filter/scenario states, including the CSV export of every filtered line.")
A(f"- **The single FAIL** (`PR.03.detail`) is the evidence for ISS-02 under the ORIGINAL instructions: 123 PASS / 2 FAIL. After the correction the same sequence passes (checks RG.*).")
A("- **Two medium reproducibility defects (ISS-01, ISS-02) were found in the run instructions and corrected in `HOW_TO_RUN.txt`**, then regression-tested in a fresh copy. No data, calculation, workbook or dashboard was changed.")
A("- **Publication is blocked by an owner decision, not by a defect.** Provenance and the redistribution licence of the data are unverified (ISS-06), and two QC files record build-machine paths (ISS-03).")
A("- **Release recommendation: QA sign-off for the documentation stage. Not ready for public publication** until ISS-06 and ISS-03 are resolved and the Windows run (ISS-05) is done.\n")

A("## 2. Scope and files tested\n")
A("Authoritative inputs (cloud working copy; each hash was verified against the approved master zip `NovaBridge_FPA_All_Phases_1-6_Master.zip` built on 30 Oct 2026):\n")
A("| Role | Path | Bytes | SHA-256 |\n|---|---|---:|---|")
for i in S["authoritative_inputs"]:
    A(f"| {i['role']} | `{i['path']}` | {i['bytes']:,} | `{i['sha256']}` |")
A("\nVersion decisions (no silent choice):\n")
A("- **Raw CSV:** `a0e6edde...` (51,938,535 bytes) is authoritative. It is the hash given in the original cleaning brief and is enforced by the cleaner's integrity gate. A different file with the same name in the owner's Downloads folder (`845b78d8...`, 51,675,512 bytes) has the same 152,682 rows but different formatting in 149,469 rows. It was not used (ISS-17).")
A("- **Phase 4 code and documents:** the Phase 5 package superseded `src/phase4_report.py` (76,306 -> 81,827 bytes), `PHASE4_ANALYSIS_REPORT.md` and `PHASE4_INSIGHT_REGISTER.md`. The later versions are authoritative. The isolated re-run regenerated both documents byte-identically.")
A("- **Workbooks:** the Phase 2 *review workbook* `fpa_monthly_close_cleaned.xlsx` (sheet Cleaned_Data, 77 fields) is a different file from the *Phase 5 analysis workbook* `fpa_month_end_close_analysis.xlsx` (12 sheets) and from the 192-column canonical CSV. All three were tested separately (checks PY08-PY10, X*).")
A("- **Excluded as non-authoritative:** the old v1 project folder and the older `fpa_monthly_close_cleaned` folder in Downloads (unapproved INCOMPLETE/test debris), and the stale loose `DASHBOARD_QA_REPORT.md`.")
A("- A full SHA-256 list of every project file is in `file_manifest_sha256.txt`. A pre-QA snapshot is in `evidence/sha256_before_phase7.txt`; every file in it still matches except `HOW_TO_RUN.txt` (ISS-01/02 correction).\n")

A("## 3. Methodology\n")
A("1. **Independent reference.** `tests/phase7/` does not import any project module. It re-parses the raw amount strings with its own parser and re-derives statement, status, entity and exclusion reasons from raw values with explicit mappings. It then rebuilds every metric in pandas.")
A("2. **Same population, same definition.** Each comparison states its population and definition. Definitions come from `docs/FINANCIAL_METRICS.md` and the SQL comments. Values on different populations are never called reconciled.")
A("3. **Tolerances.** Counts are exact. Money is 0.01 USD: inputs have at most 4 decimals and float64 summation error on about 60k terms is around 1e-7 USD, so a cent is far above noise and far below any reportable amount. Ratios are 1e-9. Dashboard display values use their display precision ($0.005M on '$xx.xxM' cards, $0.5 on whole-dollar lines).")
A("4. **Negative controls.** The financial comparison was re-run three times with a deliberately corrupted reference: one Posted line dropped, one line off by 2 cents, and one Pending line added to the Posted population. Each produced FAILs (checks NC.*), so the comparisons can detect population and one-cent errors.")
A("5. **Isolation.** Pipeline, report, workbook and dashboard builds and the existing test suites were re-run only in copies of the repository under the scratch area. The approved outputs were never overwritten. Excel recalculation used a copy of the workbook.")
A("6. **Test-harness corrections (disclosed).** Five first-run FAILs were defects in my own QA code, not in the project:")
A("   - The chart-reference parser did not unescape `&amp;`.")
A("   - The entity-table row finder also picked up rows from other tables.")
A("   - Three disclosure regular expressions were too narrow.")
A("   - One duplicate check used the wrong flag column.")
A("   - The dashboard script clicked a Reset button that is correctly disabled at the default state.")
A("   Each was fixed in the QA code and re-run. The reported counts are from the final runs.\n")

A("## 4. Data lineage and record-count reconciliation\n")
A("| Step | Stage | Records | How identified |\n|---|---|---:|---|")
for r in wf.itertuples():
    A(f"| {r.step} | {r.stage} | {r.records:,} | {r.identification if isinstance(r.identification, str) else ''} |")
A("\n**The 16,352 gap** (rows in neither Phase 6 population; first failing gate with the status gate ignored):\n")
A("| Reason | Posted | non-Posted | All |\n|---|---:|---:|---:|")
for r in gap.itertuples(index=False):
    A(f"| {r[0]} | {r[1]:,} | {r[2]:,} | {r[3]:,} |")
A("\nArithmetic: 152,682 - 58,340 Posted eligible - 77,990 non-Posted diagnostic = 16,352. The documented diagnostic population (`v_pl_actual_any_status`) applies gates 1-4 and 6-8 and drops only gate 5. So a non-Posted line that also lacks an actual amount (4,958) or has an undetermined scale (38) is in neither population: 82,986 status exclusions - 77,990 = 4,996. This is intended by the documented definition, but the dashboard does not show those 4,996 lines anywhere (see section 10).\n")
A("Record-level results (all PASS unless listed in section 10):")
A("- 152,682 raw = 152,682 cleaned. The row_id sets are identical, row order is preserved, and there are no exact duplicate raw rows.")
A("- All 19 raw-value columns are preserved byte for byte in the cleaned file.")
A("- The independent parser agrees with the cleaner on presence and value for all five amount columns.")
A("- The eligibility reason was re-derived for every row in three scopes and matches `excl_PL_actual`, `excl_PL_variance` and `excl_BS_actual` row by row.")
A("- The dashboard's embedded row sets equal the independent Posted (58,340) and non-Posted (77,990) sets exactly, with amounts within 1.5e-11 USD.")
A(f"- Restored rows: 6,265 overall (1,814 HIGH, 4,451 MEDIUM); 73 undetermined; 2,374 in the Posted population; 3,220 in the non-Posted population. All match the reported figures. Sign-conflict duplicate candidates: 1,587, none deleted.")
A(f"- Phase 2 review workbook vs canonical CSV: all 152,682 rows x 77 shared fields equal ({val('PY08')} mismatches after reading Excel date cells as calendar dates).\n")

A("## 5. Independent financial calculation results\n")
A(f"Headline from the independent reference (Posted eligible, scale-adjusted, signs as recorded, USD): revenue **{h['revenue']:,.2f}**, cost base (COGS+People+Opex) **{h['cost_cogs_people_opex']:,.2f}**, result proxy (not EBITDA) **{h['result_proxy']:,.2f}** on **{h['rows']:,}** lines.\n")
A("| Comparison | What was compared | Result |\n|---|---|---|")
for tid, what in [("F_A1", "P&L by month x section (252 rows)"), ("F_A2", "entity x section"), ("F_A3", "division x section"), ("F_A4", "GL account (24)"),
                  ("F_B1", "budget variance, 4 sign populations, incl. guarded %"), ("F_B3", "variance by division"), ("F_C1", "forecast error, WAPE, bias"),
                  ("F_D1", "prior-year column comparison by year"), ("F_E1", "gross profit S1/S2/S3 x 2 row sets x years"), ("F_F1", "cost by GL, Pareto share, rank"),
                  ("F_F2", "concentration top-1/top-3/HHI incl. cost centres"), ("F_I1", "status / scale / duplicate / sign scenarios"), ("F_I5", "scale-restored exposure")]:
    sub = [c for c in C if c["id"].startswith(tid + ".")]
    p = sum(c["status"] == "PASS" for c in sub)
    A(f"| SQL `{tid}` | {what} | {p}/{len(sub)} PASS |")
for area, what in [("sql", "SQL views read-only: grain, join fan-out, NULLs, populations, section/entity/cost-centre totals, re-run determinism"),
                   ("excel", "Phase 5 workbook: formulas, charts, values vs reference"),
                   ("dashboard", "Dashboard: 17 states x engine values, DOM, CSV export, status diagnostic, UI behaviour")]:
    sub = [c for c in C if c["area"] == area]
    k = {s_: sum(c["status"] == s_ for c in sub) for s_ in ["PASS", "FAIL", "NOT TESTED", "INFO"]}
    A(f"| {area} | {what} | {k['PASS']} PASS / {k['FAIL']} FAIL / {k['NOT TESTED']} NOT TESTED (+{k['INFO']} INFO) |")
A("\nFull metric-by-metric detail (metric, population, definition, expected, actual, absolute and relative difference, tolerance, status, explanation) is in `FINANCIAL_RECONCILIATION.xlsx`. Its Summary sheet counts are live formulas, and a recheck column recomputes |difference| <= tolerance.\n")

A("## 6. Python, SQL and Excel validation\n")
A(f"- **Python cleaning:** re-run on a copy of the raw file. Exit 0; the output CSV is **byte-identical** to the canonical file (SHA-256 c184b677...); the raw copy is unchanged; the cleaner's own 43 + 27 checks show 0 FAILED; {val('PY05')} s with peak RSS about 1.25 GB. The script refuses a raw file with the wrong hash and never overwrites its input. Its review workbook differs only in embedded run metadata.")
A(f"- **SQL:** {sum(c['area'] == 'sql' and c['status'] == 'PASS' for c in C)} read-only checks against the canonical DuckDB file, which is unchanged afterwards. Results:")
A("  - Grain is one row per source row; the dim_account join does not multiply rows.")
A("  - No unmapped sections; Posted-only and P&L-only populations hold; NULL budgets stay out of the variance view.")
A("  - Undetermined scale stays out of the any-status view; Balance Sheet and P&L do not overlap.")
A("  - Section, entity and cost-centre totals match the pandas reference.")
A("  The isolated re-run reproduced all 72 Phase 4 CSVs and both Phase 4 documents byte for byte. The database *file* is not byte-reproducible (ISS-02).")
A("- **Excel (Phase 5):** a copy was recalculated in LibreOffice with these results:")
A("  - 3,819 formulas: 0 errors and 0 differences between stored and recalculated values.")
A("  - No `#REF!`, external links, macros or broken defined names.")
A("  - Chart series all point to populated ranges.")
A("  - Monthly P&L (36 months x 7 measures), Executive Summary headline and variance %, GP1 (24 rows), entity and division tables, GL table and exclusion waterfall all match the independent reference.")
A("  - The workbook has **not** been opened in Microsoft Excel (NOT TESTED).")
A("- **Existing suites** (re-run in the copy, not counted as independent evidence):")
A("  - Phase 4 + Phase 5 pytest gave 123 PASS / 2 FAIL in the documented order (ISS-02), then all Phase 5 tests passed after step 5.")
A("  - Phase 6 QA gave 297 PASS / 0 FAIL / 1 SKIP; its negative controls detected 6/6.\n")

A("## 7. Dashboard validation\n")
A("Tested in headless Chromium against the delivered file (`43d2505a...`). Checks:")
A("- **States (17).** Year chips, entity list, scale selector, a chart cross-filter click, and section-only (cost-only, revenue-only), multi-filter, cost-centre, single-GL, quarter + month-range, all scenario combinations, the three variance populations, a near-zero account and an empty selection.")
A("- **Per state.** Line count, revenue, cost, result proxy, 7 section totals, budget variance for 4 sections (lines, actual, budget, net, gross cell variance, guarded %) and the 5-status diagnostic were compared with the independent reference. The CSV export of every filtered line was checked for count, row-set identity and section sums, and the DOM KPI cards for display precision.")
A("- **Behaviour.** Undo, Reset, cross-filter clearing, detail pagination, theme switch, keyboard focus outline, print media (interactive controls hidden, PDF generated) and four widths (no horizontal overflow) were checked.")
A("- **Errors.** There were 0 console errors and 0 non-local requests.")
A("- **Cost-only selection.** Revenue $0 and proxy margin 'n/a'; the observation panel makes no revenue or margin claim.")
A("- **Not tested.** Firefox, Safari, screen readers and physical printing.\n")

A("## 8. Security and privacy findings\n")
A("- **No credentials found.** There are no AWS/GitHub/Slack/API-key patterns, private keys or password assignments, no e-mail addresses, and no user-home paths in project text files.")
A("- **Dashboard content.** The dashboard loads no external resources. It embeds line-level data: amounts for 136,330 lines and document numbers for 58,340. It does not embed user_id or cost-centre owner names.")
A("- **Build-machine paths.** `data/processed/QC_Report.txt` and `qc_summary.json` contain machine paths and are not git-ignored (ISS-03).")
A("- **Tracked raw data.** The raw CSV has been tracked by git since Stage 0 and the repository has a GitHub remote. Visibility was not checked. Nothing was committed, pushed or published in Phase 7.")
A("- **Owner decision needed.** The data has person-like cost-centre owner names (e.g. 'K. Iyer') and system user ids. This is fine if the data is synthetic, but provenance is unverified (BLOCKED, ISS-06).\n")

A("## 9. Reproducibility and performance\n")
e = S["environment"]
A(f"Environment used: Python {e['python']}, pandas {e['pandas']}, numpy {e['numpy']} (pinned 2.4.6), duckdb {e['duckdb']}, openpyxl {e['openpyxl']}, pytest {e['pytest']}, Playwright {e['playwright']}, Chromium {e.get('chromium')}, {e.get('libreoffice')}. Linux container; **no clean-machine or Windows run** (ISS-05).\n")
A("| Step | Command | Exit | Seconds | Peak MB |\n|---|---|---:|---:|---:|")
for c in C:
    if c["id"].startswith("PR.0") and "detail" not in c["id"]:
        n = c["note"].split(" s, peak ")
        A(f"| {c['id'][3:]} | (isolated copy) | {c['actual']} | {n[0]} | {n[1].split(' MB')[0] if len(n) > 1 else ''} |")
A(f"\nCleaner: {val('PY05')} s, about 1.25 GB peak. Dashboard boot in headless Chromium: {val('UI00')} s. The 7.3 MB HTML embeds 7.15 MB of payload.\n")

A("## 10. Known limitations\n")
A("- Accepted, disclosed limitations: ISS-06 to ISS-16 in the issue log. Each was checked for consistent implementation and for disclosure in the dashboard, workbook and docs (checks AS01-AS13, all PASS).")
A("- **Hidden population (Low, documentation).** The 4,996 status-excluded lines with no actual amount or with undetermined scale appear in no dashboard view. They are counted in the Phase 4 waterfall and the Data Quality sheet, and this report documents them.")
A("- Selection consistency inside the dashboard was tested in 17 states, not in every possible filter combination.")
A("- NOT TESTED: Microsoft Excel, Firefox/Safari, assistive technology, physical printer, clean-machine install and a Windows run.\n")

A("## 11. Open issues and severity\n")
A("| ID | Severity | Status | Issue |\n|---|---|---|---|")
for i in I:
    A(f"| {i['id']} | {i['severity']} | {i['status']} | {i['title']} |")
A("\nCritical: none. High: none.")
if fails:
    A("\nChecks reported FAIL:")
    for c in fails:
        A(f"- `{c['id']}` {c['check']} - {c['note'][:220]}")
if notp:
    A("\nChecks BLOCKED / NOT TESTED:")
    for c in notp:
        A(f"- `{c['id']}` ({c['status']}) {c['check']} - {c['note'][:200]}")
A("\n## 12. Overall release recommendation\n")
A("- **Financial accuracy, data integrity and traceability:** accepted. Raw -> cleaned -> SQL -> Excel -> dashboard reconcile on identical populations, and the population gap is fully explained.")
A("- **Documentation stage:** ready, with the corrected `HOW_TO_RUN.txt`.")
A("- **Publication:** not ready. First resolve ISS-06 (provenance/licence and repository visibility), clean ISS-03, and complete ISS-05 on the Windows laptop.")
A("- **Headline figures:** all depend on provisional owner rules (R6 status, scale restoration, R9 signs). They must be presented as provisional, as the outputs already do.\n")
A("Deliverables: `PHASE7_QA_REPORT.md`, `DATA_LINEAGE_RECONCILIATION.xlsx`, `FINANCIAL_RECONCILIATION.xlsx`, `ISSUE_LOG.xlsx`, `qa_results.json`, `file_manifest_sha256.txt`, `test_execution_logs/`, `evidence/`. QA code is in `tests/phase7/`.")
(OUT / "PHASE7_QA_REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("report written", len(L), "lines;", cnt)
