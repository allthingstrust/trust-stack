"""
Recommendation and remedy generation for Trust Stack Rating
"""
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def _generate_contextual_remedy(issue_type: str, dimension: str, llm_suggestions: List[Dict[str, Any]], base_remedy: str) -> str:
    """
    Generate a contextual best practice based on the specific LLM suggestions.
    
    Args:
        issue_type: Type of issue detected
        dimension: Dimension the issue belongs to
        llm_suggestions: List of LLM-generated suggestions
        base_remedy: The generic base remedy
        
    Returns:
        A more contextual and specific best practice
    """
    # Analyze the suggestions to create a more specific remedy
    if not llm_suggestions:
        return base_remedy
    
    # Extract common themes from suggestions
    all_suggestions_text = " ".join([s.get('suggestion', '') for s in llm_suggestions]).lower()
    
    # Create context-specific guidance based on common patterns
    if 'punctuation' in all_suggestions_text or 'spacing' in all_suggestions_text or 'colon' in all_suggestions_text:
        return "Review all content for proper punctuation, spacing, and formatting consistency. Pay special attention to colons, commas, and spacing after punctuation marks."
    
    elif 'title' in all_suggestions_text and 'align' in all_suggestions_text:
        return "Ensure page titles accurately reflect the content and purpose of each page. Titles should be descriptive and aligned with the actual content to improve clarity and SEO."
    
    elif 'readability' in all_suggestions_text or 'clarity' in all_suggestions_text:
        return "Focus on improving content readability and clarity. Break up long sentences, use clear headings, and ensure the content flows logically."
    
    elif 'consistency' in all_suggestions_text or 'inconsistent' in all_suggestions_text:
        return "Audit content across all pages to ensure consistency in messaging, terminology, and formatting. Create a style guide if one doesn't exist."
    
    elif 'metadata' in all_suggestions_text or 'schema' in all_suggestions_text:
        return "Implement comprehensive metadata and structured data across all pages. This improves discoverability and helps search engines understand your content."
    
    else:
        # Default: use the first sentence of base remedy with a contextual prefix
        first_sentence = base_remedy.split('.')[0] if '.' in base_remedy else base_remedy
        return f"Based on the specific issues detected, {first_sentence.lower()}."


