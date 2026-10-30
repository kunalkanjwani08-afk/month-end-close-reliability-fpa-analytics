# Phase 5 QA report - FP&A Excel workbook

Report written: 2026-10-29 12:56 UTC. Workbook: `fpa_month_end_close_analysis.xlsx` (generated 2026-10-29T12:55:33Z).

This report records what was actually run against the **saved** workbook. Failures and skips are listed, not hidden. Microsoft Excel was **not** used; recalculation was done with LibreOffice.

## 1. Result at a glance

| Item | Result |
|---|---|
| Tests | **PASS 51 / FAIL 0 / SKIP 0** (pytest exit code 0) |
| Reconciliation sheet (live formulas) | 137 of 137 checks PASS |
| LibreOffice independent recalculation | 3819 formulas compared, 0 mismatches |
| Formula cells / errors / external links | 3819 / 0 / 0 |
| Sheets / tables / charts | 12 / 22 / 7 |
| Workbook SHA-256 | `71e23dca9e0bbce3295223188c296cd3bd5ff51759825487bae049705375f561` |

## 2. Source identity

| Input | Value |
|---|---|
| Phase 4 database SHA-256 | `00e7437697c8e11baab5d2cff7036d6dda3d251a139774adee0a2dfe92c413e6` |
| Phase 4 manifest SHA-256 | `41f572e0cca248f9c78e356b53776066ddaf1cf5cd064b0d56dc47aa1d302bdb` |
| Phase 4 output tables verified against manifest hashes and row counts | 72 |
| Phase 4 validation rows (all must PASS) | out_val_load: 55/55; out_val_exclusion_counts: 24/24; out_val_analytical: 86/86; out_val_crosscheck: 124/124 |
| Approved cleaned CSV SHA-256 | `c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47` (present and matches the approved SHA-256) |
| Generator `src/phase5_excel.py` SHA-256 | `02b45089fc71e6b10d16c738e9796755409290014e85945c80aad932ac564d0a` |

## 3. Reconciliation by area (from the saved file)

| Area | Checks | PASS |
|---|---:|---:|
| Population | 5 | 5 |
| Monthly P&L | 10 | 10 |
| Cross-sheet | 3 | 3 |
| Entity | 6 | 6 |
| Budget vs Actual | 47 | 47 |
| Forecast | 48 | 48 |
| Gross Profit | 15 | 15 |
| Insights | 1 | 1 |
| Data Quality | 1 | 1 |
| Definitions | 1 | 1 |

Expected values come from the Phase 4 analytical views (`v_pl_actual`, `v_var_scn`, `v_fc_scn`, `v_gp_rows`), not from the `out_*` tables the sheets were built from. Tolerances: counts 0; USD 0.5; ratios 1e-6.

## 4. Test results

| Test | Result | Note |
|---|---|---|
| `test_workbook_opens_and_has_the_twelve_sheets_in_order` | PASS |  |
| `test_every_sheet_has_content_and_a_title` | PASS |  |
| `test_source_tables_present_with_expected_row_counts` | PASS |  |
| `test_features_charts_tables_freeze_panes_filters` | PASS |  |
| `test_charts_have_titles` | PASS |  |
| `test_formulas_present_and_all_cached` | PASS |  |
| `test_no_formula_errors` | PASS |  |
| `test_no_external_links_anywhere` | PASS |  |
| `test_cross_sheet_references_resolve_to_populated_cells` | PASS |  |
| `test_range_references_stay_inside_their_tables` | PASS |  |
| `test_every_formula_recalculates_identically_in_libreoffice` | PASS |  |
| `test_reconciliation_fails_when_a_number_is_tampered` | PASS |  |
| `test_reconciliation_sheet_all_checks_pass_and_are_real_comparisons` | PASS |  |
| `test_summary_and_exec_status_link_to_reconciliation` | PASS |  |
| `test_populations_match_sql` | PASS |  |
| `test_monthly_totals_match_sql_by_section` | PASS |  |
| `test_monthly_rows_match_sql_month_by_month` | PASS |  |
| `test_signs_are_as_recorded_not_flipped` | PASS |  |
| `test_entity_and_division_totals_equal_monthly_total` | PASS |  |
| `test_variance_and_percent_formulas_and_guard` | PASS |  |
| `test_guard_cases_exist_and_are_suppressed_in_the_monthly_table` | PASS |  |
| `test_bridge_difference_is_zero_everywhere` | PASS |  |
| `test_forecast_figures_match_sql` | PASS |  |
| `test_gross_profit_treatments_match_sql_and_row_set_is_not_called_sign_consistent` | PASS |  |
| `test_insight_blocks_have_all_16_fields_and_match_the_register` | PASS |  |
| `test_insight_amounts_are_recomputed_from_the_database` | PASS |  |
| `test_forecast_claims_are_not_overstated` | PASS |  |
| `test_provisional_labels_everywhere` | PASS |  |
| `test_unresolved_rules_are_preserved_verbatim` | PASS |  |
| `test_no_forbidden_labels_or_invented_metrics` | PASS |  |
| `test_no_unit_economics_or_balance_sheet_balances` | PASS |  |
| `test_lineage_and_source_identity_recorded` | PASS |  |
| `test_colour_convention_blue_inputs_black_formulas_green_links` | PASS |  |
| `test_number_formats_negatives_red_in_parentheses_zero_dash` | PASS |  |
| `test_tab_navigation_links_back_to_start` | PASS |  |
| `test_generator_is_deterministic_and_does_not_touch_the_database` | PASS |  |
| `test_generator_fails_closed_on_a_tampered_phase4_output` | PASS |  |
| `test_generator_exit_1_on_missing_inputs` | PASS |  |
| `test_generator_refuses_failing_phase4_validation` | PASS |  |
| `test_wrong_csv_hash_is_refused` | PASS |  |
| `test_canonical_csv_and_raw_csv_unchanged` | PASS |  |
| `test_manifest_matches_the_saved_workbook_and_inputs` | PASS |  |
| `test_generator_script_hash_in_workbook_equals_current_script` | PASS |  |
| `test_executive_summary_separates_the_three_forecast_populations` | PASS |  |
| `test_gl_headings_agree_with_the_database` | PASS |  |
| `test_start_here_account_count_is_derived` | PASS |  |
| `test_comparable_population_table_and_reconciliation_checks_exist` | PASS |  |
| `test_insight_register_wording_is_evidence_bounded` | PASS |  |
| `test_universal_claim_counts_are_true_in_the_database` | PASS |  |
| `test_insight_ranking_links_to_detail_blocks` | PASS |  |
| `test_gp_components_reconcile_to_the_stated_gap` | PASS |  |

