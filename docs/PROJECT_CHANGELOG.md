# Project Changelog

**Month-End Close Reliability & Financial Performance Analytics**

> **Status (updated at Phase 9 publication, 30 Oct 2026):** published as part of the complete project. The owner decided to publish the whole project, including the dataset he describes as synthetic. Dataset provenance and redistribution rights remain **owner-stated and not independently verified**. Any wording below from Phase 8 that calls the release *blocked*, *draft* or *not approved* describes the Phase 8 state and is superseded by [PUBLICATION_DECISION.md](PUBLICATION_DECISION.md). No calculation, figure or finding was changed.
> **Dating rule.** No date is invented. A date appears only where the repository records it: a git commit time, a timestamp inside a report or the QC log, or a file modification time in the working copy. File times can differ from the day the work was discussed; they are labelled "file time". Where no record exists the entry says so.
> **Phase labels.** This changelog follows the labelling of the master archive and the Phase 7 report (see the numbering note in the README draft).

Related: [File catalogue](PROJECT_FILE_CATALOG.md) · [QA summary](QA_AND_VALIDATION_SUMMARY.md) · [Risks](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md)

---

## Summary

| Phase | Theme | Dated record | Outcome |
|---|---|---|---|
| Stage 0 / 1 | Design and data understanding | Git commits 2026-10-28 05:34, 06:06, 06:29 (UTC) | Repository, rules, dictionary |
| 2 | Data acquisition and quality review | QC run 2026-10-28 11:55:08 | Canonical cleaned CSV and QC outputs |
| 3 | Python cleaning and validation | Same QC run | Cleaner v1.0.0 |
| 4 | SQL and financial analysis | File times 2026-10-29 10:26–12:27 | 72 tables, insight register |
| 5 | Excel workbook | Workbook generated 2026-10-29T12:55:33Z | 12 sheets, 137 checks |
| 6 | Dashboard | File times 2026-10-30 10:29–10:43 | Nine-tab standalone HTML |
| 7 | End-to-end QA | Report generated 2026-10-30T11:58:35 | 780 checks; no critical or high issue |
| 8 | Documentation | 2026-10-30 | This package |

---

## Stage 0 and Phase 1: project design and data understanding

- **Git commit `1d601c0` (2026-10-28 05:34 UTC):** *Stage 0: raw extract, folder chart and planning docs.* The raw CSV was committed unchanged. (This is why the raw file is in git history; the repository was later verified as public with the raw file in `main`; see risk item 1.)
- **Git commit `70a63a7` (2026-10-28 06:06 UTC):** *Phase 1: add data dictionary, financial metrics rules, data provenance and README objective.*
- **Git commit `0412be8` (2026-10-28 06:29 UTC):** *Phase 1: finalize exclusion accounting and metric definitions.*
- **Decisions recorded:** one exclusion reason per row in a fixed precedence; P&L and balance sheet never added; subtotal rows excluded; amounts are text and are not summed raw; sign convention, duplicates and consolidation left open.
- **Not done:** no data analysis; the Phase 1 documents contain no results.

## Phase 2 and Phase 3: acquisition, quality review and cleaning

- **Cleaner run (QC log timestamp 2026-10-28 11:55:08):** integrity gate on the raw file (152,682 rows, 43 columns, SHA-256 `a0e6edde…`); cleaned CSV of 152,682 rows × 192 columns; no row deleted; 43 in-memory and 27 read-back checks passed; raw file unchanged after the run.
- **Delivered:** `src/clean_fpa_monthly_close.py` (version 1.0.0), `data/processed/fpa_monthly_close_cleaned.csv` (SHA-256 `c184b677…`), `QC_Report.txt`, `qc_summary.json`, and the review workbook `fpa_monthly_close_cleaned.xlsx` (77 shared fields).
- **Decisions recorded:** scale decided per row by a written rule (HIGH and MEDIUM confidence); duplicate candidates flagged, none removed; no sign changed; FX used as a diagnostic only.
- **Known issues carried forward:** build-environment paths inside the QC files (ISS-03).
- **No dated record** exists in the repository for the earlier profiling work that preceded the cleaner run.

## Phase 4: SQL database, financial analysis and analytical outputs

- **File times 2026-10-29:** acceptance review 10:26; analysis report 12:27; Phase 5 review response 12:30.
- **Built:** `src/phase4_pipeline.py`, 12 SQL scripts, a DuckDB database, 12 views, 72 output tables with a manifest, the analysis report, and a seven-insight register (INS-01 to INS-07).
- **Validation:** 289 validation rows (55 + 24 + 86 + 124) all PASS; 74 automated tests (42 fixture + 32 full-data) per the root README.
- **Changed after review:** the Phase 4 report and insight register were corrected in the Phase 5 review (documents `PHASE4_ACCEPTANCE_REVIEW.md` and `PHASE5_REVIEW_RESPONSE.md`).
- **Rejected finding recorded:** finding R7 (cost concentration read as inefficiency) was rejected; high share is descriptive only.

## Phase 5: Excel financial analysis and reconciliation

