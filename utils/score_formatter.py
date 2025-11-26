"""
Score formatting utilities for Trust Stack Rating tool
Handles conversion between internal 0-1 scale and display 0-10 scale
"""

from typing import Union


def to_display_score(internal_score: Union[float, int]) -> float:
    """
    Convert internal score (0-1 scale) to display score (0-10 scale)
    
    Args:
        internal_score: Score on 0-1 scale
        
    Returns:
        Score on 0-10 scale, rounded to 1 decimal place
    """
    if internal_score is None:
        return 0.0
    return round(float(internal_score) * 10, 1)


def to_internal_score(display_score: Union[float, int]) -> float:
    """
    Convert display score (0-10 scale) to internal score (0-1 scale)
    
    Args:
        display_score: Score on 0-10 scale
        
    Returns:
        Score on 0-1 scale
    """
    if display_score is None:
        return 0.0
    return round(float(display_score) / 10, 3)


def format_score_display(internal_score: Union[float, int], include_max: bool = True) -> str:
    """
    Format score for display with optional "/ 10" suffix
    
    Args:
        internal_score: Score on 0-1 scale
        include_max: If True, append "/ 10" to the score
        
    Returns:
        Formatted score string (e.g., "7.5 / 10" or "7.5")
    """
    display = to_display_score(internal_score)
    if include_max:
        return f"{display} / 10"
    return str(display)


def get_score_status(internal_score: Union[float, int]) -> str:
    """
    Get status indicator for a score
    
    Args:
        internal_score: Score on 0-1 scale
        
    Returns:
        Status string with emoji (e.g., "🟢 Excellent", "🟡 Good", etc.)
    """
    display = to_display_score(internal_score)
    
    if display >= 8.0:
        return "🟢 Excellent"
    elif display >= 6.0:
        return "🟡 Good"
    elif display >= 4.0:
        return "🟠 Moderate"
    else:
        return "🔴 Poor"


def get_score_emoji(internal_score: Union[float, int]) -> str:
    """
    Get emoji indicator for a score (for use in key signal evaluations)
    
    Args:
        internal_score: Score on 0-1 scale
        
    Returns:
        Emoji string (✅, ⚠️, or ❌)
    """
    display = to_display_score(internal_score)
    
    if display >= 7.0:
        return "✅"
    elif display >= 4.0:
        return "⚠️"
    else:
        return "❌"
