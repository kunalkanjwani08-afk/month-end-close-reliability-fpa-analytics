# Data Dictionary

Source file: `data/raw/fpa_monthly_close_raw_messy.csv` (43 columns, 152,682 data rows, SHA-256 in [DATA_PROVENANCE.md](DATA_PROVENANCE.md)).
Related: [FINANCIAL_METRICS.md](FINANCIAL_METRICS.md) (rules and formulas).

**Status of this document: draft for review.** Nothing here has been confirmed by a source system owner or a vendor data dictionary. None of it has been implemented in code.

## How to read this document

- **Observed** facts (counts, formats, example values) were measured on the whole file on 2026-10-28 with an ad-hoc read-only script that is not committed. They describe the raw file and are reproducible.
- **Meaning status** applies only to the business meaning:
  - **Owner-stated**: the project owner said so in the project brief.
  - **Inferred**: guessed from the column name and the observed values. Not confirmed.
  - **Unresolved**: the meaning is unclear and a decision is needed.
- **Empty** means a zero-length value. **Whitespace-only** is counted separately. Placeholders such as `NA`, `-`, `#N/A` are not empty; they are counted as placeholders.
- **Proposed type** is the type after cleaning, not a decision to convert. Every proposal is subject to the cleaning rules being written first.
- "Blank is acceptable?" is a proposal, not a finding that blanks are errors.

Every column is stored as text in the raw file. Do not assume that a numeric-looking column is a number, or that a missing value is an error.

## Key structural facts

| Fact | Observed |
|---|---|
| Grain | One row per posting line (owner-stated). `row_id` is unique, but `document_no` is **not** (see column 33). |
| P&L and balance sheet | Mixed in one file. 145,534 rows carry a P&L-family `statement` label, 7,148 a balance-sheet label. |
| Scenarios | Actual, budget, forecast and prior year are separate columns on the same row, not separate rows. |
| Non-posting rows | 350 rows have `notes` = `subtotal row` (totals, subtotals, check rows). |
| Junk entities | 173 rows carry a `legal_entity` of `Do not use`, `xxx` or `TEST ENTITY`. |
| Time fields | `posting_date` is the only date column. There is no close start, close end, deadline or approval timestamp. |

## Identity and source

| # | Column | Observed format and values | Empty / placeholders | Proposed type | Meaning (status) | Cleaning and validation considerations |
|---|---|---|---|---|---|---|
| 1 | `row_id` | `R000001` to `R152682`, sequential, all unique | none | string | Row identifier in this extract (Inferred) | Unique per file row only. Does not prove a posting is unique. Keep as the audit key. |
| 2 | `source_system` | `SAP` 49,204 (+2,038 as `SAP ` with trailing space), `Oracle` 25,582, `Excel upload` 25,514, `NetSuite` 25,364, `Tally` 24,980 | none | category (5 values after trim) | System the line came from (Inferred) | Trim. Unknown whether the same posting can arrive from two systems. |
| 3 | `extract_batch` | `CLOSE-YYYY-nnn` 149,641 rows; `CLOSE-XX-nnn` 3,041 rows; 3,578 distinct | none | string | Extract run label (Inferred) | The year is a placeholder `XX` in 3,041 rows. It is a label, not a timestamp, so it cannot support close-duration measures. |

## Period

| # | Column | Observed format and values | Empty / placeholders | Proposed type | Meaning (status) | Cleaning and validation considerations |
|---|---|---|---|---|---|---|
| 4 | `fiscal_year` | `2023` 50,077, `2024` 49,818, `2025` 49,746, `FY23` 516, `FY24` 518, `FY25` 501 | 1,506 empty | integer (2023 to 2025) | Fiscal year of the line (Inferred) | Blank may be derivable from `fiscal_period` or `posting_date`: where both are available it agrees with the posting year in 60,092 of 60,092 testable rows. Derivation rule is a proposal. |
| 5 | `fiscal_period` | 288 distinct strings in nine formats: `2023-03`, `Jul-24`, `06/2023`, `202311`, `FY24 P02`, `01-May-2023`, `7/23`, `12/25`, `November 2023` | none | year-month (first day of month) | Accounting period the line belongs to (Inferred) | Needs an explicit mapping per format. Where testable, the period month equals the posting month in all rows (`FYyy Pnn`: 4,953 of 4,953; `yyyy-mm`: 16,943 of 16,943). That is consistent with a calendar fiscal year but is **not confirmed** (Unresolved). |
| 34 | `posting_date` | `yyyy-mm-dd` 60,707; `dd/mm/yyyy` or `mm/dd/yyyy` 55,318; `dd-Mmm-yyyy` 18,321; `yyyymmdd` 10,655. Range where unambiguous: 2023-01-01 to 2025-12-27 | 7,681 empty | date | Date the line was posted (Inferred) | The slash format mixes both orders: first part above 12 in 18,842 rows (day first), second part above 12 in 11,782 rows (month first), and both parts 12 or less in 24,694 rows where order cannot be told from the value. Blank dates are not necessarily errors (Unresolved). |

