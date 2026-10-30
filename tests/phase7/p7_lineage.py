"""Phase 7 - record lineage, independent parsing/scale checks, eligibility re-derivation and the
record-count waterfall (including the 16,352-row gap between the cleaned file and the Phase 6 payload).

Independence: amounts are re-parsed from the RAW strings with p7_common.parse_amount; statement, status and
entity rules are re-derived from RAW values with explicit mappings written here; the cleaned file's
eligibility flags are only used as the thing under test. The dashboard payload is extracted from the HTML
file itself, not from the build script.
"""
import json, re, sys, time
from collections import Counter
import numpy as np
import pandas as pd
from p7_common import *

t0 = time.time()
R = Registry()
A = "lineage"

# ---------------------------------------------------------------- 0. inputs and hashes
R.cmp("L00", A, "Raw CSV SHA-256 equals approved hash", 1, int(sha256(RAW) == RAW_SHA), 0,
      note=f"approved {RAW_SHA}")
R.cmp("L01", A, "Cleaned CSV SHA-256 equals approved hash", 1, int(sha256(CLEAN) == CLEAN_SHA), 0,
      note=f"approved {CLEAN_SHA}")

raw = pd.read_csv(RAW, dtype=str, keep_default_na=False, encoding="utf-8")
cl = pd.read_csv(CLEAN, dtype=str, keep_default_na=False, encoding="utf-8-sig")
R.cmp("L02", A, "Raw rows", 152682, len(raw), 0, definition="data rows excl. header")
R.cmp("L03", A, "Raw columns", 43, raw.shape[1], 0)
R.cmp("L04", A, "Cleaned rows", 152682, len(cl), 0)
R.cmp("L05", A, "Cleaned columns", 192, cl.shape[1], 0)
R.cmp("L06", A, "Raw row_id unique", len(raw), raw.row_id.nunique(), 0)
R.cmp("L07", A, "Cleaned row_id unique", len(cl), cl.row_id.nunique(), 0)
R.cmp("L08", A, "Raw row_id set == cleaned row_id set (no row lost or added)", 0,
      len(set(raw.row_id) ^ set(cl.row_id)), 0, definition="symmetric difference of the two id sets")
srn = pd.to_numeric(cl.source_row_number)
R.cmp("L09", A, "source_row_number = raw file line (row order preserved, 2..152683)", 0,
      int((srn.values != np.arange(2, len(cl) + 2)).sum()), 0)
R.cmp("L10", A, "row_id at the same position in raw and cleaned", 0, int((raw.row_id.values != cl.row_id.values).sum()), 0)
R.cmp("L11", A, "Exact duplicate rows in raw (all 43 columns)", 0, int(raw.duplicated().sum()), 0,
      note="0 means no fully identical raw records; duplicate CANDIDATES are a separate, unresolved topic")
blank_cols = [c for c in cl.columns if (cl[c] == "").all()]
R.add("L12", A, "Cleaned columns that are entirely blank", "INFO", None, len(blank_cols), note=", ".join(blank_cols)[:300])

# raw value preservation: every raw column must survive unchanged in the cleaned file (as <col>_raw or <col>)
pres = []
for c in raw.columns:
    tgt = c if c.endswith("_raw") else (c + "_raw" if c + "_raw" in cl.columns else c)
    if c == "report_scale":
        tgt = "report_scale_raw"
    if c == "fiscal_period":
        tgt = "fiscal_period_raw"
    if c == "posting_date":
        tgt = "posting_date_raw"
    if tgt not in cl.columns:
        pres.append((c, tgt, None, "target column missing")); continue
    diff = int((raw[c].values != cl[tgt].values).sum())
    pres.append((c, tgt, diff, ""))
pd.DataFrame(pres, columns=["raw_column", "cleaned_column", "rows_differing", "note"]).to_csv(WORK / "raw_preservation.csv", index=False)
raw_named = [p for p in pres if p[1].endswith("_raw") or p[0] in ("row_id", "document_no")]
for c, tgt, diff, note in raw_named:
    R.cmp(f"L13.{c}", A, f"Raw value preserved byte-for-byte: {c} -> {tgt}", 0, diff if diff is not None else -1, 0,
          note=note)
