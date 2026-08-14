from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd

from india_futures_universe.config import FuturesUniverseConfig
from india_futures_universe.download.client import NseHttpClient, store_raw_file
from india_futures_universe.download.report_locator import ReportCandidate, candidates_for_date
from india_futures_universe.identity.active_universe_adapter import ActiveUniverseRelease
from india_futures_universe.parse.common import ParseError, read_csv_payload
from india_futures_universe.parse.contract_file import parse_contract_file
from india_futures_universe.parse.legacy_bhavcopy import parse_legacy_bhavcopy
from india_futures_universe.parse.settlement_file import parse_settlement_file
from india_futures_universe.parse.udiff_bhavcopy import parse_udiff_bhavcopy
from india_futures_universe.utils import sha256_file, write_json


ANCHORS = [
    "2006-01-31",
    "2010-01-31",
    "2013-01-31",
    "2016-01-31",
    "2019-01-31",
    "2023-01-31",
    "2024-07-05",
    "2024-07-08",
    "2024-07-09",
    "2025-01-31",
    "2026-08-12",
]


def sample_sessions(source: ActiveUniverseRelease, *, max_dates: int | None = None) -> list[str]:
    sessions = source.sessions("2006-01-31", "2026-08-12")
    session_set = set(sessions)
    selected: set[str] = {source.nearest_session_on_or_before(anchor) for anchor in ANCHORS}
    transition = "2024-07-08"
    transition_index = sessions.index(source.nearest_session_on_or_before(transition))
    selected.update(sessions[max(0, transition_index - 5) : transition_index])
    selected.update(sessions[transition_index : min(len(sessions), transition_index + 5)])
    for year in ["2018", "2023", "2026"]:
        yearly = [s for s in sessions if s.startswith(year)]
        selected.update(yearly[-5:])
    out = [s for s in sessions if s in selected and s in session_set]
    return out[:max_dates] if max_dates else out


def run_source_discovery(config: FuturesUniverseConfig, *, max_dates: int | None = None, dry_run: bool = False) -> dict:
    release = ActiveUniverseRelease(Path(config.active_universe.release_root), config.active_universe.release_id)
    validation = release.validate()
    dates = sample_sessions(release, max_dates=max_dates)
    report_root = Path(config.paths.report_root)
    report_root.mkdir(parents=True, exist_ok=True)
    matrix: list[dict] = []
    manual_queue: list[dict] = []
    templates: dict[str, list[dict]] = {}
    client = NseHttpClient(
        user_agent=config.nse.user_agent,
        reports_page=config.nse.reports_page,
        minimum_seconds_between_requests=config.nse.minimum_seconds_between_requests,
        timeout=(config.nse.connect_timeout_seconds, config.nse.read_timeout_seconds),
    )
    max_uncompressed = config.nse.maximum_uncompressed_archive_mb * 1024 * 1024
    for trade_date in dates:
        session_date = date.fromisoformat(trade_date)
        candidates = candidates_for_date(session_date)
        templates[trade_date] = [asdict(c) for c in candidates]
        for candidate in candidates:
            row = _empty_discovery_row(trade_date, candidate)
            if dry_run:
                row["failure_classification"] = "DRY_RUN"
                matrix.append(row)
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
            row["HTTP_status"] = result.status_code
            row["content_type"] = result.content_type
            row["file_available"] = result.download_status == "DOWNLOADED" and not result.failure_classification
            row["failure_classification"] = result.failure_classification
            if path:
                row["filename"] = path.name
                row["SHA256"] = sha256_file(path)
                parsed = _parse_candidate(path, candidate, trade_date)
                row.update(parsed)
            if row["failure_classification"] in {"ACCESS_DENIED", "RATE_LIMITED", "PUBLIC_ARCHIVE_NOT_AVAILABLE"}:
                manual_queue.append(
                    {
                        "trade_date": trade_date,
                        "report_name": candidate.source_format,
                        "official_source_page": candidate.source_page,
                        "expected_format": candidate.filename,
                        "reason_automatic_download_failed": row["failure_classification"],
                    }
                )
            matrix.append(row)
    matrix_df = pd.DataFrame(matrix)
    matrix_df.to_csv(report_root / "source_discovery_matrix.csv", index=False)
    pd.DataFrame(manual_queue).to_csv(report_root / "manual_download_queue.csv", index=False)
    write_json(report_root / "source_endpoint_templates.json", templates)
    _write_format_inventory(report_root / "source_format_inventory.csv", matrix_df)
    classification = classify_spike(matrix_df)
    _write_source_discovery_md(report_root / "source_discovery.md", validation, classification, matrix_df)
    _write_placeholder_reports(report_root, classification, validation, matrix_df)
    return {"active_universe_validation": validation, "classification": classification, "dates": dates, "rows": len(matrix)}


