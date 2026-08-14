from __future__ import annotations

import pandas as pd
import pytest

from india_futures_universe.derived.pairs_compatibility import validate_pairs_contract_history
from india_futures_universe.identity.resolver import resolve_symbol_on_date


def test_symbol_change_does_not_alter_earlier_mapping() -> None:
    history = pd.DataFrame(
        [
            {"symbol": "OLD", "security_id": "SEC_A", "effective_from": "2020-01-01", "effective_to": "2021-01-01"},
            {"symbol": "NEW", "security_id": "SEC_A", "effective_from": "2021-01-02", "effective_to": "2026-01-01"},
        ]
    )
    result = resolve_symbol_on_date(history, symbol="OLD", trade_date="2020-06-01")
    assert result["mapping_status"] == "EXACT_EFFECTIVE_SYMBOL_DATE_MATCH"
    assert result["security_id"] == "SEC_A"


def test_multiple_symbol_matches_fail_ambiguous() -> None:
    history = pd.DataFrame(
        [
            {"symbol": "ABC", "security_id": "SEC_A", "effective_from": "2020-01-01", "effective_to": "2022-01-01"},
            {"symbol": "ABC", "security_id": "SEC_B", "effective_from": "2020-01-01", "effective_to": "2022-01-01"},
        ]
    )
    result = resolve_symbol_on_date(history, symbol="ABC", trade_date="2020-06-01")
    assert result["mapping_status"] == "AMBIGUOUS"


def test_pairs_compatibility_rejects_header_only() -> None:
    df = pd.DataFrame(columns=["trade_date", "underlying_symbol", "underlying_symbol_raw", "security_id", "expiry_date", "contract_identifier", "lot_size", "open", "high", "low", "close", "settlement_price", "volume", "open_interest"])
    with pytest.raises(ValueError, match="empty"):
        validate_pairs_contract_history(df)


def test_pairs_compatibility_rejects_invalid_expiry() -> None:
    df = pd.DataFrame(
        [
            {
                "trade_date": "2024-01-02",
                "underlying_symbol": "ABC",
                "underlying_symbol_raw": "ABC",
                "security_id": "SEC_A",
                "expiry_date": "2024-01-01",
                "contract_identifier": "CID",
                "lot_size": 1,
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "settlement_price": 1,
                "volume": 1,
                "open_interest": 1,
            }
        ]
    )
    with pytest.raises(ValueError, match="Invalid expiry"):
        validate_pairs_contract_history(df)