changed = [p for p in pres if p not in raw_named]
R.add("L14", A, "Cleaned (normalised) columns: rows whose value differs from raw", "INFO", None,
      sum(p[2] or 0 for p in changed), note="; ".join(f"{p[0]}:{p[2]}" for p in changed)[:900],
      evidence="evidence/work/raw_preservation.csv")

# ---------------------------------------------------------------- 1. independent amount parsing
AMT = ["amount_local", "actual_usd", "budget_usd", "forecast_usd", "prior_year_usd"]
ref = pd.DataFrame({"row_id": raw.row_id.values, "srn": srn.values})
fmt_counts = {}
for a in AMT:
    vals, cls = zip(*(parse_amount(s) for s in raw[a + "_raw"]))
    v = pd.Series([np.nan if x is None else x for x in vals], dtype=float)
    ref[a + "_p"] = v.values
    fmt_counts[a] = Counter(cls)
    cp = pd.to_numeric(cl[a + "_parsed"].replace("", np.nan))
    both = v.notna() & cp.notna()
    miss_mismatch = int((v.isna() != cp.isna()).sum())
    val_mismatch = int((both & ((v - cp).abs() > 1e-9)).sum())
    R.cmp(f"L20.{a}", A, f"Independent raw parse of {a}: missing/placeholder agreement", 0, miss_mismatch, 0,
          definition="placeholders ###, #N/A, NA, N/A, n/a, null, -, blank -> missing")
    R.cmp(f"L21.{a}", A, f"Independent raw parse of {a}: value agreement (|diff| <= 1e-9)", 0, val_mismatch, 0,
          definition="US 1,234.56 / EU 1.234,56 / decimal comma 54,78 / thousands comma 4,579 / ($) / parentheses negative")
    R.add(f"L22.{a}", A, f"Ambiguous 'n,nnn' strings in {a} read as thousands (not 3-dp decimal comma)", "INFO", None,
          fmt_counts[a].get("comma_thousands_ambiguous", 0),
          note="Same reading as the cleaner. The alternative reading would shrink each value 1000x; no field in the "
               "data can settle it. Accepted limitation (disclosed).")
pd.DataFrame(fmt_counts).fillna(0).astype(int).to_csv(WORK / "amount_format_counts.csv")

# ---------------------------------------------------------------- 2. scale restoration
fac = pd.to_numeric(cl.scale_factor_applied.replace("", np.nan))
dec = cl.scale_decision
exp_fac = dec.map({"UNDIVIDED": 1.0, "DIVIDED_1E3": 1e3, "DIVIDED_1E5": 1e5})
R.cmp("L30", A, "scale_factor_applied consistent with scale_decision (1 / 1e3 / 1e5; blank otherwise)", 0,
      int(((fac != exp_fac) & ~(fac.isna() & exp_fac.isna())).sum()), 0)
for a in AMT[1:] + ["amount_local"]:
    adj = pd.to_numeric(cl[a + "_adj"].replace("", np.nan))
    expv = ref[a + "_p"] * fac
    bad = int((~((adj - expv).abs() <= 1e-6 * np.maximum(1, expv.abs())) & ~(adj.isna() & expv.isna())).sum())
    R.cmp(f"L31.{a}", A, f"{a}_adj == independently parsed raw x scale factor", 0, bad, 0,
          definition="rows with a scale decision; undetermined/non-posting rows must be blank")
restored = fac.notna() & (fac != 1)
R.cmp("L32", A, "Scale-restored rows (all 152,682 rows)", 6265, int(restored.sum()), 0, note="previously reported 6,265")
R.cmp("L33", A, "Restored rows with HIGH confidence", 1814, int((restored & (cl.scale_confidence == "HIGH")).sum()), 0)
R.cmp("L34", A, "Restored rows with MEDIUM confidence", 4451, int((restored & (cl.scale_confidence == "MEDIUM")).sum()), 0)
R.cmp("L35", A, "Undetermined-scale rows", 73, int((dec == "UNDETERMINED").sum()), 0)
lbl = raw.report_scale.str.strip()
R.add("L36", A, "Restorations by raw report_scale label", "INFO", None, int(restored.sum()),
      note=json.dumps(pd.crosstab(lbl[restored], dec[restored]).to_dict()))

