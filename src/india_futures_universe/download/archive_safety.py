from __future__ import annotations

import gzip
import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class ArchiveInspection:
    valid: bool
    source_format: str
    member_names: tuple[str, ...]
    uncompressed_size: int
    failure: str = ""


def reject_html(payload: bytes) -> None:
    head = payload[:512].lower()
    if b"<html" in head or b"<!doctype html" in head or b"access denied" in head or b"login" in head:
        raise ValueError("HTML_RETURNED_INSTEAD_OF_DATA")


def inspect_archive(payload: bytes, *, max_uncompressed_bytes: int, max_compression_ratio: int) -> ArchiveInspection:
    reject_html(payload)
    if payload.startswith(b"PK\x03\x04") or payload.startswith(b"PK\x05\x06"):
        return inspect_zip(payload, max_uncompressed_bytes=max_uncompressed_bytes, max_compression_ratio=max_compression_ratio)
    if payload.startswith(b"\x1f\x8b"):
        return inspect_gzip(payload, max_uncompressed_bytes=max_uncompressed_bytes, max_compression_ratio=max_compression_ratio)
    raise ValueError("UNSUPPORTED_FORMAT")


def inspect_zip(payload: bytes, *, max_uncompressed_bytes: int, max_compression_ratio: int) -> ArchiveInspection:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if not infos:
            raise ValueError("EMPTY_ARCHIVE")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("DUPLICATE_ARCHIVE_MEMBERS")
        total = 0
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("UNSAFE_ARCHIVE_PATH")
            total += int(info.file_size)
        _check_size(payload, total, max_uncompressed_bytes, max_compression_ratio)
        return ArchiveInspection(True, "ZIP", tuple(names), total)


def inspect_gzip(payload: bytes, *, max_uncompressed_bytes: int, max_compression_ratio: int) -> ArchiveInspection:
    try:
        data = gzip.decompress(payload)
    except Exception as exc:
        raise ValueError("CORRUPT_ARCHIVE") from exc
    _check_size(payload, len(data), max_uncompressed_bytes, max_compression_ratio)
    return ArchiveInspection(True, "GZIP", ("<gzip-stream>",), len(data))


def _check_size(payload: bytes, uncompressed_size: int, max_uncompressed_bytes: int, max_compression_ratio: int) -> None:
    if uncompressed_size <= 0:
        raise ValueError("EMPTY_ARCHIVE")
    if uncompressed_size > max_uncompressed_bytes:
        raise ValueError("ARCHIVE_TOO_LARGE")
    ratio = uncompressed_size / max(len(payload), 1)
    if ratio > max_compression_ratio:
        raise ValueError("COMPRESSION_RATIO_TOO_HIGH")
