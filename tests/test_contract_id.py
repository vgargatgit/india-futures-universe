from __future__ import annotations

from india_futures_universe.canonical.contracts import contract_id


def test_exchange_instrument_id_takes_precedence() -> None:
    cid = contract_id(exchange="NSE", segment="FO", instrument_type="FUTSTK", security_id="SEC_A", expiry_date="2024-01-25", exchange_instrument_id="123")
    assert cid == "NSE|FO|123"