# ---------------------------------------------------------------- 3. independent eligibility re-derivation
PL = {"P&L", "PL", "IS", "Income statement", "Profit & Loss"}
BS = {"Balance Sheet", "BS", "Statement of position", "B/S"}
st_raw = raw.statement.str.strip()
R.cmp("L40", A, "Every raw statement label maps to P&L or BS by the explicit list", 0,
      int((~st_raw.isin(PL | BS)).sum()), 0)
ref["is_pl"] = st_raw.isin(PL).values
R.cmp("L41", A, "Cleaned statement agrees with independent mapping", 0,
      int(((cl.statement == "P&L").values != ref.is_pl.values).sum()), 0)
nonpost = raw.notes.str.strip().str.lower().eq("subtotal row")
R.cmp("L42", A, "Non-posting rows (notes = 'subtotal row')", 350, int(nonpost.sum()), 0)
R.cmp("L43", A, "Cleaned is_posting_row agrees with notes rule", 0, int(((cl.is_posting_row == "0").values != nonpost.values).sum()), 0)
VALID = {"GB01", "SG01", "DE01", "IN01", "AE01", "US01"}
code = raw.entity_code.str.strip().str.upper()
name = raw.legal_entity.str.strip().str.lower()
junk = code.isin({"T999", "99"}) | name.isin({"test entity", "do not use", "xxx"})
resolved = code.isin(VALID) & ~junk
R.add("L44", A, "Raw legal_entity values of blank-code rows (independent view)", "INFO", None,
      int((code == "").sum()), note=json.dumps(name[code == ""].value_counts().to_dict())[:600])
# blank-code rows may be resolved by name in the cleaner; accept cleaned code only when the raw name is a known entity name
name_map = (pd.DataFrame({"n": name[resolved], "c": code[resolved]}).drop_duplicates().groupby("n").c.agg(lambda s: set(s)))
uni = {n: next(iter(c)) for n, c in name_map.items() if len(c) == 1}
by_name = (code == "") & ~junk & name.map(lambda n: n in uni)
ent_ok = resolved | by_name
ent_code = np.where(resolved, code, np.where(by_name, name.map(uni), ""))
R.cmp("L45", A, "Junk-entity rows (code T999/99 or name TEST ENTITY/Do not use/xxx)", 204,
      int((junk & ~nonpost).sum() + (junk & nonpost).sum()), 0)
R.cmp("L46", A, "Cleaned entity_code agrees with independent resolution on resolvable rows", 0,
      int(((cl.entity_code.values != ent_code) & ent_ok.values).sum()), 0)
status = raw.approval_status.str.strip()
posted = status.eq("Posted")
per_ok = cl.period_ym.ne("")

def primary(amount_present, scale_ok, scope_pl):
    r = np.full(len(raw), "ELIGIBLE", dtype=object)
    conds = [("1_NON_POSTING_ROW", nonpost.values),
             ("2_JUNK_ENTITY", junk.values),
             ("3_ENTITY_UNRESOLVABLE", ~ent_ok.values),
             ("4_OUT_OF_SCOPE_STATEMENT", (~ref.is_pl.values) if scope_pl else ref.is_pl.values),
             ("5_STATUS_NOT_ELIGIBLE", ~posted.values),
             ("6_PERIOD_UNRESOLVABLE", ~per_ok.values),
             ("7_AMOUNT_MISSING", ~amount_present),
             ("8_SCALE_UNDECIDABLE", ~scale_ok)]
    done = np.zeros(len(raw), bool)
    for lab, c in conds:
        m = c & ~done
        r[m] = lab
        done |= m
    return r

