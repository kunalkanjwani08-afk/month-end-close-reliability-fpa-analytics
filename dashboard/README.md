# dashboard — Phase 6 interactive FP&A dashboard

| Item | Path |
|---|---|
| **Dashboard (standalone HTML, 7.3 MB)** | [`outputs/phase6/fpa_financial_analytics_dashboard.html`](../outputs/phase6/fpa_financial_analytics_dashboard.html) |
| Builder (Python) | [`src/phase6_dashboard.py`](../src/phase6_dashboard.py) (+ [`phase6_core.js`](../src/phase6_core.js), [`phase6_views.js`](../src/phase6_views.js), [`phase6_style.css`](../src/phase6_style.css), [`phase6_template.html`](../src/phase6_template.html), [`phase6_report.py`](../src/phase6_report.py)) |
| QA report and screenshots | [`outputs/phase6/DASHBOARD_QA_REPORT.md`](../outputs/phase6/DASHBOARD_QA_REPORT.md), [`outputs/phase6/qa_screens/`](../outputs/phase6/qa_screens/) |
| User guide | [`docs/DASHBOARD_USER_GUIDE.md`](../docs/DASHBOARD_USER_GUIDE.md) |

## How to open it

1. Download `fpa_financial_analytics_dashboard.html` (GitHub: open the file, then the *Download raw file* button), or clone the repository.
2. Double-click it. It opens in any modern browser; no server, no internet connection, no installation.

**GitHub does not run it.** GitHub shows the file as source code; the dashboard is **not** hosted online and this repository does not claim a live demo. Hosting (for example GitHub Pages) would be a separate decision.

Nine tabs, global filters, scenario selectors, cross-filtering, CSV export and print; light/dark theme. It embeds 136,330 line-level records of the synthetic dataset, so the file works offline.

**Rebuild:** `python src/phase4_pipeline.py` then `python src/phase6_dashboard.py` (needs the database from the pipeline).
