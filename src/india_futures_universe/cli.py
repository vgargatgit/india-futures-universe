from __future__ import annotations

import argparse
import json
from pathlib import Path

from india_futures_universe.config import load_config
from india_futures_universe.download.discovery import run_source_discovery
from india_futures_universe.download.range_download import download_range
from india_futures_universe.release.recent_builder import build_recent_release


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="india-futures-data")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in [
        "discover-sources",
        "download",
        "ingest-local",
        "normalize",
        "build-canonical",
        "build-derived",
        "build-release",
        "audit-release",
        "probe-date",
        "coverage",
    ]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", required=True)
        cmd.add_argument("--start")
        cmd.add_argument("--end")
        cmd.add_argument("--dates")
        cmd.add_argument("--report-types")
        cmd.add_argument("--source-mode")
        cmd.add_argument("--resume", action="store_true")
        cmd.add_argument("--dry-run", action="store_true")
        cmd.add_argument("--max-dates", type=int)
        cmd.add_argument("--release-id")
        cmd.add_argument("--date")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command in {"discover-sources", "probe-date"}:
        if args.command == "probe-date" and args.date:
            args.max_dates = 1
        result = run_source_discovery(config, max_dates=args.max_dates, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "download":
        report_types = set((args.report_types or "bhavcopy,contract").split(","))
        result = download_range(
            config,
            start=args.start or config.research.start,
            end=args.end or config.research.end,
            report_types=report_types,
            resume=args.resume,
            max_dates=args.max_dates,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "build-release":
        if not args.release_id:
            raise SystemExit("--release-id is required")
        result = build_recent_release(config, start=args.start or config.research.start, end=args.end or config.research.end, release_id=args.release_id)
        print(json.dumps({"release_root": result["release_root"]}, indent=2, sort_keys=True))
        return 0
    Path(config.paths.report_root).mkdir(parents=True, exist_ok=True)
    raise SystemExit(f"{args.command} is scaffolded but gated until source discovery passes")


if __name__ == "__main__":
    raise SystemExit(main())
