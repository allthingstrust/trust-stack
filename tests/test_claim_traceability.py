
import unittest
from scoring.attribute_detector import TrustStackAttributeDetector
from data.models import NormalizedContent

class TestClaimTraceability(unittest.TestCase):
    def setUp(self):
        self.detector = TrustStackAttributeDetector()

    def test_claim_traceability_missing_citations(self):
        # Content with data claims but no citations
        content = NormalizedContent(
            content_id="test_1",
            src="test_source",
            platform_id="test_platform",
            author="Test Author",
            url="http://example.com",
            title="Test Page",
            body="Research shows that 50% of users prefer this. Also, $1 billion was spent last year.",
            channel="web",
            platform_type="owned",
            source_type="brand_owned"
        )
        
        attributes = self.detector.detect_attributes(content)
        
        # Check for Claim traceability attribute
        traceability_attr = next((a for a in attributes if a.attribute_id == "claim_to_source_traceability"), None)
        
        self.assertIsNotNone(traceability_attr, "Claim traceability attribute should be detected")
        self.assertEqual(traceability_attr.dimension, "verification")
        self.assertEqual(traceability_attr.label, "Claim traceability")
        self.assertLess(traceability_attr.value, 10.0, "Value should be low due to missing citations")
        self.assertIn("Data claims detected but no citations provided", traceability_attr.evidence)

    def test_claim_traceability_with_citations(self):
        # Content with data claims AND citations
        content = NormalizedContent(
            content_id="test_2",
            src="test_source",
            platform_id="test_platform",
            author="Test Author",
            url="http://example.com",
            title="Test Page",
            body="Research shows that 50% of users prefer this (Smith, 2024). Also, $1 billion was spent last year [1].",
            channel="web",
            platform_type="owned",
            source_type="brand_owned"
        )
        
        attributes = self.detector.detect_attributes(content)
        
        # Check for Claim traceability attribute
        traceability_attr = next((a for a in attributes if a.attribute_id == "claim_to_source_traceability"), None)
        
        self.assertIsNotNone(traceability_attr, "Claim traceability attribute should be detected")
        self.assertEqual(traceability_attr.value, 10.0, "Value should be high due to present citations")
        self.assertIn("Citations found", traceability_attr.evidence)

if __name__ == '__main__':
    unittest.main()
