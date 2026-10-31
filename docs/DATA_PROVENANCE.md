# Data Provenance

> **Evidence labels:** **Verified** = checked against a project file or a check that was run · **Owner-stated** = the project owner's own statement; nobody else has checked it · **Assumption** · **Unresolved** · **Not recorded** = the information was never captured and is not guessed here.

Related: [DATA_DICTIONARY.md](DATA_DICTIONARY.md), [FINANCIAL_METRICS.md](FINANCIAL_METRICS.md).

## Dataset record

| Item | Value | Label |
|---|---|---|
| Working name | NovaBridge Industries monthly close extract | Project label chosen for this repository |
| Original filename | `fpa_monthly_close_raw_messy.csv` (the repository stores it gzip-compressed as `data/raw/fpa_monthly_close_raw_messy.csv.gz`) | Verified |
| Creator | **Kunal Kanjwani, the project owner, created this synthetic dataset for this portfolio project.** | **Owner-stated** |
| Generator, tool, script, random seed | – | **Not recorded.** No generator script or seed was kept, so the data cannot be regenerated or independently verified. |
| Creation date | – | **Not recorded.** File-system dates on a copy are not treated as a creation or acquisition record. |
| Source website or URL | None: the data was not downloaded from a third party | Owner-stated |
| Original format | CSV, comma-separated, one header row | Verified |
| Encoding and line endings | UTF-8 (decodes without error, all bytes ASCII), no byte-order mark, LF line endings, final line ends with a newline | Verified (28 Oct 2026) |
| Dimensions | 43 columns, 152,682 data rows (152,683 lines including header), 51,938,535 bytes | Verified, counted with a CSV parser; no malformed rows |
| Coverage in the data | Group of six legal entities, five divisions, January 2023 to December 2025 | Verified in the file. Group and entity names are fictional (Owner-stated). |
| Licence | **None.** No open-source licence applies to the data or the code; default copyright applies. The repository is public for viewing. | Owner decision |

## Synthetic-data disclosure

- The project owner states that the data is **synthetic** and that he created it. NovaBridge Industries and its entities are fictional. This is not a real company's ledger. (Owner-stated)
- The file contains planted problems: placeholder strings in amount columns, junk entities named `TEST ENTITY`, `Do not use` and `xxx`, total and check rows inside the posting list, and near-uniform spreads in fields such as `scenario_tag` and `approval_status`. These observations are consistent with synthetic generation but do not prove it. (Verified observation; the inference is an Assumption)
- Because no generator or seed was recorded, **nobody else can independently verify how the data was produced**, and the project does not claim otherwise.
- The data contains eight person-like cost-centre owner names (initial plus surname) and eight generic system user IDs. No email address, phone number or URL appears in any column checked (30 Oct 2026). The names are treated as fictional because the group is fictional; that is an Assumption, not proof.

## File integrity

| Item | Value |
|---|---|
| Algorithm | SHA-256 of the decompressed file |
| Hash | `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff` |
| Same value in | `data/raw/README.md`, `HOW_TO_RUN.txt`, `src/clean_fpa_monthly_close.py` (the cleaner refuses to run on a different file) |

To verify: on Windows PowerShell run `Get-FileHash -Algorithm SHA256 data\raw\fpa_monthly_close_raw_messy.csv` (after decompressing, see `HOW_TO_RUN.txt`). On Linux or macOS run `sha256sum data/raw/fpa_monthly_close_raw_messy.csv`. The result must equal the hash above.

## Has the raw file been altered?

- **In this repository: No (Verified).** The file was copied byte for byte. The hash matched the owner's copy before and after copying, again on a fresh clone from GitHub on 28 Oct 2026, and after a gzip round trip on 30 Oct 2026. The cleaning script verifies the hash before every run.
- **Before it reached this repository: Not known.** Edits between creation and publication cannot be ruled out; the owner states there were none.
- No cleaning, sorting, renaming or regeneration has been applied to the raw file. All cleaning is done on copies.

## Known limitations

- No source documentation exists. Column meanings in [DATA_DICTIONARY.md](DATA_DICTIONARY.md) are mostly inferred.
- Amounts are text in many formats. Scale labels and some statuses are unreliable (Owner-stated and observed).
- The file mixes P&L and balance-sheet rows, includes non-posting rows, and contains junk entities.
- There are no close timestamps or deadlines, so close-duration measures cannot be derived.
- Rule decisions (scale, FX direction, signs, duplicates, journal status) are open. See [FINANCIAL_METRICS.md](FINANCIAL_METRICS.md).

## Appropriate use

- Suitable for demonstrating data cleaning, validation, reconciliation and financial analysis **method** on a simulated dataset.
- **Not** evidence of how any real company performed. Results from this file describe a simulated dataset and are labelled as such wherever shown.
- Figures derived from it must not be presented as real financial performance, benchmarks or industry findings.

## Publication history

On 30 Oct 2026 the owner decided to publish the complete project, including the raw dataset (compressed) and the cleaned dataset, in this public repository. Earlier drafts of this document asked the owner to confirm the origin, licence and public-release suitability of the file; the owner has since given the statements recorded above, and the repository states that it has no licence. The "Not recorded" items remain open because the information does not exist.
