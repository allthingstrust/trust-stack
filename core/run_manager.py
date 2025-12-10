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
            run_id = run.id
            store.update_run_status(session, run_id, "in_progress")

        # Ingestion and scoring can be expensive; perform outside the session scope and re-open
        try:
            assets = self._collect_assets(run_config)
            with store.session_scope(self.engine) as session:
                persisted_assets = store.bulk_insert_assets(session, run_id=run_id, assets=assets)
                session.expunge_all()

            scores = self._score_assets(persisted_assets, run_config)
            with store.session_scope(self.engine) as session:
                store.bulk_insert_dimension_scores(session, scores)
                averages = self._calculate_averages(scores)
                store.create_truststack_summary(
                    session,
                    run_id=run_id,
                    averages=averages,
                    authenticity_ratio=averages.get("authenticity_ratio"),
                    overall_score=averages.get("overall_score"),
                )
                store.update_run_status(session, run_id, "completed")
                # Eagerly load relationships to prevent DetachedInstanceError or NoneType errors
                run = (
                    session.query(models.Run)
                    .options(
                        joinedload(models.Run.brand),
                        joinedload(models.Run.scenario),
                        joinedload(models.Run.summary),
                        joinedload(models.Run.assets).joinedload(models.ContentAsset.scores)
                    )
                    .get(run_id)
                )
                session.expunge_all()

            if run_config.get("export_to_s3"):
                export_s3.export_run_to_s3(self.engine, run_id, bucket=run_config.get("s3_bucket"))
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Run %s failed", external_id)
            with store.session_scope(self.engine) as session:
                store.update_run_status(session, run_id, "failed", error_message=str(exc))
                # Eagerly load relationships to prevent DetachedInstanceError or NoneType errors
                run = (
                    session.query(models.Run)
                    .options(
                        joinedload(models.Run.brand),
                        joinedload(models.Run.scenario),
                        joinedload(models.Run.summary),
                        joinedload(models.Run.assets).joinedload(models.ContentAsset.scores)
                    )
                    .get(run_id)
                )
                session.expunge_all()
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
            # For pre-provided assets, check if they need content fetching
            # This handles the case where webapp passes URLs without body content
            fetched_assets = []
            assets_needing_fetch = []
            
            for asset in assets:
                raw_content = asset.get("raw_content") or asset.get("normalized_content") or ""
                if not raw_content and asset.get("url"):
                    assets_needing_fetch.append(asset)
                else:
                    fetched_assets.append(asset)
            
            # Fetch content for assets that need it
            if assets_needing_fetch:
                logger.info(f"Fetching content for {len(assets_needing_fetch)} pre-provided assets with empty body")
                try:
                    from ingestion.page_fetcher import fetch_pages_parallel
                    from ingestion.playwright_manager import get_browser_manager
                    
                    browser_manager = get_browser_manager()
                    browser_manager.start()
                    
                    urls = [a.get("url") for a in assets_needing_fetch if a.get("url")]
                    fetch_results = fetch_pages_parallel(urls, browser_manager=browser_manager)
                    
                    # Build a URL -> result map
                    url_to_result = {r.get("url"): r for r in fetch_results}
                    
                    for asset in assets_needing_fetch:
                        url = asset.get("url")
                        result = url_to_result.get(url, {})
                        body = result.get("body") or ""
                        
                        asset["raw_content"] = body
                        asset["normalized_content"] = body
                        asset["title"] = asset.get("title") or result.get("title") or ""
                        
                        # Preserve structured body if available
                        if result.get("structured_body"):
                            if not asset.get("meta_info"):
                                asset["meta_info"] = {}
                            asset["meta_info"]["structured_body"] = result.get("structured_body")
                        
                        fetched_assets.append(asset)
                        logger.debug(f"Fetched {len(body)} chars for {url}")
                        
                except Exception as e:
                    logger.error(f"Failed to fetch content for pre-provided assets: {e}")
                    # Still append the assets even if fetch failed
                    fetched_assets.extend(assets_needing_fetch)
            
            return fetched_assets

        sources = run_config.get("sources") or []
        keywords = run_config.get("keywords") or []
        limit = int(run_config.get("limit", 10))
        collected: List[dict] = []

        if not sources or not keywords:
            logger.info("No sources/keywords specified; proceeding with empty dataset")
            return collected

        for source in sources:
            source = (source or "").lower()
            
            # Map 'web' to the configured search provider
            if source == "web":
                from config.settings import get_secret
                provider = get_secret('SEARCH_PROVIDER', 'brave').lower()
                logger.info(f"'web' source requested, using configured provider: {provider}")
                source = provider
            
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
                        "meta_info": {
                            "query": kw,
                            "source_url": page.get("url"),
                            "title": page.get("title"),
                            "description": (page.get("body") or "")[:500]
                        },
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
                        "meta_info": {
                            "query": kw,
                            "source_url": page.get("url"),
                            "title": page.get("title"),
                            "description": (page.get("body") or "")[:500]
                        },
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
                        "meta_info": {
                            "query": kw,
                            "source_url": getattr(post, "url", None) or post.get("url") if hasattr(post, "get") else None,
                            "title": getattr(post, "title", None) or post.get("title") if hasattr(post, "get") else None,
                        },
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
                        "meta_info": {
                            "query": kw,
                            "source_url": video.get("url") if isinstance(video, dict) else None,
                            "title": video.get("title") if isinstance(video, dict) else None,
                        },
                    }
                )
        return assets
        # TODO: integrate ingestion modules (brave, reddit, youtube) based on scenario config
        logger.info("No assets supplied; proceeding with empty dataset")
        return []

    def _extract_rationale_from_content_scores(self, cs) -> dict:
        """Extract detected_attributes and dimension signals from ContentScores.meta for persistence."""
        import json
        
        rationale = {}
        
        # cs.meta may be a JSON string or dict
        meta = cs.meta if hasattr(cs, 'meta') else {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except:
                meta = {}
        
        # Extract detected_attributes if present
        if isinstance(meta, dict):
            detected_attrs = meta.get('detected_attributes', [])
            if detected_attrs:
                rationale['detected_attributes'] = detected_attrs
            
            # v5.1: Extract dimension signals for downstream aggregation
            dimensions = meta.get('dimensions', {})
            if dimensions:
                rationale['dimensions'] = dimensions
            
            # Also preserve other useful meta fields
            for key in ['attribute_count', 'source_type', 'channel']:
                if key in meta:
                    rationale[key] = meta[key]
        
        return rationale


    def _score_assets(self, assets: List[ContentAsset], run_config: dict) -> List[dict]:
        """Score a list of persisted assets.

        The RunManager supports injecting a custom scoring pipeline for tests
        or lightweight runs. If no pipeline is provided, a simple heuristic is
        used to generate placeholder scores.
        """

        # Check for ContentScorer with batch_score_content (the actual scoring method)
        if self.scoring_pipeline and hasattr(self.scoring_pipeline, "batch_score_content"):
            try:
                from data.models import NormalizedContent
                from datetime import datetime
                import json
                
                # Create mapping from content_id to asset for later lookup
                content_id_to_asset = {}
                normalized_content_list = []
                
                for asset in assets:
                    # Extract meta_info safely
                    meta = asset.meta_info or {}
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except:
                            meta = {}
                    
                    content_id = str(asset.id)
                    content_id_to_asset[content_id] = asset
                    
                    nc = NormalizedContent(
                        content_id=content_id,
                        src=asset.source_type or "web",
                        platform_id=asset.url or "",
                        author=meta.get("author", "unknown"),
                        title=asset.title or "",
                        body=asset.normalized_content or asset.raw_content or "",
                        run_id=str(asset.run_id),
                        event_ts=datetime.now().isoformat(),
                        meta=meta,
                        url=asset.url or "",
                        modality=asset.modality or "text",
                        channel=asset.channel or "web",
                        platform_type=meta.get("platform_type", "web"),
                        source_type=asset.source_type or "web",
                        source_tier=meta.get("source_tier", "unknown"),
                    )
                    normalized_content_list.append(nc)
                
                # Build brand context from run_config
                brand_context = {
                    "brand_name": run_config.get("brand_name", "unknown"),
                    "brand_id": run_config.get("brand_name", "unknown"),
                    "keywords": run_config.get("keywords", []),
                    "sources": run_config.get("sources", []),
                }
                
                # Call the actual Trust Stack scorer
                logger.info(f"Scoring {len(normalized_content_list)} assets with ContentScorer.batch_score_content()")
                content_scores_list = self.scoring_pipeline.batch_score_content(normalized_content_list, brand_context)
                
                # Track which assets were scored by ContentScorer
                scored_asset_ids = set()
                scored = []
                
                # Convert ContentScores back to the dict format expected by RunManager
                for cs in content_scores_list:
                    # ContentScores.content_id maps back to asset.id
                    asset_id = int(cs.content_id) if cs.content_id and cs.content_id.isdigit() else None
                    if asset_id:
                        scored_asset_ids.add(asset_id)
                    
                    # Calculate overall score from dimension scores (5D average)
                    dims = [
                        cs.score_provenance or 0,
                        cs.score_verification or 0,
                        cs.score_transparency or 0,
                        cs.score_coherence or 0,
                        cs.score_resonance or 0,
                    ]
                    overall = sum(dims) / len(dims) if dims else 0
                    
                    # Classification based on overall score
                    if overall >= 0.75:
                        classification = "Excellent"
                    elif overall >= 0.5:
                        classification = "Good"
                    elif overall >= 0.25:
                        classification = "Fair"
                    else:
                        classification = "Poor"
                    
                    scored.append({
                        "asset_id": asset_id,
                        "score_provenance": cs.score_provenance or 0,
                        "score_verification": cs.score_verification or 0,
                        "score_transparency": cs.score_transparency or 0,
                        "score_coherence": cs.score_coherence or 0,
                        "score_resonance": cs.score_resonance or 0,
                        "score_ai_readiness": overall,
                        "overall_score": overall,
                        "classification": classification,
                        # Include detected_attributes in rationale for persistence
                        "rationale": self._extract_rationale_from_content_scores(cs),
                    })
                
                logger.info(f"ContentScorer completed: {len(scored)} assets scored via LLM")
                
                # For any assets that were filtered out by ContentScorer (insufficient content),
                # apply heuristic fallback scoring so they still appear in the report
                unscored_assets = [a for a in assets if a.id not in scored_asset_ids]
                if unscored_assets:
                    logger.info(f"Applying heuristic fallback to {len(unscored_assets)} unscored assets (filtered by ContentScorer)")
                    for asset in unscored_assets:
                        length = len(asset.normalized_content or asset.raw_content or "")
                        # For items with no content, use a moderate baseline (0.5) rather than 0.1
                        # This reflects that we couldn't fetch the content, not that it's bad
                        if length == 0:
                            baseline = 0.5  # Neutral score for unfetchable content
                        else:
                            baseline = min(1.0, 0.3 + (length / 2000.0))  # Better baseline for short content
                        
                        scored.append({
                            "asset_id": asset.id,
                            "score_provenance": baseline,
                            "score_verification": baseline,
                            "score_transparency": baseline,
                            "score_coherence": baseline,
                            "score_resonance": baseline,
                            "score_ai_readiness": baseline,
                            "overall_score": baseline,
                            "classification": "Fair" if baseline >= 0.4 else "Poor",
                        })
                
                logger.info(f"Total scores: {len(scored)} assets (LLM: {len(scored_asset_ids)}, heuristic: {len(unscored_assets)})")
                return scored
                
            except Exception as e:
                logger.warning(f"ContentScorer scoring failed, falling back to heuristic: {e}")
                import traceback
                logger.warning(traceback.format_exc())

        # Legacy support: check for score_assets method
        if self.scoring_pipeline and hasattr(self.scoring_pipeline, "score_assets"):
            return list(self.scoring_pipeline.score_assets(assets, run_config))

        # Fallback heuristic scoring (only if no scoring pipeline available)
        logger.warning("No scoring pipeline available, using fallback heuristic scoring")
        scored: List[dict] = []
        for asset in assets:
            length = len(asset.normalized_content or asset.raw_content or "")
            # For items with no content, use a moderate baseline
            if length == 0:
                baseline = 0.5  # Neutral score for unfetchable content
            else:
                baseline = min(1.0, 0.3 + (length / 2000.0))
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
                    "classification": "Fair" if baseline >= 0.4 else "Poor",
                }
            )
        return scored

    def _calculate_averages(self, scores: Iterable[dict]) -> Dict[str, float]:
        """Calculate dimension averages using v5.1 aggregator with caps/penalties.
        
        This uses the ScoringAggregator to apply:
        - Visibility-based weight multipliers
        - Knockout caps (max 4.0 if knockout signal fails)
        - Core deficit caps (max 6.0 if core signal is low)
        - Coverage penalties
        """
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

        # Try to use v5.1 aggregator for proper dimension scoring
        try:
            from scoring.aggregator import ScoringAggregator
            from scoring.rubric import load_rubric
            from scoring.types import SignalScore
            import json
            
            rubric = load_rubric()
            trust_signals_config = rubric.get('trust_signals', {})
            
            if trust_signals_config:
                aggregator = ScoringAggregator(trust_signals_config)
                
                # Collect all signals from rationale.dimensions across all scored items
                all_signals = []
                for s in scores:
                    rationale = s.get('rationale', {})
                    if not rationale:
                        continue
                    
                    # Extract signals from dimension details if present
                    dimensions = rationale.get('dimensions', {})
                    for dim_name, dim_data in dimensions.items():
                        if not isinstance(dim_data, dict):
                            continue
                        signals_list = dim_data.get('signals', [])
                        for sig in signals_list:
                            if not isinstance(sig, dict):
                                continue
                            try:
                                signal = SignalScore(
                                    id=sig.get('id', ''),
                                    label=sig.get('label', ''),
                                    dimension=sig.get('dimension', dim_name.capitalize()),
                                    value=float(sig.get('value', 0)),
                                    weight=float(sig.get('weight', 0.2)),
                                    evidence=sig.get('evidence', []),
                                    rationale=sig.get('rationale', ''),
                                    confidence=float(sig.get('confidence', 1.0))
                                )
                                all_signals.append(signal)
                            except (ValueError, TypeError) as e:
                                logger.debug(f"Skipping malformed signal: {e}")
                                continue
                
                if all_signals:
                    # Aggregate using v5.1 logic with caps and penalties
                    dimension_scores = {}
                    for dim_name in ["Provenance", "Verification", "Transparency", "Coherence", "Resonance"]:
                        dim_score = aggregator.aggregate_dimension(dim_name, all_signals)
                        # Store on 0-1 scale (will be multiplied by 10 in reports)
                        dimension_scores[dim_name.lower()] = dim_score.value / 10.0
                    
                    # Calculate overall using aggregator
                    dim_score_objs = [aggregator.aggregate_dimension(d, all_signals) 
                                      for d in ["Provenance", "Verification", "Transparency", "Coherence", "Resonance"]]
                    trust_score = aggregator.calculate_trust_score(dim_score_objs)
                    
                    logger.info(f"Aggregated dimension scores using v5.1: {dimension_scores}")
                    
                    return {
                        "avg_provenance": dimension_scores.get("provenance"),
                        "avg_verification": dimension_scores.get("verification"),
                        "avg_transparency": dimension_scores.get("transparency"),
                        "avg_coherence": dimension_scores.get("coherence"),
                        "avg_resonance": dimension_scores.get("resonance"),
                        "avg_ai_readiness": dimension_scores.get("resonance"),  # Fallback
                        "overall_score": trust_score.overall / 100.0,  # 0-1 scale
                        "authenticity_ratio": trust_score.overall / 100.0,
                    }
        except Exception as e:
            logger.warning(f"v5.1 aggregation failed, falling back to simple averages: {e}")

        # Fallback: simple per-item averages (legacy behavior)
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

