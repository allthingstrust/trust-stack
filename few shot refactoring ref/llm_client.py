"""
Multi-provider LLM ChatClient for text summarization and analysis.

Supports: OpenAI, Anthropic Claude, Google Gemini, DeepSeek.
Prompts are imported from the centralized prompts module.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from prompts.summarization import build_summarization_prompt

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    Anthropic = None
    ANTHROPIC_AVAILABLE = False

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    GOOGLE_AVAILABLE = True
except ImportError:
    genai = None
    GenerationConfig = None
    GOOGLE_AVAILABLE = False

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"


class ChatClient:
    """Multi-provider chat client for LLM text generation."""

    PROVIDER_PATTERNS = {
        LLMProvider.ANTHROPIC: ['claude-'],
        LLMProvider.GOOGLE: ['gemini-'],
        LLMProvider.DEEPSEEK: ['deepseek-'],
        LLMProvider.OPENAI: ['gpt-', 'o1-', 'text-'],
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = 'gpt-4o',
        anthropic_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
        deepseek_api_key: Optional[str] = None
    ):
        self.default_model = default_model
        self._openai_client = None
        self._anthropic_client = None
        self._google_initialized = False
        self._deepseek_client = None

        self.openai_api_key = api_key or os.environ.get('OPENAI_API_KEY')
        self.anthropic_api_key = anthropic_api_key or os.environ.get('ANTHROPIC_API_KEY')
        self.google_api_key = google_api_key or os.environ.get('GOOGLE_API_KEY')
        self.deepseek_api_key = deepseek_api_key or os.environ.get('DEEPSEEK_API_KEY')

        if not self.openai_api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY.")

        if OPENAI_AVAILABLE:
            try:
                self._openai_client = OpenAI(api_key=self.openai_api_key)
            except Exception:
                pass

    def _detect_provider(self, model: str) -> LLMProvider:
        for provider, patterns in self.PROVIDER_PATTERNS.items():
            if any(model.startswith(p) for p in patterns):
                return provider
        return LLMProvider.OPENAI

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not OPENAI_AVAILABLE:
                raise ImportError("openai package not installed")
            self._openai_client = OpenAI(api_key=self.openai_api_key)
        return self._openai_client

    @property
    def anthropic_client(self):
        if self._anthropic_client is None:
            if not ANTHROPIC_AVAILABLE:
                raise ImportError("anthropic package not installed")
            if not self.anthropic_api_key:
                raise ValueError("Anthropic API key not configured")
            self._anthropic_client = Anthropic(api_key=self.anthropic_api_key)
        return self._anthropic_client

    @property
    def deepseek_client(self):
        if self._deepseek_client is None:
            if not OPENAI_AVAILABLE:
                raise ImportError("openai package not installed")
            if not self.deepseek_api_key:
                raise ValueError("DeepSeek API key not configured")
            self._deepseek_client = OpenAI(api_key=self.deepseek_api_key, base_url="https://api.deepseek.com")
        return self._deepseek_client

    def _init_google(self):
        if not self._google_initialized:
            if not GOOGLE_AVAILABLE:
                raise ImportError("google-generativeai package not installed")
            if not self.google_api_key:
                raise ValueError("Google API key not configured")
            genai.configure(api_key=self.google_api_key)
            self._google_initialized = True

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 150,
        temperature: float = 0.3,
        **kwargs
    ) -> Dict[str, Any]:
        """Send chat completion request to appropriate provider."""
        model = model or self.default_model
        provider = self._detect_provider(model)
        
        dispatch = {
            LLMProvider.OPENAI: self._chat_openai,
            LLMProvider.ANTHROPIC: self._chat_anthropic,
            LLMProvider.GOOGLE: self._chat_google,
            LLMProvider.DEEPSEEK: self._chat_deepseek,
        }
        
        try:
            return dispatch[provider](messages, model, max_tokens, temperature, **kwargs)
        except Exception as e:
            logger.error(f"Chat error ({provider.value}/{model}): {e}")
            raise

    def _chat_openai(self, messages, model, max_tokens, temperature, **kwargs):
        response = self.openai_client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, temperature=temperature, **kwargs
        )
        content = response.choices[0].message.content
        usage = response.usage if hasattr(response, 'usage') else None
        return {
            'content': content, 'text': content, 'model': model, 'provider': 'openai',
            'usage': {'prompt_tokens': getattr(usage, 'prompt_tokens', 0),
                      'completion_tokens': getattr(usage, 'completion_tokens', 0),
                      'total_tokens': getattr(usage, 'total_tokens', 0)} if usage else {}
        }

    def _chat_anthropic(self, messages, model, max_tokens, temperature, **kwargs):
        system_msg = None
        conv = []
        for m in messages:
            if m['role'] == 'system':
                system_msg = m['content']
            else:
                conv.append({'role': m['role'], 'content': m['content']})
        if not conv and system_msg:
            conv = [{'role': 'user', 'content': system_msg}]
            system_msg = None
        
        api_kwargs = {'model': model, 'max_tokens': max_tokens, 'temperature': temperature, 'messages': conv, **kwargs}
        if system_msg:
            api_kwargs['system'] = [{"type": "text", "text": system_msg}]
        
        response = self.anthropic_client.messages.create(**api_kwargs)
        content = response.content[0].text
        usage = response.usage if hasattr(response, 'usage') else None
        return {
            'content': content, 'text': content, 'model': model, 'provider': 'anthropic',
            'usage': {'prompt_tokens': getattr(usage, 'input_tokens', 0),
                      'completion_tokens': getattr(usage, 'output_tokens', 0),
                      'total_tokens': getattr(usage, 'input_tokens', 0) + getattr(usage, 'output_tokens', 0)} if usage else {}
        }

    def _chat_google(self, messages, model, max_tokens, temperature, **kwargs):
        self._init_google()
        gemini_msgs = [{'role': 'user' if m['role'] in ['user', 'system'] else 'model', 'parts': [m['content']]} for m in messages]
        gemini_model = genai.GenerativeModel(model)
        config = GenerationConfig(max_output_tokens=max_tokens, temperature=temperature)
        
        if len(gemini_msgs) == 1:
            response = gemini_model.generate_content(gemini_msgs[0]['parts'][0], generation_config=config)
        else:
            chat = gemini_model.start_chat(history=gemini_msgs[:-1])
            response = chat.send_message(gemini_msgs[-1]['parts'][0], generation_config=config)
        
        content = response.text
        usage = getattr(response, 'usage_metadata', None)
        return {
            'content': content, 'text': content, 'model': model, 'provider': 'google',
            'usage': {'prompt_tokens': getattr(usage, 'prompt_token_count', 0),
                      'completion_tokens': getattr(usage, 'candidates_token_count', 0),
                      'total_tokens': getattr(usage, 'total_token_count', 0)} if usage else {}
        }

    def _chat_deepseek(self, messages, model, max_tokens, temperature, **kwargs):
        response = self.deepseek_client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, temperature=temperature, **kwargs
        )
        content = response.choices[0].message.content
        usage = response.usage if hasattr(response, 'usage') else None
        return {
            'content': content, 'text': content, 'model': model, 'provider': 'deepseek',
            'usage': {'prompt_tokens': getattr(usage, 'prompt_tokens', 0),
                      'completion_tokens': getattr(usage, 'completion_tokens', 0),
                      'total_tokens': getattr(usage, 'total_tokens', 0)} if usage else {}
        }

    def summarize(self, text: str, max_words: int = 120, model: Optional[str] = None) -> Optional[str]:
        """Summarize text using few-shot prompting."""
        if not text or not text.strip():
            return None
        prompt = build_summarization_prompt(text, max_words)
        try:
            response = self.chat(messages=[{"role": "user", "content": prompt}], model=model, max_tokens=min(300, max_words * 2))
            return response.get('content') or response.get('text')
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return None
