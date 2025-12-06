"""
Trust Stack Report Generator

This module generates the detailed "Trust Stack" analysis section of the report,
matching the specific format with Rationale, Key Signal Evaluation, and Diagnostics.
"""

import logging
from typing import Dict, Any, List, Optional
from scoring.llm_client import ChatClient

logger = logging.getLogger(__name__)

# Define the standard Key Signal categories for each dimension
TRUST_STACK_DIMENSIONS = {
    'provenance': {
        'signals': [
            "Authorship & Attribution",
            "Verification & Identity",
            "Brand Presence & Continuity",
            "Metadata & Technical Provenance",
            "Intent & Legitimacy"
        ]
    },
    'resonance': {
        'signals': [
            "Dynamic Personalization",
            "Cultural Fluency & Inclusion",
            "Emotional Tone & Timing",
            "Modality & Channel Continuity",
            "Opt-in & Accessible Personalization",
            "Creative Relevance"
        ]
    },
    'coherence': {
        'signals': [
            "Narrative Alignment Across Channels",
            "Behavioral Consistency",
            "Design System & Interaction Patterns",
            "Temporal Continuity",
            "Feedback Loops & Adaptive Clarity"
        ]
    },
    'transparency': {
        'signals': [
            "Plain Language Disclosures",
            "AI/ML & Automation Clarity",
            "Provenance Labeling & Source Integrity",
            "User Control & Consent Management",
            "Explainable System Behavior",
            "Trust Recovery Mechanisms"
        ]
    },

    'verification': {
        'signals': [
            "Authentic Social Proof",
            "Human Validation & Peer Endorsement",
            "Third-Party Trust Layers",
            "Moderation & Dispute Transparency",
            "Cross-Platform Reputation Consistency",
            "Secure & Tamper-Resistant Systems"
        ]
    }
}

# Define specific diagnostic metrics for each dimension
DIMENSION_DIAGNOSTICS = {
    'provenance': [
        "Author Credibility",
        "Source Attribution",
        "Domain Authority",
        "History Transparency",
        "Citation Quality"
    ],
    'resonance': [
        "Audience Connection",
        "Emotional Engagement",
        "Cultural Relevance",
        "Value Proposition",
        "Brand Voice Appeal"
    ],
    'coherence': [
        "Content Narrative Alignment",
        "Audience Engagement Clarity",
        "Brand Messaging Consistency",
        "Product Relevance Connection",
        "Overall Content Cohesion"
    ],
    'transparency': [
        "Disclosure Clarity",
        "Intent Revelation",
        "Policy Accessibility",
        "Sourcing Transparency",
        "Limitation Acknowledgement"
    ],
    'verification': [
        "Claim Accuracy",
        "Evidence Strength",
        "Peer Corroboration",
        "Fallacy Freedom",
        "Fact-Check Status"
    ]
}

def generate_trust_stack_report(report_data: Dict[str, Any], model: str = 'gpt-4o-mini') -> str:
    """
    Generate the full Trust Stack report content.
    
    Args:
        report_data: The full report data dictionary
        model: The LLM model to use
        
    Returns:
        Markdown string containing the Trust Scores section and Full Trust Audit Report
    """
    content = []
    
    # 1. Trust Scores Section (Dimension by Dimension)
    content.append("🧠 **Trust Scores**")
    
    dimension_breakdown = report_data.get('dimension_breakdown', {})
    items = report_data.get('items', [])
    sources = report_data.get('sources', [])
    
    # Iterate through dimensions in the specific order
    ordered_dims = ['provenance', 'resonance', 'coherence', 'transparency', 'verification']
    
    for dim in ordered_dims:
        dim_data = dimension_breakdown.get(dim, {})
        avg_score = (dim_data.get('average') or 0) * 10  # Convert 0-1 to 0-10, handle None
        
        # Generate detailed analysis for this dimension
        analysis = _generate_dimension_analysis(dim, avg_score, items, sources, model)
        content.append(analysis)
        content.append(" ") # Spacer
        
    # 2. Full Trust Audit Report (Executive Summary)
    audit_report = _generate_full_audit_report(report_data, model)
    content.append(audit_report)
    
    return "\n\n".join(content)