def _empty_discovery_row(trade_date: str, candidate: ReportCandidate) -> dict:
    return {
        "trade_date": trade_date,
        "official_session": True,
        "report_type": candidate.report_type,
        "source_page": candidate.source_page,
        "resolved_url": candidate.url,
        "HTTP_status": None,
        "content_type": "",
        "filename": candidate.filename,
        "file_available": False,
        "valid_archive": False,
        "parse_status": "NOT_ATTEMPTED",
        "row_count": 0,
        "FUTSTK_row_count": 0,
        "source_format": candidate.source_format,
        "SHA256": "",
        "failure_classification": "",
    }


def _parse_candidate(path: Path, candidate: ReportCandidate, trade_date: str) -> dict:
    try:
        if candidate.source_format == "LEGACY_FO_BHAVCOPY":
            df = parse_legacy_bhavcopy(path, source_sha256=sha256_file(path))
        elif candidate.source_format == "UDIFF_FO_BHAVCOPY":
            df = parse_udiff_bhavcopy(path, source_sha256=sha256_file(path))
        elif candidate.source_format == "MII_FO_CONTRACT_FILE":
            df = parse_contract_file(path, as_of_date=trade_date, source_sha256=sha256_file(path))
        elif candidate.source_format == "FO_DAILY_SETTLEMENT":
            df = parse_settlement_file(path, source_sha256=sha256_file(path))
        elif candidate.source_format.startswith("FO_SPAN"):
            df = read_csv_payload(path)
            return {"valid_archive": True, "parse_status": "AVAILABLE_SCHEMA_UNKNOWN", "row_count": len(df), "FUTSTK_row_count": 0, "failure_classification": "AVAILABLE_SCHEMA_UNKNOWN"}
        else:
            raise ParseError("UNSUPPORTED_FORMAT")
        futstk_rows = int((df.get("instrument_type", pd.Series(dtype=str)).astype(str).str.upper() == "FUTSTK").sum())
        return {
            "valid_archive": True,
            "parse_status": "AVAILABLE_AND_PARSEABLE",
            "row_count": int(len(df)),
            "FUTSTK_row_count": futstk_rows,
            "failure_classification": "",
        }
    except Exception as exc:
        failure = str(exc).split(":", 1)[0]
        if "schema unresolved" in str(exc) or "missing mandatory columns" in str(exc):
            failure = "AVAILABLE_SCHEMA_UNKNOWN"
        return {
            "valid_archive": False,
            "parse_status": "FAILED",
            "row_count": 0,
            "FUTSTK_row_count": 0,
            "failure_classification": failure,
        }


def classify_spike(matrix: pd.DataFrame) -> str:
    parseable = matrix[matrix["parse_status"] == "AVAILABLE_AND_PARSEABLE"]
    has_legacy = ((parseable["source_format"] == "LEGACY_FO_BHAVCOPY") & (parseable["FUTSTK_row_count"] > 0)).any()
    has_udiff = ((parseable["source_format"] == "UDIFF_FO_BHAVCOPY") & (parseable["FUTSTK_row_count"] > 0)).any()
    has_contract = ((parseable["source_format"] == "MII_FO_CONTRACT_FILE") & (parseable["FUTSTK_row_count"] > 0)).any()
    access_denied = matrix["failure_classification"].isin(["ACCESS_DENIED", "RATE_LIMITED"]).any()
    if has_legacy and has_udiff and has_contract:
        return "PUBLIC_NSE_BHAVCOPY_AND_CONTRACT_HISTORY_FEASIBLE"
    if has_udiff and not has_legacy:
        return "PUBLIC_NSE_RECENT_UDIFF_ONLY"
    if has_legacy and not has_contract:
        return "PUBLIC_NSE_BHAVCOPY_HISTORY_WITHOUT_CONTRACT_MASTER"
    if has_contract and not (has_legacy or has_udiff):
        return "PUBLIC_NSE_CONTRACT_MASTER_RECENT_ONLY"
    if access_denied:
        return "PUBLIC_NSE_ACCESS_REQUIRES_MANUAL_DOWNLOAD"
    return "PUBLIC_NSE_ARCHIVE_PARTIALLY_FEASIBLE"


