"""
Summarization Prompts

Prompts for text summarization tasks.
"""

# =============================================================================
# FEW-SHOT EXAMPLES
# =============================================================================

SUMMARIZATION_EXAMPLES = """
<summarization_examples>
<example>
<input>
The quarterly earnings report showed significant growth across all divisions. Revenue increased 23% year-over-year to $4.2 billion, exceeding analyst expectations of $3.9 billion. The company attributed growth to strong performance in cloud services and enterprise software. Operating margins improved to 18.5% from 15.2% in the prior quarter. Management raised full-year guidance and announced a $500 million share buyback program.
</input>
<summary>
Company reports strong Q earnings with 23% revenue growth to $4.2B, beating expectations. Cloud and enterprise drove gains. Margins improved to 18.5%, prompting raised guidance and a $500M buyback.
</summary>
</example>

<example>
<input>
New research published in Nature suggests that regular consumption of fermented foods may significantly improve gut microbiome diversity. The two-year study followed 500 participants who consumed fermented foods daily versus a control group. Results showed a 40% increase in beneficial bacteria strains and reduced inflammation markers. Researchers caution that individual results may vary based on existing gut health.
</input>
<summary>
Nature study of 500 participants finds daily fermented food consumption increases beneficial gut bacteria by 40% and reduces inflammation over two years. Individual results may vary.
</summary>
</example>

<example>
<input>
The city council voted 7-2 to approve a new zoning ordinance that will allow mixed-use development in the downtown corridor. The measure, which takes effect January 1st, permits buildings up to 12 stories combining retail, office, and residential spaces. Opponents cited concerns about traffic congestion and parking, while supporters emphasized economic development potential and housing needs. Mayor Johnson called it "a transformative step for our community."
</input>
<summary>
City council approves (7-2) mixed-use zoning for downtown, allowing 12-story buildings with retail, office, and residential. Effective January 1st. Mayor calls it "transformative" despite traffic concerns from opponents.
</summary>
</example>
</summarization_examples>
"""

# =============================================================================
# PROMPT BUILDER
# =============================================================================

def build_summarization_prompt(text: str, max_words: int = 120) -> str:
    """Build a summarization prompt with few-shot examples."""
    return f"""{SUMMARIZATION_EXAMPLES}

Following the style of the examples above, write a concise {max_words}-word summary of this content.
Focus on key facts, findings, and actionable information.

<content>
{text}
</content>

Summary:"""
