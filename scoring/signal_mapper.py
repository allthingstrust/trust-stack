"""
Signal Mapper
Maps legacy DetectedAttributes to new SignalScores based on configuration.
"""

import logging
from typing import List, Dict, Optional
from scoring.types import SignalScore
from data.models import DetectedAttribute

logger = logging.getLogger(__name__)

class SignalMapper:
    """Maps detected attributes to signals defined in trust_signals.yml"""
    
    # Static mapping from Attribute ID -> Signal ID
    # This bridges the gap between the old attribute detector and the new signal-based scorer
    ATTRIBUTE_TO_SIGNAL_MAP = {
        # Provenance
        "author_brand_identity_verified": "prov_author_bylines",
        "c2pa_cai_manifest_present": "prov_metadata_c2pa",
        "source_domain_trust_baseline": "prov_source_clarity", # Best fit for now
        "digital_watermark_fingerprint_detected": "prov_metadata_c2pa", # Map to same signal or create new one? Mapping to C2PA for now as "cryptographic provenance"
        
        # Resonance
        "personalization_relevance_embedding_similarity": "res_personalization",
        "engagement_authenticity_ratio": "res_engagement_metrics",
        "language_locale_match": "res_cultural_fit",
        "readability_grade_level_fit": "res_readability",
        
        # Coherence
        "brand_voice_consistency_score": "coh_voice_consistency",
        "multimodal_consistency_score": "coh_design_patterns",
        "claim_consistency_across_pages": "coh_voice_consistency", # Roll into voice consistency
        "broken_link_rate": "coh_technical_health",
        
        # Transparency
        "privacy_policy_link_availability_clarity": "trans_disclosures",
        "ai_generated_assisted_disclosure_present": "trans_ai_labeling",
        "ai_vs_human_labeling_clarity": "trans_ai_labeling",
        "bot_disclosure_response_audit": "trans_ai_labeling",
        "contact_info_availability": "trans_contact_info",
        
        # Verification
        "claim_to_source_traceability": "ver_fact_accuracy",
        "seller_product_verification_rate": "ver_trust_badges",
        "verified_purchaser_review_rate": "ver_social_proof",
        "review_authenticity_confidence": "ver_social_proof",
        
        # Additional mappings
        "ad_sponsored_label_consistency": "trans_disclosures",
        "schema_compliance": "coh_technical_health",
        "metadata_completeness": "prov_source_clarity",
        "canonical_url_matches_declared_source": "prov_source_clarity",
        "exif_metadata_integrity": "prov_metadata_c2pa",
    }

    def __init__(self, trust_signals_config: Dict):
        """
        Initialize with trust signals configuration
        
        Args:
            trust_signals_config: The 'signals' section of trust_signals.yml
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
            
            if not signal_id:
                # Attribute doesn't map to a configured signal, skip it
                # (Or we could map it to a generic "other" signal if needed)
                continue
                
            signal_def = self.signals_config.get(signal_id)
            if not signal_def:
                logger.warning(f"Mapped signal ID '{signal_id}' not found in configuration")
                continue
                
            # Create SignalScore
            # Attribute value is 1-10, SignalScore expects 0-10 (compatible)
            # We use the weight from the signal definition
            
            signal = SignalScore(
                id=signal_id,
                label=signal_def.get('label', attr.label),
                dimension=signal_def.get('dimension', attr.dimension),
                value=float(attr.value),
                weight=float(signal_def.get('weight', 1.0)),
                evidence=[attr.evidence] if attr.evidence else [],
                rationale=f"Detected via {attr.attribute_id}",
                confidence=float(attr.confidence)
            )
            
            mapped_signals.append(signal)
            
        return mapped_signals
