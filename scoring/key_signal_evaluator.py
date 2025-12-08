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
# This bridges the attribute detector output to the report's key signal categories
ATTRIBUTE_TO_KEY_SIGNAL = {
    # Provenance
    'author_brand_identity_verified': 'Authorship & Attribution',
    'c2pa_cai_manifest_present': 'Metadata & Technical Provenance',
    'exif_metadata_integrity': 'Metadata & Technical Provenance',
    'canonical_url_matches_declared_source': 'Metadata & Technical Provenance',
    'source_domain_trust_baseline': 'Brand Presence & Continuity',
    'digital_watermark_fingerprint_detected': 'Metadata & Technical Provenance',
    # WHOIS-based provenance signals
    'domain_age': 'Brand Presence & Continuity',
    'whois_privacy': 'Brand Presence & Continuity',
    'ai_vs_human_labeling_clarity': 'Authorship & Attribution',
    
    # Resonance
    'personalization_relevance_embedding_similarity': 'Dynamic Personalization',
    'engagement_authenticity_ratio': 'Opt-in & Accessible Personalization',
    'language_locale_match': 'Cultural Fluency & Inclusion',
    'readability_grade_level_fit': 'Creative Relevance',
    
    # Coherence
    'brand_voice_consistency_score': 'Narrative Alignment Across Channels',
    'multimodal_consistency_score': 'Design System & Interaction Patterns',
    'claim_consistency_across_pages': 'Behavioral Consistency',
    'broken_link_rate': 'Feedback Loops & Adaptive Clarity',
    
    # Transparency
    'privacy_policy_link_availability_clarity': 'Plain Language Disclosures',
    'ai_generated_assisted_disclosure_present': 'AI/ML & Automation Clarity',
    'ai_explainability_disclosure': 'AI/ML & Automation Clarity',
    'bot_disclosure_response_audit': 'AI/ML & Automation Clarity',
    'contact_info_availability': 'User Control & Consent Management',
    'ad_sponsored_label_consistency': 'Provenance Labeling & Source Integrity',
    'data_source_citations_for_claims': 'Provenance Labeling & Source Integrity',
    
    # Verification
    'claim_to_source_traceability': 'Third-Party Trust Layers',
    'seller_product_verification_rate': 'Third-Party Trust Layers',
    'verified_purchaser_review_rate': 'Authentic Social Proof',
    'review_authenticity_confidence': 'Authentic Social Proof',
}

# Also map by LABEL string (what appears in the diagnostics table)
# This ensures we match attributes regardless of whether they have attribute_id set
LABEL_TO_KEY_SIGNAL = {
    # Provenance
    'Author/Brand Identity Verified': 'Authorship & Attribution',
    'C2PA/CAI Manifest Present': 'Metadata & Technical Provenance',
    'EXIF/Metadata Integrity': 'Metadata & Technical Provenance',
    'Canonical URL Matches Declared Source': 'Metadata & Technical Provenance',
    'Source Domain Trust Baseline': 'Brand Presence & Continuity',
    'Digital Watermark Detected': 'Metadata & Technical Provenance',
    # WHOIS-based provenance signals
    'Domain Age': 'Brand Presence & Continuity',
    'WHOIS Privacy Status': 'Brand Presence & Continuity',
    'AI vs Human Labeling Clarity': 'Authorship & Attribution',
    
    # Resonance
    'Personalization Relevance': 'Dynamic Personalization',
    'Engagement Authenticity Ratio': 'Opt-in & Accessible Personalization',
    'Language/Locale Match': 'Cultural Fluency & Inclusion',
    'Readability Grade Level Fit': 'Creative Relevance',
    
    # Coherence
    'Brand Voice Consistency Score': 'Narrative Alignment Across Channels',
    'Multimodal Consistency Score': 'Design System & Interaction Patterns',
    'Claim Consistency Across Pages': 'Behavioral Consistency',
    'Broken Link Rate': 'Feedback Loops & Adaptive Clarity',
    
    # Transparency
    'Privacy Policy Link Availability & Clarity': 'Plain Language Disclosures',
    'AI-Generated/Assisted Disclosure Present': 'AI/ML & Automation Clarity',
    'AI Explainability Disclosure': 'AI/ML & Automation Clarity',
    'Bot Disclosure Response Audit': 'AI/ML & Automation Clarity',
    'Contact/Business Info Availability': 'User Control & Consent Management',
    'Ad/Sponsored Label Consistency': 'Provenance Labeling & Source Integrity',
    'Data Source Citations for Claims': 'Provenance Labeling & Source Integrity',
    
    # Verification
    'Claim Traceability': 'Third-Party Trust Layers',
    'Claim to Source Traceability': 'Third-Party Trust Layers',
    'Seller/Product Verification Rate': 'Third-Party Trust Layers',
    'Verified Purchaser Review Rate': 'Authentic Social Proof',
    'Review Authenticity Confidence': 'Authentic Social Proof',
}


class KeySignalEvaluator:
    """Generates key signal evaluations for trust dimensions"""
    
    def __init__(self):
        """Initialize the key signal evaluator"""
        # Define key signals for each dimension based on the reference format
        self.dimension_signals = {
            'provenance': [
                'Authorship & Attribution',
                'Verification & Identity',
                'Brand Presence & Continuity',
                'Metadata & Technical Provenance',
                'Intent & Legitimacy'
            ],
            'resonance': [
                'Dynamic Personalization',
                'Cultural Fluency & Inclusion',
                'Emotional Tone & Timing',
                'Modality & Channel Continuity',
                'Opt-in & Accessible Personalization',
                'Creative Relevance'
            ],
            'coherence': [
                'Narrative Alignment Across Channels',
                'Behavioral Consistency',
                'Design System & Interaction Patterns',
                'Temporal Continuity',
                'Feedback Loops & Adaptive Clarity'
            ],
            'transparency': [
                'Plain Language Disclosures',
                'AI/ML & Automation Clarity',
                'Provenance Labeling & Source Integrity',
                'User Control & Consent Management',
                'Explainable System Behavior',
                'Trust Recovery Mechanisms'
            ],
            'verification': [
                'Authentic Social Proof',
                'Human Validation & Peer Endorsement',
                'Third-Party Trust Layers',
                'Moderation & Dispute Transparency',
                'Cross-Platform Reputation Consistency',
                'Secure & Tamper-Resistant Systems'
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
