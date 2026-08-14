from __future__ import annotations

import pandas as pd


REQUIRED_PAIRS_COLUMNS = {
    "trade_date",
    "underlying_symbol",
    "underlying_symbol_raw",
    "security_id",
    "expiry_date",
    "contract_identifier",
    "lot_size",
    "open",
    "high",
    "low",
    "close",
    "settlement_price",
    "volume",
    "open_interest",
}


def validate_pairs_contract_history(df: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_PAIRS_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"pairs_lab_contract_history missing columns: {missing}")
    if df.empty:
        raise ValueError("pairs_lab_contract_history is empty")
    if df["lot_size"].isna().any() or (df["lot_size"] <= 0).any():
        raise ValueError("Invalid lot_size")
    if df[["trade_date", "contract_identifier"]].duplicated().any():
        raise ValueError("Duplicate trade_date + contract_identifier")
    if pd.to_datetime(df["expiry_date"]).lt(pd.to_datetime(df["trade_date"])).any():
        raise ValueError("Invalid expiry before trade_date")
    if (df["security_id"].astype(str).str.len() == 0).any():
        raise ValueError("Unresolved identity")
