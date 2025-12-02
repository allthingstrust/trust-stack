
import logging
from typing import Dict, Any, Iterable, List, Optional, Tuple
from data.models import NormalizedContent

logger = logging.getLogger(__name__)

class TriageScorer:
    """
    Stage 1 Scorer: Fast, rule-based triage to filter out irrelevant content
    before sending it to the expensive Stage 2 (LLM) scorer.
    """
    
    def __init__(self):
        pass
        
    def should_score(self, content: NormalizedContent) -> Tuple[bool, str, float]:
        """
        Determine if content should be scored by the LLM.
        
        Args:
            content: The content item to evaluate
            
        Returns:
            Tuple containing:
            - should_score (bool): True if content needs LLM scoring, False if it should be skipped
            - reason (str): Reason for the decision
            - default_score (float): Default score to assign if skipped (usually 0.5)
        """
        # Rule 1: Length Check
        # Skip very short content (likely navigation, buttons, or empty pages)
        if not content.body or len(content.body.strip()) < 100:
            return False, "Content too short (< 100 chars)", 0.5
            
        # Rule 2: Keyword Check for Functional Pages
        # Skip Login / Sign Up / Cart pages if they don't have substantial content
        title_lower = content.title.lower() if content.title else ""
        functional_keywords = ['login', 'sign in', 'sign up', 'register', 'cart', 'checkout', 'forgot password']
        
        if any(kw in title_lower for kw in functional_keywords):
            # If it's a functional page AND has relatively short content, skip it
            if len(content.body.strip()) < 300:
                return False, f"Functional page detected: {content.title}", 0.5
                
        # Rule 3: Error Pages
        # Skip 404s, 500s, etc. that might have been indexed
        error_keywords = ['404', 'page not found', 'internal server error', 'access denied']
        if any(kw in title_lower for kw in error_keywords):
             return False, f"Error page detected: {content.title}", 0.5
             
        # Default: Content passes triage
        return True, "Passed triage", 0.0


def _word_count(text: str) -> int:
    return len(text.split())


def triage_score_item(content: Any, brand_keywords: Iterable[str]) -> float:
    """Score a content item between 0 and 1 using lightweight heuristics.

    The scorer intentionally favors recall over precision to ensure potentially
    relevant items are not prematurely filtered out before LLM analysis.
    """

    body = getattr(content, "body", "") or ""
    title = getattr(content, "title", "") or ""

    body_lower = body.lower()
    title_lower = title.lower()
    keywords = [kw.lower() for kw in brand_keywords]

    score = 0.5  # neutral baseline

    # Boost if any brand keyword appears in the title or body.
    if keywords and any(kw in body_lower or kw in title_lower for kw in keywords):
        score += 0.2

    # Reward longer, information-rich content and lightly penalize very short text.
    word_len = _word_count(body)
    if word_len < 30:
        score -= 0.1
    elif word_len > 80:
        score += 0.1

    # Ensure score stays in [0, 1]
    return max(0.0, min(1.0, score))


def triage_filter(
    contents: Iterable[Any],
    brand_keywords: Iterable[str],
    promote_threshold: float = 0.6,
) -> Tuple[List[Any], List[Any]]:
    """Split content into promoted and demoted buckets based on triage score."""

    promoted: List[Any] = []
    demoted: List[Any] = []

    for content in contents:
        score = triage_score_item(content, brand_keywords)
        if score >= promote_threshold:
            promoted.append(content)
        else:
            demoted.append(content)

    return promoted, demoted
