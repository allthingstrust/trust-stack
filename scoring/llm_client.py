"""
Multi-provider LLM ChatClient for text summarization and analysis.

This module provides a unified ChatClient implementation that supports multiple LLM providers:
- OpenAI (GPT-3.5, GPT-4, GPT-4o)
- Anthropic Claude (Sonnet, Haiku, Opus)
- Google Gemini (Pro, Flash)
- DeepSeek (Chat, Reasoner)

The provider is auto-detected based on the model name.

Configuration:
    OPENAI_API_KEY: OpenAI API key
    ANTHROPIC_API_KEY: Anthropic API key
    GOOGLE_API_KEY: Google Gemini API key
    DEEPSEEK_API_KEY: DeepSeek API key

Example usage:
    client = ChatClient()

    # Use OpenAI
    response = client.chat(
        model='gpt-4o',
        messages=[{'role': 'user', 'content': 'Summarize this text...'}],
        max_tokens=150
    )

    # Use Claude
    response = client.chat(
        model='claude-3-5-sonnet-20241022',
        messages=[{'role': 'user', 'content': 'Summarize this text...'}],
        max_tokens=150
    )

    summary = response.get('content')
"""

import os
import logging
from typing import Dict, Any, List, Optional
from enum import Enum

# Import OpenAI
try:
    from openai import OpenAI
    from openai import OpenAIError
except Exception:
    OpenAI = None
    OpenAIError = Exception

# Import Anthropic
try:
    from anthropic import Anthropic
    from anthropic import AnthropicError
except Exception:
    Anthropic = None
    AnthropicError = Exception

# Import Google Gemini
try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    GOOGLE_AVAILABLE = True
except Exception:
    genai = None
    GenerationConfig = None
    GOOGLE_AVAILABLE = False

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"


