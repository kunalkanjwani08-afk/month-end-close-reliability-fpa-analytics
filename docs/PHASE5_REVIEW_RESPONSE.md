# Phase 5 review round - assessment of the external (ChatGPT) review and what changed

Assessed 2026-10-29. Every point was checked against the Phase 4 database before anything was changed. Nothing was committed, pushed or published.

## 1. Verdict per point

| # | ChatGPT point | Verdict | Evidence / action |
|---|---|---|---|
| 1 | Executive Summary mixes matched-subset and all-lines forecast WAPE | **Correct** | The old summary showed only the matched pair (2.59% vs 3.67%, 24,372 lines). Now three populations are shown side by side with sample sizes: A matched same-sign 24,372 lines (2.59% / 3.67%); B comparable lines, any sign, 29,131 lines (26.81% / 29.26%); C all lines with a forecast, 30,879 lines (26.59%, no budget WAPE). The pasted figures were re-verified and are current. |
| 2a | G1 heading says 21 accounts, table has 24 | **Correct** | `out_a4_pl_gl` has 24 accounts. Heading, Start Here text and the test now derive the count from the data. |
| 2b | G2 note lists Below-EBITDA and Tax as cost | **Correct** | `out_f1_cost_by_gl` holds 17 accounts: COGS 5, People 3, Opex 8, D&A 1. Note corrected; population unchanged. |
| 3 | Revalidate all insights | **Correct in substance, with one nuance** | See section 2. The nuance: INS-03's universal claim is true on its stated basis (same-sign lines; 36/36 months, 6/6 entities, 5/5 divisions, 20/20 operating accounts) so it was kept but now states that basis and that the all-lines view differs. |
| 4 | Sign conventions / presentation | **Correct (mostly already satisfied)** | No signs were changed and no favourable/unfavourable labels exist. Wording that implied direction-as-judgement ("shortfall", "overrun", "optimistic") was replaced by arithmetic wording. |
| 5 | Docs, usability, lineage, visual review, Git check | **Correct** | README header was stale (said Phase 5 did not exist); HOW_TO_RUN and README now describe the real procedure. Lineage sheet quoted reconciliation IDs that did not exist (R-27, R-17..R-20 etc.): corrected. Definitions sheet printed across 10 pages: fixed. Several clipped columns fixed. Insights navigation links added. See section 4 for Git. |
| 6 | Regenerate from the generator, test, reconcile | **Done** | See section 3. |

Parts of the review that were not accepted as stated: none. One of my own earlier working notes (that the forecast's edge "vanishes" on comparable lines) was wrong when checked against the figures and is not in any deliverable: on comparable lines the forecast is still about 2 points closer than the budget for revenue, COGS and opex and 0.8 points further for people costs.

## 2. Insight corrections (generator `src/phase4_report.py`, register regenerated from the database)

| Insight | Before | After |
|---|---|---|
| INS-01 | impact sized the exposure | adds: sizes the exposure only; does not show which journal-status policy is correct |
| INS-02 | "Driver category: opposite-sign lines" | "Concentration of error ... an association in this extract; no cause is established" |
| INS-03 | "in every month, entity and division, and in almost every account"; "revenue shortfall / cost overrun" | "on same-sign lines in all 36 months, all 6 entities, all 5 divisions and every one of the 20 operating accounts (the all-lines view differs)"; per-section same-side counts added; D&A, below-EBITDA, tax stated as not covered; arithmetic wording |
| INS-04 | "revenue shortfall", "cost of goods above budget" | "revenue below budget", "COGS above budget"; population note that revenue and COGS variances are on different line sets; components reconcile (revenue -$7.02M = 57%, COGS $5.30M = 43% of -$12.32M, difference 0.00) |
| INS-05 | forecast closer than budget, "always on the optimistic side" | two populations never mixed (matched 24,372 lines; comparable 29,131 lines), both shown for all four sections; confidence Low for any general claim; no optimism language |
| INS-06 | "constant rate", "never move from a standard rate" | "near-constant": 98.4% of lines within 0.5% of the entity median (lowest entity-year 90.6%); neither a pay-rate nor a headcount effect is established or excluded |
| INS-07 | unchanged (provisional status and the unverifiable price reference were already stated) | - |

## 3. Workbook changes (generator `src/phase5_excel.py`)

| Item | Before | After |
|---|---|---|
| Reconciliation checks | 113 | 137 (+24: matched-subset and comparable-line count and WAPE for four sections, recomputed independently from `v_close`) |
| Formula cells | 3,737 | 3,819 |
| Worksheets | 12 | 12 (unchanged; no new sheets) |
| Forecast sheet | F3 matched only | F3b added: comparable all-lines table (same lines for both measures) |
| Executive Summary | two matched WAPE rows | three-population block with sample sizes, definitions and the not-skill caveat |
| GL sheet | "21 accounts", Pareto note listed 6 sections | 24 accounts; note lists the 4 sections actually used and says Below-EBITDA and Tax are excluded |
| Insights sheet | no navigation | ranking IDs link to blocks; "Back to ranking" under each; label column wider |
| Print layout | Definitions printed over 10 pages | fits one page wide; 49 pages in total |

## 4. Git tracking (report only; no action taken)

- `data/raw/fpa_monthly_close_raw_messy.csv` **is tracked and was pushed** (commit 1d601c0 on origin/main); the repository is public. The cleaned CSV, database and QC outputs are git-ignored.
- Provenance and licence of that raw file are unverified. Removing it from the public repository and history is an owner decision (it would require a history rewrite or making the repository private); it has not been touched.
- Untracked Phase 4 and Phase 5 work remains uncommitted.
