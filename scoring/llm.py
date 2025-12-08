import os
import json
import hashlib
import time
from typing import List, Dict, Any

CACHE_DIR = os.path.join('.cache', 'llm')


class LLMClient:
    """Minimal LLM client wrapper for classification prompts with simple file-based caching.

    This wrapper is intentionally small. In production, replace with a robust
    client, rate-limiting, retries, and secure secret handling.
    """

    def __init__(self, model: str = 'gpt-4o', cache_dir: str = None, api_key: str = None):
        self.model = model or 'gpt-4o'
        self.cache_dir = cache_dir or CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')

    def _cache_path(self, key: str) -> str:
        h = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"{self.model}.{h}.json")

    def _read_cache(self, key: str):
        p = self._cache_path(key)
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _write_cache(self, key: str, value: Any):
        p = self._cache_path(key)
        try:
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(value, f)
        except Exception:
            pass

    def _call_openai(self, prompt: str) -> Dict[str, Any]:
        try:
            import openai
        except Exception as e:
            raise RuntimeError('openai package not available') from e

        if self.api_key:
            openai.api_key = self.api_key

        # Use ChatCompletion for gpt-3.5-turbo
        resp = openai.ChatCompletion.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=400
        )
        text = resp['choices'][0]['message']['content']
        # Try to parse JSON from response
        try:
            return json.loads(text)
        except Exception:
            # fallback: return raw text
            return {'raw': text}

    def classify(self, items: List[Dict[str, Any]], rubric_version: str = 'unknown') -> Dict[str, Dict[str, Any]]:
        """Classify a list of items.

        items: list of dicts with keys: content_id, meta, final_score
        Returns mapping: content_id -> {label, confidence, notes}
        """
        results = {}
        # Build a combined cache key for the batch so we cache per-item as well
        for it in items:
            key = f"{it.get('content_id')}.{rubric_version}.{self.model}.{json.dumps(it.get('meta', {}), sort_keys=True)}.{it.get('final_score') }"
            cached = self._read_cache(key)
            if cached is not None:
                results[it['content_id']] = cached
                continue

            # Build a compact prompt asking for a JSON classification
            prompt = (
                f"You are a classifier. Given the following item metadata and a numeric score (0-100),\n"
                f"return a JSON object with keys: label (authentic|suspect|inauthentic), confidence (0.0-1.0), and optional notes.\n"
                f"Item:\n{json.dumps(it, ensure_ascii=False)}\n\nRespond with JSON only."
            )

            try:
                out = self._call_openai(prompt)
            except Exception:
                # Degrade gracefully: pick label based on final_score
                fs = float(it.get('final_score') or 0)
                if fs >= 75:
                    out = {'label': 'authentic', 'confidence': 0.9}
                elif fs >= 40:
                    out = {'label': 'suspect', 'confidence': 0.6}
                else:
                    out = {'label': 'inauthentic', 'confidence': 0.8}

            results[it['content_id']] = out
            # Cache result
            try:
                self._write_cache(key, out)
            except Exception:
                pass
            # small delay to be polite if calling real API
            time.sleep(0.05)

        return results