scale_ok = (dec != "UNDETERMINED").values
act = ref.actual_usd_p.notna().values
bud = ref.budget_usd_p.notna().values
ref["pr_pl_actual"] = primary(act, scale_ok, True)
ref["pr_pl_variance"] = primary(act & bud, scale_ok, True)
ref["pr_bs_actual"] = primary(act, scale_ok, False)
for scope, col in [("pl_actual", "excl_PL_actual"), ("pl_variance", "excl_PL_variance"), ("bs_actual", "excl_BS_actual")]:
    mism = int((ref["pr_" + scope].values != cl[col].values).sum())
    R.cmp(f"L47.{scope}", A, f"Independent primary exclusion reason == {col} (row by row)", 0, mism, 0,
          definition="precedence 1 non-posting, 2 junk, 3 entity, 4 statement, 5 status, 6 period, 7 amount, 8 scale")
    cnt = Counter(ref["pr_" + scope])
    R.cmp(f"L48.{scope}", A, f"{scope}: eligible + all exclusions = 152,682", 152682, sum(cnt.values()), 0)
    elig_flag = {"pl_actual": "eligible_PL_actual", "pl_variance": "eligible_PL_variance", "bs_actual": "eligible_BS_actual"}[scope]
    R.cmp(f"L49.{scope}", A, f"{elig_flag} flag == (reason == ELIGIBLE)", 0,
          int(((cl[elig_flag] == "1").values != (cl[col] == "ELIGIBLE").values).sum()), 0)

# ---------------------------------------------------------------- 4. Phase 6 populations and the 16,352 gap
ref["section_ok"] = True
pr = ref.pr_pl_actual
posted_elig = pr.eq("ELIGIBLE")
# any-status population as DOCUMENTED: steps 1-4 and 6-8 pass, step 5 ignored
any_status_doc = primary(act, scale_ok, True)  # recompute ignoring status below
steps_wo5 = (~nonpost.values) & (~junk.values) & ent_ok.values & ref.is_pl.values & per_ok.values & act & scale_ok
nonposted_doc = steps_wo5 & ~posted.values
R.cmp("P01", A, "Posted eligible P&L lines (Phase 6 main population)", 58340, int(posted_elig.sum()), 0)
R.cmp("P02", A, "Non-Posted lines passing steps 1-4 and 6-8 (Phase 6 diagnostic population, documented definition)",
      77990, int(nonposted_doc.sum()), 0)
R.cmp("P03", A, "Posted eligible + non-Posted diagnostic", 136330, int(posted_elig.sum() + nonposted_doc.sum()), 0)

gap = ~(posted_elig.values | nonposted_doc)
R.cmp("P04", A, "Rows in cleaned file but in neither Phase 6 population", 16352, int(gap.sum()), 0)
gap_reason = pd.Series(np.where(nonpost.values, "1_NON_POSTING_ROW", np.where(junk.values, "2_JUNK_ENTITY",
             np.where(~ent_ok.values, "3_ENTITY_UNRESOLVABLE", np.where(~ref.is_pl.values, "4_OUT_OF_SCOPE_STATEMENT (Balance Sheet)",
             np.where(~per_ok.values, "6_PERIOD_UNRESOLVABLE", np.where(~act, "7_AMOUNT_MISSING (actual)",
             np.where(~scale_ok, "8_SCALE_UNDECIDABLE", "UNEXPLAINED"))))))))[gap]
gstat = pd.Series(np.where(posted.values, "Posted", "non-Posted"))[gap]
gtab = pd.crosstab(gap_reason, gstat, margins=True)
gtab.to_csv(WORK / "gap_16352_breakdown.csv")
R.cmp("P05", A, "Gap rows with no explaining rule (UNEXPLAINED)", 0, int((gap_reason == "UNEXPLAINED").sum()), 0,
      evidence="evidence/work/gap_16352_breakdown.csv")
R.add("P06", A, "16,352 gap decomposition (reason x status)", "INFO", None, int(gap.sum()), note=gtab.to_json())

