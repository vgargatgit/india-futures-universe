from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from india_futures_universe.parse.contract_file import parse_contract_file
from india_futures_universe.parse.legacy_bhavcopy import parse_legacy_bhavcopy
from india_futures_universe.parse.udiff_bhavcopy import parse_udiff_bhavcopy


def _zip_csv(path: Path, name: str, text: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, text)
    return path


def test_legacy_bhavcopy_turnover_lakhs_to_inr(tmp_path: Path) -> None:
    csv = (
        "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP\n"
        "FUTSTK,ABC,25-Jan-2024,0,XX,100,110,99,105,106,2,3.5,10,1,01-Jan-2024\n"
    )
    path = _zip_csv(tmp_path / "fo.zip", "fo.csv", csv)
    df = parse_legacy_bhavcopy(path)
    assert df.loc[0, "instrument_type"] == "FUTSTK"
    assert df.loc[0, "turnover_inr"] == 350000
    assert df.loc[0, "contracts_traded"] == 2


def test_udiff_parser_fails_closed_on_unknown_schema(tmp_path: Path) -> None:
    path = _zip_csv(tmp_path / "udiff.zip", "x.csv", "A,B\n1,2\n")
    with pytest.raises(Exception, match="schema unresolved"):
        parse_udiff_bhavcopy(path)


def test_contract_file_preserves_lot_size(tmp_path: Path) -> None:
    path = tmp_path / "contract.csv"
    path.write_text("INSTRUMENT,SYMBOL,EXPIRY_DT,MARKET_LOT,TOKEN\nFUTSTK,ABC,25-Jan-2024,1500,123\n")
    df = parse_contract_file(path, as_of_date="2024-01-01")
    assert df.loc[0, "market_lot"] == 1500
    assert df.loc[0, "expiry_date"] == "2024-01-25"
