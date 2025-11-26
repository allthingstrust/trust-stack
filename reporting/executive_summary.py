"""
Executive Summary Generator for Trust Stack Reports

This module provides comprehensive, LLM-powered executive summaries that:
- Analyze all dimensions, not just the weakest
- Provide specific, measurable recommendations
- Reference actual content examples
- Prioritize actions by impact
- Deliver actionable insights instead of generic advice
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def generate_executive_summary(
    avg_rating: float,
    dimension_breakdown: Dict[str, Any],
    items: List[Dict[str, Any]],
    sources: List[str],
    model: str = 'gpt-4o-mini',
    use_llm: bool = True
) -> str:
    """
    Generate a comprehensive executive summary for a Trust Stack analysis.

    Args:
        avg_rating: Overall average rating (0-100 scale)
        dimension_breakdown: Dictionary of dimension statistics
        items: List of analyzed content items
        sources: List of data sources used
        model: LLM model to use (supports multi-provider)
        use_llm: If False, use template-based fallback

    Returns:
        Executive summary text (markdown formatted)
    """
    if use_llm:
        try:
            return _generate_llm_summary(
                avg_rating=avg_rating,
                dimension_breakdown=dimension_breakdown,
                items=items,
                sources=sources,
                model=model
            )
        except Exception as e:
            logger.warning(f"LLM summary generation failed, falling back to template: {e}")
            return _generate_template_summary(
                avg_rating=avg_rating,
                dimension_breakdown=dimension_breakdown,
                items=items
            )
    else:
        return _generate_template_summary(
            avg_rating=avg_rating,
            dimension_breakdown=dimension_breakdown,
            items=items
        )


def _generate_llm_summary(
    avg_rating: float,
    dimension_breakdown: Dict[str, Any],
    items: List[Dict[str, Any]],
    sources: List[str],
    model: str
) -> str:
    """
    Generate executive summary using LLM with comprehensive context.

    This provides significantly better quality than templates by:
    - Analyzing patterns across all dimensions
    - Providing specific, context-aware recommendations
    - Referencing actual content issues
    - Prioritizing by impact
    """
    from scoring.llm_client import ChatClient

    # Prepare dimension scores (0-100 scale)
    dimension_keys = ['provenance', 'verification', 'transparency', 'coherence', 'resonance']
    dimension_scores = {
        key: dimension_breakdown.get(key, {}).get('average', 0.5) * 100
        for key in dimension_keys
    }

    # Find weakest and strongest dimensions
    sorted_dims = sorted(dimension_scores.items(), key=lambda x: x[1])
    weakest_3 = sorted_dims[:3]
    strongest_2 = sorted(dimension_scores.items(), key=lambda x: x[1], reverse=True)[:2]

    # Determine rating band
    if avg_rating >= 80:
        band = "🟢 Excellent"
        band_name = "Excellent"
    elif avg_rating >= 60:
        band = "🟡 Good"
        band_name = "Good"
    elif avg_rating >= 40:
        band = "🟠 Fair"
        band_name = "Fair"
    else:
        band = "🔴 Poor"
        band_name = "Poor"

    # Extract low-scoring items for examples
    low_scoring_items = sorted(
        [item for item in items if item.get('final_score', 1.0) < 0.60],
        key=lambda x: x.get('final_score', 0)
    )[:5]

    # Build comprehensive prompt
    prompt = f"""You are an expert Trust Stack analyst writing an executive summary for a brand's content quality audit.

OVERALL PERFORMANCE:
- Average Rating: {avg_rating:.1f}/100
- Rating Band: {band} ({band_name})
- Total Content Analyzed: {len(items)} items
- Data Sources: {', '.join(sources) if sources else 'Multiple sources'}

DIMENSION BREAKDOWN (0-100 scale):
"""

    # Add all dimensions with status indicators
    for dim, score in sorted(dimension_scores.items(), key=lambda x: x[1]):
        status = "🟢" if score >= 80 else "🟡" if score >= 60 else "🟠" if score >= 40 else "🔴"
        prompt += f"  {status} {dim.title()}: {score:.1f}/100\n"

    prompt += f"""
WEAKEST AREAS (Priority for improvement):
"""
    for i, (dim, score) in enumerate(weakest_3, 1):
        gap = 60 - score  # Gap to "Good" threshold
        prompt += f"  {i}. {dim.title()}: {score:.1f}/100 (gap of {gap:.1f} points to Good threshold)\n"

    prompt += f"""