def _generate_dimension_analysis(
    dimension: str, 
    score: float, 
    items: List[Dict[str, Any]], 
    sources: List[str],
    model: str
) -> str:
    """Generate the detailed analysis for a single dimension"""
    
    signals = TRUST_STACK_DIMENSIONS.get(dimension, {}).get('signals', [])
    diagnostics = DIMENSION_DIAGNOSTICS.get(dimension, [])
    
    # Format diagnostics for prompt
    diagnostics_list = "\n".join([f"- {d}" for d in diagnostics])
    
    # Prepare context for LLM
    # We summarize the top 5 and bottom 5 items for this dimension to give the LLM concrete data
    sorted_items = sorted(items, key=lambda x: x.get('dimension_scores', {}).get(dimension, 0), reverse=True)
    top_items = sorted_items[:5]
    bottom_items = sorted_items[-5:] if len(items) > 5 else []
    
    # Deduplicate if overlap
    unique_items = []
    seen_ids = set()
    for item in top_items + bottom_items:
        # Use title or url as id if no id field
        iid = item.get('id', item.get('url', item.get('title', '')))
        if iid not in seen_ids:
            unique_items.append(item)
            seen_ids.add(iid)

    items_context = "Sample Content Items:\n"
    for item in unique_items:
        # Ensure meta is a dict
        meta = item.get('meta', {})
        if isinstance(meta, str):
            try:
                import json
                meta = json.loads(meta)
            except:
                meta = {}

        # Improved title extraction
        title = item.get('title') or meta.get('title', 'Untitled')
        item_score = (item.get('dimension_scores', {}).get(dimension) or 0) * 10
        
        # Improved URL extraction
        url = meta.get('source_url') or meta.get('url') or 'No URL'
        
        # Extract a snippet of the body content to give the LLM context
        # INCREASED CONTEXT WINDOW: 600 -> 4000 chars
        body = item.get('body', '') or meta.get('description', '')
        snippet = body[:4000].replace('\n', ' ') + "..." if body else "No content available."
                
        detected_attrs = meta.get('detected_attributes', [])
        relevant_attrs = [
            f"{attr.get('label')} ({attr.get('value')}/10)" 
            for attr in detected_attrs 
            if attr.get('dimension') == dimension
        ]
        attrs_str = ", ".join(relevant_attrs) if relevant_attrs else "None detected"

        # Get specific issues/recommendations if available
        # Note: 'issues' might be stored in different places depending on the pipeline stage
        # We check common locations
        issues = item.get('issues', []) or meta.get('issues', [])
        relevant_issues = [
            issue.get('issue', issue.get('description', '')) 
            for issue in issues 
            if issue.get('dimension') == dimension or issue.get('category') == dimension
        ]
        issues_str = "; ".join(relevant_issues[:3]) if relevant_issues else "None flagged"

        items_context += f"- [{item_score:.1f}/10] {title} ({url})\n"
        items_context += f"  Attributes: {attrs_str}\n"
        items_context += f"  Issues: {issues_str}\n"
        items_context += f"  Content Snippet: \"{snippet}\"\n"

    prompt = f"""
You are an expert Trust Stack analyst. Generate a detailed analysis for the '{dimension.title()}' dimension of a brand's content.

CONTEXT:
- Dimension: {dimension.title()}
- Overall Score: {score:.1f} / 10
- Data Sources: {', '.join(sources)}
{items_context}

REQUIRED FORMAT:
You must output the analysis in the EXACT following format. Use the provided HTML tags and markdown exactly as shown.

**{dimension.title()}**: {score:.1f} / 10

*Rationale:*

*   **[Point 1]**: [Explanation]
*   **[Point 2]**: [Explanation]
... (3-5 bullet points explaining the score)

**{dimension.upper()}**: Score: {score:.1f} / 10

🗝️ **Key Signal Evaluation**

(For each signal below, provide the status icon, the signal name as a header, bullet points, and a summary.)

{_format_signals_for_prompt_new(signals)}

🧮 **Diagnostics Snapshot**
(Create a markdown table with 2 columns: Metric, Value. Score each of the following specific metrics on a 1/10 scale based on your analysis.)

Metric | Value
--- | ---
[Metric Name] | [Score]/10

Required Metrics to Score:
{diagnostics_list}

📊 **Final {dimension.title()} Score: {score:.1f} / 10**
[A 2-3 sentence summary paragraph]

🛠️ **Recommendations to Improve {dimension.upper()}**
(Provide 3-5 concrete, actionable steps based on the **Content Snippets** and **Issues** provided above. Do NOT be generic. You MUST quote the specific content or mention the specific URL that needs improvement.)
1. [Actionable Recommendation 1 - citing specific content]
2. [Actionable Recommendation 2 - citing specific content]
3. [Actionable Recommendation 3 - citing specific content]

INSTRUCTIONS:
- Be professional, objective, and detailed.
- Use the provided score to guide the tone.
- Ensure the "Key Signal Evaluation" section covers ALL the signals listed above.
- Do NOT use headers like # or ##. Use **bold** for headers to keep font size consistent.
- CRITICAL: You MUST use the provided "Attributes" and "Issues" data in your Rationale and Key Signal Evaluation.
- CRITICAL: Recommendations must be specific and actionable. Use the provided content snippets to identify specific gaps (e.g., "The 'About' page text '...' lacks team member names"). Avoid generic advice like "Improve transparency". Instead say "Add author bylines to the blog posts at [URL]".
"""

    try:
        client = ChatClient()
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7
        )
        return response.get('content') or response.get('text') or f"Error generating analysis for {dimension}"
    except Exception as e:
        logger.error(f"Failed to generate analysis for {dimension}: {e}")
        return f"Error generating analysis for {dimension}"

