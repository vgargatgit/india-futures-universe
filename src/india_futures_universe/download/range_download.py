from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from india_futures_universe.config import FuturesUniverseConfig
from india_futures_universe.download.client import NseHttpClient, store_raw_file
from india_futures_universe.download.report_locator import ReportCandidate, candidates_for_date
from india_futures_universe.identity.active_universe_adapter import ActiveUniverseRelease
from india_futures_universe.utils import write_json


def download_range(
    config: FuturesUniverseConfig,
    *,
    start: str,
    end: str,
    report_types: set[str],
    resume: bool = True,
    max_dates: int | None = None,
) -> dict:
    release = ActiveUniverseRelease(Path(config.active_universe.release_root), config.active_universe.release_id)
    sessions = release.sessions(start, end)
    if max_dates:
        sessions = sessions[:max_dates]
    client = NseHttpClient(
        user_agent=config.nse.user_agent,
        reports_page=config.nse.reports_page,
        minimum_seconds_between_requests=config.nse.minimum_seconds_between_requests,
        timeout=(config.nse.connect_timeout_seconds, config.nse.read_timeout_seconds),
    )
    rows: list[dict] = []
    max_uncompressed = config.nse.maximum_uncompressed_archive_mb * 1024 * 1024
    for trade_date in sessions:
        chosen = _candidate_set_for_trade_date(date.fromisoformat(trade_date), report_types)
        for candidate in chosen:
            existing = _existing_raw(config.paths.raw_root, candidate.report_type, trade_date, candidate.filename)
            if resume and existing:
                rows.append(
                    {
                        "trade_date": trade_date,
                        "report_type": candidate.report_type,
                        "source_format": candidate.source_format,
                        "download_status": "SKIPPED_EXISTING",
                        "filename": str(existing),
                        "resolved_url": candidate.url,
                        "failure_classification": "",
                    }
                )
                continue
            result = client.get(candidate.url)
            path = store_raw_file(
                raw_root=config.paths.raw_root,
                report_type=candidate.report_type,
                trade_date=trade_date,
                filename=candidate.filename,
                result=result,
                source_page=candidate.source_page,
                max_uncompressed_bytes=max_uncompressed,
                max_compression_ratio=config.nse.maximum_compression_ratio,
            )
            rows.append(
                {
                    "trade_date": trade_date,
                    "report_type": candidate.report_type,
                    "source_format": candidate.source_format,
                    "download_status": result.download_status if not result.failure_classification else "FAILED",
                    "filename": str(path) if path else "",
                    "resolved_url": candidate.url,
                    "http_status": result.status_code,
                    "failure_classification": result.failure_classification,
                }
            )
    report_root = Path(config.paths.report_root)
    report_root.mkdir(parents=True, exist_ok=True)
    ledger = pd.DataFrame(rows)
    ledger.to_csv(report_root / "download_summary.csv", index=False)
    write_json(
        report_root / "download_summary.json",
        {
            "start": start,
            "end": end,
            "sessions": len(sessions),
            "attempted_reports": len(rows),
            "downloaded": int((ledger["download_status"] == "DOWNLOADED").sum()) if not ledger.empty else 0,
            "skipped_existing": int((ledger["download_status"] == "SKIPPED_EXISTING").sum()) if not ledger.empty else 0,
            "failed": int((ledger["download_status"] == "FAILED").sum()) if not ledger.empty else 0,
        },
    )
    return {"sessions": len(sessions), "attempted_reports": len(rows), "ledger": str(report_root / "download_summary.csv")}


def _candidate_set_for_trade_date(session: date, report_types: set[str]) -> list[ReportCandidate]:
    candidates = candidates_for_date(session)
    chosen: list[ReportCandidate] = []
    for candidate in candidates:
        if candidate.report_type not in report_types:
            continue
        if candidate.report_type == "bhavcopy":
            if session < date(2024, 7, 8) and candidate.source_format == "LEGACY_FO_BHAVCOPY":
                chosen.append(candidate)
            elif session >= date(2024, 7, 8) and candidate.source_format == "UDIFF_FO_BHAVCOPY":
                chosen.append(candidate)
        elif candidate.report_type == "contract":
            chosen.append(candidate)
    return chosen


def _existing_raw(raw_root: str, report_type: str, trade_date: str, filename: str) -> Path | None:
    path = Path(raw_root) / "nse_fo" / report_type / trade_date[:4] / trade_date[5:7] / trade_date[8:10] / filename
    manifest = Path(str(path) + ".manifest.json")
    if path.exists() and manifest.exists():
        return path
    return None
