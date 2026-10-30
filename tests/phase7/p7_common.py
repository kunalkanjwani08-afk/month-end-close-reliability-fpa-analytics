"""Phase 7 QA - shared helpers (independent of the Phase 2-6 code paths).

Nothing in this module imports project code (src/*). It reads the raw CSV, the cleaned CSV and the
published outputs read-only and re-derives values with its own logic. Results are appended to a check
registry that is later written to outputs/phase7/qa_results.json and the Excel workbooks.
"""
import hashlib, json, math, re, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "phase7"
WORK = OUT / "evidence" / "work"
LOGS = OUT / "test_execution_logs"
RAW = ROOT / "data/raw/fpa_monthly_close_raw_messy.csv"
CLEAN = ROOT / "data/processed/fpa_monthly_close_cleaned.csv"
DB = ROOT / "data/processed/phase4_fpa.duckdb"
XLSX = ROOT / "outputs/phase5/fpa_month_end_close_analysis.xlsx"
HTML = ROOT / "outputs/phase6/fpa_financial_analytics_dashboard.html"
for p in (OUT, WORK, LOGS):
    p.mkdir(parents=True, exist_ok=True)

RAW_SHA = "a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff"
CLEAN_SHA = "c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47"

# Tolerances (explained in the report):
#  money totals : 0.01 USD absolute (one cent). Inputs carry at most 4 decimals and sums of ~60k terms in
#                 float64 accumulate error of order 1e-7 USD, so one cent is far above numerical noise and far
#                 below any reportable amount. A genuine population or rule difference moves totals by whole USD.
#  ratios       : 1e-9 absolute.
#  counts       : exact.
TOL_USD = 0.01
TOL_RATIO = 1e-9

PLACEHOLDERS = {"", "###", "#N/A", "NA", "N/A", "n/a", "null", "-"}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def parse_amount(s):
    """Independent parser for the raw amount strings. Returns (value or None, format_class)."""
    t = s.strip()
    if t in PLACEHOLDERS:
        return None, "missing"
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1].strip()
    t = t.replace("$", "").strip()
    if t.startswith("-"):
        neg, t = (not neg), t[1:].strip()
    if not re.fullmatch(r"[0-9.,]+", t):
        return None, "unparsable"
    cls = "plain"
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):          # 1.234,56  -> EU
            t, cls = t.replace(".", "").replace(",", "."), "eu"
        else:                                     # 1,234.56  -> US
            t, cls = t.replace(",", ""), "us"
    elif "," in t:
        groups = t.split(",")
        if all(len(g) == 3 for g in groups[1:]):  # 4,579 / 1,234,567 -> thousands separator (ambiguous with a 3-dp decimal comma)
            t, cls = t.replace(",", ""), "comma_thousands_ambiguous" if len(groups) == 2 else "comma_thousands"
        elif len(groups) == 2:                    # 54,78 -> decimal comma
            t, cls = t.replace(",", "."), "dec_comma"
        else:
            return None, "unparsable"
    elif t.count(".") > 1:
        t, cls = t.replace(".", ""), "dot_thousands"
    v = float(t)
    return (-v if neg else v), cls


class Registry:
    def __init__(self):
        self.rows = []

    def add(self, cid, area, check, status, expected=None, actual=None, population="", definition="",
            tolerance="", note="", evidence=""):
        assert status in ("PASS", "FAIL", "BLOCKED", "NOT TESTED", "INFO"), status
        absd = reld = None
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) and not isinstance(expected, bool):
            if not (math.isnan(expected) or math.isnan(actual)):
                absd = abs(actual - expected)
                reld = absd / abs(expected) if expected else None
        self.rows.append(dict(id=cid, area=area, check=check, population=population, definition=definition,
                              expected=expected, actual=actual, abs_diff=absd, rel_diff=reld, tolerance=tolerance,
                              status=status, note=note, evidence=evidence))

    def cmp(self, cid, area, check, expected, actual, tol, population="", definition="", note="", evidence="", tolerance=None):
        if expected is None or actual is None:
            ok = expected is None and actual is None
        elif isinstance(expected, float) and math.isnan(expected):
            ok = isinstance(actual, float) and math.isnan(actual)
        else:
            ok = abs(actual - expected) <= tol
        self.add(cid, area, check, "PASS" if ok else "FAIL", expected, actual, population, definition,
                 tolerance if tolerance is not None else tol, note, evidence)
        return ok

    def save(self, name):
        (WORK / f"checks_{name}.json").write_text(json.dumps(self.rows, indent=1, default=str), encoding="utf-8")
        from collections import Counter
        c = Counter(r["status"] for r in self.rows)
        print(f"[{name}] {dict(c)}")
        for r in self.rows:
            if r["status"] in ("FAIL", "BLOCKED"):
                print("  ", r["status"], r["id"], r["check"], "| exp", r["expected"], "| act", r["actual"], "|", r["note"][:200])


def clean_num(s):
    return None if s == "" else float(s)
