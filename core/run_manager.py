"""Run Manager orchestrates Trust Stack runs using the new persistence layer."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from data import models
from data import store
from data import export_s3
from data.models import ContentAsset, DimensionScores, Run
from sqlalchemy.orm import joinedload

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
                # Eagerly load relationships to prevent DetachedInstanceError or NoneType errors
                run = (
                    session.query(models.Run)
                    .options(
                        joinedload(models.Run.brand),
                        joinedload(models.Run.scenario),
                        joinedload(models.Run.summary)
                    )
                    .get(run.id)
                )

            if run_config.get("export_to_s3"):
                export_s3.export_run_to_s3(self.engine, run.id, bucket=run_config.get("s3_bucket"))
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Run %s failed", external_id)
            with store.session_scope(self.engine) as session:
                store.update_run_status(session, run.id, "failed", error_message=str(exc))
                # Eagerly load relationships to prevent DetachedInstanceError or NoneType errors
                run = (
                    session.query(models.Run)
                    .options(
                        joinedload(models.Run.brand),
                        joinedload(models.Run.scenario),
                        joinedload(models.Run.summary)
                    )
                    .get(run.id)
                )
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
        should map to :class:`data.models.ContentAsset` fields. When assets are
        not supplied, this method attempts a lightweight integration with the
        existing ingestion utilities (Brave, Serper, Reddit, YouTube) based on
        configured sources and keywords.
        should map to :class:`data.models.ContentAsset` fields.
        """

        assets = run_config.get("assets")
        if assets:
            return list(assets)

        sources = run_config.get("sources") or []
        keywords = run_config.get("keywords") or []
        limit = int(run_config.get("limit", 10))
        collected: List[dict] = []

        if not sources or not keywords:
            logger.info("No sources/keywords specified; proceeding with empty dataset")
            return collected

        for source in sources:
            source = (source or "").lower()
            if source == "brave":
                collected.extend(self._collect_from_brave(keywords, limit))
            elif source == "serper":
                collected.extend(self._collect_from_serper(keywords, limit))
            elif source == "reddit":
                collected.extend(self._collect_from_reddit(keywords, limit))
            elif source == "youtube":
                collected.extend(self._collect_from_youtube(keywords, limit))
            else:
                logger.info("Unsupported source '%s' - skipping", source)

        return collected

    # ------------------------------------------------------------------
    # Source collectors (lightweight wrappers around existing ingestion code)
    # ------------------------------------------------------------------
    def _collect_from_brave(self, keywords: List[str], limit: int) -> List[dict]:
        try:
            from ingestion.brave_search import collect_brave_pages
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("Brave ingestion unavailable: %s", exc)
            return []

        assets: List[dict] = []
        for kw in keywords:
            pages = collect_brave_pages(query=kw, target_count=limit)
            for page in pages:
                assets.append(
                    {
                        "source_type": "brave",
                        "channel": "web",
                        "url": page.get("url"),
                        "title": page.get("title"),
                        "raw_content": page.get("body") or page.get("content") or page.get("snippet"),
                        "normalized_content": page.get("body") or page.get("content") or page.get("snippet"),
                        "meta_info": {"query": kw},
                    }
                )
        return assets

    def _collect_from_serper(self, keywords: List[str], limit: int) -> List[dict]:
        try:
            from ingestion.serper_search import collect_serper_pages
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("Serper ingestion unavailable: %s", exc)
            return []

        assets: List[dict] = []
        for kw in keywords:
            pages = collect_serper_pages(query=kw, target_count=limit)
            for page in pages:
                assets.append(
                    {
                        "source_type": "serper",
                        "channel": "web",
                        "url": page.get("url"),
                        "title": page.get("title"),
                        "raw_content": page.get("body") or page.get("content") or page.get("snippet"),
                        "normalized_content": page.get("body") or page.get("content") or page.get("snippet"),
                        "meta_info": {"query": kw},
                    }
                )
        return assets

    def _collect_from_reddit(self, keywords: List[str], limit: int) -> List[dict]:
        try:
            from ingestion.reddit_crawler import RedditCrawler
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("Reddit ingestion unavailable: %s", exc)
            return []

        crawler = RedditCrawler()
        assets: List[dict] = []
        for kw in keywords:
            try:
                posts = crawler.search_posts(query=kw, limit=limit)
            except Exception as exc:  # pragma: no cover - network/credential failures
                logger.warning("Reddit search failed for %s: %s", kw, exc)
                continue

            for post in posts:
                assets.append(
                    {
                        "source_type": "reddit",
                        "channel": "social",
                        "url": getattr(post, "url", None) or post.get("url") if hasattr(post, "get") else None,
                        "external_id": getattr(post, "id", None) or post.get("id") if hasattr(post, "get") else None,
                        "title": getattr(post, "title", None) or post.get("title") if hasattr(post, "get") else None,
                        "raw_content": getattr(post, "selftext", None) or post.get("selftext") if hasattr(post, "get") else None,
                        "normalized_content": getattr(post, "selftext", None) or post.get("selftext") if hasattr(post, "get") else None,
                        "meta_info": {"query": kw},
                    }
                )
        return assets

    def _collect_from_youtube(self, keywords: List[str], limit: int) -> List[dict]:
        try:
            from ingestion.youtube_scraper import YouTubeScraper
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("YouTube ingestion unavailable: %s", exc)
            return []

        scraper = YouTubeScraper()
        assets: List[dict] = []
        for kw in keywords:
            try:
                videos = scraper.search_videos(query=kw, max_results=limit)
            except Exception as exc:  # pragma: no cover - network/credential failures
                logger.warning("YouTube search failed for %s: %s", kw, exc)
                continue

            for video in videos:
                transcript = video.get("transcript") if isinstance(video, dict) else None
                assets.append(
                    {
                        "source_type": "youtube",
                        "channel": "video",
                        "url": video.get("url") if isinstance(video, dict) else None,
                        "external_id": video.get("id") if isinstance(video, dict) else None,
                        "title": video.get("title") if isinstance(video, dict) else None,
                        "raw_content": transcript or video.get("description") if isinstance(video, dict) else None,
                        "normalized_content": transcript or video.get("description") if isinstance(video, dict) else None,
                        "modality": "video",
                        "meta_info": {"query": kw},
                    }
                )
        return assets
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

