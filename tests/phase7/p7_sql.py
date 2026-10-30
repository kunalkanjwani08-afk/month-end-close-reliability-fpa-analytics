"""Phase 7 - SQL layer checks executed READ-ONLY against the canonical DuckDB database, reconciled to the
independent pandas reference; plus determinism of the isolated pipeline re-run (copy of the repository)."""
import json, sys
from pathlib import Path
import duckdb
import pandas as pd
from p7_common import *

R = Registry()
A = "sql"
h0 = sha256(DB)
R.cmp("S00", A, "Canonical DuckDB SHA-256 equals the hash recorded in Phase 6 payload", 1,
      int(h0 == "00e7437697c8e11baab5d2cff7036d6dda3d251a139774adee0a2dfe92c413e6"), 0)
con = duckdb.connect(str(DB), read_only=True)
q = lambda s: con.execute(s).fetchall()
L = pd.read_pickle(WORK / "ref_lines.pkl")
P = L[L.posted]
R.cmp("S01", A, "fact_close rows", 152682, q("select count(*) from fact_close")[0][0], 0)
R.cmp("S02", A, "fact_close columns", 192, len(q("describe fact_close")), 0)
R.cmp("S03", A, "fact_close row_id unique (grain = one source row)", 0, q("select count(*) - count(distinct row_id) from fact_close")[0][0], 0)
R.cmp("S04", A, "v_close row count = fact_close (LEFT JOIN to dim_account does not multiply rows)", 152682, q("select count(*) from v_close")[0][0], 0)
R.cmp("S05", A, "dim_account has one row per GL account", 0, q("select count(*) - count(distinct gl_account) from dim_account")[0][0], 0)
R.cmp("S06", A, "Posting rows with a GL but no section (unmapped account_group -> NULL section)", 0,
      q("select count(*) from v_close where is_posting_row = 1 and gl_account is not null and section is null")[0][0], 0)
R.cmp("S07", A, "v_pl_actual rows", 58340, q("select count(*) from v_pl_actual")[0][0], 0)
R.cmp("S08", A, "v_pl_actual_any_status rows", 136330, q("select count(*) from v_pl_actual_any_status")[0][0], 0)
R.cmp("S09", A, "v_pl_actual contains only Posted status", 0, q("select count(*) from v_pl_actual where status_group <> 'Posted'")[0][0], 0)
R.cmp("S10", A, "v_pl_actual contains no Balance Sheet rows", 0, q("select count(*) from v_pl_actual where statement <> 'P&L'")[0][0], 0)
R.cmp("S11", A, "v_pl_actual rows with NULL actual_usd_adj", 0, q("select count(*) from v_pl_actual where actual_usd_adj is null")[0][0], 0)
R.cmp("S12", A, "v_pl_actual_any_status rows with undetermined scale (gate 8 must hold without the status gate)", 0,
      q("select count(*) from v_pl_actual_any_status where scale_decision = 'UNDETERMINED'")[0][0], 0,
      note="the view has no explicit scale condition; undetermined rows have NULL actual_usd_adj, so 'actual_usd_adj IS NOT NULL' enforces gate 8")
R.add("S13", A, "status_group values in any-status view", "INFO", None, None,
      note=json.dumps(dict(q("select status_group, count(*) from v_pl_actual_any_status group by 1 order by 1"))))
R.cmp("S14", A, "Set of row_ids in v_pl_actual == independent Posted eligible set", 0,
      len(set(r[0] for r in q("select source_row_number from v_pl_actual")) ^ set(P.srn)), 0)
sec_sql = dict(q("select section, sum(actual_usd_adj) from v_pl_actual group by 1"))
sec_ref = P.groupby("sec").a.sum().to_dict()
for s in sorted(sec_ref):
    R.cmp(f"S15.{s}", A, f"SQL sum(actual_usd_adj) section {s} == pandas reference", sec_ref[s], sec_sql.get(s), TOL_USD)
