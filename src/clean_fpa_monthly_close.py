#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_fpa_monthly_close.py
==========================

Standalone, evidence-based cleaning, validation and audit pipeline for the
NovaBridge Industries monthly-close extract ``fpa_monthly_close_raw_messy.csv``
(152,682 rows x 43 text columns).

WHAT THIS SCRIPT DOES
---------------------
1.  Integrity gate: recomputes SHA-256, byte size, row and column counts of the
    raw file. If the hash differs from the expected value the script STOPS and
    explains the difference. It never substitutes another dataset.
2.  Profiles every column of the raw file (blanks, placeholders, hidden
    characters, whitespace, distinct values).
3.  Cleans the data into a NEW set of files. The raw file is opened read-only
    and is never modified. No row is ever deleted: every one of the 152,682
    raw rows appears in the cleaned output with flags and one primary
    exclusion reason (or "ELIGIBLE") per reporting scope.
4.  Writes an Excel workbook, a cleaned CSV, a cell-level audit CSV and a text
    QC report, then READS THEM BACK and validates them.

RULES THAT ARE NOT SETTLED ARE NOT HIDDEN
-----------------------------------------
Scale restoration, duplicate handling, journal-status eligibility and FX
direction are proposals (see docs/FINANCIAL_METRICS.md). The script applies
only what the data evidence supports, keeps the as-reported value next to every
adjusted value, labels each decision with its evidence and confidence, and
leaves "undetermined" rows undetermined rather than guessing.

HOW TO RUN (Windows / VS Code)
------------------------------
    pip install pandas numpy xlsxwriter openpyxl
    python clean_fpa_monthly_close.py
        [--input PATH_TO_CSV] [--output-dir PATH] [--no-excel-readback]

By default the script looks for the CSV next to itself, in ../data/raw, in the
current folder, in ./data/raw and in your Downloads folder, and writes the
results to  <Downloads>/fpa_monthly_close_cleaned/.

Requires Python 3.9+, pandas 2.x or 3.x, numpy, xlsxwriter, openpyxl.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
import traceback
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# =============================================================================
# 1. CONFIGURATION  (edit here; nothing below needs changing for a normal run)
# =============================================================================
SCRIPT_VERSION = "1.0.0"

INPUT_FILE_NAME = "fpa_monthly_close_raw_messy.csv"
OUTPUT_FOLDER_NAME = "fpa_monthly_close_cleaned"
OUTPUT_BASENAME = "fpa_monthly_close_cleaned"

# Integrity gate (values supplied by the project owner and independently
# recomputed during the investigation).
EXPECTED_SHA256 = "a0e6eddde25280aa27a60c5955743d3243b14138d876eedac0547e24a1cc6fff"
EXPECTED_ROWS = 152_682
EXPECTED_COLUMNS = 43
EXPECTED_BYTES = 51_938_535

# --- Rule switches -----------------------------------------------------------
# Restore values that the evidence shows were divided (Thousands / Lakhs).
# The as-reported value is ALWAYS kept in the *_parsed columns.
APPLY_SCALE_RESTORATION = True
# Duplicate rule is UNRESOLVED in docs/FINANCIAL_METRICS.md (R11). Default: flag
# only. If True, non-survivor same-sign field-match candidates (tier DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN, signs equal) get exclusion reason 9;
# abs-match sign-conflict copies are never removed automatically.
REMOVE_FIELD_MATCH_DUPLICATES = False
# Journal statuses that may enter reported totals (docs section 5, PROPOSED).
ELIGIBLE_APPROVAL_STATUSES = ("Posted",)

# --- Scale-decision calibration (derived from the data, see Scale_Evidence) ---
# Price identity: for GL 4100/5100 rows, |actual_usd| = |qty| x list price.
# IMPORTANT: these list prices are NOT from an independent price list. They were inferred from the
# dataset's own modal unit values (undivided rows), so the test is an INFERRED CONSISTENCY test, not
# proof against an external truth source. Replace with an authoritative price list if one exists.
LIST_PRICE_BY_FAMILY = {
    "Diagnostics": 640.0,
    "Home Comfort": 180.0,
    "Motors": 260.0,
    "Pumps & Valves": 420.0,
    "Spare Kits": 45.0,
}
PRICE_IDENTITY_GLS = ("4100", "5100")
IDENTITY_TOL_LOG10 = 0.15          # |log10(actual / (qty*price)) - log10(1/divisor)|
IDENTITY_MAX_REL_ROUNDING = 0.10   # skip identity test if rounding could move value >10%
# Peer z-score bands (log10 magnitude vs gl x entity baseline, robust sd).
Z_DIVIDED_MAX = -5.0      # z <= this  -> divided (valley between clusters is -4.5..-3.0)
Z_UNDIVIDED_MIN = -3.0    # z >= this  -> undivided
Z_SD_FLOOR = 0.25
BASELINE_MIN_GROUP = 30
LABEL_DIVISOR = {"Thousands": 1_000.0, "Lakhs": 100_000.0}

# Magnitude outlier flag (flag only, never changes a value)
OUTLIER_Z = 6.0

# Excel output
EXCEL_MAX_ROWS_EXCEPTIONS = 5_000
VERIFY_EXCEL_FULL = True   # full read-back of the big sheet (slow but thorough)

# -----------------------------------------------------------------------------
EXPECTED_HEADER = [
    "row_id", "source_system", "extract_batch", "fiscal_year", "fiscal_period",
    "legal_entity", "entity_code", "division", "country", "region",
    "cost_center_code", "cost_center_name", "cost_center_owner", "gl_account",
    "account_name", "account_group", "fs_line", "statement", "cost_nature",
    "product_family", "customer_segment", "channel", "currency",
    "amount_local_raw", "fx_rate_raw", "actual_usd_raw", "budget_usd_raw",
    "forecast_usd_raw", "prior_year_usd_raw", "qty_raw", "uom",
    "headcount_fte_raw", "document_no", "posting_date", "user_id", "line_text",
    "intercompany", "accrual", "elimination_status", "report_scale",
    "scenario_tag", "approval_status", "notes",
]
AMOUNT_RAW_COLS = ["amount_local_raw", "actual_usd_raw", "budget_usd_raw",
                   "forecast_usd_raw", "prior_year_usd_raw"]
AMOUNT_CLEAN_NAMES = {   # raw column -> short name used in cleaned columns
    "amount_local_raw": "amount_local",
    "actual_usd_raw": "actual_usd",
    "budget_usd_raw": "budget_usd",
    "forecast_usd_raw": "forecast_usd",
    "prior_year_usd_raw": "prior_year_usd",
}
USD_SHORT = ["actual_usd", "budget_usd", "forecast_usd", "prior_year_usd"]
ALL_AMT_SHORT = ["amount_local"] + USD_SHORT

ENTITY_MASTER = {  # code -> (legal entity, country, currency)
    "GB01": ("NovaBridge UK Ltd", "United Kingdom", "GBP"),
    "SG01": ("NovaBridge APAC Pte Ltd", "Singapore", "SGD"),
    "DE01": ("NovaBridge Europe GmbH", "Germany", "EUR"),
    "IN01": ("NovaBridge India Pvt Ltd", "India", "INR"),
    "AE01": ("NovaBridge MENA FZE", "UAE", "AED"),
    "US01": ("NovaBridge Americas Inc", "United States", "USD"),
}
JUNK_NAME_KEYS = {"do not use", "xxx", "test entity"}
JUNK_CODES = {"99", "T999"}
DIVISION_MAP = {  # lower-cased, whitespace-collapsed raw value -> canonical
    "industrial components": "Industrial Components",
    "industrial comp.": "Industrial Components",
    "ind. components": "Industrial Components",
    "medical devices": "Medical Devices",
    "med devices": "Medical Devices",
    "consumer durables": "Consumer Durables",
    "consumer durable": "Consumer Durables",
    "cons. durables": "Consumer Durables",
    "packaging": "Packaging",
    "pkg": "Packaging",
    "services & spares": "Services & Spares",
    "services and spares": "Services & Spares",
    "svc & spares": "Services & Spares",
}
STATEMENT_MAP = {
    "p&l": "P&L", "pl": "P&L", "is": "P&L", "income statement": "P&L",
    "profit & loss": "P&L",
    "balance sheet": "Balance Sheet", "bs": "Balance Sheet", "b/s": "Balance Sheet",
    "statement of position": "Balance Sheet",
}
COST_NATURE_MAP = {"variable": "Variable", "var": "Variable", "v": "Variable",
                   "fixed": "Fixed", "f": "Fixed", "mixed": "Mixed",
                   "financial": "Financial", "balance sheet": "Balance sheet"}
CHANNEL_MAP = {"direct": "Direct", "dir": "Direct", "distributor": "Distributor",
               "dist": "Distributor"}
UOM_MAP = {"ea": "EA", "each": "EA", "kg": "KG", "nos": "NOS"}
YES_TOKENS = {"y", "yes", "1", "true", "ic", "accrual"}
NO_TOKENS = {"n", "no", "0", "false"}
APPROVAL_MAP = {"posted": "Posted", "pending": "Pending", "rejected": "Rejected",
                "parked": "Parked"}
ELIM_MAP = {"eliminated": "Eliminated", "not eliminated": "Not eliminated",
            "pending": "Pending", "n/a": "Not applicable"}
PLACEHOLDER_UPPER = {"###", "#N/A", "#NA", "NA", "N/A", "NULL", "NONE", "NAN"}
NONPOSTING_LABEL_RE = r"^(grand total|total|total for entity|subtotal|sub-total|check)$"

EXCL_ELIGIBLE = "ELIGIBLE"
EXCL_REASONS = [
    "1_NON_POSTING_ROW", "2_JUNK_ENTITY", "3_ENTITY_UNRESOLVABLE",
    "4_OUT_OF_SCOPE_STATEMENT", "5_STATUS_NOT_ELIGIBLE", "6_PERIOD_UNRESOLVABLE",
    "7_AMOUNT_MISSING", "8_SCALE_UNDECIDABLE", "9_REMOVED_AS_DUPLICATE",
]

log = logging.getLogger("fpa_clean")


# =============================================================================
# 2. SMALL UTILITIES
# =============================================================================
class PipelineError(Exception):
    """Raised for conditions the script cannot or should not continue past."""


class IntegrityError(PipelineError):
    """Raw file differs from the expected dataset."""


def setup_logging(log_path: Optional[Path] = None) -> None:
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
    root = logging.getLogger("fpa_clean")
    root.setLevel(logging.INFO)
    root.handlers.clear()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    if log_path is not None:
        fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)


def attach_file_log(log_path: Path) -> None:
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    logging.getLogger("fpa_clean").addHandler(fh)


class StepTimer:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        self.t0 = time.time()
        log.info("START  %s", self.name)
        return self

    def __exit__(self, exc_type, exc, tb):
        log.info("DONE   %s (%.1fs)", self.name, time.time() - self.t0)
        return False


