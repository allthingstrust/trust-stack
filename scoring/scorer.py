"""
5D Trust Dimensions scorer for Trust Stack Rating tool
Scores content on Provenance, Verification, Transparency, Coherence, Resonance
Integrates with TrustStackAttributeDetector for comprehensive ratings
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import json
from dataclasses import dataclass

from config.settings import SETTINGS
from data.models import NormalizedContent, ContentScores, DetectedAttribute
from scoring.attribute_detector import TrustStackAttributeDetector
from scoring.scoring_llm_client import LLMScoringClient
from scoring.verification_manager import VerificationManager
from scoring.linguistic_analyzer import LinguisticAnalyzer
from scoring.triage import TriageScorer
from scoring.signal_mapper import SignalMapper

logger = logging.getLogger(__name__)

@dataclass
class DimensionScores:
    """Individual dimension scores"""
    provenance: float
    verification: float
    transparency: float
    coherence: float
    resonance: float

class ContentScorer:
    """
    Scores content on 5D Trust Dimensions
    Combines LLM-based scoring with Trust Stack attribute detection
    """

    def __init__(self, use_attribute_detection: bool = True):
        """
        Initialize scorer
        
        Args:
            use_attribute_detection: If True, combine LLM scores with attribute detection
        """
        # Initialize LLM scoring client
        self.llm_client = LLMScoringClient()
        self.rubric_version = SETTINGS['rubric_version']
        self.use_attribute_detection = use_attribute_detection

        # Load trust signals config
        from scoring.rubric import load_rubric
        rubric = load_rubric()
        self.trust_signals_config = rubric.get('trust_signals', {})
        self._signals_cfg = self.trust_signals_config.get('signals', {})
        
        # Initialize Aggregator
        from scoring.aggregator import ScoringAggregator
        self.aggregator = ScoringAggregator(self.trust_signals_config)

        # Initialize attribute detector if enabled
        if self.use_attribute_detection:
            try:
                self.attribute_detector = TrustStackAttributeDetector()
                logger.info(f"Attribute detector initialized with {len(self.attribute_detector.attributes)} attributes")
            except Exception as e:
                logger.warning(f"Could not initialize attribute detector: {e}. Falling back to LLM-only scoring.")
                self.use_attribute_detection = False
                self.attribute_detector = None
        else:
            self.attribute_detector = None
            
        # Initialize new managers
        self.verification_manager = VerificationManager()
        self.linguistic_analyzer = LinguisticAnalyzer()
        self.triage_scorer = TriageScorer()
        self.signal_mapper = SignalMapper(self.trust_signals_config)

    def _signal_weight(self, signal_id: str, default: float) -> float:
        """
        Get signal weight from config with fallback support.
        
        trust_signals_config shape is expected to be:
          { dimensions: {...}, signals: { <id>: { weight: ... } } }
        but we keep a fallback for legacy flat configs.
        """
        try:
            if signal_id in self._signals_cfg:
                return float(self._signals_cfg[signal_id].get('weight', default))
            # Legacy fallback: flat config structure
            legacy = self.trust_signals_config.get(signal_id, {})
            if isinstance(legacy, dict):
                return float(legacy.get('weight', default))
        except Exception:
            pass
        return float(default)
    
    def score_content(self, content: NormalizedContent, brand_context: Dict[str, Any]) -> 'TrustScore':
        """
        Score content on all 5 dimensions
        
        Args:
            content: Content to score
            brand_context: Brand-specific context and keywords
        """
        logger.debug(f"Scoring content {content.content_id}")

        try:
            # Stage 1: Triage (if enabled)
            if SETTINGS.get('triage_enabled', False):
                should_score, reason, default_score = self.triage_scorer.should_score(content)
                if not should_score:
                    logger.info(f"Skipping LLM scoring for {content.content_id}: {reason}")
                    
                    # Store triage info in metadata
                    if content.meta is None:
                        content.meta = {}
                    content.meta['triage_status'] = 'skipped'
                    content.meta['triage_reason'] = reason
                    content.meta['score_debug'] = json.dumps({'triage': {'status': 'skipped', 'reason': reason}})
                    
                    # Return a neutral TrustScore
                    from scoring.types import TrustScore
                    return TrustScore(
                        overall=default_score * 100,
                        confidence=0.0,
                        coverage=0.0,
                        dimensions={},
                        metadata=content.meta
                    )

            # Get LLM scores for each dimension
            from scoring.types import SignalScore, TrustScore
            
            signals = []
            
            # 1. Provenance
            # LLM Score -> prov_source_clarity
            prov_val, prov_conf = self._score_provenance(content, brand_context)
            logger.info(f"DEBUG: Raw Provenance LLM score for {content.content_id}: {prov_val}, Conf: {prov_conf}")
            signals.append(SignalScore(
                id="prov_source_clarity",
                label="Source Attribution",
                dimension="Provenance",
                value=prov_val,
                weight=self._signal_weight('prov_source_clarity', 0.2),
                evidence=[],
                rationale="LLM analysis of source clarity",
                confidence=prov_conf
            ))
            
            # Heuristic: Content Freshness
            freshness_val = self._score_freshness(content)
            signals.append(SignalScore(
                id="prov_date_freshness",
                label="Content Freshness",
                dimension="Provenance",
                value=freshness_val,
                weight=self._signal_weight('prov_date_freshness', 0.2),
                evidence=[],
                rationale="Heuristic date check",
                confidence=1.0
            ))
            
            # 2. Verification
            # LLM/RAG Score -> ver_fact_accuracy
            ver_val, ver_conf = self._score_verification(content, brand_context)
            logger.info(f"DEBUG: Raw Verification LLM score for {content.content_id}: {ver_val}, Conf: {ver_conf}")
            signals.append(SignalScore(
                id="ver_fact_accuracy",
                label="Factual Accuracy",
                dimension="Verification",
                value=ver_val,
                weight=self._signal_weight('ver_fact_accuracy', 0.4),
                evidence=content._llm_issues.get('verification', []) if hasattr(content, '_llm_issues') else [],
                rationale="RAG-based verification",
                confidence=ver_conf
            ))
            
            # 3. Transparency
            # LLM Score -> trans_disclosures
            trans_val, trans_conf = self._score_transparency(content, brand_context)
            logger.info(f"DEBUG: Raw Transparency LLM score for {content.content_id}: {trans_val}, Conf: {trans_conf}")
            signals.append(SignalScore(
                id="trans_disclosures",
                label="Clear Disclosures",
                dimension="Transparency",
                value=trans_val,
                weight=self._signal_weight('trans_disclosures', 0.4),
                evidence=content._llm_issues.get('transparency', []) if hasattr(content, '_llm_issues') else [],
                rationale="LLM analysis of disclosures",
                confidence=trans_conf
            ))
            
            # 4. Coherence
            # LLM Score -> coh_voice_consistency
            coh_val, coh_conf = self._score_coherence(content, brand_context)
            logger.info(f"DEBUG: Raw Coherence LLM score for {content.content_id}: {coh_val}, Conf: {coh_conf}")
            signals.append(SignalScore(
                id="coh_voice_consistency",
                label="Voice Consistency",
                dimension="Coherence",
                value=coh_val,
                weight=self._signal_weight('coh_voice_consistency', 0.4),
                evidence=content._llm_issues.get('coherence', []) if hasattr(content, '_llm_issues') else [],
                rationale="LLM analysis of voice consistency",
                confidence=coh_conf
            ))
            
            # 5. Resonance
            # LLM Score -> res_cultural_fit
            res_val, res_conf = self._score_resonance(content, brand_context)
            logger.info(f"DEBUG: Raw Resonance LLM score for {content.content_id}: {res_val}, Conf: {res_conf}")
            signals.append(SignalScore(
                id="res_cultural_fit",
                label="Cultural/Audience Fit",
                dimension="Resonance",
                value=res_val,
                weight=self._signal_weight('res_cultural_fit', 0.4),
                evidence=[],
                rationale="LLM analysis of cultural fit",
                confidence=res_conf
            ))

            # Detect attributes if enabled and map to signals
            if self.attribute_detector:
                try:
                    detected_attrs = self.attribute_detector.detect_attributes(content)
                    mapped_signals = self.signal_mapper.map_attributes_to_signals(detected_attrs)
                    
                    # Override heuristic voice consistency if guidelines were used
                    if content.meta and content.meta.get('guidelines_used'):
                        original_count = len(mapped_signals)
                        mapped_signals = [s for s in mapped_signals if s.id != 'coh_voice_consistency']
                        if len(mapped_signals) < original_count:
                            logger.info("Overriding heuristic 'coh_voice_consistency' signal because brand guidelines are active")

                    if mapped_signals:
                        logger.info(f"Adding {len(mapped_signals)} mapped signals from attribute detector")
                        signals.extend(mapped_signals)
                except Exception as e:
                    logger.warning(f"Error in attribute detection/mapping: {e}")

            # Serialize score debug info to meta
            score_debug = getattr(content, '_score_debug', {})
            if score_debug:
                if content.meta is None:
                    content.meta = {}
                content.meta['score_debug'] = json.dumps(score_debug)

            # Calculate TrustScore using Aggregator
            # This is the new "Source of Truth" for the score
            logger.info(f"DEBUG: Sending {len(signals)} signals to aggregator for {content.content_id}: {[s.id for s in signals]}")
            dim_scores = []
            for dim_name in ["Provenance", "Verification", "Transparency", "Coherence", "Resonance"]:
                dim_score = self.aggregator.aggregate_dimension(dim_name, signals)
                dim_scores.append(dim_score)
                
            trust_score = self.aggregator.calculate_trust_score(dim_scores, metadata=content.meta)
            
            return trust_score

        except Exception as e:
            logger.error(f"Error scoring content {content.content_id}: {e}")
            # Return neutral scores on error
            from scoring.types import TrustScore
            return TrustScore(overall=50.0, confidence=0.0, coverage=0.0, dimensions={}, metadata={})

    def _score_freshness(self, content: NormalizedContent) -> float:
        """Score content freshness based on publication date"""
        try:
            if not getattr(content, 'published_at', None):
                return 0.5
            
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            
            # Parse date if string
            pub_date = content.published_at
            if isinstance(pub_date, str):
                from dateutil import parser
                try:
                    pub_date = parser.parse(pub_date)
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                except:
                    return 0.5
            
            if not isinstance(pub_date, datetime):
                return 0.5
                
            age_days = (now - pub_date).days
            
            if age_days < 30:
                return 1.0
            elif age_days < 90:
                return 0.9
            elif age_days < 180:
                return 0.8
            elif age_days < 365:
                return 0.6
            else:
                return 0.4
        except Exception:
            return 0.5
    
    def _score_provenance(self, content: NormalizedContent, brand_context: Dict[str, Any]) -> Tuple[float, float]:
        """Score Provenance dimension: origin, traceability, metadata"""
        
        prompt = f"""
        Score the PROVENANCE of this content on a scale of 0.0 to 1.0.
        
        Provenance evaluates: Is the content origin clear and trustworthy?
        
        Content:
        Title: {content.title}
        Body: {content.body[:2000]}
        Author: {content.author}
        Source: {content.src}
        Platform ID: {content.platform_id}
        
        Brand Context: {brand_context.get('keywords', [])}
        
        Scoring criteria (brand content perspective):
        - 0.8-1.0: Content from official brand domain with consistent branding and messaging
        - 0.6-0.8: Professional brand presence, clear organizational source
        - 0.4-0.6: Third-party site with clear attribution to brand
        - 0.2-0.4: User-generated or unclear sourcing  
        - 0.0-0.2: Suspicious origin, potential impersonation, or misleading source
        
        NOTE: Brand landing pages and product pages from official domains should score 0.7-0.9 even without explicit author bylines, as the brand itself is the verified source.
        
        Return only a number between 0.0 and 1.0:
        """
        
        score = self._get_llm_score(prompt)
        
        # Calculate confidence
        confidence = 1.0
        
        # Penalize confidence for very short content
        if not content.body or len(content.body) < 200:
            confidence *= 0.6
            logger.debug(f"Provenance confidence reduced due to short content ({len(content.body) if content.body else 0} chars)")
            
        # Penalize confidence for missing metadata
        if not content.author and not content.src:
            confidence *= 0.8
            logger.debug("Provenance confidence reduced due to missing author/source")
            
        return score, confidence
    
    def _score_verification(self, content: NormalizedContent, brand_context: Dict[str, Any]) -> Tuple[float, float]:
        """Score Verification dimension: factual accuracy vs trusted DBs (Fact-Checked)"""
        
        # Detect if content is from brand's own domain
        content_url = getattr(content, 'url', '').lower()
        brand_keywords = [kw.lower() for kw in brand_context.get('keywords', [])]
        is_brand_owned = any(keyword in content_url for keyword in brand_keywords if keyword)
        
        # Use VerificationManager for RAG-based verification
        logger.info(f"Starting RAG verification for {content.content_id}")
        verification_result = self.verification_manager.verify_content(content)
        
        rag_score = verification_result.get('score', 0.5)
        rag_issues = verification_result.get('issues', [])
        
        # Store issues
        if not hasattr(content, '_llm_issues'):
            content._llm_issues = {}
        content._llm_issues['verification'] = rag_issues
        
        # Initialize score debug storage
        if not hasattr(content, '_score_debug'):
            content._score_debug = {}
            
        base_score = rag_score
        
        # Determine content type for multiplier
        content_type = self._determine_content_type(content)
        
        # Apply content-type multiplier from rubric configuration
        multiplier = self._get_score_multiplier('verification', content_type)
        
        # Special handling for brand-owned content if not covered by multiplier
        # (Legacy logic preservation: if brand owned and no contradictions, ensure high score)
        if is_brand_owned:
            has_contradictions = any(i['type'] == 'unverified_claims' and i.get('severity') == 'high' for i in rag_issues)
            if not has_contradictions:
                # If multiplier didn't already boost it enough, ensure it's at least 0.9
                # But we prefer the multiplier approach. 
                # Let's trust the multiplier, but maybe log if brand-owned logic would have been different.
                pass

        adjusted_score = base_score
        if multiplier != 1.0:
            adjusted_score = min(1.0, base_score * multiplier)
            logger.info(f"Verification scoring for {content.content_id[:20]}...")
            logger.info(f"  Content type: {content_type}")
            logger.info(f"  Base RAG score: {base_score:.3f}")
            logger.info(f"  Multiplier applied: {multiplier:.2f}x")
            logger.info(f"  Adjusted score: {adjusted_score:.3f}")
        
        # Store debug info
        content._score_debug['verification'] = {
            'base_score': base_score,
            'multiplier': multiplier,
            'adjusted_score': adjusted_score,
            'content_type': content_type
        }
                
        # Calculate confidence based on RAG results
        confidence = 1.0
        rag_count = verification_result.get('rag_count', 0)
        
        if rag_count == 0:
            # If we couldn't find any documents to verify against, confidence is low
            confidence = 0.3
            logger.debug("Verification confidence low: No RAG documents found")
        elif rag_count < 3:
            # Few documents found
            confidence = 0.7
            
        return adjusted_score, confidence
    
    def _score_transparency(self, content: NormalizedContent, brand_context: Dict[str, Any]) -> Tuple[float, float]:
        """Score Transparency dimension: disclosures, clarity"""
        
        prompt = f"""
        Score the TRANSPARENCY of this content and identify specific issues.
        
        Transparency evaluates: Is the brand being honest and upfront with customers?
        
        Content:
        Title: {content.title}
        Body: {content.body[:2000]}
        Author: {content.author}
        
        Respond with JSON in this exact format:
        {{
            "score": 0.6,
            "issues": [
                {{
                    "type": "missing_privacy_policy",
                    "severity": "medium",
                    "evidence": "No privacy policy link found",
                    "suggestion": "Add privacy policy link to footer"
                }}
            ]
        }}
        
        Scoring criteria (brand content perspective):
        - 0.8-1.0: Clear honest messaging, no misleading claims, straightforward about product/service
        - 0.6-0.8: Professional brand content with standard disclosures expected on main website
        - 0.4-0.6: Some unclear pricing, terms, or promotional conditions
        - 0.2-0.4: Misleading claims or hidden terms
        - 0.0-0.2: Deceptive, manipulative, or fraudulent content
        
        NOTE: Standard brand marketing pages, product listings, and landing pages should score 0.7-0.9 if they honestly represent products/services, even without visible privacy links in the main content (these are typically in footers).
        
        Only flag issues that represent genuine transparency problems, not standard web conventions.
        
        Return valid JSON with score (0.0-1.0) and issues array.
        """
        
        result = self._get_llm_score_with_reasoning(prompt)
        
        # Store LLM-identified issues in content metadata for later merging
        if not hasattr(content, '_llm_issues'):
            content._llm_issues = {}
        content._llm_issues['transparency'] = result.get('issues', [])
        
        score = result.get('score', 0.5)
        
        # Calculate confidence
        confidence = 1.0
        
        # Transparency is hard to judge on very short content
        if not content.body or len(content.body) < 300:
            confidence *= 0.7
            
        return score, confidence
    
    def _score_coherence(self, content: NormalizedContent, brand_context: Dict[str, Any]) -> Tuple[float, float]:
        """Score Coherence dimension: consistency across channels with brand guidelines"""
        
        # Check if user wants to use guidelines (from session state/brand context)
        use_guidelines = brand_context.get('use_guidelines', True)  # Default True for backward compatibility
        
        brand_guidelines = None
        if use_guidelines:
            # Load brand guidelines if available
            brand_id = brand_context.get('brand_name', '').lower().strip().replace(' ', '_')
            brand_guidelines = self._load_brand_guidelines(brand_id)
            
            if brand_guidelines:
                logger.info(f"Using brand guidelines for {brand_id} in coherence scoring ({len(brand_guidelines)} chars)")
                if content.meta is None:
                    content.meta = {}
                content.meta['guidelines_used'] = True
            else:
                logger.info(f"No guidelines found for {brand_id}, using generic coherence standards")
                if content.meta is None:
                    content.meta = {}
                content.meta['guidelines_used'] = False
        else:
            logger.info("Brand guidelines disabled by user preference")
        
        # Detect content type to adjust scoring criteria
        content_type = self._determine_content_type(content)
        
        # Run deterministic linguistic analysis
        linguistic_data = self.linguistic_analyzer.analyze(content.body)
        passive_voice_issues = linguistic_data.get('passive_voice', [])
        readability = linguistic_data.get('readability', {})
        
        # Build context guidance for the feedback step
        deterministic_context = ""
        if passive_voice_issues:
            deterministic_context += f"\n\nDETECTED PASSIVE VOICE (Use these as evidence if relevant):\n" + "\n".join([f"- {s}" for s in passive_voice_issues])
        
        if readability.get('flesch_kincaid_grade', 0) > 12:
            deterministic_context += f"\n\nDETECTED READABILITY ISSUE: Grade Level {readability.get('flesch_kincaid_grade')} (Too complex). Suggest simplifying."

        if brand_guidelines:
            # Use brand-specific guidelines
            guidelines_preview = brand_guidelines[:1500]  # First 1500 chars
            context_guidance = f"""
            BRAND GUIDELINES FOR {brand_id.upper()}:
            
            {guidelines_preview}
            
            {'... [guidelines truncated]' if len(brand_guidelines) > 1500 else ''}
            
            CRITICAL: Compare the content against these SPECIFIC brand guidelines.
            Flag inconsistencies with the documented voice, tone, vocabulary, and style rules.
            Reference specific guideline sections in your suggestions.
            
            {deterministic_context}
            """
        elif content_type in ['landing_page', 'product_page', 'other']:
            context_guidance = """
            CONTENT TYPE: Marketing/Landing Page
            
            When providing feedback, focus on:
            - MAJOR issues: broken links, contradictory claims, unprofessional content
            - Do NOT flag normal marketing variation (headlines vs CTAs, legal vs marketing copy)
            - Only flag EXTREME voice inconsistencies (professional → unprofessional)
            
            IMPORTANT - Product Listings:
            If the content appears to be a product listing or grid (repeated product names, 
            prices, "Shop now" buttons, or similar structured e-commerce content), this is 
            intentional formatting, NOT incoherent text. The text extraction may have lost 
            the visual layout, making it appear jumbled. Do NOT flag product grids as 
            coherence issues unless there are actual contradictions or errors in the product 
            information itself.
            """ + deterministic_context
        elif content_type in ['blog', 'article', 'news']:
            context_guidance = """
            CONTENT TYPE: Editorial/Blog/News
            
            When providing feedback, apply strict editorial standards:
            - Brand voice consistency throughout
            - No broken links or contradictions
            - High professional quality expected
            """ + deterministic_context
        else:
            context_guidance = """
            CONTENT TYPE: General/Social
            
            Apply standard coherence criteria when providing feedback.
            """ + deterministic_context
        
        # Format body text with structure markers if available
        if hasattr(content, 'structured_body') and content.structured_body:
            # Format structured body with element markers
            formatted_body_parts = []
            for segment in content.structured_body[:50]:  # Limit to first 50 segments
                role = segment.get('semantic_role', 'text').upper()
                text = segment.get('text', '')
                formatted_body_parts.append(f"[{role}] {text}")
            
            formatted_body = "\n".join(formatted_body_parts)
            body_preview = formatted_body[:2000]
            structure_note = "\n\nNOTE: Content includes structure markers like [HEADLINE], [SUBHEADLINE], [BODY_TEXT] to indicate HTML element types."
        else:
            # Fall back to plain text
            body_preview = content.body[:2000]
            structure_note = ""
        
        # Step 1: Simple scoring prompt
        score_prompt = f"""
        Score the COHERENCE of this content on a scale of 0.0 to 1.0.
        
        Coherence evaluates: Does the content maintain consistent brand voice and messaging?
        
        Content:
        Title: {content.title}
        Body: {body_preview}
        Source: {content.src}{structure_note}
        
        Brand Context: {brand_context.get('keywords', [])}
        
        Scoring criteria (brand content perspective):
        - 0.8-1.0: Professional brand content with consistent voice and clear messaging
        - 0.6-0.8: Good brand consistency, minor stylistic variations acceptable
        - 0.4-0.6: Mixed messaging or inconsistent tone
        - 0.2-0.4: Significant voice/tone conflicts within content
        - 0.0-0.2: Incoherent, contradictory, or unprofessional
        
        NOTE: Normal variations between headlines, body text, and CTAs are expected in professional marketing. Product listings and structured content should score 0.7-0.9 if professionally presented. Only flag genuine inconsistencies, not standard formatting conventions.
        
        Return only a number between 0.0 and 1.0:
        """
        
        # Use two-step scoring with feedback
        result = self._get_llm_score_with_feedback(
            score_prompt=score_prompt,
            content=content,
            dimension="Coherence",
            context_guidance=context_guidance
        )
        
        # Filter issues based on our strict criteria
        issues = result.get('issues', [])
        filtered_issues = []
        for issue in issues:
            confidence = issue.get('confidence', 0.0)
            if confidence >= 0.7:
                # Special validation for inconsistent_voice
                if issue.get('type') == 'inconsistent_voice':
                    evidence = issue.get('evidence', '').lower()
                    
                    # Reject if evidence is footer/boilerplate text
                    footer_indicators = [
                        '©', 'copyright', 'all rights reserved',
                        'privacy policy', 'terms of use', 'contact us',
                        'grievance redressal', 'global privacy'
                    ]
                    
                    # Reject if evidence is just repeated text (same phrase appears twice)
                    import re
                    quotes = re.findall(r"'([^']+)'", evidence)
                    if len(quotes) >= 2:
                        if quotes[0].lower().strip() == quotes[1].lower().strip():
                            logger.debug(f"Filtered inconsistent_voice: repeated text detected")
                            continue
                
                filtered_issues.append(issue)
            else:
                logger.debug(f"Filtered low-confidence Coherence issue: {issue.get('type')} (confidence={confidence})")
        
        # Store LLM-identified issues in content metadata for later merging
        if not hasattr(content, '_llm_issues'):
            content._llm_issues = {}
        content._llm_issues['coherence'] = filtered_issues
        
        base_score = result.get('score', 0.5)
        
        # Initialize score debug storage
        if not hasattr(content, '_score_debug'):
            content._score_debug = {}
        
        # Apply content-type multiplier from rubric configuration
        multiplier = self._get_score_multiplier('coherence', content_type)
        
        adjusted_score = base_score
        if multiplier != 1.0:
            adjusted_score = min(1.0, base_score * multiplier)
            logger.info(f"Coherence scoring for {content.content_id[:20]}...")
            logger.info(f"  Content type: {content_type}")
            logger.info(f"  Base LLM score: {base_score:.3f} ({base_score*100:.1f}%)")
            logger.info(f"  Multiplier applied: {multiplier:.2f}x")
            logger.info(f"  Adjusted score: {adjusted_score:.3f} ({adjusted_score*100:.1f}%)")
        else:
            logger.debug(f"Coherence score for {content_type}: {base_score:.3f} (no multiplier)")
            
        # Store debug info
        content._score_debug['coherence'] = {
            'base_score': base_score,
            'multiplier': multiplier,
            'adjusted_score': adjusted_score,
            'content_type': content_type
        }
            
        # Calculate confidence
        confidence = 1.0
        
        if not brand_guidelines and use_guidelines:
            # If we wanted guidelines but couldn't find them, confidence is lower
            confidence = 0.6
            logger.debug("Coherence confidence reduced: Missing brand guidelines")
            
        return adjusted_score, confidence
    
    def _determine_content_type(self, content: NormalizedContent) -> str:
        """
        Determine content type based on URL patterns and metadata.
        Simplified version for scorer (full version is in attribute_detector)
        """
        url_lower = content.url.lower() if hasattr(content, 'url') and content.url else ""
        
        # Check for blog/article/news patterns
        if any(p in url_lower for p in ['/blog/', '/article/', '/news/', '/story/']):
            if '/blog/' in url_lower:
                return 'blog'
            elif '/news/' in url_lower or '/story/' in url_lower:
                return 'news'
            else:
                return 'article'
        
        # Check for legal/policy pages (terms, privacy, legal disclaimers)
        legal_patterns = [
            '/terms', '/privacy', '/legal/', '/policy', '/policies/',
            '/conditions', '/disclaimer', '/compliance', '/gdpr',
            'terms-of-use', 'terms-and-conditions', 'privacy-policy'
        ]
        if any(p in url_lower for p in legal_patterns):
            return 'legal_policy'
        
        # Check for landing page patterns
        if (url_lower.endswith('/') or '/product/' in url_lower or 
            '/solution/' in url_lower or '/about' in url_lower or '/home' in url_lower):
            return 'landing_page'
        
        # Check channel
        if hasattr(content, 'channel'):
            if content.channel in ['reddit', 'twitter', 'facebook', 'instagram']:
                return 'social_post'
        
        return 'other'

    
    def _get_score_multiplier(self, dimension: str, content_type: str) -> float:
        """
        Get score multiplier for a dimension and content type from rubric configuration
        
        Args:
            dimension: Dimension name (coherence, verification, etc.)
            content_type: Content type (landing_page, blog, etc.)
        
        Returns:
            Multiplier value (default 1.0 if not configured)
        """
        try:
            from scoring.rubric import load_rubric
            rubric = load_rubric()
            
            multipliers = rubric.get('score_multipliers', {})
            dimension_multipliers = multipliers.get(dimension, {})
            
            # Try to get content-type-specific multiplier
            multiplier = dimension_multipliers.get(content_type)
            
            # Fall back to _default if not found
            if multiplier is None:
                multiplier = dimension_multipliers.get('_default', 1.0)
            
            # Ensure it's a valid number
            return float(multiplier) if multiplier is not None else 1.0
            
        except Exception as e:
            logger.warning(f"Failed to load score multiplier for {dimension}/{content_type}: {e}")
            return 1.0
    
    def _load_brand_guidelines(self, brand_id: str) -> Optional[str]:
        """
        Load brand guidelines from storage if available.
        
        Args:
            brand_id: Brand identifier
        
        Returns:
            Guidelines text or None if not found
        """
        if not brand_id:
            return None
        
        try:
            from utils.document_processor import BrandGuidelinesProcessor
            processor = BrandGuidelinesProcessor()
            guidelines = processor.load_guidelines(brand_id)
            if guidelines:
                logger.info(f"Loaded brand guidelines for {brand_id}: {len(guidelines)} characters")
            return guidelines
        except Exception as e:
            logger.warning(f"Failed to load brand guidelines for {brand_id}: {e}")
            return None
    
    def _score_resonance(self, content: NormalizedContent, brand_context: Dict[str, Any]) -> Tuple[float, float]:
        """Score Resonance dimension: cultural fit, organic engagement"""
        
        # Use engagement metrics for resonance scoring
        engagement_score = self._calculate_engagement_resonance(content)
        
        prompt = f"""
        Score the RESONANCE of this content on a scale of 0.0 to 1.0.
        
        Resonance evaluates: Does this content connect authentically with the target audience?
        
        Content:
        Title: {content.title}
        Body: {content.body[:2000]}
        
        Engagement Metrics (if available):
        Rating: {content.rating}
        Upvotes: {content.upvotes}
        Helpful Count: {content.helpful_count}
        
        Brand Context: {brand_context.get('keywords', [])}
        
        Scoring criteria (brand content perspective):
        - 0.8-1.0: Content clearly designed for and relevant to target audience
        - 0.6-0.8: Professional content that serves audience needs
        - 0.4-0.6: Generic content with limited audience connection
        - 0.2-0.4: Content that seems off-target or misaligned with audience
        - 0.0-0.2: Content that feels inauthentic, manipulative, or disconnected
        
        NOTE: Brand landing pages, product descriptions, and marketing content should score 0.6-0.8 by default if they are professionally written and relevant to the brand's audience. Higher scores for content that shows genuine understanding of customer needs.
        
        Return only a number between 0.0 and 1.0:
        """
        
        llm_score = self._get_llm_score(prompt)
        
        # Combine LLM score with engagement metrics (70% LLM, 30% engagement)
        combined_score = (0.7 * llm_score) + (0.3 * engagement_score)
        
        combined_score = min(1.0, max(0.0, combined_score))
        
        # Calculate confidence
        confidence = 1.0
        
        # If we have no engagement metrics, we are relying 100% on LLM guess
        has_metrics = (content.rating is not None or 
                      content.upvotes is not None or 
                      content.helpful_count is not None)
                      
        if not has_metrics:
            confidence = 0.5
            logger.debug("Resonance confidence reduced: No engagement metrics available")
            
        return combined_score, confidence
    
    def _calculate_engagement_resonance(self, content: NormalizedContent) -> float:
        """Calculate engagement-based resonance score"""
        score = 0.5  # Default neutral score

        # Rating-based scoring (0-1 scale)
        if content.rating is not None:
            if content.src == "amazon":
                # Amazon ratings are 1-5, convert to 0-1
                score += (content.rating - 3) * 0.1
            elif content.src == "reddit":
                # Reddit upvote ratio is 0-1, use directly
                score += (content.rating - 0.5) * 0.2

        # Upvotes-based scoring
        if content.upvotes is not None:
            # Normalize upvotes (log scale to prevent outliers from dominating)
            import math
            normalized_upvotes = math.log10(max(1, content.upvotes)) / 3  # Log base 10, max ~3
            score += normalized_upvotes * 0.1

        # Helpful count scoring (Amazon reviews)
        if content.helpful_count is not None:
            normalized_helpful = min(content.helpful_count / 20, 1.0)  # Cap at 20 helpful votes
            score += normalized_helpful * 0.1

        return min(1.0, max(0.0, score))

    def _adjust_scores_with_attributes(self, llm_scores: DimensionScores,
                                      detected_attrs: List[DetectedAttribute]) -> DimensionScores:
        """
        Adjust LLM-based dimension scores using detected Trust Stack attributes

        Args:
            llm_scores: Base scores from LLM (0.0-1.0 scale)
            detected_attrs: List of detected attributes from TrustStackAttributeDetector

        Returns:
            Adjusted dimension scores (0.0-1.0 scale)
        """
        # Start with LLM scores (convert to 0-100 for adjustment calculation)
        adjusted = {
            'provenance': llm_scores.provenance * 100,
            'resonance': llm_scores.resonance * 100,
            'coherence': llm_scores.coherence * 100,
            'transparency': llm_scores.transparency * 100,
            'verification': llm_scores.verification * 100
        }

        # Group attributes by dimension
        attrs_by_dimension = {}
        for attr in detected_attrs:
            if attr.dimension not in attrs_by_dimension:
                attrs_by_dimension[attr.dimension] = []
            attrs_by_dimension[attr.dimension].append(attr)

        # Adjust each dimension based on its detected attributes
        for dimension, attrs in attrs_by_dimension.items():
            if dimension not in adjusted:
                continue

            # Calculate adjustment from attributes (1-10 scale → adjustment)
            # Strategy: Blend attribute signals with LLM baseline
            # Attributes with high confidence and extreme values have more impact
            total_adjustment = 0.0
            total_weight = 0.0

            for attr in attrs:
                # Skip negative adjustments for LLM-identified issues
                # The LLM score already accounts for these issues, so applying
                # negative adjustments would double-penalize
                is_llm_only = attr.evidence and attr.evidence.startswith("LLM:")
                
                # Map 1-10 scale to adjustment (-50 to +50)
                # 1 = -45, 5.5 = 0, 10 = +45
                attr_adjustment = (attr.value - 5.5) * 9

                # Skip negative adjustments for LLM-only attributes
                if is_llm_only and attr_adjustment < 0:
                    logger.debug(f"Skipping negative adjustment for LLM-only attribute {attr.label} in {dimension}")
                    continue

                # Weight by confidence
                weight = attr.confidence
                total_adjustment += attr_adjustment * weight
                total_weight += weight

            if total_weight > 0:
                # Average weighted adjustment
                avg_adjustment = total_adjustment / total_weight

                # Apply adjustment with dampening (70% LLM, 30% attributes)
                # This ensures LLM baseline is respected while attributes provide nuance
                adjusted[dimension] = (
                    0.7 * adjusted[dimension] +
                    0.3 * max(0, min(100, adjusted[dimension] + avg_adjustment))
                )

                # Clamp to valid range
                adjusted[dimension] = max(0, min(100, adjusted[dimension]))

        # Convert back to 0.0-1.0 scale
        return DimensionScores(
            provenance=adjusted['provenance'] / 100,
            resonance=adjusted['resonance'] / 100,
            coherence=adjusted['coherence'] / 100,
            transparency=adjusted['transparency'] / 100,
            verification=adjusted['verification'] / 100
        )
    
    def _get_llm_score(self, prompt: str) -> float:
        """Get score from LLM API (delegates to LLMScoringClient)"""
        return self.llm_client.get_score(prompt)
    
    def _get_llm_score_with_reasoning(self, prompt: str) -> Dict[str, Any]:
        """
        Get score AND reasoning from LLM API (delegates to LLMScoringClient)
        
        Returns:
            Dictionary with 'score' (float) and 'issues' (list of dicts)
        """
        return self.llm_client.get_score_with_reasoning(prompt)
    
    def _get_llm_score_with_feedback(self, score_prompt: str, content: NormalizedContent, 
                                     dimension: str, context_guidance: str = "") -> Dict[str, Any]:
        """
        Two-step LLM scoring: Get score first, then get feedback (delegates to LLMScoringClient)
        
        Args:
            score_prompt: Prompt to get the score (0.0-1.0)
            content: Content being scored
            dimension: Dimension name (for logging)
            context_guidance: Optional context about content type
        
        Returns:
            Dictionary with 'score' (float) and 'issues' (list of dicts)
        """
        return self.llm_client.get_score_with_feedback(score_prompt, content, dimension, context_guidance)
    
    def _merge_llm_and_detector_issues(self, content: NormalizedContent, 
                                      detected_attrs: List[DetectedAttribute]) -> List[DetectedAttribute]:
        """
        Merge LLM-identified issues with detector-found attributes
        
        Args:
            content: Content object (may have _llm_issues attribute)
            detected_attrs: List of attributes detected by attribute detector
        
        Returns:
            Merged list of DetectedAttribute objects with source tracking
        """
        from scoring.issue_mapper import map_llm_issue_to_attribute
        from scoring.link_verifier import verify_broken_links
        
        merged_attrs = []
        
        # Track which attributes we've seen from the detector
        detector_attr_ids = {attr.attribute_id for attr in detected_attrs}
        
        # Add all detector-found attributes (mark as detector-only or both)
        for attr in detected_attrs:
            merged_attrs.append(attr)
        
        # Process LLM issues if they exist
        if hasattr(content, '_llm_issues'):
            # DIAGNOSTIC: Log LLM issues by dimension
            for dim, issues in content._llm_issues.items():
                if issues:
                    logger.info(f"[MERGE DIAGNOSTIC] Processing {len(issues)} LLM issues for {dim} dimension")
            
            for dimension, llm_issues in content._llm_issues.items():
                for llm_issue in llm_issues:
                    issue_type = llm_issue.get('type', '')
                    
                    # Special handling for broken_links: verify with actual HTTP checks
                    if issue_type in ['broken_links', 'outdated_links']:
                        content_text = f"{content.title} {content.body}"
                        content_url = getattr(content, 'url', None)
                        actual_broken_links = verify_broken_links(content_text, content_url)
                        
                        if not actual_broken_links:
                            # LLM hallucinated broken links - reject this issue
                            logger.warning(f"LLM hallucinated broken_links for content {content.content_id} - no actual broken links found")
                            continue
                        else:
                            # Update evidence with actual broken link URLs
                            broken_urls = [link['url'] for link in actual_broken_links[:3]]  # Max 3 examples
                            llm_issue['evidence'] = f"Verified broken links: {', '.join(broken_urls)}"
                            logger.info(f"Verified {len(actual_broken_links)} broken links for content {content.content_id}")
                    
                    # Verify quotes exist in content (prevent hallucinations)
                    # This applies to ALL issue types that provide quotes
                    if not self._verify_issue_quotes(content, llm_issue):
                        logger.warning(f"Filtered LLM issue '{issue_type}' - quote not found in content")
                        continue
                    
                    # Map LLM issue type to attribute ID
                    attr_id = map_llm_issue_to_attribute(issue_type)
                    
                    # DIAGNOSTIC: Log mapping result
                    logger.info(f"[MERGE DIAGNOSTIC] Mapping '{issue_type}' ({dimension}) → attribute_id: {attr_id}")
                    
                    if not attr_id:
                        # Log unmapped issues for debugging
                        logger.warning(f"[MERGE DIAGNOSTIC] UNMAPPED LLM issue type '{issue_type}' in {dimension} dimension for content {content.content_id}")
                        continue
                    
                    # Check if detector also found this issue
                    if attr_id in detector_attr_ids:
                        # Both found it - increase confidence of existing attribute
                        for attr in merged_attrs:
                            if attr.attribute_id == attr_id:
                                # Boost confidence when both LLM and detector agree
                                attr.confidence = min(1.0, attr.confidence * 1.2)
                                # Add LLM evidence if not present
                                if llm_issue.get('evidence') and llm_issue['evidence'] not in attr.evidence:
                                    attr.evidence += f" | LLM Note: {llm_issue['evidence']}"
                                # Add suggestion
                                if llm_issue.get('suggestion'):
                                    attr.suggestion = llm_issue['suggestion']
                                break
                    else:
                        # LLM found an issue not detected by the attribute detector
                        # Map it to a new DetectedAttribute
                        # Import DetectedAttribute if not already imported, but it should be available in the scope
                        from .attribute_detector import DetectedAttribute
                        
                        new_attr = DetectedAttribute(
                            attribute_id=attr_id,
                            dimension=dimension,
                            value=5,  # Default low score for issues
                            confidence=llm_issue.get('confidence', 0.8),
                            evidence=llm_issue.get('evidence', 'Detected by AI analysis'),
                            label=llm_issue.get('type', attr_id).replace('_', ' ').title(),
                            suggestion=llm_issue.get('suggestion')
                        )
                        merged_attrs.append(new_attr)

        return merged_attrs

    def _verify_issue_quotes(self, content: NormalizedContent, issue: Dict[str, Any]) -> bool:
        """
        Verify that quotes in the issue actually exist in the content.
        Prevents hallucinations where LLM invents text.
        
        Args:
            content: Content object
            issue: Issue dictionary from LLM
            
        Returns:
            True if quotes are valid (or no quotes to check), False if hallucinated
        """
        # Get text to check
        evidence = issue.get('evidence', '')
        suggestion = issue.get('suggestion', '')
        
        # Combine title and body for search
        full_text = (content.title + " " + content.body).lower()
        
        # Extract quotes from evidence (e.g., "EXACT QUOTE: 'text'")
        import re
        evidence_quotes = re.findall(r"'([^']+)'", evidence)
        
        # Extract quotes from suggestion (e.g., "Change 'text' -> 'new'")
        # We only care about the "before" part
        suggestion_quotes = []
        if "Change '" in suggestion:
            parts = suggestion.split("Change '")
            for part in parts[1:]:
                quote_end = part.find("'")
                if quote_end != -1:
                    suggestion_quotes.append(part[:quote_end])
        
        # Check all extracted quotes
        all_quotes = evidence_quotes + suggestion_quotes
        
        if not all_quotes:
            return True  # No quotes to verify
            
        for quote in all_quotes:
            quote_clean = quote.lower().strip()
            if len(quote_clean) < 10:
                continue  # Skip very short quotes (too common)
                
            # Check if quote exists in content
            # Use simple substring search first
            if quote_clean in full_text:
                continue
                
            # Try fuzzy match (ignore whitespace differences)
            # Normalize whitespace in both
            quote_norm = " ".join(quote_clean.split())
            text_norm = " ".join(full_text.split())
            
            if quote_norm in text_norm:
                continue
                
            # Quote not found
            logger.debug(f"Quote verification failed: '{quote_clean}' not found in content")
            return False
            
        return True

    
    def batch_score_content(self, content_list: List[NormalizedContent],
                          brand_context: Dict[str, Any]) -> List[ContentScores]:
        """
        Score multiple content items in batch
        Combines LLM scoring with Trust Stack attribute detection

        Args:
            content_list: List of content to score
            brand_context: Brand-specific context

        Returns:
            List of ContentScores with dimension ratings
        """
        from scoring.content_filter import should_skip_content
        
        scores_list = []

        logger.info(f"Batch scoring {len(content_list)} content items (attribute detection: {self.use_attribute_detection})")

        for i, content in enumerate(content_list):
            if i % 10 == 0:
                logger.info(f"Scoring progress: {i}/{len(content_list)}")

            # Pre-filter: Skip error pages, login walls, and insufficient content
            skip_reason = should_skip_content(
                title=getattr(content, 'title', ''),
                body=getattr(content, 'body', ''),
                url=getattr(content, 'url', '')
            )
            
            if skip_reason:
                logger.warning(f"Skipping content '{content.title}' ({content.content_id}): {skip_reason}")
                # Don't add to scores_list - effectively filters it out
                continue

            # Step 1: Get TrustScore (was DimensionScores)
            trust_score = self.score_content(content, brand_context)
            
            # Helper to safely get dimension value (0-10) and convert to 0-1
            def get_dim_val(ts, name):
                if name.lower() in ts.dimensions:
                    return ts.dimensions[name.lower()].value / 10.0
                return 0.0

            # Step 2: Detect Trust Stack attributes (if enabled)
            detected_attrs = []
            if self.use_attribute_detection and self.attribute_detector:
                try:
                    detected_attrs = self.attribute_detector.detect_attributes(content)
                    logger.debug(f"Detected {len(detected_attrs)} attributes for {content.content_id}")

                    # Step 2.5: Merge LLM issues with detector attributes
                    detected_attrs = self._merge_llm_and_detector_issues(content, detected_attrs)
                    logger.debug(f"After merging: {len(detected_attrs)} total attributes")

                    # Note: We skip _adjust_scores_with_attributes here because the aggregator
                    # should handle signal integration. However, since we are in a transitional state
                    # where attributes are not yet fully "signals" in the aggregator, we might miss them.
                    # For now, we accept that the TrustScore is driven by the "Legacy" signals we created above.
                    # In the next iteration, we should convert detected_attrs into SignalScores and pass them
                    # to the aggregator in step 1.
                    
                except Exception as e:
                    logger.warning(f"Attribute detection failed for {content.content_id}: {e}")

            # Step 3: Create ContentScores object
            content_scores = ContentScores(
                content_id=content.content_id,
                brand=brand_context.get('brand_name', 'unknown'),
                src=content.src,
                event_ts=content.event_ts,
                score_provenance=get_dim_val(trust_score, 'provenance'),
                score_resonance=get_dim_val(trust_score, 'resonance'),
                score_coherence=get_dim_val(trust_score, 'coherence'),
                score_transparency=get_dim_val(trust_score, 'transparency'),
                score_verification=get_dim_val(trust_score, 'verification'),
                class_label="",  # Optional - for backward compatibility
                is_authentic=False,  # Optional - for backward compatibility
                rubric_version=self.rubric_version,
                run_id=content.run_id,
                # Enhanced Trust Stack fields
                modality=getattr(content, 'modality', 'text'),
                channel=getattr(content, 'channel', 'unknown'),
                platform_type=getattr(content, 'platform_type', 'unknown'),
                meta=json.dumps(
                    # Build a meta dict that includes scoring info and detected attributes
                    (lambda cm: {
                        "scoring_timestamp": content.event_ts,
                        "brand_context": brand_context,
                        "title": getattr(content, 'title', '') or None,
                        "description": getattr(content, 'body', '') or None,
                        "source_url": (cm.get('source_url') if isinstance(cm, dict) else None) or getattr(content, 'platform_id', None),
                        # Enhanced Trust Stack metadata
                        "modality": getattr(content, 'modality', 'text'),
                        "channel": getattr(content, 'channel', 'unknown'),
                        "platform_type": getattr(content, 'platform_type', 'unknown'),
                        "url": getattr(content, 'url', ''),
                        "language": getattr(content, 'language', 'en'),
                        # Include detected attributes for downstream analysis
                        "detected_attributes": [
                            {
                                "id": attr.attribute_id,
                                "dimension": attr.dimension,
                                "label": attr.label,
                                "value": attr.value,
                                "evidence": attr.evidence,
                                "confidence": attr.confidence,
                                "suggestion": attr.suggestion  # Include LLM suggestion
                            }
                            for attr in detected_attrs
                        ] if detected_attrs else [],
                        "attribute_count": len(detected_attrs),
                        # preserve any existing content.meta under orig_meta
                        "orig_meta": cm if isinstance(cm, dict) else None,
                        # propagate explicit footer links if present so downstream reporting can use them
                        **({
                            'terms': cm.get('terms'),
                            'privacy': cm.get('privacy')
                        } if isinstance(cm, dict) and (cm.get('terms') or cm.get('privacy')) else {})
                    })(content.meta if hasattr(content, 'meta') else {})
                )
            )

            scores_list.append(content_scores)

        logger.info(f"Completed batch scoring: {len(scores_list)} items scored")
        return scores_list
