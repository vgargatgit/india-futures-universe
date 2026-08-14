from __future__ import annotations

import gzip
import io
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd


class ParseError(ValueError):
    pass


def read_csv_payload(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    payload = path.read_bytes()
    if payload.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_members = [name for name in archive.namelist() if name.lower().endswith((".csv", ".txt"))]
            if len(csv_members) != 1:
                raise ParseError(f"Expected one CSV/TXT member, found {csv_members}")
            with archive.open(csv_members[0]) as handle:
                return pd.read_csv(handle)
    if payload.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as handle:
            return pd.read_csv(handle)
    return pd.read_csv(io.BytesIO(payload))


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip().upper().replace(" ", "_") for col in out.columns]
    return out


def require_columns(df: pd.DataFrame, columns: Iterable[str], source_format: str) -> None:
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ParseError(f"{source_format} missing mandatory columns: {missing}")


def parse_date_column(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all() and (numeric > 1_000_000_000).all():
        parsed = pd.to_datetime(numeric, errors="coerce", unit="s")
    elif series.astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$").all():
        parsed = pd.to_datetime(series, errors="coerce", format="%Y-%m-%d")
    else:
        parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    if parsed.isna().any():
        raise ParseError("Invalid date value")
    return parsed.dt.date.astype(str)


def to_numeric(series: pd.Series, column: str) -> pd.Series:
    parsed = pd.to_numeric(series, errors="coerce")
    if parsed.isna().any():
        raise ParseError(f"Invalid numeric value in {column}")
    return parsed


def to_optional_numeric(series: pd.Series, *, default=0) -> pd.Series:
    cleaned = series.replace({"": default, "-": default, "XX": default, "nan": default})
    return pd.to_numeric(cleaned, errors="coerce").fillna(default)
