# Phase 8 Final Documentation QA (correction round)

**Date:** 2026-10-30. **Scope:** documentation corrections only, following an independent review of the first Phase 8 package.
**Reviewer note:** this QA was run by the same assistant that made the corrections, so it is **not** an independent second-person review.

## 1. Preservation

| Check | Result | Evidence |
|---|---|---|
| First Phase 8 package preserved | **Pass** | `outputs/phase8/` untouched; corrected copy in `outputs/phase8_final/package/` |
| Phase 1-7 files unchanged | **Pass** | Re-hashed all 220 entries of the Phase 7 manifest: 216 match, 3 differ, 1 absent from the repo. These are the **same** three Phase 7 workbooks (data-lineage and financial reconciliation, issue log) and the same outside-repo file already recorded before this round. No file outside `outputs/phase8*` has a modification time after 12:00 on 2026-10-30. `git status` shows only the pre-existing entries |
| Historical Phase 7 manifest, counts and the PR.03.detail FAIL | **Unchanged** | Not edited. Phase 7 report still states 780 executed: 774 PASS, 1 FAIL, 1 BLOCKED, 4 NOT TESTED, plus 43 INFO |
| Raw/cleaned data, SQL, formulas, dashboard code | **Unchanged** | Not opened for writing |
| Commit / push / publish / visibility change | **None made** | Only read-only GitHub API calls and local file edits |

## 2. Reviewer claims checked against sources

| Claim | Finding |
|---|---|
| Repo is public and raw CSV in `main` | **Confirmed** (API: `private: false`; tree lists the CSV at 51,938,535 bytes; 3 commits; last push 2026-10-28T06:29:51Z) |
| Variance selector does not affect forecast | **Confirmed** by `phase6_core.js:558` note, `fcPops()` (no `varPop` reference) and the Phase 6 test row; the Phase 6 limitations line is the outlier |
| `source_system` labels | **Confirmed**: SAP 49,204; Oracle 25,582; Excel upload 25,514; NetSuite 25,364; Tally 24,980; `SAP ` (trailing space) 2,038; sum 152,682 |
| 350 non-posting records | **Confirmed** (`notes` = `subtotal row`: 350 of 152,682) |
| Cleaner supports `--input` | **Confirmed** in the argument parser (`src/clean_fpa_monthly_close.py`). Command **not re-run** |
| Guard needs the absolute value | **Confirmed** (`abs(den_net) >= 0.5 * den_abs`, `den_abs > 0`) |
| **Slight disagreement with the brief** | The brief puts the errata at `docs/...` and at `outputs/phase8_final/`; both copies are provided and are identical. The brief also says to preserve the original package "separately": the original stays in `outputs/phase8/` |
| ISS-19 | Added **only** to Phase 8 documents, labelled "Phase 8 supplemental"; the Phase 7 issue log is not edited and still lists ISS-01 to ISS-18 |

## 3. Final validation list

| Item | Result |
|---|---|
| Internal links in README + 14 docs (188 links) | **0 broken** (package overlaid on the repo root) |
| Source figures vs authoritative files | Same scan as the original review: 88 numbers not literally found in the source corpus, **the identical 88 as before** (file sizes and derived values already examined in the original review); no number added this round is unsupported (152,332 = 152,682 - 350; the label counts above were counted directly) |
| Phase 7 statistics | Match the Phase 7 report (780 / 774 / 1 / 1 / 4 / 43; 17 tested dashboard states; 216/3/1 manifest result) |
| Population counts | Unchanged from the first package (58,340; 136,330; 55,043; 54,851; 54,923; 2,953; 4,996 gap). Not recomputed from the database this round; the documents were not changed in these figures |
| Contradictory GitHub-visibility statements | **None remain** outside quoted "original statement" text in the errata and the original QA report copy. Searched: "private", "nothing ... committed/pushed/published", "git-ignored", "local only", "not in git" |
| "Verified source system" / "five source systems" | **None remain** (only quoted in the errata) |
| "152,682 journal lines" | **None remain**; the required grain sentence is used in 6 documents |
| Variance-filter scope | Dashboard guide corrected; no document says forecast is affected |
| Financial limitations still disclosed | **Yes**: all 17 register items kept, plus ISS-19; no definition changed |
| Unsupported public-release-readiness claim | **None**; every status line says not approved, and the repository is called a publication blocker |
| SHA-256 manifest | Recomputed in `PHASE8_UPDATED_FILE_MANIFEST_SHA256.txt`, with a supplemental current-hash section for the 3 changed Phase 7 workbooks |

## 4. Not verified / residual risk

- The browser selector tests, the cleaner and the Phase 4-7 pipeline were **not re-run**.
- Repository visibility is a **point-in-time** check; when it became public is unknown.
- Provenance, redistribution rights, source-platform origin and GL mapping correctness remain unverified.
- Population figures were not recomputed from the database in this round.
- No independent second-person review of the corrected package has taken place.
- Windows, clean-machine, native Excel, Firefox, Safari, screen-reader and printer testing are still outstanding.
