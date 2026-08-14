from __future__ import annotations

from pathlib import Path

import pandas as pd

from india_futures_universe.parse.common import normalize_columns, parse_date_column, read_csv_payload, require_columns, to_numeric


LEGACY_COLUMNS = {
    "INSTRUMENT",
    "SYMBOL",
    "EXPIRY_DT",
    "STRIKE_PR",
    "OPTION_TYP",
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
    "SETTLE_PR",
    "CONTRACTS",
    "VAL_INLAKH",
    "OPEN_INT",
    "CHG_IN_OI",
}


def parse_legacy_bhavcopy(path: str | Path, *, source_sha256: str = "") -> pd.DataFrame:
    raw = normalize_columns(read_csv_payload(path))
    require_columns(raw, LEGACY_COLUMNS, "LEGACY_FO_BHAVCOPY")
    out = pd.DataFrame(
        {
            "instrument_type": raw["INSTRUMENT"].astype(str).str.strip(),
            "underlying_symbol_raw": raw["SYMBOL"].astype(str).str.strip(),
            "expiry_date": parse_date_column(raw["EXPIRY_DT"]),
            "strike_price": to_numeric(raw["STRIKE_PR"], "STRIKE_PR"),
            "option_type": raw["OPTION_TYP"].astype(str).str.strip(),
            "open": to_numeric(raw["OPEN"], "OPEN"),
            "high": to_numeric(raw["HIGH"], "HIGH"),
            "low": to_numeric(raw["LOW"], "LOW"),
            "close": to_numeric(raw["CLOSE"], "CLOSE"),
            "settlement_price": to_numeric(raw["SETTLE_PR"], "SETTLE_PR"),
            "contracts_traded": to_numeric(raw["CONTRACTS"], "CONTRACTS").astype("int64"),
            "turnover_inr": to_numeric(raw["VAL_INLAKH"], "VAL_INLAKH") * 100000,
            "open_interest_contracts": to_numeric(raw["OPEN_INT"], "OPEN_INT").astype("int64"),
            "change_in_open_interest_contracts": to_numeric(raw["CHG_IN_OI"], "CHG_IN_OI").astype("int64"),
            "source_format": "LEGACY_FO_BHAVCOPY",
            "source_filename": Path(path).name,
            "source_sha256": source_sha256,
            "raw_row_number": raw.index + 1,
        }
    )
    trade_date_cols = [col for col in raw.columns if col in {"TIMESTAMP", "TRADE_DATE", "DATE"}]
    out["trade_date"] = parse_date_column(raw[trade_date_cols[0]]) if trade_date_cols else ""
    out["exchange_instrument_id"] = ""
    out["underlying_value"] = pd.NA
    return out
