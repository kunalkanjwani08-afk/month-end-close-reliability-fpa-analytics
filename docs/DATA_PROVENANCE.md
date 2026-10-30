# Data Provenance

Related: [DATA_DICTIONARY.md](DATA_DICTIONARY.md), [FINANCIAL_METRICS.md](FINANCIAL_METRICS.md).

Items marked **Not recorded** or **Not independently verified** are unknown to this project. They are not guesses. Nothing in this document has been checked against an external source.

## Dataset record

| Item | Value | Status |
|---|---|---|
| Working name | NovaBridge Industries monthly close extract | Project label chosen for this repository |
| Original filename | `fpa_monthly_close_raw_messy.csv` | Recorded. The repository copy keeps the same name. |
| Source website or URL | – | **Not recorded** |
| Who supplied or generated the file | Supplied by the project owner (Kunal Kanjwani). Original creator and tool | **Not recorded** |
| Acquisition or download date | – | **Not recorded.** File-system dates on a copy are not treated as an acquisition record. |
| Original format | CSV, comma-separated, one header row | Observed |
| Encoding and line endings | UTF-8 (decodes without error, all bytes ASCII), no byte-order mark, LF line endings, final line ends with a newline | Observed 2026-10-28 |
| Reported dimensions | 43 columns, 152,682 data rows (152,683 lines including header), 51,938,535 bytes | Observed, counted with a CSV parser; no malformed rows |
| Coverage in the data | Group of six legal entities, five divisions, January 2023 to December 2025 | Observed in the file. Group and entity names are fictional. |
| Dataset licence or terms of use | – | **Not independently verified.** No licence text was supplied. Do not assume permission to redistribute beyond this repository. |

## Synthetic-data disclosure

- The project owner states the data is **synthetic**. The group (NovaBridge Industries) and its entities are fictional. This is not a real company's ledger.
- Consistent with that statement, the file contains planted problems: placeholder strings in amount columns, junk entities named `TEST ENTITY`, `Do not use` and `xxx`, total and check rows inside the posting list, and near-uniform spreads in fields such as `scenario_tag` and `approval_status`. These observations are consistent with synthetic generation but do not prove it.
- **Generator, script, random seed and creation date:** **Not recorded.** If the generating script or prompt exists, it should be stored and referenced here.
- **Not independently verified:** that the file is entirely synthetic and contains no real company information.

## File integrity

| Item | Value |
|---|---|
| Algorithm | SHA-256 |
| Hash | `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff` |
| Same hash as README | Yes. The README carries the identical value. |

To verify: on Windows PowerShell run `Get-FileHash -Algorithm SHA256 data\raw\fpa_monthly_close_raw_messy.csv`. On Linux or macOS run `sha256sum data/raw/fpa_monthly_close_raw_messy.csv`. The result must equal the hash above.

## Has the raw file been altered?

- **In this repository: No.** The file was copied byte for byte. The hash matched the owner's Downloads copy before and after copying, and again on a fresh clone from GitHub on 2026-10-28.
- **Before it reached this repository: Not known.** Edits by whoever created or passed on the file cannot be ruled out.
- No cleaning, sorting, renaming or regeneration has been applied. All cleaning will be done on copies in `data/processed/`.

## Known limitations

- No source documentation or data dictionary exists. Column meanings in DATA_DICTIONARY.md are mostly inferred.
- Amounts are text in many formats. Scale labels and some statuses are unreliable (owner-stated and observed).
- The file mixes P&L and balance-sheet rows, includes non-posting rows, and contains junk entities.
- There are no close timestamps or deadlines, so close-duration measures cannot be derived.
- Rule decisions (scale, FX direction, signs, duplicates, journal status) are still open. See FINANCIAL_METRICS.md.

## Appropriate use

- Suitable for demonstrating data cleaning, validation, reconciliation and financial analysis **method** on a controlled, simulated dataset.
- **Not** evidence of how any real company performed. Results from this file describe a simulated dataset and must be labelled as such wherever shown.
- Do not present figures derived from it as real financial performance, benchmarks or industry findings.

## For the project owner to verify

1. Where the file came from (tool, prompt, script, website or person) and the date.
2. Whether any licence or terms apply, and whether the file may be published in a public repository.
3. That the file contains no real company, customer or personal data.
4. Whether the person names in `cost_center_owner` are fictional.


## Publication update (30 Oct 2026): owner decision to publish

* The project owner states that he created the NovaBridge project and its synthetic dataset for portfolio and learning purposes, and decided to publish the complete project including the raw and cleaned datasets.
* This is an **owner statement**. The generator, seed, creation date and any licence of the file are still **not recorded**, and nothing here has been checked against an external source.
* The data contains eight person-like cost-centre owner names (initial + surname) and eight generic system user IDs. No email address, phone number or URL appears in any column checked (30 Oct 2026). The names are treated as fictional because the group is fictional; that is not proven.
* The raw file is stored GZIP-compressed (lossless; hash in `data/raw/README.md`). The cleaned dataset is published as an Excel workbook; the 192-column CSV is regenerated by the cleaning script (see `data/processed/README.md`).
* No open-source licence is granted. The statements above in this document that were written before this decision (for example "do not assume permission to redistribute") are kept as the historical record.
