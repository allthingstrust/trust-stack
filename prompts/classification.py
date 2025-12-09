"""
Classification Prompts

Prompts for content authenticity classification (authentic/suspect/inauthentic).
"""

# =============================================================================
# SYSTEM PROMPT
# =============================================================================

CLASSIFICATION_SYSTEM = """You are a content authenticity classifier for the Trust Stack framework.

Classify content into one of three categories based on trust signals:
- authentic: Genuine, trustworthy content with strong provenance and verification
- suspect: Content with mixed signals or minor concerns requiring attention
- inauthentic: Content with significant trust issues, deceptive patterns, or fabricated elements

Respond with JSON containing: label, confidence (0.0-1.0), and optional notes."""

# =============================================================================
# FEW-SHOT EXAMPLES
# =============================================================================

CLASSIFICATION_EXAMPLES = """
<classification_examples>
<example>
<item>
{"content_id": "blog-001", "meta": {"author": "John Smith, PhD", "source": "company-blog", "has_citations": true, "disclosure": "none required"}, "final_score": 82}
</item>
<o>
{"label": "authentic", "confidence": 0.9, "notes": "Strong author credentials, citations present, high overall score"}
</o>
</example>

<example>
<item>
{"content_id": "review-042", "meta": {"author": "anonymous", "source": "user-review", "has_citations": false, "engagement": "suspiciously high"}, "final_score": 45}
</item>
<o>
{"label": "suspect", "confidence": 0.75, "notes": "Anonymous author and suspicious engagement metrics warrant review despite moderate score"}
</o>
</example>

<example>
<item>
{"content_id": "article-789", "meta": {"author": "Staff Writer", "source": "unknown-domain", "has_citations": false, "ai_detected": true, "contradictions": 3}, "final_score": 28}
</item>
<o>
{"label": "inauthentic", "confidence": 0.85, "notes": "Multiple red flags: AI-generated without disclosure, no citations, internal contradictions, low trust score"}
</o>
</example>

<example>
<item>
{"content_id": "press-release-055", "meta": {"author": "Corporate Communications", "source": "official-newsroom", "has_citations": true, "disclosure": "promotional"}, "final_score": 71}
</item>
<o>
{"label": "authentic", "confidence": 0.8, "notes": "Official source with proper disclosure. Score reflects promotional nature but content is legitimate."}
</o>
</example>

<example>
<item>
{"content_id": "social-post-123", "meta": {"author": "influencer_account", "source": "instagram", "has_citations": false, "disclosure": "missing", "sponsored": true}, "final_score": 52}
</item>
<o>
{"label": "suspect", "confidence": 0.8, "notes": "Sponsored content without required disclosure. Needs FTC compliance review."}
</o>
</example>
</classification_examples>
"""

# =============================================================================
# GUIDELINES
# =============================================================================

CLASSIFICATION_GUIDELINES = """
Classification guidelines by score range:
- 75-100: Likely authentic unless metadata shows red flags
- 40-74: Suspect - review metadata carefully for determining factors  
- 0-39: Likely inauthentic unless metadata provides strong positive signals

Key red flags that override score:
- AI-generated without disclosure
- Fake engagement metrics
- Missing required sponsorship disclosures
- Multiple contradictory claims
- Fabricated citations or credentials
"""

# =============================================================================
# PROMPT BUILDER
# =============================================================================

def build_classification_prompt(item_json: str) -> str:
    """Build the complete classification prompt with few-shot examples."""
    return f"""{CLASSIFICATION_EXAMPLES}

{CLASSIFICATION_GUIDELINES}

Now classify this item:
<item>
{item_json}
</item>

Respond with JSON only: {{"label": "...", "confidence": ..., "notes": "..."}}"""
