"""
Scoring Prompts

Prompts for content authenticity scoring across Trust Stack dimensions.
"""

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

SCORING_SYSTEM = """You are an expert content authenticity evaluator for the Trust Stack framework.

Always respond in English, regardless of the language of the content being analyzed.
Provide objective, evidence-based assessments.
When scoring, use the full 0.0-1.0 range appropriately."""

# =============================================================================
# NUMERIC SCORING EXAMPLES
# =============================================================================

SCORING_EXAMPLES = """
<scoring_examples>
<example dimension="coherence" score="0.92">
Content maintains consistent professional tone throughout. Brand voice is unified. Minor improvement: one CTA uses generic phrasing.
</example>
<example dimension="coherence" score="0.45">
Tone shifts dramatically between sections - formal legal language mixed with casual slang. Multiple contradictory claims about product capabilities.
</example>
<example dimension="transparency" score="0.88">
Clear authorship, publication date, and source citations. Missing: specific methodology for cited statistics.
</example>
<example dimension="transparency" score="0.35">
No author attribution. Multiple statistics without sources. Sponsored content not disclosed.
</example>
</scoring_examples>
"""

# =============================================================================
# DIMENSION ISSUE TYPES
# =============================================================================

DIMENSION_ISSUE_TYPES = {
    'coherence': {
        'types': [
            ('inconsistent_voice', 'Voice/tone varies inappropriately across content sections'),
            ('vocabulary', 'Word choice issues, jargon inconsistency, or terminology mismatches'),
            ('tone_shift', 'Abrupt changes in formality, style, or emotional register'),
            ('contradictory_claims', 'Conflicting statements within the same content'),
            ('broken_links', 'Non-functional or dead links')
        ],
        'guidance': """
IMPORTANT for Coherence scoring:
- Different capitalization between HEADLINE and body text is INTENTIONAL design, not a tone shift
- Product listings may have repeated similar text - this is INTENTIONAL structure
- Only flag tone shifts WITHIN the same semantic element type
- Footer text naturally differs from body - this is EXPECTED"""
    },
    'verification': {
        'types': [
            ('unverified_claims', 'Factual statements without supporting sources or citations'),
            ('fake_engagement', 'Suspicious metrics, inflated numbers, or fabricated testimonials'),
            ('unlabeled_ads', 'Promotional content not clearly disclosed as advertising')
        ],
        'guidance': """
IMPORTANT for Verification scoring:
- Focus on claims that CAN be externally verified
- Distinguish between opinions (not verifiable) and facts (verifiable)
- Statistics and data points require sources"""
    },
    'transparency': {
        'types': [
            ('missing_privacy_policy', 'No privacy policy link or disclosure'),
            ('no_ai_disclosure', 'AI-generated content not disclosed'),
            ('missing_data_source_citations', 'Data claims without source attribution'),
            ('hidden_sponsored_content', 'Sponsored/paid content not clearly labeled')
        ],
        'guidance': """
IMPORTANT for Transparency scoring:
- Check for author attribution and credentials
- Verify date/timestamp presence
- Look for disclosure of conflicts of interest
- Assess clarity of data sourcing"""
    },
    'provenance': {
        'types': [
            ('unclear_authorship', 'Author not identified or credentials unclear'),
            ('missing_metadata', 'Incomplete publication metadata'),
            ('no_schema_markup', 'Missing structured data for search engines')
        ],
        'guidance': """
IMPORTANT for Provenance scoring:
- Evaluate author credibility indicators
- Check for organizational attribution
- Assess content origin clarity"""
    },
    'resonance': {
        'types': [
            ('poor_readability', 'Content difficult to read or comprehend'),
            ('inappropriate_tone', 'Tone mismatched to target audience or purpose')
        ],
        'guidance': """
IMPORTANT for Resonance scoring:
- Consider target audience appropriateness
- Evaluate reading level match
- Assess engagement quality"""
    }
}

# =============================================================================
# FEEDBACK EXAMPLES - LOW SCORES
# =============================================================================

FEEDBACK_EXAMPLES_LOW_SCORE = """
<feedback_examples>
<example dimension="coherence" score="0.65">
<content_excerpt>
We offer enterprise-grade solutions for Fortune 500 companies. Hey there! Looking for something cool? Our stuff is totally awesome and super affordable!! Contact our sales team for a customized proposal.
</content_excerpt>
<good_response>
{"issues": [{"type": "tone_shift", "confidence": 0.9, "severity": "high", "evidence": "EXACT QUOTE: 'Hey there! Looking for something cool? Our stuff is totally awesome and super affordable!!'", "suggestion": "Tone inconsistency: The casual, exclamatory language clashes with the formal enterprise positioning. Change 'Hey there! Looking for something cool? Our stuff is totally awesome and super affordable!!' → 'Discover solutions designed to meet your organization's unique requirements at competitive price points.' This improves coherence by maintaining consistent professional tone."}]}
</good_response>
</example>

<example dimension="transparency" score="0.55">
<content_excerpt>
Studies show that 87% of users prefer our product. Our revolutionary technology is backed by leading research institutions.
</content_excerpt>
<good_response>
{"issues": [{"type": "missing_data_source_citations", "confidence": 0.95, "severity": "high", "evidence": "EXACT QUOTE: 'Studies show that 87% of users prefer our product'", "suggestion": "Missing citation: The statistic lacks source attribution. Change 'Studies show that 87% of users prefer our product' → 'According to a 2024 CustomerSat survey of 1,200 users, 87% prefer our product (source: customersat.com/report-2024).' This improves transparency by providing verifiable sourcing."}]}
</good_response>
</example>

<example dimension="verification" score="0.50">
<content_excerpt>
We are the world's first company to use quantum computing for customer service. Our patented AI has won multiple industry awards.
</content_excerpt>
<good_response>
{"issues": [{"type": "unverified_claims", "confidence": 0.9, "severity": "high", "evidence": "EXACT QUOTE: 'We are the world's first company to use quantum computing for customer service'", "suggestion": "Unsubstantiated superlative: 'First' claims require documentation. Change 'We are the world's first company to use quantum computing for customer service' → 'We are among the early adopters of quantum computing applications in customer service' OR provide dated documentation proving the 'first' claim. This improves verification by avoiding unprovable absolutes."}]}
</good_response>
</example>
</feedback_examples>
"""

