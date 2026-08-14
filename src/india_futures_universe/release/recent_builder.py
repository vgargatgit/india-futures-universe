from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from india_futures_universe.canonical.contracts import contract_id
from india_futures_universe.config import FuturesUniverseConfig
from india_futures_universe.identity.active_universe_adapter import ActiveUniverseRelease
from india_futures_universe.parse.contract_file import parse_contract_file
from india_futures_universe.parse.legacy_bhavcopy import parse_legacy_bhavcopy
from india_futures_universe.parse.udiff_bhavcopy import parse_udiff_bhavcopy
from india_futures_universe.utils import git_state, sha256_file, write_json


def build_recent_release(config: FuturesUniverseConfig, *, start: str, end: str, release_id: str) -> dict:
    repo_root = Path.cwd()
    release = ActiveUniverseRelease(Path(config.active_universe.release_root), config.active_universe.release_id)
    sessions = release.sessions(start, end)
    symbol_history = _prepare_symbol_history(release.symbol_history())
    contract_master = _load_contract_rows(config, sessions, symbol_history)
    prices = _load_price_rows(config, sessions, symbol_history, contract_master)
    eligibility = _build_eligibility(contract_master)
    lifecycle = _build_lifecycle(contract_master, prices)
    expiry_buckets = _build_expiry_buckets(contract_master, release.sessions(start, end))
    roll_calendar = _build_roll_calendar(expiry_buckets, prices)
    lot_history = _build_lot_history(contract_master)
    settlement_recon = _build_settlement_reconciliation(prices)
    quality = _build_quality_daily(sessions, prices, contract_master)
    coverage = _build_coverage_by_year(prices, contract_master)
    pairs_history = _build_pairs_history(prices)
    release_root = Path(config.paths.release_root) / release_id
    release_root.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "futures_daily_prices.parquet": prices,
        "futures_contract_master_daily.parquet": contract_master,
        "futures_lot_size_history.parquet": lot_history,
        "futures_contract_lifecycle.parquet": lifecycle,
        "futures_underlying_identity_map.parquet": contract_master[_identity_columns()].drop_duplicates(),
        "futures_contract_adjustments.parquet": pd.DataFrame(columns=["contract_id", "date", "adjustment_type", "source"]),
        "futures_settlement_reconciliation.parquet": settlement_recon,
        "futstk_eligibility_daily.parquet": eligibility,
        "futures_expiry_buckets_daily.parquet": expiry_buckets,
        "futures_roll_calendar.parquet": roll_calendar,
        "futures_data_quality_daily.parquet": quality,
        "futures_coverage_by_year.parquet": coverage,
        "pairs_lab_contract_history.parquet": pairs_history,
        "pairs_lab_fno_eligibility.parquet": eligibility.rename(columns={"date": "trade_date"}),
    }
    manifest_artifacts = {}
    for name, frame in artifacts.items():
        path = release_root / name
        frame.to_parquet(path, index=False)
        manifest_artifacts[name] = {"sha256": sha256_file(path), "rows": int(len(frame))}
    manifest = {
        "release_id": release_id,
        "producer_git": git_state(repo_root),
        "research_start": start,
        "research_end": end,
        "active_universe_release": {
            "release_root": str(config.active_universe.release_root),
            "release_id": config.active_universe.release_id,
        },
        "quality_tiers": ["SOURCE_CAPTURE_ONLY", "CONTRACT_AND_LOT_VERIFIED", "HISTORICAL_MARGIN_UNAVAILABLE"],
        "known_limitations": [
            "Settlement report reconciliation unavailable in this build.",
            "SPAN historical margin unavailable; downstream must use conservative margin scenarios.",
            "Identity mapping is effective-dated symbol based unless future official ISIN evidence is added.",
        ],
        "artifact_hashes": manifest_artifacts,
    }
    for name in ["data_release_manifest.json", "research_release_manifest.json", "partitioned_artifacts_manifest.json"]:
        write_json(release_root / name, manifest)
    _write_reports(config, release_id, release_root, manifest, prices, contract_master, eligibility, coverage)
    return {"release_root": str(release_root), "manifest": manifest}


