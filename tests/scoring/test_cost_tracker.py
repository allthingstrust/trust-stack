"""
Tests for LLM Cost Tracker.

Tests verify:
- Recording usage from multiple models
- Cost calculation accuracy
- Summary formatting
- Quota alert triggers
- Reset functionality
"""

import pytest
from unittest.mock import patch, MagicMock
import os


class TestCostTracker:
    """Tests for the CostTracker class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        from scoring.cost_tracker import CostTracker
        CostTracker._instance = None
        yield
        CostTracker._instance = None

    def test_record_usage_single_model(self):
        """Test recording usage for a single model."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        cost_tracker.record("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
        
        summary = cost_tracker.get_summary()
        assert "gpt-4o-mini" in summary["models"]
        assert summary["models"]["gpt-4o-mini"]["prompt_tokens"] == 1000
        assert summary["models"]["gpt-4o-mini"]["completion_tokens"] == 500
        assert summary["models"]["gpt-4o-mini"]["calls"] == 1

    def test_record_usage_multiple_models(self):
        """Test recording usage for multiple models."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        cost_tracker.record("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
        cost_tracker.record("gpt-4o", prompt_tokens=2000, completion_tokens=800)
        cost_tracker.record("gpt-4o-mini", prompt_tokens=500, completion_tokens=200)
        
        summary = cost_tracker.get_summary()
        
        # Check individual models
        assert summary["models"]["gpt-4o-mini"]["prompt_tokens"] == 1500
        assert summary["models"]["gpt-4o-mini"]["completion_tokens"] == 700
        assert summary["models"]["gpt-4o-mini"]["calls"] == 2
        
        assert summary["models"]["gpt-4o"]["prompt_tokens"] == 2000
        assert summary["models"]["gpt-4o"]["completion_tokens"] == 800
        assert summary["models"]["gpt-4o"]["calls"] == 1
        
        # Check totals
        assert summary["totals"]["prompt_tokens"] == 3500
        assert summary["totals"]["completion_tokens"] == 1500
        assert summary["totals"]["calls"] == 3

    def test_cost_calculation(self):
        """Test that cost is calculated correctly."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        cost_tracker.record("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
        
        summary = cost_tracker.get_summary()
        expected_cost = 0.15 + 0.60  # $0.75
        
        assert abs(summary["models"]["gpt-4o-mini"]["cost_usd"] - expected_cost) < 0.001

    def test_cost_calculation_multiple_models(self):
        """Test cost calculation with multiple models."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        # gpt-4o-mini: 100K tokens each way
        cost_tracker.record("gpt-4o-mini", prompt_tokens=100_000, completion_tokens=100_000)
        # gpt-4o: 50K tokens each way
        cost_tracker.record("gpt-4o", prompt_tokens=50_000, completion_tokens=50_000)
        
        summary = cost_tracker.get_summary()
        
        # gpt-4o-mini: (100K/1M)*0.15 + (100K/1M)*0.60 = 0.015 + 0.06 = 0.075
        assert abs(summary["models"]["gpt-4o-mini"]["cost_usd"] - 0.075) < 0.001
        
        # gpt-4o: (50K/1M)*2.50 + (50K/1M)*10.00 = 0.125 + 0.50 = 0.625
        assert abs(summary["models"]["gpt-4o"]["cost_usd"] - 0.625) < 0.001
        
        # Total: 0.075 + 0.625 = 0.70
        assert abs(summary["totals"]["cost_usd"] - 0.70) < 0.001

    def test_reset(self):
        """Test reset clears all usage data."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        cost_tracker.record("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
        cost_tracker.reset()
        
        summary = cost_tracker.get_summary()
        assert len(summary["models"]) == 0
        assert summary["totals"]["prompt_tokens"] == 0
        assert summary["totals"]["calls"] == 0

    def test_print_summary_no_calls(self, capsys):
        """Test print_summary with no LLM calls."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        cost_tracker.print_summary()
        # Should not raise, just log a message

    def test_print_summary_with_calls(self, capsys):
        """Test print_summary outputs formatted table."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        cost_tracker.record("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
        cost_tracker.print_summary()
        
        captured = capsys.readouterr()
        assert "LLM Usage Summary" in captured.out
        assert "gpt-4o-mini" in captured.out
        assert "TOTAL" in captured.out

    def test_quota_alert_input_tokens(self, capsys):
        """Test quota alert for input tokens."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        # Set a low threshold for testing
        cost_tracker._quotas = {"warn_input_tokens": 1000}
        cost_tracker.record("gpt-4o-mini", prompt_tokens=2000, completion_tokens=100)
        
        cost_tracker.check_quotas()
        
        captured = capsys.readouterr()
        assert "Input tokens" in captured.out
        assert "exceeded" in captured.out

    def test_quota_alert_output_tokens(self, capsys):
        """Test quota alert for output tokens."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        cost_tracker._quotas = {"warn_output_tokens": 500}
        cost_tracker.record("gpt-4o-mini", prompt_tokens=100, completion_tokens=1000)
        
        cost_tracker.check_quotas()
        
        captured = capsys.readouterr()
        assert "Output tokens" in captured.out
        assert "exceeded" in captured.out

    def test_quota_alert_cost(self, capsys):
        """Test quota alert for cost."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        cost_tracker._quotas = {"warn_cost_usd": 0.01}
        # This will cost more than $0.01
        cost_tracker.record("gpt-4o", prompt_tokens=10_000, completion_tokens=10_000)
        
        cost_tracker.check_quotas()
        
        captured = capsys.readouterr()
        assert "cost" in captured.out.lower()
        assert "exceeded" in captured.out

    def test_unknown_model_uses_fallback_pricing(self):
        """Test that unknown models use fallback pricing."""
        from scoring.cost_tracker import CostTracker
        
        cost_tracker = CostTracker()
        # Use a model not in the pricing config
        cost_tracker.record("unknown-model-xyz", prompt_tokens=1_000_000, completion_tokens=1_000_000)
        
        summary = cost_tracker.get_summary()
        # Should use gpt-4o-mini fallback pricing: $0.15 + $0.60 = $0.75
        assert summary["models"]["unknown-model-xyz"]["cost_usd"] > 0


class TestCostTrackerIntegration:
    """Integration tests for cost tracking with ChatClient."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        from scoring.cost_tracker import CostTracker
        CostTracker._instance = None
        yield
        CostTracker._instance = None

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key-12345'})
    def test_chat_client_records_usage(self):
        """Test that ChatClient records usage to cost tracker."""
        with patch('scoring.llm_client.OpenAI') as mock_openai:
            from scoring.llm_client import ChatClient
            from scoring.cost_tracker import CostTracker
            
            # Reset and get new instance
            CostTracker._instance = None
            new_tracker = CostTracker()
            
            # Mock the OpenAI response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test response"
            mock_response.usage = MagicMock(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150
            )
            
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            # Patch the global cost_tracker used in llm_client
            with patch('scoring.cost_tracker.cost_tracker', new_tracker):
                # Make a chat call
                client = ChatClient()
                client.chat(messages=[{"role": "user", "content": "Test"}], model="gpt-4o-mini")
                
                # Verify usage was recorded
                summary = new_tracker.get_summary()
                assert "gpt-4o-mini" in summary["models"]
                assert summary["models"]["gpt-4o-mini"]["prompt_tokens"] == 100
                assert summary["models"]["gpt-4o-mini"]["completion_tokens"] == 50


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