# =============================================================================
# FEEDBACK EXAMPLES - HIGH SCORES
# =============================================================================

FEEDBACK_EXAMPLES_HIGH_SCORE = """
<optimization_examples>
<example dimension="coherence" score="0.93">
<content_excerpt>
Explore ALL PRODUCTS in our collection. Our team of experts carefully curates each item to ensure quality and authenticity.
</content_excerpt>
<good_response>
{"issues": [{"type": "improvement_opportunity", "confidence": 0.7, "severity": "low", "evidence": "EXACT QUOTE: 'Explore ALL PRODUCTS'", "suggestion": "CTA Specificity: Generic all-caps CTA could be more descriptive and brand-aligned. Change 'Explore ALL PRODUCTS' → 'Discover Our Curated Collection'. This enhances coherence by using descriptive language that matches the quality-focused messaging elsewhere."}]}
</good_response>
</example>

<example dimension="transparency" score="0.91">
<content_excerpt>
Last updated: Recently. Author: Marketing Team.
</content_excerpt>
<good_response>
{"issues": [{"type": "improvement_opportunity", "confidence": 0.75, "severity": "low", "evidence": "EXACT QUOTE: 'Last updated: Recently'", "suggestion": "Timestamp Precision: Vague time reference reduces transparency. Change 'Last updated: Recently' → 'Last updated: December 9, 2024'. This improves transparency by providing specific, verifiable date information."}]}
</good_response>
</example>
</optimization_examples>
"""

# =============================================================================
# PROMPT BUILDERS
# =============================================================================

def get_issue_types_formatted(dimension: str) -> str:
    """Get formatted issue types for a dimension."""
    dim_config = DIMENSION_ISSUE_TYPES.get(dimension.lower(), {})
    types = dim_config.get('types', [('improvement_opportunity', 'General improvement')])
    return '\\n'.join(f"  - {t[0]}: {t[1]}" for t in types)


def get_dimension_guidance(dimension: str) -> str:
    """Get dimension-specific guidance."""
    dim_config = DIMENSION_ISSUE_TYPES.get(dimension.lower(), {})
    return dim_config.get('guidance', '')


def build_feedback_prompt_low_score(
    score: float,
    dimension: str,
    title: str,
    body: str,
    context_guidance: str = "",
    max_body_chars: int = 5000
) -> str:
    """Build feedback prompt for low/medium scores (< 0.9)."""
    types_formatted = get_issue_types_formatted(dimension)
    dim_guidance = get_dimension_guidance(dimension)
    
    return f"""You scored this content's {dimension} as {score:.2f}/1.0.

{context_guidance}
{dim_guidance}

{FEEDBACK_EXAMPLES_LOW_SCORE}

Now analyze this content and identify specific issues:

<content>
Title: {title}
Body: {body[:max_body_chars]}
</content>

VALID ISSUE TYPES for {dimension.upper()}:
{types_formatted}

REQUIREMENTS:
1. Use ONLY issue types listed above
2. evidence field: Must contain "EXACT QUOTE: 'actual text from content'" - the quoted text MUST appear in the content
3. suggestion field format: "[Problem Type]: [Why it's problematic]. Change '[original text]' → '[improved text]'. This improves {dimension} because [reason]."
4. Only report issues with specific evidence from the content
5. Maximum 3 issues, prioritized by severity

Respond with JSON:
{{"issues": [...]}}"""


def build_feedback_prompt_high_score(
    score: float,
    dimension: str,
    title: str,
    body: str,
    context_guidance: str = "",
    max_body_chars: int = 5000
) -> str:
    """Build feedback prompt for high scores (>= 0.9)."""
    is_very_high = score >= 0.95
    
    instruction = "ONE minor optimization tip" if is_very_high else "1-2 improvements that would push the score higher"
    
    return f"""You scored this content's {dimension} as {score:.2f}/1.0 - {"excellent" if is_very_high else "good"}!

{context_guidance}
{get_dimension_guidance(dimension)}

{FEEDBACK_EXAMPLES_HIGH_SCORE}

Provide {instruction} for this content:

<content>
Title: {title}
Body: {body[:max_body_chars]}
</content>

REQUIREMENTS:
1. Use type "improvement_opportunity"
2. evidence: "EXACT QUOTE: 'actual text from content'"
3. suggestion: "[Aspect]: [Brief explanation]. Change '[original]' → '[improved]'. This enhances [benefit]."
4. If no meaningful improvements, return {{"issues": []}}

Respond with JSON:
{{"issues": [...]}}"""
