# Project Overview

**Month-End Close Reliability & Financial Performance Analytics**

> **Status (updated at Phase 9 publication, 30 Oct 2026):** published as part of the complete project. The owner decided to publish the whole project, including the dataset he describes as synthetic. Dataset provenance and redistribution rights remain **owner-stated and not independently verified**. Any wording below from Phase 8 that calls the release *blocked*, *draft* or *not approved* describes the Phase 8 state and is superseded by [PUBLICATION_DECISION.md](PUBLICATION_DECISION.md). No calculation, figure or finding was changed.
> **Data:** NovaBridge Industries is a fictional group. The dataset is owner-described as synthetic; its provenance and redistribution licence are not independently verified. Figures below describe a simulated extract, not a real company.
> **Evidence labels:** **Verified** = checked against a project file or Phase 7 check; **Owner-stated**; **Assumption** = provisional project rule; **Unresolved**.

Related: [Executive summary](EXECUTIVE_SUMMARY.md) · [End-to-end workflow](END_TO_END_WORKFLOW.md) · [Metrics and methodology](FINANCIAL_METRICS_AND_METHODOLOGY.md) · [Assumptions, limitations and risks](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md)

---

## 1. Business context

A group of six legal entities closes its books each month. The ledger extract for the close arrives as a single extract. Its `source_system` field carries five observed labels (SAP, Oracle, NetSuite, Tally and Excel upload); the actual originating platforms have not been independently authenticated. The extract mixes income-statement lines with balance-sheet lines, actual with budget, forecast and prior-year amounts, journals in different approval states, subtotal rows, test entities and numbers written in several formats and scales.

A finance team cannot report performance from such a file until it can answer two questions: *how much of the extract can be trusted*, and *what changes if our rules for the rest are different?* This project answers both for one extract, and then analyses the trusted part.

## 2. Project objective

To build a documented, tested and reproducible chain from a messy month-end extract to financial analysis and reporting, where:

1. every source row is accounted for, eligible or excluded for exactly one stated reason;
2. every reported number states its population, rule and sensitivity;
3. SQL, Excel and the dashboard agree with each other and with an independent recalculation;
4. unresolved accounting questions are disclosed and carried as sensitivities, not settled silently.

## 3. Scope

| In scope | Out of scope |
|---|---|
| Cleaning and validating one extract of 152,682 rows | Conclusions about any real company |
| P&L analysis by period, entity, division, GL account and cost centre | Consolidated group results and intercompany eliminations (unresolved) |
| Actual versus budget, forecast and prior year | Forecasting models; forecast-skill assessment |
| Gross-profit scenarios; cost concentration | EBITDA, DSO, DPO, working capital, balance-sheet movements |
| Balance-sheet lines described separately, never added to the P&L | Month-end close duration and on-time close rate (the file has no close timestamps) |
| Reconciliation across Python, SQL, Excel and the dashboard | Tax or statutory reporting |

## 4. Analytical questions

1. How many rows qualify for reported totals, and why is each of the others excluded?
2. Which data-quality and control issues most affect reliability?
3. On the reportable population, how do actual results compare with budget, forecast and prior year, by period, entity, division and account?
4. How large is the forecast error, and where does it sit?
5. How much of the headline depends on each unresolved assumption (journal status, scale, sign, duplicates)?
6. How concentrated is the cost base?
7. Do Python, SQL, Excel and the dashboard agree on identical populations, and where they differ, why?

## 5. Data architecture

| Layer | What it holds | Where |
|---|---|---|
| Raw | 152,682 rows × 43 text columns; never edited; SHA-256 `a0e6edde…` | [data/raw/](../data/raw/fpa_monthly_close_raw_messy.csv.gz) |
| Cleaned (canonical) | 152,682 rows × 192 columns: the 43 source fields in raw and cleaned form plus parsed amounts, scale decisions, flags and exclusion reasons; SHA-256 `c184b677…` | [data/processed/](../data/processed/fpa_monthly_close_cleaned.csv.gz) |
| Database | DuckDB file with a staging table (`stg_close_raw`), the typed fact table (`fact_close`), an account dimension (`dim_account`, 32 accounts), 12 views and 72 `out_*` result tables | `data/processed/phase4_fpa.duckdb` (generated local file, not tracked by git) |
| Outputs | The 72 result tables as CSV with a manifest; a 12-sheet workbook; a standalone dashboard | [outputs/](../outputs/) |

Each row is a source extract record. The dataset contains 152,682 source extract records, including 350 non-posting subtotal/check records. These 350 records are not treated as ordinary posted journal lines. For the 152,332 other records, the actual, budget, forecast and prior-year amounts are four attributes of the same record, not separate records. The workflow is described step by step in [END_TO_END_WORKFLOW.md](END_TO_END_WORKFLOW.md).

## 6. Financial analysis approach

- **One population rule.** A row enters the reported P&L only if it is a posting (not a subtotal), belongs to a real entity, is an income-statement line, has the status Posted, has a resolvable period, has an actual amount, and has a decidable scale. The first failed test is its single exclusion reason. *(Assumption: the Posted-only rule is provisional.)*
- **Separate populations for separate questions.** Variance uses lines with both actual and budget (55,043); forecast comparison uses lines with a forecast (54,851); prior-year comparison uses lines with a prior-year amount (54,923); the balance sheet (2,953 lines) is described separately and never added to the P&L.
- **Signs as recorded.** The sign convention is unresolved, so no amount is flipped and no variance is labelled favourable or unfavourable. Variance is simply actual minus budget, and the same-sign, opposite-sign and zero-involved lines are shown separately.
- **Sensitivities, not corrections.** Journal status, scale restoration, sign handling and duplicate candidates are each varied to show how far the headline could move. None of these scenarios is presented as the answer.
- **Aggregate before comparing.** Percentages are computed from totals, never averaged across lines.

