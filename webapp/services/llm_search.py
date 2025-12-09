"""
LLM-based search service for brand URL discovery
"""
import re
import json
import logging
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import streamlit as st
except ImportError:
    st = None

from scoring.llm_client import ChatClient
from config.settings import SETTINGS
from webapp.utils.url_utils import is_usa_host, classify_brand_url, is_promotional_url


logger = logging.getLogger(__name__)


def get_brand_domains_from_llm(brand_id: str, model: str = 'gpt-4o-mini') -> List[str]:
    """
    Use LLM to discover all official domains owned by a brand.

    This is used to build site-restricted search queries for more efficient
    brand-controlled URL collection.

    Args:
        brand_id: Brand identifier (e.g., 'mastercard', 'nike')
        model: LLM model to use (default: gpt-4o-mini for cost efficiency)

    Returns:
        List of domains (e.g., ['mastercard.com', 'investor.mastercard.com'])
    """
    prompt = f"""List all official domains and subdomains owned by {brand_id}.

Include:
- Main corporate website
- Investor relations sites
- Product/service sites
- Career/jobs sites
- Newsroom/press sites
- Developer/API sites
- International variants (e.g., .co.uk, .com.au)

Rules:
- One domain per line
- Domain only, no 'www.' prefix
- No URLs, just domains
- No explanations or numbering
- Maximum 15 domains

Example format:
mastercard.com
investor.mastercard.com
priceless.com
"""

    try:
        client = ChatClient(default_model=model)
        messages = [{"role": "user", "content": prompt}]
        
        response = client.chat(
            messages=messages,
            model=model,
            max_tokens=500,
            temperature=0
        )

        text = response.get('content', '').strip()
        logger.debug('LLM domain discovery response:\n%s', text)

        # Parse domains from response
        domains = []
        for line in text.split('\n'):
            line = line.strip()
            # Remove common prefixes/formatting
            line = line.replace('www.', '').replace('http://', '').replace('https://', '')
            line = line.split('/')[0]  # Remove any paths
            line = line.split()[0]  # Take first word if multiple

            # Validate: must contain a dot and look like a domain
            if '.' in line and len(line) > 3 and not line.startswith('#'):
                domains.append(line.lower())

        # Deduplicate and limit
        domains = list(dict.fromkeys(domains))[:15]
        logger.info(f'LLM discovered {len(domains)} domains for {brand_id}: {domains}')

        return domains

    except Exception as e:
        logger.warning(f'LLM domain discovery failed for {brand_id}: {e}')
        return []