ent_sql = {(e, s): v for e, s, v in q("select entity_code, section, sum(actual_usd_adj) from v_pl_actual group by 1,2")}
ent_ref = P.groupby(["e", "sec"]).a.sum().to_dict()
bad = sum(1 for k in ent_ref if abs(ent_ref[k] - ent_sql.get(k, 1e18)) > TOL_USD) + len(set(ent_sql) ^ set(ent_ref))
R.cmp("S16", A, "SQL entity x section actual == pandas reference (all cells)", 0, bad, 0)
cc_sql = {k: v for k, v in q("select coalesce(cost_center_code,'(blank)'), sum(abs(actual_usd_adj)) from v_pl_actual where section in ('PEOPLE','OPEX') group by 1")}
cc_ref = pd.read_csv(WORK / "ref_cost_centre.csv", keep_default_na=False).set_index("cc").abs_usd.to_dict()
bad = sum(1 for k in cc_ref if abs(cc_ref[k] - cc_sql.get(k, 1e18)) > TOL_USD) + len(set(cc_sql) ^ set(cc_ref))
R.cmp("S17", A, "SQL cost-centre absolute activity (people + opex) == pandas reference", 0, bad, 0, note=json.dumps({k: round(v, 2) for k, v in cc_sql.items()}))
pm = dict(q("select period_ym, count(*) from v_pl_actual group by 1"))
R.cmp("S18", A, "SQL months with eligible lines", 36, len(pm), 0)
R.cmp("S19", A, "SQL budget population (v_pl_budget)", 55043, q("select count(*) from v_pl_budget")[0][0], 0)
R.cmp("S20", A, "v_pl_budget rows with NULL budget (NULL handling)", 0, q("select count(*) from v_pl_budget where budget_usd_adj is null")[0][0], 0)
R.cmp("S21", A, "Balance Sheet view never mixed into P&L: overlap of v_bs_actual and v_pl_actual", 0,
      q("select count(*) from v_bs_actual b join v_pl_actual p using (row_id)")[0][0], 0)
R.cmp("S22", A, "safe_pct returns NULL when |net| < 50% of gross (macro behaviour)", 1,
      int(q("select safe_pct(10, 10, 100) is null and safe_pct(10, 60, 100) = 10/60.0")[0][0]), 0)
con.close()
R.cmp("S23", A, "Canonical DuckDB unchanged after read-only queries", 1, int(sha256(DB) == h0), 0)

# ---- isolated re-run (copy of repo) determinism, if available
copy = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if copy and (copy / "outputs/phase4/MANIFEST.json").exists():
    import hashlib
    orig = json.loads((ROOT / "outputs/phase4/MANIFEST.json").read_text())
    new = json.loads((copy / "outputs/phase4/MANIFEST.json").read_text())
    def files(m):
        f = m.get("files") or m.get("outputs") or m
        if isinstance(f, dict): return {k: (v.get("sha256") if isinstance(v, dict) else v) for k, v in f.items()}
        return {x.get("file", x.get("name")): x.get("sha256") for x in f}
    fo, fn = files(orig), files(new)
    diff = [k for k in set(fo) | set(fn) if fo.get(k) != fn.get(k)]
    R.cmp("S30", A, "Isolated pipeline re-run: Phase 4 output CSV hashes identical to the delivered MANIFEST", 0, len(diff), 0,
          note=json.dumps(diff[:10]))
    csvs = sorted((ROOT / "outputs/phase4").glob("*.csv"))
    bad = [c.name for c in csvs if sha256(c) != sha256(copy / "outputs/phase4" / c.name)]
    R.cmp("S31", A, "Isolated re-run: every outputs/phase4/*.csv byte-identical to delivered", 0, len(bad), 0, note=json.dumps(bad[:10]))
    for d in ["PHASE4_ANALYSIS_REPORT.md", "PHASE4_INSIGHT_REGISTER.md"]:
        R.cmp(f"S32.{d}", A, f"Isolated re-run: docs/{d} regenerated identically", 1,
              int(sha256(ROOT / "docs" / d) == sha256(copy / "docs" / d)), 0)
else:
    R.add("S30", A, "Isolated pipeline re-run determinism", "NOT TESTED", note="copy not supplied")
R.save("sql")
