# data/raw — original messy extract

| File | Bytes | SHA-256 |
|---|---:|---|
| `fpa_monthly_close_raw_messy.csv.gz` (stored) | 11,209,009 | (gzip container; hash of the *decompressed* file below) |
| `fpa_monthly_close_raw_messy.csv` (after decompression) | 51,938,535 | `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff` |

* 43 columns, 152,682 data rows (152,683 lines with the header). The file is the original raw extract of the fictional **NovaBridge Industries** group, never edited.
* **Stored compressed (GZIP level 9, lossless).** Decompressing returns the exact original bytes; the SHA-256 above was checked after a full compress/decompress round trip on 30 Oct 2026.
* Decompress: `gunzip -k fpa_monthly_close_raw_messy.csv.gz` (Linux/macOS/Git Bash) or the Python one-liner in [`HOW_TO_RUN.txt`](../../HOW_TO_RUN.txt). Pandas also reads `.csv.gz` directly, but the project scripts expect the decompressed file and verify its hash.
* Synthetic status, provenance and licence: see [`docs/DATA_PROVENANCE.md`](../../docs/DATA_PROVENANCE.md). The data is described by its owner as synthetic; that is not independently verified.