def extract_issues_from_items(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:

    """
    Extract specific issues from content items grouped by dimension.

    Args:
        items: List of analyzed content items with detected attributes

    Returns:
        Dictionary mapping dimension to list of specific issues found
    """
    dimension_issues = {
        'provenance': [],
        'verification': [],
        'transparency': [],
        'coherence': [],
        'resonance': []
    }

    # Define passing thresholds for specific attributes
    # Default is 10.0 (perfect score required)
    PASSING_THRESHOLDS = {
        # Author attribution is considered "present" and acceptable at 6.0+
        # (6.0 = footer attribution, 7.0 = meta tag, 8.0 = byline)
        'author_brand_identity_verified': 6.0,
        # Readability "Acceptable" (7.0) should be considered passing
        'readability_grade_level_fit': 7.0,
    }

    for item in items:
        meta = item.get('meta')
        
        # Ensure meta is always a dict
        if meta is None:
            meta = {}
        elif isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except:
                meta = {}
        elif not isinstance(meta, dict):
            meta = {}

        # Extract detected attributes - meta is guaranteed to be a dict here
        detected_attrs = meta.get('detected_attributes', [])
        title = meta.get('title') or meta.get('name') or 'Unknown content'
        title = title[:60]  # Truncate after ensuring it's a string
        url = meta.get('source_url') or meta.get('url') or ''
        language = meta.get('language', 'en')


        for attr in detected_attrs:
            dimension = attr.get('dimension', 'unknown')
            value = attr.get('value', 5)
            evidence = attr.get('evidence', '')
            label = attr.get('label', '')
            suggestion = attr.get('suggestion')  # Extract LLM suggestion
            attr_id = attr.get('attribute_id') or attr.get('id', '')

            # Determine passing threshold for this attribute
            passing_threshold = PASSING_THRESHOLDS.get(attr_id, 10.0)

            # Report if value is below the passing threshold
            if dimension in dimension_issues and value < passing_threshold:
                issue_dict = {
                    'title': title,
                    'url': url,
                    'issue': label,
                    'evidence': evidence,
                    'value': value,
                    'language': language
                }
                # Add suggestion if available
                if suggestion:
                    issue_dict['suggestion'] = suggestion
                
                dimension_issues[dimension].append(issue_dict)

        # 2. Check applied_rules (from rubric-based detection in pipeline)
        # These are issues that might not be in detected_attributes but were applied during scoring
        for rule in item.get('applied_rules', []):
            # Only consider penalties or low scores as issues
            # Assuming value < 10 indicates an issue for 1-10 scale attributes
            if rule.get('value', 10) < 10:
                dimension = rule.get('dimension', 'unknown').lower()
                issue_label = rule.get('label') or rule.get('id')
                
                if dimension not in dimension_issues:
                    dimension_issues[dimension] = []
                
                # Check if this issue is already added (avoid duplicates)
                existing_issues = [i['issue'] for i in dimension_issues[dimension] if i['url'] == url]
                if issue_label not in existing_issues:
                    dimension_issues[dimension].append({
                        'title': title,
                        'url': url,
                        'issue': issue_label,
                        'evidence': rule.get('reason', 'Issue detected by scoring rule'),
                        'value': rule.get('value'),
                        'language': language
                    })

    return dimension_issues


def get_remedy_for_issue(issue_type: str, dimension: str, issue_items: List[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    Get specific remedy recommendation for a detected issue type with contextual examples.

    Args:
        issue_type: Type of issue detected (e.g., "Privacy Policy Link Availability Clarity")
        dimension: Dimension the issue belongs to
        issue_items: Optional list of specific issue instances with evidence

    Returns:
        Dictionary with:
        - 'recommended_fix': Specific actionable remedy with concrete examples
        - 'general_best_practice': General guidance for this issue type
    """
    # Map specific issues to remedies
    remedies = {
        # Provenance
        'AI vs Human Labeling Clarity': 'Add clear labels indicating whether content is AI-generated or human-created. Use visible disclosure tags like "AI-generated" or "Created with AI assistance" on the content itself. Implement schema.org markup (CreativeWork with "author" and "isBasedOn" properties) to embed this metadata in machine-readable format for search engines and LLMs.',
        'Author/Brand Identity Verified': 'Add clear author attribution to all content. For blog posts and articles: include visible bylines with author names and optional author bio pages. For corporate pages and landing pages: add schema.org markup with author/publisher information using JSON-LD format, include <meta name="author"> tags, or add subtle footer attribution like "Content by [Team/Name]". Create an About page listing content contributors and link to it from main pages.',
        'C2PA/CAI Manifest Present': 'Implement Content Authenticity Initiative (C2PA) manifests for media files to provide cryptographic provenance. C2PA embeds tamper-proof metadata in images and videos showing who created them, when, and with what tools. This is especially important for AI-generated media.',
        'Canonical URL Matches Declared Source': 'Ensure canonical URLs match the declared source to avoid duplicate content issues. Add proper <link rel="canonical"> tags to all pages pointing to the preferred version. Common issues: HTTP vs HTTPS mismatches, www vs non-www, trailing slashes, URL parameters. Choose one canonical version and stick to it.',
        'Digital Watermark/Fingerprint Detected': 'Add digital watermarks or fingerprints to images and videos for traceability. Watermarks help prove ownership and detect unauthorized use of your media assets.',
        'EXIF/Metadata Integrity': 'Preserve EXIF metadata in images. Ensure metadata includes creator, date, location (if relevant), and copyright information. Avoid stripping metadata when processing images for web use.',
        'Source Domain Trust Baseline': 'Improve domain reputation. Ensure you have: valid SSL certificate (HTTPS), accessible privacy policy, clear contact information, professional domain age, and no association with spam or malware. Consider third-party verification badges.',
        'Schema Compliance': 'Implement schema.org structured data markup (JSON-LD) for all content types. This helps search engines understand your content and can improve visibility and trust signals.',
        'Metadata Completeness': 'Add complete metadata to all pages. Required elements: title tag, meta description, author attribution, publication/modified date, Open Graph tags (og:title, og:description, og:image), and Twitter Card tags.',
        'unclear_authorship': 'Add clear author attribution to all content. For blog posts and articles: include visible bylines with author names and optional author bio pages. For corporate pages and landing pages: add schema.org markup with author/publisher information using JSON-LD format, include <meta name="author"> tags, or add subtle footer attribution like "Content by [Team/Name]". Create an About page listing content contributors and link to it from main pages.',
        'missing_metadata': 'Add complete metadata to all pages. Required elements: title tag, meta description, author attribution, publication/modified date, Open Graph tags (og:title, og:description, og:image), and Twitter Card tags. Use tools like Google Rich Results Test to validate your metadata.',
        'no_schema_markup': 'Implement schema.org structured data markup (JSON-LD) for all content types. This helps search engines understand your content and can improve visibility and trust signals. Common schema types: Article, Product, Organization, LocalBusiness, FAQPage.',

        # Verification
        'Ad/Sponsored Label Consistency': 'Clearly label all sponsored content and advertisements. Use consistent, prominent labels: "Sponsored", "Ad", "Paid Partnership", or "Promoted". Ensure labels appear: on social media posts, in email campaigns, on website promotional content. Labels must be visible before user interaction.',
        'Agent Safety Guardrail Presence': 'Implement content safety guardrails and moderation policies for AI systems. Document publicly: what topics AI will/won\'t discuss, how harmful content is filtered, escalation procedures. Test guardrails regularly with adversarial inputs.',
        'Claim-to-source traceability': 'Add citations and inline references for all factual claims. Each claim should link to an authoritative, verifiable source (research papers, official statistics, primary sources). Avoid unsourced assertions.',
        'Engagement Authenticity Ratio': 'Monitor engagement metrics for bot activity and fake engagement. Look for: sudden spikes in followers/likes, accounts with no profile pictures, generic comments, engagement from inactive accounts. Remove fake engagement and report bot accounts. Focus on organic community building.',
        'Influencer/Partner Identity Verified': 'Verify all influencer and partner identities before collaboration. Check for: platform verification badges (blue checkmarks), consistent presence across platforms, genuine audience engagement, professional credentials. Display verification status on partnership content.',
        'Review Authenticity Confidence': 'Implement verified review systems with purchase verification. Flag suspicious patterns: multiple reviews from same IP, identical phrasing, reviews posted in rapid succession, overly promotional language. Consider implementing CAPTCHA or email verification for reviewers.',
        'Seller & Product Verification Rate': 'Verify seller identities and product authenticity. Implement: business license verification, product authenticity certificates, GTIN/UPC matching, seller reputation scoring. Display verification badges prominently on product pages.',
        'Verified Purchaser Review Rate': 'Mark reviews from verified purchasers with a badge or label. Implement purchase verification by matching order numbers to review submissions. Prioritize verified purchase reviews in display rankings.',

        # Transparency
        'AI Explainability Disclosure': 'When using AI, explain how it works and what data it uses. Create an AI transparency page covering: what AI systems you use, how they make decisions, what data they process, how users can opt out. Add "Powered by AI" disclosures on AI-generated content.',
        'AI-Generated/Assisted Disclosure Present': 'Clearly disclose when content is AI-generated or AI-assisted. Add disclosure statements prominently: "This content was created with AI assistance" or "AI-generated summary". Use visual indicators (badges, labels) and schema.org markup (digital-document-permission property).',
        'Bot Disclosure + Response Audit': 'Clearly identify bot-generated responses with disclaimers like "This is an automated response" or "AI assistant". Ensure bots: self-identify in first interaction, explain their limitations, offer clear path to human support. Audit bot responses for accuracy and helpfulness.',
        'Caption/Subtitle Availability & Accuracy': 'Add accurate captions and subtitles to all video content. Use professional captioning services or human review to verify auto-generated captions. Ensure captions include: speaker identification, relevant sound effects, music descriptions for accessibility.',
        'Data Source Citations for Claims': 'Add inline citations for all data-driven claims. Each statistic, fact, or research finding should link to: primary source (research paper, official report), publication date, credible organization. Format citations consistently (footnotes, inline links, or reference section).',
        'Privacy Policy Link Availability & Clarity': 'Add a clear Privacy Policy link to your footer and top navigation. Ensure the policy: is written in plain language (avoid legalese), clearly explains data collection practices, is updated regularly (review annually), is mobile-friendly. Consider adding a summary or FAQ section.',
        'missing_privacy_policy': 'Add a clear Privacy Policy link to your footer and top navigation. Ensure the policy: is written in plain language (avoid legalese), clearly explains data collection practices, is updated regularly (review annually), is mobile-friendly. Consider adding a summary or FAQ section.',
        'no_ai_disclosure': 'Clearly disclose when content is AI-generated or AI-assisted. Add disclosure statements prominently: "This content was created with AI assistance" or "AI-generated summary". Use visual indicators (badges, labels) and schema.org markup (digital-document-permission property).',
        'missing_data_source_citations': 'Add inline citations for all data-driven claims. Each statistic, fact, or research finding should link to: primary source (research paper, official report), publication date, credible organization. Format citations consistently (footnotes, inline links, or reference section).',
        'hidden_sponsored_content': 'Clearly label all sponsored content and advertisements. Use consistent, prominent labels: "Sponsored", "Ad", "Paid Partnership", or "Promoted". Ensure labels appear before user interaction and are visible on all platforms.',

        # Coherence
        'Brand Voice Consistency Score': 'Audit all content for consistent brand voice and tone. Create written brand voice guidelines covering: vocabulary preferences, sentence structure, formality level, personality traits (e.g., professional vs. casual). Train all content creators on these guidelines and review content before publishing.',
        'Inconsistent Voice': 'Audit all content for consistent brand voice and tone. Create written brand voice guidelines covering: vocabulary preferences, sentence structure, formality level, personality traits (e.g., professional vs. casual). Train all content creators on these guidelines and review content before publishing. Ensure the same voice is used across all channels and content types.',
        'Tone Shift': 'Review content for abrupt changes in tone or formality. Ensure consistent tone throughout each piece of content and across all brand communications. Common causes: multiple authors without style guide, mixing formal/informal language, inconsistent use of pronouns (we/you/they). Establish tone guidelines and have a single editor review for consistency.',
        'Broken Link Rate': 'Regularly audit and fix broken links using automated link checkers. Recommended tools: Broken Link Checker, Screaming Frog, or Ahrefs. Run checks weekly and fix broken links within 24-48 hours. Set up monitoring alerts for broken links.',
        'Claim Consistency Across Pages': 'Ensure factual claims are consistent across all pages and channels. Identify contradictions where different pages state different facts, figures, or positions. Create a content style guide with a single source of truth for key claims (pricing, product specs, company facts).',
        'Email-Asset Consistency Check': 'Standardize email templates to match website branding. Ensure consistency in: logo usage, color schemes, typography, button styles, promotional claims, pricing. Verify that email links point to landing pages with matching offers and messaging.',
        'Engagement-to-Trust Correlation': 'Monitor how engagement metrics (CTR, time on site, bounce rate) correlate with trust indicators. Investigate pages with high engagement but low trust scores, or vice versa. This may indicate misleading headlines, clickbait, or poor user experience.',
        'Multimodal Consistency Score': 'Ensure text, images, videos, and audio tell a consistent story. Check that: video transcripts match spoken content, image captions accurately describe visuals, infographic data matches text claims. Avoid contradictions between different media types on the same page.',
        'Temporal continuity (versions)': 'Maintain version history for content updates. Display "Last updated" dates prominently. For significant changes, provide a change log or "What\'s new" section. Consider using version control for important documents and showing edit history.',
        'Trust Fluctuation Index': 'Monitor trust score changes over time using analytics. Investigate sudden drops or spikes. Common causes: security incidents, negative press, policy changes, service outages. Set up alerts for trust score changes >10% and respond quickly.',

        # Resonance
        'Community Alignment Index': 'Engage with your community authentically and align content with community values. Monitor: social media sentiment, comment tone, shared values in discussions. Address misalignment by: listening to community feedback, adjusting messaging to reflect audience concerns, avoiding tone-deaf marketing during sensitive periods.',
        'Creative recency vs trend': 'Stay current with relevant trends while maintaining brand authenticity. Audit content freshness quarterly. Update outdated statistics, remove references to past events/trends, refresh visuals to current design standards. Balance trending topics with evergreen content.',
        'Cultural Context Alignment': 'Ensure content is culturally appropriate and relevant for target markets. Before launching in new regions: research local customs and sensitivities, verify color/symbol meanings, check for cultural references that may not translate. Work with cultural consultants and native speakers for diverse markets.',
        'Language/Locale Match': 'Provide content in appropriate languages for target markets. Avoid auto-translation for critical content. Use professional translation services with native speakers. Ensure: correct date/time formats, appropriate currency symbols, culturally relevant examples, localized imagery.',
        'Personalization relevance (embedding similarity)': 'Improve content personalization to better match user interests while respecting privacy. Analyze: user behavior patterns, content topic clusters, recommendation accuracy. Improve relevance by: better user preference models, contextual content suggestions, A/B testing personalization algorithms.',
        'Readability Grade Level Fit': 'Adjust content readability to match your target audience. Test with tools like Flesch-Kincaid or Hemingway Editor. For general audiences: aim for 8th-10th grade reading level, use short sentences (15-20 words), choose simple words over jargon. For technical audiences: adjust accordingly but maintain clarity.',
        'Tone & sentiment appropriateness': 'Ensure content tone matches context and audience expectations. Avoid overly promotional language in educational content. Match tone to platform: professional on LinkedIn, casual on TikTok. Review content for: appropriate emotion level, avoiding manipulation tactics, balancing enthusiasm with authenticity.'
    }

    base_remedy = remedies.get(issue_type, f'Address this {dimension} issue by improving content quality and adding relevant metadata.')

    # Extract LLM suggestions from issue_items
    llm_suggestions = []
    added_urls = set()  # Track URLs that were successfully added as LLM suggestions
    if issue_items:
        for item in issue_items:
            # Check if this item has a suggestion field (from LLM)
            suggestion = item.get('suggestion')
            
            # If not directly available, try to extract from evidence
            if not suggestion:
                evidence = item.get('evidence', '')
                # Check if evidence contains LLM suggestion
                if 'LLM:' in evidence and 'suggestion:' in evidence.lower():
                    # Try to extract suggestion from evidence
                    parts = evidence.split('suggestion:', 1)
                    if len(parts) > 1:
                        suggestion = parts[1].strip()
            
            # Skip if we still don't have a suggestion after trying to extract
            if not suggestion:
                continue
            
            # FIX #4: Apply confidence threshold (≥0.7 for improvement_opportunity, ≥0.8 for others)
            confidence = item.get('confidence', 0.0)
            issue_type_val = item.get('issue', '')
            
            # Lower threshold for improvement opportunities (high-scoring content)
            min_confidence = 0.7 if 'improvement' in issue_type_val.lower() or 'opportunity' in issue_type_val.lower() else 0.8
            
            if confidence < min_confidence:
                logger.debug(f"Filtering low-confidence suggestion (confidence={confidence:.2f}, threshold={min_confidence}): {suggestion[:100]}")
                continue
            
            # Filter out hallucinations: LLM quoting the prompt text instead of content
            prompt_phrases = [
                "why didn't i get 100%",
                "what specific thing could make this even better",
                "what is one small thing i could do to make this perfect",
                "the client wants to know"
            ]
            
            is_hallucination = False
            suggestion_lower = suggestion.lower()
            for phrase in prompt_phrases:
                if phrase in suggestion_lower:
                    logger.warning(f"Filtering hallucination - LLM quoted prompt text: {suggestion[:100]}")
                    is_hallucination = True
                    break
            
            if is_hallucination:
                continue
            
            # Filter out placeholder/template suggestions from the LLM
            evidence_text = item.get('evidence', '')
            
            # Check if this is a placeholder response (LLM returned template text)
            # Only filter if the suggestion is MOSTLY placeholder text (not just contains a phrase)
            placeholder_indicators = [
                'specific problematic text from content',
                'exact problematic text',
                'improved version',
                'brief explanation'
            ]
            
            is_placeholder = False
            evidence_lower = evidence_text.lower()
            
            # Only flag as placeholder if it contains the phrase AND lacks concrete content
            for indicator in placeholder_indicators:
                if indicator in suggestion_lower or indicator in evidence_lower:
                    # Check if there's actual concrete content (quotes with real text)
                    has_concrete_quotes = "'" in suggestion and suggestion.count("'") >= 4  # At least 2 quoted phrases
                    if not has_concrete_quotes:
                        logger.debug(f"Filtering placeholder suggestion containing: '{indicator}'")
                        is_placeholder = True
                        break
            
            if is_placeholder:
                continue
            
            # Define issue types that don't require concrete rewrites (general guidance is acceptable)
            GENERAL_GUIDANCE_ISSUES = [
                # Coherence (tone/voice)
                'inconsistent voice',
                'tone shift', 
                'brand voice inconsistency',
                'vocabulary',
                
                # Resonance (audience fit)
                'poor readability',
                'inappropriate tone',
                
                # Transparency structural issues (missing elements)
                'missing_privacy_policy',
                'no_ai_disclosure',
                'missing_data_source_citations',
                'hidden_sponsored_content',
                
                # Provenance structural issues (missing elements)
                'unclear_authorship',
                'missing_metadata',
                'no_schema_markup',
                
                # Verification pattern analysis
                'fake_engagement'
            ]
            
            # Check if this issue type allows general guidance
            issue_type_lower = issue_type_val.lower()
            allows_general_guidance = any(pattern in issue_type_lower for pattern in GENERAL_GUIDANCE_ISSUES)
            
            # For improvement opportunities, require aspect context
            is_improvement_opportunity = 'improvement' in issue_type_lower or 'opportunity' in issue_type_lower
            
            if is_improvement_opportunity:
                # Check if suggestion has aspect prefix (format: "Aspect Name: explanation...")
                has_aspect_prefix = ':' in suggestion and suggestion.index(':') < 60
                
                # Also check if it's just a bare quote without explanation
                is_bare_quote = (
                    not has_aspect_prefix and 
                    "Change '" not in suggestion and
                    len(suggestion) < 100 and
                    "EXACT QUOTE" not in suggestion
                )
                
                if is_bare_quote:
                    logger.warning(f"Filtering improvement opportunity without aspect context (bare quote): {suggestion[:100]}")
                    continue
                
                if not has_aspect_prefix and "Change '" not in suggestion:
                    logger.warning(f"Filtering improvement opportunity without aspect prefix or concrete rewrite: {suggestion[:100]}")
                    continue
            
            # Validate that the suggestion contains an actual concrete rewrite (unless general guidance is allowed)
            has_concrete_rewrite = ("Change '" in suggestion and ("→" in suggestion or "->" in suggestion))
            
            if not has_concrete_rewrite and not allows_general_guidance:
                logger.debug(f"Filtering suggestion without concrete rewrite: {suggestion[:100]}")
                continue
            
            # FIX #2: Validate that quoted text exists in the content
            # Extract the quoted text from the suggestion (text between quotes or after "Change '")
            quote_validated = True
            evidence_text = item.get('evidence', '')
            
            # Try to extract the quote from evidence (format: "EXACT QUOTE: 'text'")
            if 'EXACT QUOTE:' in evidence_text:
                quote_start = evidence_text.find("'")
                quote_end = evidence_text.rfind("'")
                if quote_start != -1 and quote_end != -1 and quote_start < quote_end:
                    quoted_text = evidence_text[quote_start+1:quote_end]
                    
                    # Check if this quote exists in the original content
                    # We need to check against the full content body
                    # Note: We don't have access to full content here, but we can check evidence
                    # The validation will be done at display time in the UI
                    # For now, we'll trust high-confidence suggestions
                    if len(quoted_text) < 10:
                        # Very short quotes are suspicious
                        logger.debug(f"Filtering suggestion with suspiciously short quote: '{quoted_text}'")
                        quote_validated = False
            
            # Also check if the suggestion itself looks like a hallucination
            # (e.g., suggests changing text that seems generic/made-up)
            if "Change '" in suggestion:
                # Extract the "before" text from suggestion
                before_start = suggestion.find("Change '") + 8
                before_end = suggestion.find("'", before_start)
                if before_start > 7 and before_end != -1:
                    before_text = suggestion[before_start:before_end]
                    
                    # If the before text is very generic, it might be hallucinated
                    generic_phrases = [
                        'click here', 'learn more', 'read more', 'find out',
                        'our product', 'our service', 'contact us'
                    ]
                    # Only flag as suspicious if it's ONLY a generic phrase with no context
                    if before_text.lower().strip() in generic_phrases and len(before_text) < 20:
                        logger.debug(f"Potentially generic suggestion: {before_text}")
                        # Don't filter, but log for monitoring
            
            if quote_validated:
                item_url = item.get('url', '')
                llm_suggestions.append({
                    'suggestion': suggestion,
                    'title': item.get('title', ''),
                    'url': item_url,
                    'evidence': item.get('evidence', ''),
                    'language': item.get('language', 'en'),
                    'confidence': confidence
                })
                # Track this URL as successfully added
                if item_url:
                    added_urls.add(item_url)

    # Build the recommended fix string
    recommended_fix = ""
    
    # If we have LLM suggestions, show them in numbered list
    if llm_suggestions:
        recommendation_items = []
        for idx, llm_sug in enumerate(llm_suggestions, 1):
            suggestion_text = llm_sug['suggestion']
            url = llm_sug.get('url', '')
            title = llm_sug.get('title', '')
            evidence = llm_sug.get('evidence', '')
            
            # Format the suggestion with URL and text
            lang_indicator = ""
            if llm_sug.get('language', 'en') != 'en':
                lang_code = llm_sug.get('language', '').upper()
                lang_indicator = f" (🌐 Translated from {lang_code})"
            
            # Build each recommendation as a multi-line item
            item_lines = []
            # Format:
            # 1. {Issue Description}:
            # EXACT QUOTE: '{quote}'
            # 🔗 {url}
            #     * From: {title}
            
            # Extract issue description from suggestion (first sentence or part before "Change")
            issue_desc = suggestion_text
            rewrite_part = ""
            
            # Check if this is an improvement opportunity with aspect prefix (e.g., "Brand Voice: explanation. Change...")
            # Format: "[Aspect]: [Explanation]. Change 'X' → 'Y'. [Benefit]"
            if ":" in suggestion_text and "Change '" in suggestion_text:
                # Try to extract the aspect (text before first colon)
                parts_by_colon = suggestion_text.split(":", 1)
                potential_aspect = parts_by_colon[0].strip()
                
                # Check if this looks like an aspect (short, title-case, not a sentence)
                # Common aspects: "Brand Voice Consistency", "CTA Clarity", "Tone Optimization", etc.
                if len(potential_aspect) < 50 and not potential_aspect.endswith('.'):
                    # This is likely an aspect prefix
                    # Extract everything between the colon and "Change" as the explanation
                    rest = parts_by_colon[1]
                    if "Change '" in rest:
                        explanation_and_rewrite = rest.split("Change '", 1)
                        explanation = explanation_and_rewrite[0].strip()
                        # Remove leading/trailing periods from explanation
                        if explanation.endswith('.'):
                            explanation = explanation[:-1]
                        
                        # Format: Aspect: Explanation
                        issue_desc = f"{potential_aspect}: {explanation}"
                        rewrite_part = "Change '" + explanation_and_rewrite[1]
                    else:
                        # No "Change" found, use the whole thing as description
                        issue_desc = suggestion_text
                else:
                    # Not an aspect prefix, fall through to normal logic
                    pass
            
            # Fallback: Check if this is a vocabulary/general guidance issue with description before quote
            if not rewrite_part and "EXACT QUOTE:" in suggestion_text and "Change '" not in suggestion_text:
                # Format: "[Problem Type]: [Explanation]. EXACT QUOTE: 'text'"
                # Extract everything before "EXACT QUOTE:" as the description
                parts = suggestion_text.split("EXACT QUOTE:")
                if parts[0].strip():
                    issue_desc = parts[0].strip()
                    # Remove trailing period if present
                    if issue_desc.endswith('.'):
                        issue_desc = issue_desc[:-1]
            elif not rewrite_part and "Change '" in suggestion_text:
                # Format with concrete rewrite: extract description before "Change"
                parts = suggestion_text.split("Change '")
                if parts[0].strip():
                    issue_desc = parts[0].strip()
                    if issue_desc.endswith('.'):
                        issue_desc = issue_desc[:-1]
                else:
                    issue_desc = "Suggested rewrite"
                
                rewrite_part = "Change '" + parts[1]
            elif not rewrite_part and "." in suggestion_text:
                # Fallback: use first sentence
                issue_desc = suggestion_text.split(".")[0].strip()
            
            item_lines.append(f"{idx}. {issue_desc}{lang_indicator}")
            
            if rewrite_part:
                item_lines.append(rewrite_part)
            
            # Extract quote from evidence or suggestion
            quote = ""
            if "EXACT QUOTE:" in evidence:
                quote = evidence.split("EXACT QUOTE:")[1].strip()
            elif "EXACT QUOTE:" in suggestion_text:
                # For vocabulary issues, quote may be in suggestion text
                parts = suggestion_text.split("EXACT QUOTE:")
                if len(parts) > 1:
                    quote_text = parts[1].strip()
                    # Extract just the quoted portion (between quotes if present)
                    if "'" in quote_text:
                        # Find the quoted text: 'text here'
                        start = quote_text.find("'")
                        end = quote_text.find("'", start + 1)
                        if start != -1 and end != -1:
                            quote = "'" + quote_text[start+1:end] + "'"
                        else:
                            quote = quote_text
                    else:
                        quote = quote_text
            elif "Change '" in suggestion_text:
                # Try to extract from suggestion: Change 'X' -> 'Y'
                parts = suggestion_text.split("Change '")
                if len(parts) > 1:
                    quote_part = parts[1]
                    if "'" in quote_part:
                        quote = "'" + quote_part.split("'")[0] + "'"
            
            if quote:
                item_lines.append(f"EXACT QUOTE: {quote}")
            
            if url:
                item_lines.append(f"🔗 {url}")
            
            if title:
                truncated_title = title[:60] + "..." if len(title) > 60 else title
                item_lines.append(f"    * From: {truncated_title}")
            
            recommendation_items.append("\n".join(item_lines))
        
        recommended_fix = "\n\n".join(recommendation_items)
        
    else:
        # No valid LLM suggestions (filtered out or none provided)
        # Add fallback: show specific issues with evidence (non-LLM suggestions)
        if issue_items and len(issue_items) > 0:
            example_items = []
            
            # Define structural issues that should show all URLs (not just max 3)
            structural_issues = [
                'missing_privacy_policy',
                'missing_data_source_citations',
                'no_ai_disclosure',
                'unclear_authorship',
                'missing_metadata',
                'no_schema_markup'
            ]
            
            # Check if this is a structural issue
            is_structural = any(pattern in issue_type.lower().replace(' ', '_') for pattern in structural_issues)
            
            # Check if this is an improvement opportunity
            is_improvement_opportunity = 'improvement' in issue_type.lower() or 'opportunity' in issue_type.lower()
            
            for idx, item in enumerate(issue_items, 1):
                url = item.get('url', '').strip()
                
                # Skip if this URL was already successfully added as an LLM suggestion
                if url and url in added_urls:
                    continue
                
                # For improvement opportunities, apply the same validation as above
                # Don't show items in fallback that were filtered out
                if is_improvement_opportunity:
                    suggestion = item.get('suggestion', '')
                    
                    # Skip if no suggestion
                    if not suggestion:
                        continue
                    
                    # Check for hallucinations
                    prompt_phrases = [
                        "why didn't i get 100%",
                        "what specific thing could make this even better",
                        "what is one small thing i could do to make this perfect",
                        "the client wants to know"
                    ]
                    
                    is_hallucination = any(phrase in suggestion.lower() for phrase in prompt_phrases)
                    if is_hallucination:
                        continue
                    
                    # Check for aspect prefix or concrete rewrite
                    has_aspect_prefix = ':' in suggestion and suggestion.index(':') < 60
                    has_concrete_rewrite = "Change '" in suggestion
                    
                    # Check if it's a bare quote
                    is_bare_quote = (
                        not has_aspect_prefix and 
                        not has_concrete_rewrite and
                        len(suggestion) < 100
                    )
                    
                    if is_bare_quote:
                        continue
                    
                    # If no aspect prefix and no concrete rewrite, skip
                    if not has_aspect_prefix and not has_concrete_rewrite:
                        continue
                
                evidence = item.get('evidence', '').strip()
                title = item.get('title', '').strip()
                
                # For structural issues, create a simple format: • url - description
                # For other issues, use numbered format with evidence
                if url:
                    lang_indicator = ""
                    if item.get('language', 'en') != 'en':
                        lang_code = item.get('language', '').upper()
                        lang_indicator = f" (🌐 Translated from {lang_code})"
                    
                    if is_structural:
                        # Simple bullet format for structural issues
                        # Create a concise description based on issue type
                        if 'privacy' in issue_type.lower():
                            description = "No privacy policy"
                        elif 'data source' in issue_type.lower() or 'citation' in issue_type.lower():
                            description = "No data source citations"
                        elif 'ai disclosure' in issue_type.lower() or 'ai-generated' in issue_type.lower():
                            description = "No AI disclosure"
                        elif 'author' in issue_type.lower():
                            description = "No author attribution"
                        elif 'metadata' in issue_type.lower():
                            description = "Missing metadata"
                        elif 'schema' in issue_type.lower():
                            description = "No schema markup"
                        else:
                            description = evidence if evidence and 'LLM:' not in evidence else "Issue detected"
                        
                        example_items.append(f"• {url}{lang_indicator}\n  - {description}")
                    else:
                        # Numbered format with evidence for non-structural issues
                        if evidence and 'LLM:' not in evidence:
                            item_lines = []
                            item_lines.append(f"{idx}. {evidence}{lang_indicator}")
                            item_lines.append(f"🔗 {url}")
                            
                            if title:
                                truncated_title = title[:60] + "..." if len(title) > 60 else title
                                item_lines.append(f"    * From: {truncated_title}")
                            
                            example_items.append("\n".join(item_lines))
            
            if example_items:
                if is_structural:
                    recommended_fix = "\n".join(example_items)
                else:
                    recommended_fix = "\n\n".join(example_items)
            else:
                recommended_fix = "Review content for this issue."
        else:
             recommended_fix = "Review content for this issue."

    # Generate context-specific best practice based on the suggestions
    contextual_remedy = _generate_contextual_remedy(issue_type, dimension, llm_suggestions, base_remedy)
    
    return {
        'recommended_fix': recommended_fix,
        'general_best_practice': contextual_remedy
    }


def generate_rating_recommendation(avg_rating: float, dimension_breakdown: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    """
    Generate data-driven recommendation based on dimension analysis with specific examples.

    Args:
        avg_rating: Average rating score (0-100)
        dimension_breakdown: Dictionary with dimension averages
        items: List of analyzed content items

    Returns:
        Comprehensive recommendation string with concrete examples
    """
    # Define dimension details
    dimension_info = {
        'provenance': {
            'name': 'Provenance',
            'recommendation': 'implement structured metadata (schema.org markup), add clear author attribution, and include publication timestamps on all content',
            'description': 'origin tracking and metadata'
        },
        'verification': {
            'name': 'Verification',
            'recommendation': 'fact-check claims against authoritative sources, add citations and references, and link to verifiable external data',
            'description': 'factual accuracy'
        },
        'transparency': {
            'name': 'Transparency',
            'recommendation': 'add disclosure statements, clearly identify sponsored content, and provide detailed attribution for all sources',
            'description': 'disclosure and clarity'
        },
        'coherence': {
            'name': 'Coherence',
            'recommendation': 'audit messaging consistency across all channels, align visual branding, and ensure unified voice in customer communications',
            'description': 'cross-channel consistency'
        },
        'resonance': {
            'name': 'Resonance',
            'recommendation': 'increase authentic engagement with your audience, reduce promotional language, and ensure cultural relevance in messaging',
            'description': 'audience engagement'
        }
    }

    # Find lowest-performing dimension
    dimension_keys = ['provenance', 'verification', 'transparency', 'coherence', 'resonance']
    dimension_scores = {
        key: dimension_breakdown.get(key, {}).get('average', 0.5) * 100  # Convert to 0-100 scale
        for key in dimension_keys
    }

    # Extract specific issues from items
    dimension_issues = extract_issues_from_items(items)

    # Find the dimension with the lowest score
    if dimension_scores:
        lowest_dim_key = min(dimension_scores, key=dimension_scores.get)
        lowest_dim_score = dimension_scores[lowest_dim_key]
        lowest_dim_info = dimension_info[lowest_dim_key]

        # Get example issues for the lowest dimension
        issues_for_dim = dimension_issues.get(lowest_dim_key, [])
        example_text = ""
        if issues_for_dim:
            # Get first unique issue as example
            example = issues_for_dim[0]
            
            lang_indicator = ""
            if example.get('language', 'en') != 'en':
                lang_code = example.get('language', '').upper()
                lang_indicator = f" (🌐 Translated from {lang_code})"
                
            example_text = f" For example, on \"{example['title']}\", there was an issue with {example['issue'].lower()}: {example['evidence']}{lang_indicator}."

        # Generate comprehensive summary based on rating band
        if avg_rating >= 80:
            # Excellent - maintain standards with minor optimization
            return f"Your brand content demonstrates high quality with an average rating of {avg_rating:.1f}/100. To reach even greater heights, consider optimizing {lowest_dim_info['name']} (currently at {lowest_dim_score:.1f}/100) by continuing to {lowest_dim_info['recommendation']}.{example_text}"

        elif avg_rating >= 60:
            # Good - focus on improvement area
            return f"Your content shows solid quality with an average rating of {avg_rating:.1f}/100. To improve from Good to Excellent, focus on enhancing {lowest_dim_info['name']} (currently at {lowest_dim_score:.1f}/100) by taking action to {lowest_dim_info['recommendation']}.{example_text}"

        elif avg_rating >= 40:
            # Fair - requires focused attention
            return f"Your content quality is moderate with an average rating of {avg_rating:.1f}/100, requiring attention. To mitigate weak {lowest_dim_info['description']}, you should {lowest_dim_info['recommendation']}.{example_text} This will help move your rating from Fair to Good or Excellent."

        else:
            # Poor - immediate action needed
            return f"Your content quality is low with an average rating of {avg_rating:.1f}/100, requiring immediate action. Critical issue detected in {lowest_dim_info['name']} (scoring only {lowest_dim_score:.1f}/100). You must {lowest_dim_info['recommendation']}.{example_text}"

    else:
        # Fallback if no dimension data available
        return f"Your content has an average rating of {avg_rating:.1f}/100. Comprehensive dimension analysis is needed to provide specific recommendations."
