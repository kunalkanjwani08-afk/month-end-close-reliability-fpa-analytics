# Data and Cleaning Methodology

> **Status (updated at Phase 9 publication, 30 Oct 2026):** published as part of the complete project. The owner decided to publish the whole project, including the dataset he describes as synthetic. Dataset provenance and redistribution rights remain **owner-stated and not independently verified**. Any wording below from Phase 8 that calls the release *blocked*, *draft* or *not approved* describes the Phase 8 state and is superseded by [PUBLICATION_DECISION.md](PUBLICATION_DECISION.md). No calculation, figure or finding was changed.
> **Evidence labels:** **Verified** = checked against a project file or Phase 7 check · **Owner-stated** · **Assumption** = provisional project rule · **Unresolved**.
> **Sources used:** `data/processed/QC_Report.txt`, `data/processed/qc_summary.json`, `src/clean_fpa_monthly_close.py`, `docs/DATA_DICTIONARY.md`, `docs/FINANCIAL_METRICS.md`, `docs/DATA_PROVENANCE.md`, `outputs/phase7/PHASE7_QA_REPORT.md`.

Related: [Workflow](END_TO_END_WORKFLOW.md) · [Financial metrics](FINANCIAL_METRICS_AND_METHODOLOGY.md) · [Assumptions and limitations](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md)

---

## 1. Summary

The cleaner turns a 43-column text extract into a 192-column analytical file **without deleting a single row**. It records the as-reported value beside every adjusted value, labels each decision with its evidence and confidence, and leaves undecidable cases undecided. **A cleaned dataset is not a resolved dataset:** the file is now parseable, traceable and flagged, but several business definitions (journal-status meaning, sign convention, duplicate rule, FX rate meaning, report-scale ground truth) remain open and are carried as disclosed assumptions.

## 2. Original dataset

| Fact | Value | Label |
|---|---|---|
| File | `fpa_monthly_close_raw_messy.csv` | Verified |
| Size, rows, columns | 51,938,535 bytes; 152,682 data rows (152,683 lines with the header); 43 columns | Verified |
| SHA-256 | `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff` | Verified |
| Encoding | UTF-8, no byte-order mark, LF line endings | Verified (Phase 1 observation) |
| Storage type | Every one of the 43 columns is text | Verified |
| Grain | One row per source extract record; `row_id` is unique, `document_no` is not. The dataset contains 152,682 source extract records, including 350 non-posting subtotal/check records. These 350 records are not treated as ordinary posted journal lines. | `row_id` uniqueness and the 350 count Verified; posting semantics Owner-stated |
| Coverage | Six legal entities, five divisions, January 2023 to December 2025 (36 periods; 0 entity-period gaps) | Verified |
| Content mix | P&L and balance-sheet lines in one file: 145,534 P&L-labelled rows and 7,148 balance-sheet-labelled rows | Verified |
| Observed `source_system` labels | SAP, Oracle, Excel upload, NetSuite, Tally (SAP also appears with a trailing space in 2,038 raw rows). The actual originating platforms have not been independently authenticated | Labels Verified; origin Unverified |
| Provenance | Source, creator, generation date, licence: **not recorded** | Unresolved |

Raw rows that are not postings: 350 rows with `notes` = `subtotal row` (TOTAL, Subtotal and CHECK labels).

## 3. Source columns and cleaned columns

The 43 source columns fall into identity (row, document, system, user, notes), period (fiscal year, fiscal period, posting date, extract batch), organisation (entity, division, country, region, cost centre), accounts (GL account and name, account group, FS line, statement, cost nature), dimensions (product family, customer segment, channel, unit of measure), amounts (currency, local amount, FX rate, actual, budget, forecast, prior year, quantity, headcount) and controls (intercompany, accrual, elimination status, report scale, scenario tag, approval status).

The canonical cleaned CSV has **192 columns** and the same 152,682 rows in the same order:

| Column family | Count | Purpose |
|---|---:|---|
| Preserved raw values (`*_raw`) | 17 | The text as received, beside its cleaned counterpart |
| Cleaned source fields | — | Trimmed, case-normalised, mapped fields (entity, GL, division, statement, period, and so on) |
| Parsed amounts (`*_parsed`) and parse status and format | 5 amounts + status and format columns | Numeric value exactly as reported, no scale restoration |
| Scale decision (`scale_decision`, `scale_evidence`, `scale_confidence`, `scale_factor_applied`) and adjusted amounts (`*_adj`) | 5 adjusted amounts | Provisional scale-adjusted USD; blank where scale is undetermined |
| FX and sign diagnostics | — | `fx_check`, `usd_from_local_div_rate`, `sign_pattern`, `sign_flag` |
| Duplicate diagnostics | — | `doc_group_id`, `dup_tier`, `dup_role`, agreement columns |
| Flags (`flag_*`) | 72 | Yes/no markers, never used to delete rows |
| Eligibility (`excl_PL_actual`, `eligible_PL_actual`, `excl_PL_variance`, `eligible_PL_variance`, `excl_BS_actual`, `eligible_BS_actual`) | 6 | One primary exclusion reason per row for three scopes |

The cleaned CSV is written as UTF-8 with a byte-order mark, so the first header cell reads `\ufeffsource_row_number` when the file is opened as plain UTF-8 (open it as `utf-8-sig`).

### Why the Excel review workbook is not the cleaned CSV

The Phase 2 review workbook (`fpa_monthly_close_cleaned.xlsx`, 67,381,749 bytes) is a **review copy**, not the canonical dataset. Its `Cleaned_Data` sheet holds **77 fields** that are shared with the 192-column CSV; the CSV carries the remaining 115 parsed, flagged, diagnostic and eligibility columns that a person reviewing in Excel does not need and that would exceed practical workbook width. Phase 7 compared all 152,682 rows × 77 shared fields against the CSV and found **0 mismatches** (Excel date cells read as calendar dates), and confirmed that every workbook column exists in the CSV. Only the CSV is accepted by the pipeline (it is identified by its SHA-256). The workbook also embeds run metadata, so its bytes differ on every cleaner run while its content does not.

## 4. Data types

All source fields are text. After cleaning: amounts, FX rate, quantity and headcount are numeric (`*_parsed`, `fx_rate`, `qty`, `headcount_fte`); `fiscal_year`, `period_year` and `period_month` are integers; `period_ym`, `period_end_date` and `posting_date` are dates; identifiers (`row_id`, `document_no`, `gl_account`) stay text so leading zeros and codes are preserved; flags are 0/1; categorical fields (entity code, currency, statement, status and so on) are normalised text. In DuckDB, `stg_close_raw` keeps all 192 columns as text and `fact_close` types them.

## 5. Missing values and placeholders

Placeholders are not all the same thing and none is treated as zero.

| Amount column | Cells unparsable by a simple parser (raw) | Present as placeholder or blank after strict parsing |
|---|---:|---|
| `amount_local_raw` | 9,172 | 9,172 |
| `actual_usd_raw` | 9,259 | 9,259 |
| `budget_usd_raw` | 8,915 | 8,915 |
| `forecast_usd_raw` | 9,200 | 9,200 |
| `prior_year_usd_raw` | 9,069 | 9,069 |

Placeholders recognised: `###`, `#N/A`, `NA`, `N/A`, `n/a`, `null`, hyphen (`-`, including ` - `) and blank. Whether a hyphen means zero is **Unresolved**; the cleaner treats it as missing. Other missing fields: 7,681 blank posting dates, 3,451 blank GL accounts (350 non-posting; 3,101 postings recovered from the account name), 6,841 blank cost centres, 6,180 blank regions (recovered from country), 1,506 blank fiscal years (derived from the period) and 21,784 blank approval statuses (kept as their own category). Every recovered value is flagged and written to a cell-level audit file; values that cannot be recovered stay blank.

## 6. Amount parsing

A strict grammar decides the number format, validated on all five amount columns. The cleaner's own scalar re-parse of all 763,410 amount cells (152,682 rows × 5 columns) agreed with its vectorised parser, and the independent parser written for Phase 7 agreed with the cleaner on presence and value for all five columns. The format counts below are Phase 7's independent classification.

| Format | Example | Counted in `actual_usd` |
|---|---|---:|
| Plain | `1234.56` | 106,776 |
| US | `1,234.56` | 18,451 |
| European | `1.234,56` | 6,936 |
| Decimal comma (one or two decimals) | `12,5` | 1,919 |
| Comma thousands with several groups | `1,234,567` | 24 |
| Comma pattern `n,nnn` (ambiguous, read as thousands; see below) | `1,234` | 9,317 |
| Placeholder or blank | `###`, `NA`, `-` | 9,259 |