## Organisation

| # | Column | Observed format and values | Empty / placeholders | Proposed type | Meaning (status) | Cleaning and validation considerations |
|---|---|---|---|---|---|---|
| 6 | `legal_entity` | 38 strings. Six canonical entities (NovaBridge UK Ltd, APAC Pte Ltd, Europe GmbH, MENA FZE, Americas Inc, India Pvt Ltd) plus spelling variants (`NB UK`, `Novabridge USA`, `NovaBridge  MENA FZE`). Junk: `Do not use` 63, `xxx` 60, `TEST ENTITY` 50 | 45 empty, 2 whitespace-only | category (6 entities) | Legal entity that owns the posting (Owner-stated: six entities) | Map variants through an explicit mapping table. Junk entities are non-reporting. Missing entity could be recovered from `entity_code` (proposal). |
| 7 | `entity_code` | `GB01 SG01 DE01 IN01 AE01 US01` (about 24.5k to 24.8k each), lower-case variants 4,567 rows; `99` 75, `T999`/`t999` 69 | 76 empty | category (6 codes) | Code of the legal entity (Inferred) | Upper-case. In rows with a canonical code, each code pairs with exactly one currency (GB01 GBP, SG01 SGD, DE01 EUR, IN01 INR, AE01 AED, US01 USD). That is an observed pattern, not a confirmed rule. |
| 8 | `division` | 24 strings for five divisions: Industrial Components, Medical Devices, Consumer Durables, Packaging, Services & Spares (abbreviations, case and spacing vary) | none | category (5) | Business division (Owner-stated: five divisions) | Mapping table needed (for example `Pkg`, `Med Devices`, `Cons. Durables`). |
| 9 | `country` | `United Kingdom`, `Singapore`, `Germany`, `India`, `UAE`, `United States` (about 25.3k to 25.6k each) | none | category | Country of the entity (Inferred) | Clean. Matches the six entities. |
| 10 | `region` | `Europe` 48,972, `ASEAN` 24,497, `South Asia` 24,427, `Middle East` 24,310, `North America` 24,296 | 6,180 empty | category | Reporting region (Inferred) | Each country maps to exactly one region in non-blank rows, so blanks could be derived from `country` (proposal). |
| 11 | `cost_center_code` | 8 codes (CC110, CC140, CC210, CC240, CC310, CC410, CC510, CC610); 7,405 rows use a hyphenated variant (`CC-210`) | 6,841 empty | category (8) | Cost centre of the line (Inferred) | Remove the hyphen. Blanks occur on 6,507 P&L rows and 334 balance-sheet rows, so blank is not limited to balance-sheet lines. Whether blank is acceptable is Unresolved. |
| 12 | `cost_center_name` | `Sales Office`, `Marketing`, `Finance`, `Supply Chain`, `Plant Operations`, `Quality`, `G&A`, `IT`, some with trailing space | 6,841 empty | category (8) | Name of the cost centre (Inferred) | After trim and hyphen removal, code and name pair one-to-one (8 pairs for 8 codes). |
| 13 | `cost_center_owner` | 8 named individuals (for example `A. Rahman`, `K. Iyer`) | 6,841 empty | string | Person responsible for the cost centre (Inferred) | Treat as fictional. Not needed for reported totals. |

## Accounts and classification