## 5. Checks performed on the saved file

- Reopened with openpyxl (formulas and cached values): 12 sheets in the specified order; every formula has a cached value; no `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`, `#NUM!` anywhere.
- No external links: no `externalLink` package parts, no external relationship targets, no `[n]`/`.xls`/URL references in any formula or hyperlink.
- Every cross-sheet reference points at an existing, populated cell.
- Every formula was recalculated by LibreOffice from a copy **with the cached values removed** (so LibreOffice had to compute all of them) and compared with the saved cached values.
- Mutation test: one monthly revenue input was changed in a copy and recalculated; the reconciliation sheet turned to FAIL on the checks that depend on it (proof the checks can fail).
- Totals, populations, variance and guarded %, forecast WAPE/bias, gross-profit treatments, signed GL 4190 amount and entity/division totals were re-derived from the database views and compared.
- Insight text equals the Phase 4 register; key figures were rebuilt from the database and found in the text; each block has all 16 fields; observed fact and hypothesis are separate; no savings amount is claimed.
- Rules R1-R14 are copied from `docs/FINANCIAL_METRICS.md` with their statuses unchanged (R9, R11, R12 stay Unresolved).
- Determinism: two builds with the same timestamp are byte-identical; the database is opened read-only and its hash is unchanged.
- Fail-closed gates: tampered Phase 4 output, missing inputs, failing validation row and wrong CSV hash all stop the build (exit 1 or 2) with no workbook written.

## 6. Not done / limits (read before accepting)

- **Microsoft Excel was not used.** The file was written with XlsxWriter and recalculated with LibreOffice 24.2. Excel-specific behaviour (for example table styles, conditional-format rendering, Windows fonts) has not been observed.
- Visual inspection: the saved workbook was rendered to PDF with LibreOffice (49 pages, fit to page width) and every page was looked at as an image (100 dpi, two pages per view): all 12 sheets and all populated sections, including the full length of Insights & Actions. Clipped columns, a double space in a headline, row heights and an unpaginated Definitions sheet were found and fixed this way. NOT done: opening the file in Microsoft Excel or on screen at 100% zoom, clicking the navigation links, and checking frozen panes, filters and conditional-format colours in a spreadsheet application (these are checked structurally by the tests only). At print scale, small text in the long tables was read for clipping and '###' only (a text search of the PDF found no '###').
- Tests were run on Linux, not on the user's Windows machine.
- Earlier copies of the cleaned and raw CSVs that were found outside the project folder did not match the approved hashes (Phase 4 finding); they were not used. This build uses the hash-verified Phase 4 database. The canonical CSV in this repository was hash-checked at generation.
- Everything remains **provisional**: Posted-only status rule (R6), scale restoration (R7), FX direction (R8), variance-% convention (R10), per-line summing of budget/forecast/prior-year, and the exclusion of junk entities (R4). Sign convention (R9), duplicates (R11) and consolidation (R12) are unresolved. The data is synthetic; provenance and licence are unverified.
- Not built because the data cannot support it: EBITDA, close duration / on-time close, cost-centre variance, forecast skill or bias correction, price-volume-mix and unit economics, balance-sheet ratios, consolidated group results.
- Insight text is taken from the Phase 4 register and is not re-validated by a second analyst.
- No dashboard, no Power BI, nothing committed or published.

## 7. How to regenerate

```
python src/phase5_excel.py                      # verifies Phase 4, builds the workbook and MANIFEST.json
python -m pytest tests/test_phase5_excel.py -q   # needs the workbook; LibreOffice for 2 tests
python src/phase5_excel.py --qa-report          # reruns the tests and rewrites this report
```

Exit codes: 0 ok; 1 missing/unreadable input; 2 integrity or reconciliation failure. Use `--generated-at 2026-10-29T12:00:00Z` for a byte-identical rebuild.
