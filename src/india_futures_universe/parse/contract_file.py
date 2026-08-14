from __future__ import annotations

from pathlib import Path

import pandas as pd

from india_futures_universe.parse.common import ParseError, normalize_columns, parse_date_column, read_csv_payload, to_numeric, to_optional_numeric


CONTRACT_ALIASES = {
    "instrument_type": ("INSTRUMENT", "INSTRUMENT_TYPE", "INSTRUMENT_NAME", "FININSTRMNM", "FININSTRMTP", "FINSTRM_TP"),
    "exchange_instrument_id": ("FININSTRMID", "FINSTRM_ID", "TOKEN", "INSTRUMENT_ID", "EXCHANGE_INSTRUMENT_ID"),
    "underlying_symbol_raw": ("SYMBOL", "TCKRSYMB", "TCKR_SYMB", "UNDERLYING_SYMBOL", "UNDLYG_SYMB"),
    "expiry_date": ("EXPIRY_DT", "XPRYDT", "XPRY_DT", "EXPIRY_DATE"),
    "strike_price": ("STRIKE_PR", "STRIKE_PRICE", "STRKPRIC", "STRK_PRIC"),
    "option_type": ("OPTION_TYP", "OPTION_TYPE", "OPTNTP", "OPTN_TYP"),
    "market_lot": ("MARKET_LOT", "LOT_SIZE", "MINLOT", "NEWBRDLOTQTY", "MIN_LOT", "CONTRACT_MULTIPLIER"),
    "tick_size": ("TICK_SIZE", "TCK_SZ", "BIDINTRVL"),
    "quantity_freeze": ("QTY_FRZ", "QUANTITY_FREEZE", "FREEZE_QTY", "FRZ_QTY", "MAXTRADQTY"),
}


def parse_contract_file(path: str | Path, *, as_of_date: str, source_sha256: str = "") -> pd.DataFrame:
    raw = normalize_columns(read_csv_payload(path))
    resolved = {target: _find(raw, aliases) for target, aliases in CONTRACT_ALIASES.items()}
    missing = [target for target in ["instrument_type", "underlying_symbol_raw", "expiry_date", "market_lot"] if resolved[target] is None]
    if missing:
        raise ParseError(f"MII_FO_CONTRACT_FILE schema unresolved for: {missing}")
    out = pd.DataFrame(
        {
            "as_of_date": as_of_date,
            "exchange": "NSE",
            "segment": "FO",
            "instrument_type": raw[resolved["instrument_type"]].astype(str).str.strip().map(_contract_instrument_type),
            "exchange_instrument_id": raw[resolved["exchange_instrument_id"]].astype(str).str.strip() if resolved["exchange_instrument_id"] else "",
            "underlying_symbol_raw": raw[resolved["underlying_symbol_raw"]].astype(str).str.strip(),
            "expiry_date": parse_date_column(raw[resolved["expiry_date"]]),
            "strike_price": _numeric_or_default(raw, resolved["strike_price"], "strike_price", 0.0),
            "option_type": raw[resolved["option_type"]].astype(str).str.strip() if resolved["option_type"] else "",
            "market_lot": to_numeric(raw[resolved["market_lot"]], resolved["market_lot"]).astype("int64"),
            "tick_size": _numeric_or_default(raw, resolved["tick_size"], "tick_size", pd.NA),
            "quantity_freeze": _numeric_or_default(raw, resolved["quantity_freeze"], "quantity_freeze", pd.NA),
            "contract_status": "LISTED",
            "raw_contract_key": raw.astype(str).agg("|".join, axis=1),
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


def _numeric_or_default(df: pd.DataFrame, col: str | None, label: str, default):
    if col is None:
        return pd.Series([default] * len(df), index=df.index)
    return to_optional_numeric(df[col], default=default)


def _contract_instrument_type(value: str) -> str:
    upper = value.upper()
    if upper.startswith("FUTSTK"):
        return "FUTSTK"
    if upper.startswith("FUTIDX"):
        return "FUTIDX"
    if upper.startswith("OPTSTK"):
        return "OPTSTK"
    if upper.startswith("OPTIDX"):
        return "OPTIDX"
    mapping = {"STF": "FUTSTK", "STO": "OPTSTK", "IDF": "FUTIDX", "IDO": "OPTIDX"}
    return mapping.get(upper, upper)
