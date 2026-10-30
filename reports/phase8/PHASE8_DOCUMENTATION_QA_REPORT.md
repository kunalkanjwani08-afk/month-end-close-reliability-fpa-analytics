# Phase 8 Documentation QA Report

**Project:** Month-End Close Reliability & Financial Performance Analytics
**Scope:** the Phase 8 documentation package in `outputs/phase8/documentation_package/` (1 README draft + 13 documents, about 26,700 words).
**Date:** 2026-10-30.
**Reviewer:** the author of the package (single reviewer; see section 9).
**Status:** private. Nothing was committed, pushed or published.

This report lists what was checked, what was found, and whether each issue was corrected. It does not repeat the Phase 7 QA; it checks the *documents* against their sources.

---

## 1. Result at a glance

| Question | Answer |
|---|---|
| Are all phases represented accurately? | Yes, to the extent checked: each phase's deliverables, counts and dates were taken from, or recomputed against, project files. One labelling ambiguity (Phase 2/3) is documented, not resolved |
| Were figures and definitions cross-checked? | Yes. Every comma-formatted number, `$…M` value and percentage in the 14 files was matched mechanically against the source corpus; 88 unmatched strings were then each resolved (section 4) |
| Are limitations disclosed? | Yes. The 17 required register items are present with all five required fields; untested environments are named in every document that could imply otherwise |
| Do internal links work? | 184 relative links checked against the repository with the package overlaid; all resolve once the QA report exists (183 at the first pass; the missing one was this report) |
| Documentation issues found | 15 in the package (all corrected) and 9 in the source project (none changed; recorded) |
| Phase 1–7 material altered? | No (section 7) |

## 2. Source-document inventory (built before drafting)

The brief required an inventory before drafting. Phase 8 read, without modifying, the following. Per-file paths, roles, statuses and hashes are in [`PROJECT_FILE_CATALOG.md`](../../docs/PROJECT_FILE_CATALOG.md).

| Group | What was inspected | Latest approved version identified by |
|---|---|---|
| Root | `README.md`, `HOW_TO_RUN.txt`, `requirements.txt`, `.gitignore` | Phase 7 SHA-256 manifest |
| Data | Raw CSV, canonical cleaned CSV, DuckDB file, QC report, QC summary | Manifest (authoritative inputs) |
| Docs (Phase 1–5) | 9 files in `docs/` | Manifest |
| Source code | 11 files in `src/` | Manifest |
| SQL | 12 scripts in `sql/phase4/` | Manifest |
| Phase 4 outputs | 72 CSVs and a manifest | Phase 4 manifest and Phase 7 manifest |
| Phase 5 | Workbook (all 12 sheets read with openpyxl), QA report, manifest | Manifest |
| Phase 6 | Dashboard HTML and its source (template, CSS, 2 JS files), QA report, results JSON | Manifest |
| Phase 7 | QA report, `qa_results.json` (823 records), 3 workbooks, issue log, logs, evidence | Manifest (3 workbook entries stale; see 6.1) |
| Tests | 7 test files and 12 Phase 7 modules | Manifest |
| Master archive map | `00_START_HERE_PHASE_MAP.md` in the master archive | Phase 7 report |
| Brief | The Phase 8 prompt | Owner |

Live read-only queries were also made against the DuckDB database to confirm populations (58,340; 136,330; 55,043; 54,851; 54,923; 2,953) and the workbook's sheet, table, chart and formula counts.

## 3. Checks performed

