"""
LLM Cost Tracker for Trust Stack Rating Tool

Tracks token usage across all LLM calls in a run and provides
per-model cost breakdowns with quota alerts.
"""

import logging
import os
from collections import defaultdict
from typing import Dict, Optional, Any

import yaml

logger = logging.getLogger(__name__)

# Default pricing if config file is missing (per 1M tokens, USD)
# Default pricing if config file is missing (per 1M tokens, USD)
DEFAULT_PRICING = {
    'gpt-4o': {'input': 2.50, 'output': 10.00},
    'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
    'gpt-3.5-turbo': {'input': 0.50, 'output': 1.50},
    'claude-3-5-sonnet-20241022': {'input': 3.00, 'output': 15.00},
    'claude-3-5-haiku-20241022': {'input': 1.00, 'output': 5.00},
    'claude-3-opus-20240229': {'input': 15.00, 'output': 75.00},
    'gemini-1.5-pro': {'input': 1.25, 'output': 5.00},
    'gemini-1.5-flash': {'input': 0.075, 'output': 0.30},
    'deepseek-chat': {'input': 0.14, 'output': 0.28},
}

DEFAULT_QUOTAS = {
    'warn_input_tokens': 100000,
    'warn_output_tokens': 50000,
    'warn_cost_usd': 1.00,
}