def sha256_file(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def ascii_safe(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def collapse_ws(s: pd.Series) -> pd.Series:
    """Trim, remove zero-width characters, collapse internal whitespace."""
    out = s.astype(object).str.replace(r"[\u200b\u200c\u200d\ufeff]", "", regex=True)
    out = out.str.replace(r"\s+", " ", regex=True).str.strip()
    return out


def norm_key(s: pd.Series) -> pd.Series:
    return collapse_ws(s).str.lower()


def name_key(s: pd.Series) -> pd.Series:
    """Account-name key: fix digit-3-for-e typos, & -> and, lower-case."""
    t = collapse_ws(s)
    t = t.str.replace(r"(?<=[A-Za-z])3|3(?=[A-Za-z])", "e", regex=True)
    t = t.str.replace(" & ", " and ", regex=False)
    return t.str.lower()


def fix_name_typos(s: pd.Series) -> pd.Series:
    t = collapse_ws(s)
    return t.str.replace(r"(?<=[A-Za-z])3|3(?=[A-Za-z])", "e", regex=True)


def entity_name_key(s: pd.Series) -> pd.Series:
    t = collapse_ws(s).str.lower()
    t = t.str.replace(r"[.,]", "", regex=True)
    return t.str.replace(r"\s+", " ", regex=True).str.strip()


def modal_value(values: pd.Series) -> str:
    vc = values[values != ""].value_counts()
    if vc.empty:
        return ""
    top = vc[vc == vc.iloc[0]].index.tolist()
    return sorted(top)[0]          # deterministic tie-break


def pct(a: float, b: float) -> float:
    return float(a) / float(b) * 100.0 if b else float("nan")


# =============================================================================
# 3. FILE DISCOVERY, INTEGRITY GATE, LOADING
# =============================================================================
def candidate_input_paths(cli_input: Optional[str]) -> List[Path]:
    if cli_input:
        return [Path(cli_input).expanduser()]
    here = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    cands = [
        here / INPUT_FILE_NAME,
        here.parent / "data" / "raw" / INPUT_FILE_NAME,
        Path.cwd() / INPUT_FILE_NAME,
        Path.cwd() / "data" / "raw" / INPUT_FILE_NAME,
        Path.home() / "Downloads" / INPUT_FILE_NAME,
    ]
    seen, out = set(), []
    for c in cands:
        if str(c) not in seen:
            seen.add(str(c))
            out.append(c)
    return out


def find_input_file(cli_input: Optional[str]) -> Path:
    cands = candidate_input_paths(cli_input)
    for c in cands:
        if c.is_file():
            return c.resolve()
    raise PipelineError(
        "Input file not found. Looked in:\n  " + "\n  ".join(str(c) for c in cands)
        + "\nUse --input PATH_TO_CSV to point at the file."
    )


def integrity_gate(path: Path, enforce: bool = True) -> Dict[str, object]:
    """Recompute hash and size. STOP (raise) if they differ from the expected."""
    size = path.stat().st_size
    digest = sha256_file(path)
    info = {"path": str(path), "bytes": size, "sha256": digest,
            "expected_sha256": EXPECTED_SHA256, "expected_bytes": EXPECTED_BYTES,
            "hash_match": digest == EXPECTED_SHA256,
            "size_match": size == EXPECTED_BYTES}
    log.info("Raw file: %s", path)
    log.info("  bytes  = %s (expected %s)", f"{size:,}", f"{EXPECTED_BYTES:,}")
    log.info("  sha256 = %s", digest)
    log.info("  hash match = %s", info["hash_match"])
    if enforce and not (info["hash_match"] and info["size_match"]):
        raise IntegrityError(
            "STOP - the file is not the dataset this script was built for.\n"
            f"  file      : {path}\n"
            f"  SHA-256   : {digest}\n"
            f"  expected  : {EXPECTED_SHA256}\n"
            f"  size      : {size:,} bytes (expected {EXPECTED_BYTES:,})\n"
            "A different hash means the content differs (edited, re-saved, "
            "re-encoded or a different extract). The cleaning rules, scale "
            "calibration and expected counts were derived from the original "
            "file, so applying them to another file could silently produce wrong "
            "financial figures. Nothing was cleaned and nothing was written.\n"
            "Next step: restore the original file from the repository "
            "(data/raw/) or tell me what changed so the rules can be re-derived."
        )
    return info


def load_raw(path: Path, enforce: bool = True) -> pd.DataFrame:
    """Read every cell as text. Nothing is converted, nothing is dropped."""
    last_err = None
    df = None
    for enc in ("utf-8-sig", "cp1252"):
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[],
                             encoding=enc, engine="c", low_memory=False)
            if enc != "utf-8-sig":
                log.warning("File is not valid UTF-8; decoded as %s", enc)
            break
        except UnicodeDecodeError as exc:
            last_err = exc
        except pd.errors.EmptyDataError as exc:
            raise PipelineError("The input file is empty (no header, no data). Nothing was cleaned and nothing was written.") from exc
        except pd.errors.ParserError as exc:
            raise PipelineError(f"Malformed CSV (parser error): {exc}") from exc
        except PermissionError as exc:
            raise PipelineError(f"No permission to read {path}: {exc}") from exc
    if df is None:
        raise PipelineError(f"Could not decode the file: {last_err}")
    if df.empty:
        raise PipelineError("The file has a header but no data rows.")
    header = list(df.columns)
    if header != EXPECTED_HEADER:
        missing = [c for c in EXPECTED_HEADER if c not in header]
        extra = [c for c in header if c not in EXPECTED_HEADER]
        raise PipelineError(
            "Header differs from the expected 43-column schema.\n"
            f"  missing: {missing}\n  extra: {extra}\n  order_ok: {set(header)==set(EXPECTED_HEADER)}"
        )
    n_nan = int(df.isna().sum().sum())
    if n_nan:
        log.warning("%d cells were missing (short rows); converted to empty text", n_nan)
        df = df.fillna("")
    df = df.astype(object)
    if enforce and (len(df) != EXPECTED_ROWS or df.shape[1] != EXPECTED_COLUMNS):
        raise IntegrityError(
            f"Row/column count differs although the hash matched: "
            f"{len(df):,} x {df.shape[1]} vs expected {EXPECTED_ROWS:,} x {EXPECTED_COLUMNS}. "
            "The CSV parser read the file differently from the reference; stopping."
        )
    log.info("Loaded %s rows x %d columns (all text)", f"{len(df):,}", df.shape[1])
    return df


# =============================================================================
# 4. RAW PROFILE (before any change)
# =============================================================================
def profile_columns(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    n = len(raw)
    for c in raw.columns:
        s = raw[c]
        t = s.str.strip()
        blank = t.eq("")
        ph = t.str.upper().isin(PLACEHOLDER_UPPER) | t.str.fullmatch(r"-+").fillna(False)
        rows.append({
            "column": c,
            "rows": n,
            "blank_count": int(blank.sum()),
            "blank_pct": round(pct(blank.sum(), n), 3),
            "placeholder_count": int((ph & ~blank).sum()),
            "placeholder_pct": round(pct((ph & ~blank).sum(), n), 3),
            "distinct_raw": int(s.nunique()),
            "distinct_after_trim_case": int(t.str.lower().nunique()),
            "leading_trailing_space_cells": int((s != t).sum()),
            "inner_multi_space_cells": int(t.str.contains(r"\s{2,}", regex=True).sum()),
            "tab_cr_lf_cells": int(s.str.contains(r"[\t\r\n]", regex=True).sum()),
            "non_ascii_cells": int(s.str.contains(r"[^\x00-\x7F]", regex=True).sum()),
            "other_control_char_cells": int(s.str.contains(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", regex=True).sum()),
            "max_length": int(s.str.len().max()),
            "sample_values": " | ".join(t[~blank].value_counts().head(4).index.tolist())[:120],
        })
    return pd.DataFrame(rows)


# =============================================================================
# 5. PARSERS  (amounts, plain numerics, fiscal period, posting date)
# =============================================================================
_AMOUNT_BODY_FORMATS = [
    ("plain", re.compile(r"\d+(\.\d{1,4})?")),
    ("us", re.compile(r"\d{1,3}(,\d{3})+\.\d{1,4}")),
    ("thou_int", re.compile(r"\d{1,3}(,\d{3})+")),
    ("eu", re.compile(r"\d{1,3}(\.\d{3})+,\d{1,4}")),
    ("dec_comma", re.compile(r"\d+,\d{1,2}")),
]


def _placeholder_mask(t: pd.Series) -> pd.Series:
    up = t.str.upper()
    return (up.isin(PLACEHOLDER_UPPER) | t.str.fullmatch(r"-+").fillna(False).astype(bool)) & t.ne("")


def parse_amount_series(raw: pd.Series) -> pd.DataFrame:
    """Strict text -> number parser for money columns.

    Grammar (validated on all five amount columns of the raw file):
      * optional surrounding parentheses  => negative
      * optional leading '-' and/or '$'   (spaces tolerated)
      * body is exactly one of
          plain      1234.56
          us         1,234.56
          thou_int   1,234          (integer-rounded; thousands separator)
          eu         1.234,56
          dec_comma  12,5           (1-2 decimals)
    Anything else is returned as status 'unparsed' (never guessed).
    Placeholders (###, #N/A, NA, N/A, n/a, null, '-') and blanks give NaN with
    status 'placeholder' / 'blank'. A placeholder is NOT zero.
    """
    t = collapse_ws(raw)
    blank = t.eq("")
    ph = _placeholder_mask(t)
    paren = (t.str.startswith("(") & t.str.endswith(")") & (t.str.len() >= 3))
    core = t.where(~paren, t.str[1:-1])
    m = core.str.extract(r"^([-+]?)\s*\$?\s*([-+]?)\s*(.*)$")
    sign1, sign2, body = m[0].fillna(""), m[1].fillna(""), m[2].fillna("").str.strip()
    nneg = paren.astype(int) + sign1.eq("-").astype(int) + sign2.eq("-").astype(int)
    fmt = pd.Series("", index=raw.index, dtype=object)
    for name, rx in _AMOUNT_BODY_FORMATS:
        hit = body.str.fullmatch(rx).fillna(False).astype(bool) & fmt.eq("")
        fmt = fmt.where(~hit, name)
    fmt = fmt.where(~(blank | ph | (nneg > 1)), "")
    num = body.copy()
    num = num.where(~fmt.isin(["us", "thou_int"]), num.str.replace(",", "", regex=False))
    num = num.where(fmt != "eu", num.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    num = num.where(fmt != "dec_comma", num.str.replace(",", ".", regex=False))
    ok = fmt.ne("")
    value = pd.to_numeric(num.where(ok), errors="coerce")
    value = value.where(~(ok & (nneg == 1)), -value)
    # decimals present in the source text -> rounding uncertainty (+/- 0.5 ulp)
    n_dec = pd.Series(np.nan, index=raw.index)
    pt = fmt.isin(["plain", "us"])
    n_dec = n_dec.where(~pt, body.str.split(".").str[-1].str.len().where(body.str.contains(".", regex=False), 0))
    cm = fmt.isin(["eu", "dec_comma"])
    n_dec = n_dec.where(~cm, body.str.split(",").str[-1].str.len())
    n_dec = n_dec.where(fmt != "thou_int", 0)
    abs_err = 0.5 * np.power(10.0, -n_dec.astype(float))
    status = np.where(blank, "blank", np.where(ph, "placeholder", np.where(ok, "ok", "unparsed")))
    return pd.DataFrame({
        "value": value.astype(float), "fmt": fmt, "status": pd.Series(status, index=raw.index),
        "abs_err": abs_err.astype(float), "neg_marker": nneg.ge(1),
    })


def parse_plain_numeric(raw: pd.Series, allow_negative: bool = True) -> pd.DataFrame:
    """For fx rate, qty, headcount: plain numbers only (any number of decimals)."""
    t = collapse_ws(raw)
    blank = t.eq("")
    ph = _placeholder_mask(t)
    rx = r"-?\d+(\.\d+)?" if allow_negative else r"\d+(\.\d+)?"
    ok = t.str.fullmatch(rx).fillna(False).astype(bool) & ~blank & ~ph
    value = pd.to_numeric(t.where(ok), errors="coerce").astype(float)
    status = np.where(blank, "blank", np.where(ph, "placeholder", np.where(ok, "ok", "unparsed")))
    return pd.DataFrame({"value": value, "status": pd.Series(status, index=raw.index)})


def oracle_parse_amount(s: str) -> Optional[float]:
    """Independent scalar re-implementation used ONLY for validation.

    Different logic from parse_amount_series: it decides the decimal separator
    from which separator comes last, using Decimal arithmetic.
    Returns None for placeholders/blank/unparsable.
    """
    t = re.sub(r"\s+", " ", s).strip()
    if t == "" or t.upper() in PLACEHOLDER_UPPER or re.fullmatch(r"-+", t):
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1].strip()
    if t.startswith("-"):
        neg, t = True, t[1:].strip()
    t = t.replace("$", "").strip()
    if t.startswith("-"):
        neg, t = True, t[1:].strip()
    if not t or not re.fullmatch(r"[\d.,]+", t):
        return None
    has_c, has_d = "," in t, "." in t
    if has_c and has_d:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif has_c:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", t):
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    try:
        v = float(Decimal(t))
    except (InvalidOperation, ValueError):
        return None
    return -v if neg else v


_MON = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONF = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}


def parse_period_value(s: str) -> Tuple[Optional[int], Optional[int], str]:
    """fiscal_period text -> (year, month, format). Locale independent."""
    t = s.strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})", t)
    if m:
        return int(m[1]), int(m[2]), "yyyy-mm"
    m = re.fullmatch(r"([A-Za-z]{3})-(\d{2})", t)
    if m and m[1].lower() in _MON:
        return 2000 + int(m[2]), _MON[m[1].lower()], "Mmm-yy"
    m = re.fullmatch(r"(\d{2})/(\d{4})", t)
    if m:
        return int(m[2]), int(m[1]), "mm/yyyy"
    m = re.fullmatch(r"(\d{4})(\d{2})", t)
    if m:
        return int(m[1]), int(m[2]), "yyyymm"
    m = re.fullmatch(r"FY(\d{2}) P(\d{2})", t)
    if m:
        return 2000 + int(m[1]), int(m[2]), "FYyy Pnn"
    m = re.fullmatch(r"(\d{2})-([A-Za-z]{3})-(\d{4})", t)
    if m and m[2].lower() in _MON:
        return int(m[3]), _MON[m[2].lower()], "dd-Mmm-yyyy"
    m = re.fullmatch(r"(\d{1,2})/(\d{2})", t)
    if m:
        return 2000 + int(m[2]), int(m[1]), "m/yy"
    m = re.fullmatch(r"([A-Za-z]+) (\d{4})", t)
    if m and m[1].lower() in _MONF:
        return int(m[2]), _MONF[m[1].lower()], "Month yyyy"
    return None, None, "unparsed"


def parse_periods(fiscal_period: pd.Series) -> pd.DataFrame:
    uniq = fiscal_period.drop_duplicates()
    table = {v: parse_period_value(v) for v in uniq}
    y = fiscal_period.map(lambda v: table[v][0]).astype(float)
    m = fiscal_period.map(lambda v: table[v][1]).astype(float)
    f = fiscal_period.map(lambda v: table[v][2])
    bad = (m < 1) | (m > 12)
    y = y.where(~bad, np.nan)
    m = m.where(~bad, np.nan)
    f = f.where(~bad, "unparsed")
    return pd.DataFrame({"period_year": y, "period_month": m, "period_format": f})


_DIM = np.array([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def ymd_to_datetime(y, m, d) -> pd.Series:
    """Vectorised, locale-independent date builder. Invalid dates -> NaT."""
    y = np.asarray(y, dtype=float)
    m = np.asarray(m, dtype=float)
    d = np.asarray(d, dtype=float)
    ok = np.isfinite(y) & np.isfinite(m) & np.isfinite(d) & (m >= 1) & (m <= 12) & (d >= 1) & (y >= 1900) & (y <= 2200)
    mi = np.where(ok, m, 1).astype(int)
    yi = np.where(ok, y, 2000).astype(int)
    leap = ((yi % 4 == 0) & (yi % 100 != 0)) | (yi % 400 == 0)
    dim = _DIM[mi] + ((mi == 2) & leap)
    ok = ok & (d <= dim)
    frame = pd.DataFrame({"year": np.where(ok, yi, 2000), "month": np.where(ok, mi, 1),
                          "day": np.where(ok, d, 1).astype(int)})
    out = pd.to_datetime(frame, errors="coerce")
    return out.where(pd.Series(ok, index=out.index))


def resolve_posting_dates(raw_pd: pd.Series, py: pd.Series, pm: pd.Series) -> pd.DataFrame:
    """Parse posting_date. Slash dates are day-first OR month-first in this file;
    the reading is decided by the fiscal period (the posting date lies in the
    period's month for 100% of the unambiguous rows). Never guessed otherwise."""
    t = collapse_ws(raw_pd)
    idx = t.index
    blank = t.eq("")
    iso = t.str.fullmatch(r"\d{4}-\d{2}-\d{2}").fillna(False).astype(bool)
    compact = t.str.fullmatch(r"\d{8}").fillna(False).astype(bool)
    txt = t.str.fullmatch(r"\d{2}-[A-Za-z]{3}-\d{4}").fillna(False).astype(bool)
    slash = t.str.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}").fillna(False).astype(bool)

    date = pd.Series(pd.NaT, index=idx, dtype="datetime64[ns]")
    fmt = pd.Series("unrecognised", index=idx, dtype=object)
    res = pd.Series("", index=idx, dtype=object)
    fmt[blank] = "blank"
    res[blank] = "blank"

    def part(series, mask, pattern, i):
        return pd.to_numeric(series.where(mask).str.extract(pattern)[i], errors="coerce").to_numpy()

    if iso.any():
        d = ymd_to_datetime(part(t, iso, r"^(\d{4})-(\d{2})-(\d{2})$", 0),
                            part(t, iso, r"^(\d{4})-(\d{2})-(\d{2})$", 1),
                            part(t, iso, r"^(\d{4})-(\d{2})-(\d{2})$", 2))
        date = date.where(~iso, d)
        fmt[iso] = "yyyy-mm-dd"
        res[iso] = np.where(d[iso].notna(), "iso", "invalid_calendar_date")
    if compact.any():
        pat = r"^(\d{4})(\d{2})(\d{2})$"
        d = ymd_to_datetime(part(t, compact, pat, 0), part(t, compact, pat, 1), part(t, compact, pat, 2))
        date = date.where(~compact, d)
        fmt[compact] = "yyyymmdd"
        res[compact] = np.where(d[compact].notna(), "yyyymmdd", "invalid_calendar_date")
    if txt.any():
        pat = r"^(\d{2})-([A-Za-z]{3})-(\d{4})$"
        ex = t.where(txt).str.extract(pat)
        mon = ex[1].str.lower().map(_MON)
        d = ymd_to_datetime(pd.to_numeric(ex[2], errors="coerce").to_numpy(),
                            pd.to_numeric(mon, errors="coerce").to_numpy(),
                            pd.to_numeric(ex[0], errors="coerce").to_numpy())
        date = date.where(~txt, d)
        fmt[txt] = "dd-Mmm-yyyy"
        res[txt] = np.where(d[txt].notna(), "dd-Mmm-yyyy", "invalid_calendar_date")
    if slash.any():
        pat = r"^(\d{1,2})/(\d{1,2})/(\d{4})$"
        ex = t.where(slash).str.extract(pat)
        a = pd.to_numeric(ex[0], errors="coerce").to_numpy()
        b = pd.to_numeric(ex[1], errors="coerce").to_numpy()
        y = pd.to_numeric(ex[2], errors="coerce").to_numpy()
        d_dayfirst = ymd_to_datetime(y, b, a)      # a = day, b = month
        d_monthfirst = ymd_to_datetime(y, a, b)    # a = month, b = day
        pyv, pmv = py.to_numpy(dtype=float), pm.to_numpy(dtype=float)
        have_period = np.isfinite(pyv) & np.isfinite(pmv)
        v1, v2 = d_dayfirst.notna().to_numpy(), d_monthfirst.notna().to_numpy()
        m1 = v1 & have_period & (d_dayfirst.dt.year.to_numpy() == pyv) & (d_dayfirst.dt.month.to_numpy() == pmv)
        m2 = v2 & have_period & (d_monthfirst.dt.year.to_numpy() == pyv) & (d_monthfirst.dt.month.to_numpy() == pmv)
        sl = slash.to_numpy()
        both = sl & m1 & m2
        only1 = sl & m1 & ~m2
        only2 = sl & m2 & ~m1
        # no period to lean on: accept only if exactly one reading is a valid date
        np_only1 = sl & ~have_period & v1 & ~v2
        np_only2 = sl & ~have_period & v2 & ~v1
        use1 = pd.Series(both | only1 | np_only1, index=idx)
        use2 = pd.Series(only2 | np_only2, index=idx)
        chosen = pd.Series(pd.NaT, index=idx, dtype="datetime64[ns]")
        chosen = chosen.where(~use1, d_dayfirst)        # take day-first where use1
        chosen = chosen.where(~use2, d_monthfirst)      # take month-first where use2
        date = date.where(~slash, chosen)
        fmt[slash] = "dd/mm/yyyy or mm/dd/yyyy"
        r = np.full(len(idx), "", dtype=object)
        r[sl] = "slash_unresolved_conflict_with_period"
        r[sl & ~have_period] = "slash_unresolved_no_period"
        r[sl & ~(v1 | v2)] = "invalid_calendar_date"
        r[both] = "slash_same_date_either_reading"
        r[only1] = "slash_day_first"
        r[only2] = "slash_month_first"
        r[np_only1] = "slash_day_first_by_value_only"
        r[np_only2] = "slash_month_first_by_value_only"
        res = res.where(~slash, pd.Series(r, index=idx))
    res[(res == "") & ~blank] = "unrecognised_format"
    pyv, pmv = py.to_numpy(dtype=float), pm.to_numpy(dtype=float)
    mism = (date.notna().to_numpy() & np.isfinite(pyv) & np.isfinite(pmv)
            & ((date.dt.year.to_numpy() != pyv) | (date.dt.month.to_numpy() != pmv)))
    return pd.DataFrame({"posting_date": date, "posting_date_format": fmt,
                         "posting_date_resolution": res,
                         "posting_date_period_mismatch": mism})


# =============================================================================
# 6. CLEANING CONTEXT
# =============================================================================
class Ctx:
    """Holds the raw frame, the whitespace-normalised copy S, the cleaned output
    frame D and every audit artefact produced along the way."""

    def __init__(self, raw: pd.DataFrame):
        self.raw = raw
        self.n = len(raw)
        self.S: pd.DataFrame = pd.DataFrame(index=raw.index)
        self.D: pd.DataFrame = pd.DataFrame(index=raw.index)
        self.tlog: List[dict] = []          # transformation log
        self.maps: List[pd.DataFrame] = []  # mapping tables
        self.audit: List[pd.DataFrame] = [] # cell-level material changes
        self.ev: Dict[str, pd.DataFrame] = {}  # evidence tables
        self.facts: Dict[str, object] = {}  # scalar facts for reports/validation
        self.P: Dict[str, pd.DataFrame] = {}   # parsed amount frames
        self.arr: Dict[str, np.ndarray] = {}   # working arrays

    def log_rule(self, rule_id, columns, rows, description, classification, status,
                 cells_processed=None, cells_changed=None):
        """Log one rule. 'rows' MUST be the number of DISTINCT rows affected (never a cell total).
        cells_processed / cells_changed are given only where they were measured; otherwise they stay
        blank (not stated) instead of being guessed."""
        rows = int(rows)
        if rows > self.n:
            raise PipelineError(f"internal error: rule {rule_id} reports {rows} affected rows > {self.n} rows (cells counted as rows?)")
        self.tlog.append({"rule_id": rule_id, "columns": columns,
                          "cells_processed": ("" if cells_processed is None else int(cells_processed)),
                          "cells_changed": ("" if cells_changed is None else int(cells_changed)),
                          "distinct_rows_affected": rows,
                          "pct_rows_affected": round(100.0 * rows / max(1, self.n), 3),
                          "description": description, "classification": classification,
                          "status": status})
        log.info("  [%s] %s -> %s rows", rule_id, description[:90], f"{rows:,}")

    def add_map(self, column: str, raw_vals: pd.Series, clean_vals: pd.Series, basis: str, status: str):
        f = pd.DataFrame({"raw_value": raw_vals.astype(str), "clean_value": clean_vals.astype(str)})
        g = f.groupby(["raw_value", "clean_value"], sort=True).size().reset_index(name="rows")
        g.insert(0, "column", column)
        g["basis"] = basis
        g["status"] = status
        g["changed"] = np.where(g["raw_value"] != g["clean_value"], "yes", "no")
        self.maps.append(g)

    def add_audit(self, rule_id: str, column: str, mask, raw_vals, clean_vals, basis: str):
        mask = np.asarray(mask, dtype=bool)
        if not mask.any():
            return
        a = pd.DataFrame({
            "row_id": self.raw["row_id"].to_numpy()[mask],
            "source_row_number": np.flatnonzero(mask) + 2,
            "column": column,
            "raw_value": pd.Series(raw_vals).to_numpy()[mask] if not isinstance(raw_vals, pd.Series) else raw_vals.to_numpy()[mask],
            "cleaned_value": pd.Series(clean_vals).to_numpy()[mask] if not isinstance(clean_vals, pd.Series) else clean_vals.to_numpy()[mask],
            "rule_id": rule_id,
            "basis": basis,
        })
        self.audit.append(a)


def _as_bool(x) -> np.ndarray:
    return np.asarray(x, dtype=bool)


def _canon_case_map(values: pd.Series) -> Dict[str, str]:
    """lower-key -> most frequent original spelling (deterministic tie-break)."""
    out = {}
    v = values[values != ""]
    for key, grp in v.groupby(v.str.lower()):
        out[key] = modal_value(grp)
    return out


# =============================================================================
# 7. CLEANING STEPS
# =============================================================================
def step_text(ctx: Ctx) -> None:
    raw = ctx.raw
    S = pd.DataFrame({c: collapse_ws(raw[c]) for c in raw.columns})
    ctx.S = S
    chg_mat = np.column_stack([(S[c] != raw[c]).to_numpy() for c in raw.columns])
    changed = {c: int(chg_mat[:, i].sum()) for i, c in enumerate(raw.columns)}
    tot = sum(changed.values())
    rows_changed = int(chg_mat.any(axis=1).sum())
    ctx.facts["whitespace_changed_by_col"] = changed
    ctx.facts["whitespace_cells_changed"] = int(tot)
    ctx.facts["whitespace_rows_changed"] = rows_changed
    ctx.log_rule("T01", "all 43 columns", rows_changed,
                 "Trim leading/trailing whitespace, collapse repeated internal whitespace, "
                 "remove zero-width characters (values otherwise unchanged). "
                 "Counts: %s cells changed, in %s distinct rows" % (f"{tot:,}", f"{rows_changed:,}"),
                 "Cosmetic - reversible", "Applied",
                 cells_processed=ctx.n * raw.shape[1], cells_changed=tot)
    D = ctx.D
    D["source_row_number"] = np.arange(ctx.n, dtype=np.int64) + 2   # CSV line (header = line 1)
    D["row_id"] = S["row_id"]
    D["document_no"] = S["document_no"]
    D["source_system"] = S["source_system"]
    D["user_id"] = S["user_id"]
    D["line_text"] = S["line_text"]
    D["notes"] = S["notes"]
    uid = ctx.raw["row_id"]
    ctx.facts["row_id_unique"] = bool(uid.is_unique)
    ctx.add_map("source_system", raw["source_system"], S["source_system"],
                "whitespace trim only (values otherwise unchanged)", "Applied")


def step_nonposting(ctx: Ctx) -> None:
    S = ctx.S
    lowr = lambda c: S[c].str.lower().str.fullmatch(NONPOSTING_LABEL_RE).fillna(False).astype(bool)
    notes_np = S["notes"].str.lower().eq("subtotal row").to_numpy()
    label_np = (lowr("account_name") | lowr("fs_line") | lowr("line_text")).to_numpy()
    ctx.arr["nonposting"] = notes_np
    ctx.arr["nonposting_label_only"] = label_np & ~notes_np
    ctx.arr["nonposting_notes_only"] = notes_np & ~label_np
    ctx.D["is_posting_row"] = (~notes_np).astype(int)
    ctx.facts["nonposting_n"] = int(notes_np.sum())
    ctx.facts["nonposting_label_n"] = int(label_np.sum())
    ctx.facts["nonposting_label_only_n"] = int((label_np & ~notes_np).sum())
    ctx.facts["nonposting_notes_only_n"] = int((notes_np & ~label_np).sum())
    ctx.log_rule("R3", "notes", notes_np.sum(),
                 "Identify NON-POSTING rows (notes = 'subtotal row'): TOTAL / Subtotal / CHECK rows. "
                 "Kept in the data, excluded from every total (exclusion step 1)",
                 "Confirmed (identification per Phase-1 doc R3)", "Applied (flag + exclusion)")


def step_entities(ctx: Ctx) -> None:
    S = ctx.S
    code_up = S["entity_code"].str.upper()
    name_k = entity_name_key(S["legal_entity"])
    name_junk = name_k.isin(JUNK_NAME_KEYS)
    code_junk = code_up.isin(JUNK_CODES)
    valid_code = code_up.isin(list(ENTITY_MASTER.keys()))
    learn = valid_code & ~name_junk & name_k.ne("") & ~code_junk
    ct = pd.crosstab(name_k[learn], code_up[learn])
    name_to_code, conflicts = {}, []
    for k, row in ct.iterrows():
        nz = row[row > 0]
        if len(nz) == 1:
            name_to_code[k] = nz.index[0]
        else:
            conflicts.append({"name_key": k, "codes": ",".join(f"{i}:{v}" for i, v in nz.items())})
    name_code = name_k.map(name_to_code)
    junk = (name_junk | code_junk).to_numpy()
    by_code = (valid_code & ~(name_junk | code_junk)).to_numpy()
    by_name = (~junk & ~by_code & name_code.notna().to_numpy())
    entity = np.where(by_code, code_up.to_numpy(), np.where(by_name, name_code.fillna("").to_numpy(), ""))
    status = np.where(junk, "JUNK", np.where(by_code, "RESOLVED_BY_CODE",
                      np.where(by_name, "RESOLVED_BY_NAME", "UNRESOLVED")))
    basis = np.where(name_junk & code_junk, "junk name + junk code",
              np.where(name_junk, "junk name", np.where(code_junk, "junk code", "")))
    ent_s = pd.Series(entity, index=ctx.D.index, dtype=object)
    legal = ent_s.map({k: v[0] for k, v in ENTITY_MASTER.items()}).fillna("")
    exp_country = ent_s.map({k: v[1] for k, v in ENTITY_MASTER.items()}).fillna("")
    exp_ccy = ent_s.map({k: v[2] for k, v in ENTITY_MASTER.items()}).fillna("")
    name_code_conflict = (by_code & name_code.notna().to_numpy() & (name_code.fillna("").to_numpy() != code_up.to_numpy()))
    name_unmapped = (~junk & name_k.ne("").to_numpy() & name_code.isna().to_numpy() & ~name_k.isin(name_to_code.keys()).to_numpy())
    D = ctx.D
    D["legal_entity_raw"] = ctx.raw["legal_entity"]
    D["entity_code_raw"] = ctx.raw["entity_code"]
    D["entity_code"] = ent_s
    D["legal_entity"] = legal
    D["entity_status"] = status
    D["junk_entity_basis"] = basis
    ctx.arr["entity"] = entity
    ctx.arr["junk_entity"] = junk
    ctx.arr["entity_unresolved"] = (status == "UNRESOLVED")
    ctx.arr["entity_by_name"] = by_name
    ctx.arr["entity_name_code_conflict"] = name_code_conflict
    ctx.arr["exp_country"] = exp_country.to_numpy()
    ctx.arr["exp_currency"] = exp_ccy.to_numpy()
    ctx.facts["entity_name_conflicts"] = conflicts
    ctx.facts["entity_name_to_code"] = name_to_code
    ctx.facts["entity_name_unmapped_n"] = int(name_unmapped.sum())
    ctx.facts["junk_by_name_n"] = int(name_junk.sum())
    ctx.facts["junk_by_code_n"] = int(code_junk.sum())
    ctx.facts["junk_total_n"] = int(junk.sum())
    # cross-tab of junk name vs junk code (evidence for the rule)
    jt = pd.DataFrame({"junk_name": np.where(name_junk, "junk name", np.where(name_k.eq(""), "blank name", "real name")),
                       "junk_code": np.where(code_junk, "junk code", np.where(code_up.eq(""), "blank code",
                                      np.where(valid_code, "valid code", "other code")))})
    ctx.ev["junk_entity_crosstab"] = (jt.groupby(["junk_name", "junk_code"]).size().reset_index(name="rows"))
    # mapping tables
    nm = ctx.raw["legal_entity"]
    ctx.add_map("legal_entity", nm, legal.where(~pd.Series(junk, index=nm.index), "(junk entity - not mapped)"),
                "name variants mapped to the entity_code they co-occur with (1:1 learned from data)",
                "Applied")
    ctx.add_map("entity_code", ctx.raw["entity_code"], ent_s.where(~pd.Series(junk, index=nm.index), "(junk entity - not mapped)"),
                "upper-case; 99 / T999 / blank-with-junk-name = junk", "Applied")
    _e_ch = int((legal.to_numpy() != ctx.S["legal_entity"].to_numpy()).sum())
    ctx.log_rule("E01", "legal_entity", _e_ch,
                 "Canonical legal_entity from entity_code (case-folded); name variants mapped 1:1 to code",
                 "Confirmed variants (1:1 mapping verified)", "Applied", cells_processed=ctx.n, cells_changed=_e_ch)
    ctx.log_rule("R4", "legal_entity, entity_code", junk.sum(),
                 "Junk entities ('TEST ENTITY','Do not use','xxx' or code 99/T999) flagged and excluded "
                 "(exclusion step 2); real country/currency on these rows are kept as data",
                 "Confirmed junk names (owner-stated for TEST ENTITY); Proposed for the others",
                 "Applied (flag + exclusion)")
    ctx.log_rule("E02", "entity_code", int((status == "UNRESOLVED").sum()),
                 "Entities that cannot be resolved by code or name (exclusion step 3)",
                 "Missing information", "Flag + exclusion")


def step_master(ctx: Ctx) -> None:
    S, D = ctx.S, ctx.D
    nonpost = ctx.arr["nonposting"]
    posting = ~nonpost
    gl_raw = S["gl_account"]
    has_gl = gl_raw.str.fullmatch(r"\d{4}").fillna(False).astype(bool).to_numpy()
    gl_invalid = (gl_raw.ne("").to_numpy() & ~has_gl)
    nm_key = name_key(S["account_name"])
    learn = has_gl & posting & nm_key.ne("").to_numpy()
    ct = pd.crosstab(nm_key[learn], gl_raw[learn])
    name_to_gl, conflicts = {}, []
    for k, row in ct.iterrows():
        nz = row[row > 0]
        if len(nz) == 1:
            name_to_gl[k] = nz.index[0]
        else:
            conflicts.append({"name_key": k, "gl": ",".join(nz.index)})
    mapped = nm_key.map(name_to_gl).fillna("")
    fill = posting & ~has_gl & mapped.ne("").to_numpy()
    gl = gl_raw.where(~pd.Series(fill, index=gl_raw.index), mapped)
    ctx.arr["gl_filled"] = fill
    ctx.arr["gl_unresolved"] = posting & ~(has_gl | fill)
    ctx.arr["gl_invalid"] = gl_invalid
    ctx.facts["gl_name_conflicts"] = conflicts
    D["gl_account_raw"] = ctx.raw["gl_account"]
    D["gl_account"] = gl
    ctx.add_audit("G01", "gl_account", fill, S["gl_account"], gl,
                  "blank gl_account on a posting row; filled from the normalised account_name (1:1 map learned from rows that carry both)")
    ctx.log_rule("G01", "gl_account", fill.sum(),
                 "Blank gl_account on posting rows filled from account_name (normalised: trim, '&'->'and', digit-3-for-e typo). "
                 "Map is 1:1 (verified); never used for non-posting rows",
                 "Deterministic correction (evidence-based)", "Applied + audited")
    ctx.log_rule("G02", "gl_account", int(ctx.arr["gl_unresolved"].sum()),
                 "Posting rows whose GL cannot be resolved", "Missing information", "Flag")

    # ---- GL master (account name / group / fs_line / statement / cost nature) ----
    stmt_row = S["statement"].str.lower().map(STATEMENT_MAP).fillna("")
    nat_row = S["cost_nature"].str.lower().map(COST_NATURE_MAP).fillna("")
    base = pd.DataFrame({
        "gl": gl_raw, "name": fix_name_typos(S["account_name"]), "group": S["account_group"],
        "fs": S["fs_line"], "stmt": stmt_row, "nature": nat_row})[has_gl & posting]
    group_case = _canon_case_map(S["account_group"][posting])
    master = {}
    gm_rows = []
    for g, grp in base.groupby("gl"):
        nm_mode = modal_value(grp["name"])
        grp_vals = grp["group"][grp["group"] != ""].str.lower().map(group_case)
        row = {"gl_account": g, "account_name": nm_mode,
               "account_group": modal_value(grp_vals) if len(grp_vals) else "",
               "fs_line": modal_value(grp["fs"]), "statement": modal_value(grp["stmt"]),
               "cost_nature_mode": modal_value(grp["nature"]),
               "cost_nature_mode_share": (grp["nature"].eq(modal_value(grp["nature"])) & grp["nature"].ne("")).sum()
                                         / max(1, grp["nature"].ne("").sum()),
               "rows": len(grp),
               "name_variants": name_key(grp["name"][grp["name"] != ""]).nunique(),
               "group_variants_after_case": grp_vals.nunique(),
               "fs_line_variants": grp["fs"][grp["fs"] != ""].nunique(),
               "statement_variants": grp["stmt"][grp["stmt"] != ""].nunique()}
        gm_rows.append(row)
        master[g] = row
    gm = pd.DataFrame(gm_rows)
    ctx.ev["gl_master"] = gm
    ctx.facts["gl_master_conflicts"] = int(((gm["name_variants"] > 1) | (gm["group_variants_after_case"] > 1)
                                            | (gm["fs_line_variants"] > 1) | (gm["statement_variants"] > 1)).sum())
    mp = lambda key: gl.map({g: r[key] for g, r in master.items()})
    mapped_ok = gl.isin(list(master.keys())).to_numpy() & posting
    acc_name = fix_name_typos(S["account_name"])
    acc_name = acc_name.where(~mapped_ok, mp("account_name"))
    grp_row = S["account_group"].str.lower().map(group_case).fillna(S["account_group"])
    acc_group = grp_row.where(~mapped_ok, mp("account_group"))
    fs_master = mp("fs_line").fillna("")
    fs_line = S["fs_line"].where(~(mapped_ok & S["fs_line"].eq("").to_numpy()), fs_master)
    fs_filled = mapped_ok & S["fs_line"].eq("").to_numpy() & fs_master.ne("").to_numpy()
    stmt_master = mp("statement").fillna("")
    stmt_clean = stmt_row.where(stmt_row.ne(""), stmt_master)
    stmt_conflict = (stmt_row.ne("").to_numpy() & stmt_master.ne("").to_numpy() & (stmt_row.to_numpy() != stmt_master.to_numpy()) & posting)
    stmt_unmapped = S["statement"].ne("").to_numpy() & stmt_row.eq("").to_numpy()
    D["account_name"] = acc_name
    D["account_group"] = acc_group
    D["fs_line"] = fs_line
    D["statement"] = stmt_clean
    ctx.arr["fs_filled"] = fs_filled
    ctx.arr["stmt_conflict"] = stmt_conflict
    ctx.arr["stmt_unmapped"] = stmt_unmapped
    ctx.add_audit("G03", "fs_line", fs_filled, S["fs_line"], fs_line,
                  "blank fs_line; filled from the GL master (gl_account -> fs_line is 1:1, 0 conflicts)")
    ctx.add_map("account_name", ctx.raw["account_name"], acc_name,
                "normalised and replaced by the single canonical name per GL (3->e typos, '&'/'and', spaces)", "Applied")
    ctx.add_map("account_group", ctx.raw["account_group"], acc_group, "case variants -> most frequent spelling; GL master", "Applied")
    ctx.add_map("statement", ctx.raw["statement"], stmt_clean, "label variants -> P&L / Balance Sheet", "Applied")
    ctx.add_map("fs_line", ctx.raw["fs_line"], fs_line, "blank filled from GL master; otherwise unchanged", "Applied")
    ctx.log_rule("G03", "fs_line", fs_filled.sum(), "Blank fs_line filled from GL master (1:1)", "Deterministic correction", "Applied + audited")
    _g_n = (acc_name.to_numpy() != S["account_name"].to_numpy())
    _g_g = (acc_group.to_numpy() != S["account_group"].to_numpy())
    _g_s = (stmt_clean.to_numpy() != S["statement"].to_numpy())
    ctx.log_rule("G04", "account_name, account_group, statement", int((_g_n | _g_g | _g_s).sum()),
        "Account name typos/variants, account_group case and statement labels standardised from the GL master",
        "Confirmed variants", "Applied", cells_processed=3 * ctx.n, cells_changed=int(_g_n.sum() + _g_g.sum() + _g_s.sum()))

    # cost nature: standardise label only; compare with GL expectation
    nat_mode = mp("cost_nature_mode").fillna("")
    D["cost_nature"] = nat_row
    D["cost_nature_gl_mode"] = nat_mode
    ctx.arr["nature_conflict"] = (nat_row.ne("").to_numpy() & nat_mode.ne("").to_numpy() & (nat_row.to_numpy() != nat_mode.to_numpy()) & posting)
    ctx.arr["nature_missing"] = nat_row.eq("").to_numpy() & posting
    ctx.add_map("cost_nature", ctx.raw["cost_nature"], nat_row, "F/V/Var -> Fixed/Variable; blanks stay blank", "Applied")

    # division
    dk = norm_key(S["division"])
    div = dk.map(DIVISION_MAP).fillna("")
    ctx.arr["division_unmapped"] = S["division"].ne("").to_numpy() & div.eq("").to_numpy()
    D["division"] = div
    ctx.add_map("division", ctx.raw["division"], div, "explicit alias map (24 raw spellings -> 5 divisions)", "Applied")
    _m1 = int((div.to_numpy() != S["division"].to_numpy()).sum())
    ctx.log_rule("M01", "division", _m1, "Division aliases mapped to 5 canonical divisions", "Confirmed variants", "Applied",
                 cells_processed=ctx.n, cells_changed=_m1)

    # country / currency
    D["country"] = S["country"]
    ccy = S["currency"].str.upper()
    D["currency"] = ccy
    D["currency_raw"] = ctx.raw["currency"]
    ctx.arr["country_mismatch"] = (S["country"].to_numpy() != ctx.arr["exp_country"]) & (ctx.arr["exp_country"] != "")
    ctx.arr["currency_mismatch"] = (ccy.to_numpy() != ctx.arr["exp_currency"]) & (ctx.arr["exp_currency"] != "")
    ctx.add_map("currency", ctx.raw["currency"], ccy, "upper-case", "Applied")

    # region from country
    reg_map = {}
    rc = pd.DataFrame({"c": S["country"], "r": S["region"]})
    rc = rc[(rc["r"] != "") & (rc["c"] != "")]
    reg_conf = 0
    for c, grp in rc.groupby("c"):
        if grp["r"].nunique() == 1:
            reg_map[c] = grp["r"].iloc[0]
        else:
            reg_conf += 1
    ctx.facts["region_country_conflicts"] = reg_conf
    reg_from = S["country"].map(reg_map).fillna("")
    reg_fill = S["region"].eq("").to_numpy() & reg_from.ne("").to_numpy()
    region = S["region"].where(~pd.Series(reg_fill, index=S.index), reg_from)
    D["region"] = region
    ctx.arr["region_filled"] = reg_fill
    ctx.add_audit("M02", "region", reg_fill, S["region"], region,
                  "blank region; filled from country (country -> region is 1:1 in the data)")
    ctx.log_rule("M02", "region", reg_fill.sum(), "Blank region filled from country (1:1)", "Deterministic correction", "Applied + audited")

    # cost centre
    cc_code = S["cost_center_code"].str.upper().str.replace(r"^CC-?(\d+)$", r"CC\1", regex=True)
    cc_name = S["cost_center_name"]
    cc_owner = S["cost_center_owner"]
    pair = pd.DataFrame({"c": cc_code, "n": cc_name, "o": cc_owner})
    pair = pair[(pair["c"] != "")]
    cc_name_map = {c: modal_value(g["n"]) for c, g in pair.groupby("c")}
    cc_owner_map = {c: modal_value(g["o"]) for c, g in pair.groupby("c")}
    ctx.facts["cc_name_conflicts"] = int(sum(g["n"][g["n"] != ""].nunique() > 1 for _, g in pair.groupby("c")))
    ctx.facts["cc_owner_conflicts"] = int(sum(g["o"][g["o"] != ""].nunique() > 1 for _, g in pair.groupby("c")))
    nm_fill = cc_name.eq("").to_numpy() & cc_code.ne("").to_numpy()
    ow_fill = cc_owner.eq("").to_numpy() & cc_code.ne("").to_numpy()
    D["cost_center_code"] = cc_code
    D["cost_center_name"] = cc_name.where(~pd.Series(nm_fill, index=S.index), cc_code.map(cc_name_map).fillna(""))
    D["cost_center_owner"] = cc_owner.where(~pd.Series(ow_fill, index=S.index), cc_code.map(cc_owner_map).fillna(""))
    ctx.arr["cc_missing"] = cc_code.eq("").to_numpy() & posting
    ctx.add_map("cost_center_code", ctx.raw["cost_center_code"], cc_code, "CC-210 -> CC210 (hyphen variants)", "Applied")
    _m3c = (cc_code.to_numpy() != S["cost_center_code"].to_numpy())
    ctx.log_rule("M03", "cost_center_code/name/owner", int((_m3c | nm_fill | ow_fill).sum()),
                 "Cost-centre code hyphen variants unified; name/owner trimmed. Blank cost centre stays blank "
                 "(no source to recover it from)", "Confirmed variants", "Applied",
                 cells_processed=3 * ctx.n, cells_changed=int(_m3c.sum() + nm_fill.sum() + ow_fill.sum()))


def step_periods_dates(ctx: Ctx) -> None:
    S, D = ctx.S, ctx.D
    per = parse_periods(S["fiscal_period"])
    py, pm = per["period_year"], per["period_month"]
    ok = py.notna() & pm.notna()
    ym = np.where(ok, py.fillna(0).astype(int).astype(str).str.zfill(4) + "-" + pm.fillna(0).astype(int).astype(str).str.zfill(2), "")
    end = ymd_to_datetime(py.to_numpy(), pm.to_numpy(), np.full(len(py), 1.0))
    end = (end + pd.offsets.MonthEnd(0)).where(ok)
    D["fiscal_period_raw"] = ctx.raw["fiscal_period"]
    D["period_format"] = per["period_format"]
    D["period_year"] = py.astype("Int64")
    D["period_month"] = pm.astype("Int64")
    D["period_ym"] = pd.Series(ym, index=S.index)
    D["period_end_date"] = end
    ctx.arr["py"], ctx.arr["pm"] = py, pm
    ctx.arr["period_ok"] = ok.to_numpy()
    ctx.facts["period_unparsed_n"] = int((~ok).sum())
    ctx.facts["period_months"] = int(pd.Series(ym)[ok.to_numpy()].nunique())
    ctx.ev["period_formats"] = (per.assign(raw=S["fiscal_period"]).groupby("period_format")
                                .agg(rows=("raw", "size"), example=("raw", "first")).reset_index())
    ctx.add_map("fiscal_period", ctx.raw["fiscal_period"], pd.Series(ym, index=S.index),
                "8 text formats parsed to year-month (P01 = January; supported by posting dates)", "Applied")
    ctx.log_rule("P01", "fiscal_period", ok.sum(), "fiscal_period parsed from 8 formats into period_year / period_month / period_ym",
                 "Deterministic parse", "Applied")

    # fiscal year
    fy = S["fiscal_year"]
    m4 = fy.str.fullmatch(r"\d{4}").fillna(False).astype(bool)
    mfy = fy.str.fullmatch(r"FY\d{2}").fillna(False).astype(bool)
    fy_num = pd.Series(np.nan, index=S.index)
    fy_num = fy_num.where(~m4, pd.to_numeric(fy.where(m4), errors="coerce"))
    fy_num = fy_num.where(~mfy, 2000 + pd.to_numeric(fy.where(mfy).str[2:], errors="coerce"))
    fy_clean = py.where(ok, fy_num)
    conflict = (fy_num.notna() & ok & (fy_num != py)).to_numpy()
    src = np.where(conflict, "CONFLICT_PERIOD_YEAR_USED",
           np.where(m4 & ok, "RAW_AGREES", np.where(mfy & ok, "RAW_FY_PREFIX_AGREES",
           np.where(~ok & fy_num.notna(), "RAW_ONLY", np.where(ok, "DERIVED_FROM_PERIOD", "UNRESOLVED")))))
    D["fiscal_year_raw"] = ctx.raw["fiscal_year"]
    D["fiscal_year"] = fy_clean.astype("Int64")
    D["fiscal_year_source"] = src
    ctx.arr["fy_filled"] = (src == "DERIVED_FROM_PERIOD")
    ctx.arr["fy_conflict"] = conflict
    ctx.add_audit("P02", "fiscal_year", ctx.arr["fy_filled"], ctx.raw["fiscal_year"], fy_clean.astype("Int64").astype(str),
                  "blank fiscal_year; derived from fiscal_period (fiscal_year equals the period year on 100% of rows that carry both)")
    ctx.log_rule("P02", "fiscal_year", int((src != "RAW_AGREES").sum()),
                 "fiscal_year: 'FY24' -> 2024; blank derived from fiscal_period; conflicts (if any) flagged",
                 "Deterministic correction", "Applied + audited")

    # posting date
    pdres = resolve_posting_dates(S["posting_date"], py, pm)
    D["posting_date_raw"] = ctx.raw["posting_date"]
    D["posting_date"] = pdres["posting_date"]
    D["posting_date_format"] = pdres["posting_date_format"]
    D["posting_date_resolution"] = pdres["posting_date_resolution"]
    ctx.arr["pd_mismatch"] = pdres["posting_date_period_mismatch"].to_numpy()
    res = pdres["posting_date_resolution"]
    ctx.arr["pd_blank"] = res.eq("blank").to_numpy()
    ctx.arr["pd_slash_resolved"] = res.str.startswith("slash_day") .to_numpy() | res.str.startswith("slash_month").to_numpy() | res.eq("slash_same_date_either_reading").to_numpy()
    ctx.arr["pd_unresolved"] = (res.str.contains("unresolved|invalid|unrecognised", regex=True)).to_numpy()
    ev = (pdres.assign(period_format=per["period_format"], raw_fmt=pdres["posting_date_format"])
          .groupby(["posting_date_format", "posting_date_resolution"]).size().reset_index(name="rows"))
    ctx.ev["posting_date_resolution"] = ev
    # evidence: non-slash dates vs period month, by period format
    ns = pdres["posting_date"].notna() & ~pdres["posting_date_format"].isin(["dd/mm/yyyy or mm/dd/yyyy", "blank"])
    t = pd.DataFrame({"period_format": per["period_format"][ns], "match": ~pdres["posting_date_period_mismatch"][ns]})
    ctx.ev["posting_date_vs_period"] = t.groupby("period_format")["match"].agg(rows="size", matches="sum").reset_index().assign(
        match_pct=lambda x: (x["matches"] / x["rows"] * 100).round(3))
    sl = S["posting_date"].str.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}").fillna(False).astype(bool)
    ab = S["posting_date"].where(sl).str.extract(r"^(\d{1,2})/(\d{1,2})/")
    a_ = pd.to_numeric(ab[0], errors="coerce")
    b_ = pd.to_numeric(ab[1], errors="coerce")
    amb = pd.Series(np.select([sl & (a_ > 12), sl & (b_ > 12), sl & (a_ == b_), sl], ["value forces day-first", "value forces month-first", "day = month (same either way)", "ambiguous by value - decided by period"], ""), index=S.index)
    ctx.ev["slash_date_ambiguity"] = amb[sl].value_counts().rename_axis("class").reset_index(name="rows")
    ctx.add_audit("P03", "posting_date", ctx.arr["pd_slash_resolved"], ctx.raw["posting_date"],
                  pdres["posting_date"].dt.strftime("%Y-%m-%d").fillna(""),
                  "slash date: day-first or month-first decided by which reading falls in the row's fiscal-period month (exactly one does)")
    ctx.log_rule("P03", "posting_date", int(sl.sum()),
                 "Slash dates (dd/mm vs mm/dd both occur) resolved by the fiscal-period month; unresolved ones stay blank",
                 "Assumption supported by evidence (100% of unambiguous dates lie in the period month)", "Applied + audited")
    ctx.log_rule("P04", "posting_date", int(ctx.arr["pd_blank"].sum()),
                 "Blank posting dates left blank (no source to derive them)", "Missing information", "Flag")

    # extract batch
    eb = S["extract_batch"]
    m = eb.str.extract(r"^CLOSE-(\d{4}|XX)-(\d{3})$")
    ok_b = m[0].notna()
    infer = (m[0] == "XX") & ok
    year_txt = py.fillna(0).astype(int).astype(str)
    batch = eb.where(~infer, "CLOSE-" + year_txt + "-" + m[1].fillna(""))
    bconf = (m[0].notna() & (m[0] != "XX") & ok & (pd.to_numeric(m[0], errors="coerce") != py)).to_numpy()
    D["extract_batch_raw"] = ctx.raw["extract_batch"]
    D["extract_batch"] = batch
    ctx.arr["batch_inferred"] = infer.to_numpy()
    ctx.arr["batch_conflict"] = bconf
    ctx.arr["batch_badformat"] = (eb.ne("") & ~ok_b).to_numpy()
    bp = pd.DataFrame({"b": batch, "p": pd.Series(ym, index=S.index)})
    bp = bp[bp["p"] != ""]
    ctx.facts["batches_multi_period"] = int((bp.groupby("b")["p"].nunique() > 1).sum())
    ctx.add_audit("B01", "extract_batch", ctx.arr["batch_inferred"], ctx.raw["extract_batch"], batch,
                  "'CLOSE-XX-nnn': year placeholder replaced by the fiscal-period year (batch years equal the period year on 100% of other rows)")
    ctx.log_rule("B01", "extract_batch", infer.sum(), "'CLOSE-XX-nnn' batch ids completed with the fiscal-period year",
                 "Proposed - Needs Validation (inference)", "Applied + audited")


def step_amounts(ctx: Ctx) -> None:
    S, D = ctx.S, ctx.D
    ev_rows = []
    for rawc in AMOUNT_RAW_COLS:
        short = AMOUNT_CLEAN_NAMES[rawc]
        p = parse_amount_series(ctx.raw[rawc])
        ctx.P[short] = p
        D[rawc] = ctx.raw[rawc]
        D[f"{short}_parsed"] = p["value"]
        D[f"{short}_status"] = p["status"]
        D[f"{short}_format"] = p["fmt"]
        ctx.facts[f"unparsed_{short}"] = int((p["status"] == "unparsed").sum())
        for st, cnt in p["status"].value_counts().items():
            ev_rows.append({"column": rawc, "kind": "status", "value": st, "rows": int(cnt)})
        for f_, cnt in p.loc[p["status"] == "ok", "fmt"].value_counts().items():
            ev_rows.append({"column": rawc, "kind": "format", "value": f_, "rows": int(cnt)})
        tok = collapse_ws(ctx.raw[rawc])
        tok = tok[(p["status"] == "placeholder").to_numpy()]
        for v, cnt in tok.value_counts().items():
            ev_rows.append({"column": rawc, "kind": "placeholder token", "value": v, "rows": int(cnt)})
    ctx.ev["amount_parse_evidence"] = pd.DataFrame(ev_rows)
    nonpost = ctx.arr["nonposting"]
    # fx / qty / headcount
    fx = parse_plain_numeric(ctx.raw["fx_rate_raw"], allow_negative=False)
    # qty / headcount use the full amount grammar (two qty cells carry '1,323.98')
    qty = parse_amount_series(ctx.raw["qty_raw"])
    hc = parse_amount_series(ctx.raw["headcount_fte_raw"])
    ctx.P["fx"], ctx.P["qty"], ctx.P["hc"] = fx, qty, hc
    D["fx_rate_raw"] = ctx.raw["fx_rate_raw"]
    D["fx_rate"] = fx["value"]
    D["fx_status"] = fx["status"]
    D["qty_raw"] = ctx.raw["qty_raw"]
    D["qty"] = qty["value"]
    D["headcount_fte_raw"] = ctx.raw["headcount_fte_raw"]
    D["headcount_fte"] = hc["value"]
    for nm_, fr in (("fx", fx), ("qty", qty), ("headcount", hc)):
        ctx.facts[f"unparsed_{nm_}"] = int((fr["status"] == "unparsed").sum())
    tot_cells = sum(int(ctx.P[s]["status"].isin(["ok"]).sum()) for s in ALL_AMT_SHORT)
    _ok_any = np.column_stack([(ctx.P[s]["status"] == "ok").to_numpy() for s in ALL_AMT_SHORT]).any(axis=1)
    ctx.log_rule("A01", "5 amount columns", int(_ok_any.sum()),
                 "Amount text parsed with a strict grammar (US 1,234.56 / EU 1.234,56 / decimal comma / thousands-integer / "
                 "plain; $ ; parentheses and leading '-' = negative). Nothing is guessed: unrecognised text would be "
                 "'unparsed' (count = %d)" % sum(ctx.facts[f"unparsed_{s}"] for s in ALL_AMT_SHORT),
                 "Deterministic parse (independent oracle re-check in Validation_Checks)", "Applied",
                 cells_processed=len(ALL_AMT_SHORT) * ctx.n, cells_changed=tot_cells)
    ph = sum(int((ctx.P[s]["status"] == "placeholder").sum()) for s in ALL_AMT_SHORT)
    bl = sum(int((ctx.P[s]["status"] == "blank").sum()) for s in ALL_AMT_SHORT)
    _miss_any = np.column_stack([ctx.P[s]["status"].isin(["placeholder", "blank"]).to_numpy() for s in ALL_AMT_SHORT]).any(axis=1)
    ctx.log_rule("A02", "5 amount columns", int(_miss_any.sum()),
                 "Placeholders (###, #N/A, NA, N/A, n/a, null, '-') and blanks become MISSING (NaN), never zero",
                 "Missing information", "Applied", cells_processed=len(ALL_AMT_SHORT) * ctx.n, cells_changed=ph + bl)


# =============================================================================
# 8. SCALE DECISION  (report_scale is untrusted; decided per row from evidence)
# =============================================================================
_LABEL_CANON = {"actual": "Actual", "thousands": "Thousands", "lakhs": "Lakhs", "000s": "000s",
                "in thousands": "In thousands", "": "(blank)"}
_LABEL_IMPLIED_DIVISOR = {"Actual": 1.0, "Thousands": 1000.0, "000s": 1000.0, "In thousands": 1000.0,
                          "Lakhs": 100000.0}


def _robust_sd(x: pd.Series) -> float:
    x = x.dropna()
    if len(x) < 5:
        return np.nan
    return float((x.quantile(0.9) - x.quantile(0.1)) / 2.5631)


def step_scale(ctx: Ctx) -> None:
    S, D, P = ctx.S, ctx.D, ctx.P
    n = ctx.n
    posting = pd.Series(~ctx.arr["nonposting"], index=ctx.D.index)
    gl = D["gl_account"]
    ent = D["entity_code"]
    label_raw = S["report_scale"]
    label = label_raw.str.lower().map(_LABEL_CANON)
    unknown_label = label.isna()
    label = label.fillna(label_raw)
    D["report_scale_raw"] = ctx.raw["report_scale"]
    D["report_scale_label"] = label
    implied = label.map(_LABEL_IMPLIED_DIVISOR)

    # --- magnitude per row: median log10|x| over the USD columns ---------------
    V = np.column_stack([P[s]["value"].to_numpy() for s in USD_SHORT])
    with np.errstate(divide="ignore", invalid="ignore"):
        L = np.where(np.abs(V) > 0, np.log10(np.abs(V)), np.nan)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        rowmag = np.nanmedian(L, axis=1)
    rowmag = pd.Series(rowmag, index=D.index)

    # --- price identity (GL 4100 / 5100): independent ground truth -------------
    qty = P["qty"]["value"]
    price = S["product_family"].map(LIST_PRICE_BY_FAMILY)
    act = P["actual_usd"]["value"]
    act_err = P["actual_usd"]["abs_err"]
    cand = (posting & gl.isin(PRICE_IDENTITY_GLS) & price.notna() & qty.notna() & (qty != 0)
            & act.notna() & (act != 0)).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = (act_err / act.abs()).to_numpy()
        r = np.log10(np.abs(act.to_numpy()) / (np.abs(qty.to_numpy()) * price.to_numpy(dtype=float)))
    usable = cand & np.isfinite(rel) & (rel <= IDENTITY_MAX_REL_ROUNDING) & np.isfinite(r)
    devs = np.column_stack([np.abs(r), np.abs(r + 3.0), np.abs(r + 5.0)])
    devs = np.where(np.isfinite(devs), devs, 9.0)
    best = devs.argmin(axis=1)
    best_dev = devs.min(axis=1)
    divisors = np.array([1.0, 1000.0, 100000.0])
    id_div = np.where(usable & (best_dev <= IDENTITY_TOL_LOG10), divisors[best], np.nan)
    id_nomatch = usable & (best_dev > IDENTITY_TOL_LOG10)
    D["price_identity_log10_ratio"] = np.where(usable, r, np.nan)
    ctx.arr["id_div"] = id_div
    ctx.facts["identity_candidates"] = int(cand.sum())
    ctx.facts["identity_usable"] = int(usable.sum())
    ctx.facts["identity_nomatch"] = int(id_nomatch.sum())

    # --- peer baseline from rows we are confident are undivided ----------------
    ref = (posting.to_numpy() & np.isfinite(rowmag.to_numpy()) & gl.ne("").to_numpy() & ent.ne("").to_numpy()
           & (((label == "Actual").to_numpy() & ~(id_div > 1)) | (id_div == 1)))
    rf = pd.DataFrame({"gl": gl[ref], "ent": ent[ref], "m": rowmag[ref]})
    g1 = rf.groupby(["gl", "ent"])["m"].agg(med="median", sd=_robust_sd, n="count")
    g2 = rf.groupby(["gl"])["m"].agg(med="median", sd=_robust_sd, n="count")
    k1 = pd.MultiIndex.from_arrays([gl, ent])
    a1 = g1.reindex(k1)
    a2 = g2.reindex(gl.to_numpy())
    use1 = (a1["n"].to_numpy() >= BASELINE_MIN_GROUP)
    use2 = ~use1 & (a2["n"].to_numpy() >= BASELINE_MIN_GROUP)
    med = np.where(use1, a1["med"].to_numpy(), np.where(use2, a2["med"].to_numpy(), np.nan))
    sd = np.where(use1, a1["sd"].to_numpy(), np.where(use2, a2["sd"].to_numpy(), np.nan))
    sd = np.maximum(sd, Z_SD_FLOOR)
    z = (rowmag.to_numpy() - med) / sd
    D["row_log10_magnitude"] = rowmag
    D["scale_peer_zscore"] = np.where(np.isfinite(z), np.round(z, 3), np.nan)
    D["scale_baseline_source"] = np.where(use1, "gl+entity", np.where(use2, "gl", ""))
    ctx.facts["baseline_groups_gl_entity"] = int((g1["n"] >= BASELINE_MIN_GROUP).sum())
    ctx.facts["baseline_groups_gl"] = int((g2["n"] >= BASELINE_MIN_GROUP).sum())

    # --- decision --------------------------------------------------------------
    lab = label.to_numpy()
    zf = np.isfinite(z)
    decision = np.full(n, "NOT_APPLICABLE_NON_POSTING", dtype=object)
    factor = np.full(n, np.nan)
    evidence = np.full(n, "", dtype=object)
    confidence = np.full(n, "", dtype=object)
    post = posting.to_numpy()

    def setd(mask, dec, fac, evd, conf):
        m = mask & (decision_open)
        decision[m] = dec if isinstance(dec, str) else dec[m]
        factor[m] = fac if np.isscalar(fac) else fac[m]
        evidence[m] = evd
        confidence[m] = conf
        decision_open[m] = False

    decision_open = post.copy()
    # A. price identity
    for dv, name in ((1.0, "UNDIVIDED"), (1000.0, "DIVIDED_1E3"), (100000.0, "DIVIDED_1E5")):
        setd(np.isfinite(id_div) & (id_div == dv), name, dv, "PRICE_IDENTITY", "HIGH")
    # B. labels whose tested rows were 100% undivided
    lab_undiv = np.isin(lab, ["Actual", "000s", "In thousands"])
    setd(lab_undiv, "UNDIVIDED", 1.0, "LABEL_(identity-verified_on_GL_4100/5100)", "MEDIUM")
    # C. Thousands / Lakhs / blank: peer z-score bands
    setd(zf & (z >= Z_UNDIVIDED_MIN), "UNDIVIDED", 1.0, "PEER_ZSCORE", "MEDIUM")
    setd(zf & (z <= Z_DIVIDED_MAX) & (lab == "Thousands"), "DIVIDED_1E3", 1000.0, "PEER_ZSCORE", "MEDIUM")
    setd(zf & (z <= Z_DIVIDED_MAX) & (lab == "Lakhs"), "DIVIDED_1E5", 100000.0, "PEER_ZSCORE", "MEDIUM")
    # D. everything else stays undetermined
    why = np.where(~zf, "no_magnitude_or_baseline",
                   np.where((lab == "(blank)") & (z <= Z_DIVIDED_MAX), "blank_label_low_magnitude_factor_unknown",
                            "z_between_bands"))
    setd(np.ones(n, dtype=bool), "UNDETERMINED", np.nan, "NONE", "")
    evidence[(decision == "UNDETERMINED")] = why[(decision == "UNDETERMINED")]
    D["scale_decision"] = decision
    D["scale_evidence"] = evidence
    D["scale_confidence"] = confidence
    D["scale_divisor_found"] = factor
    applied = factor if APPLY_SCALE_RESTORATION else np.where(post, 1.0, np.nan)
    D["scale_factor_applied"] = applied
    imp = implied.to_numpy(dtype=float)
    contradicted = post & np.isfinite(factor) & np.isfinite(imp) & (factor != imp)
    ctx.arr["scale_contradicted"] = contradicted
    ctx.arr["scale_undetermined"] = (decision == "UNDETERMINED")
    ctx.arr["scale_restored"] = post & np.isfinite(applied) & (applied > 1.0)
    ctx.arr["low_tail"] = post & np.isfinite(factor) & (factor == 1.0) & zf & (z <= Z_DIVIDED_MAX)
    ctx.arr["scale_unknown_label"] = unknown_label.to_numpy()

    # --- restored values -------------------------------------------------------
    for short in ALL_AMT_SHORT:
        v = P[short]["value"].to_numpy()
        adj = np.round(v * applied, 6)      # rounded to remove binary-float artefacts only
        D[f"{short}_adj"] = np.where(np.isfinite(adj), adj, np.nan)
    D["actual_usd_adj_abs_uncertainty"] = np.where(np.isfinite(applied) & P["actual_usd"]["value"].notna().to_numpy(),
                                                   P["actual_usd"]["abs_err"].to_numpy() * applied, np.nan)
    for short in ALL_AMT_SHORT:
        mask = ctx.arr["scale_restored"] & P[short]["value"].notna().to_numpy()
        ctx.add_audit("S01", f"{short}", mask, P[short]["value"].round(6), D[f"{short}_adj"].round(6),
                      "scale restoration: value multiplied by the evidence-based divisor (price identity or peer z-score); as-reported value in *_parsed")
    # --- evidence tables -------------------------------------------------------
    ev = pd.DataFrame({"label": label, "decision": decision, "evidence": evidence, "confidence": confidence})[post]
    t = ev.groupby(["label", "decision", "evidence", "confidence"]).size().reset_index(name="rows")
    t["share_of_label_%"] = (t["rows"] / t.groupby("label")["rows"].transform("sum") * 100).round(2)
    ctx.ev["scale_decision_by_label"] = t.sort_values(["label", "rows"], ascending=[True, False])

    idf = pd.DataFrame({"label": label, "id_div": id_div})[usable & np.isfinite(id_div)]
    if len(idf):
        it = idf.groupby(["label", "id_div"]).size().reset_index(name="rows")
        it["meaning"] = it["id_div"].map({1.0: "undivided (value = qty x list price)", 1000.0: "divided by 1,000", 100000.0: "divided by 100,000"})
        ctx.ev["scale_identity_truth"] = it
    # validate the z-rule on rows whose truth is known from the identity
    kn = usable & np.isfinite(id_div) & zf & np.isin(lab, ["Thousands", "Lakhs"])
    if kn.any():
        pred = np.where(z >= Z_UNDIVIDED_MIN, "UNDIVIDED", np.where(z <= Z_DIVIDED_MAX, "DIVIDED", "UNDETERMINED"))
        truth = np.where(id_div == 1.0, "UNDIVIDED", "DIVIDED")
        cf = pd.crosstab(pd.Series(truth[kn], name="truth_from_price_identity"), pd.Series(pred[kn], name="z_rule_prediction"))
        cf = cf.reset_index()
        ctx.ev["scale_z_validation"] = cf
        wrong = int(((truth[kn] == "UNDIVIDED") & (pred[kn] == "DIVIDED")).sum() + ((truth[kn] == "DIVIDED") & (pred[kn] == "UNDIVIDED")).sum())
        ctx.facts["z_rule_wrong_on_identity_rows"] = wrong
        ctx.facts["z_rule_identity_rows_tested"] = int(kn.sum())
    # natural left-tail of Actual-labelled rows (cannot be called divided)
    act_lab = post & (label == "Actual").to_numpy() & zf
    tail = pd.DataFrame({"gl_group": np.where(gl.isin(PRICE_IDENTITY_GLS), "identity GLs (4100/5100)", "other GLs"),
                         "z": z})[act_lab]
    tt = []
    for thr in (-3.0, -4.0, -5.0, -6.0, -7.0):
        for gname, grp in tail.groupby("gl_group"):
            tt.append({"gl_group": gname, "z_threshold": thr, "actual_labelled_rows": len(grp),
                       "rows_at_or_below": int((grp["z"] <= thr).sum()),
                       "share_%": round(float((grp["z"] <= thr).mean() * 100), 3)})
    ctx.ev["scale_actual_tail"] = pd.DataFrame(tt)
    ctx.facts["actual_tail_rate_other_gl"] = float(((tail["z"] <= Z_DIVIDED_MAX) & (tail["gl_group"] == "other GLs")).sum() /
                                                   max(1, (tail["gl_group"] == "other GLs").sum()))
    # value effect of restoration
    eff = pd.DataFrame({"label": label, "decision": decision,
                        "reported_abs_actual": np.abs(P["actual_usd"]["value"].to_numpy()),
                        "restored_abs_actual": np.abs(D["actual_usd_adj"].to_numpy())})[ctx.arr["scale_restored"]]
    if len(eff):
        e = eff.groupby(["label", "decision"]).agg(rows=("label", "size"), reported_abs_actual_usd=("reported_abs_actual", "sum"),
                                                   restored_abs_actual_usd=("restored_abs_actual", "sum")).reset_index()
        e["understatement_if_ignored_usd"] = e["restored_abs_actual_usd"] - e["reported_abs_actual_usd"]
        ctx.ev["scale_value_effect"] = e
    ctx.facts["scale_understatement_abs_actual"] = float((eff["restored_abs_actual"] - eff["reported_abs_actual"]).sum()) if len(eff) else 0.0
    _s1_cells = int(sum(np.isfinite(ctx.P[s]["value"].to_numpy())[ctx.arr["scale_restored"]].sum() for s in ALL_AMT_SHORT))
    ctx.log_rule("S01", "report_scale + 5 amount columns", int(ctx.arr["scale_restored"].sum()),
                 "Scale decided PER ROW from evidence (price identity > label-verified > peer z-score), not from the label. "
                 "Labels '000s' and 'In thousands' were NEVER divided in the tested rows, so they are NOT multiplied. "
                 "Rows decided as divided are multiplied by 1,000 / 100,000; as-reported values are kept in *_parsed",
                 "Evidence-based: HIGH = price-identity consistency test (list prices inferred from this dataset, not an independent source); "
                 "MEDIUM = peer z-score. Neither is a proven truth - rule status per Phase-1 doc: Unresolved",
                 "Applied (switch APPLY_SCALE_RESTORATION)",
                 cells_processed=len(ALL_AMT_SHORT) * ctx.n, cells_changed=_s1_cells)
    ctx.log_rule("S02", "report_scale", int(ctx.arr["scale_undetermined"].sum()),
                 "Scale UNDETERMINED (z-score between bands, or blank label with very low magnitude): amounts left unrestored (NaN in *_adj) "
                 "and excluded at exclusion step 8", "Unresolved", "Flag + exclusion")


# =============================================================================
# 9. FX, SIGNS, OTHER COLUMNS
# =============================================================================
def step_fx_sign(ctx: Ctx) -> None:
    D, P = ctx.D, ctx.P
    posting = pd.Series(~ctx.arr["nonposting"], index=ctx.D.index)
    ccy = D["currency"].to_numpy()
    fxv = P["fx"]["value"].to_numpy()
    fxs = P["fx"]["status"].to_numpy()
    loc = D["amount_local_adj"].to_numpy()
    act = D["actual_usd_adj"].to_numpy()
    loc_u = np.where(np.isfinite(D["amount_local_adj"].to_numpy()), P["amount_local"]["abs_err"].to_numpy() * D["scale_factor_applied"].to_numpy(), np.nan)
    act_u = D["actual_usd_adj_abs_uncertainty"].to_numpy()
    is_usd = (ccy == "USD")
    fx_ok = (fxs == "ok") & np.isfinite(fxv) & (fxv > 0)
    fx_zero = (fxs == "ok") & (fxv == 0)
    testable = posting & fx_ok & np.isfinite(loc) & np.isfinite(act) & (act != 0) & (loc != 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        exp_div = np.abs(loc) / fxv
        exp_mul = np.abs(loc) * fxv
        tol_div = np.maximum(0.001 * np.abs(act), act_u + loc_u / fxv + 1e-9)
        tol_mul = np.maximum(0.001 * np.abs(act), act_u + loc_u * fxv + 1e-9)
        m_div = testable & (np.abs(np.abs(act) - exp_div) <= tol_div)
        m_mul = testable & (np.abs(np.abs(act) - exp_mul) <= tol_mul)
        rel_diff = np.where(testable, (exp_div - np.abs(act)) / np.abs(act), np.nan)
    near1 = np.isfinite(fxv) & (np.abs(fxv - 1.0) <= 0.02)
    chk = np.full(ctx.n, "", dtype=object)
    chk[posting.to_numpy()] = "NOT_TESTABLE"
    chk[posting.to_numpy() & ~fx_ok & (fxs == "ok") & fx_zero] = "NOT_TESTABLE_FX_ZERO"
    chk[posting.to_numpy() & (fxs != "ok")] = "NOT_TESTABLE_FX_MISSING"
    chk[posting.to_numpy() & fx_ok & ~np.isfinite(loc)] = "NOT_TESTABLE_LOCAL_MISSING"
    chk[posting.to_numpy() & fx_ok & np.isfinite(loc) & ~np.isfinite(act)] = "NOT_TESTABLE_USD_MISSING_OR_SCALE_UNDETERMINED"
    chk[testable] = "NO_MATCH"
    chk[m_mul & ~m_div] = "MATCH_LOCAL_TIMES_RATE"
    chk[m_div & ~m_mul] = "MATCH_LOCAL_DIV_RATE"
    chk[m_div & m_mul] = "MATCH_BOTH_RATE_NEAR_1"
    D["fx_check"] = chk
    D["usd_from_local_div_rate"] = np.where(testable, np.sign(act) * exp_div, np.nan)
    D["fx_rel_diff_vs_actual"] = np.where(np.isfinite(rel_diff), np.round(rel_diff, 6), np.nan)
    ctx.arr["fx_zero"] = posting.to_numpy() & fx_zero
    ctx.arr["fx_missing"] = posting.to_numpy() & (fxs != "ok")
    ctx.arr["fx_one_nonusd"] = posting.to_numpy() & ~is_usd & (fxs == "ok") & (fxv == 1.0)
    ctx.arr["fx_usd_not_one"] = posting.to_numpy() & is_usd & fx_ok & (np.abs(fxv - 1.0) > 0.001)
    ctx.arr["fx_no_match"] = (chk == "NO_MATCH")
    usd_loc_neq = posting.to_numpy() & is_usd & np.isfinite(loc) & np.isfinite(act) & (np.abs(np.abs(loc) - np.abs(act)) > np.maximum(0.001 * np.abs(act), act_u + loc_u + 1e-9))
    ctx.arr["usd_local_neq"] = usd_loc_neq
    # ---- population waterfall that reconciles the three USD/FX counts quoted in different sheets ----
    pst = posting.to_numpy()
    nrate = np.abs(fxv - 1.0)
    both_amt = pst & is_usd & np.isfinite(loc) & np.isfinite(act)
    usd_p = pst & is_usd
    rate_out = usd_p & fx_ok & (nrate > 0.001)
    rate_in = usd_p & fx_ok & (nrate <= 0.001)
    ctx.facts["fx_pop"] = {
        "usd_all": int(is_usd.sum()), "usd_nonposting": int((is_usd & ~pst).sum()), "usd_posting": int(usd_p.sum()),
        "rate_unusable_text": int((usd_p & (fxs != "ok")).sum()), "rate_zero": int((usd_p & fx_zero).sum()),
        "rate_usable": int((usd_p & fx_ok).sum()), "rate_within": int(rate_in.sum()), "rate_outside": int(rate_out.sum()),
        "rate_exactly_one": int((usd_p & fx_ok & (fxv == 1.0)).sum()),
        "both_amounts": int(both_amt.sum()), "amt_differ": int(usd_loc_neq.sum()),
        "overlap": int((usd_loc_neq & rate_out).sum()), "amt_differ_rate_ok": int((usd_loc_neq & ~rate_out).sum()),
        "rate_out_amt_same_or_untestable": int((rate_out & ~usd_loc_neq).sum()),
    }
    _p = ctx.facts["fx_pop"]
    ctx.ev["fx_usd_population"] = pd.DataFrame([
        ("1", "USD-currency rows, all rows", _p["usd_all"], ""),
        ("2", "  less non-posting rows (TOTAL / Subtotal / CHECK)", -_p["usd_nonposting"], ""),
        ("3", "= USD-currency POSTING rows", _p["usd_posting"], "base population for every USD/FX count below"),
        ("4", "  less FX rate missing (NA, '-', blank)", -_p["rate_unusable_text"], "flag_fx_missing"),
        ("5", "  less FX rate = 0 (invalid)", -_p["rate_zero"], "flag_fx_zero"),
        ("6", "= USD posting rows with a USABLE rate (> 0)", _p["rate_usable"], "FX_Evidence 'fx_ok' for USD (the 23,577-type count)"),
        ("7", "    of which rate within 1.000 +/- 0.001", _p["rate_within"], "not flagged"),
        ("8", "    of which rate OUTSIDE 1.000 +/- 0.001", _p["rate_outside"], "flag_fx_usd_rate_not_one -> Open_Items and finding F12b (the 22,567-type count)"),
        ("9", "    memo: rate exactly 1.0", _p["rate_exactly_one"], "no USD row carries exactly 1.0"),
        ("10", "SEPARATE TEST ON AMOUNTS (not on the rate): USD posting rows with both local and actual present", _p["both_amounts"], "population for the amount test"),
        ("11", "    of which |local| differs from |actual USD| beyond rounding", _p["amt_differ"], "flag_usd_row_local_neq_usd -> finding F12 (the 21,106-type count)"),
        ("12", "      of which the rate is also outside 1.000 +/- 0.001 (overlap of the two tests)", _p["overlap"], ""),
        ("13", "      of which the rate is within tolerance or unusable", _p["amt_differ_rate_ok"], "amounts differ although the rate is ~1.0 or unusable"),
        ("14", "    memo: rate outside tolerance but amounts agree or cannot be tested", _p["rate_out_amt_same_or_untestable"], ""),
    ], columns=["line", "population", "rows", "used_in / flag"])
    # evidence by currency
    rows = []
    for c in sorted(set(ccy[posting.to_numpy()])):
        m = posting.to_numpy() & (ccy == c)
        t = m & testable
        rows.append({"currency": c, "posting_rows": int(m.sum()),
                     "fx_ok": int((m & fx_ok).sum()), "fx_zero": int((m & fx_zero).sum()),
                     "fx_missing(NA,-,blank)": int((m & (fxs != "ok")).sum()),
                     "fx_exactly_1.0": int((m & (fxs == "ok") & (fxv == 1.0)).sum()),
                     "median_rate": round(float(np.nanmedian(np.where(m & fx_ok, fxv, np.nan))), 6) if (m & fx_ok).any() else np.nan,
                     "p5_rate": round(float(np.nanpercentile(np.where(m & fx_ok, fxv, np.nan), 5)), 6) if (m & fx_ok).any() else np.nan,
                     "p95_rate": round(float(np.nanpercentile(np.where(m & fx_ok, fxv, np.nan), 95)), 6) if (m & fx_ok).any() else np.nan,
                     "testable_rows": int(t.sum()),
                     "match_local_div_rate": int((m & (chk == "MATCH_LOCAL_DIV_RATE")).sum()),
                     "match_local_times_rate": int((m & (chk == "MATCH_LOCAL_TIMES_RATE")).sum()),
                     "match_both(rate~1)": int((m & (chk == "MATCH_BOTH_RATE_NEAR_1")).sum()),
                     "no_match": int((m & (chk == "NO_MATCH")).sum())})
    fxe = pd.DataFrame(rows)
    ctx.ev["fx_by_currency"] = fxe
    ctx.ev["fx_check_summary"] = (pd.Series(chk[posting.to_numpy()]).value_counts().rename_axis("fx_check").reset_index(name="rows"))
    ctx.facts["fx_div_share_testable"] = float((m_div.sum()) / max(1, testable.sum()) * 100)
    ctx.facts["fx_mul_share_testable"] = float(((m_mul & ~m_div).sum()) / max(1, testable.sum()) * 100)
    ctx.facts["fx_testable"] = int(testable.sum())
    ctx.log_rule("F01", "fx_rate_raw", int(ctx.arr["fx_zero"].sum()),
                 "FX rate 0 flagged (not a valid rate): such rows are never converted. USD = local / rate is TESTED, not assumed "
                 "(fx_check); the reported actual_usd is never replaced by a recomputed value",
                 "Confirmed anomaly (zero rate); FX direction Proposed", "Flag only")
    ctx.log_rule("F02", "fx_rate_raw", int(ctx.arr["fx_one_nonusd"].sum()),
                 "Rate exactly 1.0 on a non-USD row flagged (likely default/placeholder rate)",
                 "Suspected anomaly", "Flag only")

    # --- sign pattern across the five amount columns --------------------------
    M = np.column_stack([P[s]["value"].to_numpy() for s in ALL_AMT_SHORT])
    pos = np.nansum(np.where(np.isfinite(M), M > 0, False), axis=1)
    neg = np.nansum(np.where(np.isfinite(M), M < 0, False), axis=1)
    avail = np.isfinite(M).sum(axis=1)
    # letters (not + - symbols) so Excel can never read a pattern cell as a formula.
    # Order of the 5 characters: amount_local, actual_usd, budget_usd, forecast_usd, prior_year_usd.
    # P = positive, N = negative, Z = exactly zero, _ = missing / unparsed
    ch = np.where(~np.isfinite(M), "_", np.where(M > 0, "P", np.where(M < 0, "N", "Z")))
    pattern = pd.Series(ch[:, 0]).str.cat([pd.Series(ch[:, i]) for i in range(1, 5)]).to_numpy()
    flag = np.full(ctx.n, "", dtype=object)
    p_ = posting.to_numpy()
    flag[p_] = "MIXED_OTHER"
    flag[p_ & (avail == 0)] = "NO_AMOUNTS"
    flag[p_ & (avail > 0) & (neg == 0)] = "ALL_NON_NEGATIVE"
    flag[p_ & (avail >= 3) & (neg == avail)] = "ALL_NEGATIVE"
    single = p_ & (avail >= 4) & (((neg == 1) & (pos >= 3)) | ((pos == 1) & (neg >= 3)))
    flag[single] = "SINGLE_COLUMN_SIGN_FLIP"
    flip_col = np.full(ctx.n, "", dtype=object)
    for i, s in enumerate(ALL_AMT_SHORT):
        minority = np.where(neg == 1, M[:, i] < 0, M[:, i] > 0)
        flip_col[single & np.isfinite(M[:, i]) & minority] = s
    D["sign_pattern"] = np.where(p_, pattern, "")
    D["sign_flag"] = flag
    D["sign_flip_column"] = flip_col
    locv, actv = P["amount_local"]["value"].to_numpy(), P["actual_usd"]["value"].to_numpy()
    ctx.arr["local_usd_sign_conflict"] = p_ & np.isfinite(locv) & np.isfinite(actv) & (locv != 0) & (actv != 0) & (np.sign(locv) != np.sign(actv))
    ctx.arr["sign_all_neg"] = (flag == "ALL_NEGATIVE")
    ctx.arr["sign_single_flip"] = single
    ctx.ev["sign_pattern_summary"] = (pd.Series(flag[p_]).value_counts().rename_axis("sign_flag").reset_index(name="rows"))
    ctx.log_rule("N01", "5 amount columns", int(single.sum()),
                 "Sign pattern across local/actual/budget/forecast/prior: a single column whose sign differs from the other >=3 is flagged "
                 "(column named). Values are NOT changed - the account sign convention (R9) is unresolved",
                 "Suspected anomaly (injected-noise pattern)", "Flag only")
    ctx.log_rule("N02", "5 amount columns", int(ctx.arr["sign_all_neg"].sum()),
                 "Rows negative in every available column are plausible credits/reversals: reported as information, not an error",
                 "Legitimate / information", "Flag only")


def _map_token(series: pd.Series, mapping: Dict[str, str]) -> Tuple[pd.Series, np.ndarray]:
    low = series.str.lower()
    out = low.map(mapping).fillna("")
    unmapped = (series.ne("") & out.eq("")).to_numpy()
    return out, unmapped


def step_other_columns(ctx: Ctx) -> None:
    S, D = ctx.S, ctx.D
    posting = pd.Series(~ctx.arr["nonposting"], index=ctx.D.index)
    gl = D["gl_account"]
    D["product_family"] = S["product_family"]
    D["customer_segment"] = S["customer_segment"]
    ch, ch_un = _map_token(S["channel"], {k: v for k, v in CHANNEL_MAP.items()})
    D["channel"] = ch
    ctx.add_map("channel", ctx.raw["channel"], ch, "Dir/direct -> Direct; Dist -> Distributor", "Applied")
    uom, uom_un = _map_token(S["uom"], UOM_MAP)
    D["uom"] = uom
    ctx.add_map("uom", ctx.raw["uom"], uom, "ea/Each -> EA; kg -> KG; NOS kept separate (not merged without confirmation)", "Applied")
    ic = S["intercompany"].str.lower().map(lambda v: "Y" if v in YES_TOKENS else ("N" if v in NO_TOKENS else ("" if v == "" else "?")))
    ac = S["accrual"].str.lower().map(lambda v: "Y" if v in YES_TOKENS else ("N" if v in NO_TOKENS else ("" if v == "" else "?")))
    D["intercompany"] = ic.where(ic != "?", "")
    D["accrual"] = ac.where(ac != "?", "")
    ctx.arr["ic_unmapped"] = ic.eq("?").to_numpy()
    ctx.arr["ac_unmapped"] = ac.eq("?").to_numpy()
    ctx.add_map("intercompany", ctx.raw["intercompany"], D["intercompany"], "Y/Yes/IC/1/TRUE/y -> Y ; N/No/0/FALSE/n -> N ; blank stays blank", "Applied")
    ctx.add_map("accrual", ctx.raw["accrual"], D["accrual"], "Y/Yes/1/Accrual -> Y ; N -> N ; blank stays blank", "Applied")
    el = S["elimination_status"].str.lower().map(ELIM_MAP).fillna("")
    D["elimination_status"] = el
    ctx.add_map("elimination_status", ctx.raw["elimination_status"], el, "N/A -> 'Not applicable'; blank stays blank", "Applied")
    ap = S["approval_status"].str.lower().map(APPROVAL_MAP).fillna("")
    D["approval_status"] = ap
    ctx.arr["approval_unmapped"] = (S["approval_status"].ne("") & ap.eq("")).to_numpy()
    ctx.add_map("approval_status", ctx.raw["approval_status"], ap, "pending -> Pending (case only)", "Applied")
    D["scenario_tag"] = S["scenario_tag"]
    # context checks (patterns observed in the data; flags only)
    ctx.arr["ic_blank_on_ic_gl"] = posting.to_numpy() & gl.eq("1500").to_numpy() & D["intercompany"].eq("").to_numpy()
    ctx.arr["ic_not_y_on_ic_gl"] = posting.to_numpy() & gl.eq("1500").to_numpy() & D["intercompany"].eq("N").to_numpy()
    ctx.arr["accrual_blank_on_accrual_gl"] = posting.to_numpy() & gl.eq("2200").to_numpy() & D["accrual"].eq("").to_numpy()
    ctx.arr["note_without_accrual"] = (S["notes"].isin(["accrual?", "do not reverse", "reverse next month"]) & D["accrual"].ne("Y")).to_numpy()
    # qty applicability
    qty = ctx.P["qty"]
    qgl = gl.isin(PRICE_IDENTITY_GLS).to_numpy() & posting.to_numpy()
    ctx.arr["qty_missing_on_qty_gl"] = qgl & (qty["status"] != "ok").to_numpy()
    ctx.arr["qty_negative"] = qgl & (qty["value"] < 0).fillna(False).to_numpy()
    ctx.arr["qty_zero"] = qgl & (qty["value"] == 0).fillna(False).to_numpy()
    ctx.arr["qty_on_other_gl"] = (~gl.isin(PRICE_IDENTITY_GLS).to_numpy()) & posting.to_numpy() & (qty["status"] == "ok").to_numpy()
    # revenue/COGS dimensions
    revcogs = D["account_group"].isin(["Revenue", "COGS"]).to_numpy() & posting.to_numpy()
    ctx.arr["dim_missing_revcogs"] = revcogs & (S["product_family"].eq("") | S["customer_segment"].eq("") | D["channel"].eq("")).to_numpy()
    ctx.arr["dim_on_non_revcogs"] = (~revcogs) & posting.to_numpy() & (S["product_family"].ne("") | S["customer_segment"].ne("") | D["channel"].ne("")).to_numpy()
    ctx.arr["hc_on_non_people"] = posting.to_numpy() & (ctx.P["hc"]["status"] == "ok").to_numpy() & ~D["account_group"].eq("People cost").to_numpy()
    ctx.arr["status_blank"] = D["approval_status"].eq("").to_numpy() & posting.to_numpy()
    ctx.arr["status_not_eligible"] = ~D["approval_status"].isin(list(ELIGIBLE_APPROVAL_STATUSES)).to_numpy()
    _c_pairs = (("channel", "channel"), ("uom", "uom"), ("intercompany", "intercompany"), ("accrual", "accrual"),
                ("elimination_status", "elimination_status"), ("approval_status", "approval_status"))
    _c_mat = np.column_stack([(D[c].to_numpy() != ctx.raw[r].to_numpy()) for c, r in _c_pairs])
    ctx.facts["category_cells_changed"] = int(_c_mat.sum())
    ctx.facts["category_rows_changed"] = int(_c_mat.any(axis=1).sum())
    ctx.log_rule("C01", "channel, uom, intercompany, accrual, elimination_status, approval_status",
                 int(_c_mat.any(axis=1).sum()),
                 "Category spellings standardised with explicit alias maps (see Mappings). Blank stays blank - no value is invented. "
                 "NOTE: 'changed' is measured against the RAW text, so it includes whitespace-only differences already counted in T01",
                 "Confirmed variants", "Applied", cells_processed=len(_c_pairs) * ctx.n, cells_changed=int(_c_mat.sum()))


# =============================================================================
# 10. DUPLICATES, OUTLIERS, FLAGS, EXCLUSION ACCOUNTING
# =============================================================================
def step_duplicates(ctx: Ctx) -> None:
    """Tier repeated document numbers. Nothing is deleted. A repeated document_no is NOT automatically a
    duplicate (R5). Rows that share a document_no AND the same GL account AND the same period, and whose
    comparable AMOUNT columns agree, are DUPLICATE CANDIDATES (never 'confirmed'): the match covers only the fields
    listed in the Duplicate_Review sheet (document_no, gl_account, period, entity compatibility and the five
    as-reported amount columns), NOT every column. They are split by sign:
      DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN     every comparable amount equal in value AND sign
      DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT equal in absolute value but >=1 amount has the opposite sign
                                              (could be a reversal / credit rather than a copy)."""
    D, S, P = ctx.D, ctx.S, ctx.P
    n = ctx.n
    posting = pd.Series(~ctx.arr["nonposting"], index=ctx.D.index)
    doc = S["document_no"].to_numpy()
    gl = D["gl_account"].to_numpy()
    ym = D["period_ym"].to_numpy()
    ent = D["entity_code"].to_numpy()
    junk = ctx.arr["junk_entity"]
    status = D["approval_status"].to_numpy()
    vals = {s: P[s]["value"].to_numpy() for s in ALL_AMT_SHORT}
    errs = {s: P[s]["abs_err"].to_numpy() for s in ALL_AMT_SHORT}
    n_ok = np.sum([np.isfinite(vals[s]) for s in ALL_AMT_SHORT], axis=0)
    decided = D["scale_decision"].isin(["UNDIVIDED", "DIVIDED_1E3", "DIVIDED_1E5"]).to_numpy()

    tier = np.full(n, "", dtype=object)
    role = np.full(n, "", dtype=object)
    gid = np.full(n, "", dtype=object)
    gsize = np.zeros(n, dtype=int)
    anc_of = np.full(n, -1, dtype=np.int64)
    ncmp = np.zeros(n, dtype=int)
    nagree = np.zeros(n, dtype=int)
    signdiff = np.zeros(n, dtype=int)
    tier[posting.to_numpy()] = "UNIQUE_DOCUMENT_NO"
    pos_idx = np.flatnonzero(posting.to_numpy())
    pf = pd.DataFrame({"pos": pos_idx, "doc": doc[pos_idx]})
    pf["size"] = pf.groupby("doc")["pos"].transform("size")
    multi = pf[pf["size"] >= 2].sort_values(["doc", "pos"])
    nonpost_docs = set(doc[ctx.arr["nonposting"]])
    shared_np = np.zeros(n, dtype=bool)
    shared_np[pos_idx] = pd.Series(doc[pos_idx]).isin(nonpost_docs).to_numpy()
    k = 0
    groups_info = []
    for dno, g in multi.groupby("doc", sort=True):
        ps = g["pos"].to_numpy()
        k += 1
        gname = f"DG{k:05d}"
        gid[ps] = gname
        gsize[ps] = len(ps)
        keys = [(gl[p], ym[p]) for p in ps]
        counts = {}
        for kk in keys:
            counts[kk] = counts.get(kk, 0) + 1
        main_key = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]
        line = [p for p, kk in zip(ps, keys) if kk == main_key]
        other = [p for p, kk in zip(ps, keys) if kk != main_key]
        for p in other:
            tier[p], role[p] = "SHARED_DOCUMENT_DIFFERENT_LINE", "OTHER_LINE"
        if len(line) < 2:
            for p in line:
                tier[p], role[p] = "SHARED_DOCUMENT_DIFFERENT_LINE", "OTHER_LINE"
            groups_info.append((gname, dno, len(ps), "no same-line partner"))
            continue
        real_ents = {ent[p] for p in line if ent[p] != "" and not junk[p]}
        if len(real_ents) > 1:
            for p in line:
                tier[p], role[p] = "SHARED_DOCUMENT_DIFFERENT_ENTITY", "OTHER_LINE"
            groups_info.append((gname, dno, len(ps), "different real entities"))
            continue
        line.sort(key=lambda p: (0 if status[p] == "Posted" else 1, 1 if junk[p] else 0,
                                 -int(n_ok[p]), 0 if decided[p] else 1, p))
        anchor = line[0]
        tier[anchor], role[anchor] = "GROUP_ANCHOR", "ANCHOR"
        info = "anchor + %d same-line row(s)" % (len(line) - 1)
        for p in line[1:]:
            c = a = sd = 0
            for s in ALL_AMT_SHORT:
                va, vb = vals[s][anchor], vals[s][p]
                if np.isfinite(va) and np.isfinite(vb):
                    c += 1
                    tol = errs[s][anchor] + errs[s][p] + 1e-9
                    if abs(abs(va) - abs(vb)) <= tol:
                        a += 1
                        if (va > 0) != (vb > 0) and va != 0 and vb != 0:
                            sd += 1
            ncmp[p], nagree[p], signdiff[p] = c, a, sd
            anc_of[p] = anchor
            if c >= 2 and a == c:
                tier[p] = "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN" if sd == 0 else "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT"
            elif a >= 1:
                tier[p] = "CANDIDATE_COPY_PARTIAL_AGREEMENT"
            elif c == 0:
                tier[p] = "CANDIDATE_COPY_NO_AMOUNT_EVIDENCE"
            else:
                tier[p] = "SAME_DOC_SAME_LINE_AMOUNTS_DIFFER"
            role[p] = "COPY"
        groups_info.append((gname, dno, len(ps), info))
    # --- evidence: how do the field-match rows differ in the fields that are NOT part of the comparison? ---
    nc_fields = [("extract_batch", S["extract_batch"].to_numpy()), ("posting_date", D["posting_date"].astype(str).to_numpy()),
                 ("approval_status", D["approval_status"].to_numpy()), ("line_text", S["line_text"].to_numpy()),
                 ("user_id", S["user_id"].to_numpy()), ("source_system", S["source_system"].to_numpy())]
    ev_rows = []
    for tname in ("DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN", "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT"):
        cp_idx = np.flatnonzero(tier == tname)
        row = {"tier": tname, "rows_vs_their_anchor": int(len(cp_idx))}
        for fname, arr in nc_fields:
            row[f"differs_in_{fname}"] = int((arr[cp_idx] != arr[anc_of[cp_idx]]).sum()) if len(cp_idx) else 0
        ev_rows.append(row)
    ctx.ev["dup_noncompared_diffs"] = pd.DataFrame(ev_rows)
    ctx.ev["dup_rule"] = pd.DataFrame([
        ("Scope", "POSTING rows only (the 350 non-posting rows are excluded). Rows are grouped by identical document_no."),
        ("Must be equal (otherwise tier = SHARED_DOCUMENT_DIFFERENT_LINE)", "gl_account and period_ym (the group's most frequent GL x period pair forms 'the same line')"),
        ("Entity rule", "At most one real entity_code among the same-line rows (junk / blank entities do not count); two different real entities -> SHARED_DOCUMENT_DIFFERENT_ENTITY"),
        ("Amount columns compared", "amount_local, actual_usd, budget_usd, forecast_usd, prior_year_usd - the AS-REPORTED parsed values (before any scale restoration)"),
        ("Amount tolerance", "|abs(a) - abs(b)| <= rounding(a) + rounding(b) + 1e-9, where rounding(x) = 0.5 x 10^-(decimal places written in the source text of x). A column is compared only if both values exist."),
        ("Minimum evidence", "at least 2 comparable amount columns, and ALL comparable columns must agree in absolute value -> candidate; 1 or more agree but not all -> CANDIDATE_COPY_PARTIAL_AGREEMENT"),
        ("Sign handling", "A column counts as a sign difference when both values are non-zero and have opposite signs. No sign difference -> DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN; >=1 -> DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT"),
        ("NOT compared (may differ between a candidate and its anchor)", "extract_batch, posting_date, approval_status, line_text, user_id, source_system, cost centre, product / segment / channel, qty, headcount, notes, scenario_tag. See the second table for how often they differ."),
        ("Anchor selection", "Within a group the kept anchor is the row with status 'Posted' first, then non-junk entity, then most amounts present, then a decided scale, then file order"),
        ("Removal", "NONE. No row is removed or excluded for being a duplicate candidate (rule R11 unresolved). REMOVE_FIELD_MATCH_DUPLICATES = False; if switched on it would affect SAME_SIGN candidates only."),
    ], columns=["item", "definition"])
    D["doc_group_id"] = gid
    D["doc_group_size"] = gsize
    D["dup_tier"] = tier
    D["dup_role"] = role
    D["dup_cols_compared"] = ncmp
    D["dup_cols_agree"] = nagree
    D["dup_sign_diff_cols"] = signdiff
    ctx.arr["doc_repeated"] = (gsize >= 2)
    ctx.arr["dup_fm_same_sign"] = (tier == "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN")
    ctx.arr["dup_fm_sign_conflict"] = (tier == "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT")
    ctx.arr["dup_candidate"] = np.isin(tier, ["CANDIDATE_COPY_PARTIAL_AGREEMENT", "CANDIDATE_COPY_NO_AMOUNT_EVIDENCE",
                                              "SAME_DOC_SAME_LINE_AMOUNTS_DIFFER"])
    ctx.arr["dup_anchor"] = (tier == "GROUP_ANCHOR")
    ctx.arr["doc_shared_nonposting"] = shared_np
    # non-posting rows whose document_no also appears on a posting row
    npdoc = pd.Series(doc[ctx.arr["nonposting"]])
    ctx.facts["nonposting_docs_shared_with_posting"] = int(npdoc.isin(set(doc[pos_idx])).sum())
    ctx.facts["doc_groups"] = k
    ctx.facts["doc_groups_rows"] = int((gsize >= 2).sum())
    summ = (pd.DataFrame({"tier": tier[posting.to_numpy()]}).groupby("tier").size().reset_index(name="rows"))
    ctx.ev["dup_tier_summary"] = summ.sort_values("rows", ascending=False)
    gi = pd.DataFrame(groups_info, columns=["doc_group_id", "document_no", "rows", "result"])
    ctx.ev["dup_groups"] = gi
    ctx.log_rule("D01", "document_no", int((gsize >= 2).sum()),
                 "Repeated document_no among POSTING rows tiered (anchor / field-match candidate same sign / field-match candidate sign conflict / partial candidate / shared document, different line). "
                 "Field-match candidate = same document_no, GL, period, compatible entity and every comparable AMOUNT column equal within rounding (fields and tolerances in Duplicate_Review); "
                 "NOT every column is compared. Sign conflict = equal in absolute value but >=1 amount has the opposite sign. "
                 "NO row is removed (rule R11 is unresolved); switch REMOVE_FIELD_MATCH_DUPLICATES adds exclusion step 9",
                 "Candidates only (amount-field match, not a full-row match); sign-conflict candidates may be reversals; removal rule Unresolved", "Flag only")


def step_outliers(ctx: Ctx) -> None:
    D = ctx.D
    posting = pd.Series(~ctx.arr["nonposting"], index=ctx.D.index)
    adj = D["actual_usd_adj"].to_numpy()
    ok = posting.to_numpy() & np.isfinite(adj) & (adj != 0) & ~ctx.arr["junk_entity"] & D["gl_account"].ne("").to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        lm = np.where(ok, np.log10(np.abs(adj)), np.nan)
    f = pd.DataFrame({"gl": D["gl_account"], "ent": D["entity_code"], "lm": lm})
    ff = f[ok]
    st = ff.groupby(["gl", "ent"])["lm"].agg(med="median", mad=lambda x: float((x - x.median()).abs().median()), n="count")
    keys = pd.MultiIndex.from_arrays([f["gl"], f["ent"]])
    a = st.reindex(keys)
    use = a["n"].to_numpy() >= BASELINE_MIN_GROUP
    sd = np.maximum(1.4826 * a["mad"].to_numpy(), 0.2)
    z = np.where(use, (lm - a["med"].to_numpy()) / sd, np.nan)
    D["magnitude_robust_z"] = np.where(np.isfinite(z), np.round(z, 3), np.nan)
    ctx.arr["outlier"] = ok & np.isfinite(z) & (np.abs(z) > OUTLIER_Z)
    ctx.log_rule("O01", "actual_usd_adj", int(ctx.arr["outlier"].sum()),
                 f"Extreme magnitude vs peers (|robust z| > {OUTLIER_Z} on log10 |actual| within GL x entity). Heavy tails are natural "
                 "in this data (see Scale_Evidence); this is information only",
                 "Legitimate extreme values unless proven otherwise", "Flag only")


FLAG_DEFS: List[Tuple[str, str, str]] = [
    # (flag name, ctx.arr key, finding class)
    ("flag_nonposting", "nonposting", "structural"),
    ("flag_nonposting_label_only", "nonposting_label_only", "suspected"),
    ("flag_junk_entity", "junk_entity", "structural"),
    ("flag_entity_unresolved", "entity_unresolved", "missing"),
    ("flag_entity_resolved_by_name", "entity_by_name", "assumption"),
    ("flag_entity_name_code_conflict", "entity_name_code_conflict", "suspected"),
    ("flag_country_entity_mismatch", "country_mismatch", "suspected"),
    ("flag_currency_entity_mismatch", "currency_mismatch", "suspected"),
    ("flag_gl_filled", "gl_filled", "assumption"),
    ("flag_gl_unresolved", "gl_unresolved", "missing"),
    ("flag_gl_invalid", "gl_invalid", "error"),
    ("flag_fs_line_filled", "fs_filled", "assumption"),
    ("flag_statement_gl_conflict", "stmt_conflict", "suspected"),
    ("flag_statement_unmapped", "stmt_unmapped", "error"),
    ("flag_region_filled", "region_filled", "assumption"),
    ("flag_cost_center_missing", "cc_missing", "missing"),
    ("flag_division_unmapped", "division_unmapped", "error"),
    ("flag_cost_nature_gl_conflict", "nature_conflict", "suspected"),
    ("flag_cost_nature_missing", "nature_missing", "missing"),
    ("flag_fiscal_year_filled", "fy_filled", "assumption"),
    ("flag_fiscal_year_conflict", "fy_conflict", "error"),
    ("flag_period_unparsed", "period_unparsed", "error"),
    ("flag_posting_date_missing", "pd_blank", "missing"),
    ("flag_posting_date_resolved_by_period", "pd_slash_resolved", "assumption"),
    ("flag_posting_date_unresolved", "pd_unresolved", "error"),
    ("flag_posting_date_period_mismatch", "pd_mismatch", "suspected"),
    ("flag_batch_year_inferred", "batch_inferred", "assumption"),
    ("flag_batch_year_conflict", "batch_conflict", "suspected"),
    ("flag_batch_bad_format", "batch_badformat", "error"),
    ("flag_scale_label_contradicted", "scale_contradicted", "error"),
    ("flag_scale_restored", "scale_restored", "assumption"),
    ("flag_scale_undetermined", "scale_undetermined", "unresolved"),
    ("flag_low_magnitude_tail", "low_tail", "suspected"),
    ("flag_fx_zero", "fx_zero", "error"),
    ("flag_fx_missing", "fx_missing", "missing"),
    ("flag_fx_one_nonusd", "fx_one_nonusd", "suspected"),
    ("flag_fx_usd_rate_not_one", "fx_usd_not_one", "suspected"),
    ("flag_fx_no_match", "fx_no_match", "suspected"),
    ("flag_usd_row_local_neq_usd", "usd_local_neq", "suspected"),
    ("flag_sign_single_column_flip", "sign_single_flip", "suspected"),
    ("flag_sign_all_negative", "sign_all_neg", "legitimate"),
    ("flag_local_usd_sign_conflict", "local_usd_sign_conflict", "suspected"),
    ("flag_doc_repeated", "doc_repeated", "info"),
    ("flag_dup_field_match_same_sign", "dup_fm_same_sign", "suspected"),
    ("flag_dup_field_match_sign_conflict", "dup_fm_sign_conflict", "suspected"),
    ("flag_dup_candidate", "dup_candidate", "suspected"),
    ("flag_dup_group_anchor", "dup_anchor", "info"),
    ("flag_doc_shared_with_nonposting", "doc_shared_nonposting", "info"),
    ("flag_magnitude_outlier", "outlier", "legitimate"),
    ("flag_qty_missing_on_qty_gl", "qty_missing_on_qty_gl", "missing"),
    ("flag_qty_negative", "qty_negative", "suspected"),
    ("flag_qty_zero", "qty_zero", "suspected"),
    ("flag_qty_on_other_gl", "qty_on_other_gl", "suspected"),
    ("flag_dimension_missing_rev_cogs", "dim_missing_revcogs", "missing"),
    ("flag_dimension_on_non_rev_cogs", "dim_on_non_revcogs", "suspected"),
    ("flag_headcount_on_non_people_gl", "hc_on_non_people", "suspected"),
    ("flag_ic_blank_on_gl1500", "ic_blank_on_ic_gl", "missing"),
    ("flag_ic_not_y_on_gl1500", "ic_not_y_on_ic_gl", "suspected"),
    ("flag_accrual_blank_on_gl2200", "accrual_blank_on_accrual_gl", "missing"),
    ("flag_note_without_accrual_y", "note_without_accrual", "suspected"),
    ("flag_status_blank", "status_blank", "missing"),
    ("flag_status_not_eligible", "status_not_eligible", "info"),
    ("flag_intercompany_unmapped", "ic_unmapped", "error"),
    ("flag_accrual_unmapped", "ac_unmapped", "error"),
    ("flag_approval_unmapped", "approval_unmapped", "error"),
]


def build_flags(ctx: Ctx) -> None:
    D = ctx.D
    ctx.arr["period_unparsed"] = ~ctx.arr["period_ok"]
    posting = pd.Series(~ctx.arr["nonposting"], index=ctx.D.index)
    for col, short in zip(["amount_local", "actual_usd", "budget_usd", "forecast_usd", "prior_year_usd"], ALL_AMT_SHORT):
        miss = posting.to_numpy() & (ctx.P[short]["status"] != "ok").to_numpy()
        D[f"flag_{col}_missing"] = miss.astype(np.int8)
    usd_ok = np.column_stack([(ctx.P[s]["status"] == "ok").to_numpy() for s in USD_SHORT])
    D["flag_any_usd_missing"] = (posting.to_numpy() & ~usd_ok.all(axis=1)).astype(np.int8)
    D["flag_all_usd_missing"] = (posting.to_numpy() & ~usd_ok.any(axis=1)).astype(np.int8)
    for name, key, _cls in FLAG_DEFS:
        if key not in ctx.arr:
            raise PipelineError(f"internal error: flag source '{key}' missing")
        D[name] = np.asarray(ctx.arr[key], dtype=bool).astype(np.int8)
    flag_cols = [c for c in D.columns if c.startswith("flag_")]
    s = pd.Series("", index=D.index, dtype=object)
    for c in flag_cols:
        s = s + np.where(D[c].to_numpy() == 1, c[5:] + "|", "")
    D["flags"] = s.str.rstrip("|")
    D["n_flags"] = D[flag_cols].sum(axis=1).astype(int)
    ctx.facts["flag_cols"] = flag_cols


EXCL_SCOPES = [
    ("PL_actual", "P&L", ["actual_usd"]),
    ("PL_variance", "P&L", ["actual_usd", "budget_usd"]),
    ("BS_actual", "Balance Sheet", ["actual_usd"]),
]


def assign_exclusions(ctx: Ctx) -> None:
    """One primary exclusion reason per row and scope - first failing step in the
    fixed precedence of docs/FINANCIAL_METRICS.md section 4."""
    D = ctx.D
    n = ctx.n
    for scope, stmt, cols in EXCL_SCOPES:
        reason = np.full(n, EXCL_ELIGIBLE, dtype=object)
        done = np.zeros(n, dtype=bool)

        def take(mask, label):
            m = np.asarray(mask, dtype=bool) & ~done
            reason[m] = label
            done[m] = True

        take(ctx.arr["nonposting"], EXCL_REASONS[0])
        take(ctx.arr["junk_entity"], EXCL_REASONS[1])
        take(ctx.arr["entity_unresolved"], EXCL_REASONS[2])
        take(D["statement"].to_numpy() != stmt, EXCL_REASONS[3])
        take(ctx.arr["status_not_eligible"], EXCL_REASONS[4])
        take(~ctx.arr["period_ok"], EXCL_REASONS[5])
        miss = np.zeros(n, dtype=bool)
        for c in cols:
            miss |= (ctx.P[c]["status"] != "ok").to_numpy()
        take(miss, EXCL_REASONS[6])
        take(ctx.arr["scale_undetermined"], EXCL_REASONS[7])
        if REMOVE_FIELD_MATCH_DUPLICATES:
            take(ctx.arr["dup_fm_same_sign"], EXCL_REASONS[8])
        D[f"excl_{scope}"] = reason
        D[f"eligible_{scope}"] = (reason == EXCL_ELIGIBLE).astype(np.int8)
        ctx.facts[f"excl_counts_{scope}"] = pd.Series(reason).value_counts().to_dict()
    ctx.log_rule("X01", "excl_* columns", ctx.n,
                 "Every row receives exactly one primary exclusion reason (or ELIGIBLE) per scope, first failing step of the "
                 "fixed precedence (non-posting, junk entity, entity unresolvable, wrong statement, status not eligible, period, "
                 "amount missing, scale undecidable, duplicate-removed). Secondary issues stay as flags",
                 "Proposed - Needs Validation (Phase-1 doc R14)", "Applied (flags only; no row deleted)")


def clean_dataset(raw: pd.DataFrame) -> Ctx:
    import warnings
    warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
    raw = raw.reset_index(drop=True)
    ctx = Ctx(raw)
    with StepTimer("text normalisation"):
        step_text(ctx)
    with StepTimer("non-posting rows"):
        step_nonposting(ctx)
    with StepTimer("entities"):
        step_entities(ctx)
    with StepTimer("master data (GL, names, division, cost centre, region)"):
        step_master(ctx)
    with StepTimer("periods and dates"):
        step_periods_dates(ctx)
    with StepTimer("amount parsing"):
        step_amounts(ctx)
    with StepTimer("scale decision"):
        step_scale(ctx)
    with StepTimer("FX and signs"):
        step_fx_sign(ctx)
    with StepTimer("other columns"):
        step_other_columns(ctx)
    with StepTimer("duplicate tiers"):
        step_duplicates(ctx)
    with StepTimer("magnitude outliers"):
        step_outliers(ctx)
    with StepTimer("flags"):
        build_flags(ctx)
    with StepTimer("exclusion accounting"):
        assign_exclusions(ctx)
    ctx.D = ctx.D.copy()
    return ctx


# =============================================================================
# 11. REPORT TABLES (findings, exclusion summary, profiles, validation)
# =============================================================================
RAW_TO_CLEAN = {
    "row_id": "row_id", "source_system": "source_system", "extract_batch": "extract_batch",
    "fiscal_year": "fiscal_year", "fiscal_period": "period_ym", "legal_entity": "legal_entity",
    "entity_code": "entity_code", "division": "division", "country": "country", "region": "region",
    "cost_center_code": "cost_center_code", "cost_center_name": "cost_center_name",
    "cost_center_owner": "cost_center_owner", "gl_account": "gl_account", "account_name": "account_name",
    "account_group": "account_group", "fs_line": "fs_line", "statement": "statement",
    "cost_nature": "cost_nature", "product_family": "product_family", "customer_segment": "customer_segment",
    "channel": "channel", "currency": "currency", "amount_local_raw": "amount_local_parsed",
    "fx_rate_raw": "fx_rate", "actual_usd_raw": "actual_usd_parsed", "budget_usd_raw": "budget_usd_parsed",
    "forecast_usd_raw": "forecast_usd_parsed", "prior_year_usd_raw": "prior_year_usd_parsed",
    "qty_raw": "qty", "uom": "uom", "headcount_fte_raw": "headcount_fte", "document_no": "document_no",
    "posting_date": "posting_date", "user_id": "user_id", "line_text": "line_text",
    "intercompany": "intercompany", "accrual": "accrual", "elimination_status": "elimination_status",
    "report_scale": "report_scale_label", "scenario_tag": "scenario_tag",
    "approval_status": "approval_status", "notes": "notes",
}


def _abs_actual(ctx: Ctx) -> np.ndarray:
    D = ctx.D
    adj = D["actual_usd_adj"].to_numpy(dtype=float)
    par = D["actual_usd_parsed"].to_numpy(dtype=float)
    v = np.where(np.isfinite(adj), adj, par)
    return np.where(np.isfinite(v), np.abs(v), 0.0)


def build_column_profile(ctx: Ctx, raw_profile: pd.DataFrame) -> pd.DataFrame:
    D = ctx.D
    rows = []
    for _, r in raw_profile.iterrows():
        col = r["column"]
        cc = RAW_TO_CLEAN[col]
        s = D[cc]
        if s.dtype == object or str(s.dtype).startswith("str"):
            blank = int(s.astype(object).fillna("").astype(str).str.strip().eq("").sum())
            distinct = int(s[s.astype(object).fillna("").astype(str).str.strip() != ""].nunique())
            kind = "text"
        else:
            blank = int(s.isna().sum())
            distinct = int(s.nunique())
            kind = str(s.dtype)
        d = r.to_dict()
        _t = ctx.raw[col].str.strip()
        _miss = (_t.eq("") | _t.str.upper().isin(PLACEHOLDER_UPPER) | _t.str.fullmatch(r"-+").fillna(False)).to_numpy()
        _np = ctx.arr["nonposting"]
        d.update({"raw_missing_all_rows": int(_miss.sum()), "raw_missing_nonposting_rows": int((_miss & _np).sum()),
                  "raw_missing_posting_rows": int((_miss & ~_np).sum())})
        d.update({"cleaned_column": cc, "cleaned_type": kind, "cleaned_missing_count": blank,
                  "cleaned_missing_pct": round(pct(blank, ctx.n), 3), "cleaned_distinct": distinct})
        rows.append(d)
    out = pd.DataFrame(rows)
    out = out.rename(columns={"column": "raw_column", "blank_count": "raw_blank_count", "blank_pct": "raw_blank_pct",
                              "placeholder_count": "raw_placeholder_count", "placeholder_pct": "raw_placeholder_pct",
                              "distinct_raw": "raw_distinct"})
    return out[["raw_column", "cleaned_column", "cleaned_type", "raw_blank_count", "raw_blank_pct",
                "raw_placeholder_count", "raw_placeholder_pct", "raw_missing_all_rows", "raw_missing_posting_rows",
                "raw_missing_nonposting_rows", "cleaned_missing_count", "cleaned_missing_pct",
                "raw_distinct", "distinct_after_trim_case", "cleaned_distinct",
                "leading_trailing_space_cells", "inner_multi_space_cells", "tab_cr_lf_cells",
                "non_ascii_cells", "other_control_char_cells", "max_length", "sample_values"]]


def build_exclusion_summary(ctx: Ctx) -> Tuple[pd.DataFrame, pd.DataFrame]:
    D = ctx.D
    absamt = pd.Series(_abs_actual(ctx), index=D.index)
    # STRICT: only the validated adjusted value counts (blank/undetermined = 0).
    adj_abs = pd.Series(np.abs(np.nan_to_num(D["actual_usd_adj"].to_numpy(dtype=float))), index=D.index)
    # AS REPORTED: the parsed source value, scale NOT validated (this is what an undetermined row carried in the source).
    par_abs = pd.Series(np.abs(np.nan_to_num(D["actual_usd_parsed"].to_numpy(dtype=float))), index=D.index)
    rows, detail = [], []
    for scope, stmt, cols in EXCL_SCOPES:
        col = f"excl_{scope}"
        order = [EXCL_ELIGIBLE] + EXCL_REASONS
        g = pd.DataFrame({"r": D[col], "a": adj_abs, "p": par_abs}).groupby("r").agg(
            rows=("a", "size"), abs_actual=("a", "sum"), abs_parsed=("p", "sum"))
        tot = 0
        for i, rs in enumerate(order):
            n = int(g["rows"].get(rs, 0))
            tot += n
            rows.append({"scope": scope, "statement_in_scope": stmt, "amount_columns_required": "+".join(cols),
                         "step": i, "primary_reason": rs, "rows": n,
                         "share_of_all_rows_%": round(pct(n, ctx.n), 3),
                         "sum_abs_actual_usd_adj": round(float(g["abs_actual"].get(rs, 0.0)), 2),
                         "sum_abs_actual_usd_parsed_as_reported": round(float(g["abs_parsed"].get(rs, 0.0)), 2)})
        rows.append({"scope": scope, "statement_in_scope": stmt, "amount_columns_required": "+".join(cols),
                     "step": 99, "primary_reason": "TOTAL (must equal all raw rows)", "rows": tot,
                     "share_of_all_rows_%": round(pct(tot, ctx.n), 3), "sum_abs_actual_usd_adj": np.nan,
                     "sum_abs_actual_usd_parsed_as_reported": np.nan})
        st5 = D.loc[D[col] == EXCL_REASONS[4], "approval_status"].replace("", "(blank)").value_counts()
        for k, v in st5.items():
            detail.append({"scope": scope, "detail": "step 5 split by approval_status", "value": k, "rows": int(v)})
        el = D[col] == EXCL_ELIGIBLE
        for nm, mask in (("eligible AND duplicate candidate, field match, same sign (possible double count)", el & (D["dup_tier"] == "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN")),
                         ("eligible AND duplicate candidate, field match, SIGN CONFLICT (possible reversal)", el & (D["dup_tier"] == "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT")),
                         ("eligible AND duplicate candidate", el & (D["flag_dup_candidate"] == 1)),
                         ("eligible AND scale restored", el & (D["flag_scale_restored"] == 1)),
                         ("eligible AND sign single-column flip", el & (D["flag_sign_single_column_flip"] == 1)),
                         ("eligible AND fx zero / fx 1.0 on non-USD", el & ((D["flag_fx_zero"] == 1) | (D["flag_fx_one_nonusd"] == 1)))):
            detail.append({"scope": scope, "detail": nm, "value": f"abs actual USD {absamt[mask].sum():,.2f}", "rows": int(mask.sum())})
    return pd.DataFrame(rows), pd.DataFrame(detail)


def build_flag_counts(ctx: Ctx) -> pd.DataFrame:
    D = ctx.D
    reasons = [EXCL_ELIGIBLE] + EXCL_REASONS
    cls = {n: c for n, _k, c in FLAG_DEFS}
    out = []
    for c in ctx.facts["flag_cols"]:
        row = {"flag": c, "class": cls.get(c, "missing"), "rows_all": int(D[c].sum())}
        for rs in reasons:
            row[f"PL_actual: {rs}"] = int(D.loc[D["excl_PL_actual"] == rs, c].sum())
        out.append(row)
    return pd.DataFrame(out).sort_values("rows_all", ascending=False)


def build_findings(ctx: Ctx) -> pd.DataFrame:
    """Ranked data-quality findings. impact_usd = USD at stake, defined per finding
    (see impact_basis). It is exposure/at-stake, NOT a booked error amount."""
    D = ctx.D
    post = D["is_posting_row"].to_numpy() == 1
    absamt = _abs_actual(ctx)
    adj = D["actual_usd_adj"].to_numpy(dtype=float)
    par = D["actual_usd_parsed"].to_numpy(dtype=float)
    class _FM(np.ndarray):
        """bool mask that remembers the single flag column it came from (lost after any combination)."""
        def __array_finalize__(self, obj):
            self.flag = None

    def f(c):
        m = (D[c].to_numpy() == 1).view(_FM)
        m.flag = c
        return m
    el = D["eligible_PL_actual"].to_numpy() == 1
    items = []

    def _tier(cat):
        c = cat.lower()
        if c.startswith("confirmed") or c.startswith("strongly supported"):
            return 1
        if c.startswith("probable") or c.startswith("suspected"):
            return 2
        if c.startswith("unresolved") or (c.startswith("missing information") and "recovered" not in c):
            return 3
        return 4

    def add(fid, title, cat, mask, impact, basis, action, detail="", flag=None):
        flag = flag or getattr(mask, "flag", None)
        mask = np.asarray(mask, dtype=bool)
        if not (mask & ~post).any():
            rb = "posting rows only"
        elif not (mask & post).any():
            rb = "non-posting rows only"
        else:
            rb = "all rows"
        items.append({"finding_id": fid, "finding": title, "classification": cat, "priority_tier": _tier(cat), "rows": int(mask.sum()),
                      "pct_of_rows": round(pct(mask.sum(), ctx.n), 3), "row_basis": rb, "source_flag": flag or "",
                      "impact_usd": round(float(impact), 2),
                      "impact_basis": basis, "treatment_in_output": action, "detail": detail})

    rest = f("flag_scale_restored")
    delta = np.where(rest & np.isfinite(adj) & np.isfinite(par), np.abs(adj) - np.abs(par), 0.0)
    hi = rest & (D["scale_confidence"].to_numpy() == "HIGH")
    me = rest & (D["scale_confidence"].to_numpy() == "MEDIUM")
    n1e3 = int((hi & (D["scale_decision"].to_numpy() == "DIVIDED_1E3")).sum())
    n1e5 = int((hi & (D["scale_decision"].to_numpy() == "DIVIDED_1E5")).sum())
    add("F01a", "report_scale: rows restored (x1,000 / x100,000) on the PRICE-IDENTITY test (GL 4100/5100) - HIGH confidence",
        "Strongly supported (inferred consistency test)", hi, delta[hi].sum(),
        "understatement of |actual_usd| if the as-reported value were used",
        "Restored per row; as-reported kept in *_parsed. List prices were inferred from this dataset (no independent price list), so this is a consistency test, not proof",
        f"|actual_usd| = |qty| x list price holds at ratio 1/1,000 on {n1e3:,} Thousands rows and 1/100,000 on {n1e5:,} Lakhs rows; no row fell between the clusters.")
    add("F01b", "report_scale: rows restored on the PEER Z-SCORE rule (no price identity available) - MEDIUM confidence",
        "Probable (statistical peer test)", me, delta[me].sum(),
        "understatement of |actual_usd| if the as-reported value were used",
        "Restored per row (z <= -5 vs GL x entity peers); as-reported kept in *_parsed. Not a confirmed error",
        f"Validated only on identity rows ({ctx.facts.get('z_rule_identity_rows_tested', 'n/a')} tested, {ctx.facts.get('z_rule_wrong_on_identity_rows', 'n/a')} confidently wrong). "
        f"Expected wrong restorations about {ctx.facts.get('actual_tail_rate_other_gl', 0) * int(((D['report_scale_label'] == 'Thousands') & (D['scale_decision'] == 'UNDIVIDED')).sum()):.1f} rows.")
    lab_con = f("flag_scale_label_contradicted")
    add("F02", "report_scale label contradicts the evidence ('000s' / 'In thousands' never divided; some 'Thousands' not divided)",
        "Strongly supported (label unreliable; proven on identity-tested rows)", lab_con, 0.0, "hypothetical: applying the label would overstate by up to 999x - not in this total",
        "Label ignored; decision per row; flag kept",
        "Multiplying 000s/In thousands rows by 1,000 would overstate them 1,000-fold.")
    und = f("flag_scale_undetermined")
    add("F03", "Scale undetermined (peer z-score between bands, or no USD magnitude)", "Unresolved issue", und,
        np.abs(np.nan_to_num(par))[und].sum(), "|actual_usd| AS REPORTED (unvalidated; no adjusted value exists for these rows)",
        "Not restored (actual_usd_adj blank); excluded at step 8; listed in Exceptions", "")
    dup = f("flag_dup_field_match_same_sign")
    add("F04a", "Repeated document_no: duplicate CANDIDATES - field match, same sign (same document_no, GL, period and every comparable amount column equal incl. sign; other columns may differ)",
        "Suspected anomaly (strong evidence)",
        dup, absamt[dup].sum(), "|actual_usd| of the non-anchor copies (would double count if both are summed)",
        "Flagged (anchor / copy). NOT removed - duplicate rule R11 is unresolved",
        "Match covers document_no, GL, period, entity compatibility and the five amount columns only; the candidates also differ in batch, posting date, approval status or line_text (counts in Duplicate_Review). Rule and tolerances: Duplicate_Review.")
    dsc = f("flag_dup_field_match_sign_conflict")
    add("F04b", "Repeated document_no: duplicate CANDIDATES - field match, SIGN CONFLICT (equal in absolute value, >=1 amount has the opposite sign)",
        "Suspected anomaly (possible reversal, not proven duplicate)",
        dsc, absamt[dsc].sum(), "|actual_usd| of the non-anchor rows (double count only if they are true duplicates)",
        "Flagged. NOT removed and never auto-removed (could be a reversal / credit)",
        "Previously reported together with the same-sign candidates; split because an opposite sign is not a duplicate on its face.")
    dc = f("flag_dup_candidate")
    add("F05", "Repeated document_no: candidate copies with only partial amount agreement", "Suspected anomaly", dc, absamt[dc].sum(),
        "|actual_usd| of the candidate rows", "Flagged for review", "")
    sf = f("flag_sign_single_column_flip")
    flip_act = sf & (D["sign_flip_column"].to_numpy() == "actual_usd")
    add("F06", "Sign: exactly one amount column has the opposite sign of the other >=3 columns", "Suspected anomaly",
        sf, 2 * absamt[flip_act].sum(), "net swing (2 x |actual|) where the flipped column IS actual_usd; other columns affect budget/forecast/prior/local only",
        "Flagged with the column name; values NOT changed (account sign convention R9 unresolved)",
        f"Flipped column counts: {D.loc[sf, 'sign_flip_column'].value_counts().to_dict()}")
    lc = f("flag_local_usd_sign_conflict")
    add("F07", "Local amount and actual USD have opposite signs", "Suspected anomaly", lc, 0.0,
        "no USD effect by itself (overlaps F06)", "Flagged", "A currency conversion cannot change the sign.")
    nm = f("flag_fx_no_match")
    add("F08", "FX: USD amount does not equal local / rate (every one of these rows carries rate exactly 1.0 on a non-USD currency)",
        "Confirmed anomaly", nm, absamt[nm].sum(), "|actual_usd| of rows where USD cannot be reconciled to local",
        "Flagged; actual_usd NOT replaced by a recomputed value",
        f"Rows with rate 1.0 on a non-USD row: {int(f('flag_fx_one_nonusd').sum()):,}; of these {int(nm.sum()):,} fail reconciliation.")
    one = f("flag_fx_one_nonusd") & ~nm
    add("F09", "FX rate exactly 1.0 on a non-USD row but not testable (other amount missing)", "Suspected anomaly", one,
        absamt[one].sum(), "|actual_usd| of the affected rows", "Flagged", "")
    z0 = f("flag_fx_zero")
    add("F10", "FX rate = 0 (invalid rate)", "Confirmed error", z0, absamt[z0].sum(),
        "|actual_usd| of rows whose conversion cannot be verified", "Flagged; never used to convert", "")
    fm = f("flag_fx_missing")
    add("F11", "FX rate missing (NA / '-' / blank) (POSTING rows)", "Missing information", fm, absamt[fm].sum(),
        "|actual_usd| of rows whose conversion cannot be verified", "Flagged",
        "Counts posting rows only. Column_Profile counts all rows including the 350 non-posting rows; see Count_Reconciliation.")
    un = f("flag_usd_row_local_neq_usd")
    loc = D["amount_local_adj"].to_numpy(dtype=float)
    gap = np.where(un & np.isfinite(loc) & np.isfinite(adj), np.abs(np.abs(loc) - np.abs(adj)), 0.0)
    _fp = ctx.facts["fx_pop"]
    add("F12", "AMOUNT test: USD-currency rows where |local amount| differs from |actual USD| beyond rounding",
        "Suspected anomaly", un, gap.sum(), "sum of | |local| - |actual_usd| | on those rows",
        "Flagged; reported actual_usd kept",
        f"Population = USD posting rows with both amounts present ({_fp['both_amounts']:,}); {_fp['amt_differ']:,} differ. A USD->USD conversion should leave the amount unchanged. "
        "Different test from F12b (rate); see the USD population table in FX_Evidence.")
    ur = f("flag_fx_usd_rate_not_one")
    add("F12b", "RATE test: USD-currency rows whose usable FX rate lies outside 1.000 +/- 0.001",
        "Suspected anomaly", ur, absamt[ur].sum(), "|actual_usd| of affected rows",
        "Flagged; rate and amounts kept",
        f"Of {_fp['rate_usable']:,} USD posting rows with a usable rate, {_fp['rate_outside']:,} lie outside the tolerance and {_fp['rate_within']:,} inside; "
        f"no USD row carries exactly 1.0 ({_fp['rate_exactly_one']}). Rates span about 0.97-1.03. {_fp['overlap']:,} of these rows are also in F12.")
    jk = f("flag_junk_entity")
    add("F13", "Junk entities ('TEST ENTITY', 'Do not use', 'xxx', codes 99 / T999)", "Confirmed (TEST ENTITY) / Proposed (others)", jk,
        absamt[jk].sum(), "|actual_usd| of junk-entity rows", "Excluded at step 2 (kept in file)",
        f"By name {ctx.facts['junk_by_name_n']}, by code {ctx.facts['junk_by_code_n']}, union {ctx.facts['junk_total_n']}.")
    eu = f("flag_entity_unresolved")
    add("F14", "Entity cannot be resolved (blank code and blank name)", "Missing information", eu, absamt[eu].sum(),
        "|actual_usd| of these rows", "Excluded at step 3", "Country/currency present but not used to infer the entity.")
    npst = f("flag_nonposting")
    add("F15", "Non-posting rows (TOTAL / Subtotal / CHECK) mixed with postings", "Confirmed error (structure)", npst,
        np.abs(np.nan_to_num(D.loc[npst, "actual_usd_parsed"].to_numpy(dtype=float))).sum(),
        "|actual_usd| as reported on the 350 total rows (would double count)", "Excluded at step 1 (kept in file)",
        f"Their document numbers also appear on {ctx.facts['nonposting_docs_shared_with_posting']} posting rows (naive de-duplication by document_no would delete real postings).")
    am = f("flag_actual_usd_missing")
    bud = np.abs(np.nan_to_num(D["budget_usd_adj"].to_numpy(dtype=float)))
    add("F16", "actual_usd is a placeholder or blank (###, #N/A, NA, N/A, null, '-') (POSTING rows)", "Missing information", am, bud[am].sum(),
        "PROXY: |budget_usd| on the same rows (size of what is not reported)", "NaN, never zero; excluded at step 7",
        "Counts posting rows only. Column_Profile counts all rows including the 350 non-posting rows; see Count_Reconciliation.")
    for fid, col, nm_ in (("F17", "flag_budget_usd_missing", "budget_usd"), ("F18", "flag_forecast_usd_missing", "forecast_usd"),
                          ("F19", "flag_prior_year_usd_missing", "prior_year_usd"), ("F20", "flag_amount_local_missing", "amount_local")):
        m_ = f(col)
        add(fid, f"{nm_} is a placeholder or blank (POSTING rows)", "Missing information", m_, absamt[m_].sum(),
            "|actual_usd| of affected rows (variance/forecast metrics lose these rows)", "NaN, never zero",
            "Counts posting rows only. Column_Profile counts all rows including the 350 non-posting rows; see Count_Reconciliation.")
    lt = f("flag_low_magnitude_tail")
    add("F21", "Rows decided UNDIVIDED but with extremely low magnitude vs peers (z <= -5): possible hidden division", "Suspected anomaly",
        lt, absamt[lt].sum(), "|actual_usd| of these rows (understated up to 1,000x if actually divided)",
        "Kept undivided (identity/label evidence); flagged for review",
        "Natural left tail of Actual-labelled rows is ~0.2-0.4% at this level, so most are expected to be genuine small values.")
    ou = f("flag_magnitude_outlier")
    add("F22", "Extreme magnitude vs GL x entity peers (|robust z| > %.0f)" % OUTLIER_Z, "Legitimate extreme value (unless proven otherwise)",
        ou, absamt[ou].sum(), "|actual_usd| of these rows", "Flag only", "")
    cn = f("flag_cost_nature_gl_conflict")
    add("F23", "cost_nature differs from the dominant nature of its GL (F/V flips)", "Suspected anomaly", cn, absamt[cn].sum(),
        "|actual_usd| of the rows", "Label standardised, not overwritten", "")
    for fid, col, t_, cat in (("F24", "flag_qty_negative", "Negative quantity on a revenue/COGS qty GL", "Suspected anomaly"),
                              ("F25", "flag_qty_zero", "Zero quantity on a qty GL", "Suspected anomaly"),
                              ("F26", "flag_qty_missing_on_qty_gl", "Quantity missing on GL 4100/5100", "Missing information"),
                              ("F27", "flag_headcount_on_non_people_gl", "Headcount present on a non-People-cost account", "Suspected anomaly"),
                              ("F28", "flag_dimension_on_non_rev_cogs", "Product/segment/channel filled on a non Revenue/COGS account", "Suspected anomaly"),
                              ("F29", "flag_dimension_missing_rev_cogs", "Product/segment/channel missing on a Revenue/COGS account", "Missing information")):
        m_ = f(col)
        add(fid, t_, cat, m_, absamt[m_].sum(), "|actual_usd| of affected rows", "Flag only", "")
    gf = f("flag_gl_filled")
    add("F30", "gl_account blank on posting rows (recovered from account_name)", "Missing information - recovered", gf, absamt[gf].sum(),
        "|actual_usd| of rows that would otherwise be unclassified", "Filled via 1:1 name map; audited", "")
    ff = f("flag_fs_line_filled")
    add("F31", "fs_line blank on posting rows (recovered from GL master)", "Missing information - recovered", ff, absamt[ff].sum(),
        "|actual_usd| of affected rows", "Filled via GL master; audited", "")
    rg = f("flag_region_filled")
    add("F32", "region blank (recovered from country)", "Missing information - recovered", rg, absamt[rg].sum(),
        "|actual_usd| of affected rows", "Filled via country map; audited", "")
    pdm = f("flag_posting_date_missing")
    add("F33", "posting_date blank", "Missing information", pdm, absamt[pdm].sum(), "|actual_usd| of affected rows",
        "Left blank (nothing to derive it from)", "")
    sl = f("flag_posting_date_resolved_by_period")
    add("F34", "Slash posting dates are day-first for some rows and month-first for others", "Assumption (evidence-supported)", sl,
        absamt[sl].sum(), "|actual_usd| of affected rows", "Reading decided by the fiscal-period month; audited",
        "Exactly one reading falls in the period month for every slash row; 0 conflicts.")
    ccm = f("flag_cost_center_missing")
    add("F35", "cost centre (code, name, owner) blank", "Missing information", ccm, absamt[ccm].sum(), "|actual_usd| of affected rows",
        "Left blank", "")
    fy = f("flag_fiscal_year_filled")
    add("F36", "fiscal_year blank (derived from fiscal_period)", "Missing information - recovered", fy, absamt[fy].sum(),
        "|actual_usd| of affected rows", "Derived; audited", "")
    bi = f("flag_batch_year_inferred")
    add("F37", "extract_batch 'CLOSE-XX-nnn' (year missing)", "Assumption", bi, absamt[bi].sum(), "|actual_usd| of affected rows",
        "Year inferred from fiscal period; audited", "")
    icm = f("flag_ic_blank_on_gl1500") | f("flag_accrual_blank_on_gl2200")
    add("F38", "intercompany / accrual blank where the GL implies a value", "Missing information", icm, absamt[icm].sum(),
        "|actual_usd| of affected rows", "Flag only",
        "Tested, none found: every GL 1500 row has intercompany = Y and every GL 2200 row has accrual = Y.")
    stb = f("flag_status_blank")
    add("F39", "approval_status blank (meaning unknown)", "Missing information / Unresolved", stb, absamt[stb].sum(),
        "|actual_usd| of affected rows", "Excluded from reported totals at step 5 per proposed rule", "")
    ws_cells = int(ctx.facts["whitespace_cells_changed"])
    ws_rows = int(ctx.facts["whitespace_rows_changed"])
    add("F40", "Whitespace / spacing normalisation across the 43 text columns (cosmetic, meaning unchanged)",
        "Cosmetic - corrected", np.zeros(ctx.n, dtype=bool), 0.0, "none (meaning unchanged)", "Standardised; originals kept in the *_raw columns of the CSV",
        f"{ws_cells:,} CELLS changed in {ws_rows:,} DISTINCT rows ({pct(ws_rows, ctx.n):.2f}% of rows). Category/alias normalisation (C01, E01, M01, G04) "
        f"changed {ctx.facts.get('category_cells_changed', 0):,} cells in {ctx.facts.get('category_rows_changed', 0):,} rows (measured against raw text, so it overlaps the whitespace count). "
        "No hidden/non-ASCII characters were found in any column.")
    out = pd.DataFrame(items)
    out.loc[out["finding_id"] == "F40", "rows"] = ws_rows
    out.loc[out["finding_id"] == "F40", "pct_of_rows"] = round(pct(ws_rows, ctx.n), 3)
    out.loc[out["finding_id"] == "F40", "row_basis"] = "all rows"
    out = out.sort_values(["priority_tier", "impact_usd", "rows"], ascending=[True, False, False]).reset_index(drop=True)
    out.insert(0, "rank", np.arange(1, len(out) + 1))
    return out


def build_exceptions(ctx: Ctx, limit: int) -> pd.DataFrame:
    D = ctx.D
    absamt = pd.Series(_abs_actual(ctx), index=D.index)
    high = ((D["flag_scale_undetermined"] == 1) | (D["flag_fx_no_match"] == 1) | (D["flag_fx_zero"] == 1)
            | (D["flag_sign_single_column_flip"] == 1) & (D["sign_flip_column"] == "actual_usd")
            | (D["dup_tier"] == "CANDIDATE_COPY_PARTIAL_AGREEMENT") | (D["flag_low_magnitude_tail"] == 1)
            | (D["flag_magnitude_outlier"] == 1) | (D["flag_entity_unresolved"] == 1))
    cols = ["source_row_number", "row_id", "document_no", "entity_code", "gl_account", "period_ym", "currency",
            "report_scale_label", "scale_decision", "scale_peer_zscore", "amount_local_parsed", "fx_rate",
            "actual_usd_parsed", "actual_usd_adj", "sign_pattern", "sign_flip_column", "fx_check", "dup_tier",
            "excl_PL_actual", "flags"]
    ex = D.loc[high, cols].copy()
    ex["abs_actual_usd"] = absamt[high]
    ex = ex.sort_values("abs_actual_usd", ascending=False)
    return ex.head(limit)


def build_open_items(ctx: Ctx, findings: pd.DataFrame) -> pd.DataFrame:
    D, F = ctx.D, ctx.facts
    absamt = _abs_actual(ctx)
    n_ut = int(((D["report_scale_label"] == "Thousands") & (D["scale_decision"] == "UNDIVIDED")).sum())
    el = D["eligible_PL_actual"].to_numpy() == 1
    dup_el = el & (D["dup_tier"].to_numpy() == "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN")
    sc_el = el & (D["dup_tier"].to_numpy() == "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT")
    n_hi = int((ctx.arr["scale_restored"] & (D["scale_confidence"].to_numpy() == "HIGH")).sum())
    n_me = int((ctx.arr["scale_restored"] & (D["scale_confidence"].to_numpy() == "MEDIUM")).sum())
    items = [
        ("Scale rule (R7)", "Unresolved in Phase 1; this run applies an evidence-based per-row decision.",
         f"{int(ctx.arr['scale_restored'].sum()):,} rows restored = {n_hi:,} HIGH-confidence (price-identity consistency test) + {n_me:,} MEDIUM-confidence (peer z-score). "
         "These are evidence-based restorations, NOT confirmed errors: the list prices behind the identity were inferred from this dataset, not taken from an independent source. "
         f"Labels '000s' and 'In thousands' were never divided "
         f"in any tested row. Expected wrong restorations from the z-rule: about {F['actual_tail_rate_other_gl'] * n_ut:.1f} rows "
         f"(natural tail {F['actual_tail_rate_other_gl'] * 100:.2f}% x {n_ut} undivided 'Thousands' rows). {int(ctx.arr['scale_undetermined'].sum())} rows left undetermined.",
         "Owner to confirm the rule (and ideally supply the generator/source rule) before any total is published."),
        ("Duplicate rule (R11)", "Unresolved. Nothing removed.",
         f"{int(ctx.arr['dup_fm_same_sign'].sum()):,} duplicate CANDIDATES with a field match and the same sign (amount fields only; NOT a full-row match); {int(dup_el.sum()):,} of them currently ELIGIBLE (P&L actual) "
         f"carrying |actual| {absamt[dup_el].sum():,.0f} USD - a double-count risk if copies are real duplicates. "
         f"A further {int(ctx.arr['dup_fm_sign_conflict'].sum()):,} candidates match in absolute value but have a SIGN CONFLICT (possible reversals; {int(sc_el.sum()):,} eligible) and are never auto-removed.",
         "Owner to decide: keep anchors only (set REMOVE_FIELD_MATCH_DUPLICATES = True, same-sign candidates only) or keep all."),
        ("List-price reference for the scale test", "No independent list-price source exists in the project.",
         "The prices (Diagnostics 640, Home Comfort 180, Motors 260, Pumps & Valves 420, Spare Kits 45) were inferred from the dataset's own undivided rows. "
         "The identity test is therefore an inferred consistency test.", "Owner to supply an authoritative price list, or accept the inference."),
        ("Journal-status eligibility (R6)", "PROVISIONAL: only 'Posted' enters totals (proposed rule; every ELIGIBLE total in this workbook is provisional).",
         f"Only {int((D['approval_status'] == 'Posted').sum()):,} of {ctx.n:,} rows are Posted; {int(ctx.arr['status_blank'].sum()):,} are blank. "
         "The status mix is near-uniform across entities (looks like noise).", "Owner to confirm what blank / Pending / Parked mean."),
        ("FX direction and rate quality (R8)", "USD = local / rate fits the data; rate 1.0 on non-USD rows and rate 0 do not.",
         f"Local/rate reconciles to actual USD for {F['fx_div_share_testable']:.1f}% of {F['fx_testable']:,} testable rows (sign-insensitive); "
         f"all {int(ctx.arr['fx_no_match'].sum()):,} failures have rate exactly 1.0 on a non-USD currency. {int(ctx.arr['fx_zero'].sum()):,} rows have rate 0. "
         f"USD-currency rows: {F['fx_pop']['rate_outside']:,} of {F['fx_pop']['rate_usable']:,} with a usable rate lie outside 1.000 +/- 0.001 (none is exactly 1.0); "
         f"separately, the AMOUNT test (F12) finds |local| != |actual| on {F['fx_pop']['amt_differ']:,} USD rows. The counts are different populations: see FX_Evidence.",
         "Owner to confirm the rate source and why USD rows are not 1.0."),
        ("Account sign convention (R9)", "Unresolved. No sign was changed.",
         f"{int(ctx.arr['sign_single_flip'].sum()):,} rows have exactly one column with an opposite sign; {int(ctx.arr['sign_all_neg'].sum()):,} rows are negative in every column (plausible credits).",
         "Owner to define the sign convention per account group."),
        ("Entities", "Junk / unresolved entity rows are excluded, not deleted.",
         f"Junk by name {F['junk_by_name_n']}, by code {F['junk_by_code_n']}, union {F['junk_total_n']}; {int(ctx.arr['entity_unresolved'].sum())} rows have neither a code nor a name. "
         "Phase-1 docs quote 173 (names only) - docs should be updated.", "Owner to confirm 'Do not use' / 'xxx' are non-reporting."),
        ("Missing with no source", "Left blank on purpose.",
         f"posting_date blank {int(ctx.arr['pd_blank'].sum()):,}; cost centre blank {int(ctx.arr['cc_missing'].sum()):,}; user_id/approval blank ~4-5% each.",
         "Nothing to fix in cleaning; request a better extract if these matter."),
        ("UOM 'NOS'", "Kept separate from 'EA'.", "Number-of-pieces abbreviation is probably equal to EA but is not proven.", "Owner to confirm."),
        ("Period convention", "P01 = January, fiscal year = calendar year.",
         "Supported: every non-slash posting date lies in the month implied by this reading (8 period formats, 0 exceptions).", "Owner to confirm."),
        ("Provenance and licence", "Not recorded (docs/DATA_PROVENANCE.md).", "Dataset is stated to be synthetic.", "Owner to record source and terms."),
    ]
    return pd.DataFrame(items, columns=["topic", "status / what was done", "evidence from this run", "decision needed"])


RECON_FIELDS = (
    # (Column_Profile raw column, flag column, finding id)
    ("amount_local_raw", "flag_amount_local_missing", "F20"),
    ("actual_usd_raw", "flag_actual_usd_missing", "F16"),
    ("budget_usd_raw", "flag_budget_usd_missing", "F17"),
    ("forecast_usd_raw", "flag_forecast_usd_missing", "F18"),
    ("prior_year_usd_raw", "flag_prior_year_usd_missing", "F19"),
    ("fx_rate_raw", "flag_fx_missing", "F11"),
)


def build_count_reconciliation(ctx: Ctx, findings: pd.DataFrame, flag_counts: pd.DataFrame, colprofile: pd.DataFrame):
    """Cross-sheet reconciliation. Table 1: Column_Profile (ALL rows) vs DQ_Findings / Flag_Counts (POSTING rows) for the six
    missing-value fields. Table 2: every finding that is a single flag: DQ_Findings rows vs Flag_Counts vs CSV flag sum."""
    D = ctx.D
    cp = colprofile.set_index("raw_column")
    fc = flag_counts.set_index("flag")["rows_all"]
    fd = findings.set_index("finding_id")["rows"]
    r1 = []
    for rawc, flag, fid in RECON_FIELDS:
        all_rows = int(cp.loc[rawc, "raw_missing_all_rows"])
        nonpost = int(cp.loc[rawc, "raw_missing_nonposting_rows"])
        posting = int(cp.loc[rawc, "raw_missing_posting_rows"])
        r1.append({"field": rawc, "column_profile_all_rows": all_rows, "less_non_posting_rows": nonpost,
                   "equals_posting_rows": all_rows - nonpost, "dq_findings_rows": int(fd[fid]), "finding_id": fid,
                   "flag_counts_rows_all": int(fc[flag]), "csv_flag_sum": int(D[flag].sum()),
                   "max_abs_difference": int(max(abs(all_rows - nonpost - int(fd[fid])), abs(int(fd[fid]) - int(fc[flag])),
                                                  abs(int(fc[flag]) - int(D[flag].sum())), abs(posting - int(fd[fid])))),
                   "explanation": "Column_Profile counts all 152,682 rows; DQ_Findings/Flag_Counts count posting rows only (the 350 non-posting rows are excluded from every total).",
                   })
    t1 = pd.DataFrame(r1)
    t1["status"] = np.where(t1["max_abs_difference"] == 0, "RECONCILED", "DIFFERENCE")
    r2 = []
    for row in findings.itertuples():
        if not row.source_flag:
            continue
        r2.append({"finding_id": row.finding_id, "source_flag": row.source_flag, "dq_findings_rows": int(row.rows),
                   "flag_counts_rows_all": int(fc[row.source_flag]), "csv_flag_sum": int(D[row.source_flag].sum()),
                   "max_abs_difference": int(max(abs(int(row.rows) - int(fc[row.source_flag])), abs(int(row.rows) - int(D[row.source_flag].sum()))))})
    t2 = pd.DataFrame(r2)
    t2["status"] = np.where(t2["max_abs_difference"] == 0, "RECONCILED", "DIFFERENCE")
    return t1, t2


def build_schema_map(ctx: Ctx, workbook_columns: List[str]) -> pd.DataFrame:
    """Every column of the canonical cleaned CSV: where it comes from and whether the review workbook shows it."""
    D = ctx.D
    clean_to_raw = {v: k for k, v in RAW_TO_CLEAN.items()}
    rows = []
    for i, c in enumerate(D.columns, start=1):
        if c in clean_to_raw:
            grp, src = "original field (cleaned)", clean_to_raw[c]
        elif c.endswith("_raw"):
            grp, src = "verbatim copy of the source text", c[:-4] if c[:-4] in ctx.raw.columns else ""
        elif c.endswith("_status") or c.endswith("_format"):
            grp, src = "parse status / format evidence", ""
        elif c.startswith("flag_"):
            grp, src = "0/1 data-quality flag", ""
        elif c.startswith("excl_") or c.startswith("eligible_"):
            grp, src = "exclusion accounting", ""
        else:
            grp, src = "derived / evidence", ""
        rows.append({"csv_position": i, "column": c, "group": grp, "source_raw_column": src,
                     "in_workbook_Cleaned_Data": "yes" if c in workbook_columns else "no (CSV only)"})
    return pd.DataFrame(rows)


def extra_validation(ctx: Ctx, findings: pd.DataFrame, excl: pd.DataFrame, recon1: pd.DataFrame, recon2: pd.DataFrame,
                     schema: pd.DataFrame, workbook_columns: List[str]) -> List[dict]:
    D = ctx.D
    out = []

    def chk(cid, desc, expected, actual, ok):
        out.append({"check_id": cid, "check": desc, "expected": str(expected), "actual": str(actual), "result": "PASS" if ok else "FAIL"})

    miss = [c for c in RAW_TO_CLEAN.values() if c not in workbook_columns]
    chk("V27", "Every one of the 43 original fields has its cleaned counterpart in the review workbook (no original field silently lost)", "none missing", ", ".join(miss) or "none missing", not miss)
    chk("V28", "Every original field has a cleaned counterpart in the canonical CSV", "none missing",
        ", ".join(c for c in RAW_TO_CLEAN.values() if c not in D.columns) or "none missing", all(c in D.columns for c in RAW_TO_CLEAN.values()))
    chk("V29", "Count_Reconciliation: Column_Profile (all rows) - non-posting = DQ_Findings = Flag_Counts = CSV flag sum for the 6 missing-value fields",
        "0 differences", f"{int((recon1['max_abs_difference'] != 0).sum())} differences", bool((recon1["max_abs_difference"] == 0).all()))
    chk("V30", "Count_Reconciliation: every single-flag finding equals its Flag_Counts row and the CSV flag sum", "0 differences",
        f"{int((recon2['max_abs_difference'] != 0).sum())} of {len(recon2)}", bool((recon2["max_abs_difference"] == 0).all()))
    tl = pd.DataFrame(ctx.tlog)
    chk("V31", "Transformation_Log: distinct rows affected never exceed the row count; cells_changed >= distinct rows where both are stated",
        "all valid", "all valid" if bool((tl["distinct_rows_affected"] <= ctx.n).all()) and bool(
            (pd.to_numeric(tl["cells_changed"], errors="coerce").fillna(10**12) >= tl["distinct_rows_affected"]).all()) else "violation",
        bool((tl["distinct_rows_affected"] <= ctx.n).all()) and bool((pd.to_numeric(tl["cells_changed"], errors="coerce").fillna(10**12) >= tl["distinct_rows_affected"]).all()))
    f1 = findings[findings["finding_id"].isin(["F01a", "F01b"])]["rows"].sum()
    chk("V32", "Scale restorations split: HIGH (price identity) + MEDIUM (peer z-score) = all restored rows", int(D["flag_scale_restored"].sum()), int(f1),
        int(f1) == int(D["flag_scale_restored"].sum()))
    und = D["scale_decision"].eq("UNDETERMINED")
    adjc = ["amount_local_adj", "actual_usd_adj", "budget_usd_adj", "forecast_usd_adj", "prior_year_usd_adj"]
    n_adj = int(sum(D.loc[und, c].notna().sum() for c in adjc))
    strict = excl.loc[excl["primary_reason"] == "8_SCALE_UNDECIDABLE", "sum_abs_actual_usd_adj"].astype(float).abs().sum()
    chk("V33", "Undetermined-scale rows: no adjusted value in ANY of the 5 amount columns, and the strict adjusted exclusion total is 0", "0 / 0.00", f"{n_adj} / {strict:.2f}", n_adj == 0 and strict == 0)
    chk("V34", "Duplicate tiers: same-sign candidates have no sign difference; sign-conflict candidates have >=1",
        0, int(((D["dup_tier"] == "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN") & (D["dup_sign_diff_cols"] > 0)).sum()),
        int(((D["dup_tier"] == "DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN") & (D["dup_sign_diff_cols"] > 0)).sum()) == 0 and
        int(((D["dup_tier"] == "DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT") & (D["dup_sign_diff_cols"] == 0)).sum()) == 0)
    _p = ctx.facts["fx_pop"]
    _close = (_p["usd_posting"] == _p["rate_unusable_text"] + _p["rate_zero"] + _p["rate_usable"]
              and _p["rate_usable"] == _p["rate_within"] + _p["rate_outside"]
              and _p["usd_all"] - _p["usd_nonposting"] == _p["usd_posting"]
              and _p["amt_differ"] == _p["overlap"] + _p["amt_differ_rate_ok"]
              and _p["rate_outside"] == int(D["flag_fx_usd_rate_not_one"].sum()) and _p["amt_differ"] == int(D["flag_usd_row_local_neq_usd"].sum()))
    chk("V36", "USD/FX population waterfall closes (posting = missing + zero + usable; usable = within + outside; amount test = overlap + rest) and ties to the flags",
        "closes", "closes" if _close else "does not close", _close)
    chk("V35", "Schema map covers every CSV column exactly once", D.shape[1], len(schema), len(schema) == D.shape[1] and schema["column"].is_unique)
    return out


def build_validation(ctx: Ctx, integrity: Dict[str, object]) -> pd.DataFrame:
    D, F, raw = ctx.D, ctx.facts, ctx.raw
    n = ctx.n
    checks = []

    def chk(cid, desc, expected, actual, ok):
        checks.append({"check_id": cid, "check": desc, "expected": str(expected), "actual": str(actual),
                       "result": "PASS" if ok else "FAIL"})

    chk("V01", "Raw file SHA-256 equals the expected value", EXPECTED_SHA256, integrity.get("sha256"), bool(integrity.get("hash_match")))
    chk("V02", "Raw rows x columns", f"{EXPECTED_ROWS} x {EXPECTED_COLUMNS}", f"{n} x {raw.shape[1]}", n == EXPECTED_ROWS and raw.shape[1] == EXPECTED_COLUMNS)
    chk("V03", "Cleaned rows equal raw rows (no row dropped, none added)", n, len(D), len(D) == n)
    chk("V04", "row_id unique and unchanged / in raw order", "identical", "identical" if (D["row_id"].to_numpy() == ctx.S["row_id"].to_numpy()).all() and raw["row_id"].is_unique else "different",
        bool((D["row_id"].to_numpy() == ctx.S["row_id"].to_numpy()).all() and raw["row_id"].is_unique))
    chk("V05", "Non-posting rows identified by notes equal those identified by TOTAL/Subtotal/CHECK labels (no label-only / notes-only rows)",
        "350 / 0 / 0", f"{F['nonposting_n']} / {F['nonposting_label_only_n']} / {F['nonposting_notes_only_n']}",
        F["nonposting_n"] == 350 and F["nonposting_label_only_n"] == 0 and F["nonposting_notes_only_n"] == 0)
    chk("V06", "Non-posting rows keep a blank GL (nothing was invented for them)", 0, int((D.loc[D["flag_nonposting"] == 1, "gl_account"] != "").sum()),
        int((D.loc[D["flag_nonposting"] == 1, "gl_account"] != "").sum()) == 0)
    unp = sum(F[f"unparsed_{s}"] for s in ALL_AMT_SHORT)
    chk("V07", "Amount cells that are neither parsable nor a known placeholder/blank", 0, unp, unp == 0)
    # independent oracle over every amount cell
    bad = 0
    for rc, sh in AMOUNT_CLEAN_NAMES.items():
        vals = ctx.P[sh]["value"].to_numpy()
        for s, v in zip(raw[rc].to_numpy(), vals):
            o = oracle_parse_amount(s)
            if o is None:
                if not np.isnan(v):
                    bad += 1
            elif np.isnan(v) or abs(o - v) > 1e-9:
                bad += 1
    chk("V08", "Independent scalar re-parse of all %s amount cells agrees with the vectorised parser" % f"{5 * n:,}", 0, bad, bad == 0)
    num_cols = [c for c in D.columns if D[c].dtype.kind == "f"]
    infs = int(sum(np.isinf(D[c].to_numpy(dtype=float)).sum() for c in num_cols))
    chk("V09", "No infinite values in any numeric output column", 0, infs, infs == 0)
    for scope, _s, _c in EXCL_SCOPES:
        vc = D[f"excl_{scope}"].value_counts()
        tot = int(vc.sum())
        elig = int(vc.get(EXCL_ELIGIBLE, 0))
        rs = int(sum(vc.get(r, 0) for r in EXCL_REASONS))
        chk(f"V10_{scope}", f"Exclusion identity ({scope}): eligible + sum of primary reasons = all rows", n, f"{elig} + {rs} = {elig + rs}", elig + rs == n and tot == n)
    chk("V11", "No fiscal_period left unparsed", 0, F["period_unparsed_n"], F["period_unparsed_n"] == 0)
    chk("V12", "Posting dates not in the fiscal-period month (resolved dates)", 0, int(ctx.arr["pd_mismatch"].sum()), int(ctx.arr["pd_mismatch"].sum()) == 0)
    chk("V13", "Slash dates left unresolved", 0, int(ctx.arr["pd_unresolved"].sum()), int(ctx.arr["pd_unresolved"].sum()) == 0)
    chk("V14", "GL master conflicts (one GL with >1 name/group/fs_line/statement) and name->GL conflicts", 0,
        f"{F['gl_master_conflicts']} / {len(F['gl_name_conflicts'])}", F["gl_master_conflicts"] == 0 and len(F["gl_name_conflicts"]) == 0)
    chk("V15", "Posting rows with no GL after recovery", 0, int(ctx.arr["gl_unresolved"].sum()), int(ctx.arr["gl_unresolved"].sum()) == 0)
    chk("V16", "Statement label unmapped / conflicting with GL master", 0, f"{int(ctx.arr['stmt_unmapped'].sum())} / {int(ctx.arr['stmt_conflict'].sum())}",
        int(ctx.arr["stmt_unmapped"].sum()) == 0 and int(ctx.arr["stmt_conflict"].sum()) == 0)
    chk("V17", "Entity name -> code conflicts; name/code disagreement; country or currency not matching the entity", 0,
        f"{len(F['entity_name_conflicts'])} / {int(ctx.arr['entity_name_code_conflict'].sum())} / {int(ctx.arr['country_mismatch'].sum())} / {int(ctx.arr['currency_mismatch'].sum())}",
        len(F["entity_name_conflicts"]) == 0 and int(ctx.arr["entity_name_code_conflict"].sum()) == 0
        and int(ctx.arr["country_mismatch"].sum()) == 0 and int(ctx.arr["currency_mismatch"].sum()) == 0)
    # scale recomputation
    dec = D["scale_decision"].isin(["UNDIVIDED", "DIVIDED_1E3", "DIVIDED_1E5"]).to_numpy() & (D["is_posting_row"].to_numpy() == 1)
    exp = D["actual_usd_parsed"].to_numpy(dtype=float) * np.where(D["scale_decision"] == "DIVIDED_1E3", 1000.0, np.where(D["scale_decision"] == "DIVIDED_1E5", 100000.0, 1.0))
    got = D["actual_usd_adj"].to_numpy(dtype=float)
    both = dec & np.isfinite(exp)
    if APPLY_SCALE_RESTORATION:
        okc = bool(np.allclose(np.round(exp[both], 6), got[both], rtol=0, atol=1e-6))
    else:
        okc = True
    chk("V18", "actual_usd_adj = actual_usd_parsed x decided divisor on every decided row (independent recompute)", "all equal", "all equal" if okc else "differences", okc)
    und = D["scale_decision"].eq("UNDETERMINED").to_numpy()
    chk("V19", "Undetermined-scale rows have no adjusted value (not guessed)", 0, int(np.isfinite(got[und]).sum()) if APPLY_SCALE_RESTORATION else 0,
        (not APPLY_SCALE_RESTORATION) or int(np.isfinite(got[und]).sum()) == 0)
    chk("V20", "Rows decided + undetermined + non-posting = all rows", n,
        int(dec.sum() + und.sum() + (D["is_posting_row"] == 0).sum()), int(dec.sum() + und.sum() + (D["is_posting_row"] == 0).sum()) == n)
    if "z_rule_wrong_on_identity_rows" in F:
        chk("V21", "Peer z-score rule vs price-identity truth on Thousands/Lakhs rows: confidently wrong classifications", 0,
            f"{F['z_rule_wrong_on_identity_rows']} of {F['z_rule_identity_rows_tested']}", F["z_rule_wrong_on_identity_rows"] == 0)
    nm_ = D["fx_check"].eq("NO_MATCH")
    chk("V22", "Every FX 'NO_MATCH' row has rate exactly 1.0 on a non-USD currency (information)", "all", f"{int((nm_ & (D['flag_fx_one_nonusd'] == 1)).sum())} of {int(nm_.sum())}",
        int((nm_ & (D["flag_fx_one_nonusd"] == 1)).sum()) == int(nm_.sum()))
    p = D["is_posting_row"].to_numpy() == 1
    anchors = int((D["dup_tier"] == "GROUP_ANCHOR").sum())
    chk("V23", "Duplicate tiers cover every posting row exactly once", int(p.sum()), int((D.loc[p, "dup_tier"] != "").sum()), int((D.loc[p, "dup_tier"] != "").sum()) == int(p.sum()))
    nonempty_groups = D.loc[D["dup_role"] == "ANCHOR", "doc_group_id"].nunique()
    chk("V24", "Each anchor belongs to a distinct document group", anchors, nonempty_groups, anchors == nonempty_groups)
    ws_bad = 0
    for c in D.columns:
        if c.endswith("_raw") or c in ("report_scale_raw", "currency_raw"):
            continue  # raw-copy columns intentionally keep the source text verbatim
        if D[c].dtype == object or str(D[c].dtype).startswith("str"):
            s = D[c].astype(object).fillna("").astype(str)
            ws_bad += int((s != s.str.strip()).sum())
    chk("V25", "No cleaned text cell has leading/trailing whitespace", 0, ws_bad, ws_bad == 0)
    aud = pd.concat(ctx.audit, ignore_index=True) if ctx.audit else pd.DataFrame(columns=["rule_id"])
    for rid, flag_name in (("G01", "flag_gl_filled"), ("G03", "flag_fs_line_filled"), ("M02", "flag_region_filled"),
                           ("P02", "flag_fiscal_year_filled"), ("B01", "flag_batch_year_inferred"),
                           ("P03", "flag_posting_date_resolved_by_period")):
        a = int((aud["rule_id"] == rid).sum())
        b = int(D[flag_name].sum())
        chk(f"V26_{rid}", f"Audit rows for {rid} equal flag count {flag_name}", b, a, a == b)
    return pd.DataFrame(checks)


# =============================================================================
# 12. OUTPUT WRITERS
# =============================================================================
EXCEL_CLEANED_COLUMNS = [
    "source_row_number", "row_id", "document_no", "source_system", "extract_batch", "user_id",
    "period_ym", "period_year", "period_month", "fiscal_year", "posting_date", "posting_date_resolution",
    "entity_code", "legal_entity", "entity_status", "division", "country", "region", "currency",
    "cost_center_code", "cost_center_name", "cost_center_owner", "gl_account", "account_name", "account_group", "fs_line",
    "statement", "cost_nature", "product_family", "customer_segment", "channel", "qty", "uom", "headcount_fte",
    "amount_local_parsed", "fx_rate", "actual_usd_parsed", "budget_usd_parsed", "forecast_usd_parsed",
    "prior_year_usd_parsed", "report_scale_label", "scale_decision", "scale_evidence", "scale_confidence",
    "scale_peer_zscore", "scale_factor_applied", "amount_local_adj", "actual_usd_adj", "budget_usd_adj",
    "forecast_usd_adj", "prior_year_usd_adj", "actual_usd_adj_abs_uncertainty", "fx_check", "sign_pattern",
    "sign_flag", "sign_flip_column", "intercompany", "accrual", "elimination_status", "approval_status",
    "scenario_tag", "line_text", "notes", "doc_group_id", "dup_tier", "is_posting_row",
    "excl_PL_actual", "excl_PL_variance", "excl_BS_actual", "eligible_PL_actual", "n_flags", "flags",
    # verbatim source text of the identifiers/dates that were normalised, filled or inferred (row-level traceability in the workbook)
    "entity_code_raw", "gl_account_raw", "extract_batch_raw", "fiscal_period_raw", "posting_date_raw",
]
MONEY_HINTS = ("_parsed", "_adj", "usd", "amount", "impact", "sum_abs", "understatement", "reported_abs", "restored_abs",
               "uncertainty")
DEC3_HINTS = ("zscore", "z_", "ratio", "rate", "rel_diff", "log10")


def finalize_output(tmp: Path, final: Path) -> Path:
    """Publish a fully written temporary file under its final name in one step (os.replace).
    A run that crashes half-way therefore never leaves a truncated file under the final name and
    never destroys a previous valid output. If the target is locked (open in Excel on Windows) a
    time-stamped name is used instead."""
    try:
        os.replace(tmp, final)
        return final
    except PermissionError:
        alt = final.with_name(f"{final.stem}_{time.strftime('%Y%m%d_%H%M%S')}{final.suffix}")
        os.replace(tmp, alt)
        log.warning("%s is locked (open in Excel?); wrote %s instead", final.name, alt.name)
        return alt


def _unique_if_locked(path: Path) -> Path:
    """If the target exists and cannot be opened for writing (e.g. open in Excel), use a timestamped name."""
    try:
        with open(path, "ab"):
            pass
        return path
    except PermissionError:
        alt = path.with_name(f"{path.stem}_{dt.datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
        log.warning("%s is locked (open in Excel?); writing %s instead", path.name, alt.name)
        return alt


class SheetWriter:
    """Sequential writer for a constant-memory xlsxwriter worksheet."""

    def __init__(self, wb, ws, fm):
        self.wb, self.ws, self.fm = wb, ws, fm
        self.r = 0
        self.widths: Dict[int, int] = {}

    def _w(self, c, text, cap=60):
        self.widths[c] = min(cap, max(self.widths.get(c, 8), len(str(text)) + 2))

    def title(self, text):
        self.ws.write_string(self.r, 0, text, self.fm["title"])
        self.r += 1

    def line(self, text, fmt=None):
        self.ws.write_string(self.r, 0, text, fmt or self.fm["wrap"])
        self.r += 1

    def blank(self, n=1):
        self.r += n

    def table(self, df: pd.DataFrame, title: Optional[str] = None, autofilter: bool = False, max_rows: Optional[int] = None):
        if title:
            self.title(title)
        if df is None or len(df) == 0:
            self.line("(no rows)")
            self.blank()
            return
        if max_rows is not None:
            df = df.head(max_rows)
        cols = list(df.columns)
        for c, name in enumerate(cols):
            self.ws.write_string(self.r, c, str(name), self.fm["header"])
            self._w(c, name, 40)
        hdr = self.r
        self.r += 1
        lists = [df[c].astype(object).where(df[c].notna(), None).tolist() for c in cols]
        for i in range(len(df)):
            for c, name in enumerate(cols):
                v = lists[c][i]
                self._cell(self.r, c, v, str(name))
            self.r += 1
        if autofilter:
            self.ws.autofilter(hdr, 0, self.r - 1, len(cols) - 1)
        self.blank()

    def _cell(self, r, c, v, name):
        if v is None:
            return
        if isinstance(v, (bool, np.bool_)):
            self.ws.write_string(r, c, "TRUE" if v else "FALSE")
        elif isinstance(v, (int, np.integer)):
            self.ws.write_number(r, c, int(v))
            self._w(c, v)
        elif isinstance(v, (float, np.floating)):
            if np.isfinite(v):
                lname = name.lower()
                fmt = self.fm["money"] if any(h in lname for h in MONEY_HINTS) else (self.fm["dec3"] if any(h in lname for h in DEC3_HINTS) else self.fm["dec2"])
                self.ws.write_number(r, c, float(v), fmt)
                self._w(c, f"{v:,.2f}")
        elif isinstance(v, (pd.Timestamp, dt.datetime, dt.date)):
            self.ws.write_datetime(r, c, pd.Timestamp(v).to_pydatetime(), self.fm["date"])
            self._w(c, "2000-01-01")
        else:
            s = str(v)
            self.ws.write_string(r, c, s)
            self._w(c, s)

    def finish(self):
        for c, w in self.widths.items():
            self.ws.set_column(c, c, w)


def write_cleaned_sheet(wb, ws, fm, D: pd.DataFrame, cols: List[str]) -> None:
    n = len(D)
    kinds, fmts, lists = [], [], []
    for c, name in enumerate(cols):
        s = D[name]
        ws.write_string(0, c, name, fm["header"])
        if str(s.dtype).startswith("datetime"):
            kinds.append(2)
            fmts.append(fm["date"])
        elif s.dtype.kind in "fiu" or str(s.dtype) in ("Int64", "Float64"):
            kinds.append(1)
            lname = name.lower()
            if s.dtype.kind == "f":
                fmts.append(fm["money"] if any(h in lname for h in MONEY_HINTS) and "rate" not in lname and "zscore" not in lname
                            else (fm["dec3"] if any(h in lname for h in DEC3_HINTS) else fm["dec2"]))
            else:
                fmts.append(fm["int"])
        else:
            kinds.append(0)
            fmts.append(None)
        lists.append(s.astype(object).where(s.notna(), None).tolist())
    ncol = len(cols)
    for i in range(n):
        r = i + 1
        for c in range(ncol):
            v = lists[c][i]
            if v is None:
                continue
            k = kinds[c]
            if k == 0:
                ws.write_string(r, c, v)
            elif k == 1:
                ws.write_number(r, c, v, fmts[c])
            else:
                ws.write_datetime(r, c, v.to_pydatetime() if hasattr(v, "to_pydatetime") else v, fmts[c])
    ws.freeze_panes(1, 2)
    ws.autofilter(0, 0, n, ncol - 1)
    for c, name in enumerate(cols):
        width = {"flags": 60, "line_text": 18, "legal_entity": 26, "account_name": 28, "scale_evidence": 34,
                 "dup_tier": 26, "excl_PL_actual": 24, "excl_PL_variance": 24, "excl_BS_actual": 24}.get(name, max(11, min(22, len(name) + 2)))
        ws.set_column(c, c, width)


def build_readme_lines(ctx: Ctx, integrity: Dict[str, object], findings: pd.DataFrame, excl: pd.DataFrame, runinfo: Dict[str, object]) -> List[str]:
    D = ctx.D
    pl = excl[(excl["scope"] == "PL_actual") & (excl["step"] != 99)]
    elig = int(pl.loc[pl["primary_reason"] == EXCL_ELIGIBLE, "rows"].iloc[0])
    top = findings.head(5)
    L = []
    L.append("READ THIS FIRST - fpa_monthly_close_cleaned.xlsx")
    L.append("")
    L.append(f"Generated by clean_fpa_monthly_close.py v{SCRIPT_VERSION} on {runinfo['timestamp']}. Source: {INPUT_FILE_NAME} (SHA-256 verified: {integrity.get('hash_match')}).")
    L.append("This workbook is a CLEANED COPY. The raw file was never modified. NO ROW WAS DELETED: all %s raw rows are in Cleaned_Data." % f"{ctx.n:,}")
    L.append("")
    L.append("CANONICAL OUTPUT (which file is 'the' cleaned dataset)")
    L.append(f"* CANONICAL cleaned dataset = {OUTPUT_BASENAME}.csv: all {ctx.n:,} rows x {D.shape[1]} columns (every original field, its verbatim *_raw copy, parse evidence and all 0/1 flags). Use it for the SQL phase.")
    L.append(f"* THIS WORKBOOK is a REVIEW COPY: its Cleaned_Data sheet shows all {ctx.n:,} rows but only {len(EXCEL_CLEANED_COLUMNS)} of the {D.shape[1]} columns (all 43 original fields, key evidence, exclusion accounting, flags text and the raw text of normalised identifiers).")
    L.append("* Schema_Map lists every CSV column and whether the workbook shows it. No original field is lost: all 43 have a cleaned counterpart in both files (validation V27/V28).")
    L.append("* ALL ELIGIBLE / reported totals are PROVISIONAL: they rest on the proposed rule that only 'Posted' journals count (R6). Blank / Pending / Rejected / Parked are unresolved.")
    L.append("The data is stated by the owner to be synthetic (not independently verified). Results describe a simulated dataset, not a real company.")
    L.append("")
    L.append("HOW TO READ THE CLEANED DATA")
    L.append("* *_parsed = the number exactly as reported (text converted to a number). *_adj = after the evidence-based scale decision. Use *_adj for analysis, *_parsed to trace back.")
    L.append("* Missing amounts are blank (never zero). A placeholder such as ### / #N/A / NA / '-' means 'not reported'.")
    L.append("* scale_decision / scale_evidence / scale_confidence tell you WHY a row was or was not restored. UNDETERMINED rows are left blank in *_adj.")
    L.append("* excl_PL_actual (and _PL_variance, _BS_actual) = the ONE primary reason a row is not in a reported total, or ELIGIBLE. Filter eligible_PL_actual = 1 for the P&L actual scope.")
    L.append("* flags = every issue seen on the row (pipe-separated). Full 0/1 flag columns are in the CSV.")
    L.append("* P&L and Balance Sheet rows must never be added together. Use the 'statement' column.")
    L.append("")
    L.append("HEADLINE NUMBERS")
    L.append(f"* Rows: {ctx.n:,} in, {len(D):,} out. Non-posting (TOTAL/Subtotal/CHECK) rows: {int(D['flag_nonposting'].sum()):,}. Junk-entity rows: {int(D['flag_junk_entity'].sum()):,}. Unresolvable entity: {int(D['flag_entity_unresolved'].sum()):,}.")
    L.append(f"* P&L actual scope: {elig:,} rows are ELIGIBLE (PROVISIONAL: proposed rule, only 'Posted' journals). The rest carry exactly one exclusion reason (see Exclusion_Summary).")
    _hi = int(((D['flag_scale_restored'].to_numpy() == 1) & (D['scale_confidence'].to_numpy() == 'HIGH')).sum())
    _me = int(((D['flag_scale_restored'].to_numpy() == 1) & (D['scale_confidence'].to_numpy() == 'MEDIUM')).sum())
    L.append(f"* Scale: {int(D['flag_scale_restored'].sum()):,} rows are restored in *_adj = {_hi:,} HIGH (price-identity consistency test) + {_me:,} MEDIUM (peer z-score). They are evidence-based restorations, NOT confirmed errors. {int(D['flag_scale_undetermined'].sum())} rows stay undetermined (blank in *_adj; their as-reported amounts are NOT validated).")
    L.append("* Top-ranked findings (by USD at stake): " + "; ".join(f"{r.finding_id} {r.finding[:60]}" for r in top.itertuples()))
    L.append("")
    L.append("WHAT IS PROVEN, WHAT IS ASSUMED")
    L.append("* Strongly supported (inferred consistency test, NOT independent proof): for GL 4100/5100, |actual_usd| = |qty| x list price holds exactly at ratio 1, 1/1,000 or 1/100,000. The list prices were inferred from this dataset itself; no independent price list exists.")
    L.append("* Medium confidence: the peer z-score used for rows without the identity (see Scale_Evidence for the validation and the expected error).")
    L.append("* Duplicates: 'DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN' = same document_no, GL, period and every comparable AMOUNT column equal incl. sign (other columns such as batch, posting date, status, line text are NOT compared and may differ); 'SIGN_CONFLICT' = equal in absolute value but an opposite sign (possible reversal). These are CANDIDATES, not confirmed duplicates. Nothing is removed. Rule and tolerances: Duplicate_Review.")
    L.append("* Assumptions: slash-date reading decided by the fiscal-period month; P01 = January; blank GL recovered from account name; 'NOS' kept separate from 'EA'.")
    L.append("* Not decided by this script (still open in docs/FINANCIAL_METRICS.md): duplicate removal, account sign convention, journal-status meaning of blank, consolidation. See Open_Items.")
    L.append("")
    L.append("SHEETS")
    L.append("README | QC_Summary | DQ_Findings (ranked) | Exclusion_Summary | Cleaned_Data | Non_Posting_Rows | Junk_Entity_Rows | Exceptions | Scale_Evidence | FX_Evidence | "
             "Amount_Parse_Evidence | Date_Resolution | Duplicate_Review | Flag_Counts | Mappings | Column_Profile | Schema_Map | Count_Reconciliation | Transformation_Log | Validation_Checks | Open_Items")
    L.append(f"Companion files: the CANONICAL cleaned CSV ({D.shape[1]} columns incl. 0/1 flags), cell-level audit CSV, QC_Report.txt, qc_summary.json, run_log.txt.")
    L.append("The read-back validation of the written files is recorded in QC_Report.txt (it can only be run after this workbook is saved).")
    return L


def write_workbook(path: Path, ctx: Ctx, tables: Dict[str, object], readme: List[str]) -> None:
    try:
        import xlsxwriter
    except ImportError as exc:
        raise PipelineError("The 'xlsxwriter' package is required. Install it with:  pip install xlsxwriter") from exc
    D = ctx.D
    wb = xlsxwriter.Workbook(str(path), {"constant_memory": True, "strings_to_numbers": False,
                                         "strings_to_formulas": False, "strings_to_urls": False,
                                         "nan_inf_to_errors": False})
    fm = {
        "header": wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F3864", "text_wrap": True, "valign": "top", "border": 1}),
        "title": wb.add_format({"bold": True, "font_size": 12, "font_color": "#1F3864"}),
        "wrap": wb.add_format({"text_wrap": False}),
        "money": wb.add_format({"num_format": "#,##0.00"}),
        "dec2": wb.add_format({"num_format": "0.00"}),
        "dec3": wb.add_format({"num_format": "0.000"}),
        "int": wb.add_format({"num_format": "0"}),
        "date": wb.add_format({"num_format": "yyyy-mm-dd"}),
    }
    order = ["README", "QC_Summary", "DQ_Findings", "Exclusion_Summary", "Cleaned_Data", "Non_Posting_Rows", "Junk_Entity_Rows",
             "Exceptions", "Scale_Evidence", "FX_Evidence", "Amount_Parse_Evidence", "Date_Resolution", "Duplicate_Review",
             "Flag_Counts", "Mappings", "Column_Profile", "Schema_Map", "Count_Reconciliation", "Transformation_Log", "Validation_Checks", "Open_Items"]
    wss = {name: wb.add_worksheet(name) for name in order}
    # README
    sw = SheetWriter(wb, wss["README"], fm)
    for i, line in enumerate(readme):
        wss["README"].write_string(i, 0, line, fm["title"] if i == 0 else None)
    wss["README"].set_column(0, 0, 180)
    # QC_Summary
    sw = SheetWriter(wb, wss["QC_Summary"], fm)
    sw.table(tables["qc_kv"], "Run summary")
    sw.table(tables["qc_waterfall"], "Row accounting - P&L actual scope (eligible + exclusions = all rows)")
    sw.table(tables["validation_summary"], "Validation checks (details in Validation_Checks)")
    sw.finish()
    # Findings
    sw = SheetWriter(wb, wss["DQ_Findings"], fm)
    sw.line("Ranked by priority_tier (1 = confirmed / strongly supported, 2 = probable or suspected, 3 = unresolved or missing, 4 = assumption / recovered / legitimate / cosmetic), then by impact_usd = USD at stake (see impact_basis). Exposure, NOT a booked error amount.")
    sw.line("'rows' count the rows shown in row_basis ('posting rows only' excludes the 350 non-posting rows). Count_Reconciliation ties these counts to Column_Profile and Flag_Counts.")
    sw.blank()
    sw.table(tables["findings"], None, autofilter=True)
    sw.finish()
    wss["DQ_Findings"].freeze_panes(3, 3)
    sw = SheetWriter(wb, wss["Exclusion_Summary"], fm)
    sw.line("PROVISIONAL: ELIGIBLE = journal status 'Posted' only (proposed rule R6). Meanings of blank / Pending / Rejected / Parked are unresolved, so every ELIGIBLE total is provisional.")
    sw.line("sum_abs_actual_usd_adj = validated adjusted values only (blank or undetermined rows count 0). sum_abs_actual_usd_parsed_as_reported = the source value with the scale NOT validated.")
    sw.blank()
    sw.table(tables["excl"], "One primary exclusion reason per row and scope (precedence: docs/FINANCIAL_METRICS.md section 4)")
    sw.table(tables["excl_detail"], "Details")
    sw.finish()
    write_cleaned_sheet(wb, wss["Cleaned_Data"], fm, D, EXCEL_CLEANED_COLUMNS)
    exc_cols = [c for c in EXCEL_CLEANED_COLUMNS if c in D.columns]
    sw = SheetWriter(wb, wss["Non_Posting_Rows"], fm)
    sw.table(D.loc[D["flag_nonposting"] == 1, exc_cols], "Non-posting rows (kept in the data, excluded from every total)", autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Junk_Entity_Rows"], fm)
    sw.table(ctx.ev["junk_entity_crosstab"], "Junk name vs junk code (evidence)")
    jcols = ["row_id", "document_no", "legal_entity_raw", "entity_code_raw", "entity_status", "junk_entity_basis", "country", "currency",
             "gl_account", "period_ym", "actual_usd_parsed", "approval_status", "dup_tier", "excl_PL_actual"]
    sw.table(D.loc[(D["flag_junk_entity"] == 1) | (D["flag_entity_unresolved"] == 1), jcols], "Junk and unresolvable entity rows", autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Exceptions"], fm)
    sw.line(f"Top {EXCEL_MAX_ROWS_EXCEPTIONS:,} exception rows by |actual USD| (scale undetermined, FX failures, actual-column sign flips, duplicate candidates, extreme magnitudes, unresolved entity). Full flags are in the CSV.")
    sw.blank()
    sw.table(tables["exceptions"], None, autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Scale_Evidence"], fm)
    sw.line("How the scale of each row was decided. The label in report_scale is NOT trusted.")
    sw.line("Reference (INFERRED, not independent): for GL 4100/5100, |actual_usd| = |qty| x list price. The list prices (Diagnostics 640, Home Comfort 180, Motors 260, Pumps & Valves 420, Spare Kits 45) were inferred from this dataset's own undivided rows;")
    sw.line("no independent price list exists, so this is an inferred consistency test. A ratio of 1 means undivided; 1/1,000 or 1/100,000 means divided. HIGH confidence = this test; MEDIUM = peer z-score or label-verified.")
    sw.blank()
    for key, title in (("scale_decision_by_label", "Decision by label"), ("scale_identity_truth", "Price-identity truth by label (GL 4100/5100, usable rows)"),
                       ("scale_z_validation", f"Peer z-score rule (divided if z <= {Z_DIVIDED_MAX}, undivided if z >= {Z_UNDIVIDED_MIN}) checked against the identity truth on Thousands/Lakhs rows"),
                       ("scale_actual_tail", "Natural left tail of Actual-labelled rows (shows why a low z alone cannot prove division)"),
                       ("scale_value_effect", "Value effect of restoration (abs actual USD)")):
        if key in ctx.ev:
            sw.table(ctx.ev[key], title)
    sw.table(tables["scale_notes"], "Notes and limits")
    sw.finish()
    sw = SheetWriter(wb, wss["FX_Evidence"], fm)
    sw.line("USD = local / rate is TESTED, not assumed (sign-insensitive, tolerance 0.1% or rounding uncertainty). The reported actual_usd is never replaced.")
    sw.blank()
    sw.table(ctx.ev["fx_usd_population"], "USD-currency rows: how the three counts used elsewhere (F12 amount test, F12b / Open_Items rate test, FX_Evidence usable-rate count) relate. They are DIFFERENT populations and tests, not one count reported three ways.")
    sw.table(ctx.ev["fx_check_summary"], "fx_check result (posting rows)")
    sw.table(ctx.ev["fx_by_currency"], "By currency")
    sw.table(ctx.ev["sign_pattern_summary"], "Sign pattern across the five amount columns")
    sw.finish()
    sw = SheetWriter(wb, wss["Amount_Parse_Evidence"], fm)
    sw.table(ctx.ev["amount_parse_evidence"], "Formats, statuses and placeholder tokens per amount column")
    sw.finish()
    sw = SheetWriter(wb, wss["Date_Resolution"], fm)
    sw.table(ctx.ev["period_formats"], "fiscal_period formats")
    sw.table(ctx.ev["posting_date_vs_period"], "Evidence: non-slash posting dates fall in the fiscal-period month (by period format)")
    sw.table(ctx.ev["slash_date_ambiguity"], "Slash posting dates: how ambiguous by value")
    sw.table(ctx.ev["posting_date_resolution"], "Posting date format and resolution")
    sw.finish()
    sw = SheetWriter(wb, wss["Duplicate_Review"], fm)
    sw.line("A repeated document_no is NOT automatically a duplicate. Nothing is removed. Tiers: GROUP_ANCHOR (kept), DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN, DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT, CANDIDATE_*, SHARED_DOCUMENT_*.")
    sw.table(ctx.ev["dup_rule"], "Comparison rule: fields compared, tolerance and what is NOT compared")
    sw.table(ctx.ev["dup_noncompared_diffs"], "How often the field-match candidates differ from their anchor in fields that are NOT part of the comparison")
    sw.blank()
    sw.table(ctx.ev["dup_tier_summary"], "Tier summary (posting rows)")
    dcols = ["row_id", "document_no", "doc_group_id", "dup_role", "dup_tier", "dup_cols_compared", "dup_cols_agree", "dup_sign_diff_cols",
             "entity_code", "gl_account", "period_ym", "approval_status", "actual_usd_parsed", "budget_usd_parsed", "report_scale_label",
             "scale_decision", "posting_date_raw", "extract_batch", "line_text", "excl_PL_actual"]
    sw.table(D.loc[D["doc_group_size"] >= 2, dcols].sort_values(["doc_group_id", "row_id"]), "All rows in repeated-document groups", autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Flag_Counts"], fm)
    sw.table(tables["flag_counts"], "Flag counts over ALL rows and split by the primary exclusion reason (P&L actual scope). Overlapping: not meant to add to the row total.", autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Mappings"], fm)
    mp = pd.concat(ctx.maps, ignore_index=True)
    sw.table(mp, "Every standardisation applied (raw value -> clean value, rows)", autofilter=True)
    sw.table(ctx.ev["gl_master"], "GL master built from the data")
    sw.finish()
    sw = SheetWriter(wb, wss["Column_Profile"], fm)
    sw.table(tables["column_profile"], "Raw column profile with cleaned counterpart. raw_blank/placeholder/missing_all_rows count ALL 152,682 rows; raw_missing_posting_rows excludes the 350 non-posting rows (DQ_Findings and Flag_Counts use posting rows).", autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Schema_Map"], fm)
    sw.line(f"Canonical cleaned dataset = {OUTPUT_BASENAME}.csv ({D.shape[1]} columns). This workbook's Cleaned_Data sheet is a review copy with {len(EXCEL_CLEANED_COLUMNS)} columns; the table shows every CSV column.")
    sw.blank()
    sw.table(tables["schema_map"], None, autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Count_Reconciliation"], fm)
    sw.line("Why two counts can differ: Column_Profile counts ALL rows; DQ_Findings and Flag_Counts count POSTING rows. This sheet proves the difference is exactly the non-posting rows.")
    sw.blank()
    sw.table(tables["recon1"], "A. Column_Profile (all rows) vs DQ_Findings vs Flag_Counts vs CSV flag sum - six missing-value fields")
    sw.table(tables["recon2"], "B. Every single-flag finding: DQ_Findings rows vs Flag_Counts rows_all vs CSV flag sum")
    sw.finish()
    sw = SheetWriter(wb, wss["Transformation_Log"], fm)
    sw.line("distinct_rows_affected = number of DISTINCT rows touched by the rule (never above 152,682). cells_processed / cells_changed are cell counts where measured (blank = not measured). pct_rows_affected = distinct rows / all rows.")
    sw.blank()
    sw.table(pd.DataFrame(ctx.tlog), "Every material rule: columns, cells processed, cells changed, distinct rows affected, % rows affected, classification, status", autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Validation_Checks"], fm)
    sw.table(tables["validation"], "In-memory validation before writing (file read-back results are in QC_Report.txt)", autofilter=True)
    sw.finish()
    sw = SheetWriter(wb, wss["Open_Items"], fm)
    sw.table(tables["open_items"], "Decisions and unresolved issues for the owner")
    sw.finish()
    wb.close()


def write_csv_outputs(out_dir: Path, ctx: Ctx) -> Dict[str, Path]:
    paths = {}
    p_tmp = out_dir / f"{OUTPUT_BASENAME}.csv.partial"
    ctx.D.to_csv(p_tmp, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    p = finalize_output(p_tmp, out_dir / f"{OUTPUT_BASENAME}.csv")
    paths["csv"] = p
    aud = pd.concat(ctx.audit, ignore_index=True) if ctx.audit else pd.DataFrame(
        columns=["row_id", "source_row_number", "column", "raw_value", "cleaned_value", "rule_id", "basis"])
    ap_tmp = out_dir / f"{OUTPUT_BASENAME}_cell_audit.csv.partial"
    aud.to_csv(ap_tmp, index=False, encoding="utf-8-sig")
    ap = finalize_output(ap_tmp, out_dir / f"{OUTPUT_BASENAME}_cell_audit.csv")
    paths["audit"] = ap
    ctx.facts["audit_rows"] = len(aud)
    return paths


# =============================================================================
# 13. READ-BACK VALIDATION OF WRITTEN FILES
# =============================================================================
def readback_validate(paths: Dict[str, Path], ctx: Ctx, full_excel: bool) -> pd.DataFrame:
    D = ctx.D
    out = []

    def rec(cid, desc, expected, actual, ok):
        out.append({"check_id": cid, "check": desc, "expected": str(expected), "actual": str(actual), "result": "PASS" if ok else "FAIL"})

    # CSV
    t0 = time.time()
    try:
        c = pd.read_csv(paths["csv"], dtype=str, keep_default_na=False, encoding="utf-8-sig")
        rec("RB01", "Cleaned CSV reopens: rows x columns", f"{len(D)} x {D.shape[1]}", f"{len(c)} x {c.shape[1]}", c.shape == D.shape)
        rec("RB02", "Cleaned CSV header equals the in-memory column order", "equal", "equal" if list(c.columns) == list(D.columns) else "different",
            list(c.columns) == list(D.columns))
        rec("RB03", "CSV row_id sequence equals in-memory", "equal", "equal" if (c["row_id"].to_numpy() == D["row_id"].to_numpy()).all() else "different",
            bool((c["row_id"].to_numpy() == D["row_id"].to_numpy()).all()))
        a = pd.to_numeric(c["actual_usd_adj"].replace("", np.nan)).sum()
        b = float(np.nansum(D["actual_usd_adj"].to_numpy(dtype=float)))
        rec("RB04", "Sum of actual_usd_adj in CSV equals in-memory", f"{b:,.4f}", f"{a:,.4f}", bool(np.isclose(a, b, rtol=1e-9, atol=1e-6)))
        a2 = int(pd.to_numeric(c["eligible_PL_actual"]).sum())
        b2 = int(D["eligible_PL_actual"].sum())
        rec("RB05", "Eligible (P&L actual) row count in CSV equals in-memory", b2, a2, a2 == b2)
        rec("RB06", "CSV text identifiers keep leading zeros / exact text (document_no, cost_center_code, gl_account)", "equal",
            "equal" if ((c["document_no"] == D["document_no"]).all() and (c["gl_account"] == D["gl_account"]).all() and (c["cost_center_code"] == D["cost_center_code"]).all()) else "different",
            bool((c["document_no"] == D["document_no"]).all() and (c["gl_account"] == D["gl_account"]).all() and (c["cost_center_code"] == D["cost_center_code"]).all()))
        rec("RB07", "CSV posting_date text equals in-memory ISO date", "equal",
            "equal" if (c["posting_date"] == D["posting_date"].dt.strftime("%Y-%m-%d").fillna("")).all() else "different",
            bool((c["posting_date"] == D["posting_date"].dt.strftime("%Y-%m-%d").fillna("")).all()))
        # --- extra checks on the EXACT saved CSV ---
        n_ = len(D)
        rec("RB16", "CSV keeps all original rows in source order (source_row_number = 2 .. n+1, row_id unique)", f"2..{n_ + 1}",
            f"{c['source_row_number'].iloc[0]}..{c['source_row_number'].iloc[-1]}",
            bool((pd.to_numeric(c["source_row_number"]).to_numpy() == np.arange(2, n_ + 2)).all()) and c["row_id"].is_unique)
        try:
            rp = ctx.facts.get("raw_path")
            if rp:
                rid = pd.read_csv(rp, dtype=str, keep_default_na=False, usecols=["row_id"], encoding="utf-8-sig")["row_id"].str.strip().to_numpy()
                rec("RB17", "CSV row_id sequence equals the row_id column freshly re-read from the RAW file (all rows, same order)", f"{len(rid):,} equal",
                    f"{len(c):,} rows; " + ("equal" if len(rid) == len(c) and (rid == c["row_id"].to_numpy()).all() else "DIFFERENT"),
                    len(rid) == len(c) and bool((rid == c["row_id"].to_numpy()).all()))
        except Exception as exc:  # noqa: BLE001
            rec("RB17", "Raw row_id re-read", "readable", f"ERROR {exc}", False)
        adjc = ["amount_local_adj", "actual_usd_adj", "budget_usd_adj", "forecast_usd_adj", "prior_year_usd_adj"]
        ud = c["scale_decision"] == "UNDETERMINED"
        n_adj = int(sum((c.loc[ud, k] != "").sum() for k in adjc))
        rec("RB18", "Saved CSV: scale-UNDETERMINED rows have NO adjusted value in any of the 5 amount columns", f"0 of {int(ud.sum())} rows", f"{n_adj} adjusted cells", n_adj == 0)
        rec("RB19", "Saved CSV: duplicate tiers equal in-memory (field-match same sign / field-match sign conflict / anchors)",
            f"{int((D['dup_tier'] == 'DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN').sum())} / {int((D['dup_tier'] == 'DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT').sum())} / {int((D['dup_tier'] == 'GROUP_ANCHOR').sum())}",
            f"{int((c['dup_tier'] == 'DUP_CANDIDATE_FIELD_MATCH_SAME_SIGN').sum())} / {int((c['dup_tier'] == 'DUP_CANDIDATE_FIELD_MATCH_SIGN_CONFLICT').sum())} / {int((c['dup_tier'] == 'GROUP_ANCHOR').sum())}",
            bool((c["dup_tier"] == D["dup_tier"]).all()))
        rec("RB20", "Saved CSV: cost_center_owner and the other original text fields equal in-memory", "equal",
            "equal" if all((c[k] == D[k]).all() for k in ("cost_center_owner", "cost_center_name", "legal_entity", "entity_code", "gl_account")) else "different",
            all(bool((c[k] == D[k]).all()) for k in ("cost_center_owner", "cost_center_name", "legal_entity", "entity_code", "gl_account")))
        sp = c.loc[c["sign_pattern"] != "", "sign_pattern"]
        rec("RB25", "Saved CSV: sign_pattern uses only P/N/Z/_ (5 characters, never a leading + - = @)", f"{len(sp):,} valid",
            f"{int(sp.str.fullmatch(r'[PNZ_]{5}').sum()):,} valid", bool(sp.str.fullmatch(r"[PNZ_]{5}").all()))
        trip = []
        for k in ("amount_local", "actual_usd", "budget_usd", "forecast_usd", "prior_year_usd"):
            trip.append(all(x in c.columns for x in (f"{k}_parsed", f"{k}_adj", f"{k}_status", f"{k}_format")))
        rec("RB26", "Saved CSV: as-reported text (*_raw source column), *_parsed, *_adj, *_status are four distinct columns for each of the 5 amounts",
            "5 of 5", f"{sum(trip)} of 5", all(trip))
        lead = 0
        for k in ("line_text", "cost_center_name", "legal_entity", "notes", "document_no"):
            if k in c.columns:
                lead += int(c[k].str.match(r"^[=+\-@]").sum())
        rec("RB27", "Saved CSV: formula-leading text (= + - @) in selected free-text fields is reported (informational: raw text is preserved unchanged)", "reported", f"{lead} cells", True)
        ce = None
        del c
    except Exception as exc:  # noqa: BLE001
        rec("RB01", "Cleaned CSV could be re-read", "readable", f"ERROR {exc}", False)
    try:
        ac = pd.read_csv(paths["audit"], dtype=str, keep_default_na=False, encoding="utf-8-sig")
        rec("RB08", "Audit CSV reopens; row count equals audit rows generated", ctx.facts.get("audit_rows"), len(ac), len(ac) == ctx.facts.get("audit_rows"))
    except Exception as exc:  # noqa: BLE001
        rec("RB08", "Audit CSV could be re-read", "readable", f"ERROR {exc}", False)
    # Excel
    if "xlsx" not in paths:
        log.info("Read-back validation done in %.1fs (Excel not written)", time.time() - t0)
        return pd.DataFrame(out)
    try:
        import openpyxl
        wb = openpyxl.load_workbook(paths["xlsx"], read_only=True, data_only=True)
        names = wb.sheetnames
        expected = ["README", "QC_Summary", "DQ_Findings", "Exclusion_Summary", "Cleaned_Data", "Non_Posting_Rows", "Junk_Entity_Rows",
                    "Exceptions", "Scale_Evidence", "FX_Evidence", "Amount_Parse_Evidence", "Date_Resolution", "Duplicate_Review",
                    "Flag_Counts", "Mappings", "Column_Profile", "Schema_Map", "Count_Reconciliation", "Transformation_Log", "Validation_Checks", "Open_Items"]
        rec("RB09", "Workbook reopens with all expected sheets in order", len(expected), len(names), names == expected)
        ws = wb["Cleaned_Data"]
        hdr = None
        nrows = 0
        s_adj = 0.0
        n_elig = 0
        first_ids, last_id = [], None
        i_adj = i_el = i_id = i_own = None
        n_own = 0
        limit = None if full_excel else 2000
        for r in ws.iter_rows(values_only=True):
            if hdr is None:
                hdr = list(r)
                i_adj, i_el, i_id = hdr.index("actual_usd_adj"), hdr.index("eligible_PL_actual"), hdr.index("row_id")
                i_own = hdr.index("cost_center_owner") if "cost_center_owner" in hdr else None
                continue
            nrows += 1
            v = r[i_adj]
            if isinstance(v, (int, float)):
                s_adj += v
            if r[i_el] == 1:
                n_elig += 1
            if i_own is not None and r[i_own] not in (None, ""):
                n_own += 1
            if nrows <= 3:
                first_ids.append(r[i_id])
            last_id = r[i_id]
            if limit and nrows >= limit:
                break
        rec("RB10", "Cleaned_Data header equals expected columns", len(EXCEL_CLEANED_COLUMNS), len(hdr or []), hdr == EXCEL_CLEANED_COLUMNS)
        if full_excel:
            rec("RB11", "Cleaned_Data data rows equal raw rows", ctx.n, nrows, nrows == ctx.n)
            b = float(np.nansum(D["actual_usd_adj"].to_numpy(dtype=float)))
            rec("RB12", "Sum of actual_usd_adj in the workbook equals in-memory", f"{b:,.4f}", f"{s_adj:,.4f}", bool(np.isclose(s_adj, b, rtol=1e-9, atol=1e-4)))
            rec("RB13", "Eligible (P&L actual) rows in the workbook equal in-memory", int(D["eligible_PL_actual"].sum()), n_elig, n_elig == int(D["eligible_PL_actual"].sum()))
            n_own_mem = int((D["cost_center_owner"] != "").sum())
            rec("RB21", "Workbook shows cost_center_owner (previously omitted): non-blank count equals in-memory", n_own_mem, n_own if i_own is not None else "column missing",
                i_own is not None and n_own == n_own_mem)
            rec("RB14", "First and last row_id in the workbook", f"{D['row_id'].iloc[0]} ... {D['row_id'].iloc[-1]}", f"{first_ids[:1]} ... {last_id}",
                first_ids[:1] == [D["row_id"].iloc[0]] and last_id == D["row_id"].iloc[-1])
        else:
            rec("RB11", "(partial read) first rows of Cleaned_Data match", D["row_id"].iloc[:3].tolist(), first_ids, first_ids == D["row_id"].iloc[:3].tolist())
        for nm_, cnt in (("Non_Posting_Rows", int(D["flag_nonposting"].sum())),):
            w2 = wb[nm_]
            # title row + header + data rows  -> count non-empty rows
            rows_nonempty = 0
            for r in w2.iter_rows(values_only=True):
                if any(x is not None for x in r):
                    rows_nonempty += 1
            rec("RB15", f"{nm_}: data rows (non-empty rows minus title and header)", cnt, rows_nonempty - 2, rows_nonempty - 2 == cnt)
        # saved-workbook cross-sheet checks
        try:
            st_vals = []
            for r in wb["Count_Reconciliation"].iter_rows(values_only=True):
                if r and any(x in ("RECONCILED", "DIFFERENCE") for x in r):
                    st_vals.append([x for x in r if x in ("RECONCILED", "DIFFERENCE")][-1])
            rec("RB22", "Saved workbook, Count_Reconciliation: every row RECONCILED", f"{len(st_vals)} x RECONCILED",
                f"{st_vals.count('RECONCILED')} RECONCILED / {st_vals.count('DIFFERENCE')} DIFFERENCE", len(st_vals) > 0 and st_vals.count("DIFFERENCE") == 0)
            n_schema = sum(1 for r in wb["Schema_Map"].iter_rows(min_row=3, values_only=True) if r and isinstance(r[0], (int, float)))
            rec("RB23", "Saved workbook, Schema_Map: one row per canonical CSV column", D.shape[1], n_schema, n_schema == D.shape[1])
            thdr = next(([x for x in r] for r in wb["Transformation_Log"].iter_rows(min_row=1, max_row=8, values_only=True) if r and r[0] == "rule_id"), [])
            rec("RB24", "Saved workbook, Transformation_Log header carries the separated count definitions",
                "cells_processed, cells_changed, distinct_rows_affected, pct_rows_affected", ", ".join(str(x) for x in thdr[2:6]),
                thdr[2:6] == ["cells_processed", "cells_changed", "distinct_rows_affected", "pct_rows_affected"])
        except Exception as exc:  # noqa: BLE001
            rec("RB22", "Saved workbook cross-sheet checks could be run", "readable", f"ERROR {exc}", False)
        wb.close()
    except Exception as exc:  # noqa: BLE001
        rec("RB09", "Workbook could be re-read", "readable", f"ERROR {exc}", False)
    log.info("Read-back validation done in %.1fs", time.time() - t0)
    return pd.DataFrame(out)


# =============================================================================
# 14. QC REPORT AND MAIN
# =============================================================================
def resolve_output_dir(cli_dir: Optional[str]) -> Path:
    if cli_dir:
        target = Path(cli_dir).expanduser()
    else:
        target = Path.home() / "Downloads" / OUTPUT_FOLDER_NAME
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return target.resolve()
    except OSError as exc:
        fallback = Path.cwd() / OUTPUT_FOLDER_NAME
        log.warning("Cannot write to %s (%s). Falling back to %s", target, exc, fallback)
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except OSError as exc2:
            raise PipelineError(f"No writable output folder (tried {target} and {fallback}): {exc2}") from exc2
        return fallback.resolve()


def _df_text(df: pd.DataFrame, max_rows: int = 80) -> str:
    if df is None or len(df) == 0:
        return "(none)"
    with pd.option_context("display.width", 220, "display.max_columns", 30, "display.max_colwidth", 70):
        return df.head(max_rows).to_string(index=False)


def render_qc_report(ctx: Ctx, integrity: Dict[str, object], tables: Dict[str, object], readback: pd.DataFrame,
                     runinfo: Dict[str, object], paths: Dict[str, Path], raw_unchanged: bool) -> str:
    D, F = ctx.D, ctx.facts
    L = []
    add = L.append
    add("=" * 100)
    add("QC REPORT - fpa_monthly_close cleaning")
    add("=" * 100)
    add(f"script version      : {SCRIPT_VERSION}")
    add(f"run timestamp       : {runinfo['timestamp']}")
    add(f"python / pandas / numpy : {runinfo['python']} / {pd.__version__} / {np.__version__}")
    add(f"input file          : {integrity['path']}")
    add(f"input bytes         : {integrity['bytes']:,} (expected {EXPECTED_BYTES:,})")
    add(f"input sha256        : {integrity['sha256']}")
    add(f"hash matches expected: {integrity['hash_match']}")
    add(f"raw file unchanged after run (hash re-computed): {raw_unchanged}")
    add(f"rows in / out       : {ctx.n:,} / {len(D):,}  (no row deleted)")
    add(f"columns raw / cleaned CSV / Excel sheet: {ctx.raw.shape[1]} / {D.shape[1]} / {len(EXCEL_CLEANED_COLUMNS)}")
    add(f"settings            : APPLY_SCALE_RESTORATION={APPLY_SCALE_RESTORATION}, REMOVE_FIELD_MATCH_DUPLICATES={REMOVE_FIELD_MATCH_DUPLICATES}, "
        f"eligible statuses={ELIGIBLE_APPROVAL_STATUSES}, z bands divided<={Z_DIVIDED_MAX} / undivided>={Z_UNDIVIDED_MIN}")
    add("")
    add("OUTPUT FILES (size and SHA-256 of the exact files that were re-read below)")
    for k, p in paths.items():
        try:
            hh = sha256_file(Path(p)) if Path(p).suffix.lower() in (".csv", ".xlsx") else "-"
            add(f"  {k:8s}: {p}  ({Path(p).stat().st_size:,} bytes)  sha256={hh}")
        except OSError:
            add(f"  {k:8s}: {p}")
    add(f"  CANONICAL cleaned dataset: the 'csv' file above ({D.shape[1]} columns, {len(D):,} rows). The xlsx Cleaned_Data sheet is a {len(EXCEL_CLEANED_COLUMNS)}-column review copy.")
    add("  Reported totals are PROVISIONAL (Posted-only rule R6 is proposed, not confirmed).")
    add("")
    add("ROW ACCOUNTING (one primary exclusion reason per row; precedence from docs/FINANCIAL_METRICS.md section 4)")
    add(_df_text(tables["excl"]))
    add("")
    add("FINDINGS BY PRIORITY TIER, THEN USD AT STAKE (full list in the DQ_Findings sheet)")
    add(_df_text(tables["findings"][["rank", "finding_id", "priority_tier", "finding", "classification", "rows", "row_basis", "impact_usd"]], 50))
    add("")
    add("COUNT RECONCILIATION - Column_Profile (all rows) vs DQ_Findings / Flag_Counts (posting rows)")
    add(_df_text(tables["recon1"].drop(columns=["explanation"])))
    add("")
    add("VALIDATION CHECKS (in memory, before writing)")
    add(_df_text(tables["validation"][["check_id", "check", "expected", "actual", "result"]], 100))
    add("")
    add("READ-BACK VALIDATION OF THE FILES THAT WERE WRITTEN")
    add(_df_text(readback[["check_id", "check", "expected", "actual", "result"]], 100))
    add("")
    add("OPEN ITEMS / DECISIONS FOR THE OWNER")
    for r in tables["open_items"].itertuples():
        add(f"- {r.topic}: {r._2} | {r._3} | NEXT: {r._4}")
    add("")
    add("LIMITS OF THIS CHECK")
    add("- The scale decision for rows without the price identity (outside GL 4100/5100 or without qty/product) rests on a peer z-score. It is validated on the")
    add("  identity rows only; its expected error is stated in Scale_Evidence. Rows between the bands are left undetermined.")
    add("- Joint business rules (duplicate removal, sign convention, blank-status meaning, consolidation) are NOT decided here. They are flagged, not applied.")
    add("- 'impact_usd' in DQ_Findings is USD at stake, defined per finding, not a booked error.")
    add("- The script was executed and its outputs re-read, but it cannot prove that the data is correct, only that the stated rules were applied consistently.")
    return "\n".join(L)


def make_tables(ctx: Ctx, integrity: Dict[str, object], raw_profile: pd.DataFrame, runinfo: Dict[str, object]) -> Dict[str, object]:
    D, F = ctx.D, ctx.facts
    findings = build_findings(ctx)
    excl, excl_detail = build_exclusion_summary(ctx)
    validation = build_validation(ctx, integrity)
    colprofile = build_column_profile(ctx, raw_profile)
    flag_counts = build_flag_counts(ctx)
    recon1, recon2 = build_count_reconciliation(ctx, findings, flag_counts, colprofile)
    schema_map = build_schema_map(ctx, EXCEL_CLEANED_COLUMNS)
    validation = pd.concat([validation, pd.DataFrame(extra_validation(ctx, findings, excl, recon1, recon2, schema_map, EXCEL_CLEANED_COLUMNS))],
                           ignore_index=True)
    n_ut = int(((D["report_scale_label"] == "Thousands") & (D["scale_decision"] == "UNDIVIDED")).sum())
    tail = F.get("actual_tail_rate_other_gl", float("nan"))
    scale_notes = pd.DataFrame([
        ("Z bands", f"divided if z <= {Z_DIVIDED_MAX}; undivided if z >= {Z_UNDIVIDED_MIN}; otherwise undetermined (valley between clusters is -4.5 to -3.0)."),
        ("Baseline", f"median and robust sd (p10-p90) of log10 |USD| of rows believed undivided, per GL x entity (n >= {BASELINE_MIN_GROUP}), else per GL."),
        ("Expected wrong restorations", f"about {tail * n_ut:.1f} undivided 'Thousands' rows may sit in the natural left tail (tail rate {tail * 100:.3f}% x {n_ut} undivided Thousands rows)."),
        ("Not validated", "Actual-labelled rows outside GL 4100/5100 are treated as undivided because every identity-testable Actual-labelled row was undivided; a small hidden-division population there cannot be excluded."),
        ("Rounding", "Restored values inherit the rounding of the divided source (up to +/-0.005 x divisor per amount; see actual_usd_adj_abs_uncertainty)."),
        ("Identity rows used", f"{F['identity_usable']:,} rows tested; {F['identity_nomatch']} matched neither 1, 1/1,000 nor 1/100,000."),
    ], columns=["item", "note"])
    vs = validation["result"].value_counts()
    validation_summary = pd.DataFrame({"result": ["PASS", "FAIL"], "checks": [int(vs.get("PASS", 0)), int(vs.get("FAIL", 0))]})
    kv = pd.DataFrame([
        ("script version", SCRIPT_VERSION), ("run timestamp", runinfo["timestamp"]), ("input file", integrity["path"]),
        ("SHA-256 verified", str(integrity["hash_match"])), ("rows in / out", f"{ctx.n:,} / {len(D):,}"),
        ("columns raw / canonical cleaned CSV / review workbook Cleaned_Data", f"{ctx.raw.shape[1]} / {D.shape[1]} / {len(EXCEL_CLEANED_COLUMNS)}"),
        ("CANONICAL cleaned dataset", f"{OUTPUT_BASENAME}.csv ({D.shape[1]} columns, all {ctx.n:,} rows). The workbook is a review copy (subset of columns); see Schema_Map."),
        ("reported-total basis", "PROVISIONAL: ELIGIBLE = journal status 'Posted' only (proposed rule R6; blank / Pending / Rejected / Parked unresolved)"),
        ("non-posting rows", int(D["flag_nonposting"].sum())), ("junk-entity rows", int(D["flag_junk_entity"].sum())),
        ("unresolvable-entity rows", int(D["flag_entity_unresolved"].sum())),
        ("scale restored / undetermined", f"{int(D['flag_scale_restored'].sum()):,} / {int(D['flag_scale_undetermined'].sum())}"),
        ("duplicate candidates: field match, same sign (kept, flagged)", int(D["flag_dup_field_match_same_sign"].sum())),
        ("duplicate candidates: field match, SIGN CONFLICT (kept, flagged)", int(D["flag_dup_field_match_sign_conflict"].sum())),
        ("eligible rows P&L actual", int(D["eligible_PL_actual"].sum())),
        ("eligible rows P&L variance", int(D["eligible_PL_variance"].sum())),
        ("eligible rows Balance Sheet actual", int(D["eligible_BS_actual"].sum())),
        ("APPLY_SCALE_RESTORATION", str(APPLY_SCALE_RESTORATION)), ("REMOVE_FIELD_MATCH_DUPLICATES", str(REMOVE_FIELD_MATCH_DUPLICATES)),
        ("validation checks passed / failed", f"{int(vs.get('PASS', 0))} / {int(vs.get('FAIL', 0))}"),
    ], columns=["item", "value"])
    qc_waterfall = excl[excl["scope"] == "PL_actual"][["step", "primary_reason", "rows", "share_of_all_rows_%", "sum_abs_actual_usd_adj",
                                                         "sum_abs_actual_usd_parsed_as_reported"]]
    return {
        "findings": findings, "excl": excl, "excl_detail": excl_detail, "validation": validation,
        "validation_summary": validation_summary, "qc_kv": kv, "qc_waterfall": qc_waterfall,
        "scale_notes": scale_notes, "flag_counts": flag_counts,
        "column_profile": colprofile, "recon1": recon1, "recon2": recon2, "schema_map": schema_map,
        "exceptions": build_exceptions(ctx, EXCEL_MAX_ROWS_EXCEPTIONS),
        "open_items": build_open_items(ctx, findings),
    }


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Clean and audit fpa_monthly_close_raw_messy.csv (no row is deleted; raw file untouched).")
    ap.add_argument("--input", help=f"path to {INPUT_FILE_NAME} (default: searched automatically)")
    ap.add_argument("--output-dir", help="output folder (default: <Downloads>/%s)" % OUTPUT_FOLDER_NAME)
    ap.add_argument("--no-excel-readback", action="store_true", help="read back only the first rows of the big Excel sheet (faster)")
    ap.add_argument("--skip-excel", action="store_true", help="do not write the Excel workbook (development only)")
    ap.add_argument("--skip-integrity-gate", action="store_true",
                    help="FOR SYNTHETIC TEST FIXTURES ONLY: do not stop on a hash/size/row-count mismatch (outputs are marked UNVERIFIED)")
    return ap.parse_args(argv)


def publish_run_log(out_dir: Path) -> None:
    """Close the in-progress log file and publish it as run_log.txt (a failed run leaves run_log.new.txt and the previous run_log.txt untouched)."""
    lg = logging.getLogger("fpa_clean")
    for h in list(lg.handlers):
        if isinstance(h, logging.FileHandler) and Path(h.baseFilename).name == "run_log.new.txt":
            h.flush()
            h.close()
            lg.removeHandler(h)
    src = out_dir / "run_log.new.txt"
    if src.exists():
        try:
            finalize_output(src, out_dir / "run_log.txt")
        except OSError as exc:
            log.warning("Could not publish run_log.txt: %s", exc)


def run_pipeline(args) -> int:
    t_start = time.time()
    in_path = find_input_file(args.input)
    if in_path.stat().st_size == 0:
        raise PipelineError(f"The input file is empty (0 bytes): {in_path}\nNothing was cleaned and nothing was written.")
    enforce = not args.skip_integrity_gate
    integrity = integrity_gate(in_path, enforce=enforce)          # STOPS here on a mismatch
    runinfo = {"timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "python": sys.version.split()[0]}
    # The raw file is validated BEFORE the output folder is touched, so a bad input can never
    # overwrite or disturb outputs from an earlier valid run.
    with StepTimer("load raw file"):
        raw = load_raw(in_path, enforce=enforce)
    out_dir = resolve_output_dir(args.output_dir)
    attach_file_log(out_dir / "run_log.new.txt")      # published as run_log.txt only when the run succeeds
    log.info("Output folder: %s", out_dir)
    log.info("Raw file %s sha256=%s hash_match=%s", in_path, integrity["sha256"], integrity["hash_match"])
    if not enforce:
        log.warning("INTEGRITY GATE SKIPPED - outputs are UNVERIFIED test outputs")
    ctx_raw_path = str(in_path)
    with StepTimer("raw column profile"):
        raw_profile = profile_columns(raw)
    ctx = clean_dataset(raw)
    ctx.facts["raw_path"] = ctx_raw_path
    with StepTimer("report tables and validation"):
        tables = make_tables(ctx, integrity, raw_profile, runinfo)
    fails = tables["validation"][tables["validation"]["result"] == "FAIL"]
    if len(fails):
        log.warning("%d in-memory validation check(s) FAILED:\n%s", len(fails), _df_text(fails[["check_id", "check", "expected", "actual"]]))
    paths: Dict[str, Path] = {}
    with StepTimer("write CSV outputs"):
        paths.update(write_csv_outputs(out_dir, ctx))
    if not args.skip_excel:
        xp_tmp = out_dir / f"{OUTPUT_BASENAME}.xlsx.partial"
        readme = build_readme_lines(ctx, integrity, tables["findings"], tables["excl"], runinfo)
        with StepTimer("write Excel workbook (large; please wait)"):
            write_workbook(xp_tmp, ctx, tables, readme)
        paths["xlsx"] = finalize_output(xp_tmp, out_dir / f"{OUTPUT_BASENAME}.xlsx")
    with StepTimer("read back written files"):
        readback = readback_validate(paths, ctx, full_excel=not args.no_excel_readback)
    raw_hash_after = sha256_file(in_path)
    raw_unchanged = (raw_hash_after == integrity["sha256"])
    log.info("Raw file hash after run unchanged: %s", raw_unchanged)
    report = render_qc_report(ctx, integrity, tables, readback, runinfo, paths, raw_unchanged)
    rp_tmp = out_dir / "QC_Report.txt.partial"
    rp_tmp.write_text(report, encoding="utf-8")
    rp = finalize_output(rp_tmp, out_dir / "QC_Report.txt")
    paths["qc_report"] = rp
    summary = {
        "script_version": SCRIPT_VERSION, "timestamp": runinfo["timestamp"], "integrity": integrity,
        "rows": ctx.n, "columns_cleaned_csv": int(ctx.D.shape[1]),
        "exclusion_counts": {k: v for k, v in ctx.facts.items() if str(k).startswith("excl_counts_")},
        "validation": tables["validation"].to_dict(orient="records"),
        "readback": readback.to_dict(orient="records"),
        "raw_unchanged": bool(raw_unchanged), "seconds": round(time.time() - t_start, 1),
    }
    sp_tmp = out_dir / "qc_summary.json.partial"
    sp_tmp.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    sp = finalize_output(sp_tmp, out_dir / "qc_summary.json")
    paths["qc_summary"] = sp
    n_fail = int((tables["validation"]["result"] == "FAIL").sum() + (readback["result"] == "FAIL").sum())
    log.info("=" * 70)
    log.info("FINISHED in %.0fs. Output folder: %s", time.time() - t_start, out_dir)
    for k, p in paths.items():
        log.info("  %-10s %s", k, p)
    log.info("Validation: %d in-memory + %d read-back checks, %d FAILED", len(tables["validation"]), len(readback), n_fail)
    if n_fail:
        log.warning("Some checks FAILED - read QC_Report.txt before using the output.")
    publish_run_log(out_dir)
    return 0 if n_fail == 0 else 3


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    setup_logging()
    args = parse_args(argv)
    try:
        return run_pipeline(args)
    except IntegrityError as exc:
        print("\n" + str(exc))
        return 2
    except PipelineError as exc:
        log.error("%s", exc)
        return 1
    except PermissionError as exc:
        log.error("Permission problem: %s (close the file in Excel and run again)", exc)
        return 1
    except MemoryError:
        log.error("Out of memory. Close other programs and run again (the data needs about 3 GB of RAM).")
        return 1
    except Exception:  # noqa: BLE001
        log.error("Unexpected error:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
