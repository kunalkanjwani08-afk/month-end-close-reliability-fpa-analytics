# excel — Phase 5 analysis workbook and Phase 7 reconciliation workbooks

The workbooks live where the generators write them (moving them would break the manifests and tests), and are listed here for convenience.

| Workbook | What it is | Path |
|---|---|---|
| Month-end close analysis (final) | 12 sheets, 3,819 formulas, 137 live PASS/FAIL reconciliation checks, built only from the validated database | [`outputs/phase5/fpa_month_end_close_analysis.xlsx`](../outputs/phase5/fpa_month_end_close_analysis.xlsx) |
| Data lineage reconciliation | Phase 7 independent record-count waterfall | [`outputs/phase7/DATA_LINEAGE_RECONCILIATION.xlsx`](../outputs/phase7/DATA_LINEAGE_RECONCILIATION.xlsx) |
| Financial reconciliation | Phase 7 independent pandas vs SQL / Excel / dashboard comparison | [`outputs/phase7/FINANCIAL_RECONCILIATION.xlsx`](../outputs/phase7/FINANCIAL_RECONCILIATION.xlsx) |
| Issue log | Phase 7 issues ISS-01 … ISS-18 | [`outputs/phase7/ISSUE_LOG.xlsx`](../outputs/phase7/ISSUE_LOG.xlsx) |

Generator: [`src/phase5_excel.py`](../src/phase5_excel.py) (XlsxWriter). Guide: [`docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md`](../docs/EXCEL_FINANCIAL_ANALYSIS_GUIDE.md).

**Tested:** formulas recalculated independently with headless LibreOffice. **Not tested:** native Microsoft Excel. The workbook is formula-driven and contains 7 native Excel charts; it contains **no pivot tables**.
