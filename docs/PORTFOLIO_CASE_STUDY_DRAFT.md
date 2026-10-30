# Portfolio Case Study (unpublished draft)

**Month-End Close Reliability & Financial Performance Analytics**

> **Status (updated at Phase 9 publication, 30 Oct 2026):** published as part of the complete project. The owner decided to publish the whole project, including the dataset he describes as synthetic. Dataset provenance and redistribution rights remain **owner-stated and not independently verified**. Any wording below from Phase 8 that calls the release *blocked*, *draft* or *not approved* describes the Phase 8 state and is superseded by [PUBLICATION_DECISION.md](PUBLICATION_DECISION.md). No calculation, figure or finding was changed.
> **Data:** fictional NovaBridge Industries; owner-described as synthetic, not independently verified.
> **Content rules for this draft:** aggregate figures only; no line-level data, document numbers, user IDs or cost-centre owner names; no machine paths; no claims that were not tested.

---

## 1. In one paragraph

I took a deliberately messy month-end ledger extract for a fictional six-entity group (152,682 source extract records, 43 text columns; 350 of the records are non-posting subtotal/check records, not treated as ordinary posted journal lines) and built an auditable chain from raw file to finance reporting: a row-preserving Python cleaner, a DuckDB/SQL analysis layer, a formula-driven Excel workbook and an interactive dashboard, all reconciled against an independent recalculation. The main lesson is a finance one: **before asking how the business performed, decide which journals count**. In this extract that single rule moves revenue from $202.65M to $471.58M, and the project is built to show that range rather than hide it.

## 2. The problem

A month-end extract is not a report. This one mixes income-statement and balance-sheet lines, actual, budget, forecast and prior-year amounts, five approval states, subtotal rows, test entities, a `source_system` field with five observed labels (the originating platforms have not been independently authenticated) and numbers written in several formats and scales. A finance team that sums it will produce a confident, wrong number.

The project asked two questions: **how much of the file can be trusted**, and **how far do the answers move under rules we cannot yet settle?**

## 3. What I built

| Layer | What it is | Why it exists |
|---|---|---|
| Cleaning | Python script; every source row kept; each decision recorded beside the original value | So that nothing is lost and every change can be audited |
| Rules | One exclusion reason per row, in a fixed order; 58,340 of 152,682 rows (38.2%) qualify for the reported P&L | So the population is explainable row by row |
| SQL | DuckDB database, 12 views, 72 result tables | One definition of each population; SQL outputs give the baseline results; dashboard filter states are computed in JavaScript and were checked in tested states only |
| Excel | 12 sheets, 3,819 formulas, 137 live reconciliation checks | A reviewer can see how each number is built |
| Dashboard | Standalone HTML, nine tabs, filters, assumption scenarios | Explore results and test how sensitive they are |
| QA | An independent pandas reference that imports none of the project code | A check that cannot share the project's mistakes |

## 4. What I found (aggregate, provisional, simulated data)

- **The status rule dominates.** Revenue is $202.65M on Posted journals only and $471.58M on all statuses. Scale, sign and duplicate handling move it far less (about 4%, 19% and under 1%).
- **A suspiciously regular budget variance.** On lines where actual and budget share a sign, revenue is 3.6% below budget and every cost section is 6.3%–6.4% above, in every month, entity and division. I treated that as a property of the data worth questioning, not as a business conclusion.
- **Forecast error lives in sign-conflicted lines.** Opposite-sign lines are 10%–13% of lines but 89%–91% of absolute forecast error. With no forecast version or date in the file, I refused to say anything about forecast quality.
- **Gross profit is a range.** 54.2%, 51.1% or 54.8% margin depending on how one contra-revenue account is treated. I showed all three.
- **Cost concentration is described, not judged.** Materials is 36.8% of operating-cost activity; I rejected my own first reading of that as "inefficiency" because share alone does not show it.

## 5. Decisions I would defend in an interview