def _write_format_inventory(path: Path, matrix: pd.DataFrame) -> None:
    rows = []
    for source_format, group in matrix.groupby("source_format", dropna=False):
        rows.append(
            {
                "source_format": source_format,
                "attempts": len(group),
                "parseable_files": int((group["parse_status"] == "AVAILABLE_AND_PARSEABLE").sum()),
                "first_available_date": group.loc[group["file_available"], "trade_date"].min() if group["file_available"].any() else "",
                "last_available_date": group.loc[group["file_available"], "trade_date"].max() if group["file_available"].any() else "",
                "mapping_status": "INFERRED_FROM_OBSERVED_FILE" if "LEGACY" in source_format else "UNRESOLVED_OFFICIAL_SPEC_REQUIRED",
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_source_discovery_md(path: Path, validation: dict, classification: str, matrix: pd.DataFrame) -> None:
    parseable = int((matrix["parse_status"] == "AVAILABLE_AND_PARSEABLE").sum())
    futstk_rows = int(matrix["FUTSTK_row_count"].sum())
    lines = [
        "# NSE Futures Source Discovery",
        "",
        f"Active-universe gate: `{validation['status']}`",
        f"Spike classification: `{classification}`",
        "",
        f"Sample report attempts: {len(matrix)}",
        f"Parseable reports: {parseable}",
        f"Observed FUTSTK rows in parseable reports: {futstk_rows}",
        "",
        "This spike uses official NSE/NSE Clearing public report endpoints only. It does not claim full historical coverage.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_placeholder_reports(report_root: Path, classification: str, validation: dict, matrix: pd.DataFrame) -> None:
    empty_csvs = [
        "download_summary.csv",
        "raw_file_audit.csv",
        "parser_audit.csv",
        "identity_mapping_audit.csv",
        "lot_size_history_audit.csv",
        "eligibility_coverage.csv",
        "contract_lifecycle_audit.csv",
        "settlement_reconciliation.csv",
        "legacy_udiff_transition_audit.csv",
        "missing_session_report.csv",
        "futures_coverage_by_year.csv",
        "data_quality_intervals.csv",
    ]
    for name in empty_csvs:
        p = report_root / name
        if not p.exists():
            pd.DataFrame().to_csv(p, index=False)
    readiness = {
        "spike_classification": classification,
        "active_universe_validation": validation,
        "attempted_reports": int(len(matrix)),
        "parseable_reports": int((matrix["parse_status"] == "AVAILABLE_AND_PARSEABLE").sum()),
        "futstk_rows_observed": int(matrix["FUTSTK_row_count"].sum()),
        "release_quality_classification": "SOURCE_CAPTURE_ONLY",
        "margin_evidence_available": False,
        "pairs_lab_executable_readiness": "NOT_READY_FULL_HISTORY_NOT_BUILT",
    }
    write_json(report_root / "release_readiness.json", readiness)
    (report_root / "release_readiness.md").write_text(
        "# Release Readiness\n\n"
        f"Spike classification: `{classification}`\n\n"
        "No release is published by the discovery spike. Full build remains gated by verified legacy, UDiFF and contract-file coverage.\n",
        encoding="utf-8",
    )
    (report_root / "nse_source_usage_review.md").write_text(
        "# NSE Source Usage Review\n\n"
        "Canonical inputs are restricted to official NSE or NSE Clearing public reports. "
        "Raw files are stored locally for private research and are ignored by Git. "
        "Subscription-only endpoints, CAPTCHA bypass, proxy rotation, and logged-in scraping are out of scope.\n",
        encoding="utf-8",
    )
