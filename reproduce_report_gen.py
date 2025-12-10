import json
import logging
import sys
import os
from unittest.mock import MagicMock
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO)

# Mock modules
sys.modules['scoring.llm_client'] = MagicMock()
sys.modules['scoring.key_signal_evaluator'] = MagicMock()

# Path setup
PROJECT_ROOT = os.getcwd()
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from reporting.trust_stack_report import generate_trust_stack_report, _render_diagnostics_table

def test_diagnostics_snapshot():
    print("Testing Diagnostics Snapshot Generation...")
    
    item1 = {
        'id': 'itm_1',
        'title': 'Test Item',
        'dimension_scores': {'provenance': 0.8},
        'dimension_details': {
            'provenance': {
                'signals': [
                    {'label': 'Author Identity', 'value': 1.0},
                    {'label': 'C2PA Manifest', 'value': 0.5},
                    {'label': 'Domain Trust', 'value': 0.8},
                    {'label': 'Source Clarity', 'value': 0.9},
                    {'label': 'Content Freshness', 'value': 0.7}
                ]
            }
        },
        'meta': {'url': 'http://example.com'}
    }
    
    report_data = {
        'brand_id': 'Test Brand',
        'generated_at': '2023-01-01',
        'dimension_breakdown': {'provenance': {'average': 0.8}},
        'items': [item1],
        'sources': ['test']
    }

    # Setup Mocks
    mock_evaluator = sys.modules['scoring.key_signal_evaluator'].KeySignalEvaluator()
    mock_evaluator.compute_signal_statuses.return_value = {}
    mock_client = sys.modules['scoring.llm_client'].ChatClient()


    # Test 1A: Double Braces
    mock_client.chat.return_value = {
        "content": "Rationale:\n...\n\n🧮 **Diagnostics Snapshot**\n{{DIAGNOSTICS_TABLE}}\n\n📊 **Final Provenance Score: 8.0 / 10**"
    }
    
    print("\n--- Test 1A: Placeholder Injection (Double Braces) ---")
    final_report_a = generate_trust_stack_report(report_data)
    if "| Author Identity |" in final_report_a:
        print("SUCCESS: Double brace placeholder replaced.")
    else:
        print("FAILURE: Double brace not replaced.")
        print(final_report_a[:500])

    # Test 1B: Single Braces
    mock_client.chat.return_value = {
        "content": "Rationale:\n...\n\n🧮 **Diagnostics Snapshot**\n{DIAGNOSTICS_TABLE}\n\n📊 **Final Provenance Score: 8.0 / 10**"
    }
    print("\n--- Test 1B: Placeholder Injection (Single Braces) ---")
    final_report_b = generate_trust_stack_report(report_data)
    if "| Author Identity |" in final_report_b:
        print("SUCCESS: Single brace placeholder replaced.")
    else:
        print("FAILURE: Single brace not replaced.")
        print(final_report_b[:500])

if __name__ == "__main__":
    test_diagnostics_snapshot()
