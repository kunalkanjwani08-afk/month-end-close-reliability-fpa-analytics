# excel — workbooks

| Workbook | What it is |
|---|---|
| [`fpa_month_end_close_analysis.xlsx`](fpa_month_end_close_analysis.xlsx) | **Main analysis workbook.** 12 sheets, 3,819 formulas, 7 charts and 137 live PASS/FAIL reconciliation checks, built only from the validated SQL results. |
| [`financial_reconciliation.xlsx`](financial_reconciliation.xlsx) | Independent pandas recalculation compared with the SQL results, the workbook and the dashboard. |
| [`data_lineage_reconciliation.xlsx`](data_lineage_reconciliation.xlsx) | Record-count waterfall from raw rows to each reporting population. |
| [`issue_log.xlsx`](issue_log.xlsx) | Issues found during independent validation (ISS-01 … ISS-18) and how each was handled. |

The cleaned dataset workbook is in [`data/processed/`](../data/processed/).

Generator for the main workbook: [`src/excel_workbook_builder.py`](../src/excel_workbook_builder.py) (XlsxWriter). Guide: [`docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md`](../docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md). The three reconciliation workbooks were produced by one-off validation scripts that are **not** part of the repository, so they are kept as evidence and cannot be regenerated from it. `issue_log.xlsx` is a point-in-time record of the independent validation (28-30 Oct 2026); several statuses in it have since changed (ISS-03 QC paths: resolved by regeneration; ISS-04 palette-validator path: resolved; ISS-05 clean-machine install: Linux fresh-venv run done, Windows still NOT TESTED; ISS-06 provenance: owner statement recorded, no licence). The current status of every open item is in [`docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md`](../docs/ASSUMPTIONS_LIMITATIONS_AND_RISKS.md).

**Tested:** formulas recalculated independently with headless LibreOffice. **Not tested:** native Microsoft Excel. The main workbook is formula-driven and has **no pivot tables**.
