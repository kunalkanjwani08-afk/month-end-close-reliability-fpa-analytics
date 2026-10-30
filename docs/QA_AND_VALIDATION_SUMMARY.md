# QA and Validation Summary

**Month-End Close Reliability & Financial Performance Analytics**

> **Status (updated at Phase 9 publication, 30 Oct 2026):** published as part of the complete project. The owner decided to publish the whole project, including the dataset he describes as synthetic. Dataset provenance and redistribution rights remain **owner-stated and not independently verified**. Any wording below from Phase 8 that calls the release *blocked*, *draft* or *not approved* describes the Phase 8 state and is superseded by [PUBLICATION_DECISION.md](PUBLICATION_DECISION.md). No calculation, figure or finding was changed.
> **Data:** fictional NovaBridge Industries; owner-described as synthetic.
> **Evidence labels:** Verified / Owner-stated / Assumption / Unresolved.
> **Scope of this document:** it summarises QA that was **already done** in Phases 3–7. Phase 8 did not re-run the Phase 7 QA and did not overwrite any QA evidence.

Related: [Assumptions, limitations and risks](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md) · [End-to-end workflow](END_TO_END_WORKFLOW.md) · Primary source: [`outputs/phase7/PHASE7_QA_REPORT.md`](../outputs/phase7/PHASE7_QA_REPORT.md)

---

## 1. Headline

Phase 7 executed **780 checks**:

| Result | Count |
|---|---:|
| PASS | 774 |
| FAIL | 1 |
| BLOCKED | 1 |
| NOT TESTED | 4 |
| **Executed** | **780** |
| INFO observations (not tests) | 43 |

- **No critical and no high-severity issue** was found. The issue log has 18 items: 2 Medium, 5 Low, 10 accepted limitations and 1 accepted limitation that is a publication blocker.
- Raw → cleaned → SQL → Excel → dashboard reconcile on identical populations, and the 16,352-row population gap is fully explained (0 unexplained rows).
- **QA sign-off applies to the documentation stage. The project is not ready for public publication.**

A PASS means a check passed under the stated tolerance on the stated population. It is not a statement that every business assumption is correct.

## 2. QA by phase

| Phase | What was checked | Result | Source |
|---|---|---|---|
| 3 – cleaning | Cleaner's own validation: 43 + 27 checks, row-for-row preservation, 192-column output, no row dropped | 0 FAILED | `data/processed/QC_Report.txt`, `qc_summary.json` |
| 4 – SQL | Four validation tables (`val_load` 55/55, `val_exclusion_counts` 24/24, `val_analytical` 86/86, `val_crosscheck` 124/124) | All PASS | Phase 5 report, §2 |
| 5 – Excel | 51 pytest tests; 137 live reconciliation formulas; 3,819 formulas recalculated independently in LibreOffice | 51 PASS, 137/137 PASS, 0 mismatches | `PHASE5_QA_REPORT.md` |
| 6 – dashboard | 298 browser checks in Chromium; 6 negative controls | 297 PASS / 0 FAIL / 1 SKIP; 6 of 6 detected | `DASHBOARD_QA_REPORT.md` |
| 7 – end-to-end | Independent reference, lineage, record reconciliation, re-runs, security, disclosure | 780 executed (see §1) | `PHASE7_QA_REPORT.md` |

The Phase 4 and Phase 5 test suites also ran inside Phase 7's isolated re-run. They are counted as existing suites, not as independent evidence.

## 3. Phase 7 results by area

| Area | PASS | Other |
|---|---:|---|
| Data lineage and record reconciliation | 101 | 14 INFO |
| Independent financial recomputation vs SQL | 85 | 2 INFO |
| SQL layer (canonical DuckDB, read-only) | 33 | 1 INFO |
| Phase 5 Excel workbook | 31 | 3 INFO |
| Phase 6 dashboard (browser) | 471 | 3 NOT TESTED, 2 INFO |
| Project assumptions and disclosure | 15 | 2 INFO |
| Python, SQL and Excel re-runs and reproducibility | 31 | 1 FAIL, 1 NOT TESTED, 4 INFO |
| Security, privacy and publication | 7 | 1 BLOCKED, 15 INFO |
| **Total** | **774** | 1 FAIL, 1 BLOCKED, 4 NOT TESTED, 43 INFO |

## 4. How the validation was independent

- The Phase 7 code in [`tests/phase7/`](../tests/phase7/) (12 Python modules) **does not import any project module**. It re-parses the raw amount strings with its own parser and re-derives statement, status, entity and exclusion reasons from raw values, then rebuilds every metric in pandas.
- **Tolerances:** counts exact; money 0.01 USD; ratios 1e-9; dashboard display values at their display precision.
- **Result:** every table row matched within one cent and every ratio within 1e-9 on identical populations.
- **Negative controls:** the financial comparison was re-run with a deliberately corrupted reference (one Posted line dropped; one line off by two cents; one Pending line added). Each produced FAILs, so the comparisons can detect population and one-cent errors.
- **Isolation:** builds and suites were re-run only in copies of the repository. Approved outputs were not overwritten.
- **Test-harness corrections (disclosed in Phase 7):** five first-run FAILs were defects in the QA code, not the project, and were fixed before the final run.

## 5. Record-count reconciliation

152,682 raw rows = 152,682 cleaned rows (identical row IDs and order; no row dropped). The reportable population is 58,340 Posted-eligible P&L lines (38.2% of rows).

