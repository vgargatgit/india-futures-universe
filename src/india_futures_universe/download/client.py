from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from india_futures_universe.download.archive_safety import inspect_archive, reject_html
from india_futures_universe.utils import sha256_bytes, write_json


@dataclass(frozen=True)
class DownloadResult:
    url: str
    status_code: int | None
    content_type: str
    payload: bytes
    failure_classification: str
    download_status: str
    timestamp_utc: str
    headers: dict[str, str]


class NseHttpClient:
    def __init__(self, *, user_agent: str, reports_page: str, minimum_seconds_between_requests: float, timeout: tuple[int, int]):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/csv,application/zip,application/gzip,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
            }
        )
        self.reports_page = reports_page
        self.minimum_seconds_between_requests = minimum_seconds_between_requests
        self.timeout = timeout
        self._last_request = 0.0
        self._primed = False

    def prime(self) -> None:
        if self._primed:
            return
        self._request(self.reports_page)
        self._primed = True

    def get(self, url: str) -> DownloadResult:
        if not self._primed:
            self.prime()
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            response = self._request(url)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            return DownloadResult(url, status, "", b"", _http_failure(status), "FAILED", timestamp, {})
        except requests.RequestException:
            return DownloadResult(url, None, "", b"", "PUBLIC_ARCHIVE_NOT_AVAILABLE", "FAILED", timestamp, {})
        payload = response.content
        content_type = response.headers.get("Content-Type", "")
        failure = ""
        status = "DOWNLOADED"
        if response.status_code == 200:
            try:
                reject_html(payload)
            except ValueError as exc:
                failure = str(exc)
                status = "FAILED"
        else:
            failure = _http_failure(response.status_code)
            status = "FAILED"
        return DownloadResult(url, response.status_code, content_type, payload, failure, status, timestamp, dict(response.headers))

    def _request(self, url: str) -> requests.Response:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.minimum_seconds_between_requests:
            time.sleep(self.minimum_seconds_between_requests - elapsed)
        response = self.session.get(url, timeout=self.timeout)
        self._last_request = time.monotonic()
        if response.status_code in {401, 403, 429}:
            response.raise_for_status()
        return response


def _http_failure(status: int | None) -> str:
    if status in {401, 403}:
        return "ACCESS_DENIED"
    if status == 429:
        return "RATE_LIMITED"
    if status == 404:
        return "NOT_PUBLISHED_FOR_DATE"
    return "PUBLIC_ARCHIVE_NOT_AVAILABLE"


def store_raw_file(
    *,
    raw_root: str | Path,
    report_type: str,
    trade_date: str,
    filename: str,
    result: DownloadResult,
    source_page: str,
    max_uncompressed_bytes: int,
    max_compression_ratio: int,
) -> Path | None:
    date_path = Path(raw_root) / "nse_fo" / report_type / trade_date[:4] / trade_date[5:7] / trade_date[8:10]
    date_path.mkdir(parents=True, exist_ok=True)
    if result.download_status != "DOWNLOADED":
        return None
    path = date_path / filename
    suffix = 0
    while path.exists() and sha256_bytes(path.read_bytes()) != sha256_bytes(result.payload):
        suffix += 1
        path = date_path / f"{Path(filename).stem}.rev{suffix}{Path(filename).suffix}"
    if not path.exists():
        path.write_bytes(result.payload)
    manifest = raw_manifest(
        requested_trade_date=trade_date,
        report_type=report_type,
        source_page=source_page,
        filename=path.name,
        result=result,
        max_uncompressed_bytes=max_uncompressed_bytes,
        max_compression_ratio=max_compression_ratio,
    )
    write_json(str(path) + ".manifest.json", manifest)
    return path


def raw_manifest(
    *,
    requested_trade_date: str,
    report_type: str,
    source_page: str,
    filename: str,
    result: DownloadResult,
    max_uncompressed_bytes: int,
    max_compression_ratio: int,
) -> dict:
    archive = None
    failure = result.failure_classification
    if result.payload and not failure:
        try:
            archive = inspect_archive(result.payload, max_uncompressed_bytes=max_uncompressed_bytes, max_compression_ratio=max_compression_ratio)
        except ValueError as exc:
            failure = str(exc)
    return {
        "requested_trade_date": requested_trade_date,
        "report_type": report_type,
        "source_page": source_page,
        "resolved_download_url": result.url,
        "original_filename": filename,
        "download_timestamp_utc": result.timestamp_utc,
        "http_status": result.status_code,
        "content_type": result.content_type,
        "content_length": int(len(result.payload)),
        "etag": result.headers.get("ETag"),
        "last_modified": result.headers.get("Last-Modified"),
        "sha256": sha256_bytes(result.payload) if result.payload else "",
        "compressed_size": int(len(result.payload)),
        "uncompressed_size": archive.uncompressed_size if archive else 0,
        "archive_member_names": list(archive.member_names) if archive else [],
        "source_format": archive.source_format if archive else "",
        "discovery_method": "URL_TEMPLATE_CANDIDATE",
        "download_status": result.download_status if not failure else "FAILED",
        "failure_classification": failure,
    }
