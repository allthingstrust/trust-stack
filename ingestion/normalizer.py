"""
Content normalizer for AR tool
Handles deduplication and content standardization
"""

import hashlib
import json
from typing import List, Dict, Set, Any
from datetime import datetime, timedelta
import logging

from data.models import NormalizedContent
from ingestion.metadata_extractor import MetadataExtractor

logger = logging.getLogger(__name__)

class ContentNormalizer:
    """Normalizes and deduplicates content"""

    def __init__(self, deduplication_window_hours: int = 24):
        self.deduplication_window = timedelta(hours=deduplication_window_hours)
        self.seen_hashes: Set[str] = set()
        self.metadata_extractor = MetadataExtractor()
    
    def normalize_content(self, content_list: List[NormalizedContent]) -> List[NormalizedContent]:
        """
        Normalize content by:
        1. Text cleaning and standardization
        2. Enhanced metadata extraction (modality, channel, platform type)
        3. Deduplication using SimHash
        4. Content length validation
        """
        logger.info(f"Normalizing {len(content_list)} content items")

        # Step 1: Clean and standardize text
        cleaned_content = self._clean_content(content_list)
        logger.info(f"After cleaning: {len(cleaned_content)} items")

        # Step 2: Extract enhanced metadata
        enriched_content = self._enrich_metadata(cleaned_content)
        logger.info(f"After metadata enrichment: {len(enriched_content)} items")

        # Step 3: Deduplicate using SimHash
        deduplicated_content = self._deduplicate_content(enriched_content)
        logger.info(f"After deduplication: {len(deduplicated_content)} items")

        # Step 4: Validate content length
        validated_content = self._validate_content_length(deduplicated_content)
        logger.info(f"After validation: {len(validated_content)} items")

        return validated_content
    
    def _clean_content(self, content_list: List[NormalizedContent]) -> List[NormalizedContent]:
        """Clean and standardize content text"""
        cleaned_content = []
        
        for content in content_list:
            # Clean title
            cleaned_title = self._clean_text(content.title)
            
            # Clean body
            cleaned_body = self._clean_text(content.body)
            
            # Skip if both title and body are empty after cleaning
            if not cleaned_title and not cleaned_body:
                continue
            
            # Create cleaned content object (preserve all fields including enhanced Trust Stack metadata)
            cleaned_content.append(NormalizedContent(
                content_id=content.content_id,
                src=content.src,
                platform_id=content.platform_id,
                author=content.author,
                title=cleaned_title,
                body=cleaned_body,
                rating=content.rating,
                upvotes=content.upvotes,
                helpful_count=content.helpful_count,
                event_ts=content.event_ts,
                run_id=content.run_id,
                meta=content.meta,
                # Preserve enhanced Trust Stack fields
                url=content.url,
                published_at=content.published_at,
                modality=content.modality,
                channel=content.channel,
                platform_type=content.platform_type,
                # Preserve visual analysis fields
                screenshot_path=content.screenshot_path,
                visual_analysis=content.visual_analysis
            ))
        
        return cleaned_content
    
    def _enrich_metadata(self, content_list: List[NormalizedContent]) -> List[NormalizedContent]:
        """Enrich content with enhanced metadata (modality, channel, platform type)"""
        enriched_content = []

        for content in content_list:
            try:
                # Detect modality if not already set
                if not content.modality or content.modality == "text":
                    content.modality = self.metadata_extractor.detect_modality(
                        url=content.url,
                        content_type=content.meta.get('content_type', ''),
                        src=content.src
                    )

                # Extract channel info if not already set (preserve explicitly set channels like 'web')
                if content.url and (not content.channel or content.channel in ["unknown", ""]):
                    channel, platform_type = self.metadata_extractor.extract_channel_info(
                        content.url,
                        content.src
                    )
                    content.channel = channel
                    content.platform_type = platform_type
                    logger.debug(f"Enriched {content.content_id}: channel={channel}, platform_type={platform_type}")
                else:
                    logger.debug(f"Preserving {content.content_id}: channel={content.channel}, platform_type={content.platform_type}")

                enriched_content.append(content)

            except Exception as e:
                logger.warning(f"Error enriching metadata for {content.content_id}: {e}")
                # Still include the content even if enrichment fails
                enriched_content.append(content)

        return enriched_content

    def _clean_text(self, text: str) -> str:
        """Clean individual text field"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = " ".join(text.split())
        
        # Remove common HTML entities
        html_entities = {
            "&amp;": "&",
            "&lt;": "<",
            "&gt;": ">",
            "&quot;": '"',
            "&#39;": "'",
            "&nbsp;": " "
        }
        
        for entity, replacement in html_entities.items():
            text = text.replace(entity, replacement)
        
        # Remove URLs (basic regex-like replacement)
        import re
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Remove excessive punctuation
        text = re.sub(r'[!]{2,}', '!', text)
        text = re.sub(r'[?]{2,}', '?', text)
        text = re.sub(r'[.]{3,}', '...', text)
        
        return text.strip()
    
    def _deduplicate_content(self, content_list: List[NormalizedContent]) -> List[NormalizedContent]:
        """Remove duplicate content using SimHash algorithm"""
        deduplicated_content = []
        content_hashes: Dict[str, NormalizedContent] = {}
        
        for content in content_list:
            # Generate SimHash for content
            content_hash = self._generate_simhash(content)
            
            # Check if we've seen this hash before
            if content_hash in content_hashes:
                # Keep the one with more engagement (higher rating/upvotes)
                existing = content_hashes[content_hash]
                if self._has_more_engagement(content, existing):
                    content_hashes[content_hash] = content
            else:
                content_hashes[content_hash] = content
        
        deduplicated_content = list(content_hashes.values())
        return deduplicated_content
    
    def _generate_simhash(self, content: NormalizedContent) -> str:
        """Generate SimHash for content deduplication"""
        # Combine title and body for hashing
        text_to_hash = f"{content.title} {content.body}".lower()
        
        # Simple hash-based approach (in production, use proper SimHash)
        # Split into words and create features
        words = text_to_hash.split()
        
        # Create hash from word features
        word_hashes = []
        for word in words[:50]:  # Limit to first 50 words
            word_hash = hashlib.md5(word.encode()).hexdigest()
            word_hashes.append(word_hash)
        
        # Combine hashes
        combined_hash = hashlib.md5("".join(word_hashes).encode()).hexdigest()
        return combined_hash
    
    def _has_more_engagement(self, content1: NormalizedContent, content2: NormalizedContent) -> bool:
        """Compare engagement metrics between two content items"""
        # Calculate engagement score
        score1 = self._calculate_engagement_score(content1)
        score2 = self._calculate_engagement_score(content2)
        
        return score1 > score2
    
    def _calculate_engagement_score(self, content: NormalizedContent) -> float:
        """Calculate engagement score for content"""
        score = 0.0
        
        # Rating contribution
        if content.rating is not None:
            score += content.rating * 10
        
        # Upvotes contribution
        if content.upvotes is not None:
            score += content.upvotes
        
        # Helpful count contribution (Amazon)
        if content.helpful_count is not None:
            score += content.helpful_count * 2
        
        return score
    
    def _validate_content_length(self, content_list: List[NormalizedContent]) -> List[NormalizedContent]:
        """Validate content length and filter out invalid items"""
        from config.settings import SETTINGS
        
        max_length = SETTINGS['max_content_length']
        validated_content = []
        
        for content in content_list:
            # Calculate total content length
            total_length = len(content.title) + len(content.body)
            
            # Skip if too long
            if total_length > max_length:
                logger.debug(f"Skipping content {content.content_id} - too long ({total_length} chars)")
                continue
            
            # Skip if too short (likely not meaningful)
            if total_length < 10:
                logger.debug(f"Skipping content {content.content_id} - too short ({total_length} chars)")
                continue
            
            validated_content.append(content)
        
        return validated_content
    
    def reset_deduplication_cache(self):
        """Reset the deduplication cache (call between different runs)"""
        self.seen_hashes.clear()
        logger.info("Deduplication cache reset")
    
    def get_normalization_stats(self, original_count: int, final_count: int) -> Dict[str, Any]:
        """Get statistics about normalization process"""
        return {
            "original_count": original_count,
            "final_count": final_count,
            "removed_count": original_count - final_count,
            "retention_rate": final_count / original_count if original_count > 0 else 0,
            "normalization_timestamp": datetime.now().isoformat()
        }
