#!/usr/bin/env python3
"""SQL analysis - DuckDB loading, SQL execution, validation and export.

Usage (from the repository root):
    python src/sql_analysis_pipeline.py                      # build DB, run all SQL, export outputs
    python src/sql_analysis_pipeline.py --csv PATH --db PATH --out-dir PATH

What it does, in order (it stops at the first failed gate, before anything is written):
  1. Verifies the cleaned CSV (192 columns, regenerated from the raw file by src/clean_fpa_monthly_close.py): it exists, its
     SHA-256 matches the approved value exactly - or, as a reported (never silent) fallback, after rounding two floating-point
     diagnostic columns (see NORMALISED_SHA256) - it has 152,682 rows and 192 columns, the header equals the expected schema
     (hash of the header line) and the required fields exist.
  2. Builds the DuckDB file in a temporary path:
       stg_close_raw  all 192 columns as TEXT: the parsed source field values (blank = ''); byte-level integrity is the SHA-256 gate
       fact_close     same rows, typed (blank -> NULL), row_id traceability kept
  3. Runs the numbered SQL files in sql/analysis/ in order.
  4. Exports every out_* table to CSV into a run-specific STAGING folder (deterministic ordering) with a MANIFEST
     (row count + SHA-256 per output) so reruns can be compared byte for byte.
  5. Runs every validation gate on the staged run (all out_val_* rows must be PASS, check identifiers must be unique).
  6. ONLY if every gate passes: moves the staged outputs and then the database into the accepted locations.
     If any gate fails, the previously accepted database, output CSVs and MANIFEST are left byte-for-byte untouched;
     the failed run's outputs are kept in <out-dir>_failed_run/ and its database as <db>.failed for diagnosis.
LIMIT (not overclaimed): promotion moves many files one at a time (each move is atomic, the set is not). A crash or I/O
error DURING promotion (after validation passed) can leave some new CSVs next to an older MANIFEST/database. The order
(CSVs, then MANIFEST, then database) means the database, the last item, changes only after everything else succeeded, and
tests/MANIFEST verification detects a mixed state. Validation failures, which are the normal failure path, never reach it.
The cleaned CSV and the raw data are only ever read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "processed" / "fpa_monthly_close_cleaned.csv"
DEFAULT_DB = ROOT / "build" / "fpa_analysis.duckdb"
DEFAULT_OUT = ROOT / "build" / "sql_results"
SQL_DIR = ROOT / "sql" / "analysis"

# ---- facts reported by the cleaning stage (QC_Report of the run that produced the CSV) -------------
EXPECTED_SHA256 = "c184b677bacc6f23086e3b5eedd71836643cb75064e428a1ebfee4c075fa9b47"
# Floating-point last-digit variation (investigated 31 Oct 2026, see docs/DATA_AND_CLEANING_METHODOLOGY.md, section 14):
# on CPUs without AVX-512 numpy's log10 differs from the reference environment in the last 1-15 ulps, so the cleaner writes
# a different last digit into exactly two diagnostic columns (14,071 cells; 190 of the 192 columns are identical, no flag or
# decision changes). The byte-exact SHA-256 above stays the primary gate. If, and only if, it fails, the file is accepted
# when its NORMALISED hash matches: the same CSV re-serialised with those two columns rounded to 8 significant digits.
# Acceptance by the fallback is never silent: verify_input() reports sha_status = "normalised" and the pipeline prints a warning.
NORMALISED_SHA256 = "7ceb8cafb8205aa95c0d716ef9bbba409750c6f247f14cc9e7f1b0efed7e5477"
FLOAT_VARIANT_COLUMNS = ("price_identity_log10_ratio", "row_log10_magnitude")
NORMALISED_SIGNIFICANT_DIGITS = 8
EXPECTED_ROWS = 152_682
REQUIRED_VALIDATION_TABLES = ("out_val_load", "out_val_exclusion_counts", "out_val_analytical", "out_val_crosscheck")
EXPECTED_COLS = 192
# Header fingerprint: sha256 of the 192 column names joined by "\n" (guards against reordering/renaming).
EXPECTED_HEADER_SHA256 = "5ae3fd0a30ee5aa095892cb06c33194831f2053c1f39283b6836c27082420ef6"

REQUIRED_FIELDS = [
    "row_id", "source_row_number", "document_no", "is_posting_row", "entity_code", "legal_entity", "division",
    "gl_account", "account_name", "account_group", "fs_line", "statement", "period_ym", "period_year",
    "period_month", "approval_status", "actual_usd_parsed", "actual_usd_adj", "budget_usd_adj", "forecast_usd_adj",
    "prior_year_usd_adj", "report_scale_raw", "scale_decision", "scale_confidence", "dup_tier", "sign_flag",
    "eligible_PL_actual", "eligible_PL_variance", "eligible_BS_actual", "excl_PL_actual", "excl_PL_variance",
    "excl_BS_actual",
]

# ---- type rules for fact_close ---------------------------------------------------------------------------------
DOUBLE_COLS_EXTRA = {
    "fx_rate", "qty", "headcount_fte", "price_identity_log10_ratio", "row_log10_magnitude", "scale_peer_zscore",
    "scale_divisor_found", "scale_factor_applied", "actual_usd_adj_abs_uncertainty", "usd_from_local_div_rate",
    "fx_rel_diff_vs_actual", "magnitude_robust_z",
}
DATE_COLS = {"period_end_date", "posting_date"}
INT_COLS_EXTRA = {
    "source_row_number", "is_posting_row", "gl_account", "period_year", "period_month", "fiscal_year",
    "doc_group_size", "dup_cols_compared", "dup_cols_agree", "dup_sign_diff_cols", "n_flags",
    "eligible_PL_actual", "eligible_PL_variance", "eligible_BS_actual",
}


class PipelineError(RuntimeError):
    """A gate failed; message is shown to the user and the process exits with code 1."""


class IntegrityError(PipelineError):
    """Hash/size mismatch; exit code 2."""


def col_type(name: str) -> str:
    if name in DATE_COLS:
        return "DATE"
    if name in DOUBLE_COLS_EXTRA or name.endswith("_parsed") or name.endswith("_adj"):
        return "DOUBLE"
    if name in INT_COLS_EXTRA or name.startswith("flag_"):
        return "BIGINT"
    return "VARCHAR"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_header(path: Path) -> list[str]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def normalised_sha256(path: Path, columns=FLOAT_VARIANT_COLUMNS, digits: int = NORMALISED_SIGNIFICANT_DIGITS) -> str:
    """SHA-256 of the CSV re-serialised (LF line ends, minimal quoting) with `columns` rounded to `digits` significant digits.

    Used only as the documented fallback of verify_input(): it ignores last-digit floating-point differences in those columns and
    nothing else. Every other cell, the header, the row order and the row count must be identical."""
    h = hashlib.sha256()
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    fmt = "." + str(digits) + "g"
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        idx = [header.index(c) for c in columns if c in header]
        writer.writerow(header)
        for n, row in enumerate(reader, 1):
            for i in idx:
                v = row[i]
                if v != "":
                    try:
                        row[i] = format(float(v), fmt)
                    except ValueError:
                        pass  # not a number: leave as is (it will then differ from the reference)
            writer.writerow(row)
            if n % 5000 == 0:
                h.update(buf.getvalue().encode("utf-8"))
                buf.seek(0)
                buf.truncate(0)
    h.update(buf.getvalue().encode("utf-8"))
    return h.hexdigest()


def verify_input(csv_path: Path, expected_sha: str = EXPECTED_SHA256, expected_rows: int = EXPECTED_ROWS,
                 expected_cols: int = EXPECTED_COLS, expected_normalised: str | None = NORMALISED_SHA256) -> dict:
    """Gate 1. Raises before any database is created.

    sha_status is "exact" (byte-identical to the approved file) or "normalised" (identical except last-digit floating-point
    variation in FLOAT_VARIANT_COLUMNS). Anything else raises IntegrityError."""
    if not csv_path.exists():
        raise PipelineError(
            f"Cleaned CSV not found: {csv_path}\n"
            "SQL analysis needs fpa_monthly_close_cleaned.csv (152,682 rows x 192 columns) produced by "
            "src/clean_fpa_monthly_close.py --output-dir data/processed. Do not rebuild it from the 77-column workbook sheet.")
    if csv_path.stat().st_size == 0:
        raise PipelineError(f"The cleaned CSV is empty (0 bytes): {csv_path}")
    sha = sha256_file(csv_path)
    norm = None
    if sha == expected_sha:
        status = "exact"
    else:
        norm = normalised_sha256(csv_path) if expected_normalised else None
        if expected_normalised and norm == expected_normalised:
            status = "normalised"
        else:
            raise IntegrityError(
                f"SHA-256 mismatch for {csv_path}\n  actual  : {sha}\n  expected: {expected_sha}\n"
                + (f"  normalised actual  : {norm}\n  normalised expected: {expected_normalised}\n" if expected_normalised else "")
                + "The file is not the cleaned output the data cleaning report describes (a last-digit floating-point difference in "
                  f"{', '.join(FLOAT_VARIANT_COLUMNS)} would have been accepted, but something else differs). Nothing was loaded.")
    header = read_header(csv_path)
    if len(header) != expected_cols:
        raise PipelineError(f"Expected {expected_cols} columns, found {len(header)}.")
    if len(set(header)) != len(header):
        raise PipelineError("Duplicate column names in the CSV header.")
    fp = hashlib.sha256("\n".join(header).encode()).hexdigest()
    if fp != EXPECTED_HEADER_SHA256:
        raise PipelineError("The 192 column names/order differ from the verified schema "
                            f"(header fingerprint {fp}, expected {EXPECTED_HEADER_SHA256}).")
    missing = [c for c in REQUIRED_FIELDS if c not in header]
    if missing:
        raise PipelineError(f"Required fields missing from the CSV header: {missing}")
    return {"sha256": sha, "sha_status": status, "normalised_sha256": norm, "bytes": csv_path.stat().st_size,
            "n_cols": len(header), "header": header}


def build_database(csv_path: Path, db_tmp: Path, expected_rows: int = EXPECTED_ROWS) -> duckdb.DuckDBPyConnection:
    header = read_header(csv_path)
    if db_tmp.exists():
        db_tmp.unlink()
    con = duckdb.connect(str(db_tmp))
    # One thread: parallel aggregation adds floating-point numbers in a varying order, which changes the last digits of
    # sums between runs. Single-threaded execution makes every export byte-identical (reproducibility is tested).
    con.execute("SET threads = 1")
    # --- staging: parsed source field values held as text, blank stays ''. Byte-level integrity is the input SHA-256 gate, not this table ---
    col_defs = ", ".join(f"'{c}': 'VARCHAR'" for c in header)
    con.execute(
        f"""CREATE TABLE stg_close_raw AS
            SELECT * FROM read_csv('{csv_path.as_posix()}', header=true, delim=',', quote='"', escape='"',
                   columns={{{col_defs}}}, nullstr='\x01NULLSTR\x01', max_line_size=10000000,
                   encoding='utf-8', strict_mode=true, sample_size=-1)""")
    n = con.execute("SELECT count(*) FROM stg_close_raw").fetchone()[0]
    if n != expected_rows:
        raise PipelineError(f"Loaded {n:,} rows, expected {expected_rows:,}.")
    # --- typed fact table: blank -> NULL, numeric casts are STRICT (a failed cast aborts the build) -----
    sel = []
    for c in header:
        t = col_type(c)
        src = f"NULLIF(trim({c}), '')" if t != "VARCHAR" else f"NULLIF({c}, '')"
        expr = src if t == "VARCHAR" else f"CAST({src} AS {t})"
        sel.append(f"{expr} AS {c}")
    con.execute("CREATE TABLE fact_close AS SELECT " + ", ".join(sel) + " FROM stg_close_raw ORDER BY source_row_number::BIGINT")
    n2 = con.execute("SELECT count(*) FROM fact_close").fetchone()[0]
    if n2 != n:
        raise PipelineError(f"fact_close has {n2:,} rows, staging has {n:,}.")
    return con


def run_sql_files(con: duckdb.DuckDBPyConnection, sql_dir: Path = SQL_DIR) -> list[dict]:
    log = []
    for f in sorted(sql_dir.glob("[0-9][0-9]_*.sql")):
        t0 = time.time()
        text = f.read_text(encoding="utf-8")
        stmts = con.extract_statements(text)
        for st in stmts:
            try:
                con.execute(st)
            except Exception as exc:  # noqa: BLE001 - add file context then re-raise
                raise PipelineError(f"SQL error in {f.name}: {exc}\nStatement: {st.query[:400]}") from exc
        log.append({"file": f.name, "statements": len(stmts), "seconds": round(time.time() - t0, 2)})
    return log


def validation_failures(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Every row of every out_val_* table whose status is not PASS, plus every duplicated check_id (an empty list
    means all validations passed and every check is uniquely identified)."""
    bad = []
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'out\\_val\\_%' ESCAPE '\\' ORDER BY 1").fetchall()]
    # Fail closed: an absent or empty validation table is a failure, never a silent pass.
    bad += [("MISSING_VALIDATION_TABLE", t) for t in REQUIRED_VALIDATION_TABLES if t not in tables]
    for t in tables:
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        if n == 0:
            bad.append((t, "EMPTY_VALIDATION_TABLE"))
        # IS DISTINCT FROM is NULL-safe: a NULL status is NOT 'PASS' (the plain <> operator would silently skip it)
        bad += [(t, *r) for r in con.execute(f"SELECT * FROM {t} WHERE status IS DISTINCT FROM 'PASS'").fetchall()]
        cols = [c[0] for c in con.execute(f"DESCRIBE {t}").fetchall()]
        if "check_id" in cols:
            bad += [(t, "NULL_CHECK_ID", n_null) for (n_null,) in [con.execute(f"SELECT count(*) FROM {t} WHERE check_id IS NULL").fetchone()] if n_null]
            bad += [(t, "DUPLICATE_CHECK_ID", cid, n) for cid, n in con.execute(
                f"SELECT check_id, count(*) FROM {t} GROUP BY check_id HAVING count(*) > 1 ORDER BY 1").fetchall()]
    return bad