STRONGEST AREAS (Maintain these):
"""
    for i, (dim, score) in enumerate(strongest_2, 1):
        prompt += f"  {i}. {dim.title()}: {score:.1f}/100\n"

    # Calculate issue counts per dimension to ensure LLM has accurate data
    # (Avoids "3 out of 4" errors when some items with issues aren't in the low_scoring_items list)
    from webapp.utils.recommendations import extract_issues_from_items
    dimension_issues = extract_issues_from_items(items)
    
    prompt += f"""
DIMENSION ISSUE COUNTS (Items with specific defects):
"""
    for dim in dimension_keys:
        issues = dimension_issues.get(dim, [])
        # Count unique URLs with issues in this dimension
        unique_urls_with_issues = len(set(i['url'] for i in issues))
        total_issues_count = len(issues)
        
        if total_issues_count > 0:
            prompt += f"  - {dim.title()}: {total_issues_count} specific issues detected (affecting {unique_urls_with_issues} unique items)\n"


    # Add specific problematic content examples
    if low_scoring_items:
        prompt += f"""
PROBLEMATIC CONTENT EXAMPLES (Low Trust items requiring attention):
"""
        for i, item in enumerate(low_scoring_items, 1):
            title = item.get('title', 'Untitled')[:80]
            score = item.get('final_score', 0) * 100
            source = item.get('source', 'unknown')

            # Get URL safely
            meta = item.get('meta', {})
            if isinstance(meta, str):
                try:
                    import json
                    meta = json.loads(meta) if meta else {}
                except Exception:
                    meta = {}
            url = meta.get('source_url', 'No URL') if isinstance(meta, dict) else 'No URL'

            # Extract specific dimension issues
            dim_scores = item.get('dimension_scores', {})
            if dim_scores:
                weak_dims = sorted(
                    [(k, float(v) if v else 0) for k, v in dim_scores.items()],
                    key=lambda x: x[1]
                )[:2]
                weak_dims_str = ', '.join([f"{d[0].title()}({d[1]*100:.0f})" for d in weak_dims if d[1] is not None])
            else:
                weak_dims_str = "Unknown"

            prompt += f"""
  {i}. "{title}"
     Score: {score:.1f}/100 | Source: {source}
     Weak Dimensions: {weak_dims_str}
     URL: {url}
"""

    prompt += f"""
TASK: Write a comprehensive 3-4 paragraph executive summary that:

1. **Opening Assessment** (2-3 sentences):
   - State the overall rating ({avg_rating:.1f}/100) and what the {band_name} rating means
   - Provide immediate context about the content quality across {len(items)} items
   - Set the tone: is this concerning, satisfactory, or excellent?

2. **Root Cause Analysis** (3-4 sentences):
   - Identify the 2-3 weakest dimensions and explain WHY they're scoring low
   - Reference specific patterns you see in the problematic items listed above
   - Explain the IMPACT these weaknesses have on brand trust and credibility
   - Connect the dots between dimension scores and real content issues

3. **Actionable Recommendations** (4-5 sentences):
   - Provide SPECIFIC, MEASURABLE actions to improve the weakest dimensions
   - Prioritize by impact - what will move the overall rating most?
   - Reference actual examples from the problematic items
   - Be concrete with numbers: "Add disclosure tags to the 15 items lacking transparency"
   - Avoid vague advice like "improve quality" - give specific remediation steps

4. **Expected Outcomes** (1-2 sentences):
   - State: "By following the remedies listed below, you can improve your rating from {avg_rating:.1f}/100 to approximately [target range]/100"
   - Mention which dimensions will see the most improvement
   - DO NOT mention specific timeframes (days, weeks, months) - the organization will determine their own pace

CRITICAL REQUIREMENTS:
✓ Be SPECIFIC - use actual numbers, dimensions, and examples from the data
✓ Be ACTIONABLE - provide concrete steps with clear targets
✓ Be PRIORITIZED - explicitly tell them what to fix FIRST
✓ Be REALISTIC - acknowledge platform constraints where relevant
✓ Be QUANTITATIVE - include numbers and targets throughout
✓ Use a professional, direct tone appropriate for executives
✓ Keep it concise but comprehensive (3-4 paragraphs, ~250-300 words)
✓ DO NOT include specific timeframes - just say "By following the remedies listed below"