Parentheses and a leading minus mean negative; `$` and surrounding spaces are tolerated; anything outside the grammar is "unparsed" and never guessed (none remained). **Ambiguous comma amounts:** about 9,100–9,300 amounts per column look like `n,nnn`, which could be a thousands separator or a three-decimal comma. The cleaner reads them as thousands. Phase 7 tested this reading against local amount ÷ FX rate: of 7,563 testable actuals, 6,940 fit the thousands reading and 0 fit the decimal reading (issue ISS-16, accepted, low residual risk). This is an **empirical interpretation, not a confirmed rule**.

## 7. Scale restoration

**Problem (Owner-stated):** some rows labelled `Thousands` or `Lakhs` were actually divided, and some labels do not describe the data (for example `000s` and `In thousands` rows look undivided). The label alone is therefore not trusted.

**Rule applied (Assumption, evidence-based, per row):**
1. **High confidence (price identity).** For GL 4100 and 5100 rows with a quantity and product family, |actual| should equal |quantity| × list price. If the ratio matches a division by 1,000 or 100,000, the row is restored. The list prices (Diagnostics 640, Home Comfort 180, Motors 260, Pumps & Valves 420, Spare Kits 45) were **inferred from the dataset's own undivided rows, not taken from an independent price list**, so this is a consistency test, not proof.
2. **Medium confidence (peer z-score).** Where no identity is available, the row's log-magnitude is compared with peers for the same GL and entity; far-low values are treated as divided, normal values as undivided; rows between the bands stay **undetermined**.

**Result (Verified):** 6,265 rows restored (5,326 at ÷1,000 and 939 at ÷100,000): 1,814 high-confidence and 4,451 medium-confidence; 145,994 undivided; 73 undetermined; 350 not applicable (non-posting). In the Posted P&L population 2,374 lines are restored. The as-reported value is always kept in the `*_parsed` columns; dashboards and SQL can show either basis. Undetermined rows receive no adjusted value. Status: **provisional**; the owner has not confirmed the rule or the price list.

## 8. Duplicate-candidate handling

- Repeated `document_no` is **not** a duplicate: one journal has several lines. 4,260 document numbers repeat across 8,540 rows (at most three lines per number). No two rows are identical apart from `row_id`.
- Candidate tiers are assigned on amount agreement within a document group: 2,332 same-sign field-match candidates, 1,587 sign-conflict candidates (equal in absolute value, possibly reversals) and 11 partial-agreement candidates: **3,930 candidate rows**.
- **Nothing is removed.** The setting that would remove same-sign candidates (`REMOVE_FIELD_MATCH_DUPLICATES`) is off. The effect of excluding them is shown as a sensitivity: on the Posted P&L population, excluding all candidate copies moves revenue from $202.65M to $201.02M. The duplicate rule (R11) is **Unresolved**.

## 9. Sign and FX issues

- **Signs.** Revenue and costs are mostly positive magnitudes with a minority of negatives, not debit/credit-signed. `sign_flag` records, for each row, whether all amount columns are non-negative (93,585 rows), all negative (19,614), mixed (6,053) or have exactly one column with the opposite sign (33,080 single-column flips). No sign is changed. The convention (R9) is **Unresolved**, so no variance is labelled favourable or unfavourable.
- **FX direction.** The direction USD = local ÷ rate fits the data: it reconciles for 98.7% of 125,397 testable rows. All 1,645 failures carry a rate of exactly 1.0 on a non-USD currency. 2,510 posting rows (2,517 in the raw file, which includes non-posting rows) have a rate of 0, which is invalid and is never defaulted to 1; 7,726 posting rows have a missing rate. USD-currency rows carry rates other than 1 in 22,567 of 23,577 rows with a usable rate, which is unexplained. Because actual USD is supplied as reported, no metric converts local currency; FX is a diagnostic only. FX direction (R8) is provisional; the zero and non-1.0 rate questions are **Unresolved**.

## 10. Entity and statement eligibility

