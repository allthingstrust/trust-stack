import json
import logging
import sys
import os
import re
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
    
    # Setup Mocks
    mock_evaluator = sys.modules['scoring.key_signal_evaluator'].KeySignalEvaluator()
    mock_client = sys.modules['scoring.llm_client'].ChatClient()
    mock_client.chat.return_value = {
        "content": "Rationale:\n...\n\n🧮 **Diagnostics Snapshot**\n{{DIAGNOSTICS_TABLE}}\n\n📊 **Final Provenance Score: 8.0 / 10**"
    }

    print("\n--- Test: Resonance (6 Signals) ---")
    mock_evaluator.compute_signal_statuses.return_value = {
        "Dynamic Personalization": ("✅", 10.0, []),
        # others missing = 0.0
    }
    
    report_data_res = {
        'brand_id': 'Test Brand',
        'generated_at': '2023-01-01',
        'dimension_breakdown': {'resonance': {'average': 0.8}}, 
        'items': [],
        'sources': []
    }
    
    final_report_res = generate_trust_stack_report(report_data_res)
    
    if "Dynamic Personalization" in final_report_res:
         # 10.0 * (1/6) = 1.666...
         match = re.search(r"\| Dynamic Personalization \| (.*?) points", final_report_res)
         if match:
             print(f"SUCCESS: Resonance (6 signals) rendered. Weight/Score: {match.group(1)}")
         else:
             print("FAILURE: Could not find score in table.")
    else:
         print("FAILURE: Dynamic Personalization not found.")

if __name__ == "__main__":
    test_diagnostics_snapshot()
