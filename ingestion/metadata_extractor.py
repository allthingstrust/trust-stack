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

            # Standard meta tags to extract
            target_tags = [
                'description', 'keywords', 'author', 'viewport', 'robots',
                'generator', 'application-name', 'theme-color',
                # Date related
                'date', 'pubdate', 'publish-date', 'published-date',
                'article:published_time', 'article:modified_time',
                'og:updated_time', 'last-modified'
            ]

            for name in target_tags:
                tag = soup.find('meta', attrs={'name': name})
                if tag and tag.get('content'):
                    meta_data[name] = tag['content']

                # Also try property (common for OG/article tags)
                if name.startswith('article:') or name.startswith('og:'):
                    tag = soup.find('meta', property=name)
                    if tag and tag.get('content'):
                        meta_data[name] = tag['content']

        except Exception as e:
            logger.debug(f"Error extracting meta tags: {e}")

        return meta_data

    def _extract_publication_date(self, html: str, schema_json: str = None) -> Optional[str]:
        """
        Extract publication date from various sources in priority order.
        
        Priority:
        1. OpenGraph article:published_time
        2. Schema.org datePublished
        3. Standard meta tags (pubdate, date, etc.)
        
        Returns:
            ISO format date string or None
        """
        if not html:
            return None
            
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. OpenGraph article:published_time
            og_pub = soup.find('meta', property='article:published_time')
            if og_pub and og_pub.get('content'):
                return og_pub['content']
                
            # 2. Schema.org datePublished (if already extracted)
            if schema_json:
                try:
                    data = json.loads(schema_json)
                    candidates = []
                    
                    # Handle MetadataExtractor structure which wraps json_ld
                    if isinstance(data, dict):
                        if 'json_ld' in data and isinstance(data['json_ld'], list):
                            candidates.extend(data['json_ld'])
                        else:
                            candidates.append(data)
                    elif isinstance(data, list):
                        candidates.extend(data)

                    for item in candidates:
                        # Look for common types that have dates
                        if any(t in item.get('@type', '') for t in ['Article', 'NewsArticle', 'BlogPosting', 'WebPage']):
                            if item.get('datePublished'):
                                return item['datePublished']
                            if item.get('dateCreated'):
                                return item['dateCreated']
                except:
                    pass
            
            # 2b. Schema.org via itemprop (microdata)
            date_pub = soup.find(attrs={"itemprop": "datePublished"})
            if date_pub:
                return date_pub.get('content') or date_pub.get_text()
                
            # 3. Meta tags
            meta_dates = [
                ('name', 'pubdate'),
                ('name', 'publish-date'),
                ('name', 'date'),
                ('name', 'original-publish-date'),
                ('property', 'og:updated_time') # Fallback to updated time
            ]
            
            for attr, val in meta_dates:
                tag = soup.find('meta', attrs={attr: val})
                if tag and tag.get('content'):
                    return tag['content']
                    
        except Exception as e:
            logger.debug(f"Error extracting publication date: {e}")
            
        return None

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

        # Enrich URL and canonical URL
        # If content.url is not set, try to use src or canonical
        if not content.url:
            content.url = content.src or ""
        
        canonical = self.extract_canonical_url(html)
        if canonical:
            if not content.url: # If content.url is still empty, use canonical
                content.url = canonical
            # Also store as meta for scoring
            content.meta['canonical'] = canonical

        # Extract publication date
        if html:
            published_at = self._extract_publication_date(html, content.meta.get('schema_org'))
            if published_at:
                content.published_at = published_at
                content.meta['published_at'] = published_at

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
            
            # Extract semantic text segments
            text_segments = self.extract_semantic_text_segments(html)
            content.main_text = text_segments.get('main_text', '')
            content.footer_text = text_segments.get('footer_text', '')
            content.header_text = text_segments.get('header_text', '')
            
            # Fallback if text extraction failed in previous steps
            if not content.body and content.main_text:
                content.body = content.main_text

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

    def extract_semantic_text_segments(self, html: str) -> Dict[str, str]:
        """
        Extract text content separated by semantic role (Header, Footer, Main).
        This allows scorers to distinguish between site-wide boilerplates (Footer)
        and actual unique page content.
        
        Args:
            html: HTML content
            
        Returns:
            Dict with 'main_text', 'footer_text', 'header_text', 'rest_text'
        """
        segments = {
            'main_text': '',
            'footer_text': '',
            'header_text': '',
            'rest_text': ''
        }
        
        if not html:
            return segments
            
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # --- Footer Extraction ---
            # Try semantic <footer >, role="contentinfo", or common class names
            footers = soup.find_all('footer') + \
                     soup.find_all(attrs={"role": "contentinfo"}) + \
                     soup.find_all(class_=re.compile(r'footer|site-info|copyright', re.I))
            
            footer_text_list = []
            for f in footers:
                # Avoid duplicates if elements are nested (naive check)
                t = f.get_text(" ", strip=True)
                if t and t not in " ".join(footer_text_list):
                    footer_text_list.append(t)
            segments['footer_text'] = " ".join(footer_text_list)

            # --- Header Extraction ---
            # Try semantic <header>, role="banner", or common class names
            headers = soup.find_all('header') + \
                      soup.find_all(attrs={"role": "banner"}) + \
                      soup.find_all(class_=re.compile(r'header|top-bar|nav', re.I))
            
            header_text_list = []
            for h in headers:
                t = h.get_text(" ", strip=True)
                if t and t not in " ".join(header_text_list):
                    header_text_list.append(t)
            segments['header_text'] = " ".join(header_text_list)
            
            # --- Main Content Extraction ---
            # Try semantic <main>, role="main", article, or largest text block logic
            mains = soup.find_all('main') + \
                   soup.find_all(attrs={"role": "main"}) + \
                   soup.find_all('article')
            
            main_text_list = []
            if mains:
                for m in mains:
                    t = m.get_text(" ", strip=True)
                    if t:
                        main_text_list.append(t)
                segments['main_text'] = " ".join(main_text_list)
            else:
                # Fallback: Body text minus header/footer text (approximate)
                body = soup.body.get_text(" ", strip=True) if soup.body else ""
                # Simple removal of known header/footer strings
                cleaned_body = body.replace(segments['header_text'], "").replace(segments['footer_text'], "")
                segments['main_text'] = cleaned_body

        except Exception as e:
            logger.warning(f"Error segementing HTML text: {e}")
            
        return segments
