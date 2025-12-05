"""
Scoring Contract
Defines what the scoring system is allowed to do, what inputs it accepts,
and what outputs it must produce.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# 1. Allowed Inputs
# The scorer must ONLY use these inputs. No "hallucinated" context.
@dataclass
class ScoringInput:
    content_items: List[Dict[str, Any]]  # Normalized content items
    brand_metadata: Dict[str, Any]       # Known brand info (domains, handles)
    user_config: Dict[str, Any]          # User preferences (weights, enabled signals)
    
    # Optional inputs for future expansion
    screenshots: Optional[List[str]] = None
    human_annotations: Optional[Dict[str, Any]] = None

# 2. Required Outputs
# The scorer MUST produce a TrustScore object.
# See scoring.types.TrustScore

# 3. Constraints & Guardrails
# Explicit rules for what the scorer cannot do.
CONSTRAINTS = [
    "Do not award high personalization scores without explicit signals (e.g., login, location request).",
    "Do not infer 'trust' solely from brand reputation; rely on observed signals.",
    "Do not hallucinate missing metadata (e.g., authors, dates) if not present in content.",
    "Scores must be accompanied by evidence (snippets, URLs) whenever possible.",
    "Confidence must be lowered if critical signals are missing (e.g., no privacy policy found)."
]

def validate_input(input_data: ScoringInput) -> bool:
    """Validate that input meets the contract requirements"""
    if not input_data.content_items:
        return False
    return True
