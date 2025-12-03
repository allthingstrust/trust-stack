#!/usr/bin/env python3
"""CLI entrypoint that delegates to the RunManager orchestration layer."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import os

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.run_manager import RunManager
from data import store


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _load_assets(path: Optional[str]) -> Optional[List[dict]]:
    if not path:
        return None
    asset_path = Path(path)
    if not asset_path.exists():
        raise FileNotFoundError(asset_path)
    with asset_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Run a Trust Stack analysis")
    parser.add_argument("brand", help="Brand slug to analyze (e.g. nike)")
    parser.add_argument("scenario", help="Scenario slug (e.g. web)")
    parser.add_argument("keywords", nargs="*", help="Keywords or queries to seed ingestion")
    parser.add_argument("--sources", nargs="+", default=["serper", "brave"], help="Sources to ingest from")
    parser.add_argument("--limit", type=int, default=10, help="Per-source fetch limit")
    parser.add_argument("--assets", help="Optional JSON file of pre-collected assets")
    parser.add_argument("--external-id", help="Override external id for the run")
    parser.add_argument("--export-to-s3", action="store_true", help="Upload raw + analytics outputs to S3 after completion")
    parser.add_argument("--s3-bucket", help="Override S3 bucket name")

    args = parser.parse_args()

    engine = store.init_db()
    manager = RunManager(engine=engine)

    assets = _load_assets(args.assets)
    run_config = {
        "sources": args.sources,
        "keywords": args.keywords,
        "limit": args.limit,
        "external_id": args.external_id,
        "assets": assets,
        "export_to_s3": args.export_to_s3,
        "s3_bucket": args.s3_bucket,
    }

    run = manager.run_analysis(args.brand, args.scenario, run_config)
    logger.info("Run %s completed with status %s", run.external_id, run.status)
    print(json.dumps({"run_id": run.id, "external_id": run.external_id, "status": run.status}))


if __name__ == "__main__":
    main()
