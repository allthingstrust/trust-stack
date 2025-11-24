"""
Analysis Engine Service

This module contains the main analysis pipeline that runs the Trust Stack Rating
analysis on collected content.
"""
import os
import json
import time
import logging
import streamlit as st
from datetime import datetime
from typing import List, Dict, Any

from webapp.services.brand_discovery import detect_brand_owned_url
from webapp.utils.logging_utils import ProgressAnimator, StreamlitLogHandler

logger = logging.getLogger(__name__)


def run_analysis(brand_id: str, keywords: List[str], sources: List[str], max_items: int, web_pages: int, include_comments: bool,
                 selected_urls: List[Dict] = None, search_provider: str = 'serper',
                 brand_domains: List[str] = None, brand_subdomains: List[str] = None, brand_social_handles: List[str] = None,
                 summary_model: str = 'gpt-4o-mini', recommendations_model: str = 'gpt-4o-mini', project_root: str = None):
    """Execute the analysis pipeline"""

    # Use provided project_root or get from environment/default
    if project_root is None:
        # Get PROJECT_ROOT from the main app module
        import sys
        for module_name, module in sys.modules.items():
            if hasattr(module, 'PROJECT_ROOT'):
                project_root = module.PROJECT_ROOT
                break
        if project_root is None:
            # Fallback: assume we're in webapp/services and go up two levels
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Create output directory
    output_dir = os.path.join(project_root, 'output', 'webapp_runs')
    os.makedirs(output_dir, exist_ok=True)

    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = os.path.join(output_dir, f"{brand_id}_{run_id}")
    os.makedirs(run_dir, exist_ok=True)

    # Progress tracking
    progress_bar = st.progress(0)
    
    # Reuse existing progress container if available, otherwise create new one
    if 'progress_container' in st.session_state and st.session_state['progress_container'] is not None:
        progress_animator = ProgressAnimator(container=st.session_state['progress_container'])
    else:
        progress_container = st.empty()
        progress_animator = ProgressAnimator(container=progress_container)
        st.session_state['progress_container'] = progress_container
    
    # Set up log capture for the entire analysis process
    # Attach to root logger to capture logs from all modules
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    log_handler = StreamlitLogHandler(progress_animator)
    log_handler.setLevel(logging.INFO)
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(log_formatter)
    root_logger.addHandler(log_handler)

    try:
        # Step 1: Import modules
        progress_animator.show("Initializing pipeline components...", "🔧")
        progress_bar.progress(10)

        from ingestion.brave_search import collect_brave_pages, fetch_page
        from ingestion.normalizer import ContentNormalizer
        from scoring.pipeline import ScoringPipeline
        from reporting.pdf_generator import PDFReportGenerator
        from reporting.markdown_generator import MarkdownReportGenerator
        from data.models import NormalizedContent

        try:
            from ingestion.reddit_crawler import RedditCrawler
        except:
            RedditCrawler = None

        try:
            from ingestion.youtube_scraper import YouTubeScraper
        except:
            YouTubeScraper = None

        # Step 2: Data Ingestion
        progress_animator.show(f"Ingesting content from {', '.join(sources)}...", "📥")
        progress_bar.progress(20)

        all_content = []

        # Web search ingestion (using selected provider)
        if 'web' in sources:
            # If URLs were pre-selected, use only those
            if selected_urls:
                # Filter URLs from the current search provider
                selected_web_urls = [u for u in selected_urls if u['source'] in ['brave', 'serper', 'web']]
                collected = []

                for url_data in selected_web_urls:
                    try:
                        page_data = fetch_page(url_data['url'])
                        if page_data and page_data.get('body'):
                            # Add brand-owned flag to metadata
                            page_data['is_brand_owned'] = url_data.get('is_brand_owned', False)
                            collected.append(page_data)
                    except Exception as e:
                        st.warning(f"⚠️ Could not fetch {url_data['url']}: {str(e)}")

                st.info(f"✓ Fetched {len(collected)} of {len(selected_web_urls)} selected web pages")
            else:
                # Original behavior: search and fetch automatically
                query = ' '.join(keywords)

                # Use the unified search interface with the selected provider
                from ingestion.search_unified import search
                search_results = search(query, size=web_pages, provider=search_provider)

                collected = []
                for result in search_results:
                    url = result.get('url', '')
                    if url:
                        try:
                            page_data = fetch_page(url)
                            if page_data and page_data.get('body'):
                                # Add metadata from search result
                                page_data['search_title'] = result.get('title', '')
                                page_data['search_snippet'] = result.get('snippet', '')
                                classification = detect_brand_owned_url(url, brand_id, brand_domains, brand_subdomains, brand_social_handles)
                                page_data['is_brand_owned'] = classification['is_brand_owned']
                                page_data['source_type'] = classification['source_type']
                                page_data['source_tier'] = classification['source_tier']
                                collected.append(page_data)
                        except Exception as e:
                            st.warning(f"⚠️ Could not fetch {url}: {str(e)}")

                st.info(f"✓ Collected {len(collected)} web pages using {search_provider}")

            # Convert to NormalizedContent
            for i, c in enumerate(collected):
                url = c.get('url')
                content_id = f"{search_provider}_{i}_{abs(hash(url or ''))}"
                is_brand_owned = c.get('is_brand_owned', False)

                meta = {
                    'source_url': url or '',
                    'content_type': 'web',
                    'title': c.get('title', ''),
                    'description': c.get('body', '')[:200],
                    'is_brand_owned': is_brand_owned,  # Add brand-owned flag to metadata
                    'search_provider': search_provider  # Track which provider was used
                }
                if c.get('terms'):
                    meta['terms'] = c.get('terms')
                if c.get('privacy'):
                    meta['privacy'] = c.get('privacy')

                nc = NormalizedContent(
                    content_id=content_id,
                    src=search_provider,
                    platform_id=url or '',
                    author='web',
                    title=c.get('title', '') or '',
                    body=c.get('body', '') or '',
                    run_id=run_id,
                    event_ts=datetime.now().isoformat(),
                    meta=meta,
                    url=url or '',
                    modality='text',
                    channel='web',
                    platform_type='web',
                    source_type=c.get('source_type', 'unknown'),
                    source_tier=c.get('source_tier', 'unknown'),
                    structured_body=c.get('structured_body')  # Include HTML structure metadata
                )
                all_content.append(nc)

        # Reddit ingestion
        if 'reddit' in sources and RedditCrawler:
            try:
                reddit = RedditCrawler()
                posts = reddit.search_posts(keywords=keywords, limit=max_items // len(sources))
                reddit_content = reddit.convert_to_normalized_content(posts, brand_id, run_id)
                all_content.extend(reddit_content)
                st.info(f"✓ Collected {len(reddit_content)} Reddit posts")
            except Exception as e:
                st.warning(f"⚠️ Reddit ingestion failed: {e}")

        # YouTube ingestion
        if 'youtube' in sources and YouTubeScraper:
            try:
                yt = YouTubeScraper()
                query = ' '.join(keywords)
                videos = yt.search_videos(query=query, max_results=max_items // len(sources))
                youtube_content = yt.convert_videos_to_normalized(videos, brand_id, run_id, include_comments=include_comments)
                all_content.extend(youtube_content)
                st.info(f"✓ Collected {len(youtube_content)} YouTube videos")
            except Exception as e:
                st.warning(f"⚠️ YouTube ingestion failed: {e}")

        if not all_content:
            st.error("❌ No content collected from any source")
            return

        # Step 3: Normalization
        progress_animator.show("Normalizing content...", "🔄")
        progress_bar.progress(40)

        normalizer = ContentNormalizer()
        normalized_content = normalizer.normalize_content(all_content)

        # Step 4: Scoring
        progress_animator.show("Scoring content on 5D Trust dimensions...", "📊")
        progress_bar.progress(60)

        scoring_pipeline = ScoringPipeline()
        
        # Get use_guidelines preference from session state
        use_guidelines = st.session_state.get('use_guidelines', True)
        
        brand_config = {
            'brand_id': brand_id,
            'brand_name': brand_id,
            'keywords': keywords,
            'sources': sources,
            'use_guidelines': use_guidelines  # Pass guidelines preference to scorer
        }

        pipeline_run = scoring_pipeline.run_scoring_pipeline(normalized_content, brand_config)

        # Step 5: Generate Reports
        progress_animator.show("Generating reports...", "📄")
        progress_bar.progress(80)

        scores_list = pipeline_run.classified_scores or []
        scoring_report = scoring_pipeline.generate_scoring_report(scores_list, brand_config)

        # Add LLM model configuration to the report for use in executive summary
        scoring_report['llm_model'] = summary_model
        scoring_report['recommendations_model'] = recommendations_model
        scoring_report['use_llm_summary'] = True  # Enable LLM-powered summaries

        # Generate PDF
        pdf_generator = PDFReportGenerator()
        pdf_path = os.path.join(run_dir, f'ar_report_{brand_id}_{run_id}.pdf')
        pdf_generator.generate_report(scoring_report, pdf_path, include_items_table=True)

        # Generate Markdown
        markdown_generator = MarkdownReportGenerator()
        md_path = os.path.join(run_dir, f'ar_report_{brand_id}_{run_id}.md')
        markdown_generator.generate_report(scoring_report, md_path)

        # Save run data for visualization
        run_data = {
            'run_id': run_id,
            'brand_id': brand_id,
            'keywords': keywords,
            'sources': sources,
            'timestamp': datetime.now().isoformat(),
            'pdf_path': pdf_path,
            'md_path': md_path,
            'scoring_report': scoring_report,
            'total_items': len(normalized_content)
        }

        data_path = os.path.join(run_dir, '_run_data.json')
        with open(data_path, 'w') as f:
            json.dump(run_data, f, indent=2, default=str)

        # Complete
        progress_bar.progress(100)
        progress_animator.show("Analysis complete!", "✅")
        progress_animator.clear()
        
        # Clear the progress container from session state so it doesn't appear on results page
        if 'progress_container' in st.session_state:
            st.session_state['progress_container'] = None

        st.success(f"✅ Analysis completed successfully! Analyzed {len(normalized_content)} content items.")

        # Store in session state
        st.session_state['last_run'] = run_data

        # Switch to results view
        time.sleep(1)
        st.session_state['page'] = 'results'
        st.rerun()

    except Exception as e:
        st.error(f"❌ Analysis failed: {e}")
        import traceback
        st.code(traceback.format_exc())
    
    finally:
        # Clean up log handler
        try:
            if log_handler and root_logger:
                root_logger.removeHandler(log_handler)
                if original_level is not None:
                    root_logger.setLevel(original_level)
        except:
            pass
