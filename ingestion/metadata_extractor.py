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

    def extract_provenance_data(self, html: str) -> Dict[str, str]:
        """
        Extract C2PA/CAI provenance data from HTML
        
        Args:
            html: HTML content
            
        Returns:
            Dictionary of provenance metadata
        """
        provenance = {}
        
        if not html:
            return provenance
            
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Check for standard C2PA manifest link
            # <link rel="c2pa-manifest" href="...">
            c2pa_link = soup.find('link', rel='c2pa-manifest')
            if c2pa_link and c2pa_link.get('href'):
                provenance['c2pa_manifest'] = c2pa_link['href']
                provenance['has_c2pa_manifest'] = "true"
                
            # Check for legacy CAI manifest link
            # <link rel="cai-manifest" href="...">
            if 'c2pa_manifest' not in provenance:
                cai_link = soup.find('link', rel='cai-manifest')
                if cai_link and cai_link.get('href'):
                    provenance['c2pa_manifest'] = cai_link['href'] # Map to same key for scorer
                    provenance['cai_manifest'] = cai_link['href']
                    provenance['has_c2pa_manifest'] = "true"

            # Check for meta tags
            # <meta name="c2pa-manifest" content="...">
            if 'c2pa_manifest' not in provenance:
                meta_manifest = soup.find('meta', attrs={'name': 'c2pa-manifest'})
                if meta_manifest and meta_manifest.get('content'):
                    provenance['c2pa_manifest'] = meta_manifest['content']
                    provenance['has_c2pa_manifest'] = "true"

            # Check for script tag
            # <script type="application/c2pa-manifest+json">
            if 'c2pa_manifest' not in provenance:
                script_manifest = soup.find('script', type='application/c2pa-manifest+json')
                if script_manifest and script_manifest.get('src'):
                    provenance['c2pa_manifest'] = script_manifest['src']
                    provenance['has_c2pa_manifest'] = "true"
                elif script_manifest and script_manifest.string:
                    # Inline manifest content - store indication it exists
                    provenance['c2pa_manifest'] = "inline_blob"
                    provenance['has_c2pa_manifest'] = "true"

        except Exception as e:
            logger.debug(f"Error extracting provenance data: {e}")
            
        return provenance

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
            
        # Extract provenance/C2PA data
        if html:
            provenance_data = self.extract_provenance_data(html)
            content.meta.update(provenance_data)

        # Extract significant visuals flag
        if html:
            has_significant_visuals = self.extract_significant_visuals(html)
            content.meta['has_significant_visuals'] = str(has_significant_visuals).lower()

        return content

    def extract_significant_visuals(self, html: str) -> bool:
        """
        Detect if the page contains significant visuals (hero images, large media)
        that would typically require C2PA credentials.
        
        Criteria for "significant":
        - Image dimensions > 250px (if width/height attributes present)
        - Class/ID containing 'hero', 'banner', 'featured', 'main-image'
        - Explicitly excludes known decorative elements (logo, icon, footer, nav)
        
        Args:
            html: HTML content
            
        Returns:
            True if significant visuals detected, False otherwise
        """
        if not html:
            return False
            
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. Check for Hero/Banner naming conventions in images or their containers
            # Look for images with specific classes or parents with specific classes
            hero_keywords = re.compile(r'(hero|banner|featured|cover|main-image|post-image)', re.I)
            decorative_keywords = re.compile(r'(logo|icon|avatar|user|brand|footer|nav|social)', re.I)
            
            images = soup.find_all('img')
            for img in images:
                # Get image attributes
                src = img.get('src', '')
                classes = ' '.join(img.get('class', []))
                img_id = img.get('id', '')
                alt = img.get('alt', '')
                
                # specific check: skip tracking pixels or tiny icons
                if 'tracking' in classes.lower() or 'pixel' in classes.lower():
                    continue

                # Check dimensions if available (attributes often missing, but good signal if present)
                width = img.get('width')
                height = img.get('height')
                
                try:
                    # Convert to int, handling 'px' suffix or distinct types
                    w = int(str(width).replace('px', '')) if width and str(width).replace('px', '').isdigit() else 0
                    h = int(str(height).replace('px', '')) if height and str(height).replace('px', '').isdigit() else 0
                    
                    # SIGNIFICANT SIZE SIGNAL
                    # If image is explicitly large (>250px in either dim), it's likely content
                    if w > 250 or h > 250:
                        # Double check it's not a logo (some logos are hi-res)
                        if not decorative_keywords.search(classes + img_id + src + alt):
                            return True
                except Exception:
                    pass

                # SEMANTIC NAMING SIGNAL
                # Check for hero/banner keywords
                if hero_keywords.search(classes + img_id):
                    # Ensure it's not also marked as logo/icon which overrides 'hero' (e.g. "hero-logo")
                    if not decorative_keywords.search(classes + img_id):
                        return True
            
            # 2. Check for Video elements (always considered significant)
            if soup.find('video') or soup.find('iframe', src=re.compile(r'(youtube|vimeo)', re.I)):
                return True

            # 3. Check for specific meta tags indicating a lead image (og:image is common but weak, explicit "hero" is better)
            # We already use modality detection which checks og:image, but here we want IN-BODY content.
            # So we stick to DOM elements.
                
        except Exception as e:
            logger.debug(f"Error detecting significant visuals: {e}")
            
        return False
