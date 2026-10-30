"""SQL analysis automated tests (DuckDB SQL layer + independent pandas cross-check).

FULL-DATA tests: they need the private canonical cleaned CSV. When it is absent they are SKIPPED and the run is reported
INCOMPLETE by conftest.py (non-zero exit) - a skip is never a pass. Fixture tests that need no data live in
tests/test_sql_pipeline_units.py.
Run:  python -m pytest tests -q
The module builds the SQL analysis database once from the canonical cleaned CSV (about 25 s) into a temp folder and never
touches build/fpa_analysis.duckdb. Tests cover: input gates and failure behaviour, schema/keys/types, every
SQL validation check, the independent cross-check, run-to-run reproducibility, and *mutation tests* that prove the
validations can actually fail when the data or an output is wrong (a check that cannot fail proves nothing).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import independent_crosscheck as xc  # noqa: E402
import sql_analysis_pipeline as pp  # noqa: E402

CSV = pp.DEFAULT_CSV
pytestmark = [pytest.mark.fulldata,
              pytest.mark.skipif(not CSV.exists(), reason="canonical cleaned CSV not present (data/processed/)")]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_sql(con, name: str):
    for st in con.extract_statements((ROOT / "sql" / "analysis" / name).read_text(encoding="utf-8")):
        con.execute(st)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("sql")
    db, out = base / "t.duckdb", base / "out"
    assert pp.main(["--csv", str(CSV), "--db", str(db), "--out-dir", str(out)]) == 0
    return {"db": db, "out": out, "base": base}


@pytest.fixture()
def con(built):
    c = duckdb.connect(str(built["db"]), read_only=True)
    yield c
    c.close()


# ---------------------------------------------------------------------------------------------- input gates
def test_input_is_the_verified_canonical_file():
    info = pp.verify_input(CSV)
    assert info["sha256"] == pp.EXPECTED_SHA256 and info["n_cols"] == 192


def test_canonical_csv_is_not_modified_by_the_run(built):
    assert _sha(CSV) == pp.EXPECTED_SHA256


# ---------------------------------------------------------------------------------------------- schema and load
def test_row_and_column_counts(con):
    assert con.execute("select count(*) from stg_close_raw").fetchone()[0] == 152_682
    assert con.execute("select count(*) from fact_close").fetchone()[0] == 152_682
    assert len(con.execute("describe fact_close").fetchall()) == 192
    assert len(con.execute("describe stg_close_raw").fetchall()) == 192


def test_row_id_unique_and_column_types(con):
    assert con.execute("select count(distinct row_id) from fact_close").fetchone()[0] == 152_682
    types = dict(con.execute("select column_name, data_type from information_schema.columns where table_name='fact_close'").fetchall())
    assert types["actual_usd_adj"] == "DOUBLE" and types["period_end_date"] == "DATE"
    assert types["eligible_PL_actual"] == "BIGINT" and types["row_id"] == "VARCHAR"


def test_identifiers_keep_text_form(con):
    # GL codes and entity codes are identifiers: no leading-zero or format damage in the staging text
    assert con.execute("select count(*) from stg_close_raw where gl_account <> '' and not regexp_matches(gl_account, '^[0-9]{4}$')").fetchone()[0] == 0


# ---------------------------------------------------------------------------------------------- validation results
@pytest.mark.parametrize("table", ["out_val_load", "out_val_exclusion_counts", "out_val_analytical", "out_val_crosscheck"])
def test_all_validation_rows_pass(con, table):
    n, bad = con.execute(f"select count(*), count(*) filter (where status IS DISTINCT FROM 'PASS') from {table}").fetchone()
    assert n > 0 and bad == 0, f"{table}: {bad} failing of {n}"


def test_validation_suite_size(con):
    # guards against a validation file silently losing checks
    assert con.execute("select count(*) from out_val_load").fetchone()[0] >= 55
    assert con.execute("select count(*) from out_val_analytical").fetchone()[0] >= 86
    assert con.execute("select count(*) from out_val_crosscheck").fetchone()[0] >= 124


def test_independent_crosscheck_recomputes_and_agrees(con):
    res = xc.run_crosscheck(CSV, con)
    assert len(res) >= 124 and all(r["status"] == "PASS" for r in res)


def test_bridges_close_to_zero(con):
    assert con.execute("select max(abs(bridge_difference_usd)) from out_b8_variance_bridge").fetchone()[0] < 0.01
    assert con.execute("select max(abs(bridge_difference_usd)) from out_e4_gp_variance_bridge").fetchone()[0] < 0.01


def test_no_nan_or_infinity_in_any_output(built):
    c = duckdb.connect()
    for f in sorted(built["out"].glob("*.csv")):
        cols = c.execute(f"describe select * from read_csv('{f.as_posix()}')").fetchall()
        for name, typ, *_ in cols:
            if typ == "DOUBLE":
                n = c.execute(f"select count(*) from read_csv('{f.as_posix()}') where isinf(\"{name}\") or isnan(\"{name}\")").fetchone()[0]
                assert n == 0, f"{f.name}.{name}"
    c.close()


def test_percent_guard_never_publishes_on_netted_budget(con):
    assert con.execute("""select count(*) from out_b1_variance_section
                          where variance_pct_of_abs_budget is not null and budget_netting_ratio < 0.5""").fetchone()[0] == 0


def test_manifest_matches_files(built):
    m = json.loads((built["out"] / "MANIFEST.json").read_text())
    assert len(m["outputs"]) == 72 and m["stale_files_not_regenerated"] == []
    for name, meta in m["outputs"].items():
        assert _sha(built["out"] / name) == meta["sha256"]


# ---------------------------------------------------------------------------------------------- reproducibility
def test_second_run_is_byte_identical(built, tmp_path):
    out2 = tmp_path / "out2"
    assert pp.main(["--csv", str(CSV), "--db", str(tmp_path / "t2.duckdb"), "--out-dir", str(out2)]) == 0
    a = json.loads((built["out"] / "MANIFEST.json").read_text())
    b = json.loads((out2 / "MANIFEST.json").read_text())
    assert a == b


# ---------------------------------------------------------------------------------------------- mutation tests
@pytest.fixture()
def mutable(built, tmp_path):
    p = tmp_path / "m.duckdb"
    shutil.copy(built["db"], p)
    c = duckdb.connect(str(p))
    yield c
    c.close()


def _failures(c, table):
    return [r[0] for r in c.execute(f"select check_id from {table} where status IS DISTINCT FROM 'PASS' order by 1").fetchall()]


def test_mutation_dropping_an_eligible_flag_is_caught(mutable):
    mutable.execute("update fact_close set eligible_PL_actual = 0 where row_id = (select row_id from fact_close where eligible_PL_actual = 1 limit 1)")
    _run_sql(mutable, "03_load_validation.sql")
    f = _failures(mutable, "out_val_load")
    assert "L21" in f and "L36" in f


def test_mutation_changing_one_amount_is_caught_by_load_checks(mutable):
    mutable.execute("update fact_close set actual_usd_adj = actual_usd_adj * 10 where row_id = (select row_id from fact_close where scale_factor_applied = 1 and eligible_PL_actual = 1 limit 1)")
    _run_sql(mutable, "03_load_validation.sql")
    assert "L43" in _failures(mutable, "out_val_load")


def test_mutation_duplicate_row_id_is_caught(mutable):
    mutable.execute("update fact_close set row_id = (select min(row_id) from fact_close) where row_id = (select max(row_id) from fact_close)")
    _run_sql(mutable, "03_load_validation.sql")
    assert "L05" in _failures(mutable, "out_val_load")


def test_mutation_corrupting_a_published_total_is_caught(mutable):
    mutable.execute("update out_a1_pl_period_section set actual_usd = actual_usd + 100 where section = 'REVENUE' and period_ym = '2024-03'")
    _run_sql(mutable, "99_analytical_validation.sql")
    f = _failures(mutable, "out_val_analytical")
    assert {"A01", "A03", "A06"} <= set(f)


def test_mutation_breaking_a_bridge_is_caught(mutable):
    mutable.execute("update out_b1_variance_section set net_variance_usd = net_variance_usd + 5 where scenario = 'ALL_LINES' and section = 'OPEX'")
    _run_sql(mutable, "99_analytical_validation.sql")
    assert "B04" in _failures(mutable, "out_val_analytical")


def test_mutation_wrong_wape_is_caught_by_crosscheck(mutable):
    mutable.execute("update out_c1_forecast_section set wape = wape * 1.01 where scenario = 'ALL_LINES' and section = 'REVENUE'")
    res = xc.run_crosscheck(CSV, mutable)
    assert any(r["check_id"] == "X30" and r["status"] == "FAIL" for r in res)


def test_mutation_in_scenario_table_is_caught_by_crosscheck(mutable):
    mutable.execute("update out_i1_scenarios set revenue_usd = revenue_usd + 1000 where scenario = 'ALL_STATUSES'")
    res = xc.run_crosscheck(CSV, mutable)
    assert any(r["status"] == "FAIL" and "ALL_STATUSES" in r["description"] for r in res)


def test_pipeline_gate_refuses_to_promote_on_validation_failure(built, tmp_path, monkeypatch):
    # make the independent cross-check disagree and confirm the run exits non-zero without promoting the database
    real = xc.run_crosscheck

    def lying(csv, c):
        r = real(csv, c)
        r[0]["status"] = "FAIL"
        return r
    monkeypatch.setattr(xc, "run_crosscheck", lying)
    db = tmp_path / "g.duckdb"
    rc = pp.main(["--csv", str(CSV), "--db", str(db), "--out-dir", str(tmp_path / "o")])
    assert rc == 2 and not db.exists()


# ---------------------------------------------------------------------------------------------- report generator
def test_report_generator_writes_complete_register(built, tmp_path):
    import analysis_report_builder as rp
    assert rp.main(["--db", str(built["db"]), "--docs-dir", str(tmp_path)]) == 0
    reg = (tmp_path / "INSIGHT_REGISTER.md").read_text(encoding="utf-8")
    rep = (tmp_path / "FINANCIAL_ANALYSIS_REPORT.md").read_text(encoding="utf-8")
    assert reg.count("\n## INS-") == 7
    for k in range(1, 15):  # every entry carries all 14 required elements
        assert reg.count(f"**{k}. ") == 7, f"element {k}"
    import re
    assert not re.search(r"\bnan\b|\bNaN\b|\bNone\b(?=\s*[|)\]])|\binf\b", reg + rep), "unformatted missing value in a document"
    assert "{d[" not in reg + rep and "{M(" not in reg + rep


def test_report_generator_refuses_when_validation_fails(built, tmp_path):
    import analysis_report_builder as rp
    p = tmp_path / "bad.duckdb"
    shutil.copy(built["db"], p)
    c = duckdb.connect(str(p))
    c.execute("update out_val_load set status = 'FAIL' where check_id = 'L01'")
    c.close()
    assert rp.main(["--db", str(p), "--docs-dir", str(tmp_path / "docs")]) == 2
    assert not (tmp_path / "docs").exists()


# ---------------------------------------------------------------------------------------------- review-driven additions
def test_sign_categories_partition_every_budget_pair(con):
    n_all = con.execute("select count(*) from v_close where eligible_PL_actual = 1 and budget_usd_adj is not null").fetchone()[0]
    parts = con.execute("""select sign_cat_ab, count(*) from v_close where eligible_PL_actual = 1 and budget_usd_adj is not null
                           group by 1""").fetchall()
    assert {k for k, _ in parts} <= {"SAME_SIGN_NONZERO", "OPPOSITE_SIGN_NONZERO", "ZERO_INVOLVED"}
    assert sum(v for _, v in parts) == n_all == 55_043


def test_opposite_sign_share_of_forecast_error_is_published_not_assumed(con):
    rows = con.execute("""select sign_category, sum(abs_error_usd) from out_c2_error_attribution group by 1""").fetchall()
    tot = sum(v for _, v in rows)
    opp = dict(rows).get("OPPOSITE_SIGN_NONZERO", 0)
    assert 0.85 < opp / tot < 0.95          # headline ~89-91%; a collapse or inflation would signal a classification bug


def test_no_stale_output_files_in_the_accepted_folder():
    m = json.loads((ROOT / "build" / "sql_results" / "MANIFEST.json").read_text())
    assert m["stale_files_not_regenerated"] == []
    on_disk = {p.name for p in (ROOT / "build" / "sql_results").glob("*.csv")}
    assert on_disk == set(m["outputs"]), sorted(on_disk ^ set(m["outputs"]))


def test_account_mapping_has_no_conflicts(con):
    assert con.execute("select count(*) from out_a8_account_mapping_consistency where mapping_status = 'CONFLICT'").fetchone()[0] == 0


def test_mutation_sign_category_corruption_is_caught(mutable):
    mutable.execute("update out_b7_sign_category_profile set rows_in_category = rows_in_category + 1 where rowid = 0")
    _run_sql(mutable, "99_analytical_validation.sql")
    assert _failures(mutable, "out_val_analytical"), "a corrupted sign-category profile must fail at least one check"


def test_generated_docs_have_no_overclaiming_forecast_or_staging_statements():
    txt = "".join((ROOT / "docs" / f).read_text(encoding="utf-8") for f in ("FINANCIAL_ANALYSIS_REPORT.md", "INSIGHT_REGISTER.md"))
    low = txt.lower()
    assert "bias correction can remove" not in low and "exact image" not in low and "if the bias is removed" not in low
    assert "dated forecast snapshots" in low and "back-test" in low
