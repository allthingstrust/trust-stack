
import pytest
from data.models import NormalizedContent
from scoring.triage import TriageScorer

class TestTriageScorer:
    def setup_method(self):
        self.scorer = TriageScorer()

    def test_should_score_short_content(self):
        """Test that very short content is skipped."""
        content = NormalizedContent(
            content_id="test_1",
            body="Too short",
            title="Short Title",
            url="http://example.com",
            src="web",
            platform_id="http://example.com",
            author="Unknown"
        )
        should_score, reason, default_score = self.scorer.should_score(content)
        assert should_score is False
        assert "too short" in reason.lower()
        assert default_score == 0.5

    def test_should_score_login_page(self):
        """Test that functional pages like login are skipped if content is short."""
        content = NormalizedContent(
            content_id="test_2",
            body="Username Password Login " * 10, # < 300 chars
            title="Login Page",
            url="http://example.com/login",
            src="web",
            platform_id="http://example.com/login",
            author="Unknown"
        )
        # Ensure body is < 300 chars
        assert len(content.body) < 300
        
        should_score, reason, default_score = self.scorer.should_score(content)
        assert should_score is False
        assert "Functional page detected" in reason

    def test_should_score_valid_content(self):
        """Test that substantial content passes triage."""
        content = NormalizedContent(
            content_id="test_3",
            body="This is a substantial piece of content that should definitely be passed to the LLM for scoring. " * 10,
            title="Valid Article",
            url="http://example.com/article",
            src="web",
            platform_id="http://example.com/article",
            author="Unknown"
        )
        should_score, reason, default_score = self.scorer.should_score(content)
        assert should_score is True
        assert "Passed triage" in reason

    def test_should_score_error_page(self):
        """Test that error pages are skipped."""
        content = NormalizedContent(
            content_id="test_4",
            body="404 Page Not Found " * 20,
            title="404 Not Found",
            url="http://example.com/404",
            src="web",
            platform_id="http://example.com/404",
            author="Unknown"
        )
        should_score, reason, default_score = self.scorer.should_score(content)
        assert should_score is False
        assert "Error page detected" in reason