Write the executive summary now:"""

    # Call LLM
    try:
        client = ChatClient()
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.5
        )

        summary = response.get('content') or response.get('text')

        if not summary:
            raise ValueError("LLM returned empty response")

        return summary

    except Exception as e:
        logger.error(f"LLM summary generation failed: {e}")
        raise


def _generate_template_summary(
    avg_rating: float,
    dimension_breakdown: Dict[str, Any],
    items: List[Dict[str, Any]]
) -> str:
    """
    Fallback template-based summary when LLM is unavailable or disabled.

    This is less sophisticated but provides a baseline summary.
    """
    # Dimension information
    dimension_info = {
        'provenance': {
            'name': 'Provenance',
            'recommendation': 'improve source attribution and content traceability',
            'description': 'source traceability'
        },
        'verification': {
            'name': 'Verification',
            'recommendation': 'add authoritative citations and link to verifiable data',
            'description': 'factual accuracy'
        },
        'transparency': {
            'name': 'Transparency',
            'recommendation': 'add disclosure statements and clear attribution',
            'description': 'disclosure and clarity'
        },
        'coherence': {
            'name': 'Coherence',
            'recommendation': 'ensure consistent messaging across all channels',
            'description': 'cross-channel consistency'
        },
        'resonance': {
            'name': 'Resonance',
            'recommendation': 'increase authentic audience engagement',
            'description': 'audience engagement'
        }
    }

    # Calculate dimension scores
    dimension_keys = ['provenance', 'verification', 'transparency', 'coherence', 'resonance']
    dimension_scores = {
        key: dimension_breakdown.get(key, {}).get('average', 0.5) * 100
        for key in dimension_keys
    }

    # Find lowest performing dimension
    if dimension_scores:
        lowest_dim_key = min(dimension_scores, key=dimension_scores.get)
        lowest_dim_score = dimension_scores[lowest_dim_key]
        lowest_dim_info = dimension_info[lowest_dim_key]
    else:
        return f"Your content has an average rating of {avg_rating:.1f}/100. Comprehensive dimension analysis is needed to provide specific recommendations."

    # Find an example issue
    example_text = ""
    low_items = [item for item in items if item.get('final_score', 1.0) < 0.60]
    if low_items:
        example = low_items[0]
        title = example.get('title', 'Untitled')[:60]
        example_text = f" For example, \"{title}\" scored low in {lowest_dim_info['name']}."

    # Generate summary based on rating band
    if avg_rating >= 80:
        summary = f"""Your brand content demonstrates high quality with an average rating of {avg_rating:.1f}/100 across {len(items)} analyzed items.

To reach even greater heights, consider optimizing {lowest_dim_info['name']} (currently at {lowest_dim_score:.1f}/100) by continuing to {lowest_dim_info['recommendation']}.{example_text}

By following the remedies listed below, you can improve your rating even further and maintain excellence across all Trust Stack dimensions."""

    elif avg_rating >= 60:
        summary = f"""Your content shows solid quality with an average rating of {avg_rating:.1f}/100 across {len(items)} analyzed items.

To improve from Good to Excellent, focus on enhancing {lowest_dim_info['name']} (currently at {lowest_dim_score:.1f}/100) by taking action to {lowest_dim_info['recommendation']}.{example_text}

By following the remedies listed below, you can improve your rating from {avg_rating:.1f}/100 to 80+/100 (Excellent range)."""

    elif avg_rating >= 40:
        summary = f"""Your content quality is moderate with an average rating of {avg_rating:.1f}/100 across {len(items)} analyzed items, requiring attention.

The primary issue is weak {lowest_dim_info['description']}, particularly in {lowest_dim_info['name']} (scoring {lowest_dim_score:.1f}/100). You should {lowest_dim_info['recommendation']}.{example_text}

By following the remedies listed below, you can improve your rating from {avg_rating:.1f}/100 to 60+/100 (Good range)."""

    else:
        summary = f"""Your content quality is low with an average rating of {avg_rating:.1f}/100 across {len(items)} analyzed items, requiring immediate action.

Critical issue detected in {lowest_dim_info['name']} (scoring only {lowest_dim_score:.1f}/100). You must {lowest_dim_info['recommendation']}.{example_text}

