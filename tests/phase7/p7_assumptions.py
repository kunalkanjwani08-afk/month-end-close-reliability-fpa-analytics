"""Phase 7 - project-specific assumptions: is each unresolved issue implemented consistently AND disclosed in every
user-facing output (dashboard HTML, Phase 5 workbook, documentation)? Disclosure is checked by locating the
specific wording in the delivered files (evidence = matched snippet)."""
import json, re
import openpyxl
import pandas as pd
from p7_common import *

R = Registry()
A = "assumptions"
html = HTML.read_text(encoding="utf-8")
wb = openpyxl.load_workbook(XLSX, data_only=True)
xl = "\n".join(str(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if isinstance(v, str))
docs = "\n".join((ROOT / "docs" / f).read_text(encoding="utf-8") for f in ["FINANCIAL_METRICS.md", "PHASE4_ANALYSIS_REPORT.md", "DATA_PROVENANCE.md", "PHASE4_INSIGHT_REGISTER.md"])
docs += (ROOT / "README.md").read_text(encoding="utf-8")


def disclosed(cid, topic, patterns):
    res = {}
    for name, txt in [("dashboard", html), ("workbook", xl), ("docs", docs)]:
        m = None
        for p in patterns:
            m = re.search(p, txt, re.I | re.S)
            if m: break
        res[name] = (txt[max(0, m.start() - 60):m.end() + 60].replace("\n", " ") if m else None)
    miss = [k for k, v in res.items() if v is None]
    R.add(cid, A, f"Disclosure present in dashboard, workbook and docs: {topic}", "PASS" if not miss else "FAIL",
          "dashboard+workbook+docs", ",".join(k for k, v in res.items() if v) or "none",
          note=("missing in: " + ",".join(miss) + " | " if miss else "") + json.dumps({k: (v[:160] if v else None) for k, v in res.items()}))

disclosed("AS01", "Posted-only status rule is provisional (R6)", [r"R6"])
disclosed("AS02", "Sign convention unresolved (R9), no favourable/unfavourable labels", [r"R9[^.]{0,80}unresolved", r"sign convention[^.]{0,40}unresolved", r"R9 \| Account sign convention\. \| Unresolved"])
disclosed("AS03", "Scale restoration is provisional / confidence levels", [r"scale[- ]restor[^.]{0,120}(provisional|confidence)", r"provisional[^.]{0,80}scale"])
disclosed("AS04", "Duplicate candidates retained, not confirmed duplicates", [r"not confirmed duplicates", r"candidates[^.]{0,60}retained"])
disclosed("AS05", "FX zero/missing rates unresolved, USD used as reported", [r"fx[_ ]zero", r"FX rate = 0", r"zero (FX )?rate"])
disclosed("AS06", "No forecast version / as-of date: no forecast-skill claim", [r"no forecast version", r"version or as-of date", r"forecast version"])
disclosed("AS07", "Gross profit S1/S2/S3 kept separate (discount convention unresolved)", [r"three (discount )?treatments", r"S1 = every amount signed as recorded"])
disclosed("AS08", "Balance Sheet measurement basis not established", [r"measurement basis", r"not period-end balances", r"opening/closing"])
disclosed("AS09", "DSO / DPO / working capital not computed", [r"DSO"])
disclosed("AS10", "Close duration / on-time close not computed (no timestamps)", [r"close duration", r"close-timeliness", r"close start or end time"])
disclosed("AS11", "NOS vs EA unit equivalence unverified", [r"NOS[^.]{0,40}EA", r"unit[- ]of[- ]measure"])
disclosed("AS12", "Synthetic data, provenance/licence unverified", [r"provenance"])
disclosed("AS13", "Result proxy is not EBITDA", [r"not EBITDA", r"not a reported operating profit"])
# implementation consistency (data facts re-checked here, independent of the outputs)
cl = pd.read_csv(CLEAN, dtype=str, keep_default_na=False, encoding="utf-8-sig",
                 usecols=["uom", "approval_status", "eligible_PL_actual", "statement", "flag_fx_zero", "fx_status"])
uom = cl.uom.value_counts().to_dict()
R.add("AS20", A, "Units of measure present (NOS / EA etc.) - no conversion applied anywhere in metrics", "INFO", None, None, note=json.dumps(uom))
R.cmp("AS21", A, "Eligible P&L lines whose status is not Posted (provisional rule R6 enforced)", 0,
      int(((cl.eligible_PL_actual == "1") & (cl.approval_status != "Posted")).sum()), 0)
R.cmp("AS22", A, "Eligible P&L lines whose statement is Balance Sheet", 0, int(((cl.eligible_PL_actual == "1") & (cl.statement != "P&L")).sum()), 0)
fz = (cl.eligible_PL_actual == "1") & (cl.flag_fx_zero == "1")
R.add("AS23", A, "Eligible lines with a zero FX rate (kept; USD column used as reported, no FX repair)", "INFO", None, int(fz.sum()))
R.save("assumptions")