class ChatClient:
    """
    Multi-provider chat client for LLM text generation.

    This client supports multiple LLM providers and auto-detects the provider
    based on the model name. It provides a unified interface across all providers.

    Supported Providers:
        - OpenAI: gpt-3.5-turbo, gpt-4, gpt-4o, gpt-4o-mini
        - Anthropic: claude-3-5-sonnet-20241022, claude-3-haiku-20240307, claude-3-opus-*
        - Google: gemini-1.5-pro, gemini-1.5-flash, gemini-pro
        - DeepSeek: deepseek-chat, deepseek-reasoner

    Configuration:
        - OPENAI_API_KEY: OpenAI API key
        - ANTHROPIC_API_KEY: Anthropic API key
        - GOOGLE_API_KEY: Google Gemini API key
        - DEEPSEEK_API_KEY: DeepSeek API key

    Raises:
        ImportError: If required package is not installed for the provider
        ValueError: If API key is not configured for the provider
    """

    # Model name patterns for provider detection
    PROVIDER_PATTERNS = {
        LLMProvider.ANTHROPIC: ['claude-'],
        LLMProvider.GOOGLE: ['gemini-'],
        LLMProvider.DEEPSEEK: ['deepseek-'],
        LLMProvider.OPENAI: ['gpt-', 'o1-', 'text-'],  # Default fallback
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = 'gpt-4o',
        anthropic_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
        deepseek_api_key: Optional[str] = None
    ):
        """
        Initialize ChatClient with API credentials.

        Args:
            api_key: OpenAI API key (optional, will use OPENAI_API_KEY env var)
            default_model: Default model to use (default: gpt-3.5-turbo)
            anthropic_api_key: Anthropic API key (optional, will use ANTHROPIC_API_KEY env var)
            google_api_key: Google API key (optional, will use GOOGLE_API_KEY env var)
            deepseek_api_key: DeepSeek API key (optional, will use DEEPSEEK_API_KEY env var)

        Raises:
            ValueError: If API key is not configured for the default provider
        """
        self.default_model = default_model

        # Initialize provider clients (lazy initialization on first use)
        self.openai_client = None
        self.anthropic_client = None
        self.google_client_initialized = False
        self.deepseek_client = None

        # Store API keys
        self.openai_api_key = api_key or os.environ.get('OPENAI_API_KEY')
        self.anthropic_api_key = anthropic_api_key or os.environ.get('ANTHROPIC_API_KEY')
        self.google_api_key = google_api_key or os.environ.get('GOOGLE_API_KEY')
        self.deepseek_api_key = deepseek_api_key or os.environ.get('DEEPSEEK_API_KEY')

        logger.info(f"ChatClient initialized with default model: {default_model}")
        logger.info(f"Available providers: OpenAI={bool(self.openai_api_key)}, "
                   f"Anthropic={bool(self.anthropic_api_key)}, "
                   f"Google={bool(self.google_api_key)}, "
                   f"DeepSeek={bool(self.deepseek_api_key)}")
        # Eagerly initialize OpenAI client and require API key for local tests
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable")

        if OpenAI is not None:
            try:
                self.openai_client = OpenAI(api_key=self.openai_api_key)
            except Exception:
                # Keep None if construction fails; underlying calls will raise later
                self.openai_client = None

    def _detect_provider(self, model: str) -> LLMProvider:
        """
        Detect the LLM provider based on the model name.

        Args:
            model: Model name

        Returns:
            LLMProvider enum value
        """
        for provider, patterns in self.PROVIDER_PATTERNS.items():
            for pattern in patterns:
                if model.startswith(pattern):
                    return provider
        # Default to OpenAI
        return LLMProvider.OPENAI

    def _get_openai_client(self) -> Any:
        """Lazy initialization of OpenAI client"""
        if self.openai_client is None:
            if not self.openai_api_key:
                raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable")
            if OpenAI is None:
                raise ImportError("OpenAI package not installed. Install with: pip install openai")
            self.openai_client = OpenAI(api_key=self.openai_api_key)
        return self.openai_client

    def _get_anthropic_client(self) -> Any:
        """Lazy initialization of Anthropic client"""
        if self.anthropic_client is None:
            if not self.anthropic_api_key:
                raise ValueError("Anthropic API key not configured. Set ANTHROPIC_API_KEY environment variable")
            if Anthropic is None:
                raise ImportError("Anthropic package not installed. Install with: pip install anthropic")
            self.anthropic_client = Anthropic(api_key=self.anthropic_api_key)
        return self.anthropic_client

    def _init_google_client(self):
        """Lazy initialization of Google Gemini client"""
        if not self.google_client_initialized:
            if not self.google_api_key:
                raise ValueError("Google API key not configured. Set GOOGLE_API_KEY environment variable")
            if not GOOGLE_AVAILABLE:
                raise ImportError("Google Generative AI package not installed. Install with: pip install google-generativeai")
            genai.configure(api_key=self.google_api_key)
            self.google_client_initialized = True

    def _get_deepseek_client(self) -> Any:
        """Lazy initialization of DeepSeek client (uses OpenAI-compatible API)"""
        if self.deepseek_client is None:
            if not self.deepseek_api_key:
                raise ValueError("DeepSeek API key not configured. Set DEEPSEEK_API_KEY environment variable")
            if OpenAI is None:
                raise ImportError("OpenAI package not installed. Install with: pip install openai")
            # DeepSeek uses OpenAI-compatible API
            self.deepseek_client = OpenAI(
                api_key=self.deepseek_api_key,
                base_url="https://api.deepseek.com"
            )
        return self.deepseek_client

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 150,
        temperature: float = 0.3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send a chat completion request to the appropriate LLM provider.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model to use (auto-detects provider, defaults to default_model)
            max_tokens: Maximum tokens to generate (default: 150)
            temperature: Sampling temperature 0-1 (default: 0.3)
            **kwargs: Additional arguments to pass to the provider API

        Returns:
            Dict with 'content' or 'text' key containing the response text

        Raises:
            Various provider-specific errors if API request fails
        """
        if model is None:
            model = self.default_model

        provider = self._detect_provider(model)
        logger.info(f"Using provider {provider.value} for model {model}")

        try:
            if provider == LLMProvider.OPENAI:
                return self._chat_openai(messages, model, max_tokens, temperature, **kwargs)
            elif provider == LLMProvider.ANTHROPIC:
                return self._chat_anthropic(messages, model, max_tokens, temperature, **kwargs)
            elif provider == LLMProvider.GOOGLE:
                return self._chat_google(messages, model, max_tokens, temperature, **kwargs)
            elif provider == LLMProvider.DEEPSEEK:
                return self._chat_deepseek(messages, model, max_tokens, temperature, **kwargs)
            else:
                raise ValueError(f"Unsupported provider: {provider}")

        except Exception as e:
            logger.error(f"Chat completion error with {provider.value}/{model}: {e}")
            raise

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """OpenAI chat completion"""
        client = self._get_openai_client()

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        content = response.choices[0].message.content

        return {
            'content': content,
            'text': content,
            'model': model,
            'provider': 'openai',
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens if hasattr(response, 'usage') else 0,
                'completion_tokens': response.usage.completion_tokens if hasattr(response, 'usage') else 0,
                'total_tokens': response.usage.total_tokens if hasattr(response, 'usage') else 0
            }
        }

    def _chat_anthropic(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Anthropic Claude chat completion"""
        client = self._get_anthropic_client()

        # Convert messages format (Anthropic uses system parameter separately)
        system_message = None
        anthropic_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
            else:
                anthropic_messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })

        # If no messages after filtering system, add the system as user message
        if not anthropic_messages and system_message:
            anthropic_messages = [{'role': 'user', 'content': system_message}]

        # Anthropic API call
        # Note: system parameter must be a list of content blocks (new API format)
        # Build API kwargs
        api_kwargs = {
            'model': model,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'messages': anthropic_messages,
            **kwargs
        }

        # Only include system parameter if we have a system message
        if system_message:
            api_kwargs['system'] = [{"type": "text", "text": system_message}]

        response = client.messages.create(**api_kwargs)

        content = response.content[0].text

        return {
            'content': content,
            'text': content,
            'model': model,
            'provider': 'anthropic',
            'usage': {
                'prompt_tokens': response.usage.input_tokens if hasattr(response, 'usage') else 0,
                'completion_tokens': response.usage.output_tokens if hasattr(response, 'usage') else 0,
                'total_tokens': (response.usage.input_tokens + response.usage.output_tokens) if hasattr(response, 'usage') else 0
            }
        }

    def _chat_google(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Google Gemini chat completion"""
        self._init_google_client()

        # Convert messages to Gemini format
        gemini_messages = []
        for msg in messages:
            role = 'user' if msg['role'] in ['user', 'system'] else 'model'
            gemini_messages.append({
                'role': role,
                'parts': [msg['content']]
            })

        # Create generative model
        gemini_model = genai.GenerativeModel(model)

        # Generation config
        generation_config = GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        # Start chat and send message
        if len(gemini_messages) == 1:
            # Single message
            response = gemini_model.generate_content(
                gemini_messages[0]['parts'][0],
                generation_config=generation_config
            )
        else:
            # Multi-turn conversation
            chat = gemini_model.start_chat(history=gemini_messages[:-1])
            response = chat.send_message(
                gemini_messages[-1]['parts'][0],
                generation_config=generation_config
            )

        content = response.text

        return {
            'content': content,
            'text': content,
            'model': model,
            'provider': 'google',
            'usage': {
                'prompt_tokens': getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0,
                'completion_tokens': getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0,
                'total_tokens': getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            }
        }

    def _chat_deepseek(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """DeepSeek chat completion (OpenAI-compatible API)"""
        client = self._get_deepseek_client()

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        content = response.choices[0].message.content

        return {
            'content': content,
            'text': content,
            'model': model,
            'provider': 'deepseek',
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens if hasattr(response, 'usage') else 0,
                'completion_tokens': response.usage.completion_tokens if hasattr(response, 'usage') else 0,
                'total_tokens': response.usage.total_tokens if hasattr(response, 'usage') else 0
            }
        }

    def summarize(
        self,
        text: str,
        max_words: int = 120,
        model: Optional[str] = None
    ) -> Optional[str]:
        """
        Convenience method for text summarization.

        Args:
            text: Text to summarize
            max_words: Target word count for summary (default: 120)
            model: Model to use (default: gpt-4o)

        Returns:
            Summary text or None if request fails
        """
        if not text or not text.strip():
            return None

        prompt = (
            f"Write a concise {max_words}-word human-readable summary (1-2 lines) "
            f"of the following content.\n\nContent:\n{text}\n\nSummary:"
        )

        try:
            response = self.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                max_tokens=min(300, max_words * 2)  # Rough token estimate
            )
            return response.get('content') or response.get('text')
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return None
