from __future__ import annotations

import hashlib


def contract_id(
    *,
    exchange: str,
    segment: str,
    instrument_type: str,
    security_id: str,
    expiry_date: str,
    strike_price: str | float = "0",
    option_type: str = "XX",
    raw_contract_key: str = "",
    exchange_instrument_id: str = "",
) -> str:
    if exchange_instrument_id:
        return f"{exchange}|{segment}|{exchange_instrument_id}"
    payload = "|".join([exchange, segment, instrument_type, security_id, expiry_date, str(strike_price), option_type, raw_contract_key])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{exchange}|{segment}|{instrument_type}|{security_id}|{expiry_date}|{digest}"
