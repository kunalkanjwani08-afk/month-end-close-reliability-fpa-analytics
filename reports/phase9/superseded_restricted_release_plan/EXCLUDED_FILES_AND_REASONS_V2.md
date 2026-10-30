# Excluded Files and Reasons (V2)

Nothing was deleted from any archive or from V1. "Excluded" means not placed in the V2 public folder.

| Excluded item | Where it exists | Reason | Replacement in V2 |
|---|---|---|---|
| Raw dataset (CSV) and any copy | Private archives | Provenance and redistribution rights unverified; contains person-like owner names and user IDs | None |
| Cleaned dataset, QC files, review workbook | Private archives | Row-level derived data; QC files also carry build-machine paths | None |
| DuckDB database, 72 result tables, manifests | Private archives | Results and row-level content | SQL scripts only |
| Analysis report, insight register, dictionary, metric notes | Private archives | Source-derived outcomes | Methodology-only docs |
| Excel workbook | Private archives | Contains results of the dataset | Synthetic demo |
| Generated dashboard, payload stats, screenshots | Private archives | Embeds line-level records | Builder source only |
| Phase 7 QA package, QA reconciliation workbooks | Private archives | Data-derived records | Summary only |
| `src/clean_fpa_monthly_close.py` | Master archive, V1 | Inferred price map; names, codes and calibration derived from the dataset | `src/fpa_cleaning_toolkit.py` (generic, independently written) |
| `src/phase5_excel.py` | Master archive, V1 | Dataset-specific workbook layout and labels | `src/excel_variance_demo.py` (synthetic) |
| `src/phase4_report.py`, `src/phase6_report.py` | Master archive, V1 | Result-specific narrative and figures | None |
| Phase 4/5/6 data-dependent tests, Phase 7 independent-reference code | Master and Phase 7 archives | Read the private dataset or encode its structure | Fixture tests |
| `config/private_config.json` | Owner only | Holds source-derived expectations; must never be committed | `config/private_config.template.json` (null placeholders) |
| Phase 9 V1 files `outputs/phase9/*` | Cloud working repo and Downloads | V1 conclusions were superseded | V2 reports |
| Caches (`__pycache__`, `.pytest_cache`) | Removed from the V2 folder before manifesting | Housekeeping | — |

**Not excluded but conditional** (see inventory): SQL scripts and the dashboard-builder source retain structural labels and field names of the private schema; the owner must decide whether these may be public (items O-3, O-5 in the checklist).
