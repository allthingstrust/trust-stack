import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reporting.trust_stack_report import _render_diagnostics_table, TRUST_STACK_DIMENSIONS, KEY_SIGNAL_TO_SIGNAL_ID

class TestDiagnosticsTable(unittest.TestCase):

    @patch('reporting.trust_stack_report._load_signal_config')
    def test_render_diagnostics_table_format(self, mock_load_config):
        # Mock config
        # signals: S1 (0.2), S2 (0.3)
        mock_load_config.return_value = {
            "sig_1": {"weight": 0.2, "requirement_level": "core"},
            "sig_2": {"weight": 0.3, "requirement_level": "amplifier"},
        }
        
        # Patch TRUST_STACK_DIMENSIONS temporarily for this test
        # We need to map key signal labels to IDs
        with patch.dict(TRUST_STACK_DIMENSIONS, {
            "test_dim": {"signals": ["Signal 1", "Signal 2"]}
        }, clear=True), patch.dict(KEY_SIGNAL_TO_SIGNAL_ID, {
            "Signal 1": "sig_1",
            "Signal 2": "sig_2"
        }, clear=True):
            
            dimension = "test_dim"
            fallback_score = 5.0
            
            # Key signal statuses: label -> (status_icon, avg_score, evidence)
            key_signal_statuses = {
                "Signal 1": ("✅", 8.0, []),
                "Signal 2": ("⚠️", 4.0, []),
            }
            
            # Render table
            output = _render_diagnostics_table(dimension, key_signal_statuses, fallback_score)
            
            print("\nGenerated Table:\n")
            print(output)
            print("\n----------------\n")
            
            # Assertions
            # Check for new headers
            # Expected: | Metric | Raw Score | Weight | Weighted Score | (or similar based on final text)
            # The current implementation (before my changes) has: | Metric | Contribution |
            
            # Once I update the code, I expect: | Attribute | Attribute Raw Score | Weight Percentage | Weighted Score |
            
            # Verify row content
            # Signal 1: Raw 8.0, Weight 0.2 (20%), Weighted contribution?
            # Weighted calculation:
            # S1 (8.0, 0.2), S2 (4.0, 0.3)
            # Weighted sum = 8.0*0.2 + 4.0*0.3 = 1.6 + 1.2 = 2.8
            # S1 contribution = (1.6 / 2.8) * 5.0 ~ 0.57 * 5.0 = 2.85 -> 2.9
            # S2 contribution = (1.2 / 2.8) * 5.0 ~ 0.43 * 5.0 = 2.14 -> 2.1
            # Sum = 5.0
            
            # This test will initially FAIL or show OLD format. 
            # I will use this to confirm the change.
            return output

if __name__ == '__main__':
    unittest.main()
