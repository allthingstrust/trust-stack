"""
Unit tests for social media verification badge detection.
Tests the 2024 HTML patterns for Instagram, LinkedIn, and X/Twitter.
"""
import pytest
from bs4 import BeautifulSoup
from ingestion.page_fetcher import (
    _detect_instagram_badge,
    _detect_linkedin_badge,
    _detect_twitter_badge,
    _extract_verification_badges,
)


class TestInstagramVerificationDetection:
    """Test Instagram verification badge detection with 2024 patterns."""
    
    # Exact HTML from user research (December 2024)
    INSTAGRAM_VERIFIED_SVG = '''
    <svg aria-label="Verified" class="x1lliihq x1n2onr6" fill="rgb(0, 149, 246)" 
         height="18" role="img" viewBox="0 0 40 40" width="18">
        <title>Verified</title>
        <path d="M19.998 3.094 14.638 0l-2.972 5.15H5.432v6.354L0 14.64 3.094 20 0 25.359l5.432 3.137v5.905h5.975L14.638 40l5.36-3.094L25.358 40l3.232-5.6h6.162v-6.01L40 25.359 36.905 20 40 14.641l-5.248-3.03v-6.46h-6.419L25.358 0l-5.36 3.094Zm7.415 11.225 2.254 2.287-11.43 11.5-6.835-6.93 2.244-2.258 4.587 4.581 9.18-9.18Z" fill-rule="evenodd"></path>
    </svg>
    '''
    
    INSTAGRAM_UNVERIFIED_HTML = '''
    <html>
        <body>
            <header>
                <h1>Some Profile</h1>
                <span class="x1lliihq">followers</span>
            </header>
        </body>
    </html>
    '''
    
    def test_pattern_1_aria_label_with_blue_fill(self):
        """Test primary pattern: SVG with aria-label='Verified' and blue fill."""
        soup = BeautifulSoup(self.INSTAGRAM_VERIFIED_SVG, 'lxml')
        result = {"verified": False, "platform": "instagram", "badge_type": "", "evidence": ""}
        
        result = _detect_instagram_badge(soup, result)
        
        assert result["verified"] is True
        assert result["badge_type"] == "blue_checkmark"
        assert "rgb(0, 149, 246)" in result["evidence"]
    
    def test_pattern_2_title_element(self):
        """Test pattern 2: SVG with <title>Verified</title>."""
        html = '''
        <svg height="18" role="img"><title>Verified</title><path d="M..."></path></svg>
        '''
        soup = BeautifulSoup(html, 'lxml')
        result = {"verified": False, "platform": "instagram", "badge_type": "", "evidence": ""}
        
        result = _detect_instagram_badge(soup, result)
        
        assert result["verified"] is True
        assert "<title>Verified</title>" in result["evidence"]
    
    def test_pattern_4_obfuscated_class(self):
        """Test pattern 4: 2024 obfuscated class names with blue fill."""
        html = '''
        <svg class="x1lliihq x1n2onr6" fill="rgb(0, 149, 246)" aria-label="Verified">
            <path d="M..."></path>
        </svg>
        '''
        soup = BeautifulSoup(html, 'lxml')
        result = {"verified": False, "platform": "instagram", "badge_type": "", "evidence": ""}
        
        result = _detect_instagram_badge(soup, result)
        
        assert result["verified"] is True
    
    def test_unverified_profile(self):
        """Test that unverified profiles return verified=False."""
        soup = BeautifulSoup(self.INSTAGRAM_UNVERIFIED_HTML, 'lxml')
        result = {"verified": False, "platform": "instagram", "badge_type": "", "evidence": ""}
        
        result = _detect_instagram_badge(soup, result)
        
        assert result["verified"] is False
    
    def test_hex_color_variant(self):
        """Test detection with hex color variant #0095f6."""
        html = '''
        <svg aria-label="Verified" fill="#0095f6" height="18">
            <path d="M..."></path>
        </svg>
        '''
        soup = BeautifulSoup(html, 'lxml')
        result = {"verified": False, "platform": "instagram", "badge_type": "", "evidence": ""}
        
        result = _detect_instagram_badge(soup, result)
        
        assert result["verified"] is True


class TestLinkedInVerificationDetection:
    """Test LinkedIn verification badge detection with 2024 patterns."""
    
    # Exact HTML from user research (December 2024)
    LINKEDIN_VERIFIED_USE = '''
    <html>
        <body>
            <use href="#verified-medium" width="24" height="24"></use>
        </body>
    </html>
    '''
    
    LINKEDIN_UNVERIFIED_HTML = '''
    <html>
        <body>
            <section class="profile">
                <h1>John Doe</h1>
                <span class="premium-member">Premium</span>
            </section>
        </body>
    </html>
    '''
    
    def test_pattern_1_use_href_verified(self):
        """Test primary pattern: <use href='#verified-medium'>."""
        soup = BeautifulSoup(self.LINKEDIN_VERIFIED_USE, 'lxml')
        result = {"verified": False, "platform": "linkedin", "badge_type": "", "evidence": ""}
        
        result = _detect_linkedin_badge(soup, result)
        
        assert result["verified"] is True
        assert "#verified-medium" in result["evidence"]
    
    def test_unverified_profile(self):
        """Test that unverified profiles return verified=False."""
        soup = BeautifulSoup(self.LINKEDIN_UNVERIFIED_HTML, 'lxml')
        result = {"verified": False, "platform": "linkedin", "badge_type": "", "evidence": ""}
        
        result = _detect_linkedin_badge(soup, result)
        
        assert result["verified"] is False