def suggest_brand_urls_from_llm(brand_id: str, keywords: List[str], model: str = 'gpt-4o-mini', max_urls: int = 10,
                               brand_domains: List[str] = None, verify_url_func=None,
                               fetch_page_title_func=None, search_urls_fallback_func=None) -> List[Dict[str, Any]]:
    """
    Ask an LLM to enumerate likely brand-owned URLs for the given brand.

    Args:
        brand_id: Brand identifier
        keywords: Search keywords to provide context
        model: LLM model to use
        max_urls: Maximum number of URLs to return
        brand_domains: List of brand domains for classification
        verify_url_func: Function to verify URLs (injected dependency)
        fetch_page_title_func: Function to fetch page titles (injected dependency)
        search_urls_fallback_func: Function for fallback search (injected dependency)

    Returns:
        Ordered list of dictionaries with keys `url` and `is_primary`, where primary entries come first
    """
    prompt = (
        f"Provide up to {max_urls} canonical brand-owned URLs for {brand_id}. "
    f"Include the most relevant primary domains first, followed by any supporting subdomains, english-speaking country variants, and promotional hubs that belong to {brand_id}. "
    "Highlight international domains (e.g., .com.au, .co.uk, .ca, .ie) and other brand-owned marketing sites. "
        "Return only the URLs (one per line), without numbering or explanations."
    )
    try:
        client = ChatClient(default_model=model)
        messages = [
            {'role': 'system', 'content': 'You are a helpful research assistant.'},
            {'role': 'user', 'content': prompt}
        ]
        # Respect config: do not perform LLM/verification for explicitly excluded brands
        excluded = SETTINGS.get('excluded_brands', []) or []
        if brand_id and brand_id.lower() in excluded:
            logger.info('Brand %s is in excluded_brands; skipping LLM enumeration', brand_id)
            return []

        # Ask the model for structured JSON-per-line output: url, evidence, confidence
        # Temporarily enable debug logging for this call so we can capture raw model output
        prev_level = logger.level
        try:
            logger.setLevel(logging.DEBUG)
            response = client.chat(messages=messages, max_tokens=1024)
            text = response.get('content') or response.get('text') or ''
            logger.debug('LLM raw response:\n%s', text)
        finally:
            logger.setLevel(prev_level)

        # Parse JSON lines if available (model should return one JSON object per line)
        candidates: List[Dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                url = obj.get('url')
                evidence = obj.get('evidence')
                confidence = int(obj.get('confidence') or 0)
                if url:
                    candidates.append({'url': url.strip(), 'evidence': evidence, 'confidence': confidence})
            except Exception:
                # Fall back to regex extraction per-line if JSON parse fails
                m = re.search(r'(https?://[\w\-\.\/\%\?&=#:]+)', line)
                if m:
                    candidates.append({'url': m.group(1).strip(), 'evidence': None, 'confidence': 0})
        # Build a deduped candidate list, respecting the order and any model confidence
        seen_urls = set()
        deduped_candidates: List[Dict[str, Any]] = []
        for c in candidates:
            url = c['url'].rstrip('.,;')
            if url in seen_urls:
                continue
            seen_urls.add(url)
            # prefer US/.com hosts only
            if not is_usa_host(url):
                continue
            is_primary = classify_brand_url(url, brand_id, brand_domains) == 'primary'
            deduped_candidates.append({
                'url': url,
                'evidence': c.get('evidence'),
                'confidence': c.get('confidence', 0),
                'is_primary': is_primary
            })
        # Log parsed candidates for debugging (INFO so it appears in typical logs)
        try:
            logger.info('Parsed LLM candidates (deduped, US-only): %s', json.dumps(deduped_candidates, indent=2))
        except Exception:
            logger.info('Parsed LLM candidates (deduped, US-only): %s', str(deduped_candidates))

        # Verify candidates in parallel, prioritizing primaries
        ordered = sorted(deduped_candidates, key=lambda x: (0 if x['is_primary'] else 1, -int(x.get('confidence', 0))))

        verified_entries: List[Dict[str, Any]] = []

        max_workers = min(20, max(4, len(ordered)))
        with ThreadPoolExecutor(max_workers=max_workers) as exe:
            future_to_entry = {exe.submit(verify_url_func, e['url'], brand_id): e for e in ordered}
            for fut in as_completed(future_to_entry):
                entry = future_to_entry[fut]
                try:
                    result = fut.result()
                except Exception as exc:
                    logger.debug('Verification raised for %s: %s', entry['url'], exc)
                    continue
                if result and result.get('ok'):
                    # fetch title for display
                    title = fetch_page_title_func(result.get('final_url') or entry['url'], brand_id)
                    verified_entries.append({
                        'url': result.get('final_url') or entry['url'],
                        'is_primary': entry['is_primary'],
                        'verified': True,
                        'status': result.get('status'),
                        'soft_verified': result.get('soft_verified', False),
                        'verification_method': result.get('method'),
                        'title': title,
                        'evidence': entry.get('evidence'),
                        'confidence': entry.get('confidence', 0),
                        'is_promotional': is_promotional_url(entry['url'])
                    })
                else:
                    logger.debug('Unverified candidate: %s (status=%s)', entry['url'], result.get('status') if isinstance(result, dict) else None)
                if len(verified_entries) >= max_urls:
                    break

        if verified_entries:
            # Clear any previous fallback indicator
            try:
                if st and hasattr(st, 'session_state'):
                    if 'llm_search_fallback' in st.session_state:
                        del st.session_state['llm_search_fallback']
                    if 'llm_search_fallback_count' in st.session_state:
                        del st.session_state['llm_search_fallback_count']
            except Exception:
                pass

        if not verified_entries and search_urls_fallback_func:
            logger.info('No verified URLs found after LLM verification for brand: %s. Attempting web-search fallback...', brand_id)
            try:
                fallback = search_urls_fallback_func(brand_id, keywords, target_count=max_urls)
                if fallback:
                    logger.info('Search fallback returned %d verified URLs for %s', len(fallback), brand_id)
                    verified_entries = fallback[:max_urls]
                    # Mark that fallback was used so UI can show a banner
                    try:
                        if st and hasattr(st, 'session_state'):
                            st.session_state['llm_search_fallback'] = True
                            st.session_state['llm_search_fallback_count'] = len(verified_entries)
                    except Exception:
                        pass
                else:
                    logger.warning('Search fallback did not return any verified URLs for brand: %s', brand_id)
            except Exception as e:
                logger.warning('Search fallback failed for %s: %s', brand_id, e)

        return verified_entries[:max_urls]
    except Exception as exc:
        logger.warning('LLM brand URL suggestion failed: %s', exc)
        return []


def enumerate_brand_urls_from_llm_raw(brand_id: str, keywords: List[str], model: str = 'gpt-4o-mini', candidate_limit: int = 100) -> List[str]:
    """Return raw LLM candidates (unverified) so the UI can show them for debugging/verification."""
    # Respect excluded brands config
    excluded = SETTINGS.get('excluded_brands', []) or []
    if brand_id and brand_id.lower() in excluded:
        logger.info('Brand %s is in excluded_brands; skipping raw LLM enumeration', brand_id)
        return []
    prompt = (
        f"Provide up to {candidate_limit} canonical brand-owned URLs for {brand_id}. "
        f"Include primary domains, localized variants, investor/careers pages and promotional hubs. "
        "Return only the URLs (one per line), without numbering or explanations."
    )
    try:
        client = ChatClient(default_model=model)
        messages = [
            {'role': 'system', 'content': 'You are a helpful research assistant.'},
            {'role': 'user', 'content': prompt}
        ]
        # Turn on debug briefly and log the raw response
        prev_level = logger.level
        try:
            logger.setLevel(logging.DEBUG)
            response = client.chat(messages=messages, max_tokens=512)
            text = response.get('content') or response.get('text') or ''
            logger.debug('LLM raw (raw enumerator) response:\n%s', text)
        finally:
            logger.setLevel(prev_level)
        url_candidates = re.findall(r'https?://[\w\-\.\/\%\?&=#:]+', text)
        unique_urls = []
        for url in url_candidates:
            clean_url = url.strip().rstrip('.,;')
            if clean_url not in unique_urls:
                unique_urls.append(clean_url)
            if len(unique_urls) >= candidate_limit:
                break
        return unique_urls
    except Exception:
        return []
