# Assumptions, Limitations and Risks

**Month-End Close Reliability & Financial Performance Analytics**

> **Data:** fictional NovaBridge Industries; owner-described as synthetic.
> **Evidence labels:** Verified / Owner-stated / Assumption / Unresolved.
> **No resolutions are invented.** Where the project cannot resolve an item, this register says what evidence would.

Related: [Executive summary](EXECUTIVE_SUMMARY.md) · [Metrics](FINANCIAL_METRICS.md) · Primary source: [`excel/issue_log.xlsx`](../excel/issue_log.xlsx)

---

## 1. Summary

| # | Item | Class | Independent validation issue | Publication blocker? |
|---|---|---|---|---|
| 1 | Synthetic status, provenance and licence unverified | Unresolved | ISS-06 | **Yes** |
| 2 | Posted-only eligibility (R6) | Assumption | ISS-07 | No (must be presented as provisional) |
| 3 | Scale restoration | Assumption | ISS-08 | No |
| 4 | Sign convention (R9) | Unresolved | ISS-09 | No |
| 5 | FX anomalies and zero rates | Unresolved | ISS-10 | No |
| 6 | Duplicate candidates retained (R11) | Unresolved | ISS-11 | No |
| 7 | Forecast version and as-of dates missing | Unresolved | ISS-12 | No |
| 8 | Gross-profit discount treatment | Unresolved | ISS-13 | No |
| 9 | Balance-sheet measurement basis | Unresolved | ISS-14 | No |
| 10 | NOS versus EA unit equivalence | Unresolved | ISS-15 | No |
| 11 | Ambiguous comma-formatted amounts | Empirical interpretation | ISS-16 | No |
| 12 | 4,996 non-Posted records in neither dashboard population | Documented gap | ISS-18 | No |
| 13 | GL / account-group mapping not authenticated | Assumption (accepted limitation) | ISS-19 (Documentation supplemental; **not** in the independent validation issue log, which is unchanged) | No |
| 14 | Windows and clean-machine reproducibility untested | Not tested | ISS-05 | **Yes** (Independent validation recommendation) |
| 15 | Native Microsoft Excel validation untested | Not tested | stated in Excel workbook and 7 | No |
| 16 | Firefox, Safari, screen reader, physical printer untested | Not tested | UI50–UI52 | No |
| 17 | QC reports contain machine-specific paths | Open defect | ISS-03 | **Yes** |

Items 1, 14 and 17 are the ones independent validation names as conditions for public publication (ISS-06, ISS-03 and ISS-05). The repository is public and contains the raw dataset (gzip) and the cleaned dataset, so item 1 is a live exposure, not only a future-publication risk.

---

## 2. The register

### 1. Dataset synthetic status, provenance and licence are not independently verified

- **What is uncertain.** The project owner states the data is synthetic. No provenance record, generation method or redistribution licence exists to verify that ([`docs/DATA_PROVENANCE.md`](../docs/DATA_PROVENANCE.md)). The extract contains person-like cost-centre owner names and system user IDs; this is harmless if the data is synthetic and sensitive if it is not. The raw CSV has been tracked by git since the first stage (commit `1d601c0`) and the repository has a GitHub remote. **The documentation correction round verified (2026-10-30, read-only GitHub API call) that the repository is public and that the raw CSV is present in the public `main` branch.** Earlier project notes recorded the repository as created private; when it became public is not known.
- **Why it matters.** Redistribution rights and privacy exposure decide whether anything can be published. The dashboard embeds line-level amounts for 136,330 lines and document numbers for 58,340 lines.
- **Current handling.** Owner-stated label kept ("owner-described as synthetic"). **Not private:** the repository is public, and the raw dataset was committed in earlier history (an uncompressed copy stays in git history). Redistribution of the data remains uncleared; making the repository private later would not erase history, forks or copies already downloaded. The dashboard loads no external resources; user IDs and cost-centre owner names are not embedded in the dashboard.
- **What cannot safely be concluded.** That the data is synthetic; that it may be redistributed; that any result describes a real company; that the extract is free of personal data.
- **Evidence that would resolve it.** A written provenance and generation statement from the owner, a licence or an explicit statement of ownership, and an owner decision on the public repository and its history (the raw file is in public `main`).

### 2. Posted-only (R6) eligibility is provisional

- **What is uncertain.** Whether only journals with status `Posted` belong in reported totals, and what a blank status means. Observed statuses: Posted, pending, Rejected, Parked and blank; there is no Approved. The mix is almost identical for every entity (Posted about 43%, others about 14% each), which a real posting workflow would rarely produce.
- **Why it matters.** It is the largest swing factor in the headline: revenue is $202.65M on Posted only, $404.38M excluding Rejected and $471.58M on all statuses. Only 58,340 of 152,682 rows (38.2%) are reported.
- **Current handling.** Posted-only is the baseline; the dashboard and workbook show the alternative populations (a journal-status diagnostic over 136,330 lines) and label the rule provisional.
- **What cannot safely be concluded.** That reported revenue or the result proxy is the true period result; that unposted journals are errors; that a blank status means unposted.
- **Evidence that would resolve it.** The source systems' status definitions and the owner's decision on each status, ideally with the posting workflow that generated them.

