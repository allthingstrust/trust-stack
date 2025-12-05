import pytest
from unittest.mock import MagicMock, patch
from data.models import NormalizedContent
from scoring.scorer import ContentScorer

@pytest.fixture
def scorer():
    # Mock dependencies to avoid external calls
    with patch('scoring.scorer.LLMScoringClient') as mock_llm, \
         patch('scoring.scorer.VerificationManager') as mock_vm, \
         patch('scoring.scorer.LinguisticAnalyzer') as mock_la, \
         patch('scoring.scorer.TriageScorer') as mock_ts, \
         patch('scoring.scorer.TrustStackAttributeDetector') as mock_ad:
        
        scorer = ContentScorer(use_attribute_detection=False)
        scorer.llm_client = mock_llm.return_value
        scorer.verification_manager = mock_vm.return_value
        scorer.linguistic_analyzer = mock_la.return_value
        
        # Default LLM response
        scorer.llm_client.get_score.return_value = 0.8
        scorer.llm_client.get_score_with_reasoning.return_value = {'score': 0.8, 'issues': []}
        scorer.llm_client.get_score_with_feedback.return_value = {'score': 0.8, 'issues': []}
        
        # Default linguistic analysis
        scorer.linguistic_analyzer.analyze.return_value = {'passive_voice': [], 'readability': {}}
        
        return scorer

def test_provenance_confidence_short_content(scorer):
    """Test that short content results in lower provenance confidence"""
    content = NormalizedContent(
        content_id="test1",
        body="Too short",
        title="Test",
        src="web",
        platform_id="web",
        event_ts="2023-01-01",
        author="Test Author" # Provide author so we only test length penalty
    )
    brand_context = {'keywords': []}
    
    score, confidence = scorer._score_provenance(content, brand_context)
    
    # Expected: 1.0 * 0.6 (short content) = 0.6
    assert confidence == 0.6
    assert score == 0.8

def test_provenance_confidence_missing_metadata(scorer):
    """Test that missing metadata results in lower provenance confidence"""
    content = NormalizedContent(
        content_id="test1b",
        body="This is a long enough body content to pass the length check. " * 10,
        title="Test",
        src="", # Missing source
        platform_id="web",
        event_ts="2023-01-01",
        author="" # Missing author
    )
    brand_context = {'keywords': []}
    
    score, confidence = scorer._score_provenance(content, brand_context)
    
    # Expected: 1.0 * 0.8 (missing metadata) = 0.8
    assert confidence == 0.8

def test_coherence_confidence_no_guidelines(scorer):
    """Test that missing guidelines results in lower coherence confidence"""
    content = NormalizedContent(
        content_id="test2",
        body="This is a reasonable length body content for testing purposes.",
        title="Test",
        src="web",
        platform_id="web",
        event_ts="2023-01-01",
        author="Test Author",
        url="https://example.com/blog/post" # Make it a blog post
    )
    brand_context = {'keywords': [], 'use_guidelines': True, 'brand_name': 'UnknownBrand'}
    
    # Mock _load_brand_guidelines to return None
    with patch.object(scorer, '_load_brand_guidelines', return_value=None):
        score, confidence = scorer._score_coherence(content, brand_context)
        
        # Expected: 0.6 (missing guidelines)
        assert confidence == 0.6

def test_verification_confidence_no_rag_results(scorer):
    """Test that lack of RAG results lowers verification confidence"""
    content = NormalizedContent(
        content_id="test3",
        body="Claiming something factual.",
        title="Test",
        src="web",
        platform_id="web",
        event_ts="2023-01-01",
        author="Test Author"
    )
    brand_context = {'keywords': []}
    
    # Mock verification manager to return no results
    scorer.verification_manager.verify_content.return_value = {'score': 0.5, 'issues': [], 'rag_count': 0}
    
    score, confidence = scorer._score_verification(content, brand_context)
    
    # Expected: 0.3 (no RAG results)
    assert confidence == 0.3

def test_transparency_confidence_short_content(scorer):
    """Test that short content results in lower transparency confidence"""
    content = NormalizedContent(
        content_id="test4",
        body="Too short",
        title="Test",
        src="web",
        platform_id="web",
        event_ts="2023-01-01",
        author="Test Author"
    )
    brand_context = {'keywords': []}
    
    score, confidence = scorer._score_transparency(content, brand_context)
    
    # Expected: 1.0 * 0.7 (short content) = 0.7
    assert confidence == 0.7

def test_resonance_confidence_no_metrics(scorer):
    """Test that missing engagement metrics results in lower resonance confidence"""
    content = NormalizedContent(
        content_id="test5",
        body="Some content",
        title="Test",
        src="web",
        platform_id="web",
        event_ts="2023-01-01",
        author="Test Author",
        rating=None,
        upvotes=None,
        helpful_count=None
    )
    brand_context = {'keywords': []}
    
    score, confidence = scorer._score_resonance(content, brand_context)
    
    # Expected: 0.5 (no metrics)
    assert confidence == 0.5
