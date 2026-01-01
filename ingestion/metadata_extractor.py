"""
Enhanced metadata extractor for Trust Stack 5D analysis
Handles modality detection, channel extraction, schema.org parsing, and more
"""

import re
import json
import logging
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extract enhanced metadata for Trust Stack analysis"""

    def __init__(self):
        """Initialize metadata extractor"""
        self.channel_patterns = self._build_channel_patterns()

    def _build_channel_patterns(self) -> Dict[str, Dict[str, str]]:
        """Build patterns for channel and platform type detection"""
        return {
            "youtube": {
                "domains": ["youtube.com", "youtu.be"],
                "platform_type": "social",
                "modality": "video"
            },
            "reddit": {
                "domains": ["reddit.com"],
                "platform_type": "social",
                "modality": "text"
            },
            "instagram": {
                "domains": ["instagram.com"],
                "platform_type": "social",
                "modality": "image"
            },
            "tiktok": {
                "domains": ["tiktok.com"],
                "platform_type": "social",
                "modality": "video"
            },
            "facebook": {
                "domains": ["facebook.com", "fb.com"],
                "platform_type": "social",
                "modality": "text"
            },
            "twitter": {
                "domains": ["twitter.com", "x.com"],
                "platform_type": "social",
                "modality": "text"
            },
            "amazon": {
                "domains": ["amazon.com", "amazon.co.uk", "amazon.de"],
                "platform_type": "marketplace",
                "modality": "text"
            },
            "etsy": {
                "domains": ["etsy.com"],
                "platform_type": "marketplace",
                "modality": "image"
            },
            "ebay": {
                "domains": ["ebay.com"],
                "platform_type": "marketplace",
                "modality": "text"
            },
        }

    def detect_modality(self, url: str = "", content_type: str = "", html: str = "", src: str = "") -> str:
        """
        Detect content modality (text, image, video, audio)

        Args:
            url: Content URL
            content_type: MIME type or content type hint
            html: HTML content for analysis
            src: Source platform (youtube, reddit, etc.)

        Returns:
            Modality: "text", "image", "video", or "audio"
        """
        # Check source-specific defaults
        if src == "youtube":
            return "video"
        elif src == "reddit":
            # Reddit can have images/videos, but default to text
            if url and any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                return "image"
            elif url and any(ext in url.lower() for ext in ['.mp4', '.webm', '.mov']):
                return "video"
            return "text"
        elif src == "amazon":
            return "text"  # Amazon reviews are text-based

        # Check URL for file extensions
        if url:
            url_lower = url.lower()

            # Video extensions
            if any(ext in url_lower for ext in ['.mp4', '.webm', '.mov', '.avi', '.mkv', 'youtube.com', 'youtu.be', 'vimeo.com']):
                return "video"

            # Image extensions
            if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']):
                return "image"

            # Audio extensions
            if any(ext in url_lower for ext in ['.mp3', '.wav', '.ogg', '.m4a', 'spotify.com', 'soundcloud.com']):
                return "audio"

        # Check content type
        if content_type:
            content_type_lower = content_type.lower()
            if 'video' in content_type_lower:
                return "video"
            elif 'image' in content_type_lower:
                return "image"
            elif 'audio' in content_type_lower:
                return "audio"

        # Check HTML for OpenGraph tags
        if html:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                og_type = soup.find('meta', property='og:type')
                if og_type and og_type.get('content'):
                    og_content = og_type['content'].lower()
                    if 'video' in og_content:
                        return "video"
                    elif 'audio' in og_content:
                        return "audio"
                    elif 'image' in og_content:
                        return "image"
            except Exception as e:
                logger.debug(f"Error parsing HTML for modality: {e}")

        # Default to text
        return "text"

    def extract_channel_info(self, url: str, src: str = "") -> Tuple[str, str]:
        """
        Extract channel name and platform type from URL

        Args:
            url: Content URL
            src: Source hint (youtube, reddit, etc.)

        Returns:
            Tuple of (channel_name, platform_type)
        """
        if not url:
            return (src or "unknown", "unknown")

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')

            # Check against known patterns
            for channel_name, patterns in self.channel_patterns.items():
                if any(d in domain for d in patterns["domains"]):
                    return (channel_name, patterns["platform_type"])

            # Try to classify unknown domains
            if src:
                # Use src as channel name if provided
                # Guess platform type based on domain patterns
                if any(term in domain for term in ['shop', 'store', 'buy', 'cart']):
                    return (src, "marketplace")
                elif any(term in domain for term in ['social', 'community', 'forum']):
                    return (src, "social")
                else:
                    return (src, "owned")

            # Extract domain as channel name
            channel = domain.split('.')[0] if '.' in domain else domain

            # Classify as owned by default for unknown domains
            return (channel, "owned")

        except Exception as e:
            logger.warning(f"Error extracting channel info from {url}: {e}")
            return (src or "unknown", "unknown")

    def parse_schema_org(self, html: str) -> Dict[str, any]:
        """
        Parse schema.org structured data from HTML

        Args:
            html: HTML content

        Returns:
            Dictionary of structured data found
        """
        if not html:
            return {}

        structured_data = {}

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract JSON-LD
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            if json_ld_scripts:
                json_ld_data = []
                for script in json_ld_scripts:
                    try:
                        data = json.loads(script.string)
                        json_ld_data.append(data)
                    except json.JSONDecodeError:
                        continue

                if json_ld_data:
                    structured_data['json_ld'] = json_ld_data

            # Extract microdata (simplified - would need full parser for complete extraction)
            items_with_itemtype = soup.find_all(attrs={"itemtype": True})
            if items_with_itemtype:
                structured_data['has_microdata'] = True
                structured_data['microdata_types'] = [item.get('itemtype') for item in items_with_itemtype]

            # Extract RDFa (simplified detection)
            items_with_typeof = soup.find_all(attrs={"typeof": True})
            if items_with_typeof:
                structured_data['has_rdfa'] = True

        except Exception as e:
            logger.debug(f"Error parsing schema.org data: {e}")

        return structured_data

    def extract_canonical_url(self, html: str) -> Optional[str]:
        """
        Extract canonical URL from HTML

        Args:
            html: HTML content

        Returns:
            Canonical URL if found, None otherwise
        """
        if not html:
            return None

        try:
            soup = BeautifulSoup(html, 'html.parser')
            canonical = soup.find('link', rel='canonical')
            if canonical and canonical.get('href'):
                return canonical['href']
        except Exception as e:
            logger.debug(f"Error extracting canonical URL: {e}")

        return None

    def extract_og_metadata(self, html: str) -> Dict[str, str]:
        """
        Extract Open Graph metadata from HTML

        Args:
            html: HTML content

        Returns:
            Dictionary of OG metadata
        """
        og_data = {}

        if not html:
            return og_data

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract all OG tags
            og_tags = soup.find_all('meta', property=re.compile(r'^og:'))
            for tag in og_tags:
                property_name = tag.get('property', '').replace('og:', '')
                content = tag.get('content', '')
                if property_name and content:
                    og_data[f'og_{property_name}'] = content

        except Exception as e:
            logger.debug(f"Error extracting OG metadata: {e}")

        return og_data

    def extract_meta_tags(self, html: str) -> Dict[str, str]:
        """
        Extract standard meta tags from HTML

        Args:
            html: HTML content

        Returns:
            Dictionary of meta tags
        """
        meta_data = {}

        if not html:
            return meta_data

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract description
            description = soup.find('meta', attrs={'name': 'description'})
            if description and description.get('content'):
                meta_data['description'] = description['content']

            # Extract keywords
            keywords = soup.find('meta', attrs={'name': 'keywords'})
            if keywords and keywords.get('content'):
                meta_data['keywords'] = keywords['content']

            # Extract author
            author = soup.find('meta', attrs={'name': 'author'})
            if author and author.get('content'):
                meta_data['author'] = author['content']

            # Extract robots
            robots = soup.find('meta', attrs={'name': 'robots'})
            if robots and robots.get('content'):
                meta_data['robots'] = robots['content']

        except Exception as e:
            logger.debug(f"Error extracting meta tags: {e}")

        return meta_data

    def enrich_content_metadata(self, content: 'NormalizedContent', html: str = "") -> 'NormalizedContent':
        """
        Enrich content with extracted metadata

        Args:
            content: NormalizedContent object to enrich
            html: HTML content for extraction (optional)

        Returns:
            Enriched NormalizedContent object
        """
        # Detect modality
        if not content.modality or content.modality == "text":
            content.modality = self.detect_modality(
                url=content.url,
                content_type=content.meta.get('content_type', ''),
                html=html,
                src=content.src
            )

        # Extract channel info
        if content.url and (not content.channel or content.channel == "unknown"):
            channel, platform_type = self.extract_channel_info(content.url, content.src)
            content.channel = channel
            content.platform_type = platform_type

        # Parse schema.org data if HTML provided
        if html and 'schema_org' not in content.meta:
            schema_data = self.parse_schema_org(html)
            if schema_data:
                content.meta['schema_org'] = json.dumps(schema_data)

        # Extract canonical URL
        if html and 'canonical_url' not in content.meta:
            canonical = self.extract_canonical_url(html)
            if canonical:
                content.meta['canonical_url'] = canonical

        # Extract OG metadata
        if html:
            og_data = self.extract_og_metadata(html)
            content.meta.update(og_data)

        # Extract standard meta tags
        if html:
            meta_tags = self.extract_meta_tags(html)
            content.meta.update(meta_tags)

        return content
