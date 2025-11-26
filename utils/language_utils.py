"""
Language detection utilities for content analysis
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Try to import langdetect, but provide fallback if not available
try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    logger.info("langdetect library not available, using fallback language detection")


def detect_language(text: str) -> str:
    """
    Detect the language of the given text.
    
    Args:
        text: Text to analyze
        
    Returns:
        ISO 639-1 language code (e.g., 'en', 'fr', 'es') or 'unknown'
    """
    if not text or len(text.strip()) < 10:
        return 'unknown'
    
    # Use langdetect if available
    if LANGDETECT_AVAILABLE:
        try:
            lang = detect(text)
            return lang
        except LangDetectException:
            logger.debug("Language detection failed, using fallback")
    
    # Fallback: Simple heuristic-based detection
    return _detect_language_fallback(text)


def _detect_language_fallback(text: str) -> str:
    """
    Fallback language detection using simple character-based heuristics.
    
    Args:
        text: Text to analyze
        
    Returns:
        ISO 639-1 language code or 'unknown'
    """
    text_lower = text.lower()
    
    # French indicators
    french_indicators = [
        'à', 'é', 'è', 'ê', 'ç', 'œ',  # Accented characters
        ' le ', ' la ', ' les ', ' de ', ' du ', ' des ', ' un ', ' une ',  # Articles
        ' et ', ' ou ', ' pour ', ' avec ', ' dans ', ' sur ', ' par ',  # Common words
        'ceci', 'cela', 'est', 'sont', 'bonjour', 'tout',  # More common words
        'français', 'québec', 'montréal'  # French-specific words
    ]
    
    # Spanish indicators
    spanish_indicators = [
        'ñ', 'á', 'é', 'í', 'ó', 'ú', '¿', '¡',  # Spanish-specific characters
        ' el ', ' la ', ' los ', ' las ', ' de ', ' del ', ' un ', ' una ',  # Articles
        ' y ', ' o ', ' para ', ' con ', ' en ', ' por ',  # Common words
        'esto', 'eso', 'es', 'son', 'hola', 'todo',  # More common words
        'español', 'méxico'  # Spanish-specific words
    ]
    
    # Count indicators with stricter matching
    french_count = 0
    for indicator in french_indicators:
        if indicator in text_lower:
            french_count += 1
            
    spanish_count = 0
    for indicator in spanish_indicators:
        # For very short indicators like ' y ' or ' o ', ensure they are distinct words
        if len(indicator.strip()) <= 2:
            if indicator in text_lower:
                spanish_count += 1
        else:
            if indicator in text_lower:
                spanish_count += 1
    
    # English indicators to confirm English
    english_indicators = [
        ' the ', ' and ', ' of ', ' to ', ' in ', ' is ', ' you ', ' that ', ' it ',
        ' he ', ' was ', ' for ', ' on ', ' are ', ' as ', ' with ', ' his ', ' they ',
        ' at ', ' be ', ' this ', ' have ', ' from ', ' or ', ' one ', ' had ', ' by '
    ]
    english_count = sum(1 for indicator in english_indicators if indicator in text_lower)
    
    # Determine language based on indicator counts
    # Require a significant number of indicators to override default English
    # and ensure it's significantly more than English indicators
    
    if french_count > 3 and french_count > english_count:
        return 'fr'
    elif spanish_count > 3 and spanish_count > english_count:
        return 'es'
    
    # Default to English if no strong indicators or if English is dominant
    return 'en'


def is_non_english(text: str) -> bool:
    """
    Quick check if content is non-English.
    
    Args:
        text: Text to check
        
    Returns:
        True if content appears to be non-English
    """
    if not text:
        return False
    
    lang = detect_language(text)
    return lang not in ('en', 'unknown')


def get_language_name(lang_code: str) -> str:
    """
    Get human-readable language name from ISO code.
    
    Args:
        lang_code: ISO 639-1 language code
        
    Returns:
        Human-readable language name
    """
    language_names = {
        'en': 'English',
        'fr': 'French',
        'es': 'Spanish',
        'de': 'German',
        'it': 'Italian',
        'pt': 'Portuguese',
        'nl': 'Dutch',
        'pl': 'Polish',
        'ru': 'Russian',
        'ja': 'Japanese',
        'zh': 'Chinese',
        'ko': 'Korean',
        'ar': 'Arabic',
        'unknown': 'Unknown'
    }
    
    return language_names.get(lang_code, lang_code.upper())


def get_language_flag(lang_code: str) -> str:
    """
    Get emoji flag for language code.
    
    Args:
        lang_code: ISO 639-1 language code
        
    Returns:
        Emoji flag representing the language
    """
    language_flags = {
        'en': '🇬🇧',
        'fr': '🇫🇷',
        'es': '🇪🇸',
        'de': '🇩🇪',
        'it': '🇮🇹',
        'pt': '🇵🇹',
        'nl': '🇳🇱',
        'pl': '🇵🇱',
        'ru': '🇷🇺',
        'ja': '🇯🇵',
        'zh': '🇨🇳',
        'ko': '🇰🇷',
        'ar': '🇸🇦',
        'unknown': '🌐'
    }
    
    return language_flags.get(lang_code, '🌐')