# Phase 6 restored counts
R.cmp("P07", A, "Restored rows in Posted eligible population", 2374, int((restored.values & posted_elig.values).sum()), 0)
R.cmp("P08", A, "Restored rows in non-Posted diagnostic population", 3220, int((restored.values & nonposted_doc).sum()), 0)
st_lab = status.replace({"pending": "Pending", "": "(blank)"})
R.add("P09", A, "Non-Posted diagnostic by status", "INFO", None, int(nonposted_doc.sum()),
      note=json.dumps(st_lab[nonposted_doc].value_counts().to_dict()))

# ---------------------------------------------------------------- 5. dashboard payload membership (from the HTML itself)
html = HTML.read_text(encoding="utf-8")
m = re.search(r"const DATA=(\{.*?\});\s*\n", html, re.S)
if not m:
    R.add("P10", A, "Extract payload from dashboard HTML", "BLOCKED", note="payload pattern not found")
else:
    data = json.loads(m.group(1).replace("<\\/", "</"))
    json.dump({"meta": data["meta"], "n_R": len(data["R"]["src"]), "n_X": len(data["X"]["src"])}, open(WORK / "payload_meta.json", "w"), indent=1)
    rs = set(data["R"]["src"]); xs = set(data["X"]["src"])
    exp_r = set(srn[posted_elig.values]); exp_x = set(srn[nonposted_doc])
    R.cmp("P10", A, "Dashboard Posted payload row set == independent Posted eligible set", 0, len(rs ^ exp_r), 0,
          definition="symmetric difference of source_row_number sets")
    R.cmp("P11", A, "Dashboard non-Posted payload row set == independent non-Posted diagnostic set", 0, len(xs ^ exp_x), 0)
    R.cmp("P12", A, "Posted and non-Posted payload sets do not overlap", 0, len(rs & xs), 0)
    # payload amounts vs independent amounts
    ia = pd.Series(ref.actual_usd_p.values * fac.values, index=srn.values)
    pa = pd.Series(data["R"]["a"], index=data["R"]["src"], dtype=float)
    R.cmp("P13", A, "Payload Posted actual (scale-adjusted) == independent parse x factor, max |diff|", 0.0,
          float((pa - ia.loc[pa.index]).abs().max()), 1e-6)
    xa = pd.Series(data["X"]["a"], index=data["X"]["src"], dtype=float)
    R.cmp("P14", A, "Payload non-Posted actual == independent, max |diff|", 0.0, float((xa - ia.loc[xa.index]).abs().max()), 1e-6)
    for k, col in [("b", "budget_usd_p"), ("f", "forecast_usd_p"), ("p", "prior_year_usd_p")]:
        iv = pd.Series(ref[col].values * fac.values, index=srn.values).loc[data["R"]["src"]]
        pv = pd.Series([np.nan if x is None else x for x in data["R"][k]], index=data["R"]["src"], dtype=float)
        nn = int((iv.isna() != pv.isna()).sum())
        mx = float((pv - iv).abs().max())
        R.cmp(f"P15.{k}", A, f"Payload {col[:-2]} presence and value == independent (missing mismatches)", 0, nn, 0,
              note=f"max |diff| {mx}")
    st_ix = {1: "Pending", 2: "Parked", 3: "Rejected", 4: "(blank)"}
    ps = pd.Series([st_ix[s] for s in data["X"]["st"]], index=data["X"]["src"])
    R.cmp("P16", A, "Payload non-Posted status label == raw approval_status (row by row)", 0,
          int((ps.values != st_lab.set_axis(srn.values).loc[ps.index].values).sum()), 0)
    rsr = pd.Series(data["R"]["rs"], index=data["R"]["src"])
    R.cmp("P17", A, "Payload restored marker count (Posted)", int((restored.values & posted_elig.values).sum()), int((rsr > 0).sum()), 0)
    R.add("P18", A, "Payload meta as embedded", "INFO", None, None, note=json.dumps(data["meta"])[:900])

