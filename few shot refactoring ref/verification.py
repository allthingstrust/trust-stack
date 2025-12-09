"""
Verification Prompts

Prompts for claim extraction and fact-checking verification.
"""

# =============================================================================
# CLAIM EXTRACTION
# =============================================================================

CLAIM_EXTRACTION_SYSTEM = """You are a precise fact-checker specializing in extracting verifiable claims from content.

Your task: Extract 3-5 key FACTUAL claims that can be independently verified through external sources.

EXTRACT claims that are:
- Statistics and quantifiable data points
- Specific events, dates, or timelines  
- Absolute/superlative statements ("first", "only", "largest", "best-selling")
- Citations of studies, reports, or external sources
- Named partnerships, certifications, or awards

DO NOT extract:
- Subjective opinions or value judgments
- Generic marketing language ("great service", "high quality")
- Self-referential statements that can't be externally verified
- Common knowledge facts
- Future predictions or intentions

Output format: Return ONLY a JSON object with a "claims" array containing string claims."""

CLAIM_EXTRACTION_EXAMPLES = """
<example_1>
<content>
Acme Corp, founded in 2015, has grown to serve over 2 million customers worldwide. Our patented AI technology, developed in partnership with MIT, reduces processing time by 87%. We were named the #1 enterprise solution by Gartner in 2023.
</content>
<output>
{"claims": ["Acme Corp was founded in 2015", "Acme Corp serves over 2 million customers worldwide", "Acme Corp has a partnership with MIT for AI technology development", "Acme Corp's technology reduces processing time by 87%", "Acme Corp was named #1 enterprise solution by Gartner in 2023"]}
</output>
</example_1>

<example_2>
<content>
We offer the best customer service in the industry with our amazing team. Our software is easy to use and loved by thousands. Contact us today for a free demo!
</content>
<output>
{"claims": []}
</output>
<reasoning>No verifiable factual claims - only subjective marketing statements.</reasoning>
</example_2>

<example_3>
<content>
According to a 2022 Harvard Business Review study, remote workers are 13% more productive. Our platform, used by Fortune 500 companies including Microsoft and Google, integrates with over 200 tools. Last quarter, we processed $4.2 billion in transactions.
</content>
<output>
{"claims": ["A 2022 Harvard Business Review study found remote workers are 13% more productive", "Microsoft uses this platform", "Google uses this platform", "The platform integrates with over 200 tools", "The platform processed $4.2 billion in transactions last quarter"]}
</output>
</example_3>
"""

# =============================================================================
# CLAIM VERIFICATION
# =============================================================================

VERIFICATION_SYSTEM = """You are a strict fact-checker. Evaluate claims against provided search evidence.

Classification criteria:
- SUPPORTED: Search results directly confirm the claim with matching facts/figures
- CONTRADICTED: Search results provide conflicting information that disproves the claim
- UNVERIFIED: Search results are irrelevant, outdated, or insufficient to confirm/deny

Confidence scoring:
- 0.9-1.0: Multiple authoritative sources confirm/contradict
- 0.7-0.9: Single authoritative source or multiple secondary sources
- 0.5-0.7: Partial evidence or less authoritative sources
- Below 0.5: Weak or tangential evidence

Always cite specific sources in your reasoning. Output valid JSON only."""

VERIFICATION_EXAMPLES = """
<example_1>
<claim>"Tesla delivered 1.8 million vehicles in 2023"</claim>
<search_results>
- [Tesla Q4 2023 Report](https://ir.tesla.com): Tesla achieved record deliveries of 1,808,581 vehicles in 2023
- [Reuters](https://reuters.com): Tesla reported full-year deliveries of 1.81 million vehicles
</search_results>
<output>
{"status": "SUPPORTED", "confidence": 0.95, "reasoning": "Multiple authoritative sources (Tesla's official investor relations and Reuters) confirm approximately 1.8 million vehicle deliveries in 2023."}
</output>
</example_1>

<example_2>
<claim>"Company X was founded in 2010"</claim>
<search_results>
- [Crunchbase](https://crunchbase.com): Company X founded in 2012 by John Smith
- [LinkedIn](https://linkedin.com): Company X - Founded 2012
</search_results>
<output>
{"status": "CONTRADICTED", "confidence": 0.90, "reasoning": "Both Crunchbase and LinkedIn indicate Company X was founded in 2012, not 2010 as claimed."}
</output>
</example_2>

<example_3>
<claim>"Our app reduces anxiety by 47%"</claim>
<search_results>
- [App Store](https://apps.apple.com): Meditation app with 4.5 star rating
- [TechCrunch](https://techcrunch.com): Wellness app raises $10M Series A
</search_results>
<output>
{"status": "UNVERIFIED", "confidence": 0.85, "reasoning": "Search results discuss the app's popularity and funding but contain no clinical data or studies to verify the specific 47% anxiety reduction claim."}
</output>
</example_3>
"""

# =============================================================================
# PROMPT BUILDERS
# =============================================================================

def build_claim_extraction_prompt(content_body: str, max_chars: int = 3000) -> str:
    """Build the complete claim extraction prompt with few-shot examples."""
    return f"""{CLAIM_EXTRACTION_EXAMPLES}

Now extract verifiable claims from this content:

<content>
{content_body[:max_chars]}
</content>

Return ONLY a JSON object with a "claims" array:"""


def build_verification_prompt(claim: str, search_context: str) -> str:
    """Build the complete verification prompt with few-shot examples."""
    return f"""{VERIFICATION_EXAMPLES}

Now verify this claim:

<claim>"{claim}"</claim>

<search_results>
{search_context}
</search_results>

Return JSON with status, confidence, and reasoning:"""