### 3. Scale restoration is provisional

- **What is uncertain.** The `report_scale` labels are unreliable (owner-stated). The cleaner restores a row's scale by a written rule: 6,265 rows were restored (1,814 HIGH confidence via an identity between GL 4100 and 5100 unit values and inferred list prices; 4,451 MEDIUM confidence via peer robust z-scores). 73 rows stayed undetermined and are blank.
- **Why it matters.** Across the scale scenarios the result proxy ranges from $25.51M to $29.44M, and scale moves revenue by about 4% of the baseline. MEDIUM-confidence restorations rest on peer comparison rather than a direct identity.
- **Current handling.** The raw value and the decision are kept side by side; the scenario selectors let the reader exclude MEDIUM or all restored rows or revert to as-reported amounts.
- **What cannot safely be concluded.** That any individual restored amount is correct; that the HIGH-confidence price identity reflects a real price list (the list prices are inferred from the data).
- **Evidence that would resolve it.** Source-system scale metadata per row or per feed, and an actual price list to test the identity independently.

### 4. Sign convention is unresolved (R9)

- **What is uncertain.** Whether negative amounts are credits, reversals, contra items or noise. Observed negative shares (Project scoping–3 profile of rows labelled Actual scale): GL 4190 discounts 57.8%, GL 5120 purchase price variance 31.7%, GL 7200 FX gain or loss 50.4%, most other accounts 7%–15%. In the cleaned file 33,080 rows have exactly one amount column of opposite sign to the others.
- **Why it matters.** Variance direction, gross profit and the result proxy depend on it. Opposite-sign lines carry 89%–91% of absolute forecast error, and 1,587 duplicate candidates conflict in sign.
- **Current handling.** No sign is changed. Costs are positive magnitudes. No variance is labelled favourable or unfavourable. Same-sign, opposite-sign and zero-involved lines are shown separately, and sign sensitivities are available (all-non-negative rows only; exclude single-column flips).
- **What cannot safely be concluded.** That an opposite-sign line is an error; that a positive variance is good or bad; that profit measures are right in sign.
- **Evidence that would resolve it.** The chart of accounts with a debit/credit policy per account, and source rows that carry a debit/credit indicator.

### 5. FX anomalies and zero FX rates remain unresolved

- **What is uncertain.** The direction USD = local ÷ rate fits 98.7% of 125,397 testable rows. 2,510 posting rows (2,517 in the raw file) have a rate of exactly 0, 7,726 posting rows have a missing rate, all 1,645 failures of the direction test carry a rate of exactly 1.0 on a non-USD currency, and 22,567 of 23,577 USD-currency rows with a usable rate carry a rate other than 1, which is unexplained.
- **Why it matters.** If the supplied USD amounts are wrong where the rate is anomalous, totals and entity comparisons are affected.
- **Current handling.** Supplied USD columns are used as reported. FX is a diagnostic only; no zero rate is defaulted to 1; no amount is converted. FX direction (R8) is provisional.
- **What cannot safely be concluded.** That USD amounts on anomalous-rate rows are right or wrong; that the zero rates are data-entry errors.
- **Evidence that would resolve it.** The source FX-rate tables and the conversion policy of each source system.

### 6. Duplicate candidates are retained

- **What is uncertain.** 3,930 rows are duplicate candidates (including 1,587 with sign conflict). Repeated `document_no` is not a duplicate: 4,260 numbers repeat across 8,540 rows, no two rows are identical apart from `row_id`, and one journal legitimately has several lines. Whether any candidate is a true duplicate is not known (R11).
- **Why it matters.** Excluding all copy candidates moves Posted revenue from $202.65M to $201.02M (under 1%). It is a small effect on the headline but could matter for specific cells.
- **Current handling.** All candidates are flagged and retained; the setting that would remove same-sign candidates is off; exclusion is offered as a dashboard scenario and a SQL sensitivity.
- **What cannot safely be concluded.** That the retained rows are all unique postings, or that the candidates are duplicates.
- **Evidence that would resolve it.** Source-system journal-line keys and the posting logic, or the owner's duplicate rule.

### 7. Forecast version and as-of dates are missing

