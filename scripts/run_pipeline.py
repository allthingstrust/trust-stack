#!/usr/bin/env python3
"""
Main pipeline runner script for AR tool
Executes the complete AR analysis pipeline
"""

from __future__ import annotations

import sys
import os
import argparse
from datetime import datetime
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logging_config import setup_logging
from utils.helpers import generate_run_id, validate_config
# Optional ingestion modules - import lazily and defensively to avoid hard
# dependency failures when running partial tool paths (e.g., only Brave + YouTube).
try:
    from ingestion.reddit_crawler import RedditCrawler
except Exception:
    RedditCrawler = None

try:
    from ingestion.amazon_scraper import AmazonScraper
except Exception:
    AmazonScraper = None

try:
    from ingestion.youtube_scraper import YouTubeScraper
except Exception:
    YouTubeScraper = None

from ingestion.search_unified import search
from ingestion.page_fetcher import fetch_page
from ingestion.brave_search import collect_brave_pages
from ingestion.serper_search import collect_serper_pages
from ingestion.normalizer import ContentNormalizer
from scoring.pipeline import ScoringPipeline
from reporting.pdf_generator import PDFReportGenerator
from reporting.markdown_generator import MarkdownReportGenerator
# AthenaClient requires boto3 and other AWS deps; import lazily in main()
from config.settings import APIConfig
import sys

logger = logging.getLogger(__name__)

# Import reddit auth helper
from ingestion.reddit_auth import obtain_token