# ---------------------------------------------------------------- 6. waterfall table
wf = []
wf.append(("W00", "Raw records", len(raw), "raw CSV data rows", "len(raw)"))
wf.append(("W01", "Cleaned records (1:1 with raw, no row dropped)", len(cl), "cleaned CSV rows", "L08/L09"))
c = Counter(ref.pr_pl_actual)
running = len(cl)
for k in ["1_NON_POSTING_ROW", "2_JUNK_ENTITY", "3_ENTITY_UNRESOLVABLE", "4_OUT_OF_SCOPE_STATEMENT", "5_STATUS_NOT_ELIGIBLE",
          "6_PERIOD_UNRESOLVABLE", "7_AMOUNT_MISSING", "8_SCALE_UNDECIDABLE"]:
    running -= c.get(k, 0)
    wf.append((f"W1{k[0]}", f"less {k}", -c.get(k, 0), f"remaining {running:,}", f"excl_PL_actual == '{k}' (independently re-derived, L47)"))
wf.append(("W20", "= Posted eligible P&L lines (dashboard main payload, SQL v_pl_actual)", int(posted_elig.sum()), "", "eligible_PL_actual = 1"))
st5 = (pr == "5_STATUS_NOT_ELIGIBLE").values
wf.append(("W30", "Step-5 (status) exclusions", int(st5.sum()), "", "excl_PL_actual == 5"))
wf.append(("W31", "  of which also pass steps 6-8 -> non-Posted diagnostic payload", int((st5 & nonposted_doc).sum()), "", "v_pl_actual_any_status, status <> Posted"))
wf.append(("W32", "  of which fail step 7 (actual missing) as well -> in NO payload", int((st5 & ~act).sum()), "", "status excl. AND actual missing"))
wf.append(("W33", "  of which fail step 8 (scale undetermined) only -> in NO payload", int((st5 & act & ~scale_ok).sum()), "", ""))
wf.append(("W40", "Combined Phase 6 payload", int(posted_elig.sum() + nonposted_doc.sum()), "", "P03"))
wf.append(("W41", "Not in any Phase 6 payload", int(gap.sum()), "", "P04 / gap_16352_breakdown.csv"))
cv = Counter(ref.pr_pl_variance)
wf.append(("W50", "P&L variance population (actual AND budget present)", cv["ELIGIBLE"], "", "eligible_PL_variance = 1"))
cb = Counter(ref.pr_bs_actual)
wf.append(("W60", "Balance Sheet actual population (separate, never added to P&L)", cb["ELIGIBLE"], "", "eligible_BS_actual = 1"))
fc = posted_elig.values & ref.forecast_usd_p.notna().values
py = posted_elig.values & ref.prior_year_usd_p.notna().values
wf.append(("W70", "P&L vs forecast population (eligible AND forecast present)", int(fc.sum()), "", "v_pl_forecast"))
wf.append(("W71", "P&L vs prior-year population (eligible AND PY present)", int(py.sum()), "", "v_pl_prior"))
pd.DataFrame(wf, columns=["step", "stage", "records", "note", "identification"]).to_csv(WORK / "waterfall.csv", index=False)
for s, cnt in [("pl_actual", c), ("pl_variance", cv), ("bs_actual", cb)]:
    pd.Series(cnt).sort_index().to_csv(WORK / f"exclusions_{s}.csv", header=["rows"])
R.cmp("W99", A, "Waterfall: 152,682 - exclusions = 58,340", 58340, running, 0)

# phase 4 waterfall output vs independent
p4 = pd.read_csv(ROOT / "outputs/phase4/i9_exclusion_waterfall.csv")
for _, r in p4.iterrows():
    k = r.primary_reason
    R.cmp(f"L50.{k}", A, f"SQL i9 waterfall rows for {k} == independent", c.get(k, 0), int(r.rows_n), 0)

# ---------------------------------------------------------------- 7. record-level data quality on the analytical population
pe = cl[posted_elig.values]
R.cmp("D01", A, "Posted eligible: missing entity / division / GL / period", 0,
      int((pe[["entity_code", "division", "gl_account", "period_ym"]] == "").any(axis=1).sum()), 0)
R.cmp("D02", A, "Posted eligible: period_ym within 2023-01..2025-12", 0,
      int((~pe.period_ym.between("2023-01", "2025-12")).sum()), 0)