By following the remedies listed below, you can improve your rating significantly and establish a foundation for better brand trust."""

    return summary


def generate_success_highlights(
    high_trust_items: List[Dict[str, Any]],
    avg_rating: float,
    dimension_breakdown: Dict[str, Any],
    model: str = 'gpt-4o-mini'
) -> str:
    """
    Generate LLM-powered analysis of high-performing content to identify success patterns.

    This helps users understand what's working well so they can replicate it.

    Args:
        high_trust_items: List of high-scoring content items (score >= 0.70)
        avg_rating: Overall average rating
        dimension_breakdown: Dimension statistics
        model: LLM model to use

    Returns:
        Success highlights text (markdown formatted)
    """
    if not high_trust_items:
        return "No high-trust content items available for analysis."

    from scoring.llm_client import ChatClient

    # Prepare dimension scores
    dimension_keys = ['provenance', 'verification', 'transparency', 'coherence', 'resonance']
    dimension_scores = {
        key: dimension_breakdown.get(key, {}).get('average', 0.5) * 100
        for key in dimension_keys
    }

    # Find strongest dimensions overall
    strongest_dims = sorted(dimension_scores.items(), key=lambda x: x[1], reverse=True)[:2]

    # Build context about high-trust items
    items_context = ""
    for i, item in enumerate(high_trust_items[:5], 1):
        title = item.get('title', 'Untitled')[:80]
        score = item.get('final_score', 0) * 100
        source = item.get('source', 'unknown')

        # Get URL safely
        meta = item.get('meta', {})
        if isinstance(meta, str):
            try:
                import json
                meta = json.loads(meta) if meta else {}
            except Exception:
                meta = {}
        url = meta.get('source_url', 'No URL') if isinstance(meta, dict) else 'No URL'

        # Get dimension strengths
        dim_scores = item.get('dimension_scores', {})
        if dim_scores:
            strong_dims = sorted(
                [(k, float(v) if v else 0) for k, v in dim_scores.items()],
                key=lambda x: x[1],
                reverse=True
            )[:2]
            strong_dims_str = ', '.join([f"{d[0].title()}({d[1]*100:.0f})" for d in strong_dims if d[1] is not None])
        else:
            strong_dims_str = "Unknown"

        items_context += f"""
  {i}. "{title}"
     Score: {score:.1f}/100 | Source: {source}
     Strong Dimensions: {strong_dims_str}
     URL: {url}
"""

    # Build prompt
    prompt = f"""You are analyzing high-performing content to identify success patterns for a Trust Stack content audit.

OVERALL PERFORMANCE:
- Average Rating: {avg_rating:.1f}/100
- Total High-Trust Items Analyzed: {len(high_trust_items)}

STRONGEST DIMENSIONS (Overall):
"""
    for dim, score in strongest_dims:
        prompt += f"  - {dim.title()}: {score:.1f}/100\n"

    prompt += f"""
HIGH-PERFORMING CONTENT EXAMPLES:
{items_context}

TASK: Write a concise 2-3 paragraph "Success Highlights" analysis that:

1. **Success Patterns** (2-3 sentences):
   - Identify what these high-trust items have in common
   - Explain which dimensions they excel in and WHY
   - Reference specific examples from the list above

2. **Key Differentiators** (2-3 sentences):
   - Explain what sets these successful items apart from lower-scoring content
   - Identify specific trust signals, attributes, or practices they demonstrate
   - Be concrete: mention specific elements like "clear author attribution," "verifiable sources," "consistent branding," etc.

3. **Replication Strategy** (2-3 sentences):
   - Provide SPECIFIC, ACTIONABLE advice on how to replicate this success
   - Tell them exactly what to do more of
   - Be practical: "Continue publishing content with X characteristic" or "Maintain Y practice across all channels"

CRITICAL REQUIREMENTS:
✓ Be SPECIFIC - reference actual examples and dimensions
✓ Be ACTIONABLE - tell them what to keep doing
✓ Be POSITIVE - focus on what's working well
✓ Be CONCISE - 2-3 paragraphs, ~150-200 words total
✓ Use professional, encouraging tone

Write the success highlights now:"""

    # Call LLM
    try:
        client = ChatClient()
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.5
        )

        highlights = response.get('content') or response.get('text')

        if not highlights:
            raise ValueError("LLM returned empty response")

        return highlights

    except Exception as e:
        logger.error(f"Success highlights generation failed: {e}")
        # Fallback to template
        return _generate_template_success_highlights(high_trust_items, strongest_dims)


def _generate_template_success_highlights(
    high_trust_items: List[Dict[str, Any]],
    strongest_dims: List[tuple]
) -> str:
    """Fallback template for success highlights when LLM is unavailable."""
    count = len(high_trust_items)

    # Get most common strong dimension
    dim_name = strongest_dims[0][0].title() if strongest_dims else "Trust"
    dim_score = strongest_dims[0][1] if strongest_dims else 70

    return f"""Your analysis identified {count} high-trust content items (scoring 70+/100) that exemplify best practices. These successful items demonstrate strong {dim_name} ({dim_score:.0f}/100), indicating effective implementation of trust signals and quality standards.

Key success factors include clear attribution, verifiable sources, and consistent messaging. These items show what's possible when content follows established trust and authenticity guidelines.

To replicate this success, continue applying the same quality standards and trust signals demonstrated in your high-performing content. Focus on maintaining consistency in {dim_name.lower()} practices across all channels."""
