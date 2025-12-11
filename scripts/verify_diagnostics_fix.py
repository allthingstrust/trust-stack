#!/usr/bin/env python
"""Quick verification of diagnostics table with Core/Amplifier indicators."""

import sys
sys.path.insert(0, '.')

from reporting.trust_stack_report import _render_diagnostics_table

# Test 1: Resonance (not first dimension - no legend)
print("=" * 60)
print("TEST 1: Resonance (should have NO legend, show icons)")
print("=" * 60)

mock_statuses_resonance = {
    'Cultural & Audience Fit': ('✅', 8.2, ['LLM analysis']),
    'Readability & Clarity': ('✅', 7.4, ['LLM analysis']),
    'Personalization Relevance': ('❌', 0.0, ['No data']),  # Amplifier
    'Engagement Quality': ('❌', 0.0, ['No data']),  # Amplifier
    'Language Match': ('✅', 10.0, ['LLM analysis']),
}

table = _render_diagnostics_table('resonance', mock_statuses_resonance, 8.0, [])
print(table)
print()

# Verify contributions sum
lines = table.split('\n')
total = 0.0
for line in lines:
    if '→' in line and 'final score' in line:
        contrib = float(line.split('→')[1].split('/10')[0].strip())
        total += contrib
print(f"Sum of contributions: {total:.1f} (expected: 8.0)")
print()

# Test 2: Provenance (first dimension - should have legend)
print("=" * 60)
print("TEST 2: Provenance (should have legend)")
print("=" * 60)

mock_statuses_provenance = {
    'Author & Creator Clarity': ('✅', 7.0, ['Found bylines']),
    'Source Attribution': ('✅', 8.5, ['Sources cited']),
    'Domain Trust & History': ('✅', 9.0, ['Domain verified']),
    'Content Credentials (C2PA)': ('❌', 0.0, ['Not found']),  # Amplifier
    'Content Freshness': ('⚠️', 5.0, ['Dates present']),  # Amplifier
}

table = _render_diagnostics_table('provenance', mock_statuses_provenance, 7.5, [])
print(table)
print()

print("✅ Verification complete! Check output above.")