| Gap | Rows |
|---|---:|
| Source rows | 152,682 |
| Posted-eligible P&L lines (main population) | 58,340 |
| Non-Posted diagnostic lines (`v_pl_actual_any_status` less Posted) | 77,990 |
| In neither population | 16,352 |
| of which non-Posted lines with no actual amount (4,958) or undetermined scale (38) | 4,996 |
| of which other non-status exclusions (non-posting rows, junk or unresolvable entities, balance-sheet statement, missing actual, undecidable scale) | 11,356 |

Phase 7 check P05 confirmed that every one of the 16,352 rows fails a documented non-status gate.

## 6. The one FAIL, explained accurately

`PR.03.detail` is the single FAIL among 780 checks. It records what happened when the **original** documented run instructions were followed: the Phase 4 database was rebuilt, then the pytest suite was run. Two Phase 5 tests (`test_lineage_and_source_identity_recorded` and `test_manifest_matches_the_saved_workbook_and_inputs`) failed because the database file's SHA-256 changes on every rebuild, so it no longer matches the hash stored in the workbook manifest (issue ISS-02). The Phase 4 CSV outputs were reproduced byte for byte; only the database *file* is not byte-reproducible.

- **This is a defect in the run instructions, not in the data, calculations, workbook or dashboard.** No data or calculation was changed.
- The instructions were corrected in `HOW_TO_RUN.txt` (ISS-01 and ISS-02). The corrected sequence was **regression-tested separately in a fresh copy** and passes (checks `RG.*`).
- The failing record is **preserved** in the Phase 7 evidence as the proof of the original defect; it was not edited or removed to improve the count.

## 7. The BLOCKED and NOT TESTED items

| ID | Status | What it is |
|---|---|---|
| `SEC.prov` | BLOCKED | Data provenance and redistribution licence. The owner states the data is synthetic; no provenance or licence document exists to verify it. Cannot be resolved by testing |
| `UI50` | NOT TESTED | Firefox and Safari rendering (only Chromium available) |
| `UI51` | NOT TESTED | Screen reader or other assistive technology |
| `UI52` | NOT TESTED | Physical printer output (print emulation and Chromium PDF only) |
| `ENV.clean_machine` | NOT TESTED | Clean-machine reproduction (fresh OS, `pip install -r requirements.txt`); no Windows run |

Phase 7 also states that **Microsoft Excel** was not used to open the workbook. That statement is in the report text and the Phase 5 report; it is not one of the four counted NOT TESTED checks.

## 8. Re-run and reproducibility evidence

All re-runs were on Linux (Python 3.13.16, pandas 3.0.5, numpy 2.5.3 against a pin of 2.4.6, DuckDB 2.0.0, openpyxl 3.1.5, pytest 9.2.0, Playwright 1.56.0, Chromium 141, LibreOffice 24.2.7.2).

| Component | Result |
|---|---|
| Python cleaner | Exit 0; output CSV byte-identical to the canonical cleaned file; raw copy unchanged; 253.7 s, about 1.25 GB peak memory; refuses a raw file with the wrong hash |
| Phase 4 pipeline | Reproduced all 72 CSVs and both Phase 4 documents byte for byte; database file not byte-reproducible (ISS-02) |
| Phase 5 workbook | Rebuilt and recalculated; deterministic for a fixed timestamp |
| Phase 6 dashboard | Rebuilt; 297 PASS / 0 FAIL / 1 SKIP; negative controls 6 of 6 |

No Windows run and no clean-machine install were performed.

## 9. Issue log summary (from Phase 7)

| ID | Severity | Status | Issue |
|---|---|---|---|
| ISS-01 | Medium | Corrected (documentation), regression-tested | Command to regenerate the cleaned CSV wrote it to the wrong folder |
| ISS-02 | Medium | Corrected (documentation); code unchanged | Documented order after a database rebuild produced 2 failing Phase 5 tests |
| ISS-03 | Low | Open, action before publication | QC files record build-machine paths |
| ISS-04 | Low | Open (accepted) | Phase 6 QA suite finds the palette validator through a machine-specific path |
| ISS-05 | Low | Open, NOT TESTED | No clean-machine install; installed numpy differs from the pin |
| ISS-06 | Accepted limitation (publication blocker) | BLOCKED, owner decision | Synthetic status, provenance and redistribution rights unverified |
| ISS-07 to ISS-16 | Accepted limitations | Disclosed | Posted-only rule, scale restoration, sign convention, FX, duplicates, forecast version, gross-profit treatment, balance-sheet basis, unit equivalence, comma-amount reading |
| ISS-17 | Low | Open, housekeeping | A different file with the raw file's name exists in the owner's Downloads folder |
| ISS-18 | Low | Open, documentation | 4,996 status-excluded lines are in no dashboard view |

The disclosure of ISS-06 to ISS-16 was itself checked for consistent implementation in the dashboard, workbook and documents (checks AS01–AS13, all PASS).

## 10. What the QA does not establish

- It does not show the data is real, licensed or representative; the headline figures depend on provisional rules (Posted-only, scale restoration, FX direction) and unresolved conventions (signs, duplicates, consolidation).
- It does not cover Microsoft Excel, Firefox, Safari, screen readers, a physical printer, Windows or a clean-machine install.
- Dashboard selection consistency was tested in 17 specific states, not every filter combination.
- Insight text was not reviewed by a second analyst.
- Secret and privacy checks were pattern-based; they found no credentials, e-mail addresses or user-home paths in project text files, but they found build-machine paths in the QC files (ISS-03).

## 11. Phase 8 documentation QA

The checks made on this documentation package (link integrity, figure cross-checks, forbidden-claim scan, path and personal-data scan) are reported separately in [`PHASE8_DOCUMENTATION_QA_REPORT.md`](../reports/phase8/PHASE8_DOCUMENTATION_QA_REPORT.md).
