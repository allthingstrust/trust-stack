"""
Scoring pipeline for AR tool
Orchestrates the scoring and classification process
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from data.models import NormalizedContent, ContentScores, PipelineRun, AuthenticityRatio
from .scorer import ContentScorer
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
        Run the complete scoring pipeline
        
        Args:
            content_list: List of normalized content to score
            brand_config: Brand configuration and context
            
        Returns:
            PipelineRun object with execution details
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
            
            # Step 1: Score content (Triage is handled internally by ContentScorer)
            logger.info("Step 1: Scoring content on 5D dimensions")
            scores_list = self.scorer.batch_score_content(content_list, brand_config)
            pipeline_run.items_processed += len(scores_list)
            
            # Filter out demoted items if configured
            exclude_demoted = SETTINGS.get('exclude_demoted_from_upload', False)
            if exclude_demoted:
                original_count = len(scores_list)
                scores_list = [s for s in scores_list if not (isinstance(s.meta, dict) and s.meta.get('triage_status') == 'skipped')]
                # Handle case where meta is a string (JSON)
                if len(scores_list) == original_count:
                    # Try checking serialized meta if dict check didn't filter anything
                    import json
                    filtered = []
                    for s in scores_list:
                        try:
                            if isinstance(s.meta, str):
                                m = json.loads(s.meta)
                                if m.get('triage_status') == 'skipped':
                                    continue
                            elif isinstance(s.meta, dict):
                                if s.meta.get('triage_status') == 'skipped':
                                    continue
                        except:
                            pass
                        filtered.append(s)
                    scores_list = filtered
                
                if len(scores_list) < original_count:
                    logger.info(f"Excluded {original_count - len(scores_list)} demoted items from results")
            
            # Step 2: Classify content (Authentic/Suspect/Inauthentic)
            logger.info("Step 2: Classifying content")
            classified_scores = self.classifier.batch_classify_content(scores_list)
            
            # Step 3: Upload scores to S3/Athena
            logger.info("Step 3: Uploading scores to S3/Athena")
            self._upload_scores_to_athena(classified_scores, brand_id)
            
            # Step 4: Calculate and log Authenticity Ratio
            logger.info("Step 4: Calculating Authenticity Ratio")
            ar_calc = self._calculate_authenticity_ratio(classified_scores, brand_id, run_id, include_appendix=True)
            # _calculate_authenticity_ratio may return (AuthenticityRatio, per_item_breakdowns)
            if isinstance(ar_calc, tuple) and len(ar_calc) == 2:
                ar_result, per_item_breakdowns = ar_calc
            else:
                ar_result = ar_calc
                per_item_breakdowns = []
            
            # Attach classified scores to the pipeline run so callers can use
            # the exact objects that were uploaded to S3/Athena.
            pipeline_run.classified_scores = classified_scores

            # Complete pipeline run
            pipeline_run.end_time = datetime.now()
            pipeline_run.status = "completed"
            
            logger.info(f"Scoring pipeline {run_id} completed successfully")
            try:
                logger.info(f"Authenticity Ratio: {ar_result.authenticity_ratio_pct:.2f}%")
            except Exception:
                logger.info(f"Authenticity Ratio computed")

            # Attach per-item appendix to the pipeline run for callers that
            # want to render a detailed appendix in reports or UIs.
            try:
                pipeline_run.appendix = per_item_breakdowns
            except Exception:
                # Non-fatal if PipelineRun dataclass doesn't accept arbitrary attrs
                pass
            
        except Exception as e:
            pipeline_run.end_time = datetime.now()
            pipeline_run.status = "failed"
            pipeline_run.errors.append(str(e))
            logger.error(f"Scoring pipeline {run_id} failed: {e}")
            raise
        
        return pipeline_run
    
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
    
    def _calculate_authenticity_ratio(self, scores_list: List[ContentScores], 
                                    brand_id: str, run_id: str,
                                    include_appendix: bool = False) -> AuthenticityRatio:
        """Calculate Authenticity Ratio from scores.

        By default this function returns an AuthenticityRatio dataclass. If
        include_appendix=True it returns a tuple: (AuthenticityRatio, per_item_breakdowns).
        """
        if not scores_list:
            logger.info(f"AR Calculation for {brand_id}: no scores")
            return (
                AuthenticityRatio(
                brand_id=brand_id,
                source=",",
                run_id=run_id,
                total_items=0,
                authentic_items=0,
                suspect_items=0,
                inauthentic_items=0,
                authenticity_ratio_pct=0.0
                ), []
            )

        # Load rubric (weights, thresholds, attributes, defaults)
        from scoring.rubric import load_rubric
        rubric = load_rubric()
        weights = rubric.get('dimension_weights', {})
        thresholds = rubric.get('thresholds', {'authentic': 75, 'suspect': 40})
        attributes_cfg = rubric.get('attributes', [])
        defaults = rubric.get('defaults', {})

        # triage settings
        max_llm_items = defaults.get('max_llm_items', 5)
        triage_method = defaults.get('triage_method', 'top_uncertain')

        def _parse_meta(s: ContentScores):
            meta = {}
            try:
                if isinstance(s.meta, str):
                    import json as _json
                    meta = _json.loads(s.meta) if s.meta else {}
                elif isinstance(s.meta, dict):
                    meta = s.meta
            except Exception:
                meta = {}
            return meta

        authentic_count = 0
        suspect_count = 0
        inauthentic_count = 0
        total_count = len(scores_list)

        per_item_breakdowns = []
        for s in scores_list:
            # Defensive defaults for missing scores (5D)
            p = getattr(s, 'score_provenance', 0.0) or 0.0
            r = getattr(s, 'score_resonance', 0.0) or 0.0
            c = getattr(s, 'score_coherence', 0.0) or 0.0
            t = getattr(s, 'score_transparency', 0.0) or 0.0
            v = getattr(s, 'score_verification', 0.0) or 0.0
            # Base weighted score (0-100). Use weights.get to be resilient.
            base = (
                p * weights.get('provenance', 0.0) +
                r * weights.get('resonance', 0.0) +
                c * weights.get('coherence', 0.0) +
                t * weights.get('transparency', 0.0) +
                v * weights.get('verification', 0.0)
            ) * 100.0

            # Metadata bonuses/penalties applied from attributes_cfg
            meta = _parse_meta(s)
            # Normalize/enrich meta so reporting can rely on common keys
            try:
                # prefer existing keys but fall back to content fields on the score
                if isinstance(meta, dict):
                    meta_title = meta.get('title') or getattr(s, 'title', None) or meta.get('name')
                    meta_desc = meta.get('description') or meta.get('snippet') or getattr(s, 'body', None)
                    meta_url = meta.get('source_url') or meta.get('url') or getattr(s, 'platform_id', None)
                    meta_modality = meta.get('modality') or getattr(s, 'modality', 'text')
                    meta_channel = meta.get('channel') or getattr(s, 'channel', 'unknown')
                    meta_platform_type = meta.get('platform_type') or getattr(s, 'platform_type', 'unknown')

                    if meta_title:
                        meta['title'] = meta_title
                    if meta_desc:
                        meta['description'] = meta_desc
                    if meta_url:
                        meta['source_url'] = meta_url
                    if meta_modality:
                        meta['modality'] = meta_modality
                    if meta_channel:
                        meta['channel'] = meta_channel
                    if meta_platform_type:
                        meta['platform_type'] = meta_platform_type
                else:
                    meta = {}
            except Exception:
                meta = {}
            applied_rules = []

            for attr in attributes_cfg:
                if not attr.get('enabled', True):
                    continue
                aid = attr.get('id')
                effect = attr.get('effect', 'bonus')
                val = attr.get('value', 0) or 0
                # condition support: e.g., {op: '>=', threshold: 0.8}
                condition = attr.get('condition')
                match_meta_keys = attr.get('match_meta', [])

                triggered = False
                reason = None

                # If a numeric condition is present, attempt to evaluate against meta
                if condition and match_meta_keys:
                    # try to find a numeric field in meta matching any key
                    for mk in match_meta_keys:
                        if mk in meta:
                            try:
                                mval = float(meta.get(mk))
                                op = condition.get('op')
                                th = float(condition.get('threshold'))
                                if op == '>=' and mval >= th:
                                    triggered = True
                                    reason = f"{mk} {mval} {op} {th}"
                                    break
                                if op == '<=' and mval <= th:
                                    triggered = True
                                    reason = f"{mk} {mval} {op} {th}"
                                    break
                                if op == '>' and mval > th:
                                    triggered = True
                                    reason = f"{mk} {mval} {op} {th}"
                                    break
                                if op == '<' and mval < th:
                                    triggered = True
                                    reason = f"{mk} {mval} {op} {th}"
                                    break
                            except Exception:
                                continue
                else:
                    # Otherwise, trigger if any of match_meta_keys present and truthy in meta
                    for mk in match_meta_keys:
                        if mk in meta and meta.get(mk):
                            triggered = True
                            reason = f"meta.{mk} present"
                            break

                if triggered and val != 0:
                    applied_rules.append({
                        "id": aid,
                        "effect": effect,
                        "value": val,
                        "reason": reason,
                        "dimension": attr.get('dimension'),
                        "label": attr.get('label')  # Include label for UI display
                    })
                    if effect == 'bonus':
                        base += float(val)
                    elif effect == 'penalty':
                        base -= float(abs(val))

            # Clamp
            item_score = max(0.0, min(100.0, base))

            # Classification thresholds from config
            auth_th = thresholds.get('authentic', 75.0)
            susp_th = thresholds.get('suspect', 40.0)

            label = 'inauthentic'
            if item_score >= auth_th:
                label = 'authentic'
            elif item_score >= susp_th:
                label = 'suspect'
            else:
                label = 'inauthentic'

            # Persist classification back to the ContentScores object so
            # subsequent logic and AR counting use the same final labels.
            try:
                s.class_label = label
                s.is_authentic = True if label == 'authentic' else False
            except Exception:
                pass

            # Build dimension scores dict (5D)
            dim_scores = {
                'provenance': p,
                'resonance': r,
                'coherence': c,
                'transparency': t,
                'verification': v,
            }

            per_item_breakdowns.append({
                'content_id': s.content_id,
                'source': getattr(s, 'src', ''),
                'event_ts': getattr(s, 'event_ts', ''),
                'dimension_scores': dim_scores,
                'dimensions': dim_scores,  # Alias for compatibility with markdown_generator
                'base_score': base,
                'applied_rules': applied_rules,
                'final_score': item_score,
                'label': label,
                'meta': meta,
            })

        # Triage: select items for LLM review based on triage_method
        try:
            auth_th = thresholds.get('authentic', 75.0)
            susp_th = thresholds.get('suspect', 40.0)
        except Exception:
            auth_th = 75.0
            susp_th = 40.0

        triage_candidates = [d for d in per_item_breakdowns if d['label'] == 'suspect']
        selected_for_llm = []
        if triage_method == 'top_uncertain' and triage_candidates:
            mid = (auth_th + susp_th) / 2.0
            triage_candidates.sort(key=lambda x: abs(x['final_score'] - mid))
            selected_for_llm = triage_candidates[:max_llm_items]

        # Log triage selection
        if selected_for_llm:
            ids = [x['content_id'] for x in selected_for_llm]
            logger.info(f"Triage selected {len(ids)} items for LLM review (max_llm_items={max_llm_items}): {ids}")

            # Call LLM for selected items and merge results back
            try:
                from scoring.llm import LLMClient
                llm = LLMClient(model=defaults.get('llm_model'))
                # prepare items
                batch_items = []
                for item in selected_for_llm:
                    batch_items.append({
                        'content_id': item['content_id'],
                        'meta': {},
                        'final_score': item['final_score']
                    })

                llm_results = llm.classify(batch_items, rubric_version=defaults.get('version', 'unknown'))

                # Merge LLM labels back into scores_list (ContentScores)
                id_to_score = {s.content_id: s for s in scores_list}
                for cid, res in llm_results.items():
                    s = id_to_score.get(cid)
                    if not s:
                        continue
                    label = res.get('label') if isinstance(res, dict) else None
                    conf = res.get('confidence') if isinstance(res, dict) else None
                    if label:
                        s.class_label = label
                        s.is_authentic = True if label == 'authentic' else False
                        # attach llm confidence to meta for traceability
                        try:
                            import json as _json
                            meta = _json.loads(s.meta) if isinstance(s.meta, str) and s.meta else (s.meta or {})
                        except Exception:
                            meta = {}
                        meta['_llm_classification'] = {'label': label, 'confidence': conf}
                        try:
                            s.meta = _json.dumps(meta)
                        except Exception:
                            s.meta = str(meta)
                # Apply small per-dimension score adjustments based on LLM confidence
                try:
                    adj_scale = float(defaults.get('llm_score_adjustment_scale', 20.0))
                except Exception:
                    adj_scale = 20.0

                # Build lookup for breakdowns
                id_to_breakdown = {d['content_id']: d for d in per_item_breakdowns}
                for cid, res in llm_results.items():
                    bd = id_to_breakdown.get(cid)
                    if not bd:
                        continue
                    if isinstance(res, dict):
                        label = res.get('label')
                        try:
                            conf = float(res.get('confidence') or 0)
                        except Exception:
                            conf = 0.0
                        # Only adjust when we have a confident auth/inauth result
                        if label in ('authentic', 'inauthentic') and conf > 0:
                            # delta in fractional dimension points (0-1)
                            dim_delta = (conf - 0.5) * adj_scale / 100.0

                            # Update the underlying ContentScores per-dimension
                            s = id_to_score.get(cid)
                            if not s:
                                continue
                            # capture original per-dimension scores
                            orig_scores = {
                                'provenance': getattr(s, 'score_provenance', 0.0) or 0.0,
                                'resonance': getattr(s, 'score_resonance', 0.0) or 0.0,
                                'coherence': getattr(s, 'score_coherence', 0.0) or 0.0,
                                'transparency': getattr(s, 'score_transparency', 0.0) or 0.0,
                                'verification': getattr(s, 'score_verification', 0.0) or 0.0,
                            }

                            # compute original weighted (0-100)
                            orig_weighted = (
                                orig_scores['provenance'] * weights.get('provenance', 0.0) +
                                orig_scores['resonance'] * weights.get('resonance', 0.0) +
                                orig_scores['coherence'] * weights.get('coherence', 0.0) +
                                orig_scores['transparency'] * weights.get('transparency', 0.0) +
                                orig_scores['verification'] * weights.get('verification', 0.0)
                            ) * 100.0

                            # apply delta sign
                            sign = 1 if label == 'authentic' else -1
                            new_scores = {}
                            for dim, orig in orig_scores.items():
                                ns = max(0.0, min(1.0, orig + sign * dim_delta))
                                new_scores[dim] = ns
                                setattr(s, f"score_{dim}", ns)

                            # compute new weighted + preserve attribute additive total
                            new_weighted = (
                                new_scores['provenance'] * weights.get('provenance', 0.0) +
                                new_scores['resonance'] * weights.get('resonance', 0.0) +
                                new_scores['coherence'] * weights.get('coherence', 0.0) +
                                new_scores['transparency'] * weights.get('transparency', 0.0) +
                                new_scores['verification'] * weights.get('verification', 0.0)
                            ) * 100.0

                            # attribute additive total = bd.base_score - orig_weighted
                            attribute_total = bd.get('base_score', 0.0) - orig_weighted
                            new_final = max(0.0, min(100.0, new_weighted + attribute_total))
                            bd['final_score'] = new_final

                            # annotate meta with details
                            try:
                                import json as _json
                                meta = _json.loads(s.meta) if isinstance(s.meta, str) and s.meta else (s.meta or {})
                            except Exception:
                                meta = {}
                            meta['_llm_adjusted_scores'] = new_scores
                            meta['_llm_adjusted_score_total'] = new_final
                            meta['_llm_classification_confidence'] = conf
                            try:
                                s.meta = _json.dumps(meta)
                            except Exception:
                                s.meta = str(meta)
            except Exception as e:
                logger.warning(f"LLM classification failed or not available: {e}")

        # After potential LLM adjustments, recompute authentic/suspect/inauthentic
        # counts from the (possibly) updated ContentScores so the AR reflects
        # the final labels returned to callers and uploaded to Athena.
        try:
            authentic_count = sum(1 for sc in scores_list if getattr(sc, 'class_label', None) == 'authentic')
            suspect_count = sum(1 for sc in scores_list if getattr(sc, 'class_label', None) == 'suspect')
            inauthentic_count = sum(1 for sc in scores_list if getattr(sc, 'class_label', None) == 'inauthentic')
        except Exception:
            # Fallback to zeros if something unexpected happens
            authentic_count = 0
            suspect_count = 0
            inauthentic_count = 0

        # Sync per_item_breakdowns labels with any final class_label present on
        # the ContentScores to keep per-item diagnostics consistent.
        try:
            id_to_score = {s.content_id: s for s in scores_list}
            for bd in per_item_breakdowns:
                s_obj = id_to_score.get(bd.get('content_id'))
                if s_obj and getattr(s_obj, 'class_label', None):
                    bd['label'] = getattr(s_obj, 'class_label')
                    # If LLM adjusted a final score, prefer that
                    try:
                        import json as _json
                        meta = _json.loads(s_obj.meta) if isinstance(s_obj.meta, str) and s_obj.meta else (s_obj.meta or {})
                    except Exception:
                        meta = {}
                    if isinstance(meta, dict) and meta.get('_llm_adjusted_score_total'):
                        bd['final_score'] = float(meta.get('_llm_adjusted_score_total'))
        except Exception:
            # Non-fatal; per-item diagnostics are best-effort
            pass

        # Calculate Core AR percentage (authentic items / total *100)
        core_ar = (authentic_count / total_count * 100.0) if total_count > 0 else 0.0

        # Build source string from unique sources in the scores list
        sources = sorted({s.src for s in scores_list})
        source_str = ",".join(sources) if sources else ""

        logger.info(f"AR Calculation for {brand_id}:")
        logger.info(f"  Total items: {total_count}")
        logger.info(f"  Authentic: {authentic_count} ({(authentic_count/total_count*100) if total_count else 0:.1f}%)")
        logger.info(f"  Suspect: {suspect_count} ({(suspect_count/total_count*100) if total_count else 0:.1f}%)")
        logger.info(f"  Inauthentic: {inauthentic_count} ({(inauthentic_count/total_count*100) if total_count else 0:.1f}%)")
        logger.info(f"  Core AR: {core_ar:.2f}%")

        ar = AuthenticityRatio(
                brand_id=brand_id,
                source=source_str,
                run_id=run_id,
                total_items=total_count,
                authentic_items=authentic_count,
                suspect_items=suspect_count,
                inauthentic_items=inauthentic_count,
                authenticity_ratio_pct=core_ar
            )
        if include_appendix:
            return (ar, per_item_breakdowns)
        return ar
    
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
        
        # Calculate AR. If the provided scores_list appears to be pre-classified
        # (i.e., class_label values are set to authentic/suspect/inauthentic),
        # derive AR from those labels so callers that pass in pre-classified
        # scores get consistent reporting. Otherwise, compute AR using the
        # rubric-based calculator (_calculate_authenticity_ratio).
        preclassified = any(getattr(s, 'class_label', None) not in (None, 'pending') for s in scores_list)
        if preclassified:
            authentic_count = sum(1 for s in scores_list if s.class_label == 'authentic')
            suspect_count = sum(1 for s in scores_list if s.class_label == 'suspect')
            inauthentic_count = sum(1 for s in scores_list if s.class_label == 'inauthentic')
            total_count = len(scores_list)
            core_pct = (authentic_count / total_count * 100.0) if total_count > 0 else 0.0
            from data.models import AuthenticityRatio as ARModel
            ar_result = ARModel(
                brand_id=brand_config.get('brand_id', 'unknown'),
                source=','.join(sorted({s.src for s in scores_list})),
                run_id=scores_list[0].run_id if scores_list else 'unknown',
                total_items=total_count,
                authentic_items=authentic_count,
                suspect_items=suspect_count,
                inauthentic_items=inauthentic_count,
                authenticity_ratio_pct=core_pct
            )
        else:
            ar_calc = self._calculate_authenticity_ratio(
                scores_list,
                brand_config.get('brand_id', 'unknown'),
                scores_list[0].run_id if scores_list else 'unknown',
                include_appendix=True
            )
            if isinstance(ar_calc, tuple) and len(ar_calc) == 2:
                ar_result, per_item_breakdowns = ar_calc
            else:
                ar_result = ar_calc
                per_item_breakdowns = []

        # Reporting expects a dict-like structure (with .get). If we returned
        # an AuthenticityRatio dataclass, convert it to a dict with the
        # previous keys including extended_ar_pct.
        if hasattr(ar_result, '__dict__'):
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
        else:
            ar_dict = ar_result
        
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
