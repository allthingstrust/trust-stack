"""Run Manager orchestrates Trust Stack runs using the new persistence layer."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from data import models
from data import store
from data.models import ContentAsset, DimensionScores, Run

logger = logging.getLogger(__name__)


class RunManager:
    """High level orchestrator for a Trust Stack analysis run."""

    def __init__(self, engine=None, scoring_pipeline=None, settings: Optional[dict] = None):
        self.engine = engine or store.init_db()
        self.settings = settings or {}
        self.scoring_pipeline = scoring_pipeline

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_analysis(self, brand_slug: str, scenario_slug: str, run_config: Optional[dict] = None) -> Run:
        run_config = run_config or {}
        external_id = run_config.get("external_id") or self._generate_external_id(brand_slug)

        with store.session_scope(self.engine) as session:
            brand = store.get_or_create_brand(session, slug=brand_slug, name=run_config.get("brand_name"))
            scenario = store.get_or_create_scenario(
                session,
                slug=scenario_slug,
                name=run_config.get("scenario_name"),
                description=run_config.get("scenario_description"),
                config=run_config.get("scenario_config") or {},
            )
            run = store.create_run(session, brand=brand, scenario=scenario, external_id=external_id, config=run_config)
            session.flush()
            store.update_run_status(session, run.id, "in_progress")

        # Ingestion and scoring can be expensive; perform outside the session scope and re-open
        try:
            assets = self._collect_assets(run_config)
            with store.session_scope(self.engine) as session:
                persisted_assets = store.bulk_insert_assets(session, run_id=run.id, assets=assets)

            scores = self._score_assets(persisted_assets, run_config)
            with store.session_scope(self.engine) as session:
                store.bulk_insert_dimension_scores(session, scores)
                averages = self._calculate_averages(scores)
                store.create_truststack_summary(
                    session,
                    run_id=run.id,
                    averages=averages,
                    authenticity_ratio=averages.get("authenticity_ratio"),
                    overall_score=averages.get("overall_score"),
                )
                store.update_run_status(session, run.id, "completed")
                run = session.get(models.Run, run.id) if hasattr(session, "get") else session.query(models.Run).get(run.id)
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Run %s failed", external_id)
            with store.session_scope(self.engine) as session:
                store.update_run_status(session, run.id, "failed", error_message=str(exc))
                run = session.get(models.Run, run.id) if hasattr(session, "get") else session.query(models.Run).get(run.id)
        return run

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _generate_external_id(self, brand_slug: str) -> str:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{brand_slug}_{stamp}_{uuid.uuid4().hex[:6]}"

    def _collect_assets(self, run_config: dict) -> List[dict]:
        """Collect assets from configured sources.

        During the refactor we allow callers to pass pre-built assets via
        ``run_config['assets']`` to keep tests deterministic. Each asset dict
        should map to :class:`data.models.ContentAsset` fields.
        """

        assets = run_config.get("assets")
        if assets:
            return list(assets)

        # TODO: integrate ingestion modules (brave, reddit, youtube) based on scenario config
        logger.info("No assets supplied; proceeding with empty dataset")
        return []

    def _score_assets(self, assets: List[ContentAsset], run_config: dict) -> List[dict]:
        """Score a list of persisted assets.

        The RunManager supports injecting a custom scoring pipeline for tests
        or lightweight runs. If no pipeline is provided, a simple heuristic is
        used to generate placeholder scores.
        """

        if self.scoring_pipeline and hasattr(self.scoring_pipeline, "score_assets"):
            return list(self.scoring_pipeline.score_assets(assets, run_config))

        # Fallback heuristic scoring
        scored: List[dict] = []
        for asset in assets:
            length = len(asset.normalized_content or asset.raw_content or "")
            baseline = min(1.0, 0.1 + (length / 1000.0))
            scored.append(
                {
                    "asset_id": asset.id,
                    "score_provenance": baseline,
                    "score_verification": baseline,
                    "score_transparency": baseline,
                    "score_coherence": baseline,
                    "score_resonance": baseline,
                    "score_ai_readiness": baseline,
                    "overall_score": baseline,
                    "classification": "Excellent" if baseline >= 0.8 else "Fair",
                }
            )
        return scored

    def _calculate_averages(self, scores: Iterable[dict]) -> Dict[str, float]:
        scores = list(scores)
        if not scores:
            return {k: None for k in [
                "avg_provenance",
                "avg_verification",
                "avg_transparency",
                "avg_coherence",
                "avg_resonance",
                "avg_ai_readiness",
                "overall_score",
                "authenticity_ratio",
            ]}

        def _avg(key):
            vals = [s.get(key) for s in scores if s.get(key) is not None]
            return sum(vals) / len(vals) if vals else None

        averages = {
            "avg_provenance": _avg("score_provenance"),
            "avg_verification": _avg("score_verification"),
            "avg_transparency": _avg("score_transparency"),
            "avg_coherence": _avg("score_coherence"),
            "avg_resonance": _avg("score_resonance"),
            "avg_ai_readiness": _avg("score_ai_readiness"),
        }

        averages["overall_score"] = _avg("overall_score")
        averages["authenticity_ratio"] = averages["overall_score"]
        return averages