| # | Column | Observed format and values | Empty / placeholders | Proposed type | Meaning (status) | Cleaning and validation considerations |
|---|---|---|---|---|---|---|
| 14 | `gl_account` | 32 four-digit codes (1xxx, 2xxx balance sheet; 4xxx to 8xxx P&L); 4100, 4190, 4110, 5100 each about 26k rows | 3,451 empty | string (keep as text) | General-ledger account (Inferred) | 350 of the blanks are non-posting rows; 3,101 blanks are not flagged non-posting (Unresolved). Where present, code range agrees with `statement`: every 1xxx/2xxx row is balance-sheet labelled and no 4xxx to 8xxx row is. |
| 15 | `account_name` | 122 distinct strings versus 32 GL codes. Includes non-posting labels `TOTAL`, `Grand Total`, `CHECK`, `Total for entity`, `Subtotal` (with typos) | none | string | Account description (Inferred) | The GL-to-name mapping has not been validated. Non-posting labels all fall within the 350 `subtotal row` rows. |
| 16 | `account_group` | Revenue, COGS, Operating expense, People cost, Working capital, Below EBITDA, Tax, Depreciation; 15 strings (case variants) | none | category (8) | Reporting group of the account (Inferred) | Case-normalise. `Working capital` occurs only on balance-sheet labelled rows; no balance-sheet row has another group. |
| 17 | `fs_line` | 33 labels such as `Net sales`, `Discounts`, `Material cost`, `Receivables`; `TOTAL` 339 | 3,758 empty | category | Financial-statement line (Inferred) | `TOTAL` rows are non-posting. Blank on real postings is Unresolved. |
| 18 | `statement` | P&L family (`P&L`, `PL`, `IS`, `Income statement`, `Profit & Loss`) 145,534 rows; balance-sheet family (`Balance Sheet`, `BS `, `Statement of position`, `B/S`, `BS`) 7,148 rows | none | category (2: P&L, Balance sheet) | Which statement the line belongs to (Owner-stated: both are mixed in the file) | Normalise to two values. Never add the two families together. |
| 19 | `cost_nature` | `Variable` 116,168, `Fixed` 15,152, `Balance sheet` 6,790, `Mixed` 5,990, `Financial` 2,548, abbreviations `F`, `Var`, `V` | 1,524 empty | category | Fixed/variable behaviour of the cost (Inferred) | Normalise abbreviations (`F` to Fixed, `V` and `Var` to Variable) as a proposal. Not needed for headline totals. |
| 20 | `product_family` | `Spare Kits`, `Diagnostics`, `Motors`, `Home Comfort`, `Pumps & Valves` | 49,094 empty | category | Product family sold (Inferred) | Populated on 77,863 of 81,985 revenue-group rows and on 25,725 of 70,697 other rows. Blank is plausible where a line is not product-specific. |
| 21 | `customer_segment` | `Aftermarket`, `Public`, `OEM` | 51,346 empty | category | Customer segment (Inferred) | Same pattern as `product_family`. Blank likely acceptable. |
| 22 | `channel` | `Direct` 51,257, `Distributor` 51,257, variants `Dist`, `direct`, `Dir` | 44,435 empty | category (2) | Sales channel (Inferred) | Normalise variants. Blank likely acceptable on non-sales lines. |

## Amounts and measures

All amount columns are text. Formats seen: plain decimals, thousands separators (`9,999`), `$ ` prefix, negative as leading minus or in parentheses `(9,999.99)`, European format (`9.999,99`, `999,99`), four decimals, leading or trailing spaces.

| # | Column | Observed placeholders (rows) | Not parsable by a heuristic parser | Proposed type | Meaning (status) | Cleaning and validation considerations |
|---|---|---|---|---|---|---|
| 23 | `currency` | `GBP SGD EUR INR USD AED` plus lower-case variants (about 3,000) | none | category (6, upper-case) | Currency of `amount_local_raw` (Inferred) | Upper-case. See `entity_code`. |
| 24 | `amount_local_raw` | `###` 3,585, `null` 735, `NA` 712, `-` 703, `#N/A` 702, empty 699, ` - ` 693, `n/a` 686, `N/A` 657 | 9,172 | decimal | Amount in local currency (Inferred) | Placeholders are not all the same thing. `-` or ` - ` can mean zero in accounting layouts; this is **Unresolved**, not assumed missing. Comma use is ambiguous (`1,234` thousands or decimal comma); a parsing rule must be written and tested. |
| 25 | `fx_rate_raw` | `NA` 2,612, `-` 2,570, empty 2,561, `0` 2,517 | 7,743 non-numeric, plus 2,517 zero | decimal | Exchange rate (Inferred). Direction Unresolved, see FINANCIAL_METRICS | Zero is not a valid rate. Rows with USD currency also carry rates other than 1 (for example `1.001498`), which is unexplained. |
| 26 | `actual_usd_raw` | `###` 3,617, ` - ` 735, `#N/A` 735, `n/a` 728, `-` 711, `N/A` 705, `NA` 690, empty 674, `null` 664 | 9,259 | decimal | Actual amount in USD (Inferred) | Sign and scale rules are Unresolved (see FINANCIAL_METRICS). |
| 27 | `budget_usd_raw` | same placeholder families | 8,915 | decimal | Budget amount in USD (Inferred) | Whether budget is stored per posting line or repeated is Unresolved. |
| 28 | `forecast_usd_raw` | same placeholder families | 9,200 | decimal | Forecast amount in USD (Inferred) | Same question as budget. |
| 29 | `prior_year_usd_raw` | same placeholder families | 9,069 | decimal | Prior-year actual in USD (Inferred) | Same question as budget. |
| 30 | `qty_raw` | numeric in 52,989 rows (all in Revenue and COGS groups); `NA` 33,307, empty 33,235, `-` 33,149 | 99,693 | decimal | Quantity (Inferred) | Negative quantities exist. Not needed for P&L totals. |
| 31 | `uom` | `EA` 46,843, `KG` 5,120, `Each` 1,261, `ea` 1,255, `NOS` 1,231, `kg` 1,173 | 95,799 empty | category | Unit of measure (Inferred) | `EA`, `Each`, `ea` look equivalent; `NOS` unconfirmed. |
| 32 | `headcount_fte_raw` | numeric in 5,341 rows (mainly People cost group); `NA` 49,296, empty 49,128, `-` 48,917 | 147,341 | decimal | Headcount in FTE (Inferred) | Informational. Do not sum across periods. |

