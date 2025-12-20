"""
Verification Manager

Handles RAG-based verification of content claims using Serper Search.
Prompts are imported from the centralized prompts module.
"""

import logging
import json
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from ingestion.serper_search import search_serper
from scoring.scoring_llm_client import LLMScoringClient
from data.models import NormalizedContent

from prompts.verification import (
    CLAIM_EXTRACTION_SYSTEM,
    VERIFICATION_SYSTEM,
    build_claim_extraction_prompt,
    build_verification_prompt,
)

logger = logging.getLogger(__name__)


class VerificationManager:
    """
    Manages the verification process:
    1. Extract claims from content
    2. Search for evidence (Serper/Google Search)
    3. Verify claims against evidence
    """
    
    def __init__(self):
        self.llm_client = LLMScoringClient()
        
    def verify_content(self, content: NormalizedContent) -> Dict[str, Any]:
        """Perform fact-checked verification of content."""
        # Check for visual verification (social media)
        visual_verification = self._check_visual_verification(content)
        
        claims = self._extract_claims(content)
        if not claims and not visual_verification:
            logger.info(f"No verifiable claims found for {content.content_id}")
            return {'score': 0.5, 'issues': []}
            
        verified_claims = self._verify_claims_parallel(claims)
        
        # Merge visual verification results
        if visual_verification:
            verified_claims.insert(0, visual_verification)
            
        return self._aggregate_results(verified_claims)

    def _check_visual_verification(self, content: NormalizedContent) -> Optional[Dict[str, Any]]:
        """Check if visual analysis found a verification badge."""
        if not content.visual_analysis:
            return None
            
        social_verif = content.visual_analysis.get('social_verification')
        if not social_verif or not social_verif.get('is_verified'):
            return None
            
        platform = social_verif.get('platform', 'social media')
        evidence = social_verif.get('evidence', 'Visual analysis detected verification badge')
        
        logger.info(f"Visual verification found for {content.content_id} on {platform}")
        
        return {
            "claim": f"Account is verified on {platform}",
            "status": "SUPPORTED",
            "confidence": 0.95,
            "reasoning": f"Visual Analysis confirmed verification badge: {evidence}",
            "source": "visual_analysis"
        }

    def _extract_claims(self, content: NormalizedContent) -> List[str]:
        """Extract 3-5 key factual claims from content.
        
        For brand-owned content (ecommerce, D2C), first-party product data
        (prices, specs, inventory) is excluded from extraction since the
        brand IS the authoritative source for this data.
        """
        # Check if content is from brand-owned source
        source_type = getattr(content, 'source_type', 'unknown')
        is_brand_owned = source_type.lower() in ('brand_owned', 'brand-owned', 'owned')
        
        if is_brand_owned:
            logger.info(f"Brand-owned content detected for {content.content_id} - excluding first-party product data from claims")
        
        prompt = build_claim_extraction_prompt(content.body, is_brand_owned=is_brand_owned)
        
        try:
            response = self.llm_client.client.chat(
                model=self.llm_client.model,
                messages=[
                    {"role": "system", "content": CLAIM_EXTRACTION_SYSTEM},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            result = json.loads(response.get('content', '{}'))
            claims = [c.strip() for c in result.get('claims', []) if c and c.strip()]
            return claims[:5]
        except Exception as e:
            logger.error(f"Claim extraction failed: {e}")
            return []

    def _verify_claims_parallel(self, claims: List[str]) -> List[Dict[str, Any]]:
        """Verify multiple claims in parallel."""
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(self._verify_single_claim, c): c for c in claims}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    claim = futures[future]
                    logger.error(f"Verification failed for '{claim}': {e}")
                    results.append({
                        "claim": claim,
                        "status": "UNVERIFIED",
                        "confidence": 0.5,
                        "reasoning": f"Verification error: {str(e)}"
                    })
        return results

    def _verify_single_claim(self, claim: str) -> Dict[str, Any]:
        """Search for evidence and verify a single claim."""
        try:
            search_results = search_serper(claim, size=3)
        except Exception as e:
            logger.warning(f"Search failed for '{claim}': {e}")
            search_results = []
        
        if not search_results:
            return {
                "claim": claim,
                "status": "UNVERIFIED",
                "confidence": 0.9,
                "reasoning": "No search results found."
            }
            
        context = "\n".join([
            f"- [{r['title']}]({r['url']}): {r['snippet']}" 
            for r in search_results
        ])
        
        prompt = build_verification_prompt(claim, context)
        
        try:
            response = self.llm_client.client.chat(
                model=self.llm_client.model,
                messages=[
                    {"role": "system", "content": VERIFICATION_SYSTEM},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            result = json.loads(response.get('content', '{}'))
            result['claim'] = claim
            result['evidence'] = context
            result['status'] = result.get('status', 'UNVERIFIED').upper()
            result['confidence'] = min(1.0, max(0.0, float(result.get('confidence', 0.5))))
            
            if result['status'] not in ['SUPPORTED', 'CONTRADICTED', 'UNVERIFIED']:
                result['status'] = 'UNVERIFIED'
            return result
        except Exception as e:
            logger.error(f"Verification failed for '{claim}': {e}")
            return {"claim": claim, "status": "UNVERIFIED", "confidence": 0.5}

    def _aggregate_results(self, verified_claims: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate final score and format issues."""
        if not verified_claims:
            return {'score': 0.5, 'issues': []}
            
        supported = sum(1 for c in verified_claims if c.get('status') == 'SUPPORTED')
        contradicted = sum(1 for c in verified_claims if c.get('status') == 'CONTRADICTED')
        unverified = sum(1 for c in verified_claims if c.get('status') == 'UNVERIFIED')
        
        score = 0.5 + (supported * 0.1) - (contradicted * 0.2) - (unverified * 0.05)
        score = min(1.0, max(0.0, score))
        
        issues = []
        for c in verified_claims:
            status = c.get('status', 'UNVERIFIED')
            if status == 'CONTRADICTED':
                issues.append({
                    "type": "unverified_claims",
                    "confidence": c.get('confidence', 0.8),
                    "severity": "high",
                    "evidence": f"Claim: '{c['claim']}'\nVerdict: CONTRADICTED\n{c.get('reasoning', '')}",
                    "suggestion": f"Remove or correct this claim: {c.get('reasoning', '')}"
                })
            elif status == 'UNVERIFIED':
                issues.append({
                    "type": "unverified_claims",
                    "confidence": 0.8,
                    "severity": "medium",
                    "evidence": f"Claim: '{c['claim']}'\nVerdict: UNVERIFIED\n{c.get('reasoning', '')}",
                    "suggestion": "Add a citation or source for this claim."
                })
            
        return {
            'score': score,
            'issues': issues,
            'meta': {'total': len(verified_claims), 'supported': supported, 
                     'contradicted': contradicted, 'unverified': unverified,
                     'details': verified_claims}
        }
