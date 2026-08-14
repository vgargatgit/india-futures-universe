# NSE Source Formats

This producer treats NSE and NSE Clearing reports as the only canonical futures sources.

## LEGACY_FO_BHAVCOPY

- Official report name: F&O common bhavcopy CSV.
- Transition: discontinued with effect from 2024-07-08 according to the NSE derivatives reports page.
- Compression: ZIP.
- Mapping status: `INFERRED_FROM_OBSERVED_FILE` until the historical specification is pinned.
- Turnover unit: source `VAL_INLAKH`, converted to INR by multiplying by 100,000.

## UDIFF_FO_BHAVCOPY

- Official report name: F&O UDiFF Common Bhavcopy Final ZIP.
- Specification source: NSE/NSE Clearing UDiFF guidance, catalogue, format workbook, sample ZIP and circulars.
- Mapping status: `UNRESOLVED_OFFICIAL_SPEC_REQUIRED` until the workbook and sample are pinned.
- The parser is alias-based and fails closed when mandatory semantic columns are not resolved.

## MII_FO_CONTRACT_FILE

- Official report name: F&O-MII contract file.
- Intended canonical use: dated listed contract set, FUTSTK eligibility, expiry, market lot and quantity freeze.
- Mapping status: `UNRESOLVED_OFFICIAL_SPEC_REQUIRED` until current official headers are pinned.
- Bhavcopy presence is not treated as complete eligibility.

## FO_DAILY_SETTLEMENT

- Official report name: F&O daily settlement prices.
- Intended canonical use: reconciliation against bhavcopy settlement price and fallback only with unambiguous contract mapping.
- Mapping status: `UNRESOLVED_OFFICIAL_SAMPLE_REQUIRED`.

## FO_SPAN_BOD / FO_SPAN_EOD

- Official report names: F&O begin-of-day and end-of-day SPAN risk parameter files.
- V1 scope: source availability inventory only.
- Margin parsing is optional and does not block the first contract-price release.

## Shared Safety Rules

- HTML, login pages and access-denied bodies are rejected even with HTTP 200.
- ZIP/GZIP files are inspected for path traversal, empty archives, duplicate members and compression bombs.
- Raw files are immutable and stored with sidecar manifests.
- Canonical prices are never back-adjusted into continuous futures in this release.