## Journal and controls

| # | Column | Observed format and values | Empty / placeholders | Proposed type | Meaning (status) | Cleaning and validation considerations |
|---|---|---|---|---|---|---|
| 33 | `document_no` | `JE` plus seven digits, 148,402 distinct; 4,260 numbers repeat across 8,540 rows (at most 3 lines per number) | none | string | Journal document number (Inferred) | Not a unique posting key. A repeated number can be several lines of one journal. No two rows are identical apart from `row_id`. |
| 35 | `user_id` | 7 user ids (`ssc_pl`, `ssc_my`, `audit.ext`, `fi_close`, `plant.bot`, `excel.loader`, `KB`), about 18.2k to 18.7k each | 4,531 empty, 18,689 single space | string | User who posted or prepared the line (Inferred) | Meaning of each id Unresolved. Blank vs single space may differ. |
| 36 | `line_text` | 39 distinct; `IC charge`, `close entry`, `reclass`, `manual` about 21.8k each; many repeat the `fs_line` label; `TOTAL` 45 (all 45 are `subtotal row` lines) | 21,861 empty, 21,902 whitespace-only | string | Free-text line description (Inferred) | Could mark journal type (reclass, close entry, manual). Unresolved whether these are control signals. |
| 37 | `intercompany` | 12 spellings. Yes-like (`Y`, `Yes`, `y`, `IC`, `1`, `TRUE`) 5,761; no-like (`N`, `No`, `n`, `0`, `FALSE`) 122,427 | 24,494 empty | boolean | Intercompany flag (Inferred) | Normalise to true, false, unknown. Blank is not treated as false. |
| 38 | `accrual` | `N` 43,004; yes-like (`Y`, `Yes`, `1`, `Accrual`) 10,553 | 99,125 empty | boolean | Accrual flag (Inferred) | Blank is not treated as false. |
| 39 | `elimination_status` | `N/A` 30,000, `Eliminated` 815, `Not eliminated` 802, `Pending` 779 | 120,286 empty | category | Intercompany elimination state (Inferred) | Treatment for consolidated totals is Unresolved. |
| 40 | `report_scale` | `Actual` 143,223, `Thousands` 6,305, `Lakhs` 978, `000s` 975, `In thousands` 922 | 279 empty | category | Stated unit scale of the amounts (Owner-stated: unreliable) | Do not use the label alone. Magnitude evidence is in FINANCIAL_METRICS section 8. |
| 41 | `scenario_tag` | `Reported` 19,272, `actuals` 19,269, `Close` 19,176, `Management` 18,988, `ACT+BUD` 18,972, `Actual` 18,937, `ACT` 18,921 | 19,147 empty | category | Scenario label (Owner-stated: noise) | Near-uniform spread is consistent with noise but this was not tested against other columns. Do not use to select scenarios. |
| 42 | `approval_status` | `Posted` 65,381, `pending` 22,072, `Rejected` 21,795, `Parked` 21,650 | 21,784 empty | category | Journal status (Inferred) | **There is no value `Approved`.** Each status needs an explicit treatment (FINANCIAL_METRICS section 5). |
| 43 | `notes` | `reverse next month` 1,081, `do not reverse` 1,081, `accrual?` 1,065, `subtotal row` 350 | 149,105 empty | string | Free-text note (Inferred) | `subtotal row` marks the 350 non-posting rows. Reversal notes are not yet investigated. |

## Gaps in this dictionary

- No source documentation exists in the repository, so every meaning marked Inferred should be confirmed by whoever produced the file.
- Column 24 to 29 parsing rules and the 288 `fiscal_period` mappings are not yet written.
- The `legal_entity`, `division`, `cost_center` and `account_name` mapping tables are not yet written.
- Counts in this document describe the file as received and will change only if the raw file changes. Its hash is recorded in DATA_PROVENANCE.md.
