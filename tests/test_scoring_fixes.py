import unittest
from unittest.mock import MagicMock
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scoring.scorer import ContentScorer
from webapp.utils.recommendations import get_remedy_for_issue

class TestScoringFixes(unittest.TestCase):
    def setUp(self):
        self.scorer = ContentScorer()
        
    def test_verify_issue_quotes_valid(self):
        """Test that valid quotes are accepted"""
        content = MagicMock()
        content.title = "Test Page"
        content.body = "This is a test page with some content. We value transparency."
        
        issue = {
            'evidence': "EXACT QUOTE: 'value transparency'",
            'suggestion': "Change 'value transparency' -> 'prioritize transparency'"
        }
        
        result = self.scorer._verify_issue_quotes(content, issue)
        self.assertTrue(result, "Valid quote should be accepted")
        
    def test_verify_issue_quotes_hallucination(self):
        """Test that hallucinated quotes are rejected"""
        content = MagicMock()
        content.title = "Test Page"
        content.body = "This is a test page with some content."
        
        issue = {
            'evidence': "EXACT QUOTE: 'completely made up text'",
            'suggestion': "Change 'completely made up text' -> 'real text'"
        }
        
        result = self.scorer._verify_issue_quotes(content, issue)
        self.assertFalse(result, "Hallucinated quote should be rejected")
        
    def test_verify_issue_quotes_fuzzy(self):
        """Test that quotes with minor whitespace differences are accepted"""
        content = MagicMock()
        content.title = "Test Page"
        content.body = "This is a    test page."
        
        issue = {
            'evidence': "EXACT QUOTE: 'is a test page'",
            'suggestion': "Change 'is a test page' -> 'is a good page'"
        }
        
        result = self.scorer._verify_issue_quotes(content, issue)
        self.assertTrue(result, "Fuzzy quote match should be accepted")

    def test_recommendation_formatting(self):
        """Test the formatting of recommendations"""
        issue_type = "Inconsistent Voice"
        dimension = "Coherence"
        
        issue_items = [
            {
                'suggestion': "Change 'bad' -> 'good' to improve consistency",
                'url': "http://example.com/page1",
                'title': "Page 1",
                'evidence': "Found 'bad'",
                'confidence': 0.9
            },
            {
                'suggestion': "Change 'worse' -> 'better'",
                'url': "http://example.com/page2",
                'title': "Page 2",
                'evidence': "Found 'worse'",
                'confidence': 0.95
            }
        ]
        
        output = get_remedy_for_issue(issue_type, dimension, issue_items)
        
        # Check for key elements in the output
        self.assertIn("🔗 http://example.com/page1", output['recommended_fix'])
        self.assertIn("Change 'bad' -> 'good'", output['recommended_fix'])
        self.assertIn("* From: Page 1", output['recommended_fix'])
        self.assertIn("🔗 http://example.com/page2", output['recommended_fix'])
        
        # Check that general best practice is at the top
        self.assertIn("Audit content across all pages to ensure consistency", output['general_best_practice'])

if __name__ == '__main__':
    unittest.main()
