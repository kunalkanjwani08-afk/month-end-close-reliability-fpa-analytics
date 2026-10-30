# Phase 8 Independent Review: Errata

**Month-End Close Reliability & Financial Performance Analytics**

> **Status:** correction record for the first Phase 8 package (kept unchanged in `outputs/phase8/`). Corrected documents are in `outputs/phase8_final/package/`.
> **Scope of this file.** Documentation errors only. No dataset, SQL, Excel formula, dashboard code, definition or Phase 1-7 evidence file was changed.
> **Not a certification.** The documentation is not claimed to be perfect or externally certified.

Related: [README draft](../reports/phase8/README_PHASE8_DRAFT.md) · [Risks](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md) · [Dashboard guide](DASHBOARD_USER_GUIDE.md) · [Changelog](PROJECT_CHANGELOG.md)

---

## 1. Limits of the original Phase 8 review

The original Phase 8 QA report records 15 documentation corrections (D1-D15) and 9 source issues (S1-S9). That review was performed by **one reviewer, the same one who wrote the documents. It was not an independent second-person review.** An independent reviewer afterwards found the additional errors listed below, which the original review missed. The original QA report is not deleted or rewritten; a supplemental addendum is appended to its copy in the corrected package.

## 2. Verification performed in the correction round

Read-only checks only: a GitHub API call (repository metadata, `main` tree, commit list), `git ls-files`, reading `src/phase6_core.js`, `src/phase6_views.js`, `src/clean_fpa_monthly_close.py`, `sql/phase4/01_dimensions_and_views.sql`, `docs/DATA_DICTIONARY.md`, `outputs/phase6/DASHBOARD_QA_REPORT.md`, and counting `source_system` values in the raw CSV. **Not done:** re-running the cleaner, the browser selector tests, or any Phase 7 test.

## 3. Errata

