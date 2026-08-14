from __future__ import annotations

from pathlib import Path

import pandas as pd

from india_futures_universe.parse.common import ParseError, normalize_columns, parse_date_column, read_csv_payload, to_numeric, to_optional_numeric


UDIFF_ALIASES = {
    "trade_date": ("TRAD_DT", "TRADDT", "TRADE_DATE"),
    "instrument_type": ("INSTRUMENT", "INSTRUMENT_TYPE", "INST_TYP", "FININSTRMTP", "FINSTRM_TP"),
    "underlying_symbol_raw": ("SYMBOL", "TCKRSYMB", "TCKR_SYMB", "UNDERLYING_SYMBOL", "UNDLYG_SYMB"),
    "expiry_date": ("EXPIRY_DT", "XPRYDT", "XPRY_DT", "EXPIRY_DATE"),
    "strike_price": ("STRIKE_PR", "STRIKE_PRICE", "STRKPRIC", "STRK_PRIC"),
    "option_type": ("OPTION_TYP", "OPTION_TYPE", "OPTNTP", "OPTN_TYP"),
    "open": ("OPEN", "OPEN_PRICE", "OPNPRIC", "OPN_PRIC"),
    "high": ("HIGH", "HIGH_PRICE", "HGHPRIC", "HGH_PRIC"),
    "low": ("LOW", "LOW_PRICE", "LWPRIC", "LW_PRIC"),
    "close": ("CLOSE", "CLOSE_PRICE", "CLSPRIC", "CLS_PRIC"),
    "settlement_price": ("SETTLE_PR", "SETTLEMENT_PRICE", "STTLMPRIC", "STTLM_PRIC"),
    "contracts_traded": ("CONTRACTS", "NO_OF_CONTRACTS", "TTLTRADGVOL", "TTLNB_OF_CTRCTS_TRAD"),
    "turnover_inr": ("TURNOVER_INR", "VAL_INR", "TTLTRFVAL"),
    "open_interest_contracts": ("OPEN_INT", "OPEN_INTEREST", "OPNINTRST"),
    "change_in_open_interest_contracts": ("CHG_IN_OI", "CHANGE_IN_OI", "CHNGINOPNINTRST"),
    "exchange_instrument_id": ("FININSTRMID", "FINSTRM_ID", "EXCHANGE_INSTRUMENT_ID", "INSTRUMENT_ID"),
    "underlying_value": ("UNDERLYING_VALUE", "UNDRLYGPRIC", "UNDLYG_STTL_PRIC"),
}


def parse_udiff_bhavcopy(path: str | Path, *, source_sha256: str = "") -> pd.DataFrame:
    raw = normalize_columns(read_csv_payload(path, usecols_normalized=_needed_columns(UDIFF_ALIASES)))
    resolved = {target: _find(raw, aliases) for target, aliases in UDIFF_ALIASES.items()}
    mandatory = [
        "trade_date",
        "instrument_type",
        "underlying_symbol_raw",
        "expiry_date",
        "open",
        "high",
        "low",
        "close",
        "settlement_price",
        "contracts_traded",
        "open_interest_contracts",
    ]
    missing = [target for target in mandatory if resolved[target] is None]
    if missing:
        raise ParseError(f"UDIFF_FO_BHAVCOPY schema unresolved for: {missing}")
    out = pd.DataFrame(
        {
            "trade_date": parse_date_column(raw[resolved["trade_date"]]),
            "instrument_type": raw[resolved["instrument_type"]].astype(str).str.strip().map(_udiff_instrument_type),
            "underlying_symbol_raw": raw[resolved["underlying_symbol_raw"]].astype(str).str.strip(),
            "expiry_date": parse_date_column(raw[resolved["expiry_date"]]),
            "strike_price": _numeric_or_default(raw, resolved["strike_price"], "strike_price", 0.0),
            "option_type": raw[resolved["option_type"]].astype(str).str.strip() if resolved["option_type"] else "",
            "open": to_numeric(raw[resolved["open"]], resolved["open"]),
            "high": to_numeric(raw[resolved["high"]], resolved["high"]),
            "low": to_numeric(raw[resolved["low"]], resolved["low"]),
            "close": to_numeric(raw[resolved["close"]], resolved["close"]),
            "settlement_price": to_numeric(raw[resolved["settlement_price"]], resolved["settlement_price"]),
            "contracts_traded": to_numeric(raw[resolved["contracts_traded"]], resolved["contracts_traded"]).astype("int64"),
            "turnover_inr": _numeric_or_default(raw, resolved["turnover_inr"], "turnover_inr", pd.NA),
            "open_interest_contracts": to_numeric(raw[resolved["open_interest_contracts"]], resolved["open_interest_contracts"]).astype("int64"),
            "change_in_open_interest_contracts": _numeric_or_default(raw, resolved["change_in_open_interest_contracts"], "change_in_open_interest_contracts", 0).astype("int64"),
            "exchange_instrument_id": raw[resolved["exchange_instrument_id"]].astype(str).str.strip() if resolved["exchange_instrument_id"] else "",
            "underlying_value": _numeric_or_default(raw, resolved["underlying_value"], "underlying_value", pd.NA),
            "source_format": "UDIFF_FO_BHAVCOPY",
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


def _needed_columns(aliases: dict[str, tuple[str, ...]]) -> set[str]:
    return {alias.upper().replace(" ", "_") for values in aliases.values() for alias in values}


def _numeric_or_default(df: pd.DataFrame, col: str | None, label: str, default):
    if col is None:
        return pd.Series([default] * len(df), index=df.index)
    return to_optional_numeric(df[col], default=default)


def _udiff_instrument_type(value: str) -> str:
    mapping = {"STF": "FUTSTK", "STO": "OPTSTK", "IDF": "FUTIDX", "IDO": "OPTIDX"}
    return mapping.get(value.upper(), value.upper())