def main():
    """Main pipeline execution function"""
    parser = argparse.ArgumentParser(description='Run AR analysis pipeline')
    parser.add_argument('--brand-id', required=True, help='Brand ID to analyze')
    parser.add_argument('--brand-name', help='Brand name (defaults to brand-id)')
    parser.add_argument('--keywords', nargs='+', required=True, help='Brand keywords to search for')
    parser.add_argument('--sources', nargs='+', default=['reddit', 'amazon'], help='Data sources to use')
    parser.add_argument('--output-dir', default='./output', help='Output directory for reports')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    parser.add_argument('--dry-run', action='store_true', help='Run without making API calls or uploading data')
    parser.add_argument('--max-items', '-n', type=int, default=100, help='Maximum total items to analyze across all sources (default: 100)')
    parser.add_argument('--max-content', type=int, help='[DEPRECATED] Use --max-items instead')
    parser.add_argument('--brave-pages', type=int, default=10, help='Number of Brave search results/pages to fetch (default: 10)')
    parser.add_argument('--include-comments', action='store_true', help='Include comments in analysis (overrides settings include_comments_in_analysis)')
    parser.add_argument('--use-llm-examples', action='store_true', help='Use LLM to produce abstractive summaries for executive examples')
    parser.add_argument('--llm-model', default='gpt-3.5-turbo',
                        help='LLM model for executive summaries (default: gpt-3.5-turbo). '
                             'OpenAI: gpt-3.5-turbo, gpt-4o-mini, gpt-4o | '
                             'Claude: claude-3-haiku-20240307, claude-3-5-sonnet-20241022 | '
                             'Google: gemini-1.5-flash, gemini-1.5-pro | '
                             'DeepSeek: deepseek-chat, deepseek-reasoner')
    parser.add_argument('--recommendations-model', default='gpt-4o-mini',
                        help='LLM model for recommendations (default: gpt-4o-mini). '
                             'OpenAI: gpt-3.5-turbo, gpt-4o-mini, gpt-4o | '
                             'Claude: claude-3-haiku-20240307, claude-3-5-sonnet-20241022 | '
                             'Google: gemini-1.5-flash, gemini-1.5-pro | '
                             'DeepSeek: deepseek-chat, deepseek-reasoner')

    # URL collection ratio enforcement arguments
    parser.add_argument('--brand-domains', nargs='+', help='Brand-owned domains for URL classification (e.g., nike.com nike.co.uk)')
    parser.add_argument('--brand-subdomains', nargs='+', help='Brand-owned subdomains (e.g., blog.nike.com help.nike.com)')
    parser.add_argument('--brand-social-handles', nargs='+', help='Brand social media handles (e.g., @nike nike)')
    parser.add_argument('--brand-owned-ratio', type=float, default=0.6, help='Target ratio of brand-owned URLs (default: 0.6 = 60%%)')
    parser.add_argument('--third-party-ratio', type=float, default=0.4, help='Target ratio of 3rd party URLs (default: 0.4 = 40%%)')

    args = parser.parse_args()
    # Normalize sources to lowercase to be case-insensitive (users may pass 'Brave' or 'Youtube')
    args.sources = [s.lower() for s in args.sources]

    # Backwards-compatible handling of deprecated --max-content
    # Prefer explicit --max-items when provided; fall back to --max-content if present.
    max_items = args.max_items
    if args.max_content is not None:
        try:
            # allow --max-content to override when explicitly specified
            max_items = int(args.max_content)
        except Exception:
            pass
    try:
        max_items = int(max_items)
        if max_items <= 0:
            max_items = 100
    except Exception:
        max_items = 100
    
    # Setup logging
    log_file = os.path.join(args.output_dir, 'logs', f'ar_pipeline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    setup_logging(log_level=args.log_level, log_file=log_file)
    
    logger.info("Starting AR analysis pipeline")
    logger.info(f"Brand ID: {args.brand_id}")
    logger.info(f"Keywords: {args.keywords}")
    logger.info(f"Sources: {args.sources}")
    logger.info(f"Max items to analyze: {max_items}")
    logger.info(f"Dry run: {args.dry_run}")
    
    try:
        # Validate configuration
        logger.info("Validating configuration...")
        config_issues = validate_config()
        if config_issues:
            logger.warning(f"Configuration issues found: {config_issues}")
        
        # Validate API credentials for selected sources
        def _missing_keys_for_source(sources_list):
            missing = {}
            cfg = APIConfig()
            if 'reddit' in sources_list:
                if not cfg.reddit_client_id or not cfg.reddit_client_secret:
                    missing['reddit'] = ['REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET']
            if 'youtube' in sources_list:
                if not cfg.youtube_api_key:
                    missing['youtube'] = ['YOUTUBE_API_KEY']
            if 'amazon' in sources_list:
                if not cfg.amazon_access_key or not cfg.amazon_secret_key:
                    missing['amazon'] = ['AMAZON_ACCESS_KEY', 'AMAZON_SECRET_KEY']
            if 'yelp' in sources_list:
                # Yelp Fusion uses a single API Key
                if not os.getenv('YELP_API_KEY'):
                    missing['yelp'] = ['YELP_API_KEY']
            return missing

        missing = _missing_keys_for_source(args.sources)
        if missing:
            for src, keys in missing.items():
                logger.error(f"Missing API keys for source '{src}': {', '.join(keys)}")
            logger.error("Please set the required environment variables (e.g., in .env) and retry.")
            sys.exit(2)
        
        # Generate run ID
        run_id = generate_run_id()
        logger.info(f"Generated run ID: {run_id}")
        
        # Create output directory
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Setup brand configuration
        brand_config = {
            'brand_id': args.brand_id,
            'brand_name': args.brand_name or args.brand_id,
            'keywords': args.keywords,
            'sources': args.sources
        }
        
    # Initialize components
        logger.info("Initializing pipeline components...")
        # Obtain Reddit token early (if reddit is in sources and not a dry run)
        if 'reddit' in args.sources and not args.dry_run:
            token, resp = obtain_token()
            if token:
                logger.info("Obtained Reddit access token for pipeline (masked)")
            else:
                logger.warning(f"Could not obtain Reddit token: {resp}")
                # Proceeding without token will cause Reddit ingestion to fail later; exit early
                logger.error("Reddit authentication failed; aborting pipeline.")
                sys.exit(3)
        if not args.dry_run:
            try:
                from data.athena_client import AthenaClient
                athena_client = AthenaClient()
            except Exception as e:
                logger.warning(f"AthenaClient not available (will skip uploads): {e}")
                athena_client = None
        else:
            athena_client = None

        # Initialize source-specific scrapers lazily below when we actually
        # attempt to ingest from a particular source. This avoids import-time
        # dependency issues for optional SDKs (e.g., praw for Reddit).
        reddit_crawler = None
        amazon_scraper = None
        youtube_scraper = None
        # Apply per-run override for including comments if supplied
        if args.include_comments:
            try:
                from config.settings import SETTINGS
                SETTINGS['include_comments_in_analysis'] = True
                logger.info('Overriding settings: include_comments_in_analysis = True for this run')
            except Exception:
                logger.warning('Could not override include_comments_in_analysis setting; proceeding with configured value')
        
        normalizer = ContentNormalizer()
        scoring_pipeline = ScoringPipeline()
        pdf_generator = PDFReportGenerator()
        markdown_generator = MarkdownReportGenerator()
        
        # Step 1: Data Ingestion
        logger.info("Step 1: Data Ingestion")
        all_content = []
        
        if 'reddit' in args.sources:
            logger.info("Ingesting Reddit data...")
            if args.dry_run:
                logger.info("Dry run: Skipping Reddit ingestion")
            else:
                if RedditCrawler is None:
                    logger.warning("Reddit ingestion unavailable: missing optional dependency (praw). Skipping Reddit.")
                else:
                    try:
                        reddit_crawler = RedditCrawler()
                        reddit_posts = reddit_crawler.search_posts(
                            keywords=args.keywords,
                            limit=max_items // max(1, len(args.sources))
                        )
                        reddit_content = reddit_crawler.convert_to_normalized_content(
                            reddit_posts, args.brand_id, run_id
                        )
                        all_content.extend(reddit_content)
                        logger.info(f"Retrieved {len(reddit_content)} Reddit content items")
                    except Exception as e:
                        logger.warning(f"Skipping Reddit ingestion due to error: {e}")
        
        if 'amazon' in args.sources:
            logger.info("Ingesting Amazon data...")
            if args.dry_run:
                logger.info("Dry run: Skipping Amazon ingestion")
            else:
                if AmazonScraper is None:
                    logger.warning("Amazon ingestion unavailable: missing optional dependency. Skipping Amazon.")
                else:
                    try:
                        amazon_scraper = AmazonScraper()
                        # mock_reviews_for_demo signature = (brand_keywords: List[str], num_reviews: int = 50)
                        amazon_reviews = amazon_scraper.mock_reviews_for_demo(
                            args.keywords,
                            num_reviews=max_items // max(1, len(args.sources))
                        )
                        amazon_content = amazon_scraper.convert_to_normalized_content(
                            amazon_reviews, args.brand_id, run_id
                        )
                        all_content.extend(amazon_content)
                        logger.info(f"Retrieved {len(amazon_content)} Amazon content items")
                    except Exception as e:
                        logger.warning(f"Skipping Amazon ingestion due to error: {e}")

        if 'youtube' in args.sources:
            logger.info("Ingesting YouTube data...")
            if args.dry_run:
                logger.info("Dry run: Skipping YouTube ingestion")
            else:
                if YouTubeScraper is None:
                    logger.warning("YouTube ingestion unavailable: missing optional dependency (googleapiclient). Skipping YouTube.")
                else:
                    try:
                        # Build a search query from keywords
                        youtube_scraper = YouTubeScraper()
                        query = ' '.join(args.keywords)
                        videos = youtube_scraper.search_videos(query=query, max_results=max_items // max(1, len(args.sources)))
                        youtube_content = youtube_scraper.convert_videos_to_normalized(videos, args.brand_id, run_id)
                        all_content.extend(youtube_content)
                        logger.info(f"Retrieved {len(youtube_content)} YouTube content items")
                    except Exception as e:
                        logger.warning(f"Skipping YouTube ingestion due to error: {e}")

        if 'brave' in args.sources:
            logger.info("Ingesting Brave search results...")
            if not args.dry_run:
                query = ' '.join(args.keywords)
                # Use the new collect_brave_pages helper to gather N successful pages
                target = min(args.brave_pages, max_items)

                # Create URL collection config if brand domains are provided
                url_config = None
                if args.brand_domains:
                    from ingestion.domain_classifier import URLCollectionConfig
                    url_config = URLCollectionConfig(
                        brand_owned_ratio=args.brand_owned_ratio,
                        third_party_ratio=args.third_party_ratio,
                        brand_domains=args.brand_domains or [],
                        brand_subdomains=args.brand_subdomains or [],
                        brand_social_handles=args.brand_social_handles or []
                    )
                    logger.info(f"URL ratio enforcement enabled: {args.brand_owned_ratio:.0%} brand-owned / {args.third_party_ratio:.0%} 3rd party")

                try:
                    collected = collect_brave_pages(query, target_count=target, url_collection_config=url_config)
                except Exception as e:
                    logger.warning(f"Brave collection failed: {e}")
                    collected = []

                brave_items = []
                from data.models import NormalizedContent
                for i, c in enumerate(collected):
                    url = c.get('url')
                    content_id = f"brave_{i}_{abs(hash(url or ''))}"
                    source_type = c.get('source_type', 'unknown')
                    source_tier = c.get('source_tier', 'unknown')
                    logger.info(f"Creating Brave content: url={url}, source_type={source_type}, source_tier={source_tier}")

                    meta = {
                        'source_url': url or '',
                        'content_type': 'web'
                    }
                    # Include footer-extracted links when available
                    if isinstance(c, dict):
                        terms = c.get('terms')
                        privacy = c.get('privacy')
                        if terms:
                            meta['terms'] = terms
                        if privacy:
                            meta['privacy'] = privacy

                    nc = NormalizedContent(
                        content_id=content_id,
                        src='brave',
                        platform_id=url or '',
                        author='web',
                        title=c.get('title', '') or '',
                        body=c.get('body', '') or '',
                        run_id=run_id,
                        event_ts=datetime.now().isoformat(),
                        meta=meta,
                        # Enhanced Trust Stack fields
                        url=url or '',
                        modality='text',
                        channel='web',
                        platform_type='web',
                        # URL source classification
                        source_type=source_type,
                        source_tier=source_tier
                    )
                    brave_items.append(nc)
                all_content.extend(brave_items)
                logger.info(f"Retrieved {len(brave_items)} Brave content items (successful fetches)")
            else:
                logger.info("Dry run: Skipping Brave ingestion")

        if 'serper' in args.sources:
            logger.info("Ingesting Serper search results...")
            if not args.dry_run:
                query = ' '.join(args.keywords)
                # Use the collect_serper_pages helper to gather N successful pages
                target = min(args.brave_pages, max_items)  # Reuse --brave-pages arg for now

                # Create URL collection config if brand domains are provided
                url_config = None
                if args.brand_domains:
                    from ingestion.domain_classifier import URLCollectionConfig
                    url_config = URLCollectionConfig(
                        brand_owned_ratio=args.brand_owned_ratio,
                        third_party_ratio=args.third_party_ratio,
                        brand_domains=args.brand_domains or [],
                        brand_subdomains=args.brand_subdomains or [],
                        brand_social_handles=args.brand_social_handles or []
                    )
                    logger.info(f"URL ratio enforcement enabled: {args.brand_owned_ratio:.0%} brand-owned / {args.third_party_ratio:.0%} 3rd party")

                try:
                    collected = collect_serper_pages(query, target_count=target, url_collection_config=url_config)
                except Exception as e:
                    logger.warning(f"Serper collection failed: {e}")
                    collected = []

                serper_items = []
                from data.models import NormalizedContent
                for i, c in enumerate(collected):
                    url = c.get('url')
                    content_id = f"serper_{i}_{abs(hash(url or ''))}"
                    source_type = c.get('source_type', 'unknown')
                    source_tier = c.get('source_tier', 'unknown')
                    logger.info(f"Creating Serper content: url={url}, source_type={source_type}, source_tier={source_tier}")

                    meta = {
                        'source_url': url or '',
                        'content_type': 'web'
                    }
                    # Include footer-extracted links when available
                    if isinstance(c, dict):
                        terms = c.get('terms')
                        privacy = c.get('privacy')
                        if terms:
                            meta['terms'] = terms
                        if privacy:
                            meta['privacy'] = privacy

                    nc = NormalizedContent(
                        content_id=content_id,
                        src='serper',
                        platform_id=url or '',
                        author='web',
                        title=c.get('title', '') or '',
                        body=c.get('body', '') or '',
                        run_id=run_id,
                        event_ts=datetime.now().isoformat(),
                        meta=meta,
                        # Enhanced Trust Stack fields
                        url=url or '',
                        modality='text',
                        channel='web',
                        platform_type='web',
                        # URL source classification
                        source_type=source_type,
                        source_tier=source_tier
                    )
                    serper_items.append(nc)
                all_content.extend(serper_items)
                logger.info(f"Retrieved {len(serper_items)} Serper content items (successful fetches)")
            else:
                logger.info("Dry run: Skipping Serper ingestion")

        if not all_content:
            logger.warning("No content retrieved from any source")
            return
        
        # Step 2: Content Normalization
        logger.info("Step 2: Content Normalization")
        normalized_content = normalizer.normalize_content(all_content)
        logger.info(f"Normalized {len(normalized_content)} content items")

        # Report URL distribution if ratio enforcement was enabled
        if args.brand_domains:
            brand_owned_count = sum(1 for c in normalized_content if getattr(c, 'source_type', None) == 'brand_owned')
            third_party_count = sum(1 for c in normalized_content if getattr(c, 'source_type', None) == 'third_party')
            unknown_count = len(normalized_content) - brand_owned_count - third_party_count

            logger.info("=" * 60)
            logger.info("URL Distribution Summary:")
            logger.info(f"  Brand-owned: {brand_owned_count} ({brand_owned_count/len(normalized_content)*100:.1f}%)")
            logger.info(f"  3rd party:   {third_party_count} ({third_party_count/len(normalized_content)*100:.1f}%)")
            if unknown_count > 0:
                logger.info(f"  Unknown:     {unknown_count} ({unknown_count/len(normalized_content)*100:.1f}%)")
            logger.info(f"  Total:       {len(normalized_content)}")
            logger.info("=" * 60)
        
        # Step 3: Upload normalized content to S3/Athena
        if not args.dry_run and athena_client:
            logger.info("Uploading normalized content to S3/Athena...")
            for source in args.sources:
                source_content = [c for c in normalized_content if c.src == source]
                if source_content:
                    athena_client.upload_normalized_content(
                        source_content, args.brand_id, source, run_id
                    )
        
        # Step 4: Content Scoring and Classification
        logger.info("Step 3: Content Scoring and Classification")
        pipeline_run = scoring_pipeline.run_scoring_pipeline(
            normalized_content, brand_config
        )
        
        # Step 5: Generate Reports
        logger.info("Step 4: Generating Reports")

        # Use the classified scores produced by the scoring pipeline for report
        # generation. This ensures the report reflects the actual classifications
        # that were uploaded to S3/Athena.
        scores_list = pipeline_run.classified_scores or []

        # Generate scoring report
        scoring_report = scoring_pipeline.generate_scoring_report(scores_list, brand_config)

        # Generate PDF report
        pdf_path = os.path.join(args.output_dir, f'ar_report_{args.brand_id}_{run_id}.pdf')
        pdf_generator.generate_report(scoring_report, pdf_path)
        logger.info(f"Generated PDF report: {pdf_path}")

        # Optionally inject LLM flags into the report generator data
        scoring_report['use_llm_for_examples'] = bool(args.use_llm_examples)
        scoring_report['llm_model'] = args.llm_model
        scoring_report['recommendations_model'] = args.recommendations_model

        # Generate Markdown report
        md_path = os.path.join(args.output_dir, f'ar_report_{args.brand_id}_{run_id}.md')
        markdown_generator.generate_report(scoring_report, md_path)
        logger.info(f"Generated Markdown report: {md_path}")

        # Pipeline completion
        logger.info("Pipeline completed successfully!")
        logger.info(f"Run ID: {run_id}")
        logger.info(f"Total content processed: {len(normalized_content)}")
        logger.info(f"Reports generated in: {args.output_dir}")

        if not args.dry_run:
            logger.info(f"Data uploaded to S3/Athena for brand: {args.brand_id}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise

if __name__ == "__main__":
    main()


def run_pipeline_for_contents(urls: list, output_dir: str = './output', brand_id: str = 'brand', sources: list | None = None, keywords: list | None = None, include_comments: bool | None = None, include_items_table: bool = False, brand_domains: list | None = None, brand_subdomains: list | None = None, brand_owned_ratio: float = 0.6) -> dict:
    """Run the pipeline for a set of URLs (used by the Streamlit webapp).

    This helper is intentionally lightweight: it will fetch each URL using
    the brave_search.fetch_page helper, convert to NormalizedContent objects,
    call the normalizer and scoring pipeline, and write reports to output_dir.
    """
    # Local imports to avoid circular imports when script is used as module
    from ingestion import brave_search
    from data.models import NormalizedContent

    os.makedirs(output_dir, exist_ok=True)

    # Simple run_id generation
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Determine sources and keywords
    if sources is None:
        sources = ['brave']
    if keywords is None:
        keywords = [brand_id]

    # Fetch pages (Brave) if requested
    fetched = []
    if 'brave' in sources and urls:
        for i, u in enumerate(urls):
            page = brave_search.fetch_page(u)
            content_id = f"web_{i}_{abs(hash(u))}"
            nc = NormalizedContent(
                content_id=content_id,
                src='brave',
                platform_id=u,
                author='web',
                title=page.get('title', '') or '',
                body=page.get('body', '') or '',
                run_id=run_id,
                event_ts=datetime.now().isoformat(),
                meta={'content_type': 'web', 'source_url': u, 'terms': page.get('terms',''), 'privacy': page.get('privacy','')},
                # Enhanced Trust Stack fields
                url=u,
                modality='text',
                channel='web',
                platform_type='web'
            )
            fetched.append(nc)

    # If brand_domains not supplied but brand_id is present, infer conservative defaults
    if brand_domains is None and brand_id:
        # keep inference minimal to avoid overreach
        brand_domains = [f"{brand_id}.com", f"www.{brand_id}.com"]
    if brand_subdomains is None and brand_id:
        brand_subdomains = [f"blog.{brand_id}.com", f"shop.{brand_id}.com", f"store.{brand_id}.com"]

    # If ratio enforcement requested, and brand-owned pages are insufficient,
    # attempt to extract brand subpages from fetched brand-owned pages to hit target
    try:
        from ingestion.domain_classifier import URLCollectionConfig, classify_url, URLSourceType
        from ingestion.brave_search import _extract_internal_links, fetch_page as _fetch_page
        # Only attempt if we have any fetched items and a desired ratio
        if fetched and brand_domains:
            total_target = len(fetched)
            config = URLCollectionConfig(
                brand_owned_ratio=brand_owned_ratio,
                third_party_ratio=1.0 - brand_owned_ratio,
                brand_domains=brand_domains,
                brand_subdomains=brand_subdomains or [],
                brand_social_handles=[]
            )

            # Count current brand-owned items
            brand_owned_now = 0
            for item in fetched:
                url = item.get('url') or item.get('platform_id') or item.get('source_url')
                try:
                    cl = classify_url(url, config)
                    if cl.source_type == URLSourceType.BRAND_OWNED:
                        brand_owned_now += 1
                except Exception:
                    continue

            target_brand = int(total_target * config.brand_owned_ratio)
            # If we need more brand-owned pages, try extracting subpages
            if brand_owned_now < target_brand:
                need = target_brand - brand_owned_now
                # Iterate over fetched brand-owned primary pages and extract internal links
                for item in list(fetched):
                    if need <= 0:
                        break
                    url = item.get('url') or item.get('platform_id') or item.get('source_url')
                    try:
                        cl = classify_url(url, config)
                        if cl.source_type != URLSourceType.BRAND_OWNED:
                            continue
                        # Try to extract internal links (limit per page)
                        internal = _extract_internal_links(url, item.get('body', ''), max_links=10)
                        for sub in internal:
                            if need <= 0:
                                break
                            try:
                                sub_page = _fetch_page(sub)
                                body = sub_page.get('body') or ''
                                if body and len(body) >= 200:
                                    # attach minimal metadata similar to collectors
                                    sub_page['source_type'] = 'brand_owned'
                                    sub_page['source_tier'] = 'brand_subpage'
                                    fetched.append({
                                        'title': sub_page.get('title', ''),
                                        'body': sub_page.get('body', ''),
                                        'url': sub,
                                        'terms': sub_page.get('terms', ''),
                                        'privacy': sub_page.get('privacy', ''),
                                        'source_type': 'brand_owned',
                                        'source_tier': 'brand_subpage'
                                    })
                                    need -= 1
                            except Exception:
                                continue
                    except Exception:
                        continue
    except Exception:
        # If anything goes wrong in the optional enrichment step, continue gracefully
        pass

    # Ingest Reddit if requested
    if 'reddit' in sources:
        try:
            reddit = RedditCrawler()
            posts = reddit.search_posts(keywords=keywords, limit=10)
            reddit_norm = reddit.convert_to_normalized_content(posts, brand_id, run_id)
            fetched.extend(reddit_norm)
        except Exception as e:
            logger.warning(f"Skipping Reddit ingestion in programmatic run: {e}")

    # Ingest YouTube if requested
    if 'youtube' in sources:
        try:
            try:
                yt = YouTubeScraper()
            except Exception as e:
                # Missing API key or config
                raise
            # Simple query from keywords
            q = ' '.join(keywords)
            videos = yt.search_videos(query=q, max_results=5)
            youtube_norm = yt.convert_videos_to_normalized(videos, brand_id, run_id, include_comments=include_comments)
            fetched.extend(youtube_norm)
        except Exception as e:
            logger.warning(f"Skipping YouTube ingestion in programmatic run: {e}")

    if not fetched:
        raise RuntimeError('No content fetched')

    # Normalize
    normalizer = ContentNormalizer()
    normalized = normalizer.normalize_content(fetched)

    # Score
    scoring_pipeline = ScoringPipeline()
    pipeline_run = scoring_pipeline.run_scoring_pipeline(normalized, {
        'brand_id': brand_id,
        'brand_name': brand_id,
        'keywords': [brand_id],
        'sources': ['brave']
    })

    # Generate reports
    pdf_generator = PDFReportGenerator()
    markdown_generator = MarkdownReportGenerator()

    pdf_path = os.path.join(output_dir, f'ar_report_{brand_id}_{run_id}.pdf')
    md_path = os.path.join(output_dir, f'ar_report_{brand_id}_{run_id}.md')

    scores_list = pipeline_run.classified_scores or []
    scoring_report = scoring_pipeline.generate_scoring_report(scores_list, {
        'brand_id': brand_id,
        'brand_name': brand_id,
        'keywords': [brand_id],
        'sources': ['brave']
    })

    pdf_generator.generate_report(scoring_report, pdf_path, include_items_table=include_items_table)
    markdown_generator.generate_report(scoring_report, md_path)

    return {
        'run_id': run_id,
        'pdf': pdf_path,
        'md': md_path,
        'items': len(normalized)
    }
