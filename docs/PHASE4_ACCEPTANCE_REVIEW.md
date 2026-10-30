# Phase 4 acceptance review

Review of the external ChatGPT audit of Phase 4. Every claim was tested against the code and data before any change. Items that were right were implemented; items that were wrong or overstated were not.

## 1. Verdict summary

Nearly all items were valid. Two were only partly valid (H, P: the pandas cross-check was already an independent code path, though its identifiers could collide and its coverage was thinner than claimed). The review also overstated three things: the roughly 90% opposite-sign share of forecast error survives the fix, no account-mapping conflict exists, and no zero-MAD month exists (guards were added anyway, because the code was unsafe even though the data did not trigger it).

## 2. Issue register

| # | Issue | Verdict | Severity | Evidence | Action |
|---|---|---|---|---|---|
| 1 | Binary sign test mixed opposite-sign with zero-involved lines | Valid | High | 76 zero-involved budget lines sat in the "disagree" bucket | 4 categories: SAME_SIGN_NONZERO, OPPOSITE_SIGN_NONZERO, ZERO_INVOLVED, MISSING_OR_UNAVAILABLE (SQL macro and independent pandas version agree on 12 edge cases) |
| 2 | "AS_REPORTED" scenario name implied raw values | Valid | Medium | Amounts are scale-adjusted | Renamed ALL_LINES / signs as recorded |
| 3 | Status exposure ranked diagnostic partitions as policy scenarios | Valid | High | Revenue range was quoted as 200% | scenario_class BASELINE / POLICY_SCENARIO / STATUS_PARTITION_DIAGNOSTIC; ranking uses baseline and policy only; range now 133% (result-proxy 105%) |
| 4 | Forecast-error attribution not split by sign category | Valid | High | Opposite-sign share of absolute error 91.4/88.9/90.0/89.3% before | Per-category table; now 91.2/88.6/89.9/89.1%; zero-involved lines carry at most 0.24% |
| 5 | Insight text stated causes the data cannot prove | Valid | High | INS-02 | Rewritten as observed / driver / unresolved / next layers; caution that WAPE by sign is outcome-selected |
| 6 | Robust z undefined when MAD = 0; NULL could read as "within range" | Valid (code), not triggered (data) | Medium | 0 months with MAD = 0; 860 within range, 3 amount-unusual, 1 coverage-driven, 0 not scorable | robust_z returns NULL; anomaly_class has an explicit "not scorable" class; unit-tested |
| 7 | Gross-profit row set called "sign consistent" | Valid | Medium | Rule is ALL_NON_NEGATIVE; zero rows qualify | Renamed ROWS_ALL_NON_NEGATIVE; comment corrected; hand-computed fixture test incl. all-negative revenue |
| 8 | Top-10 and top-3 ties not deterministic | Valid | Low | rank() can return more than ten cells | row_number with explicit tie-break; checks B17, F06 |
| 9 | Fixed 0.25% / 2% thresholds untested | Valid | Medium | Conventions, not standards | b9 and b11 sweeps (69 cells at 0.25% covering 91% of absolute variance; 130 of 144 cells at >= 2%; top-10 overlap 8 of 10) |
| 10 | Account mapping assumed 1:1 | Valid (assumption), no conflict found | Low | 32 of 32 GL accounts consistent | out_a8 table; checks L52-L55 |
| 11 | Grain evidence ignored missing values | Valid | Medium | COUNT(DISTINCT) skips NULL | Four-pattern classification; text says pattern evidence is not proof of additivity |
| 12 | Outputs written in place before validation (unsafe promotion) | Valid | High | Failed run could leave mixed state | Stage -> validate -> promote; failed runs go to `outputs/phase4_failed_run/` and `.duckdb.failed`; sentinel-tested |
| 13 | Check identifiers could be duplicated | Valid | Medium | X90 ids collided | assert_unique_ids; validation_failures reports DUPLICATE_CHECK_ID |
| 14 | Tests skipped at module level, no fixture tests | Valid | High | Whole file skipped without the CSV | conftest INCOMPLETE banner and non-zero exit; 31 fixture tests |
| 15 | README described Phase 1 | Valid | High | | Rewritten |
| 16 | Stale output files in the manifest folder | Valid | Medium | `b7_sign_opposed_profile.csv`, `b9_materiality_sensitivity.csv` | Deleted; manifest lists 72 tables and 0 stale |
| 17 | Sign-category profile (b7) had no validation | Found by this review's mutation test | Medium | Corrupted b7 passed all checks | Checks B18-B20 added |
| 18 | Report printed a raw `{d['top10']}` placeholder | Found by this review's tests | Low | f-string prefix missing | Fixed; test guards it |
| 19 | Provenance and licence verified? | Not verifiable | Medium | Owner-described synthetic data | Stated as UNVERIFIED everywhere; not claimed |

