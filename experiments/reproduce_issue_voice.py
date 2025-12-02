
import sys
import os
import json

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webapp.utils.recommendations import get_remedy_for_issue

def reproduce():
    # Mock issue item as it might come from the scorer/LLM
    # The user provided:
    # Issue: Inconsistent Voice
    # Evidence: EXACT QUOTE: 'HOME TOOTHPASTE A TOOTHPASTE FOR EVERY SMILE...'
    
    mock_items = [
        {
            "issue": "Inconsistent Voice",
            "evidence": "EXACT QUOTE: 'HOME TOOTHPASTE A TOOTHPASTE FOR EVERY SMILE The first ever toothpaste to be recognized by the ADA to be proven effective against cavities, now with specialized formulas to help personalize your oral care'",
            "title": "Shop our Best Toothpastes for a good oral hygiene | Crest US",
            "url": "https://crest.com/en-us/oral-care-products/toothpaste",
            "value": 4.0,
            "confidence": 0.85,
            # Simulating what the LLM might have returned as a suggestion
            # If the LLM didn't return a suggestion, this might be empty or generic
            "suggestion": "Ensure the same voice is used across all channels and content types." 
        }
    ]
    
    print("Generating remedy for Inconsistent Voice...")
    remedy_data = get_remedy_for_issue("Inconsistent Voice", "coherence", mock_items)
    
    print("\n--- Generated Remedy ---")
    print(f"Recommended Fix:\n{remedy_data['recommended_fix']}")
    print(f"\nGeneral Best Practice:\n{remedy_data['general_best_practice']}")
    print("------------------------")

    # Check if the output contains specific feedback
    if "run-on sentence" in remedy_data['recommended_fix'].lower() or "structure" in remedy_data['recommended_fix'].lower():
        print("Specific feedback found.")
    else:
        print("Specific feedback NOT found (reproduced).")

if __name__ == "__main__":
    reproduce()
