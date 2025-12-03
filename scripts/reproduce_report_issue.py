
import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

from reporting.trust_stack_report import _generate_dimension_analysis

# Mock data
items = [
    {
        'title': 'Test Article 1',
        'body': 'This is a test article with some content. ' * 50,
        'meta': {
            'source_url': 'https://example.com/1', 
            'description': 'Description 1',
            'detected_attributes': [{'label': 'Author Credibility', 'value': 8, 'dimension': 'provenance'}]
        },
        'dimension_scores': {'provenance': 0.8},
        'issues': [{'issue': 'Missing author bio', 'dimension': 'provenance'}]
    },
    {
        'title': 'Test Article 2',
        'body': 'Another test article. ' * 50,
        'meta': {
            'source_url': 'https://example.com/2', 
            'description': 'Description 2',
            'detected_attributes': [{'label': 'Source Attribution', 'value': 3, 'dimension': 'provenance'}]
        },
        'dimension_scores': {'provenance': 0.4},
        'issues': [{'issue': 'No citations found', 'dimension': 'provenance'}]
    },
    {
        'title': 'Test Article 3',
        'body': 'Third test article. ' * 50,
        'meta': {
            'source_url': 'https://example.com/3', 
            'description': 'Description 3',
            'detected_attributes': [{'label': 'Domain Authority', 'value': 9, 'dimension': 'provenance'}]
        },
        'dimension_scores': {'provenance': 0.9}
    },
    {
        'title': 'Test Article 4',
        'body': 'Fourth test article. ' * 50,
        'meta': {
            'source_url': 'https://example.com/4', 
            'description': 'Description 4',
            'detected_attributes': [{'label': 'History Transparency', 'value': 2, 'dimension': 'provenance'}]
        },
        'dimension_scores': {'provenance': 0.2},
        'issues': [{'issue': 'Domain hidden', 'dimension': 'provenance'}]
    }
]

sources = ['https://example.com']
dimension = 'provenance'
score = 6.5
model = 'gpt-4o-mini'

# Monkey patch ChatClient to just print the prompt
class MockChatClient:
    def chat(self, model, messages, max_tokens, temperature):
        print("\n--- Generated Prompt ---")
        print(messages[0]['content'])
        return {'content': 'Mock response'}

import reporting.trust_stack_report
reporting.trust_stack_report.ChatClient = MockChatClient

# Run generation
print("Running generation...")
_generate_dimension_analysis(dimension, score, items, sources, model)
