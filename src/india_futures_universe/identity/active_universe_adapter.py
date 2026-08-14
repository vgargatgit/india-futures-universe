from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class ActiveUniverseRelease:
    release_root: Path
    release_id: str

    def validate(self) -> dict:
        required = [
            "data_release_manifest.json",
            "research_release_manifest.json",
            "partitioned_artifacts_manifest.json",
            "trading_calendar.parquet",
            "symbol_history.parquet",
            "security_master.parquet",
            "research_universe_monthly.parquet",
        ]
        missing = [name for name in required if not (self.release_root / name).exists()]
        status = "INDIA_ACTIVE_UNIVERSE_PIN_VALIDATED" if not missing else "BLOCKED_PINNED_ACTIVE_UNIVERSE_RELEASE_UNAVAILABLE"
        return {"status": status, "release_id": self.release_id, "release_root": str(self.release_root), "missing": missing}

    def trading_calendar(self) -> pd.DataFrame:
        return pd.read_parquet(self.release_root / "trading_calendar.parquet")

    def symbol_history(self) -> pd.DataFrame:
        return pd.read_parquet(self.release_root / "symbol_history.parquet")

    def security_master(self) -> pd.DataFrame:
        return pd.read_parquet(self.release_root / "security_master.parquet")

    def research_universe_monthly(self) -> pd.DataFrame:
        return pd.read_parquet(self.release_root / "research_universe_monthly.parquet")

    def sessions(self, start: str, end: str) -> list[str]:
        cal = self.trading_calendar()
        dates = pd.to_datetime(cal["date"]).dt.date.astype(str)
        mask = (dates >= start) & (dates <= end)
        return dates[mask].sort_values().tolist()

    def nearest_session_on_or_before(self, target_date: str) -> str:
        dates = self.sessions("1900-01-01", target_date)
        if not dates:
            raise ValueError(f"No active-universe session on or before {target_date}")
        return dates[-1]

    def top100_liquid_universe(self, formation_date: str) -> pd.DataFrame:
        universe = self.research_universe_monthly()
        date_series = pd.to_datetime(universe["date"]).dt.date.astype(str)
        snapshot_dates = sorted(date_series[date_series <= formation_date].unique())
        if not snapshot_dates:
            raise ValueError(f"No research universe snapshot on or before {formation_date}")
        snapshot = universe[date_series == snapshot_dates[-1]].copy()
        eligible_col = "LIQUID_V1_eligible_1" if "LIQUID_V1_eligible_1" in snapshot.columns else "liquid_v1_eligible"
        rank_col = "liquidity_rank_126"
        required = {"security_id", "symbol_at_date", eligible_col, rank_col}
        missing = sorted(required - set(snapshot.columns))
        if missing:
            raise ValueError(f"Research universe missing columns: {missing}")
        filtered = snapshot[snapshot[eligible_col].astype(bool)].copy()
        filtered = filtered.sort_values([rank_col, "security_id"], kind="mergesort").head(100)
        return filtered[["date", "security_id", "symbol_at_date", rank_col]]
