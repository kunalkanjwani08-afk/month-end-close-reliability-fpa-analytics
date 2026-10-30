# sql — Phase 4 DuckDB analysis

Twelve numbered scripts in [`phase4/`](phase4/) define every population once and then build the analysis. They are executed in order by [`src/phase4_pipeline.py`](../src/phase4_pipeline.py) against an in-process DuckDB database built from the cleaned CSV.

| Script | Purpose |
|---|---|
| `01_dimensions_and_views` | Typed fact table, dimensions, the reporting views (`v_pl_actual`, `v_pl_budget`, `v_pl_forecast`, `v_pl_prior`, `v_bs_actual`, …) |
| `02_grain_and_overview` | Row grain, period coverage, P&L by period / entity / division / GL |
| `03_load_validation` | Load checks against the cleaner's counts |
| `04_budget_variance` | Budget variance (actual − budget), guarded %, bridges, persistence |
| `05_forecast_error` | Forecast error, bias, WAPE |
| `06_prior_year` | Prior-year column vs the dataset's own prior-year actuals |
| `07_gross_profit` | Three explicit treatments of the discount account |
| `08_cost_structure` | Pareto shares, HHI |
| `09_trend_volatility` | Trend and volatility |
| `10_balance_sheet` | Balance-sheet records, kept apart from the P&L |
| `11_dq_exposure_scenarios` | Status / scale / sign / duplicate scenarios, exclusion waterfall |
| `99_analytical_validation` | Structural and analytical validation rows (fail-closed) |

**Database setup.** There is nothing to install beyond `pip install -r requirements.txt` (the `duckdb` Python package). `python src/phase4_pipeline.py` creates `data/processed/phase4_fpa.duckdb`, runs the scripts, validates (55 + 24 + 86 + 124 rows) and writes 72 output tables to [`outputs/phase4/`](../outputs/phase4/). Exit code 0 means every validation passed. The database file itself is not published.

Account numbers and other dataset-specific values are read from the cleaned data, not hard-coded into the scripts.