def _load_contract_rows(config: FuturesUniverseConfig, sessions: list[str], symbol_history: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for trade_date in sessions:
        path = _raw_path(config.paths.raw_root, "contract", trade_date, f"NSE_FO_contract_{trade_date[8:10]}{trade_date[5:7]}{trade_date[:4]}.csv.gz")
        if not path.exists():
            continue
        parsed = parse_contract_file(path, as_of_date=trade_date, source_sha256=sha256_file(path))
        parsed = parsed[parsed["instrument_type"] == "FUTSTK"].copy()
        if parsed.empty:
            continue
        mapped = _map_identity(parsed, symbol_history, date_col="as_of_date")
        mapped["contract_id"] = mapped.apply(
            lambda r: contract_id(
                exchange="NSE",
                segment="FO",
                instrument_type="FUTSTK",
                security_id=r["security_id"],
                expiry_date=r["expiry_date"],
                raw_contract_key=r["raw_contract_key"],
                exchange_instrument_id=str(r["exchange_instrument_id"]),
            ),
            axis=1,
        )
        mapped["contract_file_sha256"] = sha256_file(path)
        mapped["quality_status"] = mapped["mapping_status"].map(lambda s: "CONTRACT_AND_LOT_VERIFIED" if s == "EXACT_EFFECTIVE_SYMBOL_DATE_MATCH" else "UNRESOLVED_IDENTITY")
        frames.append(mapped)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _load_price_rows(config: FuturesUniverseConfig, sessions: list[str], symbol_history: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for trade_date in sessions:
        if trade_date < "2024-07-08":
            path = _raw_path(config.paths.raw_root, "bhavcopy", trade_date, f"fo{trade_date[8:10]}{pd.Timestamp(trade_date).strftime('%b').upper()}{trade_date[:4]}bhav.csv.zip")
            source = "LEGACY_FO_BHAVCOPY"
        else:
            path = _raw_path(config.paths.raw_root, "bhavcopy", trade_date, f"BhavCopy_NSE_FO_0_0_0_{trade_date.replace('-', '')}_F_0000.csv.zip")
            source = "UDIFF_FO_BHAVCOPY"
        if not path.exists():
            continue
        parsed = parse_legacy_bhavcopy(path, source_sha256=sha256_file(path)) if source == "LEGACY_FO_BHAVCOPY" else parse_udiff_bhavcopy(path, source_sha256=sha256_file(path))
        parsed = parsed[parsed["instrument_type"] == "FUTSTK"].copy()
        if parsed.empty:
            continue
        parsed["trade_date"] = parsed["trade_date"].replace("", trade_date)
        mapped = _map_identity(parsed, symbol_history, date_col="trade_date")
        mapped = _attach_contract_facts(mapped, contracts)
        mapped["trading_observation_status"] = "TRADED_OR_SETTLED"
        mapped["data_quality_status"] = mapped["mapping_status"].map(lambda s: "CONTRACT_PRICE_WITH_MASTER" if s == "EXACT_EFFECTIVE_SYMBOL_DATE_MATCH" else "UNRESOLVED_IDENTITY")
        frames.append(mapped)
    if not frames:
        return pd.DataFrame()
    prices = pd.concat(frames, ignore_index=True)
    prices = prices[prices["contract_id"].notna() & prices["lot_size"].notna() & prices["contract_id"].astype(str).str.len().gt(0)].copy()
    prices = prices.drop_duplicates(["trade_date", "contract_id"], keep="last")
    return prices


def _map_identity(frame: pd.DataFrame, symbol_history: pd.DataFrame, *, date_col: str) -> pd.DataFrame:
    cache: dict[tuple[str, str], dict] = {}
    rows = []
    for row in frame.to_dict("records"):
        key = (str(row["underlying_symbol_raw"]), str(row[date_col]))
        result = cache.get(key)
        if result is None:
            result = _resolve_symbol_fast(symbol_history, symbol=key[0], trade_date=key[1])
            cache[key] = result
        row.update(result)
        rows.append(row)
    return pd.DataFrame(rows)


def _prepare_symbol_history(symbol_history: pd.DataFrame) -> pd.DataFrame:
    out = symbol_history.copy()
    out["_symbol_upper"] = out["symbol"].astype(str).str.upper()
    out["_effective_from"] = pd.to_datetime(out["effective_from"]).dt.date.astype(str)
    out["_effective_to"] = pd.to_datetime(out["effective_to"]).dt.date.astype(str)
    return out


def _resolve_symbol_fast(symbol_history: pd.DataFrame, *, symbol: str, trade_date: str) -> dict:
    target = symbol.strip().upper()
    matches = symbol_history[(symbol_history["_symbol_upper"] == target) & (symbol_history["_effective_from"] <= trade_date) & (symbol_history["_effective_to"] >= trade_date)]
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


def _attach_contract_facts(prices: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    if contracts.empty:
        prices["contract_id"] = ""
        prices["lot_size"] = pd.NA
        prices["contract_file_sha256"] = ""
        return prices
    contract_key = contracts[
        ["as_of_date", "security_id", "expiry_date", "exchange_instrument_id", "contract_id", "market_lot", "contract_file_sha256"]
    ].rename(columns={"as_of_date": "trade_date", "market_lot": "lot_size"})
    join_cols = ["trade_date", "security_id", "expiry_date"]
    if "exchange_instrument_id" in prices.columns and prices["exchange_instrument_id"].astype(str).str.len().gt(0).any():
        merged = prices.merge(
            contract_key[["trade_date", "security_id", "expiry_date", "exchange_instrument_id", "contract_id", "lot_size", "contract_file_sha256"]],
            on=["trade_date", "security_id", "expiry_date", "exchange_instrument_id"],
            how="left",
        )
    else:
        merged = prices.merge(
            contract_key[["trade_date", "security_id", "expiry_date", "contract_id", "lot_size", "contract_file_sha256"]],
            on=join_cols,
            how="left",
        )
    return merged


def _build_eligibility(contracts: pd.DataFrame) -> pd.DataFrame:
    if contracts.empty:
        return pd.DataFrame()
    contracts = contracts[contracts["mapping_status"] == "EXACT_EFFECTIVE_SYMBOL_DATE_MATCH"].copy()
    grouped = contracts.sort_values(["as_of_date", "security_id", "expiry_date"]).groupby(["as_of_date", "security_id", "underlying_symbol_raw"], as_index=False)
    out = grouped.agg(active_contract_count=("contract_id", "nunique"), contract_file_sha256=("contract_file_sha256", "first"), quality_status=("quality_status", "min"))
    expiries = contracts.sort_values(["as_of_date", "security_id", "expiry_date"]).groupby(["as_of_date", "security_id"])["expiry_date"].agg(list).reset_index()
    expiries["near_expiry_date"] = expiries["expiry_date"].map(lambda x: x[0] if len(x) > 0 else "")
    expiries["next_expiry_date"] = expiries["expiry_date"].map(lambda x: x[1] if len(x) > 1 else "")
    expiries["far_expiry_date"] = expiries["expiry_date"].map(lambda x: x[2] if len(x) > 2 else "")
    out = out.merge(expiries.drop(columns=["expiry_date"]), on=["as_of_date", "security_id"], how="left")
    out = out.rename(columns={"as_of_date": "date"})
    out["futstk_eligible"] = True
    out["eligibility_evidence"] = "OFFICIAL_DAILY_CONTRACT_FILE"
    return out


def _build_lifecycle(contracts: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if contracts.empty:
        return pd.DataFrame()
    base = contracts.groupby(["contract_id", "security_id", "expiry_date"], as_index=False).agg(first_contract_file_date=("as_of_date", "min"), last_contract_file_date=("as_of_date", "max"), lot_size_change_count=("market_lot", "nunique"))
    if not prices.empty:
        traded = prices.groupby("contract_id", as_index=False).agg(first_bhavcopy_date=("trade_date", "min"), last_bhavcopy_date=("trade_date", "max"), traded_session_count=("trade_date", "nunique"))
        base = base.merge(traded, on="contract_id", how="left")
    else:
        base["first_bhavcopy_date"] = ""
        base["last_bhavcopy_date"] = ""
        base["traded_session_count"] = 0
    base["zero_trade_session_count"] = 0
    base["introduction_evidence"] = "OFFICIAL_DAILY_CONTRACT_FILE"
    base["expiration_evidence"] = "OFFICIAL_DAILY_CONTRACT_FILE"
    return base


def _build_expiry_buckets(contracts: pd.DataFrame, sessions: list[str]) -> pd.DataFrame:
    if contracts.empty:
        return pd.DataFrame()
    rows = []
    for (trade_date, security_id), group in contracts.groupby(["as_of_date", "security_id"]):
        ordered = group.sort_values("expiry_date").reset_index(drop=True)
        for idx, row in ordered.iterrows():
            rows.append(
                {
                    "date": trade_date,
                    "contract_id": row["contract_id"],
                    "security_id": security_id,
                    "expiry_date": row["expiry_date"],
                    "sessions_to_expiry": _sessions_to_expiry(sessions, trade_date, row["expiry_date"]),
                    "expiry_bucket": ["NEAR", "NEXT", "FAR"][idx] if idx < 3 else "OTHER",
                }
            )
    return pd.DataFrame(rows)


def _build_roll_calendar(expiry_buckets: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if expiry_buckets.empty:
        return pd.DataFrame()
    near = expiry_buckets[expiry_buckets["expiry_bucket"] == "NEAR"].copy()
    nxt = expiry_buckets[expiry_buckets["expiry_bucket"] == "NEXT"].copy()
    out = near.merge(nxt[["date", "security_id", "contract_id", "expiry_date"]], on=["date", "security_id"], how="left", suffixes=("_near", "_next"))
    price_cols = prices[["trade_date", "contract_id", "settlement_price", "contracts_traded", "open_interest_contracts"]].rename(columns={"trade_date": "date"})
    out = out.merge(price_cols, left_on=["date", "contract_id_near"], right_on=["date", "contract_id"], how="left").drop(columns=["contract_id"])
    out = out.rename(columns={"settlement_price": "near_settlement", "contracts_traded": "near_volume", "open_interest_contracts": "near_open_interest"})
    out = out.merge(price_cols, left_on=["date", "contract_id_next"], right_on=["date", "contract_id"], how="left").drop(columns=["contract_id"])
    out = out.rename(columns={"settlement_price": "next_settlement", "contracts_traded": "next_volume", "open_interest_contracts": "next_open_interest", "sessions_to_expiry": "sessions_to_near_expiry"})
    out["canonical_roll_date_5_sessions"] = out["sessions_to_near_expiry"] <= 5
    out["roll_basis"] = out["next_settlement"] - out["near_settlement"]
    out["roll_data_quality"] = "OFFICIAL_CONTRACT_AND_BHAVCOPY" 
    return out


def _build_lot_history(contracts: pd.DataFrame) -> pd.DataFrame:
    if contracts.empty:
        return pd.DataFrame()
    rows = []
    for (security_id, symbol, lot), group in contracts.groupby(["security_id", "underlying_symbol_raw", "market_lot"]):
        rows.append(
            {
                "security_id": security_id,
                "underlying_symbol_raw": symbol,
                "effective_from": group["as_of_date"].min(),
                "effective_to": group["as_of_date"].max(),
                "lot_size": int(lot),
                "source_as_of_date": group["as_of_date"].min(),
                "source_contract_file": group["source_filename"].iloc[0],
                "source_sha256": group["source_sha256"].iloc[0],
                "evidence_status": "OFFICIAL_DAILY_CONTRACT_FILE",
            }
        )
    return pd.DataFrame(rows)


def _build_settlement_reconciliation(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    return prices[["trade_date", "contract_id", "settlement_price", "source_sha256"]].rename(
        columns={"settlement_price": "bhavcopy_settlement", "source_sha256": "bhavcopy_source_sha256"}
    ).assign(settlement_report_price=pd.NA, absolute_difference=pd.NA, relative_difference=pd.NA, reconciliation_status="BHAVCOPY_ONLY", settlement_source_sha256="")


def _build_quality_daily(sessions: list[str], prices: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for session in sessions:
        rows.append(
            {
                "date": session,
                "bhavcopy_rows": int((prices["trade_date"] == session).sum()) if not prices.empty else 0,
                "contract_rows": int((contracts["as_of_date"] == session).sum()) if not contracts.empty else 0,
                "quality_status": "RESEARCH_HIGH_CONFIDENCE_PRICE_AND_CONTRACT" if (not prices.empty and (prices["trade_date"] == session).any() and not contracts.empty and (contracts["as_of_date"] == session).any()) else "SOURCE_CAPTURE_INCOMPLETE",
            }
        )
    return pd.DataFrame(rows)


def _build_coverage_by_year(prices: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    years = sorted(set(pd.to_datetime(prices["trade_date"]).dt.year if not prices.empty else []) | set(pd.to_datetime(contracts["as_of_date"]).dt.year if not contracts.empty else []))
    for year in years:
        rows.append(
            {
                "year": int(year),
                "price_rows": int((pd.to_datetime(prices["trade_date"]).dt.year == year).sum()) if not prices.empty else 0,
                "contract_rows": int((pd.to_datetime(contracts["as_of_date"]).dt.year == year).sum()) if not contracts.empty else 0,
                "security_count": int(prices.loc[pd.to_datetime(prices["trade_date"]).dt.year == year, "security_id"].nunique()) if not prices.empty else 0,
            }
        )
    return pd.DataFrame(rows)


def _build_pairs_history(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    out = prices.rename(
        columns={
            "underlying_symbol_raw": "underlying_symbol",
            "contract_id": "contract_identifier",
            "contracts_traded": "volume",
            "open_interest_contracts": "open_interest",
        }
    ).copy()
    out["underlying_symbol_raw"] = out["underlying_symbol"]
    out["lot_size_evidence_status"] = "OFFICIAL_DAILY_CONTRACT_FILE"
    out["identity_mapping_status"] = out["mapping_status"]
    return out[
        [
            "trade_date",
            "underlying_symbol",
            "underlying_symbol_raw",
            "security_id",
            "expiry_date",
            "contract_identifier",
            "exchange_instrument_id",
            "lot_size",
            "open",
            "high",
            "low",
            "close",
            "settlement_price",
            "volume",
            "open_interest",
            "change_in_open_interest_contracts",
            "turnover_inr",
            "underlying_value",
            "source_format",
            "source_filename",
            "source_sha256",
            "contract_file_sha256",
            "identity_mapping_status",
            "lot_size_evidence_status",
            "data_quality_status",
        ]
    ]


def _write_reports(config, release_id, release_root, manifest, prices, contracts, eligibility, coverage) -> None:
    report_root = Path(config.paths.report_root)
    report_root.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(report_root / "futures_coverage_by_year.csv", index=False)
    contracts[_identity_columns()].drop_duplicates().to_csv(report_root / "identity_mapping_audit.csv", index=False)
    _build_lot_history(contracts).to_csv(report_root / "lot_size_history_audit.csv", index=False)
    eligibility.to_csv(report_root / "eligibility_coverage.csv", index=False)
    readiness = {
        "release_id": release_id,
        "release_root": str(release_root),
        "futures_daily_price_rows": int(len(prices)),
        "contract_master_rows": int(len(contracts)),
        "futstk_eligible_rows": int(len(eligibility)),
        "unique_mapped_security_count": int(prices["security_id"].nunique()) if not prices.empty else 0,
        "identity_mapping_failures": int((prices["mapping_status"] != "EXACT_EFFECTIVE_SYMBOL_DATE_MATCH").sum()) if not prices.empty else 0,
        "lot_size_verified_fraction": 1.0 if not contracts.empty else 0.0,
        "settlement_verified_fraction": 0.0,
        "release_quality_classification": "RESEARCH_HIGH_CONFIDENCE_PRICE_AND_CONTRACT_WITHOUT_MARGIN" if not prices.empty and not contracts.empty else "SOURCE_CAPTURE_ONLY",
        "pairs_compatibility_file": str(release_root / "pairs_lab_contract_history.parquet"),
        "margin_evidence": "HISTORICAL_MARGIN_UNAVAILABLE",
        "known_limitations": manifest["known_limitations"],
    }
    write_json(report_root / "release_readiness.json", readiness)
    (report_root / "release_readiness.md").write_text(
        "# Release Readiness\n\n"
        f"Release `{release_id}` contains {len(prices):,} FUTSTK daily price rows and {len(contracts):,} contract-master rows.\n\n"
        "Historical SPAN margin and settlement-report reconciliation are not available in this build.\n",
        encoding="utf-8",
    )


def _raw_path(raw_root: str, report_type: str, trade_date: str, filename: str) -> Path:
    return Path(raw_root) / "nse_fo" / report_type / trade_date[:4] / trade_date[5:7] / trade_date[8:10] / filename


def _sessions_to_expiry(sessions: list[str], trade_date: str, expiry_date: str) -> int:
    future = [s for s in sessions if trade_date <= s <= expiry_date]
    return max(len(future) - 1, 0)


def _identity_columns() -> list[str]:
    return [
        "as_of_date",
        "underlying_symbol_raw",
        "security_id",
        "mapping_status",
        "mapping_method",
        "mapping_evidence_start",
        "mapping_evidence_end",
        "match_count",
        "source_sha256",
    ]