## 3. Changes that did not move the answer

Same-sign variances (revenue -$7.02M, -3.6%; people +$2.29M) and all-lines variances are unchanged. The "about 90% of forecast error sits in opposite-sign lines" headline survives. Account mapping is clean. The review changed the labels, safeguards and tests, not the core financial result.

## 4. Test and validation results (run on Linux, DuckDB 2.0.0)

| Suite | Result |
|---|---|
| pytest (round 1) | 62 passed (superseded by the round-2 count below) |
| Without the cleaned CSV | 31 pass, 31 skip, reported INCOMPLETE, exit code 1 (verified by moving the file away and back) |
| out_val_load | 55 / 55 PASS |
| out_val_exclusion_counts | 24 / 24 PASS |
| out_val_analytical | 86 / 86 PASS |
| out_val_crosscheck (independent pandas) | 124 / 124 PASS |
| Output manifest | 72 tables, 0 stale files, hash and row count per file verified by test |
| Determinism | second full run produces an identical manifest (tested) |

Windows was not tested.

## 5. Full-data run status

Input `fpa_monthly_close_cleaned.csv`: SHA-256 `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47`, 152,682 rows, 192 columns (header fingerprint verified). Populations: P&L actual 58,340; with budget 55,043; balance sheet 2,953; any-status P&L 136,330. The raw and cleaned CSVs were not modified (hash re-verified after the test run).

## 6. Remaining assumptions (unresolved by design)

Account sign convention (R9), budget construction method, balance-sheet measurement basis, and the provenance and licence of the data. Thresholds (|z| >= 3, 50% net-budget guard, 0.25% and 2% sweeps) are project conventions, not accounting standards. An opposite-sign line is an observation, not a proven error.

## 7. Git status

Nothing was committed, pushed or published; no history was rewritten and no visibility changed.

## 8. Phase 5 readiness

Phase 4 is ready to hand over as an analytical base. Phase 5 should not start until you ask. Before it does, decide the sign convention and budget method, because every favourable/adverse label in Excel depends on them.

---

# Round 2: final targeted corrections (second external review)

Each point was checked before acting.

