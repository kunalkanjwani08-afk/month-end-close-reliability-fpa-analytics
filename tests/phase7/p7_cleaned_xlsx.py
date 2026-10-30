"""Phase 7 - the Phase 2 cleaned workbook (fpa_monthly_close_cleaned.xlsx, 'Cleaned_Data' sheet, 77 fields) versus the
canonical 192-column cleaned CSV: same rows, column subset, same values (every row, every shared column)."""
import sys, json, hashlib, openpyxl, csv, datetime, collections
from pathlib import Path
X = Path(sys.argv[1]); C = Path(sys.argv[2]); OUTF = Path(sys.argv[3])
h = hashlib.sha256(X.read_bytes()).hexdigest()
wb = openpyxl.load_workbook(X, read_only=True)
sheets = {ws.title: (ws.max_row, ws.max_column) for ws in wb.worksheets}
it = wb["Cleaned_Data"].iter_rows(values_only=True)
hx = list(next(it))
rd = csv.reader(open(C, encoding="utf-8-sig", newline=""))
hc = next(rd)
missing = [c for c in hx if c not in hc]
idx = [(i, hc.index(c)) for i, c in enumerate(hx) if c in hc]
n = bad = 0; ex = []; bycol = collections.Counter(); datefix = 0
for xr, cr in zip(it, rd):
    n += 1
    for i, j in idx:
        v = xr[i]
        if isinstance(v, datetime.datetime) and v.time() == datetime.time(0):
            v = v.date().isoformat(); datefix += 1   # Excel stores dates as date cells; compare the calendar date
        a = "" if v is None else str(v); b = cr[j]
        if a != b:
            try:
                if abs(float(a) - float(b)) <= 1e-9 * max(1, abs(float(b))): continue
            except ValueError:
                pass
            bad += 1; bycol[hx[i]] += 1
            if len(ex) < 15: ex.append((n, hx[i], a[:40], b[:40]))
rest = sum(1 for _ in it) + sum(1 for _ in rd)
res = dict(sha256=h, sheets=sheets, xlsx_cols=len(hx), csv_cols=len(hc), cols_not_in_csv=missing, rows_compared=n,
           leftover_rows=rest, cell_mismatches=bad, mismatches_by_column=dict(bycol), date_cells_normalised=datefix, examples=ex)
OUTF.write_text(json.dumps(res, indent=1, default=str)); print(json.dumps({k: v for k, v in res.items() if k != "sheets"}, default=str))