- **What is uncertain.** The extract has no forecast version, as-of date or snapshot. It is unknown whether the forecast was made before or after each period closed, and whether the per-line forecast values can be summed.
- **Why it matters.** Without that, a forecast comparison cannot be read as forecast quality.
- **Current handling.** The project computes WAPE and bias as comparisons of two columns and states in the SQL, workbook and dashboard that no forecast-skill statement is made.
- **What cannot safely be concluded.** That the forecast is accurate or inaccurate in general; that bias is a forecasting habit; any forecast-skill ranking.
- **Evidence that would resolve it.** Forecast snapshots with version and as-of dates.

### 8. Gross-profit discount treatment is unresolved

- **What is uncertain.** GL 4190 (sales discounts and rebates) is negative on about 58% of lines and positive on the rest, so it is unclear whether it should reduce, add to, or be excluded from revenue.
- **Why it matters.** Gross margin on all eligible rows is 54.2% (as recorded, S1), 51.1% (always reduces revenue, S2) or 54.8% (excluded, S3).
- **Current handling.** All three treatments are shown side by side, none is declared authoritative, and S1 is labelled the as-recorded view.
- **What cannot safely be concluded.** A single gross profit or margin; the true size of discounts.
- **Evidence that would resolve it.** The sign policy for GL 4190 (item 4) and the source documents for discounts.

### 9. Balance-sheet measurement basis is not established

- **What is uncertain.** Whether balance-sheet amounts are opening balances, closing balances or movements. 2,953 lines qualify as eligible balance-sheet actuals.
- **Why it matters.** Balance-sheet amounts cannot be summed across periods and cannot support ratios until the basis is known.
- **Current handling.** Balance-sheet lines are described separately (coverage, by-account, spread, volatility) and never added to the P&L. DSO, DPO, working capital and balance-sheet ratios are not computed.
- **What cannot safely be concluded.** Any balance-sheet position, movement, liquidity or working-capital statement.
- **Evidence that would resolve it.** A definition of the balance-sheet fields from the source systems or owner, and a matching opening-closing roll-forward.

### 10. NOS versus EA unit equivalence is unverified

- **What is uncertain.** Units of measure `EA`, `Each` and `ea` look equivalent; `NOS` (1,231 rows) is unconfirmed. Unit-value equality between product revenue (GL 4100) and materials cost (GL 5100) is also unverified.
- **Why it matters.** Mixing units would distort price and the HIGH-confidence scale identity in item 3.
- **Current handling.** Units are normalised conservatively; no unit economics, price-volume-mix or per-unit margin is produced; the unit-value equality is tested and reported (`e5_unit_value_equality`) without being used as a conclusion.
- **What cannot safely be concluded.** Per-unit price, cost or margin; that NOS equals EA.
- **Evidence that would resolve it.** The unit-of-measure master data or an owner mapping.

### 11. Ambiguous comma-formatted amounts have a documented empirical interpretation

- **What is uncertain.** About 9,100–9,300 amounts per column look like `n,nnn`, which could be a thousands separator or a three-decimal comma. The cleaner reads them as thousands.
- **Why it matters.** The other reading would change those amounts by a factor of 1,000.
- **Current handling.** Independent validation tested the reading against local amount ÷ FX rate: of 7,563 testable actuals, 6,940 fit the thousands reading and 0 fit the decimal reading. independent validation judged the evidence to support the current reading (ISS-16, low residual risk).
- **What cannot safely be concluded.** That every `n,nnn` amount is a thousands value; the test covers only the rows where an FX check is possible.
- **Evidence that would resolve it.** The source-system number format per feed.

### 12. The 4,996 non-Posted records failing the amount or scale gates appear in neither dashboard population

- **What is uncertain.** Nothing about the count: 152,682 − 58,340 − 77,990 = 16,352, and 4,996 of those are non-Posted lines that would otherwise be in the status diagnostic: 4,958 have no actual amount and 38 have an undetermined scale. The diagnostic population drops only the status gate, so these fail another gate and are in no dashboard view.
- **Why it matters.** The journal-status table on the Data Quality tab does not show every non-Posted line, so it should not be read as the full status picture.
- **Current handling.** Counted in the row accounting, the SQL analysis waterfall and the workbook's Data Quality sheet; documented in the independent validation report and in [the dashboard guide](DASHBOARD_USER_GUIDE.md). The dashboard was not changed (ISS-18, Low).
- **What cannot safely be concluded.** That the status diagnostic is complete; the value of these lines (they have no actual amount or no determined scale).
- **Evidence that would resolve it.** An owner decision whether to display them, as a count-only row in the status table, in a future dashboard revision. This is a documentation limitation, not a calculation error.

### 13. The GL / account-group mapping has not been authenticated against an authoritative chart of accounts

