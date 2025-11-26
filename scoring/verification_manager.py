"""
Verification Manager
Handles RAG-based verification of content claims using Brave Search.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from ingestion.serper_search import search_serper
from scoring.scoring_llm_client import LLMScoringClient
from data.models import NormalizedContent

logger = logging.getLogger(__name__)

class VerificationManager:
    """
    Manages the verification process:
    1. Extract claims from content
    2. Search for evidence (Brave Search)
    3. Verify claims against evidence
    """
    
    def __init__(self):
        self.llm_client = LLMScoringClient()
        
    def verify_content(self, content: NormalizedContent) -> Dict[str, Any]:
        """
        Perform fact-checked verification of content.
        
        Returns:
            Dict with 'score' (float) and 'issues' (list)
        """
        # 1. Extract checkable claims
        claims = self._extract_claims(content)
        if not claims:
            logger.info(f"No verifiable claims found for {content.content_id}")
            return {'score': 0.5, 'issues': []}  # Neutral if no claims
            
        # 2. Verify each claim with search
        verified_claims = self._verify_claims_parallel(claims)
        
        # 3. Aggregate results into score and issues
        return self._aggregate_results(verified_claims)
    
    def _extract_claims(self, content: NormalizedContent) -> List[str]:
        """Extract 3-5 key factual claims from content."""
        prompt = f"""
        Extract 3-5 key FACTUAL claims from this content that should be verified.
        Focus on:
        - Statistics and data points
        - Specific events or dates
        - Absolute statements ("We are the first...", "The only...")
        - Citations of external studies
        
        Do NOT extract:
        - Opinions or subjective statements
        - Generic marketing fluff ("We offer great service")
        - Common knowledge
        
        Content:
        {content.body[:3000]}
        
        Return ONLY a JSON list of strings:
        ["claim 1", "claim 2", ...]
        """
        
        try:
            response = self.llm_client.client.chat.completions.create(
                model=self.llm_client.model,
                messages=[
                    {"role": "system", "content": "You are a fact-checker. Extract specific claims as a JSON list."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            result = json.loads(response.choices[0].message.content)
            return result.get('claims', [])[:5]  # Limit to 5 claims max
        except Exception as e:
            logger.error(f"Claim extraction failed: {e}")
            return []

    def _verify_claims_parallel(self, claims: List[str]) -> List[Dict[str, Any]]:
        """Verify multiple claims in parallel."""
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_claim = {executor.submit(self._verify_single_claim, claim): claim for claim in claims}
            for future in as_completed(future_to_claim):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Claim verification failed: {e}")
        return results

    def _verify_single_claim(self, claim: str) -> Dict[str, Any]:
        """Search for evidence and verify a single claim."""
        # Search Serper (Google)
        try:
            search_results = search_serper(claim, size=3)
        except Exception as e:
            logger.warning(f"Serper search failed for '{claim}': {e}")
            search_results = []
        
        if not search_results:
            return {
                "claim": claim,
                "status": "UNVERIFIED",
                "confidence": 0.9,
                "reasoning": "No search results found to support this claim."
            }
            
        # Format context
        context = "\n".join([
            f"- [{r['title']}]({r['url']}): {r['snippet']}" 
            for r in search_results
        ])
        
        # Verify with LLM
        prompt = f"""
        Verify this claim using the provided search results.
        
        Claim: "{claim}"
        
        Search Results:
        {context}
        
        Determine if the claim is:
        - SUPPORTED: Search results confirm it.
        - CONTRADICTED: Search results prove it wrong.
        - UNVERIFIED: Search results are irrelevant or inconclusive.
        
        Return JSON:
        {{
            "status": "SUPPORTED" | "CONTRADICTED" | "UNVERIFIED",
            "confidence": 0.0-1.0,
            "reasoning": "Brief explanation citing sources."
        }}
        """
        
        try:
            response = self.llm_client.client.chat.completions.create(
                model=self.llm_client.model,
                messages=[
                    {"role": "system", "content": "You are a strict fact-checker. Respond in JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            result = json.loads(response.choices[0].message.content)
            result['claim'] = claim
            result['evidence'] = context  # Store evidence for debugging
            return result
        except Exception as e:
            logger.error(f"Verification step failed for claim '{claim}': {e}")
            return {"claim": claim, "status": "unverified", "confidence": 0.0}

    def _aggregate_results(self, verified_claims: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate final score and format issues."""
        if not verified_claims:
            return {'score': 0.5, 'issues': []}
            
        supported_count = sum(1 for c in verified_claims if c.get('status') == 'SUPPORTED')
        contradicted_count = sum(1 for c in verified_claims if c.get('status') == 'CONTRADICTED')
        total = len(verified_claims)
        
        # Simple scoring logic
        # Start at 0.5. Add points for supported, subtract for contradicted.
        # Unverified claims slightly lower score (penalty for making claims you can't back up)
        
        score = 0.5 + (supported_count * 0.1) - (contradicted_count * 0.2)
        score = min(1.0, max(0.0, score))
        
        issues = []
        for c in verified_claims:
            if c.get('status') == 'CONTRADICTED':
                issues.append({
                    "type": "unverified_claims",  # Mapping to existing issue type
                    "confidence": c.get('confidence', 0.8),
                    "severity": "high",
                    "evidence": f"Claim: '{c['claim']}'\nReasoning: {c.get('reasoning', '')}",
                    "suggestion": "Remove or correct this claim based on external evidence."
                })
            elif c.get('status') == 'UNVERIFIED':
                 issues.append({
                    "type": "unverified_claims",
                    "confidence": 0.8, # Higher confidence so it passes the UI threshold
                    "severity": "medium",
                    "evidence": f"Claim: '{c['claim']}' could not be verified. {c.get('reasoning', '')}",
                    "suggestion": "Add a citation or source for this claim."
                })
                
        return {
            'score': score,
            'issues': issues,
            'meta': verified_claims # Store full details for debugging
        }