- **Junk and unresolved entities.** `TEST ENTITY`, `Do not use`, `xxx` (by name) and codes `99` and `T999` (by code) mark 204 rows in total (173 by name, 144 by code); 16 further rows have neither a code nor a name and cannot be resolved. These are excluded, not deleted. Earlier Phase 1 documents quote 173 (names only); the cleaner's union of name and code is 204. Only `TEST ENTITY` is owner-confirmed as non-reporting; `Do not use` and `xxx` are an Assumption.
- **Statements.** Ten raw labels are normalised to two: P&L (145,534 rows) and Balance Sheet (7,148 rows). A balance-sheet line is out of scope for a P&L metric and the reverse (7,125 balance-sheet rows are excluded from the P&L population after earlier gates). The two are never added together. The measurement basis of balance-sheet lines (opening, closing or movement) is **Unresolved**.

## 11. Journal statuses

| Status | Rows | Treatment (Assumption R6, provisional) |
|---|---:|---|
| Posted | 65,381 | Eligible for reported totals |
| Pending | 22,072 | Excluded from reported totals; counted in the status diagnostic |
| Rejected | 21,795 | Excluded; counted in the status diagnostic |
| Parked | 21,650 | Excluded; kept separate from Rejected |
| Blank | 21,784 | Excluded; meaning unknown (**Unresolved**) |

There is no `Approved` value. The status mix is nearly identical for every entity and for P&L and balance-sheet rows (Posted about 42.8%), which is consistent with generated noise but is an observation, not a conclusion.

## 12. How each row gets its reason

Each of the three scopes (P&L actual, P&L variance, balance-sheet actual) assigns the **first** failed gate in a fixed order: (1) non-posting row, (2) junk entity, (3) entity unresolvable, (4) out-of-scope statement, (5) status not eligible, (6) period unresolvable, (7) amount missing, (8) scale undecidable. Gate 9 (removal as a duplicate) is defined in the specification but not used, because no row is removed.

| Scope | Eligible | Total rows | Identity checked |
|---|---:|---:|---|
| P&L actual | 58,340 | 152,682 | eligible + reasons = 152,682 |
| P&L variance (actual and budget present) | 55,043 | 152,682 | same |
| Balance sheet actual | 2,953 | 152,682 | same |

For P&L actual the reasons are: non-posting 350; junk entity 204; entity unresolvable 16; out-of-scope statement 7,125; status not eligible 82,986; period unresolvable 0; amount missing 3,637; scale undecidable 24; eligible 58,340. Secondary quality issues (blank cost centre, missing FX rate, duplicate candidate and so on) are **flags**, never reasons.

## 13. Cleaning validation

- The cleaner runs **43 in-memory checks** before writing and **27 read-back checks** on the files it wrote; all PASS in the approved run. Examples: rows in equal rows out; `row_id` unique and in raw order; non-posting rows keep a blank GL; an independent scalar re-parse of all 763,410 amount cells agrees with the vectorised parser; `actual_usd_adj` equals parsed × decided divisor on every decided row; undetermined rows have no adjusted value; the exclusion identity closes for each scope.
- Phase 7 re-ran the cleaner on a copy of the raw file: the output CSV was **byte-identical** (SHA-256 `c184b677…`), the raw copy was unchanged, and the cleaner's own checks showed 0 failures.
- Phase 7 independently re-derived every row's exclusion reason from the raw values and matched all 152,682 rows in all three scopes.

## 14. Row preservation and integrity

152,682 raw rows = 152,682 cleaned rows. The `row_id` sets are identical, order is preserved, the raw-value columns are preserved byte for byte, and the raw file's hash was recomputed after the run and unchanged. The reconciliation from 152,682 source rows to the dashboard populations is in [QA_AND_VALIDATION_SUMMARY.md](QA_AND_VALIDATION_SUMMARY.md).

## 15. What cleaning did not resolve

| Remains open | Handling |
|---|---|
| Meaning of blank, Pending and Parked statuses | Excluded from the baseline; shown as scenarios |
| Sign convention by account (notably GL 4190 discounts and GL 5120) | No sign changed |
| Duplicate rule | Candidates flagged, none removed |
| FX zero and non-1.0 rates | Not repaired |
| Scale ground truth and list prices | Restoration is provisional; as-reported amounts retained |
| Budget, forecast and prior-year summability per line | Assumed summable per line (project convention) |
| Provenance and licence | Not recorded |

The full register, with what cannot be concluded and what evidence would resolve each item, is [ASSUMPTIONS_LIMITATIONS_AND_RISKS.md](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md).
