import json
import os
from typing import Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
RUBRIC_PATH = os.path.join(PROJECT_ROOT, "config", "rubric.json")

DEFAULT_RUBRIC: Dict[str, Any] = {
    "version": "1.0",
    "dimension_weights": {
        "provenance": 0.14705882352941177,
        "resonance": 0.17647058823529413,
        "coherence": 0.2647058823529412,
        "transparency": 0.16176470588235295,
        "verification": 0.25,
    },
    "thresholds": {"authentic": 75, "suspect": 40},
    "attributes": [],
    "defaults": {
        "max_total_bonus": 50,
        "max_total_penalty": -50,
        "normalize_weights": True,
        "max_llm_items": 10,
        "llm_model": "gpt-3.5-turbo",
        "triage_method": "top_uncertain",
        "max_llm_cost_per_run": None,
    },
}



def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(weights.values())
    if not total:
        return weights
    return {k: float(v) / float(total) for k, v in weights.items()}


def load_rubric(path: str = None) -> Dict[str, Any]:
    """Load rubric JSON from `config/rubric.json` with validation and fallbacks.

    Returns a dict with keys: dimension_weights, thresholds, attributes, defaults
    """
    p = path or RUBRIC_PATH
    if not os.path.exists(p):
        return DEFAULT_RUBRIC.copy()

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return DEFAULT_RUBRIC.copy()

    # Basic validation and fill defaults
    dim = data.get("dimension_weights", DEFAULT_RUBRIC["dimension_weights"])
    defaults = data.get("defaults", DEFAULT_RUBRIC["defaults"])
    if defaults.get("normalize_weights", True):
        dim = _normalize_weights(dim)

    thresholds = data.get("thresholds", DEFAULT_RUBRIC["thresholds"])
    attributes = data.get("attributes", DEFAULT_RUBRIC["attributes"])

    score_multipliers = data.get("score_multipliers", DEFAULT_RUBRIC.get("score_multipliers", {}))

    # Load trust signals config
    trust_signals = {}
    signals_path = os.path.join(PROJECT_ROOT, "scoring", "config", "trust_signals.yml")
    if os.path.exists(signals_path):
        try:
            import yaml
            with open(signals_path, "r", encoding="utf-8") as f:
                trust_signals = yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Failed to load trust_signals.yml: {e}")
            # Fallback or empty dict
            pass

    return {
        "version": data.get("version", DEFAULT_RUBRIC.get("version")),
        "dimension_weights": dim,
        "thresholds": thresholds,
        "attributes": attributes,
        "defaults": defaults,
        "score_multipliers": score_multipliers,
        "trust_signals": trust_signals, # New field
    }


if __name__ == "__main__":
    import pprint

    pprint.pprint(load_rubric())