- **What is uncertain.** `dim_account` (32 accounts) is built from the extract itself. The mapping from GL to name, group, FS line and statement was checked for one-to-one consistency (`a8_account_mapping_consistency`; load-validation checks L49 and L52–L55; a conflict would fail the load). Whether those mappings are right has not been checked against a real chart of accounts.
- **Why it matters.** Section assignment decides whether a line is revenue, COGS, people, opex or balance sheet, and therefore every total.
- **Accepted limitation (ISS-19, documentation supplemental).** The GL/account_group/section mapping is internally consistent and was used in the independent recalculation, but its accounting correctness has not been independently authenticated against an authoritative chart of accounts. The independent validation issue log lists ISS-01 to ISS-18 and is deliberately not edited; ISS-19 is recorded only in documentation documents.
- **Current handling.** The mapping is internally consistent and is used as provided. No account was reclassified or invented.
- **What cannot safely be concluded.** That the account classification is correct in an accounting sense, or that the 32 accounts are the complete chart.
- **Evidence that would resolve it.** The owner's chart of accounts with section and statement per account.

### 14. Windows and clean-machine reproducibility remain untested

- **What is uncertain.** Every re-run was on a Linux container with packages already installed (numpy 2.5.3 installed against a pin of 2.4.6). No virtual-environment install from `requirements.txt` and no Windows run was done, although the owner works on Windows with VS Code. The cleaner takes about 4–5 minutes and about 1.25 GB of memory.
- **Why it matters.** The corrected run instructions have not been shown to work on the target machine, and the pins have not been exercised in a fresh install.
- **Current handling.** README and guides state the limit. `HOW_TO_RUN.txt` was corrected after independent validation (ISS-01, ISS-02) and regression-tested on Linux. The dashboard-build command is not in `HOW_TO_RUN.txt` (it ran with exit 0 in independent validation); adding it is a recommendation for the next phase.
- **What cannot safely be concluded.** That the project installs and runs on Windows or on a clean machine; that `requirements.txt` is complete (Playwright and LibreOffice, used only for QA, are not listed).
- **Evidence that would resolve it.** A fresh-venv install and a full documented run on the Windows laptop, with `pip check`.

### 15. Native Microsoft Excel validation remains untested

- **What is uncertain.** The workbook was written with XlsxWriter and checked with LibreOffice 24.2 only. Table styles, conditional-format colours, fonts, frozen panes, filters, navigation links and chart appearance in Excel have not been observed.
- **Why it matters.** The workbook is the main finance-facing deliverable.
- **Current handling.** The limit is stated in the workbook guide and the Excel workbook and independent validation reports; 3,819 formulas were recalculated independently and matched.
- **What cannot safely be concluded.** That the workbook looks or behaves as intended in Excel.
- **Evidence that would resolve it.** Opening and walking the workbook in Microsoft Excel and recording the result.

### 16. Firefox, Safari, screen-reader and physical-printer testing remain outstanding

- **What is uncertain.** The dashboard was tested in headless Chromium only. Keyboard operation and ARIA attributes were asserted programmatically, but no assistive-technology test, no other browser and no physical printer were used (Independent validation UI50, UI51, UI52).
- **Why it matters.** Layout, scripts, accessibility and print output may differ.
- **Current handling.** Stated in the dashboard guide and independent validation report; no accessibility, cross-browser or print-quality claim is made.
- **What cannot safely be concluded.** That the dashboard works in Firefox or Safari, is accessible, or prints correctly on paper.
- **Evidence that would resolve it.** Manual runs in Firefox and Safari, an NVDA/JAWS/VoiceOver walk-through, and a physical print.

### 17. QC reports contain machine-specific paths requiring portable handling

- **What is uncertain.** Nothing about the fact: `data/processed/QC_Report.txt` and `qc_summary.json` record the build environment's input and scratch paths, and they are not git-ignored (ISS-03). documentation verified that the files still contain them and did not alter them.
- **Why it matters.** Paths disclose the build environment's layout and the files would be published with the repository. Rule 10 of the documentation brief forbids exposing machine paths.
- **Current handling.** Not changed in documentation (the cleaned and QC files are preserved). This documentation package quotes no machine path. Related findings: `tests/dashboard_browser_qa.py` finds the palette validator through a machine-specific glob (ISS-04), and the one-off validation scripts (not published) hard-codes a scratch directory.
- **What cannot safely be concluded.** That the repository is ready to publish.
- **Evidence that would resolve it.** Regenerating or sanitising the QC files with a portable (repository-relative) path, adding them to `.gitignore` if appropriate, and re-checking hashes and tests. This is a publication action requiring owner approval, because it modifies the data cleaning QC outputs.

---

## 3. Dependencies between items

- Items 3, 4, 8 and 10 interact: the scale identity (3) depends on unit equality (10), gross profit (8) depends on the sign policy (4), and the sign policy also governs the 1,587 sign-conflict duplicates (6).
- Items 1, 14 and 17 are the practical open questions. Resolving items 2–11 would change the numbers; resolving 14–17 would change only what has been verified.
