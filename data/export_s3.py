"""S3 export helpers for completed Trust Stack runs.

This module complements the existing S3 utilities without replacing them.
It focuses on exporting analytics-friendly Parquet datasets and raw JSON
snapshots that match the long-term layout described in the refactor brief.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Iterable, List, Tuple

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from data import store
from data.models import ContentAsset, DimensionScores, Run

logger = logging.getLogger(__name__)


DEFAULT_BUCKET = os.getenv("TRUSTSTACK_S3_BUCKET", "truststack-data")


def export_run_to_s3(engine, run_id: int, bucket: str | None = None) -> Tuple[List[str], List[str]]:
    """Export run results to S3 in both raw and analytics layouts.

    Returns a tuple of (raw_keys, analytics_keys) for observability.
    """

    bucket = bucket or DEFAULT_BUCKET
    client = boto3.client("s3")

    with store.session_scope(engine) as session:
        run: Run | None = session.query(Run).get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        brand = run.brand
        brand_slug = brand.slug if brand else "unknown"
        started_at = run.started_at or datetime.utcnow()
        assets: List[ContentAsset] = session.query(ContentAsset).filter_by(run_id=run_id).all()
        asset_ids = [asset.id for asset in assets]
        scores: List[DimensionScores] = [
            score for score in session.query(DimensionScores).all() if score.asset_id in asset_ids
        ]

        run_data = {
            "id": run.id,
            "external_id": run.external_id,
            "brand_id": run.brand_id,
            "scenario_id": run.scenario_id,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "config": json.dumps(run.config or {}),
            "error_message": run.error_message,
        }

        asset_rows = [
            {
                "id": asset.id,
                "run_id": asset.run_id,
                "source_type": asset.source_type,
                "channel": asset.channel,
                "url": asset.url,
                "external_id": asset.external_id,
                "title": asset.title,
                "raw_content": asset.raw_content,
                "normalized_content": asset.normalized_content,
                "modality": asset.modality,
                "language": asset.language,
                "metadata": json.dumps(asset.metadata or {}),
                "created_at": asset.created_at,
            }
            for asset in assets
        ]

        score_rows = [
            {
                "id": score.id,
                "asset_id": score.asset_id,
                "score_provenance": score.score_provenance,
                "score_verification": score.score_verification,
                "score_transparency": score.score_transparency,
                "score_coherence": score.score_coherence,
                "score_resonance": score.score_resonance,
                "score_ai_readiness": score.score_ai_readiness,
                "overall_score": score.overall_score,
                "classification": score.classification,
                "rationale": json.dumps(score.rationale or {}),
                "flags": json.dumps(score.flags or {}),
                "created_at": score.created_at,
            }
            for score in scores
        ]

    raw_keys = _upload_raw_assets(client, bucket, brand_slug, run_data["external_id"], asset_rows)
    analytics_keys = _upload_parquet_tables(
        client,
        bucket,
        brand_slug,
        started_at,
        run_data,
        asset_rows,
        score_rows,
    )
    return raw_keys, analytics_keys


def _upload_raw_assets(client, bucket: str, brand_slug: str, external_id: str, assets: Iterable[dict]) -> List[str]:
    keys: List[str] = []
    for asset in assets:
        payload = {
            "id": asset.get("id"),
            "run_id": asset.get("run_id"),
            "source_type": asset.get("source_type"),
            "channel": asset.get("channel"),
            "url": asset.get("url"),
            "external_id": asset.get("external_id"),
            "title": asset.get("title"),
            "raw_content": asset.get("raw_content"),
            "normalized_content": asset.get("normalized_content"),
            "modality": asset.get("modality"),
            "language": asset.get("language"),
            "metadata": asset.get("metadata"),
            "created_at": asset.get("created_at").isoformat() if asset.get("created_at") else None,
        }
        key = f"raw/{brand_slug}/{external_id}/{asset.get('source_type')}/{asset.get('id')}.json"
        client.put_object(Bucket=bucket, Key=key, Body=json.dumps(payload).encode("utf-8"))
        keys.append(key)
        logger.debug("Uploaded raw asset %s", key)
    return keys


def _upload_parquet_tables(
    client,
    bucket: str,
    brand_slug: str,
    started_at: datetime,
    run: dict,
    assets: List[dict],
    scores: List[dict],
) -> List[str]:
    year = started_at.strftime("%Y")
    month = started_at.strftime("%m")
    day = started_at.strftime("%d")

    analytics_keys: List[str] = []

    def _upload(table_name: str, rows: List[dict]):
        if not rows:
            return
        for row in rows:
            row.setdefault("brand_slug", brand_slug)
            row.setdefault("year", year)
            row.setdefault("month", month)
            row.setdefault("day", day)
        table = pa.Table.from_pylist(rows)
        buffer = BytesIO()
        pq.write_table(table, buffer, compression="snappy")
        buffer.seek(0)
        key = f"analytics/{table_name}/{brand_slug}/year={year}/month={month}/day={day}/part-run-{run['id']}.parquet"
        client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue(), ContentType="application/octet-stream")
        analytics_keys.append(key)
        logger.debug("Uploaded analytics table %s", key)

    run_rows = [run]

    _upload("assets", assets)
    _upload("scores", scores)
    _upload("runs", run_rows)
    return analytics_keys