1. **Keeping every row.** Excluding by flag rather than deleting meant the 152,682 = 152,682 reconciliation could be proved.
2. **Not flipping signs.** The convention was unknown, so I showed same-sign and opposite-sign lines separately and refused to label anything favourable or unfavourable.
3. **A guarded variance percentage.** When positive and negative budget lines net to near zero, a percentage is meaningless; the project hides it below a stated threshold and shows the sensitivity to that threshold.
4. **Range over point estimate.** Where the data could not settle a question (status, scale, discounts), the output carries scenarios, not a favourite.
5. **Independent validation.** The reference code was written without importing the project's code, and negative controls proved the comparison could fail.
6. **Reporting what failed.** The one FAIL among 780 checks is kept in the evidence with its explanation: it recorded a defect in my run instructions, not in the data.

## 6. What went wrong, and what I learned

- **The run instructions were wrong.** Phase 7 found that the documented cleaner command wrote its output to the wrong folder, and that the documented test order failed two tests after a database rebuild. Both were documentation defects; I corrected the instructions and regression-tested the fix.
- **A dashboard bug was found only by a new regression test.** The print routine left a section open in the live page afterwards.
- **Some of my early evidence was not independent.** An in-page "reconciled" badge compared the dashboard with itself; it was relabelled, and independence came from the separate pandas reference.
- **A population gap I had not documented.** 4,996 non-Posted lines appear in no dashboard view. Phase 7 found it; it is now disclosed.

## 7. What this does not show

- Anything about a real company. The data is owner-described as synthetic and that is unverified.
- That the headline numbers are right. They depend on provisional rules (Posted-only, scale restoration, FX direction) and unresolved conventions (signs, duplicates, consolidation).
- Forecast skill, EBITDA, working capital, close duration or consolidated results.
- That it works outside the tested environment: it was tested on Linux and in headless Chromium. Not tested: Windows, a clean-machine install, native Microsoft Excel, Firefox, Safari, screen readers, a physical printer.

## 8. Skills evidenced

Only skills with a deliverable behind them:

- **FP&A and management accounting:** budget, forecast and prior-year variance; guarded percentages; gross-profit scenarios; cost concentration; reconciliation across tools.
- **SQL:** DuckDB views, macros, window functions, scenario tables, validation queries.
- **Python:** pandas data cleaning, deterministic pipelines, fail-closed gates, pytest.
- **Excel:** formula-driven models, live reconciliation checks, Excel tables and charts (generated with XlsxWriter; verified with LibreOffice, not Excel).
- **BI and dashboarding:** a standalone HTML dashboard with filters, scenarios and cross-filtering (hand-built; no BI product such as Power BI was used).
- **Data quality and controls:** exclusion accounting, lineage, issue logging.

## 9. How the work was done

The project was developed with an AI assistant (Claude Code) doing much of the implementation, under my direction, with my review at each phase. The owner should decide how to state this when the case study is published; it should be stated accurately.

## 10. Evidence available on request

Aggregate and documented only: the QA report (780 checks), the assumptions and limitations register (17 items, plus the accepted ISS-19 limitation on the GL/account mapping), the reconciliation workbook, the dashboard (privately, because it embeds line-level data) and the workbook.

## 11. Before this is ever published (owner checklist)

| Item | Needed |
|---|---|
| Data provenance and redistribution licence | Written confirmation from the owner |
| Public repository holding the raw file | **Verified public with the raw CSV in `main` (2026-10-30).** Owner to decide manually whether to make it private, knowing that this does not erase history, forks or downloaded copies; re-check current visibility |
| Build-machine paths in two QC files | Sanitise or regenerate |
| Windows and clean-machine run | Execute and document |
| Dashboard | Decide whether the line-level payload may be shared at all |
| Personal data | Confirm that cost-centre owner names and user IDs are synthetic |
| Wording | Replace "I" statements with the owner's own account; remove anything the owner cannot stand behind |