gl_map = cl[cl.is_posting_row == "1"].groupby("gl_account").account_group.nunique()
R.cmp("D03", A, "GL account -> account_group mapping is 1:1 (posting rows)", 0, int((gl_map > 1).sum()), 0)
R.add("D04", A, "Posted eligible rows with blank cost centre", "INFO", None, int((pe.cost_center_code == "").sum()))
DUPT = ["DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN", "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT", "CANDIDATE_COPY_PARTIAL_AGREEMENT"]
R.add("D05", A, "Posted eligible rows that are duplicate candidates (retained, not deleted)", "INFO", None,
      int(pe.dup_tier.isin(DUPT).sum()), note=json.dumps(pe.dup_tier.value_counts().to_dict()) +
      " | note: flag_dup_candidate marks only CANDIDATE_COPY_PARTIAL_AGREEMENT (11 rows); field-match tiers have their own flags")
R.cmp("D06", A, "Sign-conflict duplicate candidates (all rows)", 1587, int(cl.dup_tier.eq("DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT").sum()), 0)
R.cmp("D07", A, "Duplicate-candidate rows deleted by cleaning (raw rows with a candidate tier missing from cleaned)", 0,
      len(set(raw.row_id) - set(cl.row_id)), 0, note="cleaned rows = raw rows (L08): 3,930 candidate rows all retained")
fx0_raw = raw.fx_rate_raw.str.strip().eq("0")
R.cmp("D08", A, "Raw FX rate = 0 rows", 2517, int(fx0_raw.sum()), 0)
R.cmp("D08b", A, "flag_fx_zero = raw zero rate on POSTING rows (non-posting zero rows not flagged by design)",
      int((fx0_raw & ~nonpost).sum()), int(cl.flag_fx_zero.eq("1").sum()), 0,
      note="2,517 raw zeros = 2,510 posting + 7 non-posting rows; FX is not used to derive any reported USD amount")
# empirical test of the ambiguous 'n,nnn' reading: rows whose actual is ambiguous but local is unambiguous and FX > 0
la = [parse_amount(s) for s in raw.amount_local_raw]
aa = [parse_amount(s) for s in raw.actual_usd_raw]
fxv = pd.to_numeric(cl.fx_rate.replace("", np.nan)).values
tt = [(lv / fxv[i], av) for i, ((lv, lc), (av, ac)) in enumerate(zip(la, aa))
      if ac == "comma_thousands_ambiguous" and lc in ("plain", "us", "eu", "dec_comma") and lv and fxv[i] > 0]
tt = np.array(tt)
fit_th = int((np.abs(tt[:, 0] - tt[:, 1]) <= np.maximum(0.02 * np.abs(tt[:, 1]), 1)).sum())
fit_dc = int((np.abs(tt[:, 0] - tt[:, 1] / 1000) <= np.maximum(0.02 * np.abs(tt[:, 1] / 1000), 1)).sum())
R.cmp("L23", A, "Ambiguous 'n,nnn' actuals: rows fitting a 3-dp decimal reading via local/FX (must be 0)", 0, fit_dc, 0,
      note=f"{len(tt):,} testable rows; {fit_th:,} fit the thousands reading within 2% or 1 USD, {fit_dc} fit the "
           "decimal reading. Evidence supports the cleaner's thousands interpretation.")
num_bad = 0
for col in ["actual_usd_adj", "budget_usd_adj", "forecast_usd_adj", "prior_year_usd_adj"]:
    v = pd.to_numeric(pe[col].replace("", np.nan))
    num_bad += int(np.isinf(v).sum())
R.cmp("D09", A, "Infinite values in adjusted amounts (eligible)", 0, num_bad, 0)

# save reference frame for the financial step
ref["entity_code_ref"] = ent_code
ref["posted_elig"] = posted_elig.values
ref["nonposted_diag"] = nonposted_doc
ref["fac"] = fac.values
ref["status"] = st_lab.values
ref.to_pickle(WORK / "ref_frame.pkl")
R.save("lineage")
print("seconds", round(time.time() - t0, 1))