class CostTracker:
    """Singleton class to track LLM usage and costs across a run."""

    _instance: Optional['CostTracker'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._usage: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {'prompt_tokens': 0, 'completion_tokens': 0, 'calls': 0}
        )
        self._pricing: Dict[str, Dict[str, float]] = {}
        self._quotas: Dict[str, float] = {}
        self._load_config()

    def _load_config(self):
        """Load pricing and quota config from YAML file."""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'config', 'llm_pricing.yml'
        )
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                self._pricing = config.get('models', DEFAULT_PRICING)
                self._quotas = config.get('quotas', DEFAULT_QUOTAS)
                logger.debug(f"Loaded LLM pricing config from {config_path}")
            else:
                logger.warning(f"LLM pricing config not found at {config_path}, using defaults")
                self._pricing = DEFAULT_PRICING
                self._quotas = DEFAULT_QUOTAS
        except Exception as e:
            logger.warning(f"Error loading LLM pricing config: {e}, using defaults")
            self._pricing = DEFAULT_PRICING
            self._quotas = DEFAULT_QUOTAS

    def record(self, model: str, prompt_tokens: int, completion_tokens: int):
        """Record token usage for a model."""
        self._usage[model]['prompt_tokens'] += prompt_tokens
        self._usage[model]['completion_tokens'] += completion_tokens
        self._usage[model]['calls'] += 1
        logger.debug(f"Recorded usage for {model}: +{prompt_tokens} input, +{completion_tokens} output")

    def _get_model_pricing(self, model: str) -> Dict[str, float]:
        """Get pricing for a model."""
        # Exact match
        if model in self._pricing:
            return self._pricing[model]
        
        # Sort known models by length (descending) to prioritize specific matches
        # e.g. 'claude-3-opus' should match before 'claude-3' if both exist
        sorted_models = sorted(self._pricing.keys(), key=len, reverse=True)
        
        # Prefix match
        for known_model in sorted_models:
            if model.startswith(known_model):
                return self._pricing[known_model]
        
        # Default fallback - assume gpt-4o-mini pricing
        logger.warning(f"Unknown model pricing for '{model}', using gpt-4o-mini rates")
        return self._pricing.get('gpt-4o-mini', {'input': 0.15, 'output': 0.60})

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost in USD for given token counts."""
        pricing = self._get_model_pricing(model)
        input_cost = (prompt_tokens / 1_000_000) * pricing['input']
        output_cost = (completion_tokens / 1_000_000) * pricing['output']
        return input_cost + output_cost

    def get_summary(self) -> Dict[str, Any]:
        """Get usage summary with per-model breakdown and totals."""
        summary = {
            'models': {},
            'totals': {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0,
                'calls': 0,
                'cost_usd': 0.0,
            }
        }

        for model, usage in self._usage.items():
            prompt_tokens = usage['prompt_tokens']
            completion_tokens = usage['completion_tokens']
            calls = usage['calls']
            cost = self._calculate_cost(model, prompt_tokens, completion_tokens)

            summary['models'][model] = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': prompt_tokens + completion_tokens,
                'calls': calls,
                'cost_usd': cost,
            }

            summary['totals']['prompt_tokens'] += prompt_tokens
            summary['totals']['completion_tokens'] += completion_tokens
            summary['totals']['total_tokens'] += prompt_tokens + completion_tokens
            summary['totals']['calls'] += calls
            summary['totals']['cost_usd'] += cost

        return summary

    def print_summary(self):
        """Print formatted usage summary to terminal."""
        summary = self.get_summary()
        
        if not summary['models']:
            logger.info("No LLM calls recorded in this run.")
            return

        # Build formatted table
        lines = []
        lines.append("")
        lines.append("╔═══════════════════════════════════════════════════════════════════╗")
        lines.append("║                        LLM Usage Summary                          ║")
        lines.append("╠═══════════════════════════╦════════════╦═════════════╦════════════╣")
        lines.append("║ Model                     ║ Input Tok  ║ Output Tok  ║ Est. Cost  ║")
        lines.append("╠═══════════════════════════╬════════════╬═════════════╬════════════╣")

        for model, data in sorted(summary['models'].items()):
            model_display = model[:25] if len(model) <= 25 else model[:22] + "..."
            lines.append(
                f"║ {model_display:<25} ║ {data['prompt_tokens']:>10,} ║ {data['completion_tokens']:>11,} ║ ${data['cost_usd']:>8.4f} ║"
            )

        lines.append("╠═══════════════════════════╬════════════╬═════════════╬════════════╣")
        totals = summary['totals']
        lines.append(
            f"║ {'TOTAL':<25} ║ {totals['prompt_tokens']:>10,} ║ {totals['completion_tokens']:>11,} ║ ${totals['cost_usd']:>8.4f} ║"
        )
        lines.append("╚═══════════════════════════╩════════════╩═════════════╩════════════╝")
        lines.append(f"  Total API Calls: {totals['calls']}")
        lines.append("")

        # Print to terminal via logging (INFO level)
        for line in lines:
            print(line)

    def check_quotas(self):
        """Check if usage exceeds quota thresholds and log warnings."""
        summary = self.get_summary()
        totals = summary['totals']
        warnings = []

        if totals['prompt_tokens'] > self._quotas.get('warn_input_tokens', float('inf')):
            warnings.append(
                f"⚠️  Input tokens ({totals['prompt_tokens']:,}) exceeded threshold "
                f"({self._quotas['warn_input_tokens']:,})"
            )

        if totals['completion_tokens'] > self._quotas.get('warn_output_tokens', float('inf')):
            warnings.append(
                f"⚠️  Output tokens ({totals['completion_tokens']:,}) exceeded threshold "
                f"({self._quotas['warn_output_tokens']:,})"
            )

        if totals['cost_usd'] > self._quotas.get('warn_cost_usd', float('inf')):
            warnings.append(
                f"⚠️  Estimated cost (${totals['cost_usd']:.4f}) exceeded threshold "
                f"(${self._quotas['warn_cost_usd']:.2f})"
            )

        for warning in warnings:
            print(warning)
            logger.warning(warning)

    def reset(self):
        """Reset usage counters for a new run."""
        self._usage.clear()
        self._usage = defaultdict(
            lambda: {'prompt_tokens': 0, 'completion_tokens': 0, 'calls': 0}
        )
        logger.debug("Cost tracker reset")


# Global singleton instance
cost_tracker = CostTracker()