def _format_signals_for_prompt(signals: List[str]) -> str:
    """Format signals for the prompt (Legacy)"""
    return "\n".join([f"{i+1}. {s}" for i, s in enumerate(signals)])

def _format_signals_for_prompt_new(signals: List[str]) -> str:
    """Format signals for the prompt (New)"""
    return "\n".join([f"{i+1}. {s}" for i, s in enumerate(signals)])

def _generate_full_audit_report(report_data: Dict[str, Any], model: str) -> str:
    """Generate the 'Full Trust Audit Report' executive summary section"""
    
    brand_id = report_data.get('brand_id', 'Unknown Brand')
    generated_at = report_data.get('generated_at', 'Unknown Date')
    
    # Calculate scores for summary
    dim_breakdown = report_data.get('dimension_breakdown', {})
    scores = {k: v.get('average', 0)*10 for k, v in dim_breakdown.items()}
    
    prompt = f"""
You are writing the "Full Trust Audit Report" executive summary.

CONTEXT:
- Brand: {brand_id}
- Date: {generated_at}
- Scores:
  - Provenance: {scores.get('provenance', 0):.1f}/10
  - Resonance: {scores.get('resonance', 0):.1f}/10
  - Coherence: {scores.get('coherence', 0):.1f}/10
  - Transparency: {scores.get('transparency', 0):.1f}/10
  - Verification: {scores.get('verification', 0):.1f}/10

REQUIRED FORMAT:

📄 Full Trust Audit Report
🔐 Trust Audit Report for {brand_id}
Generated on {generated_at}

📣 Executive Summary
[A paragraph summarizing the overall trust posture, strengths, and weaknesses.]

📊 Trust Profile Snapshot
● ✅ Provenance: {scores.get('provenance', 0):.1f}/10
● ✅ Resonance: {scores.get('resonance', 0):.1f}/10
● ✅ Coherence: {scores.get('coherence', 0):.1f}/10
● ✅ Transparency: {scores.get('transparency', 0):.1f}/10
● ⚠️ Verification: {scores.get('verification', 0):.1f}/10
(Use ✅ for scores >= 7.0, ⚠️ for 4.0-6.9, ❌ for < 4.0)

🔍 Strategic Observations
**Strengths**
[Bullet points of strong areas]

**Areas of Concern**
[Bullet points of weak areas. Be specific about what is missing or weak.]

📌 Recommended Actions
[Bullet points of detailed, actionable remedy recommendations. Avoid generic advice. Suggest specific technical or content fixes.]

📊 Aggregated Brand Trust Summary
Analyzed {report_data.get('total_items_analyzed', 0)} URLs for brand "{brand_id}".

Average Trust Scores by Dimension
Provenance: {scores.get('provenance', 0):.1f} / 10
Resonance: {scores.get('resonance', 0):.1f} / 10
Coherence: {scores.get('coherence', 0):.1f} / 10
Transparency: {scores.get('transparency', 0):.1f} / 10
Verification: {scores.get('verification', 0):.1f} / 10

INSTRUCTIONS:
- Synthesize the scores into a cohesive narrative.
- Highlight the most critical issues in "Areas of Concern".
- CRITICAL: "Recommended Actions" must be detailed and actionable. Provide specific remedies for the identified weaknesses.
"""

    try:
        client = ChatClient()
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
            temperature=0.7
        )
        return response.get('content') or response.get('text') or "Error generating audit report"
    except Exception as e:
        logger.error(f"Failed to generate audit report: {e}")
        return "Error generating audit report"
