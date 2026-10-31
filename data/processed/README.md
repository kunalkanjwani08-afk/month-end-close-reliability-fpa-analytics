# data/processed: cleaned data and cleaning QC

| File | What it is |
|---|---|
| `fpa_monthly_close_cleaned.xlsx` | **The published cleaned dataset (review workbook, 64 MB).** Sheet `Cleaned_Data`: 152,682 rows (no row deleted) x 77 columns. The other 20 sheets document the cleaning: data-quality findings, exclusion summary, exceptions, junk-entity and non-posting rows, scale, FX and amount-parsing evidence, duplicate review, mappings, column profile, schema map, transformation log, validation checks and open items. It is kept as evidence and is not modified by this project's later work. |
| `QC_Report.txt`, `qc_summary.json` | Quality-control output of the cleaning script, from a full run on the published raw file (43 in-memory + 27 read-back checks, 0 failed). They record file names only, no machine paths. |

* Produced from the raw file by [`src/clean_fpa_monthly_close.py`](../../src/clean_fpa_monthly_close.py).
* **The workbook shows 77 of the 192 columns the script produces.** The SQL analysis also needs the flag, raw-copy and adjustment columns, which live in a 174.5 MB CSV (`fpa_monthly_close_cleaned.csv`, SHA-256 `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47`). That CSV is **not stored** in the repository (it is git-ignored): regenerate it with `python src/clean_fpa_monthly_close.py --output-dir data/processed` after decompressing the raw file (about 4-5 minutes; see [`HOW_TO_RUN.txt`](../../HOW_TO_RUN.txt)).
* **Regenerating overwrites** this workbook, `QC_Report.txt` and `qc_summary.json` with equivalent content and a new timestamp; `git restore` returns the published versions.
* **The regenerated CSV is byte-identical on some CPUs and differs in the last digit of two floating-point columns on others** (investigated 31 Oct 2026: 2 of 192 columns, no flag or decision affected). The SQL pipeline handles this with a reported, documented fallback; see [`docs/DATA_AND_CLEANING_METHODOLOGY.md`](../../docs/DATA_AND_CLEANING_METHODOLOGY.md), section 14.
* `build/fpa_analysis.duckdb` (86 MB) is generated, git-ignored and rebuilt by `python src/sql_analysis_pipeline.py` in about 20 seconds.
* Should the 64 MB workbook ever move out of the repository (for example to a GitHub Release asset), the CSV above can be regenerated, but the audit sheets exist only in the workbook, so it is kept here.