| # | Check | Method | Result |
|---|---|---|---|
| C1 | Internal links | Script resolves every relative Markdown link, with the package overlaid on the repository root | 184 links, 0 broken after this report was written |
| C2 | Mermaid diagram | Extracted from `END_TO_END_WORKFLOW.md` and rendered with Mermaid CLI in Chromium | Rendered without error (one diagram) |
| C3 | Numbers | Script extracts `$…M`, comma-formatted numbers and percentages and searches the source corpus | 88 unmatched strings; all resolved (section 4) |
| C4 | Derived numbers | Recomputed: 13.0% (26.32 ÷ 202.65 = 12.99%); 11,356 and 4,315 (16,352 − 4,996 and 7,041 + 4,315); $201.02M (201,016,749.51 from the Phase 6 report); concentration shares from `f2_concentration.csv`; gross margins from `e1_gross_profit.csv` (54.2%, 51.1%, 54.8%) | Agree |
| C5 | Definitions | SQL macro signatures, view definitions and metric formulas read from the SQL scripts and compared with the documents | Four discrepancies found and corrected (section 5) |
| C6 | Forbidden-claim scan | Searched for EBITDA, favourable/unfavourable, real company, "approved", Excel/Windows/accessibility claims, DSO/DPO/working capital | Every hit is a negation, disclaimer or "not produced" statement. No affirmative forbidden claim |
| C7 | Machine paths, e-mail, personal names | Regex scan of all 14 files for home or temp paths, drive paths, e-mail addresses, the owner's name, cost-centre owner names | 0 matches |
| C8 | Cross-document consistency | Counts of checks, sheets, tables, formulas, tabs, views, issues and accounts compared across files | Consistent (780; 12; 72; 3,819; nine; 12; 18; 32) |
| C9 | Hash verification | All 219 manifest entries present in the repository re-hashed | 216 match; 3 differ (6.1); 1 entry is outside the repository |
| C10 | Preservation | Files newer than the Phase 7 outputs found outside `outputs/phase8/`; git status compared | None; git status shows only pre-existing entries plus `outputs/phase8/` |
| C11 | Register completeness | 17 required items each checked for the five required fields | 17 of 17 complete |
| C12 | Required sections | README sections A–H; the 13 docs; metrics list; QA summary counts; Excel 12 sheets; dashboard 9 tabs | All present |

## 4. Resolution of the 88 unmatched number strings

| Strings | Explanation |
|---|---|
| 51 file-size values in the catalogue | Taken from the filesystem and the manifest; not in any prose source |
| 12.99%, 13.0% | Derived: 26.32 ÷ 202.65 |
| 11,356; 4,315 | Derived from the Phase 7 gap table |
| $201.02M | Rounded from 201,016,749.51 (Phase 6 report) |
| 25.8%, 36.1%, 51.1% (repeated in several files) | Rounded from `f2_concentration.csv` (0.2579, 0.3605) and `e1_gross_profit.csv` (0.5110) |
| 7,726; 145,994; 5,326; 6,053; 93,585; 106,776; 18,451; 6,936; 1,919; 9,317 | Present in the QC report or Phase 7 evidence work files without thousands separators |
| 1,234,567 | An illustrative example in the methodology document, labelled as such |

No unmatched string was left unexplained.

## 5. Issues found in the package, and whether corrected