class TestXTwitterVerificationDetection:
    """Test X/Twitter verification badge detection with 2024 patterns."""
    
    # Exact HTML from user research (December 2024)
    X_VERIFIED_SVG = '''
    <svg viewBox="0 0 22 22" aria-label="Verified account" role="img" 
         class="r-4qtqp9 r-yyyyoo r-1xvli5t r-bnwqim r-lrvibr r-m6rgpd r-f9ja8p r-og9te1" 
         data-testid="icon-verified">
        <g>
            <linearGradient gradientUnits="userSpaceOnUse" id="18-a" x1="4.411" x2="18.083" y1="2.495" y2="21.508">
                <stop offset="0" stop-color="#f4e72a"></stop>
                <stop offset=".539" stop-color="#cd8105"></stop>
                <stop offset=".68" stop-color="#cb7b00"></stop>
                <stop offset="1" stop-color="#f4ec26"></stop>
                <stop offset="1" stop-color="#f4e72a"></stop>
            </linearGradient>
            <path d="M13.324 3.848L11 1.6..." fill="url(#18-a)"></path>
        </g>
    </svg>
    '''
    
    X_UNVERIFIED_HTML = '''
    <html>
        <body>
            <div class="profile">
                <h1>Some User</h1>
                <svg aria-label="Profile picture"></svg>
            </div>
        </body>
    </html>
    '''
    
    def test_pattern_1_data_testid(self):
        """Test primary pattern: data-testid='icon-verified'."""
        soup = BeautifulSoup(self.X_VERIFIED_SVG, 'lxml')
        result = {"verified": False, "platform": "twitter", "badge_type": "", "evidence": ""}
        
        result = _detect_twitter_badge(soup, result)
        
        assert result["verified"] is True
        assert result["badge_type"] == "gold_checkmark"
        assert "data-testid" in result["evidence"]
    
    def test_pattern_3_aria_label_verified_account(self):
        """Test pattern 3: aria-label='Verified account'."""
        html = '''
        <svg aria-label="Verified account" role="img"><path d="M..."></path></svg>
        '''
        soup = BeautifulSoup(html, 'lxml')
        result = {"verified": False, "platform": "twitter", "badge_type": "", "evidence": ""}
        
        result = _detect_twitter_badge(soup, result)
        
        assert result["verified"] is True
        assert result["badge_type"] == "gold_checkmark"
    
    def test_pattern_5_gold_gradient(self):
        """Test pattern 5: SVG with gold gradient colors."""
        html = '''
        <svg viewBox="0 0 22 22">
            <linearGradient id="grad">
                <stop stop-color="#f4e72a"></stop>
                <stop stop-color="#cd8105"></stop>
            </linearGradient>
        </svg>
        '''
        soup = BeautifulSoup(html, 'lxml')
        result = {"verified": False, "platform": "twitter", "badge_type": "", "evidence": ""}
        
        result = _detect_twitter_badge(soup, result)
        
        assert result["verified"] is True
        assert "gold gradient" in result["evidence"]
    
    def test_unverified_profile(self):
        """Test that unverified profiles return verified=False."""
        soup = BeautifulSoup(self.X_UNVERIFIED_HTML, 'lxml')
        result = {"verified": False, "platform": "twitter", "badge_type": "", "evidence": ""}
        
        result = _detect_twitter_badge(soup, result)
        
        assert result["verified"] is False


class TestExtractVerificationBadges:
    """Test the main _extract_verification_badges function."""
    
    def test_instagram_url_detection(self):
        """Test that Instagram URLs are routed correctly."""
        html = '''
        <svg aria-label="Verified" fill="rgb(0, 149, 246)">
            <title>Verified</title>
        </svg>
        '''
        result = _extract_verification_badges(html, "https://www.instagram.com/murrayscheese/")
        
        assert result["platform"] == "instagram"
        assert result["verified"] is True
    
    def test_twitter_url_detection(self):
        """Test that X/Twitter URLs are routed correctly."""
        html = '<svg data-testid="icon-verified"></svg>'
        result = _extract_verification_badges(html, "https://x.com/someuser")
        
        assert result["platform"] == "twitter"
        assert result["verified"] is True
    
    def test_linkedin_url_detection(self):
        """Test that LinkedIn URLs are routed correctly."""
        html = '<use href="#verified-medium"></use>'
        result = _extract_verification_badges(html, "https://www.linkedin.com/company/example")
        
        assert result["platform"] == "linkedin"
        assert result["verified"] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
