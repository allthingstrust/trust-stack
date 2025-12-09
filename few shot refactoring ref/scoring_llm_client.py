"""
LLM Scoring Client for Trust Stack Rating Tool

Centralizes all LLM API interactions for content scoring.
Prompts are imported from the centralized prompts module.
"""

from typing import Dict, Any
import logging
import json
import re

from config.settings import APIConfig
from data.models import NormalizedContent
from scoring.llm_client import ChatClient

from prompts.scoring import (
    SCORING_SYSTEM,
    SCORING_EXAMPLES,
    build_feedback_prompt_low_score,
    build_feedback_prompt_high_score,
)

logger = logging.getLogger(__name__)


class LLMScoringClient:
    """Client for LLM-based content scoring."""
    
    def __init__(self, model: str = "gpt-4o"):
        self.client = ChatClient(
            api_key=APIConfig.openai_api_key,
            anthropic_api_key=APIConfig.anthropic_api_key,
            google_api_key=APIConfig.google_api_key,
            deepseek_api_key=APIConfig.deepseek_api_key,
            default_model=model
        )
        self.model = model

    def get_score(self, prompt: str) -> float:
        """Get a simple numeric score from LLM."""
        enhanced_prompt = f"""{SCORING_EXAMPLES}

Based on the examples above, score the following content.
Respond with ONLY a single decimal number between 0.0 and 1.0.

{prompt}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SCORING_SYSTEM + " Respond with only a number."},
                    {"role": "user", "content": enhanced_prompt}
                ],
                max_tokens=10,
                temperature=0.1
            )
            score_text = response.get('content', '').strip()
            match = re.search(r'(\d+\.?\d*)', score_text)
            if match:
                return min(1.0, max(0.0, float(match.group(1))))
            return 0.5
        except Exception as e:
            logger.error(f"LLM scoring error: {e}")
            return 0.5

    def get_score_with_reasoning(self, prompt: str) -> Dict[str, Any]:
        """Get score AND reasoning from LLM with structured JSON output."""
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SCORING_SYSTEM + " Respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.1
            )
            result = self._parse_json_response(response.get('content', ''))
            score = min(1.0, max(0.0, float(result.get('score', 0.5))))
            issues = result.get('issues', []) if isinstance(result.get('issues'), list) else []
            return {'score': score, 'issues': issues}
        except Exception as e:
            logger.error(f"LLM structured scoring error: {e}")
            return {'score': 0.5, 'issues': []}

    def get_score_with_feedback(
        self, 
        score_prompt: str, 
        content: NormalizedContent,
        dimension: str, 
        context_guidance: str = ""
    ) -> Dict[str, Any]:
        """Two-step LLM scoring: Get score first, then get feedback based on score."""
        score = self.get_score(score_prompt)
        logger.debug(f"{dimension} base score: {score:.2f}")
        
        # Build appropriate feedback prompt based on score
        if score < 0.9:
            feedback_prompt = build_feedback_prompt_low_score(
                score=score,
                dimension=dimension,
                title=content.title,
                body=content.body,
                context_guidance=context_guidance
            )
        else:
            feedback_prompt = build_feedback_prompt_high_score(
                score=score,
                dimension=dimension,
                title=content.title,
                body=content.body,
                context_guidance=context_guidance
            )
        
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SCORING_SYSTEM + " Respond with valid JSON."},
                    {"role": "user", "content": feedback_prompt}
                ],
                max_tokens=600,
                temperature=0.3
            )
            feedback_data = self._parse_json_response(response.get('content', ''))
            issues = self._validate_issues(feedback_data.get('issues', []), content.body)
            return {'score': score, 'issues': issues}
        except Exception as e:
            logger.error(f"LLM feedback error for {dimension}: {e}")
            return {'score': score, 'issues': []}

    def _validate_issues(self, issues: list, content_body: str) -> list:
        """Validate issues to ensure quality."""
        validated = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            if not all(k in issue for k in ['type', 'evidence', 'suggestion']):
                continue
            issue.setdefault('confidence', 0.8)
            issue.setdefault('severity', 'medium')
            validated.append(issue)
        return validated

    def _parse_json_response(self, response_text: str) -> dict:
        """Parse JSON from LLM response."""
        response_text = response_text.strip()
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass
        
        if '```' in response_text:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        
        match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    def generate(self, prompt: str, model: str = None, max_tokens: int = 500, temperature: float = 0.3) -> str:
        """Generate text response from LLM."""
        try:
            response = self.client.chat(
                model=model or self.model,
                messages=[
                    {"role": "system", "content": SCORING_SYSTEM},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.get('content', '').strip()
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return ""
