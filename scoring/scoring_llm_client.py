"""
LLM Scoring Client for Trust Stack Rating Tool
Centralizes all OpenAI API interactions for content scoring
"""

from openai import OpenAI
from typing import Dict, Any
import logging
import json

from config.settings import APIConfig
from data.models import NormalizedContent

logger = logging.getLogger(__name__)


class LLMScoringClient:
    """
    Client for LLM-based content scoring
    Handles all OpenAI API interactions with different scoring patterns
    """
    
    def __init__(self, model: str = "gpt-3.5-turbo"):
        """
        Initialize LLM scoring client
        
        Args:
            model: OpenAI model to use (default: gpt-3.5-turbo)
        """
        self.client = OpenAI(api_key=APIConfig.openai_api_key)
        self.model = model
    
    def get_score(self, prompt: str) -> float:
        """
        Get a simple numeric score from LLM
        
        Args:
            prompt: Scoring prompt
        
        Returns:
            Score between 0.0 and 1.0
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert content authenticity evaluator. Always respond in English, regardless of the language of the content being analyzed. Respond with only a number between 0.0 and 1.0."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.1
            )
            
            # Parse response
            try:
                score_text = response.choices[0].message.content.strip()
            except Exception:
                score_text = str(response.choices[0].message.get('content', '')).strip()
            
            score = float(score_text)
            
            # Ensure score is in valid range
            return min(1.0, max(0.0, score))
            
        except Exception as e:
            logger.error(f"LLM scoring error: {e}")
            return 0.5  # Return neutral score on error
    
    def get_score_with_reasoning(self, prompt: str) -> Dict[str, Any]:
        """
        Get score AND reasoning from LLM with structured JSON output
        
        Args:
            prompt: Scoring prompt that requests JSON response
        
        Returns:
            Dictionary with 'score' (float) and 'issues' (list of dicts)
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert content authenticity evaluator. Always respond in English with valid JSON, regardless of the language of the content being analyzed."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            # Parse JSON response
            try:
                response_text = response.choices[0].message.content.strip()
                result = json.loads(response_text)
            except Exception:
                response_text = str(response.choices[0].message.get('content', '{}')).strip()
                result = json.loads(response_text)
            
            # Validate and normalize
            score = float(result.get('score', 0.5))
            score = min(1.0, max(0.0, score))
            
            issues = result.get('issues', [])
            if not isinstance(issues, list):
                issues = []
            
            return {
                'score': score,
                'issues': issues
            }
            
        except Exception as e:
            logger.error(f"LLM structured scoring error: {e}")
            return {
                'score': 0.5,
                'issues': []
            }
    
    def get_score_with_feedback(self, score_prompt: str, content: NormalizedContent,
                                dimension: str, context_guidance: str = "") -> Dict[str, Any]:
        """
        Two-step LLM scoring: Get score first, then get feedback based on score
        
        Args:
            score_prompt: Prompt to get the score (0.0-1.0)
            content: Content being scored
            dimension: Dimension name (for logging)
            context_guidance: Optional context about content type
        
        Returns:
            Dictionary with 'score' (float) and 'issues' (list of dicts)
        """
        # Step 1: Get the score
        score = self.get_score(score_prompt)
        logger.debug(f"{dimension} base score: {score:.2f}")
        
        # Step 2: Get feedback based on score
        if score < 0.9:
            # Low/medium score: Ask for specific issues with concrete rewrites
            # Provide valid issue types based on dimension
            valid_types = self._get_valid_issue_types(dimension)
            
            feedback_prompt = f"""
            You scored this content's {dimension} as {score:.1f} out of 1.0.
            
            {context_guidance}
            
            What specific issues caused this lower score? Provide actionable feedback with CONCRETE REWRITES.
            
            Content:
            Title: {content.title}
            Body: {content.body[:5000]}
            
            Respond with JSON in this exact format:
            {{
                "issues": [
                    {{
                        "type": "issue_type",
                        "confidence": 0.85,
                        "severity": "high",
                        "evidence": "EXACT QUOTE: 'the actual text from the content'",
                        "suggestion": "Change 'the actual text from the content' → 'the corrected text'. This improves {dimension} because [reason]."
                    }}
                ]
            }}
            
            VALID ISSUE TYPES FOR {dimension.upper()}:
            {valid_types}
            
            CRITICAL REQUIREMENTS:
            1. Use ONLY the issue types listed above
            2. Provide EXACT QUOTES in evidence field - the quoted text MUST appear in the content above
            3. In suggestion field, show CONCRETE REWRITE using format: "Change 'X' → 'Y'"
            4. Include brief explanation of WHY the change improves {dimension}
            5. Only report issues you can support with specific text FROM THE CONTENT PROVIDED
            6. If you cannot find a specific quote in the content, DO NOT make up suggestions
            7. For the following issue types, explicitly state the specific issue (e.g., "run-on sentence", "missing citation", "passive voice") in the suggestion:
               - inconsistent_voice, tone_shift, vocabulary, contradictory_claims
               - unverified_claims, fake_engagement, unlabeled_ads
               - hidden_sponsored_content, missing_data_source_citations
               - poor_readability, inappropriate_tone
            
            8. CRITICAL - For VOCABULARY and TONE SHIFT issues specifically:
               - Start with the problem type: "Inconsistent terminology:", "Jargon mismatch:", "Brand voice deviation:", "Unclear wording:", "Tone shift:", etc.
               - Explain WHY the flagged text is problematic
               - Then provide the EXACT QUOTE
               - Format: "[Problem Type]: [Explanation]. EXACT QUOTE: 'text from content'"
               - Example: "Jargon mismatch: The phrase 'Zone Enhancement Information' is technical jargon that doesn't match the plain-language style used elsewhere. EXACT QUOTE: 'Zone Enhancement Information'"
               - DO NOT start the suggestion with "EXACT QUOTE" - you MUST provide an explanation first.
            
            IMPORTANT - Visual Hierarchy & Structure Awareness:
            If the content includes element markers like [HEADLINE], [SUBHEADLINE], [BODY_TEXT], [PRODUCT_LISTING]:
            - Different capitalization between HEADLINE and other elements is INTENTIONAL design
            - Only flag tone shifts WITHIN the same semantic element type
            - Headlines naturally use ALL CAPS or Title Case - this is NOT a tone shift
            - Product listings may have repeated similar text - this is INTENTIONAL structure
            - Footer text often has different tone than body - this is EXPECTED
            
            EXAMPLE GOOD SUGGESTIONS:
            
            For concrete rewrites:
            "Change 'Find the right type of Mastercard payment card for you' → 'Discover the perfect Mastercard for your needs'. This improves coherence by using more consistent, engaging brand voice."
            
            For vocabulary issues (no rewrite needed):
            "Inconsistent terminology: The site uses both 'customer' and 'client' interchangeably, which can confuse readers. EXACT QUOTE: 'Our clients receive premium service'"
            "Jargon mismatch: Technical term doesn't align with the conversational tone used throughout the rest of the page. EXACT QUOTE: 'Zone Enhancement Information'"
            
            EXAMPLE BAD SUGGESTIONS (DO NOT DO THIS):
            "Improve the wording" or "Make it more professional" (too vague, no concrete rewrite)
            Suggesting changes to text that doesn't appear in the content provided
            Flagging capitalization differences between [HEADLINE] and [BODY_TEXT] as tone shifts
            For vocabulary: Just providing a quote without explaining what type of vocabulary problem it is
            "EXACT QUOTE: 'some text'" (missing explanation)
            """
        else:
            # High score (0.9-1.0): Suggestions are optional, especially for very high scores
            if score >= 0.95:
                # Very high score (≥0.95): Request minor optimization tips
                feedback_prompt = f"""
                You scored this content's {dimension} as {score:.1f} out of 1.0 - this is excellent!
                
                {context_guidance}
                
                Even excellent content can be optimized. Provide ONE minor, specific optimization tip with a CONCRETE REWRITE.
                
                Content:
                Title: {content.title}
                Body: {content.body[:5000]}
                
                CRITICAL REQUIREMENTS:
                1. Provide exactly ONE optimization tip
                2. Use the issue type "improvement_opportunity"
                3. The quoted text MUST appear in the content above - DO NOT make up quotes or quote from this prompt
                4. Show CONCRETE REWRITE using format: "Change 'X' → 'Y'"
                5. Explain WHY this small change improves the content
                6. **REQUIRED**: Start suggestion with a specific aspect prefix (e.g., "Brand Voice Consistency:", "CTA Clarity:", "Tone Optimization:")
                7. DO NOT quote any text from this prompt itself (e.g., do not quote "What is one small thing I could do to make this perfect?")
                8. If you cannot find specific text to improve, return an empty issues array
                
                Respond with JSON in this exact format:
                {{
                    "issues": [
                        {{
                            "type": "improvement_opportunity",
                            "confidence": 0.7,
                            "severity": "low",
                            "evidence": "EXACT QUOTE: 'the actual text from content'",
                            "suggestion": "[Specific Aspect]: [Brief explanation of current state and why it could be better]. Change 'the actual text from content' → 'the optimized text'. This enhances [specific benefit]."
                        }}
                    ]
                }}
                
                REQUIRED FORMAT FOR SUGGESTION:
                - MUST start with aspect prefix followed by colon (e.g., "Call-to-Action Clarity:")
                - MUST include explanation of why current text could be better
                - MUST include concrete rewrite with "Change 'X' → 'Y'" format
                - MUST explain the benefit of the change
                
                EXAMPLE FOR COHERENCE:
                "suggestion": "Call-to-Action Clarity: The phrase uses generic all-caps text that could be more specific and engaging. Change 'Explore ALL PRODUCTS' → 'Discover Our Complete Oral Care Collection'. This enhances coherence by using descriptive, brand-aligned language instead of generic CTAs."
                
                EXAMPLE FOR TRANSPARENCY:
                "suggestion": "Timestamp Specificity: The vague time reference reduces transparency. Change 'Posted recently' → 'Published on January 15, 2024'. This enhances transparency by providing specific, verifiable dates."
                
                INVALID EXAMPLES (DO NOT DO THIS):
                - "Change 'text' → 'better text'" (missing aspect prefix)
                - Quoting text from this prompt instead of from the content
                - "Teeth Whitening Remove surface stains..." (just quoting content without aspect or explanation)
                - "EXACT QUOTE: 'some text'" (just providing the quote without any suggestion)
                """
            else:
                # High score (0.9-0.95): Ask for improvement suggestions with concrete rewrites
                feedback_prompt = f"""
                You scored this content's {dimension} as {score:.1f} out of 1.0 - this is good!
                
                {context_guidance}
                
                Provide at least ONE specific, actionable improvement with a CONCRETE REWRITE that would move the score closer to 100%.
                
                Content:
                Title: {content.title}
                Body: {content.body[:5000]}
                
                CRITICAL REQUIREMENTS:
                1. Provide at least ONE improvement if possible
                2. The quoted text MUST appear in the content above - DO NOT make up quotes or quote from this prompt
                3. Provide a SINGLE exact quote showing what could be improved
                4. Show CONCRETE REWRITE using format: "Change 'X' → 'Y'"
                5. Explain WHY this change would improve the score
                6. **REQUIRED**: Start suggestion with a specific aspect prefix (e.g., "Brand Voice Consistency:", "CTA Clarity:", "Tone Optimization:")
                7. DO NOT quote any text from this prompt itself (e.g., do not quote "Why didn't I get 100%?")
                8. If you cannot find specific text to quote, return an empty issues array
                
                Respond with JSON in this exact format:
                {{
                    "issues": [
                        {{
                            "type": "improvement_opportunity",
                            "confidence": 0.75,
                            "severity": "low",
                            "evidence": "EXACT QUOTE: 'the actual text from content'",
                            "suggestion": "[Specific Aspect]: [Brief explanation]. Change 'the actual text from content' → 'the enhanced text'. This would improve {dimension} by [reason]."
                        }}
                    ]
                }}
                
                REQUIRED FORMAT FOR SUGGESTION:
                - MUST start with aspect prefix followed by colon (e.g., "Call-to-Action Clarity:")
                - MUST include explanation of why current text could be better
                - MUST include concrete rewrite with "Change 'X' → 'Y'" format
                - MUST explain the benefit of the change
                
                EXAMPLES OF GOOD SUGGESTIONS WITH CONCRETE REWRITES:
                - "Call-to-Action Clarity: Generic wording could be more specific. Change 'Click here to learn more' → 'Explore our complete product guide'. This improves coherence by providing specific, descriptive CTAs."
                - "Timestamp Specificity: Vague time reference reduces transparency. Change 'Posted recently' → 'Published on January 15, 2024'. This improves transparency by adding specific timestamps."
                
                INVALID EXAMPLES (DO NOT DO THIS):
                - "Change 'text' → 'better text'" (missing aspect prefix and explanation)
                - "Add a call-to-action" (no concrete rewrite shown)
                - "Improve the wording" (too vague)
                - Quoting text from this prompt instead of from the content
                - "Explore ALL PRODUCTS" (just a quote without aspect or explanation)
                - "EXACT QUOTE: 'some text'" (just providing the quote without any suggestion)
                """
        
        # Get feedback from LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert content evaluator. Always respond in English with valid JSON, regardless of the language of the content being analyzed."},
                    {"role": "user", "content": feedback_prompt}
                ],
                max_tokens=500,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            feedback_text = response.choices[0].message.content.strip()
            feedback_data = json.loads(feedback_text)
            
            return {
                'score': score,
                'issues': feedback_data.get('issues', [])
            }
            
        except Exception as e:
            logger.error(f"LLM feedback error for {dimension}: {e}")
            return {'score': score, 'issues': []}
    
    def _get_valid_issue_types(self, dimension: str) -> str:
        """
        Get valid issue types for a dimension
        
        Args:
            dimension: Dimension name (Coherence, Verification, etc.)
        
        Returns:
            Formatted string of valid issue types
        """
        dimension_lower = dimension.lower()
        
        issue_types = {
            'coherence': [
                'inconsistent_voice - voice/tone varies across content',
                'vocabulary - word choice issues or jargon inconsistency',
                'tone_shift - abrupt changes in formality or style',
                'contradictory_claims - conflicting statements',
                'broken_links - non-functional links'
            ],
            'verification': [
                'unverified_claims - statements without sources',
                'fake_engagement - suspicious metrics',
                'unlabeled_ads - undisclosed sponsored content'
            ],
            'transparency': [
                'missing_privacy_policy - no privacy policy link',
                'no_ai_disclosure - AI usage not disclosed',
                'missing_data_source_citations - claims lack sources',
                'hidden_sponsored_content - ads not clearly labeled'
            ],
            'provenance': [
                'unclear_authorship - author not identified',
                'missing_metadata - incomplete metadata',
                'no_schema_markup - missing structured data'
            ],
            'resonance': [
                'poor_readability - difficult to read',
                'inappropriate_tone - tone does not match audience'
            ]
        }
        
        types = issue_types.get(dimension_lower, ['improvement_opportunity'])
        return '\n'.join(f'  - {t}' for t in types)

    def generate(self, prompt: str, model: str = None, max_tokens: int = 500, temperature: float = 0.3) -> str:
        """
        Generate text response from LLM
        
        Args:
            prompt: Input prompt
            model: Optional model override
            max_tokens: Max tokens for response
            temperature: Temperature for response
            
        Returns:
            Generated text string
        """
        try:
            response = self.client.chat.completions.create(
                model=model or self.model,
                messages=[
                    {"role": "system", "content": "You are an expert content authenticity evaluator. Always respond in English."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            try:
                return response.choices[0].message.content.strip()
            except Exception:
                return str(response.choices[0].message.get('content', '')).strip()
                
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return ""
