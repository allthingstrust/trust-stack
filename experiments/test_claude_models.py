#!/usr/bin/env python3
"""
Quick test to find which Claude models actually work with your API key
"""

import os
import sys

try:
    from anthropic import Anthropic
except ImportError:
    print("❌ anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

# Get API key
api_key = os.getenv('ANTHROPIC_API_KEY')
if not api_key:
    print("❌ ANTHROPIC_API_KEY not set in environment")
    sys.exit(1)

client = Anthropic(api_key=api_key)

# Test different model names
test_models = [
    # Claude 3.5 Sonnet (newest)
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",

    # Claude 3 Opus
    "claude-3-opus-20240229",
    "claude-3-opus-latest",

    # Claude 3 Sonnet
    "claude-3-sonnet-20240229",

    # Claude 3 Haiku
    "claude-3-haiku-20240307",

    # Try without dates
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
]

print("Testing Claude models with your API key...\n")
print("=" * 60)

working_models = []

for model in test_models:
    try:
        response = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )
        print(f"✅ {model:40} WORKS!")
        working_models.append(model)
    except Exception as e:
        error_msg = str(e)
        if "not_found_error" in error_msg:
            print(f"❌ {model:40} Not Found (404)")
        elif "permission" in error_msg.lower():
            print(f"⚠️  {model:40} No Permission")
        else:
            print(f"❌ {model:40} Error: {error_msg[:50]}")

print("\n" + "=" * 60)
print(f"\n✅ Working models: {len(working_models)}")
if working_models:
    print("\nUse these in your app:")
    for m in working_models:
        print(f"  - {m}")
else:
    print("\n❌ No Claude models work with your API key!")
    print("\nPossible issues:")
    print("  1. API key is invalid or expired")
    print("  2. API key doesn't have access to Claude 3 models")
    print("  3. Account needs to be upgraded")
    print("\nCheck: https://console.anthropic.com/settings/keys")
