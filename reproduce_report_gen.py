import json
import logging
from typing import Dict, List, Any

# Mock the KeySignalEvaluator to avoid external dependencies
import sys
from unittest.mock import MagicMock

# Configure logging
logging.basicConfig(level=logging.INFO)

# Mock modules that might be missing or require dependencies
sys.modules['scoring.llm_client'] = MagicMock()
sys.modules['scoring.key_signal_evaluator'] = MagicMock()

# Import the report generator
# We need to make sure the project root is in path
import os
PROJECT_ROOT = os.getcwd()
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from reporting.trust_stack_report import generate_trust_stack_report, _render_diagnostics_table

def test_diagnostics_snapshot():
    print("Testing Diagnostics Snapshot Generation...")
    
    # Mock ChatClient returns
    mock_client = sys.modules['scoring.llm_client'].ChatClient()
    mock_client.chat.return_value = {"content": "Mocked LLM Analysis"}

    # Mock KeySignalEvaluator returns
    mock_evaluator = sys.modules['scoring.key_signal_evaluator'].KeySignalEvaluator()
    mock_evaluator.compute_signal_statuses.return_value = {}

    # Create mock items with signals for Provenance (5 signals mock)
    # We simulate aggregated signals by providing pre-computed dimension details or mocked items
    # The _compute_diagnostics_from_signals function looks for 'dimension_details' or 'meta'
    
    # Let's create items that effectively have signal scores
    # Since we can't easily mock the internal _compute_diagnostics_from_signals logic without
    # full object structures, let's mock the input to _render_diagnostics_table directly first
    # to test the formatting logic, which is what we changed.
    
    print("\n--- Test 1: Direct function test (Provenance: 2 signals) ---")
    items_direct = [] # Unused in this direct test of logic with mocked internal call if we could, 
                      # but we can't easily mock the internal call.
                      # Instead, let's construct items that WILL be parsed correctly.
    
    # We need to see how _compute_diagnostics_from_signals parses items.
    # It looks for item.get('dimension_details', {}).get(dimension).get('signals', [])
    
    item1 = {
        'dimension_details': {
            'provenance': {
                'signals': [
                    {'label': 'Author Identity', 'value': 1.0}, # 1.0 * 10 = 10.0
                    {'label': 'C2PA Manifest', 'value': 0.5},   # 0.5 * 10 = 5.0
                    {'label': 'Domain Trust', 'value': 0.8},    # 0.8 * 10 = 8.0
                    {'label': 'Source Clarity', 'value': 0.9},  # 0.9 * 10 = 9.0
                    {'label': 'Content Freshness', 'value': 0.7}# 0.7 * 10 = 7.0
                ]
            }
        }
    }
    
    # Render table for Provenance
    table_prov = _render_diagnostics_table('provenance', [item1], 0.0)
    print(table_prov)
    
    # Expected: 5 signals -> Weight = 0.2
    # Author Identity: 10.0 * 0.2 = 2.0
    # C2PA: 5.0 * 0.2 = 1.0
    
    print("\n--- Test 2: Resonance (4 signals) ---")
    item2 = {
        'dimension_details': {
            'resonance': {
                'signals': [
                    {'label': 'Signal A', 'value': 1.0},
                    {'label': 'Signal B', 'value': 1.0},
                    {'label': 'Signal C', 'value': 1.0},
                    {'label': 'Signal D', 'value': 1.0}
                ]
            }
        }
    }
    # Render table for Resonance
    table_res = _render_diagnostics_table('resonance', [item2], 0.0)
    print(table_res)
    # Expected: 4 signals -> Weight = 0.25
    # Signal A: 10.0 * 0.25 = 2.5
    
    print("\n--- Test 3: Null case (No signals) ---")
    table_null = _render_diagnostics_table('provenance', [], 5.0)
    print(table_null)

if __name__ == "__main__":
    test_diagnostics_snapshot()
