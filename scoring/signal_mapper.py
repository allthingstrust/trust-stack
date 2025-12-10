"""
Signal Mapper (v5.1)
Maps legacy DetectedAttributes to new SignalScores based on configuration.
Includes complete attribute-to-signal mapping for all 39 v5.1 signals.
"""

import logging
from typing import List, Dict, Optional
from scoring.types import SignalScore
from data.models import DetectedAttribute

logger = logging.getLogger(__name__)

class SignalMapper:
    """Maps detected attributes to signals defined in trust_signals.yml"""
    
    # v5.1: Complete mapping from Attribute ID -> Signal ID
    # Based on unified_signal_mapping_v5.1.csv
    ATTRIBUTE_TO_SIGNAL_MAP = {
        # --- PROVENANCE (8 attributes) ---
        "ai_vs_human_labeling_clarity": "trans_ai_labeling",  # Cross-dimension: Provenance -> Transparency
        "author_brand_identity_verified": "prov_author_bylines",
        "c2pa_cai_manifest_present": "prov_metadata_c2pa",
        "canonical_url_matches_declared_source": "prov_source_clarity",
        "source_domain_trust_baseline": "prov_domain_trust",
        "creator_brand_disclosure_match": "trans_disclosures",  # Cross-dimension: Provenance -> Transparency
        "exif_metadata_integrity": "prov_metadata_c2pa",
        "first_seen_timestamp_crawl": "prov_date_freshness",
        # Additional provenance mappings (from legacy)
        "domain_age": "prov_domain_trust",
        "whois_privacy": "prov_domain_trust",
        "digital_watermark_fingerprint_detected": "prov_metadata_c2pa",
        "metadata_completeness": "prov_source_clarity",
        "verified_platform_account": "prov_author_bylines",
        
        # --- RESONANCE (7 attributes) ---
        "language_locale_match": "res_cultural_fit",
        "cultural_context_alignment": "res_cultural_fit",
        "readability_grade_level_fit": "res_readability",
        "tone_sentiment_appropriateness": "res_cultural_fit",
        "accessibility_compliance_wcag": None,  # needs_new_signal - unmapped for now
        "personalization_relevance_embedding_similarity": "res_personalization",
        "community_alignment_index": "res_engagement_metrics",
        
        # --- COHERENCE (6 attributes) ---
        "brand_voice_consistency_score": "coh_voice_consistency",
        "claim_consistency_across_pages": "coh_voice_consistency",
        "multimodal_consistency_score": "coh_design_patterns",
        "email_asset_consistency_check": "coh_cross_channel",
        "temporal_continuity_versions": None,  # needs_new_signal - unmapped for now
        "version_history_completeness": None,  # needs_new_signal - unmapped for now
        # Additional coherence mappings (from legacy)
        "broken_link_rate": "coh_technical_health",
        "schema_compliance": "coh_technical_health",
        
        # --- TRANSPARENCY (7 attributes) ---
        "ai_generated_assisted_disclosure_present": "trans_ai_labeling",
        "data_source_citations_for_claims": "prov_source_clarity",  # Cross-dimension: Transparency -> Provenance
        "privacy_policy_link_availability_clarity": "trans_disclosures",
        "bot_disclosure_response_audit": "trans_ai_labeling",
        "ai_explainability_disclosure": "trans_ai_labeling",
        "model_identification_version": "trans_ai_labeling",
        # Additional transparency mappings (from legacy)
        "contact_info_availability": "trans_contact_info",
        
        # --- VERIFICATION (11 attributes) ---
        "ad_sponsored_label_consistency": "trans_disclosures",  # Cross-dimension: Verification -> Transparency
        "sponsored_content_labeling": "trans_disclosures",  # Cross-dimension: Verification -> Transparency
        "claim_to_source_traceability": "ver_fact_accuracy",
        "engagement_authenticity_ratio": "res_engagement_metrics",  # Cross-dimension: Verification -> Resonance
        "review_authenticity_confidence": "ver_social_proof",
        "third_party_certifications_present": "ver_trust_badges",
        "verified_purchaser_review_rate": "ver_social_proof",
        "seller_product_verification_rate": "ver_trust_badges",
        "influencer_partner_identity_verified": None,  # needs_new_signal - unmapped for now
        "synthetic_media_traceability": "prov_metadata_c2pa",  # Cross-dimension: Verification -> Provenance
        "channel_account_security_posture": None,  # needs_new_signal - unmapped for now
    }

    def __init__(self, trust_signals_config: Dict):
        """
        Initialize with trust signals configuration
        
        Args:
            trust_signals_config: The full trust_signals config dict 
                                  (with 'dimensions', 'signals', 'scoring' keys)
        """
        self.signals_config = trust_signals_config.get('signals', {})

    def map_attributes_to_signals(self, attributes: List[DetectedAttribute]) -> List[SignalScore]:
        """
        Convert a list of DetectedAttributes to SignalScores.
        
        Args:
            attributes: List of attributes detected by TrustStackAttributeDetector
            
        Returns:
            List of SignalScore objects ready for the Aggregator
        """
        mapped_signals = []
        
        for attr in attributes:
            signal_id = self.ATTRIBUTE_TO_SIGNAL_MAP.get(attr.attribute_id)
            
            if signal_id is None:
                # Attribute doesn't map to a configured signal (unmapped or needs_new_signal)
                logger.debug(f"Attribute '{attr.attribute_id}' has no signal mapping, skipping")
                continue
                
            signal_def = self.signals_config.get(signal_id)
            if not signal_def:
                logger.warning(f"Mapped signal ID '{signal_id}' not found in configuration")
                continue
                
            # Create SignalScore
            # Attribute value is 1-10, SignalScore expects 0.0-1.0
            # Defensive normalization: handle edge cases
            raw_value = float(attr.value)
            if raw_value > 1.0:
                signal_value = raw_value / 10.0
            else:
                signal_value = raw_value
            signal_value = max(0.0, min(1.0, signal_value))  # Clamp to 0-1
            
            # We use the weight from the signal definition
            signal = SignalScore(
                id=signal_id,
                label=signal_def.get('label', attr.label),
                dimension=signal_def.get('dimension', attr.dimension),
                value=signal_value,
                weight=float(signal_def.get('weight', 1.0)),
                evidence=[attr.evidence] if attr.evidence else [],
                rationale=f"Detected via {attr.attribute_id}",
                confidence=float(attr.confidence)
            )
            
            mapped_signals.append(signal)
            
        return mapped_signals
