"""pytest configuration for the Phase 4 tests.

Why this file exists: tests that need the private canonical cleaned CSV are marked `fulldata` and are SKIPPED when the
CSV is absent. A skipped test proves nothing, so a run in which any `fulldata` test was skipped is reported loudly as
INCOMPLETE and exits non-zero. Set P4_ALLOW_SKIPPED_FULLDATA=1 only for a deliberate fixture-only run (for example on a
machine that never has the private CSV); the banner is still printed.
"""
from __future__ import annotations

import os

import pytest

SKIP_REASON_FRAGMENTS = ("canonical cleaned CSV not present", "LibreOffice not available")


def pytest_configure(config):
    config.addinivalue_line("markers", "fulldata: needs the canonical cleaned CSV (and, for integration tests, a full database build)")


def _skipped_fulldata(terminalreporter) -> list:
    out = []
    for rep in terminalreporter.stats.get("skipped", []):
        text = str(getattr(rep, "longrepr", ""))
        if any(f in text for f in SKIP_REASON_FRAGMENTS):
            out.append(rep)
    return out


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    st = terminalreporter.stats
    passed, failed = len(st.get("passed", [])), len(st.get("failed", [])) + len(st.get("error", []))
    skipped = len(st.get("skipped", []))
    fd = len(_skipped_fulldata(terminalreporter))
    terminalreporter.write_sep("=", "TEST RESULT (PASS / FAIL / SKIP reported separately)")
    terminalreporter.write_line(f"PASS: {passed}    FAIL: {failed}    SKIP: {skipped} (of which full-data tests skipped: {fd})")
    if fd:
        terminalreporter.write_line(
            f"INCOMPLETE - {fd} test(s) were SKIPPED because the canonical cleaned CSV or LibreOffice is absent. "
            "This is NOT a full pass: place data/processed/fpa_monthly_close_cleaned.csv / install LibreOffice and rerun.", red=True, bold=True)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr is None or session.exitstatus != 0:
        return
    if _skipped_fulldata(tr) and os.environ.get("P4_ALLOW_SKIPPED_FULLDATA") != "1":
        session.exitstatus = 1  # never report an all-skipped important test set as a passing run
