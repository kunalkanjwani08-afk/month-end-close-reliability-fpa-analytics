# Dashboard User Guide

**Month-End Close Reliability & Financial Performance Analytics**

> **Data:** fictional NovaBridge Industries; owner-described as synthetic. The dashboard embeds line-level data and should not be shared until provenance, licence and sensitivity are reviewed.
> **Evidence labels:** Verified / Owner-stated / Assumption / Unresolved.
> **Testing boundary:** tested in headless **Chromium** only (Dashboard and independent validation). Not tested: Firefox, Safari, screen readers or other assistive technology, a physical printer, Microsoft Excel (not relevant here), Windows.

Related: [Metrics](FINANCIAL_METRICS.md) · [Risks](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md)

---

## 1. What it is

[`dashboard/fpa_financial_analytics_dashboard.html`](../dashboard/fpa_financial_analytics_dashboard.html) is a single standalone HTML file (7,317,802 bytes) with embedded CSS, JavaScript and data. It loads no external resources. It is built from [`src/dashboard_builder.py`](../src/dashboard_builder.py) with `dashboard_template.html`, `dashboard_style.css`, `dashboard_core.js` and `dashboard_views.js`.

It lets a reviewer explore the SQL analysis results under filters and assumption scenarios. It is a review tool for a simulated extract, not a decision system.

## 2. Opening it

1. Double-click the file, or open it from a browser's File menu. A current Chromium-based browser is the only environment tested.
2. No server, install or internet connection is needed. Page load in headless Chromium was about 0.5–0.7 s on the Linux test machine (one run; not a benchmark).
3. If the page shows no data, the browser has blocked scripts for local files; try another Chromium-based browser. This has not been tested in other browsers.

## 3. Layout

- **Header:** logo, title, a one-line scope description that updates with the live state (scale basis, duplicates, sign handling, population, filters), two check badges, and the action buttons: *Export all filtered lines (CSV)*, *Print report / PDF* and the theme toggle.
- **Global filters** (below the header): year chips, quarter chips, From/To month, and searchable multi-selects for Entity, Division, Section, GL account and Cost centre; four scenario selectors; *Reset filters* and *Undo*.
- **Active-filter chips** list every active filter, scenario and chart selection.
- **Nine tabs** (arrow keys move between tabs).

## 4. The nine tabs

| # | Tab | What it shows |
|---|---|---|
| 1 | **Executive Overview** | Five KPI cards (below), each with a monthly trend, a year-on-year badge and a drill-through button; monthly revenue, cost base and result proxy; result-proxy bridge from revenue to result; signed total by section; revenue and result proxy by entity; revenue by division; proxy margin by entity; budget variance snapshot |
| 2 | **Trends & Performance** | Monthly trend of a selected metric; entity trend; result proxy margin by month; quarterly totals; seasonality; year summary with true year-over-year |
| 3 | **Budget & Variance** | Variance by section (net versus gross); monthly net variance for revenue and for cost base; cumulative net variance versus budget; sign-category profile; largest entity × GL variances; entity × section variance %; sign-population sensitivity |
| 4 | **Forecast & Prior-Year** | Forecast and budget accuracy by population, WAPE by quarter, where the forecast error sits (opposite-sign lines), actual versus the dataset's prior-year column |
| 5 | **Drivers & Concentration** | Ranked cost accounts and Pareto by GL; cost-centre view (People + Opex); concentration (share, HHI); cost mix and cost-to-revenue by year; persistent one-sided deviations; salary per FTE |
| 6 | **Gross Profit & Scenarios** | Gross profit under the three discount treatments (S1, S2, S3) with a row-set toggle; gross margin by year; gross profit by entity; gross profit versus budget on same-sign lines; sensitivity of the headline to unresolved assumptions |
| 7 | **Insights & Actions** | Dynamic insights recomputed for the current selection (observation, scope, calculation, drivers, evidence, confidence, hypothesis, action, evidence needed, monitoring) and fixed SQL analysis findings labelled as portfolio-level (they do not change with filters) |
| 8 | **Data Quality & Methodology** | Data readiness gate, row accounting for all source rows, flag exposure, journal-status diagnostic for the current selection, metric dictionary, open assumptions, provenance and file details, baseline reconciliation |
| 9 | **Detail Lines** | Line-level table with search, sort and pagination (50 rows per page) |

