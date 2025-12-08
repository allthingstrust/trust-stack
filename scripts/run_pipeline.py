#!/usr/bin/env python3
"""CLI entrypoint that delegates to the RunManager orchestration layer."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import os
from typing import List, Optional
from dotenv import load_dotenv

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
    parser.add_argument("--print-report", action="store_true", help="Generate and print full Trust Stack Report to console")

    args = parser.parse_args()

    # Load environment variables (critical for API keys)
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

    if not os.getenv('SERPER_API_KEY') and 'serper' in args.sources:
        print("WARNING: SERPER_API_KEY not found in environment. Search may fail.")

    # Initialize scoring pipeline (LLM + Attributes)
    try:
        from scoring.scorer import ContentScorer
        scoring_pipeline = ContentScorer(use_attribute_detection=True)
        logger.info("ContentScorer initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize ContentScorer: {e}")
        scoring_pipeline = None

    engine = store.init_db()
    manager = RunManager(engine=engine, scoring_pipeline=scoring_pipeline)

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

    print(f"Starting analysis for brand: {args.brand}...")
    run = manager.run_analysis(args.brand, args.scenario, run_config)
    logger.info("Run %s completed with status %s", run.external_id, run.status)
    
    # Simple JSON output for machine parsing
    print(json.dumps({"run_id": run.id, "external_id": run.external_id, "status": run.status}))

    # Generate full human-readable report if requested
    if args.print_report:
        print("\nGethering report data...")
        from data import models
        from sqlalchemy.orm import joinedload
        from reporting.trust_stack_report import generate_trust_stack_report

        with store.session_scope(engine) as session:
            # Re-fetch run with all relationships loaded
            run_data = session.query(models.Run).options(
                joinedload(models.Run.summary),
                joinedload(models.Run.brand),
                joinedload(models.Run.assets).joinedload(models.ContentAsset.scores)
            ).filter(models.Run.id == run.id).first()

            if not run_data:
                print("Error: Could not retrieve run data for reporting.")
                return

            # Construct report_data dictionary expected by the report generator
            items = []
            for asset in run_data.assets:
                item = {
                    "id": asset.id,
                    "url": asset.url,
                    "title": asset.title,
                    "body": asset.raw_content, # simplified
                    "meta": asset.meta_info or {},
                    "dimension_scores": {}
                }
                
                # Extract scores if available
                if asset.scores and len(asset.scores) > 0:
                    score = asset.scores[0]
                    item["final_score"] = (score.overall_score or 0) * 100
                    item["dimension_scores"] = {
                        "provenance": score.score_provenance,
                        "verification": score.score_verification,
                        "transparency": score.score_transparency,
                        "coherence": score.score_coherence,
                        "resonance": score.score_resonance,
                        "ai_readiness": score.score_ai_readiness
                    }
                    # Merge detected_attributes from rationale
                    rationale = score.rationale or {}
                    if isinstance(rationale, dict) and rationale.get('detected_attributes'):
                        item["meta"]["detected_attributes"] = rationale["detected_attributes"]
                
                items.append(item)

            dimension_breakdown = {}
            if run_data.summary:
                dimension_breakdown = {
                    "provenance": {"average": run_data.summary.avg_provenance or 0},
                    "verification": {"average": run_data.summary.avg_verification or 0},
                    "transparency": {"average": run_data.summary.avg_transparency or 0},
                    "coherence": {"average": run_data.summary.avg_coherence or 0},
                    "resonance": {"average": run_data.summary.avg_resonance or 0},
                    "ai_readiness": {"average": run_data.summary.avg_ai_readiness or 0}
                }

            report_data_dict = {
                "brand_id": run_data.brand.name if run_data.brand else args.brand,
                "generated_at": run_data.started_at.strftime("%Y-%m-%d"),
                "total_items_analyzed": len(items),
                "dimension_breakdown": dimension_breakdown,
                "items": items,
                "sources": run_config.get("sources", [])
            }

            print("\n" + "="*80)
            print(f"TRUST STACK REPORT: {args.brand}")
            print("="*80 + "\n")
            
            try:
                report_text = generate_trust_stack_report(report_data_dict)
                print(report_text)
            except Exception as e:
                print(f"Error generating report: {e}")
                import traceback
                traceback.print_exc()

            print("\n" + "="*80)


if __name__ == "__main__":
    main()
