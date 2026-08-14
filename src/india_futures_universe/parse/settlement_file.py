from __future__ import annotations

from pathlib import Path

import pandas as pd

from india_futures_universe.parse.common import ParseError, normalize_columns, parse_date_column, read_csv_payload, to_numeric


def parse_settlement_file(path: str | Path, *, source_sha256: str = "") -> pd.DataFrame:
    raw = normalize_columns(read_csv_payload(path))
    symbol_col = _find(raw, ("SYMBOL", "TCKR_SYMB", "UNDERLYING_SYMBOL"))
    expiry_col = _find(raw, ("EXPIRY_DT", "XPRY_DT", "EXPIRY_DATE"))
    price_col = _find(raw, ("SETTLE_PR", "SETTLEMENT_PRICE", "STTLM_PRIC"))
    instrument_col = _find(raw, ("INSTRUMENT", "INSTRUMENT_TYPE", "FINSTRM_TP"))
    if not symbol_col or not expiry_col or not price_col:
        raise ParseError("FO_DAILY_SETTLEMENT schema unresolved")
    out = pd.DataFrame(
        {
            "instrument_type": raw[instrument_col].astype(str).str.strip() if instrument_col else "",
            "underlying_symbol_raw": raw[symbol_col].astype(str).str.strip(),
            "expiry_date": parse_date_column(raw[expiry_col]),
            "settlement_report_price": to_numeric(raw[price_col], price_col),
            "source_format": "FO_DAILY_SETTLEMENT",
            "source_filename": Path(path).name,
            "source_sha256": source_sha256,
            "raw_row_number": raw.index + 1,
        }
    )
    return out


def _find(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    normalized_aliases = {alias.upper().replace(" ", "_") for alias in aliases}
    for col in df.columns:
        if col in normalized_aliases:
            return col
    return None