def store_crosscheck(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """Independent pandas recomputation (src/independent_crosscheck.py) stored as out_val_crosscheck."""
    from independent_crosscheck import run_crosscheck  # local import keeps pandas out of the SQL-only path
    rows = run_crosscheck(csv_path, con)
    con.execute("CREATE OR REPLACE TABLE out_val_crosscheck (check_id VARCHAR, description VARCHAR, pandas_value DOUBLE, "
                "sql_value DOUBLE, difference DOUBLE, tolerance DOUBLE, status VARCHAR)")
    con.executemany("INSERT INTO out_val_crosscheck VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [[r["check_id"], r["description"], r["pandas_value"], r["sql_value"], r["difference"], r["tolerance"], r["status"]] for r in rows])
    return len(rows)


def export_outputs(con: duckdb.DuckDBPyConnection, out_dir: Path, reference_dir: Path | None = None) -> dict:
    """Write every out_* table to out_dir (deterministic order) plus MANIFEST.json. `reference_dir` is the accepted
    output folder: files that exist there but were not regenerated are listed as stale (never deleted)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'out\\_%' ESCAPE '\\' ORDER BY 1").fetchall()]
    manifest = {}
    for t in tables:
        p = out_dir / f"{t[4:]}.csv"
        tmp = p.with_suffix(".csv.partial")
        # ORDER BY ALL makes the export deterministic regardless of execution order
        con.execute(f"COPY (SELECT * FROM {t} ORDER BY ALL) TO '{tmp.as_posix()}' (HEADER, DELIMITER ',')")
        os.replace(tmp, p)
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        manifest[p.name] = {"rows": n, "sha256": sha256_file(p)}
    # stale files from older runs are reported, never silently deleted
    ref = reference_dir if reference_dir is not None else out_dir
    stale = sorted(set(x.name for x in ref.glob("*.csv")) - set(manifest)) if ref.exists() else []
    (out_dir / "MANIFEST.json").write_text(json.dumps({"outputs": manifest, "stale_files_not_regenerated": stale},
                                                      indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _safe_close(con) -> None:
    """Close a connection without ever replacing the exception that is already propagating."""
    try:
        con.close()
    except Exception:  # noqa: BLE001 - cleanup must not mask the root cause
        pass


def finalize(con: duckdb.DuckDBPyConnection, tmp_db: Path, db_path: Path, out_dir: Path) -> dict:
    """Stage -> validate -> promote. Accepted artefacts (database, output CSVs, MANIFEST) change ONLY if every gate passes.

    * outputs are exported to a run-specific staging folder next to out_dir;
    * all out_val_* rows must be PASS and all check identifiers unique;
    * on failure the staging folder is kept as <out_dir>_failed_run and the database as <db>.failed; nothing accepted is touched;
    * on success every staged CSV is moved into out_dir (each move atomic), then MANIFEST.json, then the database.
    """
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}_staging_", dir=out_dir.parent))
    try:
        manifest = export_outputs(con, stage, reference_dir=out_dir)
        bad = validation_failures(con)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise  # the original exception propagates; the connection is closed once, in the finally below
    finally:
        _safe_close(con)
    if bad:
        failed = out_dir.parent / f"{out_dir.name}_failed_run"
        if failed.exists():
            shutil.rmtree(failed)  # only the previous FAILED diagnostics folder is replaced, never accepted outputs
        os.replace(stage, failed)
        failed_db = db_path.with_name(db_path.name + ".failed")
        if tmp_db.exists():
            os.replace(tmp_db, failed_db)
        for b in bad[:20]:
            print("VALIDATION FAIL:", b, file=sys.stderr)
        raise IntegrityError(f"{len(bad)} validation problem(s); accepted database and outputs left untouched. "
                             f"Diagnostics: {failed} and {failed_db}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(stage.glob("*.csv")):
        os.replace(f, out_dir / f.name)
    os.replace(stage / "MANIFEST.json", out_dir / "MANIFEST.json")
    shutil.rmtree(stage, ignore_errors=True)
    os.replace(tmp_db, db_path)
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    args = ap.parse_args(argv)
    t0 = time.time()
    con = None
    try:
        info = verify_input(args.csv, args.expected_sha256,
                            expected_normalised=NORMALISED_SHA256 if args.expected_sha256 == EXPECTED_SHA256 else None)
        print(f"[1/4] input verified ({info['sha_status']}): {args.csv}\n      sha256={info['sha256']}\n      {info['bytes']:,} bytes, {info['n_cols']} columns")
        if info["sha_status"] == "normalised":
            print("      WARNING: the file is NOT byte-identical to the approved CSV. It matches after rounding "
                  f"{' and '.join(FLOAT_VARIANT_COLUMNS)} to {NORMALISED_SIGNIFICANT_DIGITS} significant digits (last-digit floating-point "
                  "variation from the CPU that ran the cleaner). All other cells are identical.", file=sys.stderr)
        args.db.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.db.with_suffix(".duckdb.partial")
        con = build_database(args.csv, tmp)
        print(f"[2/4] database built ({time.time() - t0:.0f}s): stg_close_raw + fact_close loaded")
        log = run_sql_files(con)
        for r in log:
            print(f"      {r['file']}: {r['statements']} statements, {r['seconds']}s")
        print("[3/4] SQL complete")
        n_x = store_crosscheck(con, args.csv)
        print(f"      independent pandas cross-check: {n_x} figures recomputed")
        manifest = finalize(con, tmp, args.db, args.out_dir)
        print(f"[4/4] validated and promoted {len(manifest)} output tables to {args.out_dir}")
        print(f"database: {args.db}\nFINISHED in {time.time() - t0:.0f}s")
        return 0
    except IntegrityError as exc:
        print(f"INTEGRITY ERROR: {exc}", file=sys.stderr)
        return 2
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if con is not None:
            _safe_close(con)  # idempotent; never replaces an exception already in flight


if __name__ == "__main__":
    sys.exit(main())
