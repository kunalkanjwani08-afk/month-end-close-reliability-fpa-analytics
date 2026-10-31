# Documentation index

Start with the document that matches what you need. All figures describe a **synthetic** extract for the fictional NovaBridge Industries.

## Where to start

| If you want to... | Read |
|---|---|
| Understand the result in five minutes (executive / financial reporting) | [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md), then [FINANCIAL_ANALYSIS_REPORT.md](FINANCIAL_ANALYSIS_REPORT.md) and [INSIGHT_REGISTER.md](INSIGHT_REGISTER.md) |
| Know where the data came from and what each column means | [DATA_PROVENANCE.md](DATA_PROVENANCE.md), [DATA_DICTIONARY.md](DATA_DICTIONARY.md) |
| See how the raw file was cleaned and quality-checked | [DATA_AND_CLEANING_METHODOLOGY.md](DATA_AND_CLEANING_METHODOLOGY.md) (includes the CPU-reproducibility finding, section 14) |
| Check a metric definition, rule or assumption | [FINANCIAL_METRICS.md](FINANCIAL_METRICS.md), [ASSUMPTIONS_LIMITATIONS_AND_RISKS.md](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md) |
| Run or read the SQL | [SQL_ANALYTICS_GUIDE.md](SQL_ANALYTICS_GUIDE.md), [../sql/README.md](../sql/README.md) |
| Use the Excel workbook | [EXCEL_FINANCIAL_ANALYSIS_GUIDE.md](EXCEL_FINANCIAL_ANALYSIS_GUIDE.md), [../excel/README.md](../excel/README.md) |
| Use the dashboard | [DASHBOARD_USER_GUIDE.md](DASHBOARD_USER_GUIDE.md), [../dashboard/README.md](../dashboard/README.md) |
| Re-run the project and its tests | [../HOW_TO_RUN.txt](../HOW_TO_RUN.txt) (Windows PowerShell and Linux; expected output and failure codes for every step) |

`FINANCIAL_ANALYSIS_REPORT.md` and `INSIGHT_REGISTER.md` are **generated** by `src/analysis_report_builder.py`. Change the generator, not the Markdown.

## Terminology used throughout

| Term | Meaning |
|---|---|
| NovaBridge Industries | The fictional group the data is about |
| Month-end close / FP&A / P&L | Monthly accounting close; financial planning and analysis; income statement |
| Posted-eligible population | The 58,340 lines that pass every eligibility rule, including journal status = Posted; the base for headline figures |
| As-reported amount | The value parsed from the source text, before any scale restoration |
| Scale-adjusted amount | The as-reported amount restored to full scale where a documented test supports it |
| Provisional assumption | A working rule chosen so the analysis can proceed; changing it changes the numbers |
| Unresolved rule | A rule the data cannot settle and the owner has not decided (sign convention, duplicates, consolidation) |

## Evidence labels

| Label | Meaning |
|---|---|
| **Verified** | Checked against a project file or by a check that was run |
| **Owner-stated** | The project owner's own statement; not independently checkable |
| **Assumption** | A working convention, not established fact |
| **Unresolved** | Open; the evidence that would settle it is listed in the risk register |
| **Not tested** | No test was run (for example Windows, native Excel, Firefox, Safari) |

Every financial result should state its population, period, currency, formula, assumptions and limitations; if one is missing in a document, treat the figure as incomplete.
