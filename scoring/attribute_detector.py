"""
Trust Stack Attribute Detector
Detects 36 Trust Stack attributes from normalized content metadata
"""
import json
import re
from typing import List, Dict, Optional
from urllib.parse import urlparse
import logging

from data.models import NormalizedContent, DetectedAttribute

# Import WHOIS lookup for domain trust signals
try:
    from ingestion.whois_lookup import get_whois_lookup, WHOIS_AVAILABLE
except ImportError:
    WHOIS_AVAILABLE = False
    def get_whois_lookup():
        return None

logger = logging.getLogger(__name__)


class TrustStackAttributeDetector:
    """Detects Trust Stack attributes from content metadata"""

    def __init__(self, rubric_path: str = "config/rubric.json"):
        """
        Initialize detector with rubric configuration

        Args:
            rubric_path: Path to rubric.json containing attribute definitions
        """
        with open(rubric_path, "r", encoding="utf-8") as f:
            self.rubric = json.load(f)

        # Load only enabled attributes
        self.attributes = {
            attr["id"]: attr
            for attr in self.rubric["attributes"]
            if attr.get("enabled", False)
        }

        logger.info(f"Loaded {len(self.attributes)} enabled Trust Stack attributes")

    def detect_attributes(self, content: NormalizedContent, site_level_signals: Optional[Dict] = None) -> List[DetectedAttribute]:
        """
        Detect Trust Stack attributes in the content.
        
        Args:
            content: Normalized content object
            site_level_signals: Optional site-wide signals (for inheritance)
            
        Returns:
            List of detected attributes
        """
        detected = []
        site_level_signals = site_level_signals or {}
        
        # Dispatch to specific detection methods based on ID
        detection_methods = {
            "ai_vs_human_labeling_clarity": self._detect_ai_human_labeling,
            "author_brand_identity_verified": self._detect_author_verified,
            "c2pa_cai_manifest_present": self._detect_c2pa_manifest,
            "canonical_url_matches_declared_source": self._detect_canonical_url,
            "digital_watermark_fingerprint_detected": self._detect_watermark,
            "exif_metadata_integrity": self._detect_exif_integrity,
            "source_domain_trust_baseline": self._detect_domain_trust,
            "domain_age": self._detect_domain_age,
            "whois_privacy": self._detect_whois_privacy,
            "verified_platform_account": self._detect_platform_verification,
            
            # Resonance
            "community_alignment_index": self._detect_community_alignment,
            "creative_recency_vs_trend": self._detect_trend_alignment,
            "cultural_context_alignment": self._detect_cultural_context,
            "language_locale_match": self._detect_language_match,
            "personalization_relevance_embedding_similarity": self._detect_personalization,
            "readability_grade_level_fit": self._detect_readability,
            "tone_sentiment_appropriateness": self._detect_tone_sentiment,       
            
            # Coherence
            "brand_voice_consistency_score": self._detect_brand_voice,
            "broken_link_rate": self._detect_broken_links,
            "claim_consistency_across_pages": self._detect_claim_consistency,
            "email_asset_consistency_check": self._detect_email_consistency,
            "engagement_to_trust_correlation": self._detect_engagement_trust,
            "multimodal_consistency_score": self._detect_multimodal_consistency,
            "temporal_continuity_versions": self._detect_temporal_continuity,
            "trust_fluctuation_index": self._detect_trust_fluctuation,
            
            # Transparency
            "ai_explainability_disclosure": self._detect_ai_explainability,
            "ai_generated_assisted_disclosure_present": self._detect_ai_disclosure,
            "bot_disclosure_response_audit": self._detect_bot_disclosure,
            "caption_subtitle_availability_accuracy": self._detect_captions,
            "data_source_citations_for_claims": self._detect_citations,
            "privacy_policy_link_availability_clarity": self._detect_privacy_policy,
            "contact_info_availability": self._detect_contact_info,
            
            # Verification
            "ad_sponsored_label_consistency": self._detect_ad_labels,
            "agent_safety_guardrail_presence": self._detect_safety_guardrails,
            "claim_to_source_traceability": self._detect_claim_traceability,
            "engagement_authenticity_ratio": self._detect_engagement_authenticity,
            "influencer_partner_identity_verified": self._detect_influencer_verified,
            "review_authenticity_confidence": self._detect_review_authenticity,
            "seller_product_verification_rate": self._detect_seller_verification,
            "verified_purchaser_review_rate": self._detect_verified_purchaser,

            # 
            "schema_compliance": self._detect_schema_compliance,
            "metadata_completeness": self._detect_metadata_completeness,
            "llm_retrievability": self._detect_llm_retrievability,
            "canonical_linking": self._detect_canonical_linking,
            "indexing_visibility": self._detect_indexing_visibility,
            "ethical_training_signals": self._detect_ethical_training_signals,
        }

        for attr_id, detection_func in detection_methods.items():
            if attr_id in self.attributes:
                try:
                    # Pass site_level_signals to methods that support it
                    if attr_id in ["author_brand_identity_verified", "ai_generated_assisted_disclosure_present"]:
                        result = detection_func(content, site_level_signals=site_level_signals)
                    else:
                        result = detection_func(content)
                        
                    if result:
                        detected.append(result)
                except Exception as e:
                    logger.warning(f"Error detecting {attr_id}: {e}")
                    
        return detected

    # ===== PROVENANCE DETECTORS =====

    def _detect_ai_human_labeling(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """
        Detect AI vs human labeling clarity using a robust, multi-signal, context-aware approach.
        
        Signals checked (in order of reliability):
        1. Structured Data (Schema.org Author/Creator)
        2. Machine-Readable Metadata (C2PA, meta tags)
        3. Explicit Declaration Statements (Prioritizing Footer/Header for site-wide policies)
        
        Key Improvements:
        - Segments text into Main vs Footer/Header to avoid false positives from body copy
        - Prevents "AI-powered" product descriptions in body from triggering labeling flags
        """
        score = 0
        confidence = 0.0
        evidence_list = []
        meta = content.meta or {}
        
        # Use segmented text if available, fallback to full body
        main_text = (content.main_text or content.body or "").lower()
        footer_header_text = ((content.footer_text or "") + " " + (content.header_text or "")).lower()
        full_text = (main_text + " " + footer_header_text + " " + content.title.lower())
        
        # --- Signal 1: Structured Data (Schema.org) ---
        schema_json = meta.get('schema_org')
        if schema_json:
            found_human_schema = False
            try:
                data = json.loads(schema_json)
                flat_data = self._flatten_json_ld(data)
                
                for item in flat_data:
                    # Check Author type
                    author = item.get('author') or item.get('creator')
                    if author:
                        authors = author if isinstance(author, list) else [author]
                        for a in authors:
                            a_type = a.get('@type') if isinstance(a, dict) else None
                            if a_type == 'Person':
                                found_human_schema = True
                                evidence_list.append(f"Schema.org Author is Person ({a.get('name', 'named')})")
                            elif a_type == 'Organization':
                                found_human_schema = True 
                                evidence_list.append(f"Schema.org Author is Organization ({a.get('name', 'named')})")
            except Exception:
                pass
            
            if found_human_schema:
                score += 4
                confidence += 0.4
                
        # --- Signal 2: Machine-Readable Metadata ---
        if meta.get('has_c2pa_manifest') == 'true':
            score += 5
            confidence += 0.5
            evidence_list.append("C2PA/Content Credentials manifest present")
            
        if meta.get('author'):
            score += 2
            confidence += 0.2
            evidence_list.append(f"Meta Author tag found: {meta['author']}")
            
        if meta.get('ai-generated') == 'true':
            score += 5
            confidence += 0.5
            evidence_list.append("Meta tag explicitly declares AI generation")

        # --- Signal 3: Explicit Declaration Statements (Scoped Search) ---
        
        # A. Authorship Declarations (Expect in Footer/Header mostly)
        human_patterns = [
            r"human-led", 
            r"written by a human", 
            r"authored by\s+[A-Z]", 
            r"no ai was used",
            r"human-created content"
        ]
        
        # Check Footer/Header FIRST for declarations (Higher confidence)
        for pattern in human_patterns:
            if re.search(pattern, footer_header_text):
                score += 4
                confidence += 0.4
                evidence_list.append(f"Site-wide human authorship declaration found in footer/header ('{pattern}')")
                break
            elif re.search(pattern, main_text):
                score += 3
                confidence += 0.3
                evidence_list.append(f"Human authorship declaration found in body ('{pattern}')")
                break
                
        # B. AI Disclosure Declarations
        ai_patterns = [
            r"generated by ai",
            r"ai-generated content",
            r"created with the assistance of ai",
            r"ai supports the work",
            r"assisted by artificial intelligence"
        ]
        
        for pattern in ai_patterns:
            if re.search(pattern, footer_header_text):
                score += 4
                confidence += 0.4
                evidence_list.append(f"Site-wide AI disclosure found in footer/header ('{pattern}')")
                break
            elif re.search(pattern, main_text):
                score += 3
                confidence += 0.3
                evidence_list.append(f"AI disclosure found in body ('{pattern}')")
                break
        
        # --- Final Evaluation ---
        final_score = min(score, 10.0)
        
        if final_score >= 4.0:
            return DetectedAttribute(
                attribute_id="ai_vs_human_labeling_clarity",
                dimension="provenance",
                label="AI vs Human Labeling Clarity",
                value=final_score if final_score >= 5 else 5.0, 
                evidence="; ".join(evidence_list),
                confidence=min(confidence + 0.2, 1.0),
                status="present",
                reason="Robust labeling signals found"
            )
            
        # --- Fallback: Negative Detection (Context Restricted) ---
        # ONLY check main_text for AI generation artifacts to avoid false positives
        # from footer terms or nav items
        
        ai_triggers = [
            r"as an ai language model",
            r"i am a machine learning model",
            r"generated by chatgpt"
        ]
        
        for trigger in ai_triggers:
            if re.search(trigger, main_text):
                return DetectedAttribute(
                    attribute_id="ai_vs_human_labeling_clarity",
                    dimension="provenance",
                    label="AI vs Human Labeling Clarity",
                    value=1.0, 
                    evidence=f"Content contains AI generation artifacts ('{trigger}') but lacks disclosure",
                    confidence=0.9,
                    status="absent",
                    reason="Missing disclosure for apparent AI content"
                )
        
        return None

    def _detect_author_verified(self, content: NormalizedContent, site_level_signals: Optional[Dict] = None) -> Optional[DetectedAttribute]:
        """
        Detect if author/brand identity is verified.
        
        Checks for:
        1. Explicit author bylines
        2. "About" page links
        3. Schema.org Person/Organization
        4. Verified social profiles
        5. Global author info (inherited)
        """
        # ... (rest of method, need to inject inheritance check before returning weak signal)
        
        author = content.author
        meta = content.meta or {}
        site_level_signals = site_level_signals or {}
        
        # Check explicit author field
        if author and len(author) > 2 and author.lower() not in ["admin", "editor", "unknown", "staff"]:
            return DetectedAttribute(
                attribute_id="author_brand_identity_verified",
                dimension="provenance",
                label="Author/Brand Identity Verified",
                value=10.0,
                evidence=f"Explicit author byline found: {author}",
                confidence=0.9,
                status="present",
                reason="Explicit author byline"
            )
            
        # Check extracted schema/meta data (from page_fetcher)
        # We use a helper here because this logic is complex
        alt_attribution = self._check_alternative_attribution(content, meta)
        if alt_attribution['found']:
             return DetectedAttribute(
                attribute_id="author_brand_identity_verified",
                dimension="provenance",
                label="Author/Brand Identity Verified",
                value=alt_attribution['score'],
                evidence=alt_attribution['evidence'],
                confidence=alt_attribution['confidence'],
                status="present",
                reason=alt_attribution['evidence']
            )
            
        # Check global/site-level signals (inheritance)
        global_authors = site_level_signals.get("global_author_info", [])
        if global_authors:
            # We have site-level author info (e.g. from About page)
            evidence_str = global_authors[0] if isinstance(global_authors, list) else str(global_authors)
            return DetectedAttribute(
                attribute_id="author_brand_identity_verified",
                dimension="provenance",
                label="Author/Brand Identity Verified",
                value=8.0, # Good score for site-wide transparency
                evidence=f"Site-wide authorship verified: {evidence_str}",
                confidence=0.85,
                status="present",
                reason="Inherited site-wide authorship"
            )

        # Fallback: Check for 'About' link in body (weak signal)
        if "about" in content.body.lower()[:500]: # Check first 500 chars (menu/header typically)
             return DetectedAttribute(
                attribute_id="author_brand_identity_verified",
                dimension="provenance",
                label="Author/Brand Identity Verified",
                value=5.0,
                evidence="Possible 'About' link found in header/menu",
                confidence=0.5,
                status="partial",
                reason="Ambiguous 'About' link"
            )
            
        # Not found - Distinguish absent vs unknown based on content quality
        status = "absent"
        reason = "No clear author identity found in metadata or content"
        confidence = 0.8
        
        if len(content.body or "") < 200:
             status = "unknown"
             reason = "Content too short to reliably detect author"
             confidence = 0.5
            
        return DetectedAttribute(
            attribute_id="author_brand_identity_verified",
            dimension="provenance",
            label="Author/Brand Identity Verified",
            value=1.0,
            evidence=reason,
            confidence=confidence,
            status=status,
            reason=reason
        )


    def _determine_content_type(self, content: NormalizedContent) -> str:
        """
        Determine content type based on channel, URL patterns, and metadata.

        Returns:
            Content type: 'blog', 'article', 'news', 'landing_page', 'other'
        """
        url_lower = content.url.lower()

        # Check for blog/article/news patterns in URL
        blog_patterns = ['/blog/', '/article/', '/post/', '/news/', '/story/']
        if any(pattern in url_lower for pattern in blog_patterns):
            if '/blog/' in url_lower:
                return 'blog'
            elif '/news/' in url_lower or '/story/' in url_lower:
                return 'news'
            else:
                return 'article'

        # Check for landing page patterns
        landing_patterns = [
            url_lower.endswith('/'),  # Root or section homepage
            '/product/' in url_lower,
            '/solution/' in url_lower,
            '/service/' in url_lower,
            '/about' in url_lower,
            '/home' in url_lower
        ]
        if any(landing_patterns):
            return 'landing_page'

        # Check metadata for content type hints
        meta = content.meta or {}
        meta_type = meta.get('type', '').lower()
        if meta_type in ['article', 'blog', 'news', 'blogposting', 'newsarticle']:
            return meta_type

        # Check schema.org data
        schema_org = meta.get('schema_org')
        if schema_org:
            try:
                import json
                schema_data = json.loads(schema_org) if isinstance(schema_org, str) else schema_org
                
                # Use flattened list to finding type across all nodes
                flat_schema = self._flatten_json_ld(schema_data)
                
                for schema_item in flat_schema:
                    schema_type = schema_item.get('@type', '')
                    if isinstance(schema_type, str):
                        if 'Article' in schema_type or 'BlogPosting' in schema_type:
                            return 'blog' if 'Blog' in schema_type else 'article'
                        elif 'NewsArticle' in schema_type:
                            return 'news'
                        elif 'WebPage' in schema_type or 'Organization' in schema_type:
                            # Don't return immediately for WebPage/Organization as they are generic
                            # but can be used as a weak signal if nothing else matches
                            pass
            except Exception as e:
                logger.debug(f"Error checking schema type: {e}")

        # Default based on channel
        if content.channel in ['reddit', 'twitter', 'facebook', 'instagram']:
            return 'social_post'
        elif content.channel in ['youtube', 'tiktok']:
            return 'video'

        return 'other'

    def _flatten_json_ld(self, data: any) -> List[Dict]:
        """
        Recursively flatten JSON-LD data to handle @graph and nested structures.
        Returns a flat list of all objects found.
        """
        items = []
        
        if isinstance(data, list):
            for item in data:
                items.extend(self._flatten_json_ld(item))
        elif isinstance(data, dict):
            # Check for specific JSON-LD structures to unwrap
            if '@graph' in data:
                items.extend(self._flatten_json_ld(data['@graph']))
            elif 'json_ld' in data: # Handle our internal wrapper
                 items.extend(self._flatten_json_ld(data['json_ld']))
            else:
                # Expecting a single item object
                items.append(data)
                
                # Also check common nested properties that might contain entity objects
                # but careful not to duplicate if they are just references
                # For now, we trust that @graph usually brings everything to top level
                # But for deeply nested non-graph structures, we could recurse on specific keys
                # like 'mainEntity', 'contains', etc. if needed.
                pass
                
        return items

    def _check_alternative_attribution(self, content: NormalizedContent, meta: Dict) -> Dict[str, any]:
        """
        Check for alternative attribution methods suitable for corporate landing pages.

        Looks for:
        - Structured data (schema.org author/contributor/publisher)
        - Meta author tags
        - Footer attribution indicators
        - About/credits page links

        Returns:
            Dict with keys: found (bool), score (float), evidence (str), confidence (float)
        """
        attribution_methods = []

        # Check schema.org structured data
        schema_org = meta.get('schema_org')
        if schema_org:
            try:
                import json
                schema_data = json.loads(schema_org) if isinstance(schema_org, str) else schema_org

                # Robustly flatten any nested structure (like @graph)
                schema_list = self._flatten_json_ld(schema_data)

                for schema_item in schema_list:
                    if not isinstance(schema_item, dict):
                        continue

                    # Check for author
                    if 'author' in schema_item:
                        author = schema_item['author']
                        # author can be list, dict, or string
                        authors = author if isinstance(author, list) else [author]
                        
                        for auth in authors:
                            if isinstance(auth, dict):
                                author_name = auth.get('name', '')
                            else:
                                author_name = str(auth)
                                
                            if author_name and author_name.lower() not in ['unknown', 'anonymous']:
                                attribution_methods.append(f"Schema.org author: {author_name}")

                    # Check for contributor
                    if 'contributor' in schema_item:
                        contributor = schema_item['contributor']
                        contributors = contributor if isinstance(contributor, list) else [contributor]
                        
                        for contrib in contributors:
                            if isinstance(contrib, dict):
                                contrib_name = contrib.get('name', '')
                            else:
                                contrib_name = str(contrib)
                            if contrib_name:
                                attribution_methods.append(f"Schema.org contributor: {contrib_name}")

                    # Check for publisher
                    if 'publisher' in schema_item:
                        publisher = schema_item['publisher']
                        if isinstance(publisher, dict):
                             # Often publisher is an Organization with a name
                            pub_name = publisher.get('name', '')
                             # Sometimes publisher is just a reference ID, verify if we can find it?
                             # For now, just taking name if present
                        else:
                            pub_name = str(publisher)
                        if pub_name:
                            attribution_methods.append(f"Schema.org publisher: {pub_name}")
            except Exception as e:
                logger.debug(f"Error checking alternative attribution: {e}")
                pass

        # Check meta author tag
        meta_author = meta.get('author')
        if meta_author and meta_author.lower() not in ['unknown', 'anonymous', '']:
            attribution_methods.append(f"Meta author tag: {meta_author}")

        # Check for footer attribution indicators in meta
        footer_indicators = ['maintained_by', 'content_by', 'team', 'department']
        for indicator in footer_indicators:
            if indicator in meta and meta[indicator]:
                attribution_methods.append(f"Footer attribution: {meta[indicator]}")

        # Check for about/credits page links in meta
        about_links = ['about_url', 'credits_url', 'team_url']
        for link_key in about_links:
            if link_key in meta and meta[link_key]:
                attribution_methods.append(f"Credits page available: {meta[link_key]}")

        # Determine score based on attribution methods found
        if not attribution_methods:
            return {
                'found': False,
                'score': 3.0,
                'evidence': '',
                'confidence': 0.8,
                'status': 'absent'
            }

        # Score based on type and quantity of attribution
        if any('Schema.org author:' in method for method in attribution_methods):
            score = 8.0
            confidence = 0.95
        elif any('Meta author tag:' in method for method in attribution_methods):
            score = 7.0
            confidence = 0.9
        elif any('Schema.org publisher:' in method or 'Schema.org contributor:' in method for method in attribution_methods):
            score = 7.0
            confidence = 0.9
        elif any('Footer attribution:' in method for method in attribution_methods):
            score = 6.0
            confidence = 0.85
        elif any('Credits page' in method for method in attribution_methods):
            score = 6.0
            confidence = 0.8
        else:
            score = 5.0
            confidence = 0.75

        evidence = "Alternative attribution found: " + "; ".join(attribution_methods[:2])  # Limit evidence length

        return {
            'found': True,
            'score': score,
            'evidence': evidence,
            'confidence': confidence,
            'status': 'present'
        }

    def _detect_c2pa_manifest(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect C2PA/CAI manifest presence"""
        meta = content.meta or {}

        has_c2pa = any(key in meta for key in ["c2pa_manifest", "cai_manifest", "content_credentials"])

        if has_c2pa:
            is_valid = meta.get("c2pa_valid") != "false"
            value = 10.0 if is_valid else 5.0
            evidence = "C2PA manifest present and valid" if is_valid else "C2PA manifest present but invalid"
            return DetectedAttribute(
                attribute_id="c2pa_cai_manifest_present",
                dimension="provenance",
                label="C2PA/CAI Manifest Present",
                value=value,
                evidence=evidence,
                confidence=1.0
            )
        else:
            # CONDITIONAL PENALTY LOGIC
            # Only penalize if content is naturally visual OR contains significant visuals
            modality = getattr(content, 'modality', 'text')
            has_visuals = meta.get('has_significant_visuals') == 'true'

            if modality == 'text' and not has_visuals:
                 # Text-only content with no hero images -> No penalty (return None)
                 return None

            return DetectedAttribute(
                attribute_id="c2pa_cai_manifest_present",
                dimension="provenance",
                label="C2PA/CAI Manifest Present",
                value=1.0,
                evidence="No C2PA manifest found",
                confidence=1.0
            )

    def _detect_canonical_url(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect canonical URL match"""
        meta = content.meta or {}
        canonical_url = meta.get("canonical_url", "")
        # Fallback to content.url if meta['url'] is missing (common with some scrapers)
        source_url = meta.get("url") or content.url or ""

        if not canonical_url:
            return None  # Can't determine without canonical URL
            
        if not source_url:
            # If we still don't have a source URL, we can't compare.
            # Returning None avoids a false positive partial match.
            return None

        # Parse both URLs
        try:
            # Normalize URLs by removing trailing slashes for cleaner comparison
            canonical_norm = canonical_url.rstrip('/')
            source_norm = source_url.rstrip('/')
            
            if canonical_norm == source_norm:
                 return DetectedAttribute(
                    attribute_id="canonical_url_matches_declared_source",
                    dimension="provenance",
                    label="Canonical URL Matches Declared Source",
                    value=10.0,
                    evidence="Canonical URL exact match",
                    confidence=1.0,
                    status="present",
                    reason="Exact match"
                )

            canonical_domain = urlparse(canonical_url).netloc
            source_domain = urlparse(source_url).netloc

            if canonical_domain == source_domain:
                # Same domain but different path/params -> Partial match
                # Check if it is just http vs https
                if canonical_domain == source_domain and urlparse(canonical_url).path == urlparse(source_url).path:
                     return DetectedAttribute(
                        attribute_id="canonical_url_matches_declared_source",
                        dimension="provenance",
                        label="Canonical URL Matches Declared Source",
                        value=10.0,
                        evidence="Canonical URL matches (protocol difference only)",
                        confidence=1.0,
                        status="present",
                        reason="Protocol difference only"
                    )

                value = 5.0
                evidence = "Canonical URL points to same domain but different path"
            elif canonical_domain.replace('www.', '') == source_domain.replace('www.', ''):
                 # Handle www vs non-www
                 if urlparse(canonical_url).path == urlparse(source_url).path:
                      return DetectedAttribute(
                        attribute_id="canonical_url_matches_declared_source",
                        dimension="provenance",
                        label="Canonical URL Matches Declared Source",
                        value=10.0,
                        evidence="Canonical URL matches (subdomain/www difference only)",
                        confidence=1.0,
                        status="present",
                        reason="Subdomain difference only"
                    )
                 value = 5.0
                 evidence = "Canonical URL points to same base domain"
            else:
                value = 1.0
                evidence = f"Canonical URL mismatch: declared {canonical_domain} vs source {source_domain}"

            return DetectedAttribute(
                attribute_id="canonical_url_matches_declared_source",
                dimension="provenance",
                label="Canonical URL Matches Declared Source",
                value=value,
                evidence=evidence,
                confidence=1.0,
                status="present" if value > 1.0 else "absent",
                reason=evidence
            )
        except Exception:
            return None

    def _detect_watermark(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect digital watermark/fingerprint"""
        meta = content.meta or {}

        has_watermark = any(key in meta for key in ["watermark", "fingerprint", "digital_signature"])

        if has_watermark:
            return DetectedAttribute(
                attribute_id="digital_watermark_fingerprint_detected",
                dimension="provenance",
                label="Digital Watermark/Fingerprint Detected",
                value=10.0,
                evidence="Watermark detected in metadata",
                confidence=1.0
            )
        return None  # Only report if found

    def _detect_exif_integrity(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect EXIF/metadata integrity"""
        meta = content.meta or {}

        if "exif_data" in meta:
            exif_status = meta.get("exif_status", "intact")

            if exif_status == "intact":
                value = 10.0
                evidence = "EXIF metadata intact"
            elif exif_status == "stripped":
                value = 5.0
                evidence = "EXIF metadata stripped"
            else:  # spoofed
                value = 1.0
                evidence = "EXIF metadata spoofed"

            return DetectedAttribute(
                attribute_id="exif_metadata_integrity",
                dimension="provenance",
                label="EXIF/Metadata Integrity",
                value=value,
                evidence=evidence,
                confidence=1.0
            )
        return None

    def _detect_domain_trust(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect source domain trust baseline"""
        meta = content.meta or {}

        # Simple domain reputation based on source
        domain = meta.get("domain", "")
        source = content.src.lower()

        # Trusted platforms get higher scores
        trusted_sources = {
            "reddit": 7.0,
            "youtube": 7.0,
            "amazon": 8.0,
        }

        # Known high-trust domains
        trusted_domains = [
            ".gov", ".edu", ".org",
            "nytimes.com", "wsj.com", "bbc.com", "reuters.com"
        ]

        # Check for red flags
        red_flags = []
        if meta.get("ssl_valid") == "false":
            red_flags.append("No valid SSL certificate")
        
        # Check for privacy policy URL (propagated from page fetcher)
        # If the key exists but is empty, it means we looked but didn't find one.
        privacy_url = meta.get("privacy")
        if privacy_url is not None and not privacy_url:
            red_flags.append("No privacy policy found")
        elif meta.get("has_privacy_policy") == "false":
             # Fallback to legacy flag if present
            red_flags.append("No privacy policy found")
        if meta.get("domain_age_days") and int(meta.get("domain_age_days", 999)) < 30:
            red_flags.append("Very new domain (less than 30 days old)")
        if meta.get("malware_detected") == "true":
            red_flags.append("Malware detected")
        if meta.get("spam_score") and float(meta.get("spam_score", 0)) > 7.0:
            red_flags.append("High spam score")

        # If there are red flags, report low trust
        if red_flags:
            return DetectedAttribute(
                attribute_id="source_domain_trust_baseline",
                dimension="provenance",
                label="Source Domain Trust Baseline",
                value=2.0,
                evidence=f"Domain trust issues: {'; '.join(red_flags)}",
                confidence=0.9
            )

        # Report only trusted sources/domains positively (Overrides everything else)
        if source in trusted_sources:
            return DetectedAttribute(
                attribute_id="source_domain_trust_baseline",
                dimension="provenance",
                label="Source Domain Trust Baseline",
                value=trusted_sources[source],
                evidence=f"Trusted platform: {source}",
                confidence=0.8
            )
        elif any(domain.endswith(td) for td in trusted_domains):
            return DetectedAttribute(
                attribute_id="source_domain_trust_baseline",
                dimension="provenance",
                label="Source Domain Trust Baseline",
                value=9.0,
                evidence=f"High-trust domain: {domain}",
                confidence=0.8
            )

        # Graduated Trust Model for non-institutional domains
        # Base score for "Neutral" (no red flags)
        score = 5.0
        positive_signals = []

        # 1. SSL Check
        if meta.get("ssl_valid") == "true":
            score += 1.0
            positive_signals.append("Valid SSL")

        # 2. Privacy Policy Check (URL presence)
        if meta.get("privacy"):
            score += 1.0
            positive_signals.append("Privacy Policy found")

        # 3. Domain Age Bonus
        try:
            age_days = int(meta.get("domain_age_days", 0))
            if age_days > 365:
                score += 1.0
                positive_signals.append("Established domain (>1y)")
            elif age_days > 90:
                score += 0.5
                positive_signals.append("Established domain (>90d)")
        except (ValueError, TypeError):
            pass

        # Cap at 8.0 for hygiene-only trust
        # (Scores 9.0-10.0 are reserved for Institutional Authority)
        final_score = min(score, 8.0)
        
        evidence = "Domain hygiene analysis"
        if positive_signals:
            evidence += f": {', '.join(positive_signals)}"

        return DetectedAttribute(
            attribute_id="source_domain_trust_baseline",
            dimension="provenance",
            label="Source Domain Trust Baseline",
            value=final_score,
            evidence=evidence,
            confidence=0.7
        )

    def _detect_domain_age(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """
        Detect domain age using WHOIS lookup.
        
        Older domains are generally more trustworthy. This is a strong
        provenance signal that helps identify fly-by-night operations
        vs established organizations.
        """
        if not WHOIS_AVAILABLE:
            return None
        
        # Get URL from content
        url = content.url
        if not url:
            return None
        
        # Only do WHOIS lookup for web sources, not social platforms
        # Social platforms (reddit, youtube, etc.) have their own trust baselines
        if content.src.lower() in ['reddit', 'youtube', 'twitter', 'facebook', 'instagram', 'tiktok', 'amazon']:
            return None
        
        try:
            whois_lookup = get_whois_lookup()
            if not whois_lookup or not whois_lookup.available:
                return None
            
            result = whois_lookup.lookup(url)
            
            if 'error' in result:
                logger.debug(f"WHOIS lookup failed for {url}: {result['error']}")
                return None
            
            signals = result.get('trust_signals', {})
            age_score = signals.get('domain_age_score')
            
            if age_score is None:
                return None
            
            age_years = result.get('domain_age_years')
            assessment = signals.get('domain_age_assessment', '')
            
            # Store WHOIS data in content meta for other detectors
            if hasattr(content, 'meta') and content.meta is not None:
                content.meta['whois_domain_age_years'] = age_years
                content.meta['whois_domain_age_days'] = result.get('domain_age_days')
                content.meta['whois_registrar'] = result.get('registrar')
            
            return DetectedAttribute(
                attribute_id="domain_age",
                dimension="provenance",
                label="Domain Age",
                value=age_score,
                evidence=f"Domain age: {age_years} years. {assessment}",
                confidence=0.9
            )
            
        except Exception as e:
            logger.warning(f"Error detecting domain age for {url}: {e}")
            return None

    def _detect_whois_privacy(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """
        Detect WHOIS privacy/proxy registration.
        
        WHOIS privacy services hide the registrant identity. While legitimate
        for personal privacy, it can be a yellow flag for commercial sites
        where transparency is expected.
        """
        if not WHOIS_AVAILABLE:
            return None
        
        # Get URL from content
        url = content.url
        if not url:
            return None
        
        # Only do WHOIS lookup for web sources
        if content.src.lower() in ['reddit', 'youtube', 'twitter', 'facebook', 'instagram', 'tiktok', 'amazon']:
            return None
        
        try:
            whois_lookup = get_whois_lookup()
            if not whois_lookup or not whois_lookup.available:
                return None
            
            result = whois_lookup.lookup(url)
            
            if 'error' in result:
                return None
            
            signals = result.get('trust_signals', {})
            privacy_score = signals.get('privacy_score')
            
            if privacy_score is None:
                return None
            
            has_privacy = result.get('whois_privacy', False)
            assessment = signals.get('privacy_assessment', '')
            registrant_org = result.get('registrant_org')
            
            # Store in content meta
            if hasattr(content, 'meta') and content.meta is not None:
                content.meta['whois_privacy'] = has_privacy
                content.meta['whois_registrant_org'] = registrant_org
            
            # Only report if privacy is enabled (a potential flag)
            # or if we have a clear positive signal (visible registration)
            if has_privacy:
                return DetectedAttribute(
                    attribute_id="whois_privacy",
                    dimension="provenance",
                    label="WHOIS Privacy Status",
                    value=privacy_score,
                    evidence=f"WHOIS privacy enabled - registrant identity hidden. {assessment}",
                    confidence=0.85
                )
            elif registrant_org:
                return DetectedAttribute(
                    attribute_id="whois_privacy",
                    dimension="provenance",
                    label="WHOIS Privacy Status",
                    value=privacy_score,
                    evidence=f"Registrant publicly visible: {registrant_org}",
                    confidence=0.9
                )
            else:
                # Neutral case - no privacy but also no org info
                return None
            
        except Exception as e:
            logger.warning(f"Error detecting WHOIS privacy for {url}: {e}")
            return None

    def _detect_platform_verification(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """
        Detect platform verification badges for social media accounts.
        
        This creates a dedicated attribute that maps to 'Verification & Identity'
        key signal, separate from author verification. Detects blue checkmarks
        and verified status on Instagram, LinkedIn, X/Twitter, etc.
        """
        meta = content.meta or {}
        
        # Check for platform verification badges extracted by page_fetcher
        verification_badges = meta.get("verification_badges", {})
        
        if isinstance(verification_badges, dict) and verification_badges.get("verified"):
            platform = verification_badges.get("platform", "unknown")
            badge_type = verification_badges.get("badge_type", "verification_badge")
            evidence = verification_badges.get("evidence", "Platform verification detected")
            
            # Platform verification is high-confidence
            return DetectedAttribute(
                attribute_id="verified_platform_account",
                dimension="provenance",
                label="Verified Platform Account",
                value=10.0,
                evidence=f"Verified {platform} account: {badge_type}. {evidence}",
                confidence=1.0
            )
        
        # Check if this is a known social media platform without verification
        url_lower = content.url.lower() if content.url else ""
        social_platforms = ['instagram.com', 'linkedin.com', 'twitter.com', 'x.com', 'facebook.com', 'tiktok.com']
        
        is_social = any(platform in url_lower for platform in social_platforms)
        
        if is_social:
            # Social media without detected verification badge
            logger.debug("[VERIFICATION] No verification badge in meta for social URL: %s (badges: %s)", 
                        url_lower[:50], verification_badges)
            return DetectedAttribute(
                attribute_id="verified_platform_account",
                dimension="provenance",
                label="Verified Platform Account", 
                value=3.0,
                evidence="Social media profile without verified badge detected",
                confidence=0.7
            )
        
        # Not a social media platform - don't report (not applicable)
        return None

    # ===== RESONANCE DETECTORS =====

    def _detect_community_alignment(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect community alignment index (placeholder)"""
        # TODO: Implement hashtag/mention graph analysis
        return None

    def _detect_trend_alignment(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect creative recency vs trend (placeholder)"""
        # TODO: Implement trend API integration
        return None

    def _detect_cultural_context(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect cultural context alignment (placeholder)"""
        # TODO: Implement NER + cultural knowledge base
        return None

    def _detect_language_match(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect language/locale match"""
        meta = content.meta or {}
        detected_lang = meta.get("language", "en")

        # Assume English is target for now
        target_lang = "en"
        
        # Default to match if language is missing or matches target
        # This ensures we don't penalize content just because language detection failed or wasn't run
        if not detected_lang or detected_lang == target_lang:
            value = 10.0
            evidence = f"Language match: {detected_lang or 'en'}"
        else:
            value = 1.0
            evidence = f"Language mismatch: {detected_lang} (expected: {target_lang})"

        return DetectedAttribute(
            attribute_id="language_locale_match",
            dimension="resonance",
            label="Language/Locale Match",
            value=value,
            evidence=evidence,
            confidence=0.9
        )

    def _detect_personalization(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect personalization relevance (placeholder)"""
        # TODO: Implement embedding similarity
        return None

    def _detect_readability(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect readability grade level fit"""
        text = content.body

        # Simple readability heuristic (words per sentence)
        if not text or len(text) < 50:
            return None

        # Count total words
        words = len(text.split())
        
        # First, try traditional sentence splitting (periods, exclamation, question marks)
        # Use a more robust regex that handles multiple punctuation marks
        sentence_list = re.split(r'(?<=[\.\!\?])\s+', text)
        sentence_list = [s.strip() for s in sentence_list if len(s.strip()) > 0]

        # Secondary pass: Check for "run-on" sentences that are actually lists or unpunctuated blocks
        refined_sentence_list = []
        for sentence in sentence_list:
            # If a sentence is very long (> 50 words) and contains newlines, it might be a list or block
            if len(sentence.split()) > 50 and '\n' in sentence:
                # Split by newlines
                lines = [line.strip() for line in sentence.split('\n') if line.strip()]
                refined_sentence_list.extend(lines)
            else:
                refined_sentence_list.append(sentence)
        
        sentence_list = refined_sentence_list

        # Filter out "list-like" items from the sentence count
        # Heuristic: Real sentences usually have at least 5 words. 
        # Very short lines in a long block are likely list items (navigation, product names, etc.)
        # We keep them if they end in punctuation, otherwise we treat them as fragments to ignore
        # or count as short sentences depending on context.
        # Here, we'll filter out very short fragments (< 5 words) that don't end in punctuation
        # to avoid skewing the count with "Home", "About", "Contact", etc.
        
        final_sentences = []
        for s in sentence_list:
            word_count = len(s.split())
            if word_count < 5 and not s[-1] in ['.', '!', '?']:
                continue # Skip short fragments
            final_sentences.append(s)
            
        sentence_list = final_sentences

        # If we have very few sentences for the amount of text, try splitting on newlines too
        # This handles product pages, navigation, lists, etc.
        if len(sentence_list) < 3 and words > 100:
            # Try splitting on newlines as well
            line_list = [line.strip() for line in text.split('\n') if len(line.strip()) > 10]
            
            # Check if this looks like list/navigation content (many short lines)
            if len(line_list) > 3:  # Lowered from 5 to catch more list cases
                avg_line_length = sum(len(line.split()) for line in line_list) / len(line_list)
                
                # If average line is very short (< 10 words), this is likely navigation/lists, not prose
                if avg_line_length < 10:
                    return None  # Skip readability analysis for non-prose content
            
            # Use lines as sentences if we have more lines than traditional sentences
            if len(line_list) > len(sentence_list):
                sentence_list = line_list
        
        # Additional check: if we have very few sentences but the text has many newlines,
        # it's likely list/navigation content even if it doesn't meet the > 100 words threshold
        if len(sentence_list) <= 1 and words > 20:
            newline_count = text.count('\n')
            # If there are many newlines relative to the text (> 1 newline per 10 words), skip
            if newline_count > words / 10:
                return None

        if len(sentence_list) == 0:
            return None

        # Calculate words per sentence for each sentence
        sentence_word_counts = [len(s.split()) for s in sentence_list]
        
        # Use median instead of mean to be robust against outliers
        sentence_word_counts.sort()
        n = len(sentence_word_counts)
        if n == 0:
            return None
            
        if n % 2 == 0:
            median_words = (sentence_word_counts[n//2 - 1] + sentence_word_counts[n//2]) / 2
        else:
            median_words = sentence_word_counts[n//2]
        
        # Also calculate mean for comparison
        mean_words = sum(sentence_word_counts) / len(sentence_word_counts)
        
        # Use median as the primary metric (more robust)
        words_per_sentence = median_words

        # Target: 15-20 words per sentence (grade 8-10)
        if 12 <= words_per_sentence <= 22:
            value = 10.0
            evidence = f"Readable: {words_per_sentence:.1f} words/sentence"
        elif 8 <= words_per_sentence <= 30:
            value = 7.0
            evidence = f"Acceptable: {words_per_sentence:.1f} words/sentence"
        else:
            value = 4.0
            evidence = f"Difficult: {words_per_sentence:.1f} words/sentence"

        return DetectedAttribute(
            attribute_id="readability_grade_level_fit",
            dimension="resonance",
            label="Readability Grade Level Fit",
            value=value,
            evidence=evidence,
            confidence=0.7
        )

    def _detect_tone_sentiment(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect tone & sentiment appropriateness (placeholder)"""
        # TODO: Integrate sentiment analysis model
        return None

    # ===== COHERENCE DETECTORS =====

    def _detect_brand_voice(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect brand voice consistency"""
        # Simple heuristic: Check for professional tone markers vs casual/slang
        text = (content.body + " " + content.title).lower()
        
        # Slang/casual markers that might violate professional brand voice
        casual_markers = ["gonna", "wanna", "lol", "lmao", "omg", "thx", "u", "ur", "cuz"]
        found_markers = [m for m in casual_markers if f" {m} " in text]
        
        if found_markers:
            return DetectedAttribute(
                attribute_id="brand_voice_consistency_score",
                dimension="coherence",
                label="Brand Voice Consistency Score",
                value=4.0,
                evidence=f"Inconsistent brand voice detected (casual markers: {', '.join(found_markers[:3])})",
                confidence=0.7
            )
            
        # Positive signal: No slang found implies professional voice
        return DetectedAttribute(
            attribute_id="brand_voice_consistency_score",
            dimension="coherence",
            label="Brand Voice Consistency Score",
            value=10.0,
            evidence="Professional brand voice maintained (no casual markers detected)",
            confidence=0.6
        )

    def _detect_broken_links(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect broken link rate"""
        text = content.body + " " + content.title

        # Find URLs in text
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

        if not urls:
            return None  # No links to check

        # Check metadata for broken link info
        meta = content.meta or {}
        broken_count = int(meta.get("broken_links", 0))
        total_count = len(urls)

        if broken_count == 0:
            value = 10.0
            evidence = f"No broken links ({total_count} total)"
        else:
            broken_rate = broken_count / total_count
            if broken_rate < 0.01:
                value = 10.0
            elif broken_rate < 0.05:
                value = 7.0
            elif broken_rate < 0.10:
                value = 4.0
            else:
                value = 1.0
            evidence = f"{broken_count}/{total_count} broken links ({broken_rate:.1%})"

        return DetectedAttribute(
            attribute_id="broken_link_rate",
            dimension="coherence",
            label="Broken Link Rate",
            value=value,
            evidence=evidence,
            confidence=0.8
        )

    def _detect_claim_consistency(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect claim consistency across pages"""
        # Heuristic: Check for contradictory terms in close proximity
        text = content.body.lower()
        
        contradictions = [
            ("always", "never"),
            ("100%", "some"),
            ("free", "paid"),
            ("guaranteed", "estimated")
        ]
        
        for term1, term2 in contradictions:
            if term1 in text and term2 in text:
                # Check distance
                idx1 = text.find(term1)
                idx2 = text.find(term2)
                if abs(idx1 - idx2) < 100:  # Close proximity
                    return DetectedAttribute(
                        attribute_id="claim_consistency_across_pages",
                        dimension="coherence",
                        label="Claim Consistency Across Pages",
                        value=3.0,
                        evidence=f"Potential contradiction detected: '{term1}' vs '{term2}'",
                        confidence=0.6
                    )
        return None  # No contradictions detected

    def _detect_email_consistency(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect email-asset consistency"""
        # Only relevant for email content
        if content.channel != 'email':
            return None
            
        # Check if email content matches landing page (simulated via metadata)
        meta = content.meta or {}
        if meta.get('landing_page_match') == 'false':
            return DetectedAttribute(
                attribute_id="email_asset_consistency_check",
                dimension="coherence",
                label="Email-Asset Consistency Check",
                value=2.0,
                evidence="Email content contradicts landing page offer",
                confidence=0.9
            )
        return None

    def _detect_engagement_trust(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect engagement-to-trust correlation"""
        # Skip detection for content types where engagement metrics aren't applicable
        if not self._should_have_engagement_metrics(content):
            return None

        # Use engagement metrics as proxy
        upvotes = content.upvotes or 0
        rating = content.rating or 0.0

        # Only flag if there's actually concerning engagement patterns
        # Don't flag pages with zero engagement - that's normal for many pages
        if upvotes == 0 and rating == 0.0:
            return None  # No engagement data available, skip

        # High engagement + high rating = high trust
        if upvotes > 50 and rating > 4.0:
            value = 10.0
            evidence = f"High engagement ({upvotes} upvotes, {rating:.1f} rating)"
        elif upvotes > 10 and rating > 3.0:
            value = 7.0
            evidence = f"Moderate engagement ({upvotes} upvotes, {rating:.1f} rating)"
        elif upvotes > 5 or rating > 2.0:
            value = 6.0
            evidence = f"Moderate engagement ({upvotes} upvotes, {rating:.1f} rating)"
        else:
            # Only flag as concerning if there's negative engagement (low rating with votes)
            if rating < 2.0 and (upvotes > 5 or rating > 0):
                value = 3.0
                evidence = f"Low trust with engagement present ({upvotes} upvotes, {rating:.1f} rating)"
            else:
                return None  # Skip neutral cases

        return DetectedAttribute(
            attribute_id="engagement_to_trust_correlation",
            dimension="coherence",
            label="Engagement-to-Trust Correlation",
            value=value,
            evidence=evidence,
            confidence=0.6
        )

    def _should_have_engagement_metrics(self, content: NormalizedContent) -> bool:
        """
        Determine if engagement metrics (upvotes, ratings) are expected for this content type.

        Returns False for:
        - Job boards and career sites
        - Corporate websites and landing pages
        - Documentation and knowledge bases
        - News sites (unless they have commenting systems)
        - Government and educational sites
        - Static informational pages

        Returns True for:
        - Social media platforms (reddit, youtube, instagram, tiktok)
        - Marketplaces with reviews (amazon, etsy, yelp)
        - Community forums and discussion boards
        - Review platforms
        """
        # Social platforms and marketplaces always have engagement features
        engagement_channels = {'reddit', 'youtube', 'amazon', 'instagram', 'tiktok',
                              'facebook', 'twitter', 'yelp', 'tripadvisor', 'etsy'}
        if content.channel.lower() in engagement_channels:
            return True

        # Platform types that typically have engagement
        if content.platform_type.lower() in {'social', 'marketplace'}:
            return True

        # Check URL patterns for non-engagement sites
        url_lower = content.url.lower()

        # Job boards and career sites
        job_patterns = ['careers.', 'jobs.', '/careers/', '/jobs/', 'apply.',
                       'greenhouse.io', 'lever.co', 'workday.com', 'taleo.net',
                       'jobvite.com', 'indeed.com', 'linkedin.com/jobs']
        if any(pattern in url_lower for pattern in job_patterns):
            return False

        # Corporate landing pages and marketing sites
        if content.platform_type.lower() == 'owned' and content.source_type.lower() == 'brand_owned':
            # Brand-owned content typically doesn't have engagement features
            # unless it's explicitly a community or review section
            if not any(keyword in url_lower for keyword in ['/reviews/', '/community/', '/forum/', '/comments/']):
                return False

        # Documentation and knowledge bases
        doc_patterns = ['docs.', '/docs/', '/documentation/', 'developer.', '/api/',
                       'help.', '/help/', 'support.', '/kb/', 'wiki.']
        if any(pattern in url_lower for pattern in doc_patterns):
            return False

        # Government and educational sites (typically informational)
        if any(domain in url_lower for domain in ['.gov', '.edu', '.mil']):
            return False

        # Default to True if we can't determine - let the metric run
        # This is conservative: we'd rather have false positives than miss real engagement issues
        return True

    def _detect_multimodal_consistency(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect multimodal consistency (placeholder)"""
        # TODO: Implement caption vs transcript comparison
        return None

    def _detect_temporal_continuity(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect temporal continuity (placeholder)"""
        # TODO: Check version history metadata
        return None

    def _detect_trust_fluctuation(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect trust fluctuation index (placeholder)"""
        # TODO: Implement time-series sentiment analysis
        return None

    # ===== TRANSPARENCY DETECTORS =====

    def _detect_ai_explainability(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect AI explainability disclosure"""
        text = (content.body + " " + content.title).lower()
        meta = content.meta or {}

        # First, check if the page actually uses AI features
        ai_feature_indicators = [
            "artificial intelligence", "machine learning", "ai-powered", "ai powered",
            "personalized", "personalisation", "recommendation", "recommendations",
            "smart", "intelligent", "automated", "chatbot", "virtual assistant",
            "predicted", "prediction", "algorithm", "algorithmic"
        ]

        # Check if page uses AI
        uses_ai = (
            any(indicator in text for indicator in ai_feature_indicators) or
            meta.get("uses_ai") == "true" or
            meta.get("has_recommendations") == "true"
        )

        # Only check for explainability if AI is being used
        if not uses_ai:
            return None  # Page doesn't use AI, no disclosure needed

        # If AI is used, check for explainability
        explainability_phrases = [
            "why you're seeing this",
            "how this works",
            "how we recommend",
            "how we personalize",
            "learn more about our recommendations",
            "about our algorithm",
            "transparency",
            "explain"
        ]

        has_explainability = any(phrase in text for phrase in explainability_phrases)

        if has_explainability:
            return DetectedAttribute(
                attribute_id="ai_explainability_disclosure",
                dimension="transparency",
                label="AI Explainability Disclosure",
                value=10.0,
                evidence="Explainability disclosure found for AI features",
                confidence=0.9
            )
        else:
            return DetectedAttribute(
                attribute_id="ai_explainability_disclosure",
                dimension="transparency",
                label="AI Explainability Disclosure",
                value=2.0,
                evidence="AI features detected but no explainability disclosure",
                confidence=0.8
            )

    def _detect_ai_disclosure(self, content: NormalizedContent, site_level_signals: Optional[Dict] = None) -> Optional[DetectedAttribute]:
        """Detect AI-generated/assisted disclosure"""
        text = (content.body + " " + content.title).lower()
        meta = content.meta or {}
        site_level_signals = site_level_signals or {}

        ai_disclosure_phrases = [
            "ai-generated", "ai generated",
            "ai-assisted", "ai assisted",
            "generated by ai",
            "created with ai"
        ]

        has_disclosure = (
            any(phrase in text for phrase in ai_disclosure_phrases) or
            meta.get("ai_generated") == "true"
        )

        if has_disclosure:
            return DetectedAttribute(
                attribute_id="ai_generated_assisted_disclosure_present",
                dimension="transparency",
                label="AI-Generated/Assisted Disclosure Present",
                value=10.0,
                evidence="AI disclosure present",
                confidence=1.0
            )
        
        # Check global inheritance
        if site_level_signals.get("has_global_ai_disclosure"):
            return DetectedAttribute(
                attribute_id="ai_generated_assisted_disclosure_present",
                dimension="transparency",
                label="AI-Generated/Assisted Disclosure Present",
                value=8.0, # Slightly lower than explicit on-page, but still high
                evidence="Inherited from site-wide AI disclosure (e.g. footer/policy)",
                confidence=0.9
            )

        # Default negative
        return DetectedAttribute(
            attribute_id="ai_generated_assisted_disclosure_present",
            dimension="transparency",
            label="AI-Generated/Assisted Disclosure Present",
            value=1.0,
            evidence="No AI disclosure",
            confidence=1.0
        )

    def _detect_bot_disclosure(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect bot disclosure (placeholder)"""
        # TODO: Check for bot self-identification
        return None

    def _detect_captions(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect caption/subtitle availability"""
        meta = content.meta or {}

        # Only applicable to video content
        if content.src != "youtube":
            return None

        has_captions = meta.get("has_captions") == "true"

        if has_captions:
            return DetectedAttribute(
                attribute_id="caption_subtitle_availability_accuracy",
                dimension="transparency",
                label="Caption/Subtitle Availability & Accuracy",
                value=10.0,
                evidence="Captions available",
                confidence=1.0
            )
        else:
            return DetectedAttribute(
                attribute_id="caption_subtitle_availability_accuracy",
                dimension="transparency",
                label="Caption/Subtitle Availability & Accuracy",
                value=1.0,
                evidence="No captions found",
                confidence=1.0
            )

    def _detect_citations(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect data source citations"""
        text = content.body

        # First, check if the page actually has data-driven claims that need citations
        data_claim_indicators = [
            r'\d+%',  # Percentages: 50%
            r'\$[\d,]+',  # Dollar amounts: $1,000
            r'\d+\s*million',  # Large numbers: 5 million
            r'\d+\s*billion',
            r'\d+\s*thousand',
            r'study\s+(?:found|shows|revealed)',
            r'research\s+(?:found|shows|revealed)',
            r'survey\s+(?:found|shows|revealed)',
            r'statistics?\s+(?:show|indicate)',
            r'data\s+(?:show|indicate)',
            r'according\s+to\s+(?:a\s+)?(?:study|research|survey|report)',
            r'findings?\s+(?:from|of)',
            r'results?\s+(?:from|of)',
        ]

        # Check if content has data-driven claims
        has_data_claims = any(re.search(pattern, text, re.IGNORECASE) for pattern in data_claim_indicators)

        # Skip pages without data claims
        if not has_data_claims:
            return None

        # Content has data claims, now check for citations
        citation_patterns = [
            r'\[\d+\]',  # [1], [2], etc.
            r'\(\w+,? \d{4}\)',  # (Author, 2024)
            r'according to\s+[\w\s]+(?:University|Institute|Organization|Agency|Department)',
            r'source:\s*[\w\s]+',
            r'cited by',
            r'study by',
            r'research by',
            r'report by'
        ]

        has_citations = any(re.search(pattern, text, re.IGNORECASE) for pattern in citation_patterns)

        if has_citations:
            return DetectedAttribute(
                attribute_id="data_source_citations_for_claims",
                dimension="transparency",
                label="Data Source Citations for Claims",
                value=10.0,
                evidence="Citations found for data claims",
                confidence=0.85
            )
        else:
            return DetectedAttribute(
                attribute_id="data_source_citations_for_claims",
                dimension="transparency",
                label="Data Source Citations for Claims",
                value=2.0,
                evidence="Data claims detected but no citations provided",
                confidence=0.8
            )

    def _detect_privacy_policy(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect privacy policy link"""
        text = (content.body + " " + content.title).lower()
        meta = content.meta or {}

        # Check for privacy policy in multiple ways
    
        # 0. Check if the page ITSELF is a privacy policy
        # If the URL contains "privacy" or "legal", it's likely the policy itself
        if "privacy" in content.url.lower() or "legal" in content.url.lower() or "terms" in content.url.lower():
             return DetectedAttribute(
                attribute_id="privacy_policy_link_availability_clarity",
                dimension="transparency",
                label="Privacy Policy Link Availability & Clarity",
                value=10.0,
                evidence="Page appears to be a privacy policy or legal page",
                confidence=0.95
            )

        # 1. Check metadata for privacy policy URL
        has_privacy_url = any(key in meta for key in [
            "privacy_policy_url", "privacy_url", "privacy_policy_link"
        ])

        # 2. Check for common privacy policy link text variations
        privacy_link_patterns = [
            "privacy policy",
            "privacy notice",
            "privacy statement",
            "data protection",
            "privacy & terms",
            "privacy and terms",
            "cookie policy",
            "privacy center",
            "your privacy",
            "legal",
            "terms of use",
            "terms of service",
            "cookie preferences",
            "cookie settings",
            "personal information",
            "data privacy",
            "legal notice"
        ]

        has_privacy_text = any(pattern in text for pattern in privacy_link_patterns)

        # 3. Check for /privacy or similar URL patterns in the text
        privacy_url_patterns = [
            "/privacy",
            "/privacy-policy",
            "/legal/privacy",
            "/privacy-notice",
            "/legal",
            "/terms"
        ]

        has_privacy_url_pattern = any(pattern in text for pattern in privacy_url_patterns)

        # Determine if privacy policy is present
        if has_privacy_url or has_privacy_text or has_privacy_url_pattern:
            return DetectedAttribute(
                attribute_id="privacy_policy_link_availability_clarity",
                dimension="transparency",
                label="Privacy Policy Link Availability & Clarity",
                value=10.0,
                evidence="Privacy policy link found",
                confidence=0.9
            )

        # Only flag as missing for owned/corporate content where privacy policy is expected
        # Don't flag social media posts, marketplace listings, etc.
        content_type = self._determine_content_type(content)
        if content_type in ['landing_page', 'other'] and content.platform_type.lower() == 'owned':
            return DetectedAttribute(
                attribute_id="privacy_policy_link_availability_clarity",
                dimension="transparency",
                label="Privacy Policy Link Availability & Clarity",
                value=2.0,
                evidence="No privacy policy link detected on owned content",
                confidence=0.7
            )

        return None  # Not applicable for social/marketplace content

    def _detect_contact_info(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect contact/business info availability"""
        text = (content.body + " " + content.title).lower()
        meta = content.meta or {}

        # Check metadata
        has_contact_meta = any(key in meta for key in ["contact_url", "email", "phone", "address"])

        # Check for email patterns (simple regex)
        has_email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)

        # Check for phone patterns (very simple, to avoid false positives)
        # Look for "Call us: ..." or similar context if possible, but simple pattern for now
        # has_phone = re.search(r'\+?[\d\s-]{10,}', text) # Too risky for false positives

        # Check for "Contact Us" links/text
        contact_phrases = ["contact us", "get in touch", "customer support", "help center", "contact support"]
        has_contact_phrase = any(phrase in text for phrase in contact_phrases)

        if has_contact_meta or has_email or has_contact_phrase:
            return DetectedAttribute(
                attribute_id="contact_info_availability",
                dimension="transparency",
                label="Contact/Business Info Availability",
                value=10.0,
                evidence="Contact info or link found",
                confidence=0.9
            )
        
        return DetectedAttribute(
            attribute_id="contact_info_availability",
            dimension="transparency",
            label="Contact/Business Info Availability",
            value=2.0,
            evidence="No contact info detected",
            confidence=0.7
        )

    # ===== VERIFICATION DETECTORS =====

    def _detect_ad_labels(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect ad/sponsored label consistency"""
        text = (content.body + " " + content.title).lower()
        meta = content.meta or {}

        ad_labels = ["sponsored", "advertisement", "ad", "promoted", "paid partnership"]

        has_ad_label = (
            any(label in text for label in ad_labels) or
            meta.get("is_sponsored") == "true"
        )

        # Check for ad intent without proper labeling
        ad_intent_markers = ["buy now", "limited time offer", "discount code", "affiliate link"]
        has_ad_intent = any(m in text for m in ad_intent_markers)
        
        if has_ad_intent and not has_ad_label:
            return DetectedAttribute(
                attribute_id="ad_sponsored_label_consistency",
                dimension="verification",
                label="Ad/Sponsored Label Consistency",
                value=1.0,
                evidence="Commercial intent detected without visible ad disclosure",
                confidence=0.8
            )
        
        return None  # No issue detected

    def _detect_safety_guardrails(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect agent safety guardrails (placeholder)"""
        # TODO: Check for safety features in bot responses
        return None

    def _detect_claim_traceability(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect claim-to-source traceability"""
        # Reuse logic from _detect_citations since it covers the same ground
        # (detecting data claims and checking for citations)
        
        # We'll use a slightly stricter threshold or different logic if needed,
        # but for now, the core requirement is the same: claims need sources.
        
        # Call the existing citation detector
        citation_result = self._detect_citations(content)
        
        if not citation_result:
            return None
            
        # Map the result to the Verification dimension
        # If citations are missing (value < 10), it's a traceability issue
        
        # We only want to report this if there's an issue (value < 10)
        # or if we want to give credit for good traceability
        
        return DetectedAttribute(
            attribute_id="claim_to_source_traceability",
            dimension="verification",
            label="Claim traceability",  # Must match rubric.json
            value=citation_result.value,
            evidence=citation_result.evidence,
            confidence=citation_result.confidence
        )

    def _detect_engagement_authenticity(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect engagement authenticity ratio"""

        # Determine content type to check if engagement is expected
        content_type = self._determine_content_type(content)

        # Skip engagement detection for landing pages and promotional pages
        # where user engagement (upvotes, helpful counts) is not expected
        if content_type == 'landing_page':
            return None

        # Only apply engagement scoring to content types where it's meaningful
        # (blog, article, news, social_post)
        if content_type not in ['blog', 'article', 'news', 'social_post']:
            return None

        # Check for signs of authentic engagement
        upvotes = content.upvotes or 0
        helpful_count = content.helpful_count or 0

        # Simple heuristic: high engagement = likely authentic
        if upvotes > 100 or helpful_count > 10:
            value = 9.0
            evidence = f"High authentic engagement ({upvotes} upvotes, {helpful_count} helpful)"
        elif upvotes > 10:
            value = 7.0
            evidence = f"Moderate engagement ({upvotes} upvotes)"
        else:
            value = 5.0  # Neutral
            evidence = f"Low engagement ({upvotes} upvotes)"

        return DetectedAttribute(
            attribute_id="engagement_authenticity_ratio",
            dimension="verification",
            label="Engagement Authenticity Ratio",
            value=value,
            evidence=evidence,
            confidence=0.6
        )

    def _detect_influencer_verified(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect influencer/partner identity verification"""
        # Similar to author verification
        meta = content.meta or {}

        is_verified = (
            meta.get("influencer_verified") == "true" or
            meta.get("verified") == "true"
        )

        if is_verified:
            return DetectedAttribute(
                attribute_id="influencer_partner_identity_verified",
                dimension="verification",
                label="Influencer/Partner Identity Verified",
                value=10.0,
                evidence="Verified influencer/partner",
                confidence=1.0
            )
        return None

    def _detect_review_authenticity(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect review authenticity confidence"""
        text = (content.body + " " + content.title).lower()
        meta = content.meta or {}

        # 1. Amazon-specific logic (keep existing)
        if content.src == "amazon":
            is_verified = meta.get("verified_purchase") == "true"
            helpful_count = content.helpful_count or 0

            if is_verified and helpful_count > 5:
                value = 10.0
                evidence = "Verified purchase with helpful votes"
            elif is_verified:
                value = 8.0
                evidence = "Verified purchase"
            else:
                value = 5.0
                evidence = "Unverified purchase"
            
            return DetectedAttribute(
                attribute_id="review_authenticity_confidence",
                dimension="verification",
                label="Review Authenticity Confidence",
                value=value,
                evidence=evidence,
                confidence=0.7
            )

        # 2. General logic for other sites
        # Check for "Reviews" section or star ratings
        has_reviews_section = "reviews" in text or "customer reviews" in text
        
        # Look for "4.5 out of 5" or "4.5/5" patterns
        star_rating_match = re.search(r'(\d(?:\.\d)?)\s*(?:out of|/)\s*5', text)
        
        if has_reviews_section and star_rating_match:
            rating = float(star_rating_match.group(1))
            return DetectedAttribute(
                attribute_id="review_authenticity_confidence",
                dimension="verification",
                label="Review Authenticity Confidence",
                value=8.0, # Good confidence if we see ratings and review section
                evidence=f"Reviews section found with rating {rating}/5",
                confidence=0.6
            )
        elif has_reviews_section:
             return DetectedAttribute(
                attribute_id="review_authenticity_confidence",
                dimension="verification",
                label="Review Authenticity Confidence",
                value=6.0,
                evidence="Reviews section detected",
                confidence=0.5
            )

        return None

    def _detect_seller_verification(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect seller & product verification rate (placeholder)"""
        # TODO: Implement marketplace verification checking
        return None

    def _detect_verified_purchaser(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect verified purchaser review rate"""
        # Only applicable to Amazon reviews
        if content.src != "amazon":
            return None

        meta = content.meta or {}
        is_verified = meta.get("verified_purchase") == "true"

        if is_verified:
            return DetectedAttribute(
                attribute_id="verified_purchaser_review_rate",
                dimension="verification",
                label="Verified Purchaser Review Rate",
                value=10.0,
                evidence="Verified purchase badge present",
                confidence=1.0
            )
        else:
            return DetectedAttribute(
                attribute_id="verified_purchaser_review_rate",
                dimension="verification",
                label="Verified Purchaser Review Rate",
                value=3.0,
                evidence="No verified purchase badge",
                confidence=1.0
            )

    # ===== AI READINESS DETECTORS =====

    def _detect_schema_compliance(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect schema.org compliance"""
        meta = content.meta or {}

        # Check for schema.org structured data
        has_schema = any(key in meta for key in ["schema_org", "json_ld", "microdata", "rdfa"])
        schema_valid = meta.get("schema_valid") != "false"

        if has_schema and schema_valid:
            value = 10.0
            evidence = "Complete and valid schema.org markup present"
        elif has_schema:
            value = 7.0
            evidence = "Schema.org markup present but may be incomplete"
        else:
            value = 1.0
            evidence = "No schema.org structured data detected"

        return DetectedAttribute(
            label="Schema.org Compliance",
            value=value,
            evidence=evidence,
            confidence=0.9
        )

    def _detect_metadata_completeness(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect metadata completeness"""
        meta = content.meta or {}

        # Check for key metadata fields
        required_fields = ["title", "description", "author", "date", "keywords"]
        present_fields = []

        if content.title and len(content.title.strip()) > 0:
            present_fields.append("title")
        if content.body and len(content.body.strip()) > 100:  # Assume body contains description
            present_fields.append("description")
        if content.author and len(content.author.strip()) > 0:
            present_fields.append("author")
        if content.published_at:
            present_fields.append("date")
        if meta.get("keywords") or meta.get("tags"):
            present_fields.append("keywords")

        # Check OG tags
        has_og_tags = any(key.startswith("og_") for key in meta.keys())
        if has_og_tags:
            present_fields.append("og_tags")

        completeness = len(present_fields) / len(required_fields)
        value = 1.0 + (completeness * 9.0)  # Scale 1-10

        return DetectedAttribute(
            attribute_id="metadata_completeness",
            label="Metadata Completeness",
            value=value,
            evidence=f"{len(present_fields)}/{len(required_fields)} key metadata fields present",
            confidence=1.0
        )

    def _detect_llm_retrievability(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect LLM retrievability (indexability)"""
        meta = content.meta or {}

        # Check robots meta tag
        robots_content = meta.get("robots", "").lower()
        has_noindex = "noindex" in robots_content
        has_nofollow = "nofollow" in robots_content

        # Check if content is indexable
        if has_noindex:
            value = 1.0
            evidence = "Content has noindex directive - not retrievable by LLMs"
        elif has_nofollow:
            value = 5.0
            evidence = "Content has nofollow directive - limited retrievability"
        else:
            # Check if sitemap or other indexing signals exist
            has_sitemap = meta.get("in_sitemap") == "true"
            if has_sitemap:
                value = 10.0
                evidence = "Fully indexable with sitemap presence"
            else:
                value = 8.0
                evidence = "Indexable but no explicit sitemap signal"

        return DetectedAttribute(
            attribute_id="llm_retrievability",
            label="LLM Retrievability",
            value=value,
            evidence=evidence,
            confidence=0.9
        )

    def _detect_canonical_linking(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect canonical URL presence and validity"""
        meta = content.meta or {}

        canonical_url = meta.get("canonical_url") or meta.get("canonical")
        current_url = content.url

        if canonical_url:
            # Check if canonical matches current URL
            if canonical_url == current_url or canonical_url.rstrip('/') == current_url.rstrip('/'):
                value = 10.0
                evidence = "Canonical URL present and matches current URL"
            else:
                value = 5.0
                evidence = f"Canonical URL present but points elsewhere: {canonical_url}"
        else:
            value = 1.0
            evidence = "No canonical URL specified"

        return DetectedAttribute(
            attribute_id="canonical_linking",
            label="Canonical Linking",
            value=value,
            evidence=evidence,
            confidence=1.0
        )

    def _detect_indexing_visibility(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect indexing visibility (sitemap, robots.txt)"""
        meta = content.meta or {}

        has_sitemap = meta.get("has_sitemap") == "true" or meta.get("in_sitemap") == "true"
        robots_allowed = meta.get("robots_txt_allowed") != "false"
        has_noindex = "noindex" in meta.get("robots", "").lower()

        # Calculate score based on indexing signals
        if has_sitemap and robots_allowed and not has_noindex:
            value = 10.0
            evidence = "Sitemap present, robots.txt allows crawling, no noindex tag"
        elif robots_allowed and not has_noindex:
            value = 7.0
            evidence = "Indexable but no sitemap detected"
        elif has_noindex:
            value = 1.0
            evidence = "Noindex tag prevents indexing"
        else:
            value = 3.0
            evidence = "Limited indexing signals"

        return DetectedAttribute(
            attribute_id="indexing_visibility",
            label="Indexing Visibility",
            value=value,
            evidence=evidence,
            confidence=0.8
        )

    def _detect_ethical_training_signals(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect AI training opt-out/ethical signals"""
        meta = content.meta or {}

        # Check for TDM (Text and Data Mining) reservations
        has_tdm_reservation = any(key in meta for key in ["tdm_reservation", "ai_training_optout", "robots_tdm"])

        # Check robots.txt for AI crawler directives
        robots_txt = meta.get("robots_txt", "").lower()
        has_ai_directive = any(bot in robots_txt for bot in ["gptbot", "ccbot", "anthropic-ai", "claude-web"])

        if has_tdm_reservation or has_ai_directive:
            value = 10.0
            evidence = "Clear AI training opt-out or TDM reservation signals present"
        elif meta.get("copyright") or meta.get("rights"):
            value = 5.0
            evidence = "Copyright/rights metadata present (ambiguous AI training policy)"
        else:
            value = 1.0
            evidence = "No AI training policy or TDM reservation signals"

        return DetectedAttribute(
            attribute_id="ethical_training_signals",
            label="Ethical Training Signals",
            value=value,
            evidence=evidence,
            confidence=0.7
        )

    def _detect_ad_labels(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect ad/sponsored label consistency"""
        text = (content.body + " " + content.title).lower()
        
        # Check for ad intent markers without proper labeling
        ad_intent_markers = ["buy now", "limited time offer", "discount code", "affiliate link"]
        has_ad_intent = any(m in text for m in ad_intent_markers)
        
        proper_labels = ["ad", "sponsored", "paid partnership", "promoted"]
        has_proper_label = any(l in text for l in proper_labels)
        
        if has_ad_intent and not has_proper_label:
            return DetectedAttribute(
                attribute_id="ad_sponsored_label_consistency",
                dimension="verification",
                label="Ad/Sponsored Label Consistency",
                value=1.0,
                evidence="Commercial intent detected without visible ad disclosure",
                confidence=0.8
            )
        return None

    def _detect_safety_guardrails(self, content: NormalizedContent) -> Optional[DetectedAttribute]:
        """Detect agent safety guardrail presence"""
        # Only relevant for agent/bot content
        if content.modality != 'agent':
            return None
            
        # Check metadata for guardrail config
        meta = content.meta or {}
        if meta.get('safety_guardrails') == 'false':
             return DetectedAttribute(
                attribute_id="agent_safety_guardrail_presence",
                dimension="verification",
                label="Agent Safety Guardrail Presence",
                value=1.0,
                evidence="No safety guardrails configuration found",
                confidence=1.0
            )
        return None