| # | Document | Issue | Corrected? |
|---|---|---|---|
| D1 | PROJECT_OVERVIEW | Finding 6 cited INS-06 for the concentration caveat. INS-06 is the salary-rate insight | Yes: now cites rejected finding R7 in the Phase 4 report |
| D2 | README | The reproducibility sequence listed the dashboard build as if it were in `HOW_TO_RUN.txt` | Yes: marked as not in `HOW_TO_RUN.txt`; adding it is a Phase 9 recommendation |
| D3 | DATA_AND_CLEANING | "Comma thousands" row merged two classes | Yes: split into multi-group (24) and ambiguous `n,nnn` (9,317) |
| D4 | DATA_AND_CLEANING | An unsupported inference that the byte-order mark exists "so Excel opens it correctly" | Yes: removed; the file is described as to be opened as UTF-8 with BOM |
| D5 | DATA_AND_CLEANING | Parser-agreement wording went beyond the evidence | Yes: reworded to the verified facts |
| D6 | SQL_ANALYTICS | Macro arguments (`safe_pct`, `anomaly_class`) were wrong | Yes: corrected from the SQL |
| D7 | SQL_ANALYTICS | `v_pl_budget`, `v_pl_forecast` and `v_pl_prior` rules described imprecisely | Yes: now the exact eligibility flag and the documented convention |
| D8 | DASHBOARD_USER_GUIDE | Chart-to-tab mapping partly guessed | Yes: re-mapped from the chart identifiers in the source |
| D9 | DASHBOARD_USER_GUIDE | The 11,356 "other" gap rows described with unverified examples | Yes: replaced with the Phase 7 breakdown (7,041 Posted and 4,315 non-Posted, by gate) |
| D10 | FINANCIAL_METRICS | "6,265 restored rows in the main population" was wrong (2,374 Posted and 3,220 non-Posted in the payload) | Yes |
| D11 | FINANCIAL_METRICS | "62 undetermined-scale rows" conflated the first-failing-gate count with the 73 total | Yes |
| D12 | QA_AND_VALIDATION_SUMMARY | A "Phase 7 rating 8.5/10" line had no repository source; the QA report link pointed to the wrong relative path | Yes: line removed; link fixed |
| D13 | PROJECT_FILE_CATALOG | First draft said no unmanifested files existed. A proper scan found 65 (30 screenshots, 28 work files, 5 cache files, plus the manifest and report) | Yes: corrected and listed |
| D14 | PORTFOLIO_CASE_STUDY | A bullet describing this phase's own review as a project lesson | Yes: removed |
| D15 | RISK REGISTER | Negative-sign shares were not tied to a source | Yes: labelled as the Phase 1–3 profile of rows labelled Actual scale |

Total: 15 corrections to the package, found during drafting and checking.

## 6. Issues found in the source project (recorded, not changed)

Phase 8 must not modify Phase 1–7 material. These are recorded for the owner.

| # | Finding | Effect | Recommended action (Phase 9, owner approval) |
|---|---|---|---|
| S1 | **Stale manifest hashes.** `DATA_LINEAGE_RECONCILIATION.xlsx`, `FINANCIAL_RECONCILIATION.xlsx` and `ISSUE_LOG.xlsx` were rewritten about two seconds after the Phase 7 manifest (file times 11:58:38–11:58:41 against 11:58:36), so their manifest hashes and sizes no longer match | The manifest cannot verify three Phase 7 workbooks | Regenerate the manifest; keep the current files |
| S2 | The Phase 6 report says "Print outputs the visible tab", but the print stylesheet (`.panel{display:block!important;page-break-before:always}`) and the same report's print check (nine views, 38 PDF pages) show all nine tabs print | A reader could misdescribe print behaviour | Correct the sentence; the dashboard guide follows the code |
| S3 | Root `README.md` pre-dates Phases 4–7 (says the dashboard does not exist) | Outdated repository front page | Replace with the README draft after owner review |
| S4 | `docs/FINANCIAL_METRICS.md` says it contains no results and states an unguarded variance %; Phase 4 onward uses a 50%-guarded percentage | Two definitions in the repository | Mark as historical or update |
| S5 | `HOW_TO_RUN.txt` does not include the dashboard build step | Incomplete reproducibility sequence | Add the command |
| S6 | `requirements.txt` omits Playwright and LibreOffice, used by QA | A QA re-run on a clean machine would fail | List as optional QA dependencies |
| S7 | QC files contain build-environment paths (ISS-03); `tests/phase7/p7_pipeline_checks.py` hard-codes a scratch directory and `tests/phase6_dashboard_qa.py` globs a machine-specific path (ISS-04) | Publication blocker (QC files); portability (tests) | Sanitise, make paths relative |
| S8 | Junk-entity counts differ across documents: 173 (names only, Phase 1) and 204 (names plus codes, cleaner) | Possible confusion | Explained in the methodology document; no change needed |
| S9 | Phase labelling for Phases 2 and 3 differs between project files | Possible confusion | Numbering note added to the README draft |

## 7. Preservation check

