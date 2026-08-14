from __future__ import annotations

import pandas as pd


def resolve_symbol_on_date(symbol_history: pd.DataFrame, *, symbol: str, trade_date: str) -> dict:
    required = {"symbol", "security_id", "effective_from", "effective_to"}
    missing = sorted(required - set(symbol_history.columns))
    if missing:
        raise ValueError(f"symbol_history missing columns: {missing}")
    history = symbol_history.copy()
    target = symbol.strip().upper()
    symbols = history["symbol"].astype(str).str.upper()
    start = pd.to_datetime(history["effective_from"]).dt.date.astype(str)
    end = pd.to_datetime(history["effective_to"]).dt.date.astype(str)
    matches = history[(symbols == target) & (start <= trade_date) & (end >= trade_date)]
    if len(matches) == 1:
        row = matches.iloc[0]
        return {
            "mapping_status": "EXACT_EFFECTIVE_SYMBOL_DATE_MATCH",
            "security_id": row["security_id"],
            "mapping_method": "symbol_history",
            "mapping_evidence_start": row["effective_from"],
            "mapping_evidence_end": row["effective_to"],
            "match_count": 1,
        }
    if len(matches) == 0:
        return {
            "mapping_status": "UNMAPPED",
            "security_id": "",
            "mapping_method": "symbol_history",
            "mapping_evidence_start": "",
            "mapping_evidence_end": "",
            "match_count": 0,
        }
    return {
        "mapping_status": "AMBIGUOUS",
        "security_id": "",
        "mapping_method": "symbol_history",
        "mapping_evidence_start": "",
        "mapping_evidence_end": "",
        "match_count": int(len(matches)),
    }
