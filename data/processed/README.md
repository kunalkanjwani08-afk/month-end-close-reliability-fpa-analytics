# data/processed — cleaned data and cleaning QC

| File | Bytes | SHA-256 (of the decompressed CSV) |
|---|---:|---|
| `fpa_monthly_close_cleaned.csv.gz` (stored) | 28,548,927 | — |
| `fpa_monthly_close_cleaned.csv` (after decompression) | 174,545,248 | `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47` |
| `QC_Report.txt`, `qc_summary.json` | 50,141 / 16,328 | cleaning QC output of the Phase 3 script |

* The canonical cleaned dataset: 152,682 rows (**no row deleted**), 192 columns, produced by [`src/clean_fpa_monthly_close.py`](../../src/clean_fpa_monthly_close.py).
* Stored as lossless GZIP (level 9); the decompressed hash above was verified after a round trip on 30 Oct 2026. The Phase 4 pipeline refuses any cleaned file that does not match this hash.
* `phase4_fpa.duckdb` (86 MB) is **not published**: it is rebuilt in about 30 seconds by `python src/phase4_pipeline.py`. Its bytes differ between rebuilds although its content does not.
* The QC files record sandbox build paths (for example `/tmp/...`); they contain no personal paths. They are published unchanged because other files record their hashes.