| # | Claim | Verdict | Evidence | Action (files) |
|---|---|---|---|---|
| 1 | `status <> 'PASS'` skips NULL statuses | **Valid in principle.** The SQL validation tables could not produce a NULL (a CASE ELSE gives FAIL), but the check itself was not fail-closed, and a NULL would have passed | Reproduced with a test: a NULL row is invisible to `<>` | `src/phase4_pipeline.py` now uses `IS DISTINCT FROM 'PASS'`, also fails on missing or empty validation tables and NULL or duplicate IDs; `tests/test_phase4.py` helpers and `sql/phase4/03_load_validation.sql` line 119 made NULL-safe |
| 1b | Tests must exercise the failure path | **Valid.** Proved: reverting the fix makes 2 tests fail | 5 mutation modes (FAIL, NULL status, duplicate ID, NULL ID, lowercase pass) each assert the run fails and the accepted CSV, MANIFEST and database are byte-identical; diagnostics go to a separate `_failed_run` folder and repeat failures replace only that folder | `tests/test_phase4_units.py` |
| 2 | Matrix lists 109 of 112 files | **Valid.** The two placeholders and the matrix itself were missing | Count mismatch confirmed | Placeholders now exist as real files; matrix regenerated from the actual package file list (count checked against the zip); CSV rows state exactly which automated checks ran (header = database columns, row count by two parsers, SHA-256, nan/inf scan) and that no cell was read manually |
| 2b | TEST_PLAN says nothing is implemented and describes automatic duplicate removal | **Valid** | Plan predated the tests; the pipeline flags and retains duplicates | `docs/TEST_PLAN.md`: status table (implemented / planned / CI not implemented); duplicate wording corrected; CI marked as non-existent |
| 3 | Exclude raw CSVs from git | **Valid, with a caveat the review missed.** `data/raw/fpa_monthly_close_raw_messy.csv` is already tracked since Stage 0, so `.gitignore` does not untrack it | `git ls-files` | `.gitignore` adds `data/raw/*.csv`, `data/raw/*.xlsx`. I did **not** untrack or delete anything; that is your decision (see limitations) |
| 4 | Forecast text over-claims | **Valid** | INS-05 said a bias correction "can remove" the pattern | `src/phase4_report.py` rewritten: a systematic directional difference in this sample, no claim about a correctable bias, recommendation is dated snapshots then a back-test, impact stated as none claimable; figures unchanged; both generated docs regenerated |
| 5a | `stg_close_raw` is an "exact image" | **Valid wording issue** | Table holds parsed field values as text | `src/phase4_pipeline.py` and `src/phase4_report.py` reworded; byte-level integrity is the SHA-256 gate |
| 5b | Redundant connection cleanup in the exception handler | **Valid, minor.** Closed twice in `finalize`; no cleanup at all in `main` for earlier failures | Read the code | One idempotent `_safe_close` in a `finally`; it cannot replace the root exception (tested with a connection whose `close()` also raises) |
| 5c | Promotion interruption test / document non-atomicity | **Valid** | Moving many files is not atomic | Two tests: failure on the first move leaves everything unchanged; failure on the MANIFEST move leaves new CSVs beside the old manifest with the database untouched (detectable). The limit is stated in the module docstring and here |

## Round 2 results (Linux, Python 3.13, DuckDB 2.0.0)

| Item | Result |
|---|---|
| Fixture suite (`tests/test_phase4_units.py`) | **42 PASS, 0 FAIL, 0 SKIP** |
| Full-data suite (`tests/test_phase4.py`) | **32 PASS, 0 FAIL, 0 SKIP** (the canonical CSV was present, so nothing was blocked) |
| Full pipeline independently re-run | Yes, exit 0; 55 + 24 + 86 + 124 validation rows all PASS, none NULL, no duplicate IDs |
| Output tables | 72, `stale_files_not_regenerated` is empty; every CSV re-checked against MANIFEST (row count, SHA-256) and against the database schema by the matrix generator |
| Raw CSV SHA-256 | `a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff` unchanged |
| Canonical cleaned CSV SHA-256 | `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47` unchanged |
| Git | nothing staged, committed or pushed |

## Remaining limitations (honest)

- **Git:** the raw CSV is already tracked, and the 72 Phase 4 output tables, docs and source are untracked but not ignored. Nothing was removed or staged. Until provenance, licence and sensitivity are checked, keep the repository private and keep local: the raw and cleaned CSVs, the DuckDB file and `data/processed/QC_*`. The output tables are aggregated, but they derive from the same unverified data.
- **Provenance and licence:** unverified (owner-described synthetic data).
- **Accounting conventions:** sign convention (R9), budget method and balance-sheet measurement basis are unresolved; opposite-sign lines are an observation, not a proven error.
- **Scale:** `report_scale` restoration is a provisional rule with a quantified sensitivity (`out_i4`, `out_i5`), not a confirmed fact.
- **Forecast timing:** no forecast version or as-of date; forecast skill and any correction are unknowable from this extract.
- **CI:** none exists; Windows untested; the promotion step is not atomic across files (documented, detectable).

## Final recommendation

**Accept Phase 4 as a validated analytical base and proceed to Phase 5 when you ask.** No blocker prevents acceptance of the analysis. Three decisions should precede any Excel favourable/adverse labelling: sign convention, budget method, forecast timing. Phase 5 has not been started.