## 5. KPIs

| KPI | Definition | Default value |
|---|---|---:|
| Revenue | Sum of scale-adjusted actual revenue, Posted-eligible lines | $202.65M |
| Cost base | COGS + People + Opex | $176.33M |
| Result proxy | Revenue − cost base. **Not EBITDA** | $26.32M |
| Revenue vs budget | Actual − budget on lines with a budget (net variance, with a guarded %) | see dashboard |
| Cost base vs budget | Same for the cost sections | see dashboard |

Default values are for 58,340 lines with all filters off. They match the independent reference within a cent (Dashboard and independent validation).

## 6. Filters and controls

| Control | Behaviour | Tested |
|---|---|---|
| Year and quarter chips | Toggle periods | Dashboard, independent validation (Chromium) |
| From / To month | Month range | Yes |
| Entity, Division, Section, GL account, Cost centre | Searchable multi-select; cost centre includes "(no cost centre)" | Yes |
| Variance-comparison population | All comparable / same-sign / opposite-sign / zero-involved. **Changes only:** Budget & Variance, the Executive variance KPI, the prior-year comparison table and the variance insights. **Does not change:** forecast accuracy, line counts, revenue and cost KPIs, gross profit or data-quality tables (authority: `src/dashboard_core.js` note text and `sVar` wiring; `fcPops()` does not read the selector) | Yes |
| Scale basis | Adjusted all (baseline) / as reported / restore HIGH confidence only / exclude MEDIUM / exclude all restored | Yes |
| Duplicate candidates | Retained (baseline) / exclude same-sign candidates / exclude all copy candidates | Yes |
| Sign handling | As recorded (baseline) / all-non-negative rows only / exclude single-column sign flips | Yes |
| Reset filters | Restores the default state and full data | Yes |
| Undo | Reverts the last change only; disabled at the default state | Yes |
| Theme toggle | Light and dark; choice stored in the browser; the system preference is used when nothing is stored | Yes |

When any scenario selector is changed, a visible **SCENARIO ACTIVE** flag and the changed settings appear in the header. Scenarios are sensitivities, not corrections.

## 7. Cross-filtering

- Clicking a bar, a heat-map row, a bridge step or a trend point applies a **chart selection** (for example *Entity = US01* or *Month = Dec 23*). Clicking the selected bar again, the chip's ×, *Undo* or *Reset* clears it.
- A bar that would produce an empty result under the current filters is **disabled** (greyed, removed from the tab order) and a notice explains why. If a later filter makes a chart selection empty, the selection is removed with a visible notice.
- The detail table shows only the lines in the current selection.

## 8. Population scope

The dashboard does not use one population on every page.

| Population | Lines | Used for |
|---|---:|---|
| Posted-eligible P&L lines (main) | 58,340 | KPIs, trends, drivers, gross profit, detail lines |
| Comparison populations (subsets with a budget, forecast or prior-year amount) | 55,043 budget; 54,851 forecast; 54,923 prior year | Variance and prior-year comparisons use their own subsets; forecast views use the forecast subset |
| Non-Posted lines, embedded for the status diagnostic | 77,990 | The journal-status table on the Data Quality tab only |
| Balance-sheet lines | 2,953 | Described in the workbook and SQL; never added to the P&L |

