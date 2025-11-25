"""
Search Orchestration Service

This module coordinates the main URL search and discovery process,
including web search, social media discovery, and URL classification.
"""
import os
import logging
import streamlit as st
from typing import List, Dict, Any

from webapp.utils.logging_utils import StreamlitLogHandler, ProgressAnimator
from webapp.utils.url_utils import is_login_page, is_core_domain
from webapp.services.brand_discovery import detect_brand_owned_url
from webapp.services.llm_search import get_brand_domains_from_llm
from webapp.services.social_search import search_social_media_channels

logger = logging.getLogger(__name__)


def search_for_urls(brand_id: str, keywords: List[str], sources: List[str], web_pages: int, search_provider: str = 'serper',
                    brand_domains: List[str] = None, brand_subdomains: List[str] = None, brand_social_handles: List[str] = None,
                    collection_strategy: str = 'both', brand_owned_ratio: int = 60):
    """Search for URLs and store them in session state for user selection"""
    
    # Initialize log handler variables for cleanup in finally block
    log_handler = None
    search_logger = None
    original_level = None

    # Use the pre-created progress container placeholder from the main page
    # This ensures the progress indicator appears in the correct location (below URLs)
    if 'progress_container_placeholder' in st.session_state and st.session_state['progress_container_placeholder'] is not None:
        progress_container = st.session_state['progress_container_placeholder']
    else:
        # Fallback: create a new container if placeholder doesn't exist
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
                    llm_domains = get_brand_domains_from_llm(brand_id, model='gpt-4o-mini')
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
                # Configure timeout for larger requests (scale with number of pages)
                # Each pagination batch needs time, so scale appropriately
                original_timeout = os.environ.get('BRAVE_API_TIMEOUT')
                timeout_seconds = min(30, 10 + (web_pages // 10))
                os.environ['BRAVE_API_TIMEOUT'] = str(timeout_seconds)

                # Calculate expected number of API requests
                if search_provider == 'brave':
                    max_per_request = int(os.getenv('BRAVE_API_MAX_COUNT', '20'))
                else:  # serper
                    # Serper returns 10 results per page, regardless of the num parameter
                    max_per_request = 10

                expected_requests = (web_pages + max_per_request - 1) // max_per_request  # Ceiling division

                if expected_requests > 1:
                    logger.info(f"Searching {search_provider}: query={query}, size={web_pages}, will make ~{expected_requests} paginated requests")
                    progress_animator.show(f"Preparing {expected_requests} API requests to fetch {web_pages} URLs", "📡")
                else:
                    logger.info(f"Searching {search_provider}: query={query}, size={web_pages}")
                    progress_animator.show(f"Fetching up to {web_pages} search results", "📡")

                # Create URLCollectionConfig for ratio enforcement
                url_collection_config = None
                if collection_strategy in ["brand_controlled", "both", "third_party"]:
                    # For brand_controlled and both, we need brand_domains to identify brand URLs
                    # For third_party, we can proceed with empty brand_domains (everything is 3rd party)
                    if collection_strategy in ["brand_controlled", "both"] and not brand_domains:
                        logger.error(f"⚠️ FILTERING DISABLED: {collection_strategy} strategy requires brand_domains, but none were provided. All URLs (brand-owned AND third-party) will be collected without filtering.")
                        logger.error(f"⚠️ This means third-party URLs will appear in results even with 'brand-controlled' selected!")
                    else:
                        from ingestion.domain_classifier import URLCollectionConfig

                        # Convert percentage to decimal ratio
                        brand_ratio = brand_owned_ratio / 100.0
                        third_party_ratio = 1.0 - brand_ratio

                        url_collection_config = URLCollectionConfig(
                            brand_owned_ratio=brand_ratio,
                            third_party_ratio=third_party_ratio,
                            brand_domains=brand_domains or [],
                            brand_subdomains=brand_subdomains or [],
                            brand_social_handles=brand_social_handles or []
                        )
                        logger.info(f"✓ Created URLCollectionConfig with {collection_strategy} strategy: {brand_ratio:.1%} brand-owned, {third_party_ratio:.1%} 3rd party")
                        logger.info(f"✓ Brand domains for filtering: {brand_domains[:5]}{'...' if len(brand_domains) > 5 else ''} ({len(brand_domains)} total)")
                        logger.info(f"✓ Brand subdomains: {brand_subdomains[:3]}{'...' if len(brand_subdomains) > 3 else ''} ({len(brand_subdomains)} total)")
                        logger.info(f"✓ Social handles: {brand_social_handles[:3]}{'...' if len(brand_social_handles) > 3 else ''} ({len(brand_social_handles)} total)")

                progress_bar.progress(50)

                # Use collect functions for ratio enforcement
                search_results = []
                # Use 5x pool size to account for access-denied URLs and stricter content filtering
                pool_size = web_pages * 5

                progress_animator.show(f"Collecting from pool of {pool_size} URLs with {collection_strategy} filtering", "🔄")

                # Set up log capture for the entire search process
                # Attach to root logger to capture logs from all modules
                search_logger = logging.getLogger()  # Root logger
                original_level = search_logger.level
                search_logger.setLevel(logging.INFO)  # Ensure logger captures INFO level
                log_handler = StreamlitLogHandler(progress_animator)
                log_handler.setLevel(logging.INFO)
                # Use full formatter with timestamp
                log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                log_handler.setFormatter(log_formatter)
                search_logger.addHandler(log_handler)

                if search_provider == 'brave':
                    from ingestion.brave_search import collect_brave_pages
                    progress_animator.show(f"Executing Brave Search API requests ({brand_owned_ratio}% brand-owned target)", "🌐")

                    pages = collect_brave_pages(
                        query=query,
                        target_count=web_pages,
                        pool_size=pool_size,
                        url_collection_config=url_collection_config
                    )
                    # Convert to search result format and show URLs as we process them
                    total_pages = len(pages)
                    for idx, page in enumerate(pages):
                        url = page.get('url', '')
                        # Show each URL as it's being inspected
                        progress_animator.show(
                            f"Inspecting result {idx + 1}/{total_pages}",
                            "🔍",
                            url=url
                        )
                        search_results.append({
                            'url': url,
                            'title': page.get('title', 'No title'),
                            'snippet': page.get('body', '')[:200]
                        })
                        # Update progress proportionally (50% -> 70%)
                        progress_percent = 50 + int((idx + 1) / total_pages * 20)
                        progress_bar.progress(min(progress_percent, 70))
                else:  # serper
                    from ingestion.serper_search import collect_serper_pages
                    progress_animator.show(f"Executing Google Search API requests ({brand_owned_ratio}% brand-owned target)", "⚡")

                    # Set up log capture for the entire search process
                    # Attach to root logger to capture logs from all modules
                    search_logger = logging.getLogger()  # Root logger
                    original_level = search_logger.level
                    search_logger.setLevel(logging.INFO)  # Ensure logger captures INFO level
                    log_handler = StreamlitLogHandler(progress_animator)
                    log_handler.setLevel(logging.INFO)
                    # Use full formatter with timestamp
                    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                    log_handler.setFormatter(log_formatter)
                    search_logger.addHandler(log_handler)

                    pages = collect_serper_pages(
                        query=query,
                        target_count=web_pages,
                        pool_size=pool_size,
                        url_collection_config=url_collection_config
                    )
                    # Convert to search result format and show URLs as we process them
                    total_pages = len(pages)
                    for idx, page in enumerate(pages):
                        url = page.get('url', '')
                        # Show each URL as it's being inspected
                        progress_animator.show(
                            f"Inspecting result {idx + 1}/{total_pages}",
                            "🔍",
                            url=url
                        )
                        search_results.append({
                            'url': url,
                            'title': page.get('title', 'No title'),
                            'snippet': page.get('body', '')[:200]
                        })
                        # Update progress proportionally (50% -> 70%)
                        progress_percent = 50 + int((idx + 1) / total_pages * 20)
                        progress_bar.progress(min(progress_percent, 70))

                progress_bar.progress(70)

                # Restore original timeout
                if original_timeout is not None:
                    os.environ['BRAVE_API_TIMEOUT'] = original_timeout
                else:
                    os.environ.pop('BRAVE_API_TIMEOUT', None)

                if not search_results:
                    st.warning(f"⚠️ No search results found. Try different keywords or check your {search_provider.upper()} API configuration.")

                    # Provide helpful diagnostics
                    st.info("**Troubleshooting tips:**")
                    if search_provider == 'brave':
                        st.markdown("""
                        - **Check your Brave API key**: Ensure `BRAVE_API_KEY` environment variable is set
                        - **Check the logs**: Look at the terminal/console for detailed error messages
                        - **Try fewer pages**: Start with 10-20 pages to test the connection
                        - **Verify API quota**: Your Brave API plan may have reached its limit
                        - **Check search query**: Try simpler, more common keywords first
                        """)
                    else:  # serper
                        st.markdown("""
                        - **Check your Serper API key**: Ensure `SERPER_API_KEY` environment variable is set
                        - **Check the logs**: Look at the terminal/console for detailed error messages
                        - **Try fewer pages**: Start with 10-20 pages to test the connection
                        - **Verify API quota**: Your Serper API plan may have reached its limit
                        - **Check search query**: Try simpler, more common keywords first
                        """)

                    # Show current configuration for debugging
                    with st.expander("🔍 Show Configuration Details"):
                        if search_provider == 'brave':
                            st.code(f"""
Provider: Brave Search
Query: {query}
Pages requested: {web_pages}
Timeout: {timeout_seconds}s
API Key set: {'Yes' if os.getenv('BRAVE_API_KEY') else 'No'}
API Endpoint: {os.getenv('BRAVE_API_ENDPOINT', 'https://api.search.brave.com/res/v1/web/search')}
""")
                        else:
                            st.code(f"""
Provider: Serper (Google Search)
Query: {query}
Pages requested: {web_pages}
Timeout: {timeout_seconds}s
API Key set: {'Yes' if os.getenv('SERPER_API_KEY') else 'No'}
""")

                    progress_bar.empty()
                    progress_animator.clear()
                    return

                # Classify URLs and show them as we process them
                total_results = len(search_results)
                filtered_count = 0
                for idx, result in enumerate(search_results):
                    url = result.get('url', '')
                    if url:
                        # Filter out login pages
                        if is_login_page(url):
                            filtered_count += 1
                            logger.debug(f"Filtered out login page: {url}")
                            continue

                        # Show the current URL being classified (rotate through them)
                        progress_animator.show(
                            f"Classifying URL {idx + 1}/{total_results}",
                            "🏷️",
                            url=url
                        )

                        classification = detect_brand_owned_url(url, brand_id, brand_domains, brand_subdomains, brand_social_handles)

                        # Check if this is a core domain
                        is_core = is_core_domain(url, brand_domains)

                        found_urls.append({
                            'url': url,
                            'title': result.get('title', 'No title'),
                            'description': result.get('snippet', result.get('description', '')),
                            'is_brand_owned': classification['is_brand_owned'],
                            'is_core_domain': is_core,
                            'source_type': classification['source_type'],
                            'source_tier': classification['source_tier'],
                            'classification_reason': classification['reason'],
                            'selected': True,  # Default to selected
                            'source': search_provider
                        })

                        # Update progress bar proportionally (70% -> 90%)
                        progress_percent = 70 + int((idx + 1) / total_results * 20)
                        progress_bar.progress(min(progress_percent, 90))

                if filtered_count > 0:
                    logger.info(f"Filtered out {filtered_count} login pages from results")

                # Prioritize URLs by:
                # 1. Core domains first (mastercard.com, mastercard.co.uk)
                # 2. Other brand-owned URLs
                # 3. Third-party URLs
                # Within each category, sort alphabetically by URL
                found_urls.sort(key=lambda x: (
                    not x.get('is_core_domain', False),  # Core domains first
                    not x['is_brand_owned'],              # Then brand-owned
                    x['url']                               # Then alphabetically
                ))
                logger.info(f"Sorted {len(found_urls)} URLs with core domains prioritized (filtered {filtered_count} login pages)")

                progress_bar.progress(90)
                st.session_state['found_urls'] = found_urls

                brand_owned_count = sum(1 for u in found_urls if u['is_brand_owned'])
                third_party_count = sum(1 for u in found_urls if not u['is_brand_owned'])
                social_count = sum(1 for u in found_urls if u.get('platform'))

                progress_bar.progress(100)
                if social_count > 0:
                    progress_animator.show(f"Search complete! Found {brand_owned_count} brand + {third_party_count} 3rd-party URLs (including {social_count} social channels)", "✅")
                else:
                    progress_animator.show(f"Search complete! Found {brand_owned_count} brand + {third_party_count} 3rd-party URLs", "✅")
                
                progress_bar.empty()

                if social_count > 0:
                    st.success(f"✓ Found {len(found_urls)} URLs ({brand_owned_count} brand-owned including {social_count} social channels, {third_party_count} third-party)")
                else:
                    st.success(f"✓ Found {len(found_urls)} URLs ({brand_owned_count} brand-owned, {third_party_count} third-party)")
                st.rerun()

            except TimeoutError as e:
                logger.error(f"Timeout error during {search_provider} search: {e}")
                st.error(f"⏱️ Search timed out after {timeout_seconds} seconds. Try requesting fewer URLs or check your network connection.")

            except ConnectionError as e:
                logger.error(f"Connection error during {search_provider} search: {e}")
                st.error(f"🌐 Connection error: Could not reach {search_provider.upper()} API. Please check your internet connection.")

            except Exception as e:
                logger.error(f"Error during {search_provider} search: {type(e).__name__}: {e}")
                st.error(f"❌ Search failed: {type(e).__name__}: {str(e)}")

                # Show more helpful error messages for common issues
                if 'api' in str(e).lower() or 'key' in str(e).lower():
                    api_key_name = 'BRAVE_API_KEY' if search_provider == 'brave' else 'SERPER_API_KEY'
                    st.info(f"💡 Tip: Check that your {api_key_name} is set correctly in your environment.")
                elif 'timeout' in str(e).lower():
                    st.info("💡 Tip: Try reducing the number of web pages to fetch, or check your network connection.")

    except Exception as e:
        logger.error(f"Unexpected error in search_for_urls: {type(e).__name__}: {e}")
        st.error(f"❌ Unexpected error: {type(e).__name__}: {str(e)}")

    finally:
        # Clean up progress indicators
        try:
            progress_bar.empty()
            if 'progress_animator' in locals():
                progress_animator.clear()
            
            # Ensure progress container is cleared from session state
            if 'progress_container' in st.session_state:
                if st.session_state['progress_container'] is not None:
                    st.session_state['progress_container'].empty()
                st.session_state['progress_container'] = None

            # Also clear the placeholder itself
            if 'progress_container_placeholder' in st.session_state:
                if st.session_state['progress_container_placeholder'] is not None:
                    st.session_state['progress_container_placeholder'].empty()
                st.session_state['progress_container_placeholder'] = None

            # Clean up log handler if it was created
            if search_logger:
                # Remove ALL StreamlitLogHandlers to be safe
                handlers_to_remove = [h for h in search_logger.handlers if isinstance(h, StreamlitLogHandler)]
                for h in handlers_to_remove:
                    search_logger.removeHandler(h)
                
                if original_level is not None:
                    search_logger.setLevel(original_level)
        except:
            pass
