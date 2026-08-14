from __future__ import annotations

import gzip
import io
import zipfile

import pytest

from india_futures_universe.download.archive_safety import inspect_archive


def _zip(payloads: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in payloads.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_zip_path_traversal_rejected() -> None:
    with pytest.raises(ValueError, match="UNSAFE_ARCHIVE_PATH"):
        inspect_archive(_zip({"../evil.csv": b"x"}), max_uncompressed_bytes=1000, max_compression_ratio=100)


def test_empty_zip_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w"):
        pass
    with pytest.raises(ValueError, match="EMPTY_ARCHIVE"):
        inspect_archive(buffer.getvalue(), max_uncompressed_bytes=1000, max_compression_ratio=100)


def test_html_200_rejected() -> None:
    with pytest.raises(ValueError, match="HTML_RETURNED_INSTEAD_OF_DATA"):
        inspect_archive(b"<html>Access Denied</html>", max_uncompressed_bytes=1000, max_compression_ratio=100)


def test_corrupt_gzip_rejected() -> None:
    with pytest.raises(ValueError, match="CORRUPT_ARCHIVE"):
        inspect_archive(b"\x1f\x8bnot-gzip", max_uncompressed_bytes=1000, max_compression_ratio=100)


def test_gzip_valid() -> None:
    payload = gzip.compress(b"a,b\n1,2\n")
    result = inspect_archive(payload, max_uncompressed_bytes=1000, max_compression_ratio=100)
    assert result.source_format == "GZIP"
    assert result.uncompressed_size > 0