| Rule from the brief | Evidence |
|---|---|
| Phase 1–7 deliverables preserved | 216 of the 219 re-hashed manifest entries match; the 3 mismatches are Phase 7 workbooks whose file times (11:58) pre-date Phase 8 |
| Raw and canonical cleaned datasets unmodified | Their hashes (`a0e6edde…`, `c184b677…`) match the manifest |
| SQL database, calculations, definitions unmodified | Database hash (`00e74376…`) matches; SQL scripts match; opened read-only only |
| Workbook and dashboard not rebuilt or redesigned | Their hashes (`71e23dca…`, `43d2505a…`) match |
| Phase 7 QA not restarted; QA evidence not overwritten | No file under `outputs/phase7/` has a modification time later than Phase 7 |
| No historical report or source deleted | Nothing was deleted |
| No commit, push or publish | Git status shows only pre-existing entries plus the new `outputs/phase8/` folder; no git write command was run |
| No credentials, personal information or machine paths | Scan C7: 0 matches |
| Dedicated Phase 8 folder | All work is in `outputs/phase8/` |
| Root README preserved; changes documented | The root README is unchanged (hash matches). The draft replacement is in the package; the decision to replace it is left to Phase 9 |

## 8. Remaining documentation gaps

1. **Owner review.** All "Owner-stated" labels and every statement about what the owner decided come from the project documents; the owner has not reviewed them in Phase 8.
2. **Cleaning-script internals.** The methodology document describes cleaning outputs and rules from the QC report and Phase 7 evidence. It does not document the cleaner's source code function by function.
3. **Phase 2 profiling.** No dated record in the repository for the earlier profiling work; the changelog says so.
4. **Dashboard code.** The dashboard guide documents behaviour, not the JavaScript architecture.
5. **Workbook cell-level formulas.** The Excel guide documents sheets, tables and key formulas, not each of the 3,819.
6. **Source-level corrections S1–S9** are recorded here but not applied.
7. **Package placement.** The package sits in `outputs/phase8/documentation_package/`. The docs link to repository files as if they were copied to `docs/`, so link integrity depends on that overlay. Copying into the repository is a Phase 9 step.

## 9. Limits of this QA

- **One reviewer.** The package was written and checked by the same author. No second analyst reviewed it.
- **Not rendered.** Markdown was checked as text. Only the Mermaid diagram was rendered. Table layout in a Markdown viewer was not inspected.
- **Pattern-based scans.** The number scan finds strings absent from the sources; it does not find a correct number used in the wrong sentence. That risk was handled by reading the definitions and several narrative claims against sources (C5), not exhaustively.
- **Phase 7 statements were relied on** for results that Phase 8 did not re-run (780 checks, independent reference results, Chromium results). Phase 8 re-checked populations and counts by read-only queries but did not re-run the Phase 7 suites, by instruction.
- **Spelling and style** were not checked by a tool.
- **Owner-facing judgments** (what counts as a publication blocker) restate Phase 7's recommendation.

## 10. Conclusion

The documentation package accurately reflects Phases 1–7 as recorded in the project files, discloses the unresolved assumptions and untested environments, and leaves every Phase 1–7 deliverable untouched. Fifteen defects in the drafts were found and corrected during checking. Nine source-project issues were found and recorded, including a stale-hash defect in the Phase 7 manifest that Phase 7 did not report. The package is ready for owner review; it is not ready for publication.


---

# SUPPLEMENTAL ADDENDUM (Phase 8 independent-review correction round, 2026-10-30)

**The text above is the original review, unchanged. This addendum qualifies it.**

1. **Single reviewer.** The original review was performed by one reviewer, who also wrote the documents. It was not an independent second-person review.
2. **Missed errors.** An independent review found further errors the original did not (repository visibility and "private / nothing published" statements, raw CSV described as git-ignored, variance-filter scope, source-system wording, record grain, README `--input`, SQL traceability, guard wording, missing ISS-19 label). They are listed in `docs/PHASE8_INDEPENDENT_REVIEW_ERRATA.md` and corrected in this package.
3. **Superseded statements.** Wherever the text above says the project is private, that nothing has been published, that the raw file is local or git-ignored, or that the variance selector changes forecast comparisons, it is superseded by the corrected documents.
4. **Not claimed.** The corrected package is not claimed perfect or externally certified. See `PHASE8_FINAL_DOCUMENTATION_QA.md`.
