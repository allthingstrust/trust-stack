"""
Trust Stack Prompts Module

Centralized prompt templates and few-shot examples for all LLM interactions.
Separating prompts from code enables:
- Independent version control of prompts
- A/B testing of prompt variants
- Non-developer prompt iteration
- Easier auditing and review
"""

from prompts.verification import (
    CLAIM_EXTRACTION_SYSTEM,
    CLAIM_EXTRACTION_EXAMPLES,
    VERIFICATION_SYSTEM,
    VERIFICATION_EXAMPLES,
)

from prompts.scoring import (
    SCORING_SYSTEM,
    SCORING_EXAMPLES,
    DIMENSION_ISSUE_TYPES,
    FEEDBACK_EXAMPLES_LOW_SCORE,
    FEEDBACK_EXAMPLES_HIGH_SCORE,
)

from prompts.classification import (
    CLASSIFICATION_SYSTEM,
    CLASSIFICATION_EXAMPLES,
)

from prompts.summarization import (
    SUMMARIZATION_EXAMPLES,
)

__all__ = [
    # Verification
    'CLAIM_EXTRACTION_SYSTEM',
    'CLAIM_EXTRACTION_EXAMPLES',
    'VERIFICATION_SYSTEM',
    'VERIFICATION_EXAMPLES',
    # Scoring
    'SCORING_SYSTEM',
    'SCORING_EXAMPLES',
    'DIMENSION_ISSUE_TYPES',
    'FEEDBACK_EXAMPLES_LOW_SCORE',
    'FEEDBACK_EXAMPLES_HIGH_SCORE',
    # Classification
    'CLASSIFICATION_SYSTEM',
    'CLASSIFICATION_EXAMPLES',
    # Summarization
    'SUMMARIZATION_EXAMPLES',
]
