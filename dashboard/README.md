# dashboard — interactive FP&A dashboard

| Item | Path |
|---|---|
| **Dashboard (standalone HTML, 7.3 MB)** | [`fpa_financial_analytics_dashboard.html`](fpa_financial_analytics_dashboard.html) |
| Screenshots | [`screenshots/`](screenshots/) |
| Builder (Python) | [`src/dashboard_builder.py`](../src/dashboard_builder.py), with [`dashboard_core.js`](../src/dashboard_core.js), [`dashboard_views.js`](../src/dashboard_views.js), [`dashboard_style.css`](../src/dashboard_style.css) and [`dashboard_template.html`](../src/dashboard_template.html) |
| User guide | [`docs/DASHBOARD_USER_GUIDE.md`](../docs/DASHBOARD_USER_GUIDE.md) |

## How to open it

1. Download `fpa_financial_analytics_dashboard.html` (GitHub: open the file, then *Download raw file*), or clone the repository.
2. Double-click it. It opens in any modern browser; no server, no internet connection, no installation.

**GitHub does not run it.** GitHub shows the file as source code; the dashboard is **not** hosted online and this repository does not claim a live demo.

Nine tabs, global filters, scenario selectors, cross-filtering, CSV export, print layout and a light/dark theme. It embeds 136,330 line-level records of the synthetic dataset, so it works offline.

**Rebuild:** follow steps 0-6 in [`HOW_TO_RUN.txt`](../HOW_TO_RUN.txt) (the builder needs the database from the SQL analysis pipeline).
