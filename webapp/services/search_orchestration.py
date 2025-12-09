"""
Search Orchestration Service

This module coordinates the main URL search and discovery process,
including web search, social media discovery, and URL classification.
"""
import os
import logging
import time
import streamlit as st
from typing import List, Dict, Any

from webapp.utils.logging_utils import StreamlitLogHandler, ProgressAnimator
from webapp.utils.url_utils import is_login_page, is_core_domain
from webapp.services.brand_discovery import detect_brand_owned_url
from webapp.services.llm_search import get_brand_domains_from_llm
from webapp.services.social_search import search_social_media_channels
from ingestion.page_fetcher import fetch_pages_parallel
from ingestion.playwright_manager import get_browser_manager

logger = logging.getLogger(__name__)


def perform_initial_search(brand_id: str, keywords: List[str], sources: List[str], web_pages: int, search_provider: str = 'serper',
                    brand_domains: List[str] = None, brand_subdomains: List[str] = None, brand_social_handles: List[str] = None,
                    collection_strategy: str = 'both', brand_owned_ratio: int = 60, search_model: str = 'gpt-4o-mini'):
    """
    Step 1: Search for URLs and store them in session state for user selection.
    Does NOT fetch page content yet.
    """
    
    # Initialize log handler variables for cleanup in finally block
    log_handler = None
    search_logger = None
    original_level = None

    # Use the pre-created progress container placeholder from the main page
    if 'progress_container_placeholder' in st.session_state and st.session_state['progress_container_placeholder'] is not None:
        progress_container = st.session_state['progress_container_placeholder']
    else:
        progress_container = st.empty()
    
    progress_animator = ProgressAnimator(container=progress_container)
    st.session_state['progress_container'] = progress_container
    
    progress_bar = st.progress(0)

    try:
        progress_animator.show("Initializing web search engine...", "🚀")
        progress_bar.progress(10)

        found_urls = []

        # Social media search - find official brand channels
        progress_animator.show("Searching for official social media channels...", "📱")
        progress_bar.progress(15)
        social_results = search_social_media_channels(brand_id, search_provider, progress_animator, logger)
        if social_results:
            logger.info(f"Found {len(social_results)} potential social media channels")
            for result in social_results:
                found_urls.append(result)

        # Web search (using selected provider: Brave or Serper)
        if 'web' in sources:
            base_query = ' '.join(keywords)

            # For brand-controlled searches, use LLM to discover domains and restrict search
            if collection_strategy == 'brand_controlled':
                # Check cache first to avoid repeated LLM calls
                cache_key = f'brand_domains_{brand_id}'
                if cache_key in st.session_state:
                    llm_domains = st.session_state[cache_key]
                    logger.info(f'Using cached domains for {brand_id}: {llm_domains}')
                    progress_animator.show(f"Using {len(llm_domains)} cached brand domains for {brand_id}", "📦")
                else:
                    progress_animator.show(f"Discovering brand domains for {brand_id} using AI...", "🤖")
                    llm_domains = get_brand_domains_from_llm(brand_id, model=search_model)
                    # Cache for this session
                    st.session_state[cache_key] = llm_domains

                if llm_domains:
                    # Build site-restricted query using discovered domains
                    site_filters = " OR ".join([f"site:{domain}" for domain in llm_domains[:10]])
                    query = f"{base_query} ({site_filters})"
                    logger.info(f'Built site-restricted query for {brand_id}: {len(llm_domains)} domains')
                    progress_animator.show(f"Targeting {len(llm_domains)} verified brand domains", "🎯")
                else:
                    # Fallback to regular query if LLM fails
                    query = base_query
                    logger.warning(f'LLM domain discovery returned no domains for {brand_id}, using regular query')
                    progress_animator.show("Proceeding with general web search", "🌐")
            else:
                query = base_query

            provider_display = 'Brave Search' if search_provider == 'brave' else 'Google (via Serper)'
            provider_emoji = '🌐' if search_provider == 'brave' else '🔍'
            progress_animator.show(f"Querying {provider_display} for: {query[:80]}...", provider_emoji)
            progress_bar.progress(30)

            try:
                # Configure timeout for larger requests
                original_timeout = os.environ.get('BRAVE_API_TIMEOUT')
                timeout_seconds = min(30, 10 + (web_pages // 10))
                os.environ['BRAVE_API_TIMEOUT'] = str(timeout_seconds)

                # Set up log capture
                search_logger = logging.getLogger()
                original_level = search_logger.level
                search_logger.setLevel(logging.INFO)
                log_handler = StreamlitLogHandler(progress_animator)
                log_handler.setLevel(logging.INFO)
                log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                log_handler.setFormatter(log_formatter)
                search_logger.addHandler(log_handler)

                search_results = []
                search_start_time = time.time()

                if search_provider == 'brave':
                    from ingestion.brave_search import search_brave
                    progress_animator.show(f"Executing Brave Search API requests...", "🌐")
                    
                    # Search ONLY (no fetching)
                    # Request slightly more than needed to account for duplicates/filters
                    search_size = int(web_pages * 1.5)
                    raw_results = search_brave(query, size=search_size)
                    
                    for item in raw_results:
                        search_results.append({
                            'url': item.get('url'),
                            'title': item.get('title', 'No title'),
                            'snippet': item.get('snippet', '')
                        })

                else:  # serper
                    from ingestion.serper_search import search_serper
                    progress_animator.show(f"Executing Google Search API requests...", "⚡")
                    
                    # Search ONLY (no fetching)
                    search_size = int(web_pages * 1.5)
                    raw_results = search_serper(query, size=search_size)
                    
                    for item in raw_results:
                        search_results.append({
                            'url': item.get('url'),
                            'title': item.get('title', 'No title'),
                            'snippet': item.get('snippet', '')
                        })

                search_duration = time.time() - search_start_time
                st.session_state['last_search_duration'] = search_duration
                logger.info(f"Search completed in {search_duration:.2f} seconds")

                progress_bar.progress(60)

                # Restore original timeout
                if original_timeout is not None:
                    os.environ['BRAVE_API_TIMEOUT'] = original_timeout
                else:
                    os.environ.pop('BRAVE_API_TIMEOUT', None)

                if not search_results:
                    st.warning(f"⚠️ No search results found. Try different keywords or check your {search_provider.upper()} API configuration.")
                    progress_bar.empty()
                    progress_animator.clear()
                    return

                # Classify URLs
                total_results = len(search_results)
                filtered_count = 0
                
                # Deduplicate based on URL
                seen_urls = set(u['url'] for u in found_urls) # Start with social URLs
                
                for idx, result in enumerate(search_results):
                    url = result.get('url', '')
                    if not url or url in seen_urls:
                        continue
                    
                    seen_urls.add(url)

                    # Filter out login pages
                    if is_login_page(url):
                        filtered_count += 1
                        continue

                    # Show classification progress
                    progress_animator.show(
                        f"Classifying URL {idx + 1}/{total_results}",
                        "🏷️",
                        url=url
                    )

                    classification = detect_brand_owned_url(url, brand_id, brand_domains, brand_subdomains, brand_social_handles)
                    is_core = is_core_domain(url, brand_domains)

                    found_urls.append({
                        'url': url,
                        'title': result.get('title', 'No title'),
                        'description': result.get('snippet', ''),
                        'is_brand_owned': classification['is_brand_owned'],
                        'is_core_domain': is_core,
                        'source_type': classification['source_type'],
                        'source_tier': classification['source_tier'],
                        'classification_reason': classification['reason'],
                        'selected': True,  # Default to selected
                        'source': search_provider,
                        'fetched': False  # Mark as not yet fetched
                    })

                    progress_percent = 60 + int((idx + 1) / total_results * 30)
                    progress_bar.progress(min(progress_percent, 90))

                # Sort URLs
                found_urls.sort(key=lambda x: (
                    not x.get('is_core_domain', False),
                    not x['is_brand_owned'],
                    x['url']
                ))

                st.session_state['found_urls'] = found_urls
                
                brand_owned_count = sum(1 for u in found_urls if u['is_brand_owned'])
                third_party_count = sum(1 for u in found_urls if not u['is_brand_owned'])
                
                progress_bar.progress(100)
                progress_animator.show(f"Search complete! Found {len(found_urls)} URLs. Please select URLs to analyze.", "✅")
                
                time.sleep(1) # Let user see the success message
                progress_bar.empty()
                st.rerun()

            except Exception as e:
                logger.error(f"Error during search: {e}")
                st.error(f"❌ Search failed: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error in perform_initial_search: {e}")
        st.error(f"❌ Unexpected error: {str(e)}")

    finally:
        # Clean up
        try:
            progress_bar.empty()
            if 'progress_animator' in locals():
                progress_animator.clear()
            if search_logger and log_handler:
                search_logger.removeHandler(log_handler)
                if original_level is not None:
                    search_logger.setLevel(original_level)
        except:
            pass


def fetch_and_process_selected_urls(selected_urls: List[Dict[str, Any]]):
    """
    Step 2: Fetch content for the selected URLs.
    """
    if not selected_urls:
        return []

    # Initialize progress
    if 'progress_container_placeholder' in st.session_state and st.session_state['progress_container_placeholder'] is not None:
        progress_container = st.session_state['progress_container_placeholder']
    else:
        progress_container = st.empty()
    
    progress_animator = ProgressAnimator(container=progress_container)
    progress_bar = st.progress(0)
    
    try:
        urls_to_fetch = [u['url'] for u in selected_urls if not u.get('fetched', False)]
        already_fetched = [u for u in selected_urls if u.get('fetched', False)]
        
        if not urls_to_fetch:
            return selected_urls

        progress_animator.show(f"Fetching content for {len(urls_to_fetch)} URLs...", "📥")
        
        # Set up logging
        search_logger = logging.getLogger()
        log_handler = StreamlitLogHandler(progress_animator)
        log_handler.setLevel(logging.INFO)
        log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log_handler.setFormatter(log_formatter)
        search_logger.addHandler(log_handler)

        # Initialize persistent browser manager
        browser_manager = None
        try:
            browser_manager = get_browser_manager()
            if browser_manager.start():
                logger.info('[ORCHESTRATION] Initialized persistent Playwright browser for delayed fetch')
            else:
                browser_manager = None
        except Exception as e:
            logger.warning('[ORCHESTRATION] Could not start persistent browser: %s', e)
            browser_manager = None

        # Fetch pages in parallel
        fetched_results = fetch_pages_parallel(urls_to_fetch, max_workers=5, browser_manager=browser_manager)
        
        # Map results back to original objects
        processed_urls = []
        
        # Add already fetched ones first
        processed_urls.extend(already_fetched)
        
        # Process new results
        for idx, result in enumerate(fetched_results):
            url = result.get('url')
            # Find corresponding original object
            original = next((u for u in selected_urls if u['url'] == url), None)
            
            if original:
                # Update with fetched content
                original['title'] = result.get('title') or original.get('title', 'No title')
                original['body'] = result.get('body', '')
                original['status'] = 200 if result.get('body') else 0 # Simple status proxy
                original['fetched'] = True
                
                # Check for thin content
                if not original['body'] or len(original['body']) < 200:
                    original['warning'] = "Thin content"
                
                processed_urls.append(original)
            
            progress_percent = int((idx + 1) / len(fetched_results) * 100)
            progress_bar.progress(progress_percent)
            progress_animator.show(f"Processed {idx + 1}/{len(fetched_results)} URLs", "📄", url=url)

        search_logger.removeHandler(log_handler)
        progress_bar.empty()
        progress_animator.clear()
        
        return processed_urls

    except Exception as e:
        logger.error(f"Error fetching pages: {e}")
        st.error(f"❌ Error fetching pages: {str(e)}")
        return selected_urls
    finally:
        try:
            progress_bar.empty()
            progress_animator.clear()
        except:
            pass
