"""
Key Signal Evaluation Generator
Generates structured key signal assessments for each trust dimension.
Computes status DETERMINISTICALLY from detected attributes, then uses LLM for explanatory text.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from data.models import NormalizedContent

logger = logging.getLogger(__name__)


# Mapping from detected attribute IDs to key signal names
# v5.1: Aligned with actual signals in trust_signals.yml
ATTRIBUTE_TO_KEY_SIGNAL = {
    # Provenance
    'author_brand_identity_verified': 'Author & Creator Clarity',
    'verified_platform_account': 'Author & Creator Clarity',
    'canonical_url_matches_declared_source': 'Source Attribution',
    'c2pa_cai_manifest_present': 'Content Credentials (C2PA)',
    'exif_metadata_integrity': 'Content Credentials (C2PA)',
    'digital_watermark_fingerprint_detected': 'Content Credentials (C2PA)',
    'source_domain_trust_baseline': 'Domain Trust & History',
    'domain_age': 'Domain Trust & History',
    'whois_privacy': 'Domain Trust & History',
    'first_seen_timestamp_crawl': 'Content Freshness',
    
    # Resonance
    'language_locale_match': 'Language Match',
    'cultural_context_alignment': 'Cultural & Audience Fit',
    'tone_sentiment_appropriateness': 'Cultural & Audience Fit',
    'readability_grade_level_fit': 'Readability & Clarity',
    'personalization_relevance_embedding_similarity': 'Personalization Relevance',
    'engagement_authenticity_ratio': 'Engagement Quality',
    'community_alignment_index': 'Engagement Quality',
    
    # Coherence
    'brand_voice_consistency_score': 'Voice Consistency',
    'claim_consistency_across_pages': 'Claim Consistency',
    'multimodal_consistency_score': 'Visual/Design Coherence',
    'email_asset_consistency_check': 'Cross-Channel Alignment',
    'broken_link_rate': 'Technical Health',
    'schema_compliance': 'Technical Health',
    
    # Transparency
    'privacy_policy_link_availability_clarity': 'Privacy Policy Clarity',
    'ai_generated_assisted_disclosure_present': 'AI Usage Disclosure',
    'ai_explainability_disclosure': 'AI Usage Disclosure',
    'bot_disclosure_response_audit': 'AI Usage Disclosure',
    'ai_vs_human_labeling_clarity': 'AI Usage Disclosure',
    'contact_info_availability': 'Contact/Business Info',
    'ad_sponsored_label_consistency': 'Clear Disclosures',
    'data_source_citations_for_claims': 'Data Source Citations',
    
    # Verification
    'claim_to_source_traceability': 'Claim Traceability',
    'seller_product_verification_rate': 'Trust Badges & Certs',
    'third_party_certifications_present': 'Trust Badges & Certs',
    'verified_purchaser_review_rate': 'Review Authenticity',
    'review_authenticity_confidence': 'Review Authenticity',
}

# Also map by LABEL string (what appears in the diagnostics table)
# v5.1: Aligned with actual signals in trust_signals.yml
LABEL_TO_KEY_SIGNAL = {
    # Provenance
    'Author/Brand Identity Verified': 'Author & Creator Clarity',
    'Verified Platform Account': 'Author & Creator Clarity',
    'Canonical URL Matches Declared Source': 'Source Attribution',
    'C2PA/CAI Manifest Present': 'Content Credentials (C2PA)',
    'EXIF/Metadata Integrity': 'Content Credentials (C2PA)',
    'Digital Watermark Detected': 'Content Credentials (C2PA)',
    'Source Domain Trust Baseline': 'Domain Trust & History',
    'Domain Age': 'Domain Trust & History',
    'WHOIS Privacy Status': 'Domain Trust & History',
    
    # Resonance
    'Language/Locale Match': 'Language Match',
    'Cultural Context Alignment': 'Cultural & Audience Fit',
    'Tone Sentiment Appropriateness': 'Cultural & Audience Fit',
    'Readability Grade Level Fit': 'Readability & Clarity',
    'Personalization Relevance': 'Personalization Relevance',
    'Engagement Authenticity Ratio': 'Engagement Quality',
    
    # Coherence
    'Brand Voice Consistency Score': 'Voice Consistency',
    'Claim Consistency Across Pages': 'Claim Consistency',
    'Multimodal Consistency Score': 'Visual/Design Coherence',
    'Broken Link Rate': 'Technical Health',
    
    # Transparency
    'Privacy Policy Link Availability & Clarity': 'Privacy Policy Clarity',
    'AI-Generated/Assisted Disclosure Present': 'AI Usage Disclosure',
    'AI Explainability Disclosure': 'AI Usage Disclosure',
    'Bot Disclosure Response Audit': 'AI Usage Disclosure',
    'AI vs Human Labeling Clarity': 'AI Usage Disclosure',
    'Contact/Business Info Availability': 'Contact/Business Info',
    'Ad/Sponsored Label Consistency': 'Clear Disclosures',
    'Data Source Citations for Claims': 'Data Source Citations',
    
    # Verification
    'Claim Traceability': 'Claim Traceability',
    'Claim to Source Traceability': 'Claim Traceability',
    'Seller/Product Verification Rate': 'Trust Badges & Certs',
    'Third Party Certifications Present': 'Trust Badges & Certs',
    'Verified Purchaser Review Rate': 'Review Authenticity',
    'Review Authenticity Confidence': 'Review Authenticity',
}


class KeySignalEvaluator:
    """Generates key signal evaluations for trust dimensions"""
    
    def __init__(self):
        """Initialize the key signal evaluator"""
        # v5.1: Key signals aligned with trust_signals.yml (5 per dimension)
        self.dimension_signals = {
            'provenance': [
                'Author & Creator Clarity',
                'Source Attribution',
                'Domain Trust & History',
                'Content Credentials (C2PA)',
                'Content Freshness'
            ],
            'resonance': [
                'Cultural & Audience Fit',
                'Readability & Clarity',
                'Personalization Relevance',
                'Engagement Quality',
                'Language Match'
            ],
            'coherence': [
                'Voice Consistency',
                'Visual/Design Coherence',
                'Cross-Channel Alignment',
                'Technical Health',
                'Claim Consistency'
            ],
            'transparency': [
                'Clear Disclosures',
                'AI Usage Disclosure',
                'Contact/Business Info',
                'Privacy Policy Clarity',
                'Data Source Citations'
            ],
            'verification': [
                'Factual Accuracy',
                'Trust Badges & Certs',
                'External Social Proof',
                'Review Authenticity',
                'Claim Traceability'
            ]
        }
    
    def compute_signal_statuses(
        self,
        dimension: str,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Tuple[str, float, List[str]]]:
        """
        Compute key signal statuses DETERMINISTICALLY from detected attributes.
        
        Args:
            dimension: Dimension name (provenance, resonance, etc.)
            items: List of content items with 'meta.detected_attributes'
            
        Returns:
            Dict mapping signal_name -> (status_icon, avg_score, evidence_list)
            Status icons: ✅ (>=7), ⚠️ (4-6.9), ❌ (<4 or no data)
        """
        if dimension not in self.dimension_signals:
            return {}
        
        # Collect all detected attributes from all items
        all_attributes = []
        for item in items:
            meta = item.get('meta', {})
            if isinstance(meta, str):
                try:
                    import json
                    meta = json.loads(meta) if meta else {}
                except:
                    meta = {}
            detected = meta.get('detected_attributes', [])
            all_attributes.extend(detected)
        
        # Aggregate scores per key signal
        signal_scores: Dict[str, List[Tuple[float, str]]] = {}
        for attr in all_attributes:
            attr_id = attr.get('attribute_id', '')
            attr_label = attr.get('label', '')
            attr_dimension = attr.get('dimension', '').lower()
            
            # Only process attributes for this dimension
            if attr_dimension != dimension.lower():
                continue
            
            # Map to key signal - try by ID first, then by label
            key_signal = ATTRIBUTE_TO_KEY_SIGNAL.get(attr_id)
            if not key_signal:
                key_signal = LABEL_TO_KEY_SIGNAL.get(attr_label)
            if not key_signal:
                # Log unmapped attribute for debugging
                logger.debug(f"Unmapped attribute: id='{attr_id}', label='{attr_label}'")
                continue
            
            # Record score and evidence
            score = float(attr.get('value', 0))
            evidence = attr.get('evidence', '')
            
            if key_signal not in signal_scores:
                signal_scores[key_signal] = []
            signal_scores[key_signal].append((score, evidence))
        
        # Compute status for each key signal
        results = {}
        for signal_name in self.dimension_signals.get(dimension, []):
            scores_evidence = signal_scores.get(signal_name, [])
            
            if not scores_evidence:
                # No data for this signal
                results[signal_name] = ('❌', 0.0, ['No attributes detected'])
            else:
                scores = [s for s, _ in scores_evidence]
                evidence = [e for _, e in scores_evidence if e][:3]  # Limit to 3
                avg_score = sum(scores) / len(scores)
                
                if avg_score >= 7.0:
                    status = '✅'
                elif avg_score >= 4.0:
                    status = '⚠️'
                else:
                    status = '❌'
                
                results[signal_name] = (status, avg_score, evidence)
        
        return results
    
    def generate_key_signals(
        self,
        dimension: str,
        items: List[Dict[str, Any]],
        dimension_score: float,
        model: str = 'gpt-4o-mini'
    ) -> List[Dict[str, Any]]:
        """
        Generate key signal evaluations for a dimension
        
        Args:
            dimension: Dimension name (provenance, resonance, etc.)
            items: List of analyzed content items
            dimension_score: Average score for this dimension (0-1 scale)
            model: LLM model to use
            
        Returns:
            List of signal evaluations with status (✅/⚠️/❌), summary, and assessment
        """
        if dimension not in self.dimension_signals:
            logger.warning(f"Unknown dimension: {dimension}")
            return []
        
        signals = self.dimension_signals[dimension]
        evaluations = []
        
        # Use LLM to evaluate each signal
        for idx, signal_name in enumerate(signals, 1):
            evaluation = self._evaluate_signal_with_llm(
                dimension=dimension,
                signal_name=signal_name,
                signal_number=idx,
                items=items,
                dimension_score=dimension_score,
                model=model
            )
            if evaluation:
                evaluations.append(evaluation)
        
        return evaluations
    
    def _evaluate_signal_with_llm(
        self,
        dimension: str,
        signal_name: str,
        signal_number: int,
        items: List[Dict[str, Any]],
        dimension_score: float,
        model: str
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to evaluate a specific signal
        
        Returns:
            Dict with keys: number, name, status (✅/⚠️/❌), summary, assessment
        """
        try:
            from scoring.scoring_llm_client import LLMScoringClient
            
            # Prepare context from items
            context = self._prepare_context_for_signal(items, dimension, signal_name)
            
            # Create prompt for LLM
            prompt = self._create_signal_evaluation_prompt(
                dimension=dimension,
                signal_name=signal_name,
                context=context,
                dimension_score=dimension_score
            )
            
            # Call LLM
            client = LLMScoringClient()
            response = client.generate(
                prompt=prompt,
                model=model,
                max_tokens=300,
                temperature=0.3
            )
            
            # Parse response
            response_text = response.strip() if response else ''
            if not response_text:
                return None
            
            # Extract status and assessment from response
            status = self._extract_status_from_response(response_text, dimension_score)
            assessment = response_text.strip()
            
            # Create summary (first sentence or up to 100 chars)
            summary = assessment.split('.')[0][:100] + ('...' if len(assessment.split('.')[0]) > 100 else '.')
            
            return {
                'number': signal_number,
                'name': signal_name,
                'status': status,
                'summary': summary,
                'assessment': assessment
            }
            
        except Exception as e:
            logger.error(f"Error evaluating signal {signal_name}: {e}")
            # Return a fallback evaluation
            return {
                'number': signal_number,
                'name': signal_name,
                'status': '⚠️',
                'summary': 'Analysis pending',
                'assessment': f'Automated evaluation for {signal_name} is being processed.'
            }
    
    def _prepare_context_for_signal(
        self,
        items: List[Dict[str, Any]],
        dimension: str,
        signal_name: str
    ) -> str:
        """
        Prepare relevant context from items for signal evaluation
        
        Args:
            items: Content items
            dimension: Dimension name
            signal_name: Signal name
            
        Returns:
            Context string for LLM
        """
        # Sample up to 5 items for context
        sample_items = items[:5] if len(items) > 5 else items
        
        context_parts = []
        for item in sample_items:
            meta = item.get('meta', {})
            if isinstance(meta, str):
                try:
                    import json
                    meta = json.loads(meta) if meta else {}
                except:
                    meta = {}
            
            # Extract relevant info
            title = meta.get('title', item.get('title', 'Untitled'))
            url = meta.get('source_url', meta.get('url', ''))
            
            # Get dimension-specific attributes
            detected_attrs = meta.get('detected_attributes', [])
            relevant_attrs = [
                attr for attr in detected_attrs
                if attr.get('dimension') == dimension
            ]
            
            # Construct context entry
            entry = f"- {title}"
            if relevant_attrs:
                attr_summary = ', '.join([
                    f"{attr.get('label')}: {attr.get('value')}/10"
                    for attr in relevant_attrs[:3]
                ])
                entry += f" (Attributes: {attr_summary})"
            
            # Add content snippet for context
            body = item.get('body', '') or meta.get('description', '')
            if body:
                # Truncate body to avoid hitting token limits, but keep enough for context
                snippet = body[:500].replace('\n', ' ')
                entry += f"\n  Content Snippet: \"{snippet}...\""
            
            context_parts.append(entry)
        
        if not context_parts:
            return "Limited content metadata available for analysis."
        
        return "\n\n".join(context_parts)
    
    def _create_signal_evaluation_prompt(
        self,
        dimension: str,
        signal_name: str,
        context: str,
        dimension_score: float
    ) -> str:
        """
        Create LLM prompt for signal evaluation
        
        Args:
            dimension: Dimension name
            signal_name: Signal name
            context: Context from content items
            dimension_score: Overall dimension score (0-1)
            
        Returns:
            Prompt string
        """
        # Convert score to 0-10 scale for prompt
        score_display = round(dimension_score * 10, 1)
        
        prompt = f"""Evaluate the "{signal_name}" signal for the {dimension.title()} trust dimension.

Overall {dimension.title()} Score: {score_display} / 10

Content Analysis:
{context}

Instructions:
1. First, infer the PRIMARY INTENT of the site based on the content (e.g., E-commerce/Promotional, News/Journalism, Corporate/Informational, Personal/Blog).
2. Contextualize your evaluation based on this intent. 
   - If the site is PROMOTIONAL (e.g., selling products), do NOT criticize it for "prioritizing sales messaging" or "promotional focus" - that is its purpose. Instead, evaluate how it builds trust WITHIN that context (e.g., are claims substantiated? is pricing transparent? is the "About Us" informative?).
   - If the site is INFORMATIONAL, expect higher standards of neutrality and sourcing.
3. Provide a concise assessment (2-3 sentences) of how well the content performs on this specific signal ({signal_name}).

CRITICAL: You MUST include concrete details and direct quotes from the content analysis to support your assessment. 
Do not use generic phrases like "the content lacks clear authorship". Instead, say "The 'About Us' page does not list any team members" or "The article by 'Jane Doe' establishes clear authorship".

Focus on:
1. Specific evidence found (quote it!) or specific gaps observed
2. How this specific evidence impacts trust given the site's context
3. Whether the signal is present and strong

Assessment:"""
        
        return prompt
        
        return prompt
    
    def _extract_status_from_response(
        self,
        response_text: str,
        dimension_score: float
    ) -> str:
        """
        Determine status indicator (✅/⚠️/❌) from LLM response and score
        
        Args:
            response_text: LLM response
            dimension_score: Dimension score (0-1)
            
        Returns:
            Status emoji
        """
        # Check for explicit positive/negative language
        positive_indicators = [
            'strong', 'excellent', 'clear', 'present', 'well', 'good',
            'consistent', 'robust', 'effective', 'comprehensive'
        ]
        negative_indicators = [
            'missing', 'absent', 'weak', 'poor', 'lacking', 'limited',
            'unclear', 'inconsistent', 'insufficient', 'no evidence'
        ]
        
        text_lower = response_text.lower()
        
        positive_count = sum(1 for word in positive_indicators if word in text_lower)
        negative_count = sum(1 for word in negative_indicators if word in text_lower)
        
        # Combine text analysis with score
        if dimension_score >= 0.7 and positive_count > negative_count:
            return '✅'
        elif dimension_score < 0.4 or negative_count > positive_count + 1:
            return '❌'
        else:
            return '⚠️'


def generate_key_signals_for_dimension(
    dimension: str,
    items: List[Dict[str, Any]],
    dimension_score: float,
    model: str = 'gpt-4o-mini'
) -> List[Dict[str, Any]]:
    """
    Convenience function to generate key signals for a dimension
    
    Args:
        dimension: Dimension name
        items: Content items
        dimension_score: Dimension score (0-1)
        model: LLM model to use
        
    Returns:
        List of signal evaluations
    """
    evaluator = KeySignalEvaluator()
    return evaluator.generate_key_signals(
        dimension=dimension,
        items=items,
        dimension_score=dimension_score,
        model=model
    )
