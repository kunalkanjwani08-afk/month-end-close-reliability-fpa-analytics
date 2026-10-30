# Executive Summary

**Month-End Close Reliability & Financial Performance Analytics**

> **Data:** fictional NovaBridge Industries. The owner describes the data as synthetic; provenance and licence are not independently verified. This summary describes a simulated extract, not a real company.
> **Evidence labels:** Verified / Owner-stated / Assumption / Unresolved.

Related: [Metrics](FINANCIAL_METRICS.md) · [Risks](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md)

---

## The question

A group of six legal entities delivers its month-end ledger extract as one file whose `source_system` field carries five observed labels (the originating platforms have not been independently authenticated). The file mixes income-statement and balance-sheet lines, four kinds of amount (actual, budget, forecast, prior year), journals in different approval states, subtotal rows, test entities and numbers written in several formats and scales. **How much of it can be trusted, and how much do the answers change under the rules we cannot yet settle?**

## What was built

| Layer | Deliverable | Scale |
|---|---|---|
| Cleaning | Reproducible Python cleaner and QC report | 152,682 rows in, 152,682 out; none deleted; 43 source columns become 192 |
| SQL | DuckDB database, 12 views, 72 result tables | SQL outputs give the baseline results; dashboard filter states are computed in JavaScript (see the SQL guide, section on traceability) |
| Excel | 12-sheet formula-driven workbook | 3,819 formulas; 137 live reconciliation checks |
| Dashboard | Standalone interactive HTML, nine tabs | Filters, scenarios, cross-filtering, CSV export |
| QA | Independent pandas reference and project audit | 780 checks executed |

## What the numbers say (Posted-only, scale-adjusted, signs as recorded; provisional)

| Measure | Value |
|---|---|
| Rows qualifying for reported totals | 58,340 of 152,682 (38.2%) |
| Revenue | $202.65M |
| Cost base (COGS + People + Opex) | $176.33M |
| Result proxy (revenue less cost base; **not EBITDA**) | $26.32M (13.0% of revenue) |

1. **The population rule matters more than anything else.** Revenue is $202.65M counting Posted journals only, $404.38M excluding Rejected, and $471.58M counting every status. Which journals belong in the close is a decision the data cannot make.
2. **Budget variance is strikingly uniform.** On lines where actual and budget share a sign, revenue is 3.6% below budget and each cost section is 6.3%–6.4% above, in every month, entity, division and operating account. A pattern this regular is a property of the data; whether it reflects how the budget was built is unknown.
3. **Forecast error sits in sign-conflicted lines.** Lines where forecast and actual have opposite signs (10%–13% of lines) carry 89%–91% of the absolute forecast error. The file has no forecast version or date, so **no statement is made about forecast quality**.
4. **Gross profit is a range.** Gross margin is 54.2%, 51.1% or 54.8% depending on how sales discounts are treated; none is declared right.
5. **Cost is concentrated.** Materials is 36.8% of operating-cost activity; one division is 36.1% of the cost base; one entity is 25.8%. This is described, not judged.
6. **Scale restoration is a moderate sensitivity.** 6,265 amounts were restored to full scale; across the scale scenarios the result proxy ranges from $25.51M to $29.44M.

## How far the results can be trusted

- **Arithmetic and traceability: strong.** Python, SQL, Excel and the dashboard reconcile on identical populations. An independent pandas reference matched every table row within one cent and every ratio within 1e-9, and the 16,352-row gap between the source and the dashboard populations is fully explained.
- **Business meaning: provisional.** The Posted-only rule, scale restoration, FX direction and the variance-percentage guard are working conventions. The sign convention, duplicate handling and consolidation are unresolved. All headline numbers inherit this.
- **QA result.** 780 checks executed: 774 PASS, 1 FAIL, 1 BLOCKED, 4 NOT TESTED (plus 43 observations). No critical or high-severity issue. The one FAIL records a defect in the original run instructions (corrected and re-tested), not in the data or calculations.

## What was deliberately not done

Favourable or unfavourable labels; forecast-skill claims; a single gross-profit figure; EBITDA; DSO, DPO and working capital; close duration; consolidated group results. Each is blocked by information the extract does not contain (see the [risk register](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md)).

## Status and next decisions

| Item | Status |
|---|---|
| Scoping, cleaning, SQL analysis, Excel workbook, dashboard and independent validation | Complete |
| Documentation | Complete; in `docs/` |
| Public release | **Published 30 Oct 2026**, public, no licence |

**Open limitations:** the analytical rules listed in the [risk register](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md) (Posted-only eligibility, scale restoration, sign convention, duplicates, consolidation) remain provisional or unresolved. **Not tested:** Windows, native Microsoft Excel, Firefox, Safari, screen readers, a physical printer.

**Decisions still needed from the owner:** confirm or change the Posted-only rule, and provide the sign policy for the chart of accounts.
