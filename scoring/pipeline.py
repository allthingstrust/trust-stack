"""
Scoring pipeline for the Trust Stack Rating tool.
Orchestrates scoring, optional legacy classification, and reporting.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from data.models import NormalizedContent, ContentScores, PipelineRun, AuthenticityRatio
from .scorer import ContentScorer
from config.settings import SETTINGS
from .classifier import ContentClassifier

logger = logging.getLogger(__name__)

class ScoringPipeline:
    """Orchestrates the scoring and classification pipeline"""
    
    def __init__(self):
        self.scorer = ContentScorer()
        self.classifier = ContentClassifier()
        # Athena client is optional at runtime (may require boto3). Initialize
        # lazily when upload is requested to allow local runs without AWS deps.
        self.athena_client = None
    
    def run_scoring_pipeline(self, content_list: List[NormalizedContent],
                           brand_config: Dict[str, Any]) -> PipelineRun:
        """
        Run the Trust Stack rating pipeline.

        Flow:
            1. Optional pre-filtering and language detection (legacy behavior kept)
            2. Score content (LLM + attribute detection handled inside ContentScorer)
            3. Optional legacy classification (Authentic/Suspect/Inauthentic)
            4. Optional legacy AR calculation
            5. Upload scores to Athena
        """
        run_id = str(uuid.uuid4())
        brand_id = brand_config.get('brand_id', 'unknown')
        
        # Initialize pipeline run
        pipeline_run = PipelineRun(
            run_id=run_id,
            brand_id=brand_id,
            start_time=datetime.now(),
            status="running"
        )
        
        logger.info(f"Starting scoring pipeline {run_id} for brand {brand_id}")
        logger.info(f"Processing {len(content_list)} content items")
        
        try:
            # Step 0: Filter out error pages, login walls, and insufficient content
            from scoring.content_filter import should_skip_content
            
            filtered_content = []
            skipped_count = 0
            for content in content_list:
                skip_reason = should_skip_content(
                    title=getattr(content, 'title', ''),
                    body=getattr(content, 'body', ''),
                    url=getattr(content, 'url', '')
                )
                
                if skip_reason:
                    logger.info(f"Pre-filtering: Skipped '{content.title}' ({skip_reason})")
                    skipped_count += 1
                else:
                    filtered_content.append(content)
            
            logger.info(f"Pre-filter: Kept {len(filtered_content)}/{len(content_list)} items (skipped {skipped_count} error/login pages)")
            content_list = filtered_content  # Use filtered list for rest of pipeline
            
            # Step 0.5: Detect language for all content
            from utils.language_utils import detect_language
            for content in content_list:
                content.language = detect_language(content.body)
                # Log non-English content for visibility
                if content.language != 'en':
                    logger.info(f"Detected non-English content: {content.title} ({content.language})")
            
            # Step 1: Score content (ContentScorer handles attribute detection internally)
            logger.info("Step 1: Scoring content on Trust Stack dimensions")
            scores_list = self.scorer.batch_score_content(content_list, brand_config)
            pipeline_run.items_processed = len(scores_list)

            # Filter out demoted items if configured
            exclude_demoted = SETTINGS.get('exclude_demoted_from_upload', False)
            if exclude_demoted:
                scores_list = self._filter_demoted(scores_list)

            # Step 2: Classification (legacy mode only)
            legacy_mode = SETTINGS.get('enable_legacy_ar_mode', True)
            if legacy_mode:
                logger.info("Step 2: Classifying content (legacy AR mode)")
                classified_scores = self.classifier.batch_classify_content(scores_list)
            else:
                logger.info("Step 2: Skipping legacy classification; logging Trust Stack rating bands")
                self.classifier.log_rating_band_summary(scores_list)
                classified_scores = scores_list

            # Step 3: Upload scores to S3/Athena
            logger.info("Step 3: Uploading scores to S3/Athena")
            self._upload_scores_to_athena(classified_scores, brand_id)

            # Step 4: Legacy AR calculation (optional)
            ar_result = None
            if legacy_mode:
                logger.info("Step 4: Calculating Legacy Authenticity Ratio")
                ar_result = AuthenticityRatio.from_ratings(
                    ratings=classified_scores,
                    brand_id=brand_id,
                    source=",".join(sorted({s.src for s in classified_scores})),
                    run_id=run_id,
                )

            # Attach results to the pipeline run so callers can use downstream
            pipeline_run.classified_scores = classified_scores
            pipeline_run.ar_result = ar_result

            # Complete pipeline run
            pipeline_run.end_time = datetime.now()
            pipeline_run.status = "completed"

            logger.info(f"Scoring pipeline {run_id} completed successfully")
            if ar_result:
                logger.info(f"Authenticity Ratio: {ar_result.authenticity_ratio_pct:.2f}%")
            
        except Exception as e:
            pipeline_run.end_time = datetime.now()
            pipeline_run.status = "failed"
            pipeline_run.errors.append(str(e))
            logger.error(f"Scoring pipeline {run_id} failed: {e}")
            raise

        return pipeline_run

    def _filter_demoted(self, scores_list: List[ContentScores]) -> List[ContentScores]:
        """Remove demoted items based on triage metadata."""
        original_count = len(scores_list)
        filtered = []

        for score in scores_list:
            meta = getattr(score, "meta", {})
            try:
                if isinstance(meta, str):
                    import json

                    meta = json.loads(meta) if meta else {}
            except Exception:
                meta = {}

            if isinstance(meta, dict) and meta.get("triage_status") == "skipped":
                continue

            filtered.append(score)

        if original_count != len(filtered):
            logger.info(f"Excluded {original_count - len(filtered)} demoted items from results")

        return filtered

    def _upload_scores_to_athena(self, scores_list: List[ContentScores], brand_id: str) -> None:
        """Upload content scores to S3/Athena"""
        if not scores_list:
            logger.warning("No scores to upload")
            return
        
        # Group scores by source
        scores_by_source = {}
        for score in scores_list:
            source = score.src
            if source not in scores_by_source:
                scores_by_source[source] = []
            scores_by_source[source].append(score)
        
        # Upload each source separately. Initialize AthenaClient lazily so
        # environments without boto3 can still run the pipeline locally.
        try:
            if self.athena_client is None:
                from data.athena_client import AthenaClient
                self.athena_client = AthenaClient()
        except Exception as e:
            logger.warning(f"Athena/S3 upload skipped: could not initialize AthenaClient: {e}")
            return

        for source, source_scores in scores_by_source.items():
            run_id = source_scores[0].run_id
            try:
                self.athena_client.upload_content_scores(source_scores, brand_id, source, run_id)
            except Exception as e:
                logger.warning(f"Failed to upload scores for source {source}: {e}")
    
    def get_pipeline_status(self, run_id: str) -> Optional[PipelineRun]:
        """Get status of a pipeline run"""
        # In production, this would query a database
        # For now, return None as we don't persist pipeline runs
        return None
    
    def list_recent_runs(self, brand_id: str, limit: int = 10) -> List[PipelineRun]:
        """List recent pipeline runs for a brand"""
        # In production, this would query a database
        # For now, return empty list
        return []
    
    def analyze_dimension_trends(self, brand_id: str, days: int = 30) -> Dict[str, Any]:
        """Analyze dimension score trends over time"""
        # This would query Athena for historical scores
        # For now, return placeholder analysis
        return {
            "brand_id": brand_id,
            "analysis_period_days": days,
            "trend_analysis": "Placeholder - implement Athena queries for historical data",
            "dimension_trends": {
                "provenance": {"trend": "stable", "average": 0.75},
                "verification": {"trend": "improving", "average": 0.68},
                "transparency": {"trend": "declining", "average": 0.72},
                "coherence": {"trend": "stable", "average": 0.70},
                "resonance": {"trend": "improving", "average": 0.65}
            }
        }
    
    def generate_scoring_report(self, scores_list: List[ContentScores], 
                              brand_config: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed scoring report"""
        # If no scores are provided, return a structured report with zeros so
        # callers don't need to handle a special error case.
        if not scores_list:
            ar_zero = {
                'brand_id': brand_config.get('brand_id', 'unknown'),
                'run_id': 'unknown',
                'total_items': 0,
                'authentic_items': 0,
                'suspect_items': 0,
                'inauthentic_items': 0,
                'authenticity_ratio_pct': 0.0,
                'extended_ar_pct': 0.0
            }

            return {
                "brand_id": brand_config.get('brand_id', 'unknown'),
                "run_id": 'unknown',
                "generated_at": datetime.now().isoformat(),
                "authenticity_ratio": ar_zero,
                "classification_analysis": {},
                "dimension_breakdown": {},
                "total_items_analyzed": 0,
                "rubric_version": "unknown"
            }
        
        # Get classification analysis
        analysis = self.classifier.analyze_dimension_performance(scores_list)
        
        legacy_mode = SETTINGS.get('enable_legacy_ar_mode', True)
        per_item_breakdowns: List[Dict[str, Any]] = []
        ar_result = None

        if legacy_mode:
            ar_result = AuthenticityRatio.from_ratings(
                ratings=scores_list,
                brand_id=brand_config.get('brand_id', 'unknown'),
                source=','.join(sorted({s.src for s in scores_list})),
                run_id=scores_list[0].run_id if scores_list else 'unknown'
            )

        # Reporting expects a dict-like structure (with .get). If we returned
        # an AuthenticityRatio dataclass, convert it to a dict with the
        # previous keys including extended_ar_pct.
        if ar_result and hasattr(ar_result, '__dict__'):
            ar_dict = {
                'brand_id': ar_result.brand_id,
                'run_id': ar_result.run_id,
                'total_items': ar_result.total_items,
                'authentic_items': ar_result.authentic_items,
                'suspect_items': ar_result.suspect_items,
                'inauthentic_items': ar_result.inauthentic_items,
                'authenticity_ratio_pct': ar_result.authenticity_ratio_pct,
                'extended_ar_pct': ar_result.extended_ar
            }
        elif ar_result:
            ar_dict = ar_result
        else:
            ar_dict = {}
        
        # Generate dimension breakdown
        dimension_breakdown = {}
        for dimension in ["provenance", "verification", "transparency", "coherence", "resonance"]:
            scores = [getattr(s, f"score_{dimension}", 0.5) for s in scores_list]  # Default to 0.5 if not present
            dimension_breakdown[dimension] = {
                "average": sum(scores) / len(scores) if scores else 0,
                "min": min(scores) if scores else 0,
                "max": max(scores) if scores else 0,
                "std_dev": self._calculate_std_dev(scores)
            }
        
        report = {
            "brand_id": brand_config.get('brand_id', 'unknown'),
            "run_id": scores_list[0].run_id if scores_list else 'unknown',
            "generated_at": datetime.now().isoformat(),
            "authenticity_ratio": ar_dict,
            "classification_analysis": analysis,
            "dimension_breakdown": dimension_breakdown,
            "total_items_analyzed": len(scores_list),
            # Include data sources used for this report (prefer explicit brand_config, fallback to sources present on scores)
            "sources": brand_config.get('sources') if brand_config.get('sources') else sorted({s.src for s in scores_list}),
            "rubric_version": scores_list[0].rubric_version if scores_list else "unknown"
        }

        # Include per-item appendix if available
        report['appendix'] = per_item_breakdowns if 'per_item_breakdowns' in locals() else []

        # Ensure appendix entries include the original/meta fields from the ContentScores
        # Build an enriched appendix from scores_list and merge any existing breakdowns
        enriched = []
        try:
            import json as _json
            id_to_bd = {d.get('content_id'): d for d in (per_item_breakdowns if 'per_item_breakdowns' in locals() else [])}
            for s in scores_list:
                try:
                    meta = s.meta
                    if isinstance(meta, str):
                        meta_obj = _json.loads(meta) if meta else {}
                    elif isinstance(meta, dict):
                        meta_obj = meta
                    else:
                        meta_obj = {}
                except Exception:
                    meta_obj = {}

                # Smart fallback: ensure channel/platform_type are set
                if not meta_obj.get('channel') or meta_obj.get('channel') == 'unknown':
                    # Try to get from ContentScores attributes first
                    channel = getattr(s, 'channel', 'unknown')
                    platform_type = getattr(s, 'platform_type', 'unknown')

                    # If still unknown, derive from src
                    if channel == 'unknown' or not channel:
                        src_to_channel = {
                            'reddit': ('reddit', 'social'),
                            'youtube': ('youtube', 'social'),
                            'amazon': ('amazon', 'marketplace'),
                            'brave': ('web', 'web'),
                        }
                        src = getattr(s, 'src', '')
                        if src in src_to_channel:
                            channel, platform_type = src_to_channel[src]
                        else:
                            channel = src if src else 'unknown'
                            platform_type = 'unknown'

                    meta_obj['channel'] = channel
                    meta_obj['platform_type'] = platform_type

                dims = {
                    'provenance': getattr(s, 'score_provenance', None),
                    'resonance': getattr(s, 'score_resonance', None),
                    'coherence': getattr(s, 'score_coherence', None),
                    'transparency': getattr(s, 'score_transparency', None),
                    'verification': getattr(s, 'score_verification', None),
                }

                # Compute a simple mean-based final score when rubric weights are not available here (5D)
                try:
                    vals = [
                        float(getattr(s, 'score_provenance', 0.0) or 0.0),
                        float(getattr(s, 'score_resonance', 0.0) or 0.0),
                        float(getattr(s, 'score_coherence', 0.0) or 0.0),
                        float(getattr(s, 'score_transparency', 0.0) or 0.0),
                        float(getattr(s, 'score_verification', 0.0) or 0.0),]
                    from statistics import mean as _mean
                    final_score = float(_mean(vals) * 100.0)
                except Exception:
                    final_score = None

                bd = {
                    'content_id': getattr(s, 'content_id', None),
                    'source': getattr(s, 'src', None),
                    'final_score': final_score,
                    'label': getattr(s, 'class_label', None) or '',
                    'meta': meta_obj,
                    'dimension_scores': dims,
                    'dimensions': dims,  # Alias for markdown_generator compatibility
                }

                # If a breakdown exists from the AR calc, merge its richer fields
                existing = id_to_bd.get(bd.get('content_id'))
                if existing and isinstance(existing, dict):
                    # overlay keys like 'applied_rules', 'rationale', etc.
                    for k, v in existing.items():
                        if k not in bd or not bd.get(k):
                            bd[k] = v

                enriched.append(bd)
        except Exception:
            enriched = per_item_breakdowns if 'per_item_breakdowns' in locals() else []

        report['appendix'] = enriched

        # Compute a content-type breakdown (percentage) using meta JSON where available
        content_type_counts = {}
        total = 0
        for s in scores_list:
            total += 1
            try:
                # meta might be a JSON string or dict depending on upstream. Try to parse
                meta = s.meta
                if isinstance(meta, str):
                    import json as _json
                    meta_obj = _json.loads(meta) if meta else {}
                elif isinstance(meta, dict):
                    meta_obj = meta
                else:
                    meta_obj = {}

                ctype = meta_obj.get('content_type') or getattr(s, 'content_type', None) or 'unknown'
            except Exception:
                ctype = 'unknown'

            content_type_counts[ctype] = content_type_counts.get(ctype, 0) + 1

        # Convert to percentage breakdown
        content_type_pct = {k: (v / total * 100.0) for k, v in content_type_counts.items()} if total > 0 else {}
        report['content_type_breakdown_pct'] = content_type_pct
        # Build a per-item summary for reporting (title/url, per-dimension scores, final score, label)
        per_items = []
        for s in scores_list:
            try:
                meta = s.meta
                if isinstance(meta, str):
                    import json as _json
                    meta_obj = _json.loads(meta) if meta else {}
                elif isinstance(meta, dict):
                    meta_obj = meta
                else:
                    meta_obj = {}
            except Exception:
                meta_obj = {}

            # compute a simple final score from per-dimension scores and SETTINGS weights
            from config.settings import SETTINGS
            w = SETTINGS.get('scoring_weights')
            try:
                final_score = (
                    getattr(s, 'score_provenance', 0.0) * w.provenance +
                    getattr(s, 'score_resonance', 0.0) * w.resonance +
                    getattr(s, 'score_coherence', 0.0) * w.coherence +
                    getattr(s, 'score_transparency', 0.0) * w.transparency +
                    getattr(s, 'score_verification', 0.0) * w.verification
                ) * 100.0
            except Exception:
                final_score = 0.0

            # Prefer LLM-adjusted final score if present in meta
            try:
                if isinstance(meta_obj, dict) and meta_obj.get('_llm_adjusted_score_total'):
                    final_score = float(meta_obj.get('_llm_adjusted_score_total'))
            except Exception:
                pass

            per_items.append({
                'content_id': s.content_id,
                'source': getattr(s, 'src', ''),
                'final_score': final_score,
                'label': getattr(s, 'class_label', '') or '',
                'meta': meta_obj,
                'title': meta_obj.get('title') or getattr(s, 'title', None),
                'body': getattr(s, 'body', None) or meta_obj.get('description') or meta_obj.get('snippet')
            })

        report['items'] = per_items

        # Score-based AR: mean of per-item final scores (0-100) converted to percentage
        try:
            if per_items:
                score_mean = sum([it.get('final_score', 0.0) for it in per_items]) / len(per_items)
            else:
                score_mean = 0.0
        except Exception:
            score_mean = 0.0
        report['score_based_ar_pct'] = float(score_mean)
        
        return report
    
    def _calculate_std_dev(self, scores: List[float]) -> float:
        """Calculate standard deviation"""
        if len(scores) < 2:
            return 0.0
        
        mean = sum(scores) / len(scores)
        variance = sum((x - mean) ** 2 for x in scores) / (len(scores) - 1)
        return variance ** 0.5