Definitions and formulas are in [FINANCIAL_METRICS_AND_METHODOLOGY.md](FINANCIAL_METRICS_AND_METHODOLOGY.md).

## 7. Deliverables

| Deliverable | Purpose | Guide |
|---|---|---|
| Cleaning script and QC report | Reproducible, row-preserving cleaning with an audit trail | [DATA_AND_CLEANING_METHODOLOGY.md](DATA_AND_CLEANING_METHODOLOGY.md) |
| SQL pipeline, 72 output tables, analysis report, 7-insight register | Validated financial analysis | [SQL_ANALYTICS_GUIDE.md](SQL_ANALYTICS_GUIDE.md) |
| Excel workbook (12 sheets) | Formula-driven review and live reconciliation | [EXCEL_FINANCIAL_ANALYSIS_GUIDE.md](EXCEL_FINANCIAL_ANALYSIS_GUIDE.md) |
| Interactive dashboard (nine tabs) | Exploration under filters and scenarios | [DASHBOARD_USER_GUIDE.md](DASHBOARD_USER_GUIDE.md) |
| Phase 7 QA package | Independent validation and issue log | [QA_AND_VALIDATION_SUMMARY.md](QA_AND_VALIDATION_SUMMARY.md) |

## 8. Key findings

All figures are USD, scale-adjusted (provisional), signs as recorded, on the Posted-only population unless stated. They are **observed arithmetic on a simulated extract under provisional rules**, not business conclusions.

| # | Finding | Evidence |
|---|---|---|
| 1 | **The population rule is the largest swing factor.** Reported revenue is $202.65M on Posted lines only, $404.38M excluding Rejected, and $471.58M on all statuses. The result proxy moves from $26.32M to $49.16M and $53.88M. Scale, sign and duplicate handling move revenue by 4%, 19% and 1% of the baseline (INS-01). | Verified (Phase 4 `i1`, Phase 7 `F_I1`) |
| 2 | **Headline, Posted-only baseline.** Revenue $202.65M; cost base (COGS + People + Opex) $176.33M; result proxy $26.32M, which is 13.0% of revenue, on 58,340 lines. The proxy is not EBITDA. | Verified (independent pandas reference, Phase 7) |
| 3 | **Budget variance is strikingly uniform.** On same-sign lines revenue is 3.6% below budget and each cost section is 6.3%–6.4% above, in all 36 months, all six entities, all five divisions and every one of the 20 operating accounts (INS-03). A pattern this regular is a property of the data; whether it reflects how the budget was built is unknown. | Verified arithmetic; business reading Low confidence |
| 4 | **Forecast error is concentrated on opposite-sign lines.** Lines whose forecast and actual have opposite signs (10% to 13% of lines) carry 89% to 91% of the absolute forecast error (INS-02). Because the extract has no forecast version or as-of date, no forecast-skill statement is made. | Verified arithmetic |
| 5 | **Gross profit is a range, not a number.** Gross margin on all eligible rows is 54.2% (discount account at its recorded sign), 51.1% (discounts always reduce revenue) or 54.8% (discounts excluded). On same-sign lines gross profit is $12.3M below budget: 57% from revenue below budget, 43% from COGS above (INS-04). | Verified |
| 6 | **Cost is concentrated.** Materials (GL 5100) is 36.8% of operating-cost activity against a 5.9% equal-share benchmark; Consumer Durables is 36.1% of the cost base across five divisions; US01 is 25.8% across six entities. High share is descriptive: it is not called inefficiency (rejected finding R7 in the Phase 4 report). | Verified |
| 7 | **Scale restoration matters moderately.** 6,265 rows (1,814 high-confidence, 4,451 medium-confidence) were restored to full scale; across the scale scenarios the result proxy ranges from $25.51M to $29.44M (INS-07). | Verified |

## 9. Important limitations

- The dataset is owner-described as synthetic; provenance and licence are unverified. Nothing here is evidence about a real company.
- Posted-only status, scale restoration, FX direction and the variance-percentage rule are provisional; the sign convention, duplicate handling and consolidation are unresolved.
- Forecast has no version or date; balance-sheet measurement basis is unknown; unit-of-measure equivalence (NOS versus EA) is unverified.
- 4,996 non-Posted lines are in no dashboard view (documented; see [DASHBOARD_USER_GUIDE.md](DASHBOARD_USER_GUIDE.md)).
- Not tested: Windows, clean-machine install, native Microsoft Excel, Firefox, Safari, screen readers, physical printer.

The complete register is [ASSUMPTIONS_LIMITATIONS_AND_RISKS.md](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md).

## 10. Final project status

Phases 1–7 are complete. Phase 7 executed 780 checks (774 PASS, 1 FAIL, 1 BLOCKED, 4 NOT TESTED, plus 43 INFO observations) and found no critical or high issue. Phase 8 documentation is in preparation. **Public release (Phase 9, 30 Oct 2026):** the owner decided to publish the complete project. Data provenance and redistribution rights remain unverified, build-machine (sandbox) paths remain in two QC files, and Windows, clean-machine and native-Excel tests were not performed.
