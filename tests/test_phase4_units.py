"""Phase 4 unit and fixture tests. These need NO private data: they run anywhere and must always pass.

They cover the logic that the full-data tests cannot isolate: input gates, the sign-category rule (SQL macro and the
independent pandas version), robust-z/anomaly macros with constant, zero-MAD and missing inputs, the gross-profit
treatments on a hand-computed fixture (including all-negative and zero-involved rows), check-id uniqueness, and the
staged-promotion sentinel test (accepted artefacts must not change when a validation fails).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import phase4_crosscheck as xc  # noqa: E402
import phase4_pipeline as pp  # noqa: E402

SQL = ROOT / "sql" / "phase4"


def _statements(name: str):
    return list(duckdb.connect().extract_statements((SQL / name).read_text(encoding="utf-8")))


@pytest.fixture()
def mem():
    c = duckdb.connect()
    for st in _statements("01_dimensions_and_views.sql"):
        if st.query.lstrip().upper().startswith("CREATE OR REPLACE MACRO"):
            c.execute(st)
    yield c
    c.close()


# ------------------------------------------------------------------------------------------------ input gates
def test_missing_csv_stops_and_leaves_existing_db_untouched(tmp_path):
    db = tmp_path / "keep.duckdb"
    db.write_bytes(b"sentinel")
    rc = pp.main(["--csv", str(tmp_path / "nope.csv"), "--db", str(db), "--out-dir", str(tmp_path / "o")])
    assert rc == 1 and db.read_bytes() == b"sentinel" and not (tmp_path / "o").exists()


def test_empty_file_stops(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_bytes(b"")
    assert pp.main(["--csv", str(f), "--db", str(tmp_path / "d.duckdb"), "--out-dir", str(tmp_path / "o")]) == 1
    assert not (tmp_path / "d.duckdb").exists()


def test_hash_mismatch_is_an_integrity_error(tmp_path):
    f = tmp_path / "other.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    db = tmp_path / "d.duckdb"
    assert pp.main(["--csv", str(f), "--db", str(db), "--out-dir", str(tmp_path / "o")]) == 2
    assert not db.exists()


def test_wrong_column_count_stops_even_if_hash_accepted(tmp_path):
    f = tmp_path / "narrow.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(pp.PipelineError, match="columns"):
        pp.verify_input(f, expected_sha=pp.sha256_file(f), expected_rows=1)


def test_schema_mismatch_with_right_column_count_stops(tmp_path):
    f = tmp_path / "wide.csv"
    f.write_text(",".join(f"c{i}" for i in range(pp.EXPECTED_COLS)) + "\n" + ",".join("1" for _ in range(pp.EXPECTED_COLS)) + "\n", encoding="utf-8")
    with pytest.raises(pp.PipelineError, match="differ from the verified schema"):
        pp.verify_input(f, expected_sha=pp.sha256_file(f), expected_rows=1)


def test_duplicate_header_names_stop(tmp_path):
    f = tmp_path / "dup.csv"
    f.write_text(",".join(["x"] * pp.EXPECTED_COLS) + "\n", encoding="utf-8")
    with pytest.raises(pp.PipelineError, match="Duplicate"):
        pp.verify_input(f, expected_sha=pp.sha256_file(f), expected_rows=0)


# ------------------------------------------------------------------------------------------------ sign category
SIGN_CASES = [
    (5.0, 3.0, "SAME_SIGN_NONZERO"), (-5.0, -3.0, "SAME_SIGN_NONZERO"),
    (5.0, -3.0, "OPPOSITE_SIGN_NONZERO"), (-5.0, 3.0, "OPPOSITE_SIGN_NONZERO"),
    (0.0, 3.0, "ZERO_INVOLVED"), (3.0, 0.0, "ZERO_INVOLVED"), (0.0, 0.0, "ZERO_INVOLVED"), (0.0, -2.0, "ZERO_INVOLVED"),
    (None, 3.0, "MISSING_OR_UNAVAILABLE"), (3.0, None, "MISSING_OR_UNAVAILABLE"), (None, None, "MISSING_OR_UNAVAILABLE"),
    (None, 0.0, "MISSING_OR_UNAVAILABLE"),
]


@pytest.mark.parametrize("a,b,expected", SIGN_CASES)
def test_sql_sign_cat_macro(mem, a, b, expected):
    assert mem.execute("SELECT sign_cat(?::DOUBLE, ?::DOUBLE)", [a, b]).fetchone()[0] == expected


def test_pandas_sign_category_matches_sql_macro(mem):
    a = pd.Series([c[0] for c in SIGN_CASES], dtype="float64")
    b = pd.Series([c[1] for c in SIGN_CASES], dtype="float64")
    assert list(xc.sign_category(a, b)) == [c[2] for c in SIGN_CASES]
    for x, y, exp in SIGN_CASES:
        assert mem.execute("SELECT sign_cat(?::DOUBLE, ?::DOUBLE)", [x, y]).fetchone()[0] == exp


# ------------------------------------------------------------------------------------------------ safe_pct / robust_z
def test_safe_pct_guard(mem):
    q = "SELECT safe_pct(?::DOUBLE, ?::DOUBLE, ?::DOUBLE)"
    assert mem.execute(q, [10, 100, 100]).fetchone()[0] == pytest.approx(0.1)      # fully net
    assert mem.execute(q, [10, 40, 100]).fetchone()[0] is None                     # netted below 50% of gross -> not published
    assert mem.execute(q, [10, 50, 100]).fetchone()[0] == pytest.approx(0.2)       # exactly at the guard
    assert mem.execute(q, [10, 0, 0]).fetchone()[0] is None                        # zero denominators
    assert mem.execute(q, [10, -100, 100]).fetchone()[0] == pytest.approx(0.1)     # negative net budget uses abs()


def test_robust_z_edge_cases(mem):
    q = "SELECT robust_z(?::DOUBLE, ?::DOUBLE, ?::DOUBLE)"
    assert mem.execute(q, [5, 5, 0]).fetchone()[0] is None          # constant series: MAD = 0 -> not scorable
    assert mem.execute(q, [9, 5, 0]).fetchone()[0] is None          # zero MAD with a deviation must NOT become infinity
    assert mem.execute(q, [None, 5, 1]).fetchone()[0] is None
    assert mem.execute(q, [5, None, 1]).fetchone()[0] is None
    assert mem.execute(q, [5, 5, None]).fetchone()[0] is None
    assert mem.execute(q, [5, 5, 1]).fetchone()[0] == 0
    assert mem.execute(q, [1000, 5, 1]).fetchone()[0] == pytest.approx((1000 - 5) / 1.4826)


def test_anomaly_class_never_treats_null_as_within_range(mem):
    q = "SELECT anomaly_class(?::DOUBLE, ?::DOUBLE)"
    assert mem.execute(q, [None, 0]).fetchone()[0].startswith("not scorable")
    assert mem.execute(q, [None, None]).fetchone()[0].startswith("not scorable")
    assert mem.execute(q, [1.0, 1.0]).fetchone()[0] == "within range"
    assert mem.execute(q, [4.0, 0.5]).fetchone()[0].startswith("amount unusual with normal")
    assert mem.execute(q, [4.0, 4.0]).fetchone()[0].startswith("coverage-driven")
    assert mem.execute(q, [4.0, None]).fetchone()[0].startswith("amount unusual, row-count score not available")
    assert mem.execute(q, [-3.0, 0.1]).fetchone()[0].startswith("amount unusual with normal")   # boundary |z| = 3, negative side


# ------------------------------------------------------------------------------------------------ gross profit fixture
GP_ROWS = [  # row_id, section, gl, amount, sign_flag
    ("r1", "REVENUE", 4100, 100.0, "ALL_NON_NEGATIVE"),
    ("r2", "REVENUE", 4190, -20.0, "ALL_NEGATIVE"),
    ("r3", "REVENUE", 4190, 10.0, "ALL_NON_NEGATIVE"),
    ("r4", "REVENUE", 4190, 0.0, "ALL_NON_NEGATIVE"),          # zero-involved row sits INSIDE the non-negative row set
    ("r5", "COGS", 5100, 30.0, "ALL_NON_NEGATIVE"),
    ("r6", "COGS", 5100, -5.0, "SINGLE_COLUMN_SIGN_FLIP"),
    ("r7", "OPEX", 6100, 999.0, "ALL_NON_NEGATIVE"),           # not revenue/COGS: must not enter gross profit
]


def _gp_con(mem, rows):
    mem.execute("""CREATE TABLE v_pl_actual (row_id VARCHAR, entity_code VARCHAR, division VARCHAR, period_year INTEGER,
                   period_ym VARCHAR, section VARCHAR, gl_account INTEGER, actual_usd_adj DOUBLE, sign_flag VARCHAR)""")
    mem.executemany("INSERT INTO v_pl_actual VALUES (?, 'E1', 'D1', 2024, '2024-01', ?, ?, ?, ?)",
                    [(r[0], r[1], r[2], r[3], r[4]) for r in rows])
    wanted = ("gp_treatment", "gp_rowset", "v_gp_rows", "out_e1_gross_profit")
    for st in _statements("07_gross_profit.sql"):
        q = st.query
        if any(f" {w} " in q.split("AS", 1)[0] + " " for w in wanted):
            mem.execute(st)
    return mem


def _e1(c, rowset, treatment):
    r = c.execute("""SELECT revenue_usd, cogs_usd, gross_profit_usd, gross_margin_pct, rows_in_scope FROM out_e1_gross_profit
                     WHERE rowset = ? AND treatment = ? AND period = 'ALL YEARS'""", [rowset, treatment]).fetchone()
    return r


def test_gross_profit_treatments_hand_computed(mem):
    c = _gp_con(mem, GP_ROWS)
    # ROWS_ALL: revenue S1 = 100-20+10+0 = 90 ; S2 = 100-20-10-0 = 70 ; S3 = 100 ; COGS = 30-5 = 25
    assert _e1(c, "ROWS_ALL", "GP_S1_SIGNED_AS_RECORDED")[:3] == (90.0, 25.0, 65.0)
    assert _e1(c, "ROWS_ALL", "GP_S2_DISCOUNT_ABS")[:3] == (70.0, 25.0, 45.0)
    assert _e1(c, "ROWS_ALL", "GP_S3_EXCL_DISCOUNT")[:3] == (100.0, 25.0, 75.0)
    assert _e1(c, "ROWS_ALL", "GP_S1_SIGNED_AS_RECORDED")[3] == pytest.approx(65 / 90)
    # ROWS_ALL_NON_NEGATIVE keeps the zero row (zero counts as non-negative) and drops ALL_NEGATIVE / SIGN_FLIP rows
    assert _e1(c, "ROWS_ALL_NON_NEGATIVE", "GP_S1_SIGNED_AS_RECORDED")[:3] == (110.0, 30.0, 80.0)
    assert _e1(c, "ROWS_ALL_NON_NEGATIVE", "GP_S2_DISCOUNT_ABS")[:3] == (90.0, 30.0, 60.0)
    assert _e1(c, "ROWS_ALL_NON_NEGATIVE", "GP_S3_EXCL_DISCOUNT")[:3] == (100.0, 30.0, 70.0)
    # the OPEX row is outside gross profit: 6 revenue/COGS rows in ROWS_ALL, 5 in the non-negative set
    assert _e1(c, "ROWS_ALL", "GP_S1_SIGNED_AS_RECORDED")[4] == 6
    assert _e1(c, "ROWS_ALL_NON_NEGATIVE", "GP_S1_SIGNED_AS_RECORDED")[4] == 4


def test_gross_profit_all_negative_revenue_gives_null_margin_not_error(mem):
    c = _gp_con(mem, [("n1", "REVENUE", 4100, -50.0, "ALL_NEGATIVE"), ("n2", "COGS", 5100, 10.0, "ALL_NON_NEGATIVE")])
    rev, cogs, gp, margin, _ = _e1(c, "ROWS_ALL", "GP_S1_SIGNED_AS_RECORDED")
    assert (rev, cogs, gp) == (-50.0, 10.0, -60.0) and margin is None


def test_gross_profit_rowset_with_no_rows_is_absent_not_zero(mem):
    c = _gp_con(mem, [("n1", "REVENUE", 4100, -50.0, "ALL_NEGATIVE")])
    assert _e1(c, "ROWS_ALL_NON_NEGATIVE", "GP_S1_SIGNED_AS_RECORDED") is None


# ------------------------------------------------------------------------------------------------ check-id uniqueness
def test_assert_unique_ids_accepts_unique_and_rejects_duplicates():
    xc.assert_unique_ids([{"check_id": "A"}, {"check_id": "B"}])
    with pytest.raises(ValueError, match="X90_01"):
        xc.assert_unique_ids([{"check_id": "X90_01"}, {"check_id": "X90_01"}, {"check_id": "B"}])


def test_validation_failures_reports_duplicate_check_ids():
    c = duckdb.connect()
    c.execute("CREATE TABLE out_val_t (check_id VARCHAR, status VARCHAR)")
    c.execute("INSERT INTO out_val_t VALUES ('A','PASS'), ('A','PASS'), ('B','PASS')")
    own = [b for b in pp.validation_failures(c) if b[0] == "out_val_t" or b[1:2] == ("out_val_t",)]
    assert own == [("out_val_t", "DUPLICATE_CHECK_ID", "A", 2)]
    c.execute("INSERT INTO out_val_t VALUES ('C','FAIL')")
    assert ("out_val_t", "C", "FAIL") in pp.validation_failures(c)
    c.close()


def test_sql_validation_files_have_unique_check_ids_in_source():
    import re
    for name in ("03_load_validation.sql", "99_analytical_validation.sql"):
        ids = re.findall(r"^\s*(?:SELECT|UNION ALL SELECT)\s+'([A-Z]\d{2,3})'", (SQL / name).read_text(encoding="utf-8"), flags=re.M)
        assert len(ids) == len(set(ids)) and len(ids) >= 50, f"{name}: {len(ids)} ids, {len(ids) - len(set(ids))} duplicated"


# ------------------------------------------------------------------------------------------------ staged promotion
def _mini_run(tmp_path, status, extra_rows=()):
    """A tiny run: one output table plus the four REQUIRED validation tables (all PASS) plus out_val_x carrying `status`
    (a string, or None for a NULL status) and any extra (check_id, status) rows."""
    tmp_db = tmp_path / "d.duckdb.partial"
    con = duckdb.connect(str(tmp_db))
    con.execute("CREATE TABLE out_x (a INTEGER)")
    con.execute("INSERT INTO out_x VALUES (1), (2)")
    for t in pp.REQUIRED_VALIDATION_TABLES:
        con.execute(f"CREATE TABLE {t} (check_id VARCHAR, status VARCHAR)")
        con.execute(f"INSERT INTO {t} VALUES ('{t}_ok', 'PASS')")
    con.execute("CREATE TABLE out_val_x (check_id VARCHAR, status VARCHAR)")
    con.execute("INSERT INTO out_val_x VALUES ('V1', ?)", [status])
    for cid, st in extra_rows:
        con.execute("INSERT INTO out_val_x VALUES (?, ?)", [cid, st])
    return con, tmp_db


def _accepted(tmp_path):
    out, db = tmp_path / "out", tmp_path / "d.duckdb"
    out.mkdir()
    (out / "x.csv").write_text("OLD-ACCEPTED", encoding="utf-8")
    (out / "MANIFEST.json").write_text("OLD-MANIFEST", encoding="utf-8")
    db.write_bytes(b"OLD-DB")
    return out, db


def test_failed_validation_leaves_accepted_artefacts_untouched(tmp_path):
    out, db = _accepted(tmp_path)
    con, tmp_db = _mini_run(tmp_path, "FAIL")
    with pytest.raises(pp.IntegrityError):
        pp.finalize(con, tmp_db, db, out)
    assert (out / "x.csv").read_text() == "OLD-ACCEPTED"
    assert (out / "MANIFEST.json").read_text() == "OLD-MANIFEST"
    assert db.read_bytes() == b"OLD-DB"
    assert (tmp_path / "out_failed_run" / "x.csv").exists() and (tmp_path / "d.duckdb.failed").exists()
    assert not any(p.name.startswith(".out_staging_") for p in tmp_path.iterdir()), "staging folder must not be left behind"


def test_passing_validation_promotes_everything(tmp_path):
    out, db = _accepted(tmp_path)
    con, tmp_db = _mini_run(tmp_path, "PASS")
    manifest = pp.finalize(con, tmp_db, db, out)
    assert (out / "x.csv").read_text().splitlines() == ["a", "1", "2"]
    m = json.loads((out / "MANIFEST.json").read_text())
    assert set(m["outputs"]) == set(manifest) == {"x.csv", "val_x.csv"} | {t[4:] + ".csv" for t in pp.REQUIRED_VALIDATION_TABLES}
    assert m["outputs"]["x.csv"]["rows"] == 2
    assert db.read_bytes()[:4] != b"OLD-" and not tmp_db.exists()
    assert not any(p.name.startswith(".out_staging_") for p in tmp_path.iterdir())


def test_stale_output_files_are_reported_in_manifest(tmp_path):
    out, db = _accepted(tmp_path)
    (out / "gone.csv").write_text("stale", encoding="utf-8")
    con, tmp_db = _mini_run(tmp_path, "PASS")
    pp.finalize(con, tmp_db, db, out)
    assert json.loads((out / "MANIFEST.json").read_text())["stale_files_not_regenerated"] == ["gone.csv"]


# ------------------------------------------------------------------------------------------------ fail-closed mutation tests
def _snapshot(out, db):
    return ((out / "x.csv").read_bytes(), (out / "MANIFEST.json").read_bytes(), db.read_bytes(), sorted(p.name for p in out.iterdir()))


@pytest.mark.parametrize("status,extra", [
    ("FAIL", ()),                                   # an explicit failure
    (None, ()),                                     # a NULL status: `status <> 'PASS'` would silently skip this row
    ("PASS", (("V1", "PASS"),)),                    # duplicate validation id
    ("PASS", ((None, "PASS"),)),                    # missing validation id
    ("pass", ()),                                   # not exactly PASS (case) must not count as a pass
], ids=["FAIL", "NULL-status", "duplicate-id", "NULL-id", "lowercase-pass"])
def test_each_failure_mode_fails_the_run_and_leaves_accepted_artefacts_unchanged(tmp_path, status, extra):
    out, db = _accepted(tmp_path)
    before = _snapshot(out, db)
    con, tmp_db = _mini_run(tmp_path, status, extra)
    with pytest.raises(pp.IntegrityError):
        pp.finalize(con, tmp_db, db, out)
    assert _snapshot(out, db) == before
    assert (tmp_path / "out_failed_run" / "x.csv").exists()      # diagnostics live in a SEPARATE folder
    assert (tmp_path / "d.duckdb.failed").exists()


def test_null_status_is_detected_by_the_null_safe_check_but_not_by_the_naive_one():
    c = duckdb.connect()
    c.execute("CREATE TABLE out_val_t (check_id VARCHAR, status VARCHAR)")
    c.execute("INSERT INTO out_val_t VALUES ('A', NULL)")
    assert c.execute("SELECT count(*) FROM out_val_t WHERE status <> 'PASS'").fetchone()[0] == 0          # the bug
    assert c.execute("SELECT count(*) FROM out_val_t WHERE status IS DISTINCT FROM 'PASS'").fetchone()[0] == 1
    assert ("out_val_t", "A", None) in pp.validation_failures(c)
    c.close()


def test_missing_or_empty_required_validation_table_fails_closed():
    c = duckdb.connect()
    assert ("MISSING_VALIDATION_TABLE", "out_val_load") in pp.validation_failures(c)
    for t in pp.REQUIRED_VALIDATION_TABLES:
        c.execute(f"CREATE TABLE {t} (check_id VARCHAR, status VARCHAR)")
    assert ("out_val_load", "EMPTY_VALIDATION_TABLE") in pp.validation_failures(c)
    for t in pp.REQUIRED_VALIDATION_TABLES:
        c.execute(f"INSERT INTO {t} VALUES ('ok', 'PASS')")
    assert pp.validation_failures(c) == []
    c.close()


def test_repeated_failures_replace_only_the_failed_run_folder(tmp_path):
    out, db = _accepted(tmp_path)
    before = _snapshot(out, db)
    for _ in range(2):
        con, tmp_db = _mini_run(tmp_path, "FAIL")
        with pytest.raises(pp.IntegrityError):
            pp.finalize(con, tmp_db, db, out)
    assert _snapshot(out, db) == before


def test_cleanup_never_hides_the_root_exception(tmp_path, monkeypatch):
    class BadCon:
        def close(self):
            raise OSError("close-also-failed")

    def boom(con, stage, reference_dir=None):
        raise RuntimeError("root-cause-export-failed")
    monkeypatch.setattr(pp, "export_outputs", boom)
    with pytest.raises(RuntimeError, match="root-cause-export-failed"):
        pp.finalize(BadCon(), tmp_path / "t.partial", tmp_path / "d.duckdb", tmp_path / "out")
    assert not any(p.name.startswith(".out_staging_") for p in tmp_path.iterdir())


def _fail_replace_into(monkeypatch, out, name):
    real = pp.os.replace

    def fake(src, dst, *a, **k):
        if Path(dst) == out / name:
            raise OSError(f"simulated failure while promoting {name}")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(pp.os, "replace", fake)


def test_promotion_failure_on_first_move_leaves_accepted_artefacts_unchanged(tmp_path, monkeypatch):
    out, db = _accepted(tmp_path)
    before = _snapshot(out, db)
    con, tmp_db = _mini_run(tmp_path, "PASS")
    _fail_replace_into(monkeypatch, out, min(f"{t[4:]}.csv" for t in pp.REQUIRED_VALIDATION_TABLES + ("out_val_x", "out_x")))  # first CSV promoted (sorted order)
    with pytest.raises(OSError, match="simulated failure"):
        pp.finalize(con, tmp_db, db, out)
    assert (out / "x.csv").read_bytes() == before[0] and (out / "MANIFEST.json").read_bytes() == before[1] and db.read_bytes() == before[2]


def test_promotion_failure_midway_is_a_documented_non_atomic_case_that_is_detectable(tmp_path, monkeypatch):
    """LIMIT: moving many files is not atomic. If the MANIFEST move fails after the CSVs moved, the accepted CSVs are new but
    the manifest and database are still the old ones. The database (moved last) is untouched and the mismatch is detectable."""
    out, db = _accepted(tmp_path)
    con, tmp_db = _mini_run(tmp_path, "PASS")
    _fail_replace_into(monkeypatch, out, "MANIFEST.json")
    with pytest.raises(OSError, match="simulated failure"):
        pp.finalize(con, tmp_db, db, out)
    assert db.read_bytes() == b"OLD-DB"                           # database is promoted last, so it never moved
    assert (out / "MANIFEST.json").read_text() == "OLD-MANIFEST"
    assert (out / "x.csv").read_text().splitlines() == ["a", "1", "2"]   # new CSV beside an old manifest = detectable mixed state