| # | Affected document(s) | Original misleading statement or scope | Correction made | Evidence | Verified? |
|---|---|---|---|---|---|
| E1 | README draft; risk register item 1; changelog; case study; every "private" status line | Described the project as private, "everything is private", "nothing has been committed, pushed or published", repository visibility "not checked" | Added a *Repository status* section and replaced the statements: repository public, raw CSV in public `main`, committed earlier, Phase 8 not pushed, owner must re-check and decide | GitHub API: `private: false`, `visibility: public`, last push 2026-10-28T06:29:51Z; `main` tree lists the raw CSV at 51,938,535 bytes | **Yes** (point in time, 2026-10-30) |
| E2 | README draft; workflow; file catalogue; SQL guide | Raw CSV described as "local only" / "git-ignored" / "not in git" | Raw CSV described as tracked and public; cleaned CSV and DuckDB file described as generated, untracked outputs | `git ls-files data` lists the raw CSV; remote tree has no `data/processed` files; the working-copy `.gitignore` edit is uncommitted and cannot untrack a tracked file | **Yes** |
| E3 | Dashboard user guide (two places) | Variance-comparison selector "changes the variance, forecast and prior-year comparisons" | Scope corrected: affects Budget & Variance, Executive variance KPI, prior-year comparison table, variance insights; does **not** affect forecast accuracy, line counts, revenue/cost KPIs, gross profit or data-quality tables | `phase6_core.js` line 558 note text; `fcPops()` contains no reference to `varPop`; `pyAgg(S.varPop)` does; Phase 6 QA test row quoting the note | **Yes** by source reading. Browser selector tests **not re-run** |
| E4 | README draft; project overview; methodology; executive summary; case study | "Five source systems" / "arrives from SAP, Oracle..." / "Verified" source systems | Reworded: five **observed labels** in `source_system`; originating platforms **not independently authenticated**. Trailing-space SAP variant (2,038 rows) noted in documents, source data unchanged | Raw CSV counts: SAP 49,204, Oracle 25,582, Excel upload 25,514, NetSuite 25,364, Tally 24,980, `SAP ` 2,038 (sum 152,682) | Labels and counts **Yes**; platform origin **Unverified** |
| E5 | Project overview; methodology; SQL guide; workflow; case study; financial-metrics limitation | Each of the 152,682 rows called a journal line / posting | Replaced with the required grain statement: 152,682 source extract records, including 350 non-posting subtotal/check records not treated as ordinary posted journal lines. Counts unchanged | `docs/DATA_DICTIONARY.md`: 350 rows with `notes` = `subtotal row` | **Yes** |
| E6 | README draft | Cleaner command without `--input` | Command now names `data/raw/fpa_monthly_close_raw_messy.csv` with PowerShell backtick continuation; reason stated; `HOW_TO_RUN.txt` (Phase 7 file) noted as still showing the short form | `clean_fpa_monthly_close.py` argument parser defines `--input`; default is an automatic search | Flag exists **Yes**; command **not re-executed** this round |
| E7 | SQL guide; executive summary; case study | "Every analytical number can be traced to one of these tables" / "every number traceable to a query" | Rewritten: SQL gives baseline results; dashboard filter states are computed in JavaScript from the embedded payload; Phase 7 compared tested states only (17); not every filter combination tested | `phase6_core.js`/`phase6_views.js` compute in the page; Phase 7 report: 17 states | **Yes** |
| E8 | SQL guide; financial-metrics limitation | Guard described as "net budget at least 50% of gross budget" (absolute value omitted) | Written as \|Net Budget\| >= 50% x Gross Absolute Budget (and the denominator must be positive) | `safe_pct` macro: `CASE WHEN den_abs > 0 AND abs(den_net) >= 0.5 * den_abs THEN num / abs(den_net) END` | **Yes** |
| E9 | Risk register item 13 and summary | GL/account mapping limitation had no issue ID | Added accepted limitation **ISS-19** (Phase 8 supplemental). It is **not** in the Phase 7 issue log, which stays ISS-01 to ISS-18 and is unchanged. No mapping invented or altered | Phase 7 issue log; existing item 13 text | **Yes** (wording); the mapping's accounting correctness remains **unverified** |
| E10 | Changelog; README version-control row | "Nothing was committed, pushed or published" | Explicit timeline: raw CSV committed 2026-10-28; remote last push 06:29:51 UTC; Phases 2-7 not on the remote; Phase 8 not pushed; when the repository became public unknown | Commit list from the GitHub API and `git log` | **Yes**; the date of becoming public is **unknown** |
| E11 | Original Phase 8 QA report | Presented as a complete review ("15 corrected") | This errata file and an addendum state it was one reviewer, non-independent, and incomplete | The independent findings above | **Yes** |
| E12 | Phase 6 QA report (not edited) | Limitations section line: selector "changes variance, forecast and prior-year comparisons" | See section 4 | See section 4 | **Yes** by source reading |

## 4. Erratum for the Phase 6 QA report (original not edited)

`outputs/phase6/DASHBOARD_QA_REPORT.md` contains two statements that disagree. Its correction table and a PASS test row say the selector does **not** change forecast accuracy, and quote the dashboard's own note ("It changes only: Budget & Variance, the Executive variance KPI, the prior-year comparison table and variance insights"). A later limitations line says it "changes variance, forecast and prior-year comparisons". **The source implementation and the specific selector test are treated as authoritative** because: the note text is generated by the code the user sees; the forecast population function `fcPops()` does not read the selector state; and the test row checks the shipped note. The limitations line is a loose summary sentence and is wrong on forecast. The Phase 6 report is left as-is (historical evidence); readers should use this erratum.

## 5. What remains open

- Repository visibility and the raw CSV in public history: owner decision, not taken here.
- Data provenance and redistribution rights: unresolved.
- Source-platform origin and GL/account classification: unverified.
- Browser selector tests and the cleaner command were not re-run in this round.
- No second-person review of the corrected package has been done.
