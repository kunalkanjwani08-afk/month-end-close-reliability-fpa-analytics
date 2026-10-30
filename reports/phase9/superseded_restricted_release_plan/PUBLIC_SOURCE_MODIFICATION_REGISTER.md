# Public Source Modification Register

Compares the **approved source** (master archive) with the **V1 public candidate** and with **V2**. No V2 file is claimed to be byte-identical to the approved source unless the table says so. "Logic changed?" refers to financial calculation logic; changes to *gating and validation* behaviour are stated separately because they matter for assurance.

| File | Approved source → V1 | V1 → V2 exact change | Why | Calculation logic changed? | Validation |
|---|---|---|---|---|---|
| `src/clean_fpa_monthly_close.py` | Present in V1 with an inferred price map and dataset-specific names/codes | **Excluded** | Dataset-derived reference values; cannot be published without verified rights | n/a | Absent from V2 |
| `src/phase5_excel.py` | Present in V1 | **Excluded**; synthetic `excel_variance_demo.py` added | Dataset-specific layout and labels | n/a | Demo covered by tests and a one-off LibreOffice recalculation |
| `src/phase4_report.py` | V1 changed one sentence ("+3.7% revenue ambition and -6% cost reduction targets applied uniformly" → a uniform revenue ambition and cost reduction target applied across all lines); no calculation code changed; compiled OK | **Excluded** | Report writer embeds result-specific narrative; the wording-only sanitisation in V1 was insufficient | No (V1); n/a (V2) | V1: py_compile. V2: absent |
| `src/phase6_report.py` | Present in V1 | **Excluded** | Result-specific narrative | n/a | Absent |
| `src/phase4_pipeline.py` | Hard-coded expected hash, rows, columns, header hash and account numbers | Constants removed; `verify_input`/`build_database` take a private config; `cfg_params` table built; `--config` argument; exit 3 on config error | Source-derived constants | **No** change to loading/typing/SQL execution. **Gating behaviour changed**: expected values now come from the owner config | 74-test fixture suite (config missing/null stop; verification; promotion) |
| `src/phase4_crosscheck.py` | Hard-coded entity, accounts, years | Takes config; entity = first sorted entity; years derived from data; salary-check entity derived | Source-derived literals | Cross-check **sampling choices changed** (which entity/year is spot-checked); formulas unchanged | py_compile; not run against data in this phase |
| `src/phase6_dashboard.py` | Hard-coded salary account | Read from config; `cfg` added to payload | Source-derived constant | No | py_compile; not run (inputs withheld) |
| `src/phase6_core.js` | Hard-coded discount account constant | Resolved from `P.cfg.discountGl`; text generic | Source-derived constant | No | `node --check`; not run in a browser in this phase |
| `src/phase6_views.js` | Hard-coded baseline line; account text; budget-insight hypothesis echoing an observed pattern | Line removed; text generic; hypothesis neutralised | Source-derived content | No | `node --check`; not browser-tested in this phase |
| `src/phase6_template.html` | Hard-coded count | Removed | Source-derived | No | Scan |
| `src/phase6_style.css` | Identical to approved | Unchanged | — | No | Hash equal to master |
| `sql/phase4/02_…`, `05_…` | Identical to approved | Unchanged | — | No | Hash equal to master |
| `sql/phase4/01,04,06,07,08,09,10,11` | V1 had dataset-specific comments and GL literals | GL literals → `cfg_params`; comments de-identified | Source-derived | No change to query logic other than the literal source | Empty-schema smoke test: all scripts parse and bind. **Results not verified** |
| `sql/phase4/03_load_validation.sql` | V1 had expected-count baselines and a hard-coded account-count constant | Replaced with structural/partition checks and invariants | Source-derived baselines | **Validation logic weakened by design**: structural checks do not detect value drift that a baseline would | Smoke test binds; check results on real data not verified |
| `sql/phase4/99_analytical_validation.sql` | V1 had expected counts, entity/year literals | Expected counts → recounts from `fact_close`; entity/year derived | Source-derived | Validation expectations now recomputed in-database, so some checks are **self-referential** and weaker than independent baselines | Smoke test binds |
| `tests/test_phase4_units.py` | Source-derived ids in fixtures | Invented ids 9901–9904; config tests added | Source-derived | n/a (tests) | 74 tests pass (whole suite) |
| `tests/conftest.py` | Identical | Unchanged | — | n/a | Hash equal to master |
| `src/private_config.py`, `src/fpa_cleaning_toolkit.py`, `src/excel_variance_demo.py`, `tests/test_cleaning_toolkit.py`, `tests/test_excel_variance_demo.py`, `config/private_config.template.json` | n/a | **New in V2** | Replace excluded functionality with generic/synthetic equivalents | n/a | Fixture tests; not validated against any real data |

## Honest summary

- Financial calculation formulas were not edited. Several **assurance** mechanisms were changed: expected-value gating now depends on an owner-supplied config, cross-check sampling choices differ, and two SQL validation scripts lost their independent baselines.
- The modified code has been checked for syntax, binding (SQL on an empty schema) and fixture-level behaviour. It has **not** been re-run end to end on the real data in this phase, so equality of outputs with the approved version is **unproven**.