**Hidden population (ISS-18, documented, not corrected).** 152,682 source rows − 58,340 Posted-eligible − 77,990 non-Posted diagnostic = 16,352. Of these, 4,996 lines have a status other than Posted and also lack an actual amount (4,958) or have an undetermined scale (38). They are counted in the row accounting and the SQL analysis waterfall, but they are **in no dashboard view** and not in the journal-status diagnostic, because the diagnostic population drops only the status gate and these lines fail another gate. The remaining 11,356 (7,041 Posted and 4,315 non-Posted) fail a non-status gate: non-posting rows, junk or unresolvable entities, balance-sheet statement, missing actual amount (Posted lines) or undecidable scale (Posted lines). independent validation verified the arithmetic.

The fixed **revenue populations** in the forecast tab are population A (matched same-sign, 24,372 lines), B (comparable, 29,131) and C (all forecast, 30,879).

## 9. Detail table, CSV export and print

- **Detail Lines:** search, sort (missing values sort last and show a dash), and pagination at 50 rows per page.
- **Export all filtered lines (CSV):** downloads every line matching the current filters, not just the visible page, as UTF-8 with a header. Fields are escaped, and values starting with a formula character are prefixed with an apostrophe to prevent spreadsheet formula injection. Tested in Chromium; the file name is `fpa_filtered_detail_lines.csv`.
- **Print report / PDF:** the print stylesheet hides the controls, prints each of the nine tabs on its own page and restores the live state afterwards. A generated PDF preview from Chromium print-media emulation ran to 38 pages. The detail table prints only the current page; use the CSV export for every line. Printing was tested by emulation and PDF generation, **not on a physical printer**.

## 10. Provisional assumptions you should know about

The dashboard shows these as open assumptions on the Data Quality tab.

| Assumption | Status |
|---|---|
| Posted-only population (R6) | Provisional; changing it is the largest swing factor |
| Scale restoration (R7) | Provisional; HIGH and MEDIUM confidence are shown separately |
| FX direction (R8) | Provisional |
| Variance % guard of 50% (R10) | Provisional |
| Sign convention (R9), duplicate handling (R11), consolidation (R12) | Unresolved |
| Forecast has no version or as-of date | No forecast-skill claim is made |
| Balance-sheet measurement basis | Unknown; no balance-sheet ratios |

Not shown because the data cannot support them: DSO, DPO, working capital, close duration, unit economics, EBITDA. The dashboard makes no favourable or unfavourable judgement: positive means actual above budget, negative below.

## 11. How it was verified

| Check | Result | Source |
|---|---|---|
| Dashboard browser suite | 297 PASS / 0 FAIL / 1 SKIP of 298 | Dashboard report |
| Dashboard negative controls | 6 of 6 re-introduced defects detected | Dashboard report |
| Independent validation dashboard module | 471 PASS / 0 FAIL / 3 NOT TESTED (+2 INFO) | Independent validation report |
| Engine and DOM values against the independent pandas reference | 17 filter and scenario states, within a cent | Independent validation |
| Dashboard row sets equal the independent Posted (58,340) and non-Posted (77,990) sets | Exact | Independent validation |
| No external network references; no console errors after load and interaction | Pass | Dashboard, independent validation |

Selection consistency was tested in 17 specific states, **not every possible filter combination**. The in-page "Baseline checks" badge compares default values with embedded SQL analysis tables; the "Selection checks" badge compares two implementations inside the same page. Neither is an independent test; independence comes from the pandas reference in the test suites.

## 12. What was not tested

- **Firefox, Safari** and any browser other than Chromium.
- **Screen readers and other assistive technology.** Keyboard operation (tab arrows, Enter and Space on bars) and ARIA roles, names and states were asserted programmatically and by keyboard tests, but no accessibility audit or assistive-technology test was done, so this guide makes no accessibility claim.
- **A physical printer.**
- **Windows** and a clean-machine run.
- Every possible filter combination.

## 13. Limitations

- Line-level amounts for 136,330 lines and document numbers for 58,340 lines are embedded in the HTML. The file does not embed user IDs or cost-centre owner names. It must not be shared until provenance and licence are resolved.
- All values are provisional and describe a simulated extract.
- The 4,996-line hidden population (section 8) is documented but not shown.
