"""
LLM Client for Classification

Minimal LLM client wrapper for classification prompts with caching.
Prompts are imported from the centralized prompts module.
"""

import os
import json
import hashlib
import time
import re
from typing import List, Dict, Any

from prompts.classification import (
    CLASSIFICATION_SYSTEM,
    build_classification_prompt,
)

CACHE_DIR = os.path.join('.cache', 'llm')


class LLMClient:
    """LLM client wrapper for classification with file-based caching."""

    def __init__(self, model: str = 'gpt-4o', cache_dir: str = None, api_key: str = None):
        self.model = model or 'gpt-4o'
        self.cache_dir = cache_dir or CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')

    def _cache_path(self, key: str) -> str:
        h = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"{self.model}.{h}.json")

    def _read_cache(self, key: str) -> Any:
        p = self._cache_path(key)
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _write_cache(self, key: str, value: Any) -> None:
        try:
            with open(self._cache_path(key), 'w', encoding='utf-8') as f:
                json.dump(value, f)
        except Exception:
            pass

    def _call_openai(self, prompt: str) -> Dict[str, Any]:
        """Make OpenAI API call with few-shot classification prompt."""
        try:
            import openai
        except ImportError as e:
            raise RuntimeError('openai package not available') from e

        if self.api_key:
            openai.api_key = self.api_key

        resp = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=200
        )
        
        text = resp['choices'][0]['message']['content'].strip()
        
        try:
            if '```' in text:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
            return json.loads(text)
        except json.JSONDecodeError:
            return {'raw': text}

    def classify(self, items: List[Dict[str, Any]], rubric_version: str = 'unknown') -> Dict[str, Dict[str, Any]]:
        """Classify a list of items."""
        results = {}
        
        for item in items:
            content_id = item.get('content_id', 'unknown')
            cache_key = f"{content_id}.{rubric_version}.{self.model}.{json.dumps(item.get('meta', {}), sort_keys=True)}.{item.get('final_score')}"
            
            cached = self._read_cache(cache_key)
            if cached is not None:
                results[content_id] = cached
                continue

            item_json = json.dumps(item, ensure_ascii=False, indent=2)
            prompt = build_classification_prompt(item_json)

            try:
                out = self._call_openai(prompt)
                if 'label' not in out or out.get('label') not in ['authentic', 'suspect', 'inauthentic']:
                    out = self._fallback_classification(item)
            except Exception as e:
                out = self._fallback_classification(item)
                out['notes'] = f"Fallback (error: {str(e)[:50]})"

            results[content_id] = out
            self._write_cache(cache_key, out)
            time.sleep(0.05)

        return results

    def _fallback_classification(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback classification based on final_score."""
        fs = float(item.get('final_score') or 0)
        if fs >= 75:
            return {'label': 'authentic', 'confidence': 0.7, 'notes': 'Score-based fallback'}
        elif fs >= 40:
            return {'label': 'suspect', 'confidence': 0.6, 'notes': 'Score-based fallback'}
        else:
            return {'label': 'inauthentic', 'confidence': 0.7, 'notes': 'Score-based fallback'}
