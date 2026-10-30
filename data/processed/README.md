# data/processed — cleaned data and cleaning QC

| File | What it is |
|---|---|
| `fpa_monthly_close_cleaned.xlsx` | **The cleaned dataset.** Sheet `Cleaned_Data`: 152,682 rows (no row deleted) × 77 columns. Further sheets document the cleaning: data-quality findings, exclusion summary, exceptions, duplicate review, mappings, column profile, transformation log, validation checks and open items (21 sheets). |
| `QC_Report.txt`, `qc_summary.json` | Quality-control output of the cleaning script. |

* Produced from the raw file by [`src/clean_fpa_monthly_close.py`](../../src/clean_fpa_monthly_close.py).
* **The workbook shows 77 of the 192 columns the script produces.** The SQL analysis also needs the extra flag, raw-copy and adjustment columns, which live in a 174.5 MB CSV (`fpa_monthly_close_cleaned.csv`, SHA-256 `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47`). That CSV is not stored in the repository: running `python src/clean_fpa_monthly_close.py --output-dir data/processed` on the raw file regenerates it. On 30 Oct 2026 this was done from the published raw file and the CSV hash matched exactly; the regenerated workbook's sheets matched the published one except for the run timestamp and input path.
* `build/fpa_analysis.duckdb` (86 MB) is not published; `python src/sql_analysis_pipeline.py` rebuilds it in about 20 seconds.
* The QC files record sandbox build paths (for example `/tmp/...`); they contain no personal paths.
