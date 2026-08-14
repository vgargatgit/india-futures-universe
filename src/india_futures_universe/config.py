from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ResearchConfig:
    start: str
    end: str
    instrument_types: tuple[str, ...]


@dataclass(frozen=True)
class ActiveUniverseConfig:
    release_root: str
    release_id: str
    require_manifest_validation: bool


@dataclass(frozen=True)
class NseConfig:
    source_mode: str
    reports_page: str
    minimum_seconds_between_requests: float
    maximum_retries: int
    connect_timeout_seconds: int
    read_timeout_seconds: int
    user_agent: str
    maximum_uncompressed_archive_mb: int
    maximum_compression_ratio: int


@dataclass(frozen=True)
class PathsConfig:
    raw_root: str
    normalized_root: str
    canonical_root: str
    derived_root: str
    report_root: str
    release_root: str


@dataclass(frozen=True)
class FuturesUniverseConfig:
    project_id: str
    research: ResearchConfig
    active_universe: ActiveUniverseConfig
    nse: NseConfig
    paths: PathsConfig
    formats: dict[str, Any]
    quality: dict[str, Any]


def load_config(path: str | Path) -> FuturesUniverseConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    allowed = {"project_id", "research", "active_universe", "nse", "formats", "quality", "paths"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"Unknown top-level config keys: {unknown}")
    if raw["project_id"] != "INDIA_FUTURES_UNIVERSE_V1":
        raise ValueError("Unsupported project_id")
    research = raw["research"]
    active = raw["active_universe"]
    nse = raw["nse"]
    paths = raw["paths"]
    _reject_unknown("research", research, {"start", "end", "instrument_types"})
    _reject_unknown("active_universe", active, {"release_root", "release_id", "require_manifest_validation"})
    _reject_unknown(
        "nse",
        nse,
        {
            "source_mode",
            "reports_page",
            "minimum_seconds_between_requests",
            "maximum_retries",
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "user_agent",
            "maximum_uncompressed_archive_mb",
            "maximum_compression_ratio",
        },
    )
    _reject_unknown("paths", paths, {"raw_root", "normalized_root", "canonical_root", "derived_root", "report_root", "release_root"})
    return FuturesUniverseConfig(
        project_id=raw["project_id"],
        research=ResearchConfig(str(research["start"]), str(research["end"]), tuple(research["instrument_types"])),
        active_universe=ActiveUniverseConfig(str(active["release_root"]), str(active["release_id"]), bool(active["require_manifest_validation"])),
        nse=NseConfig(
            str(nse["source_mode"]),
            str(nse["reports_page"]),
            float(nse["minimum_seconds_between_requests"]),
            int(nse["maximum_retries"]),
            int(nse["connect_timeout_seconds"]),
            int(nse["read_timeout_seconds"]),
            str(nse["user_agent"]),
            int(nse["maximum_uncompressed_archive_mb"]),
            int(nse["maximum_compression_ratio"]),
        ),
        formats=dict(raw["formats"]),
        quality=dict(raw["quality"]),
        paths=PathsConfig(**{key: str(value) for key, value in paths.items()}),
    )


def _reject_unknown(section: str, payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"Unknown {section} keys: {unknown}")