- **Workbook generated 2026-10-29T12:55:33Z; QA report written 2026-10-29 12:56 UTC.**
- **Built:** `src/phase5_excel.py`; 12 sheets, 22 tables, 7 charts, 3,819 formulas; a reconciliation sheet of 137 live checks.
- **Validation:** 51 tests PASS; LibreOffice independent recalculation, 0 mismatches; mutation test turned the checks red as intended.
- **Not done:** the workbook was never opened in Microsoft Excel.

## Phase 6: interactive dashboard

- **File times 2026-10-30:** dashboard HTML 10:29; QA report 10:43.
- **Built:** a standalone HTML file (7.32 MB) with nine tabs; later extended after review with scenario selectors, a line-level journal-status diagnostic (77,990 non-Posted lines), KPI trend charts, cross-filtering with a selectability guard, a dynamic scope description, new charts, and a corrected palette (contrast checked in both themes).
- **Validation:** 297 PASS / 0 FAIL / 1 SKIP of 298 browser checks; 6 of 6 negative controls detected.
- **Defect found and fixed during Phase 6:** the print routine left the header basis open in the live page; state is now restored after printing.
- **SKIP:** screen-reader testing (no assistive technology available).

## Phase 7: end-to-end QA, independent financial validation and project audit

- **Report generated 2026-10-30T11:58:35.** `HOW_TO_RUN.txt` was corrected at file time 11:49.
- **Executed:** 780 checks: 774 PASS, 1 FAIL, 1 BLOCKED, 4 NOT TESTED, plus 43 INFO observations. An independent pandas reference reproduced the SQL, the workbook and the dashboard on identical populations.
- **Issues found:** ISS-01 and ISS-02 (run instructions) corrected in `HOW_TO_RUN.txt` and regression-tested; ISS-03 to ISS-18 logged (no critical or high).
- **Corrected in Phase 7:** the documented command to regenerate the cleaned CSV (it wrote to the wrong folder) and the documented test order after a database rebuild. The original instructions are preserved in `outputs/phase7/evidence/originals_before_correction/`.
- **Master archive** `NovaBridge_FPA_All_Phases_1-6_Master.zip` was built on 2026-10-30 (per the Phase 7 report).
- **No data, calculation, workbook or dashboard was changed in Phase 7.**

## Phase 8: professional documentation (this package)

- **Date:** 2026-10-30.
- **Created, all under `outputs/phase8/`:** `documentation_package/README_PHASE8_DRAFT.md`; 13 documents in `documentation_package/docs/`; and `PHASE8_DOCUMENTATION_QA_REPORT.md`.
- **Method:** every figure was taken from, or recomputed against, a Phase 1–7 source; evidence is labelled Verified, Owner-stated, Assumption or Unresolved.
- **Not changed:** the raw and cleaned datasets, the database, calculations, definitions, the workbook, the dashboard, the Phase 1–7 documents, the root README, any QA evidence. No Phase 8 file was committed or pushed by this work. (This does not mean nothing was ever published: the raw CSV was committed in Stage 0 and the repository was publicly accessible when checked.)
- **Documentation gaps found and recorded:** outdated root README and Phase 1–3 metrics document; the dashboard build step missing from `HOW_TO_RUN.txt`; QA-only tools missing from `requirements.txt`; a Phase 6 report sentence on print behaviour that contradicts the code; stale manifest hashes for three Phase 7 workbooks.

## Repository and publication timeline

| When | Event | Status |
|---|---|---|
| 2026-10-28 05:34 UTC | Stage 0 commit `1d601c0` committed the raw CSV to Git | Verified (git log) |
| 2026-10-28 06:06 and 06:29 UTC | Two Phase 1 commits (documents only) | Verified |
| 2026-10-28 06:29:51 UTC | Last push to the remote | Verified (GitHub API) |
| Unknown | The repository became (or was created) publicly accessible. Earlier notes recorded it as created private | Not known |
| Phases 2 to 7 | Work done locally; Phase 7 did not publish additional project changes | Verified (remote tree holds only Stage 0 and Phase 1 files) |
| 2026-10-30 | Read-only check: repository public; raw CSV in public `main` | Verified (point in time) |
| Phase 8 | Documents drafted; **not committed or pushed** | Verified (git status) |
| Now | The owner must check the current visibility; the data remains uncleared for public redistribution | Open |

## Phase 8 independent-review correction round

- **Date:** 2026-10-30. An independent reviewer found factual and terminology errors in the first Phase 8 package (repository visibility, variance-filter scope, source-system wording, record grain, README command, SQL traceability, missing ISS-19). Corrections are in `outputs/phase8_final/`; the first package is kept unchanged in `outputs/phase8/`. See `docs/PHASE8_INDEPENDENT_REVIEW_ERRATA.md`.

## Open at the end of Phase 8

| Item | Source |
|---|---|
| Public release blocked: data provenance and licence; **public repository holds the raw file in `main` and in history** | ISS-06 |
| Build-environment paths in the QC files | ISS-03 |
| No Windows or clean-machine run | ISS-05 |
| 4,996 lines in no dashboard view (documented) | ISS-18 |
| Not tested: Microsoft Excel, Firefox, Safari, screen readers, physical printer | Phase 5–7 |
| Owner decisions: Posted-only rule, sign policy, duplicate rule, consolidation | R6, R9, R11, R12 |

## What is next

Phase 9 (publication preparation) has **not** been started and starts only when requested.
