# Search Architecture Documentation

## Overview

The Authenticity Ratio search system is a high-performance, multi-threaded web search and content collection pipeline that discovers and fetches web pages for brand analysis. The system recently achieved a **major performance improvement**, reducing search times from **128.76 seconds to ~34.47 seconds** (73% faster) through per-domain rate limiting optimizations.

**Last Updated**: 2025-11-28  
**Current Performance**: ~34.47 seconds for typical searches  
**Previous Performance**: 128.76 seconds (before per-domain rate limiting)

---

## Architecture Components

### 1. Search Orchestration (`webapp/services/search_orchestration.py`)

**Purpose**: High-level coordinator for the entire search process

**Key Responsibilities**:
- Manages the overall search workflow
- Coordinates web search, social media discovery, and URL classification
- Provides real-time progress updates via Streamlit UI
- Handles error recovery and user feedback
- Tracks search duration metrics

**Main Function**: `search_for_urls()`

**Flow**:
1. Initialize progress tracking and logging
2. Search for social media channels (if enabled)
3. Execute web search (Brave or Serper)
4. Classify URLs (brand-owned vs third-party)
5. Filter out login pages
6. Sort results (core domains → brand-owned → third-party)
7. Return results to UI

**Performance Tracking**:
```python
search_start_time = time.time()
pages = collect_serper_pages(...)
search_duration = time.time() - search_start_time
st.session_state['last_search_duration'] = search_duration
logger.info(f"Search completed in {search_duration:.2f} seconds")
```

---

### 2. Search Providers

#### Serper Search (`ingestion/serper_search.py`)

**Purpose**: Google Search API integration via Serper.dev

**Key Features**:
- Cost-effective Google search (~$0.30 per 1,000 searches)
- Automatic pagination (10 results per page)
- Producer-Consumer pattern with thread pool
- Per-domain rate limiting for parallel requests
- Smart domain diversity enforcement

**Main Functions**:
- `search_serper()`: Execute API requests with pagination
- `collect_serper_pages()`: Parallel page collection with ratio enforcement

**Producer-Consumer Architecture**:
```
Main Thread (Producer)          Worker Threads (Consumers)
     │                                  │
     ├─► Fetch search results          │
     ├─► Push URLs to queue ──────────►├─► Fetch page content
     ├─► Dynamic batch sizing           ├─► Classify URL
     └─► Monitor progress               ├─► Validate content
                                        └─► Add to results
```

**Performance Optimizations**:
- **5 concurrent workers** for parallel page fetching
- **Per-domain rate limiting** (1.0s interval) allows parallel requests to different domains
- **Dynamic batch sizing** based on success rate
- **Domain diversity limits** (configurable per search strategy)
- **Persistent Playwright browser** for JavaScript-heavy pages

**Configuration**:
```bash
SERPER_API_KEY=<your-key>
SERPER_REQUEST_INTERVAL=1.0  # Per-domain rate limit
SERPER_MAX_PER_REQUEST=100   # Max results per API call
SERPER_API_TIMEOUT=30        # Request timeout
```

#### Brave Search (`ingestion/brave_search.py`)

**Purpose**: Alternative search provider using Brave Search API

**Similar architecture** to Serper with provider-specific adaptations.

---

### 3. Page Fetcher (`ingestion/page_fetcher.py`)

**Purpose**: Unified page fetching with intelligent content extraction

**Key Features**:
- **Multi-strategy content extraction** (article, main, content divs, paragraphs)
- **Structured content detection** (product grids, lists, tables)
- **Smart Playwright fallback** for JavaScript-heavy pages
- **Robots.txt compliance**
- **Session management** for connection pooling
- **Domain-specific configuration learning**

**Content Extraction Strategies** (in priority order):
1. **Structured content**: Product grids, HTML lists, tables
2. **`<article>` tag**: News articles, blog posts
3. **`<main>` tag or `[role="main"]`**: Semantic main content
4. **Content divs**: Divs with content-related class names
5. **All `<p>` tags**: Paragraph aggregation
6. **Longest div**: Heuristic-based selection
7. **Full `<body>`**: Fallback

**Playwright Fallback Logic**:
```python
# Attempt HTTP fetch first
resp = session.get(url, headers=headers, timeout=timeout)

# Fallback to Playwright if:
# - Status code != 200
# - Content is too thin (< 200 chars)
# - Domain is known to require JavaScript rendering
if should_use_playwright(url):
    result = _fetch_with_playwright(url, user_agent, browser_manager)
    if result.get('body') and len(result['body']) >= 150:
        # Mark domain as requiring Playwright for future requests
        _domain_config.mark_requires_playwright(url)
        return result
```

**Parallel Fetching**:
```python
def fetch_pages_parallel(urls, max_workers=5, browser_manager=None):
    # Fetches multiple pages concurrently
    # Uses ThreadPoolExecutor with Streamlit context attachment
    # Returns results in original URL order
```

---

### 4. Rate Limiter (`ingestion/rate_limiter.py`)

**Purpose**: Thread-safe per-domain rate limiting

**Critical Performance Component**: This was the key to the 73% performance improvement!

**How It Works**:
```python
class PerDomainRateLimiter:
    def __init__(self, default_interval=2.0):
        self._domain_last_request: Dict[str, float] = {}
        self._domain_locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()  # Lock for managing locks
    
    def wait_for_domain(self, url: str):
        domain = urlparse(url).netloc
        
        # Get or create domain-specific lock
        with self._locks_lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = threading.Lock()
            domain_lock = self._domain_locks[domain]
        
        # Acquire domain lock, calculate sleep time
        with domain_lock:
            last_time = self._domain_last_request.get(domain, 0)
            elapsed = time.monotonic() - last_time
            sleep_time = max(0, self._default_interval - elapsed)
            self._domain_last_request[domain] = time.monotonic() + sleep_time
        
        # Sleep OUTSIDE the lock (allows other domains to proceed)
        if sleep_time > 0:
            time.sleep(sleep_time)
```

**Why This Matters**:
- **Before**: Global lock → all requests serialized → 128.76s
- **After**: Per-domain locks → parallel requests to different domains → 34.47s
- **Benefit**: Respects server rate limits while maximizing parallelism

**Example**:
```
Time →  0s    1s    2s    3s    4s
        │     │     │     │     │
nike.com│─────│─────│─────│─────│  (1s interval)
        │     │     │     │     │
adidas  │─────│─────│─────│─────│  (parallel!)
        │     │     │     │     │
reebok  │─────│─────│─────│─────│  (parallel!)
```

---

### 5. Playwright Manager (`ingestion/playwright_manager.py`)

**Purpose**: Thread-safe persistent browser for JavaScript rendering

**Key Features**:
- **Singleton pattern** for browser reuse
- **Dedicated browser thread** for thread safety
- **Request queue** for concurrent fetch requests
- **Auto-restart** on crashes
- **GPU disabled** (fixes macOS crashes)

**Architecture**:
```
Main Thread                    Browser Thread
    │                               │
    ├─► fetch_page(url) ────────►  │
    │   (submit request)            ├─► Launch browser (once)
    │                               ├─► Process fetch queue
    │                               ├─► Navigate to URL
    │   ◄──────── result ──────────┤   Extract content
    │                               └─► Return result
```

**Benefits**:
- **Faster**: Browser stays open between requests
- **Stable**: Dedicated thread avoids event loop conflicts
- **Safe**: Thread-safe queue-based communication

**Configuration**:
```bash
AR_USE_PLAYWRIGHT=true  # Enable Playwright globally
```

---

### 6. Domain Classifier (`ingestion/domain_classifier.py`)

**Purpose**: Classify URLs as brand-owned or third-party

**Classification Types**:

**Brand-Owned Tiers**:
- `PRIMARY_WEBSITE`: Main brand domain (e.g., nike.com)
- `CONTENT_HUB`: Blog, newsroom subdomains
- `DIRECT_TO_CONSUMER`: E-commerce, store locators
- `BRAND_SOCIAL`: Official social media accounts

**Third-Party Tiers**:
- `NEWS_MEDIA`: NYTimes, WSJ, BBC, etc.
- `USER_GENERATED`: Reddit, Twitter, forums
- `EXPERT_PROFESSIONAL`: Gartner, Forrester, Medium
- `MARKETPLACE`: Amazon, eBay, Walmart

**Ratio Enforcement**:
```python
config = URLCollectionConfig(
    brand_owned_ratio=0.6,      # 60% brand-owned
    third_party_ratio=0.4,      # 40% third-party
    brand_domains=['nike.com', 'nike.co.uk'],
    brand_subdomains=['blog', 'news', 'about'],
    brand_social_handles=['nike', 'nikefootball']
)
```

**Smart Matching**:
- Handles international domains (`.co.uk`, `.com.au`)
- Subdomain matching (blog.nike.com)
- Social handle matching (twitter.com/nike)
- Path-based classification (e.g., `/blog/` → content hub)

---

## Search Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Search Orchestration (search_orchestration.py)          │
│    - Initialize progress tracking                           │
│    - Configure search parameters                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Social Media Discovery (social_search.py)               │
│    - Find official brand channels                           │
│    - Classify social platforms                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Web Search (serper_search.py / brave_search.py)         │
│    ┌───────────────────────────────────────────────┐       │
│    │ Producer Thread                               │       │
│    │  - Fetch search results (paginated)           │       │
│    │  - Push URLs to queue                         │       │
│    │  - Dynamic batch sizing                       │       │
│    └───────────────┬───────────────────────────────┘       │
│                    │                                        │
│                    ▼                                        │
│    ┌───────────────────────────────────────────────┐       │
│    │ Worker Threads (5 concurrent)                 │       │
│    │  - Fetch page content (page_fetcher.py)       │       │
│    │  - Classify URL (domain_classifier.py)        │       │
│    │  - Validate content length                    │       │
│    │  - Check domain diversity                     │       │
│    │  - Enforce brand/3rd-party ratio              │       │
│    └───────────────────────────────────────────────┘       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Page Fetching (page_fetcher.py)                         │
│    ┌───────────────────────────────────────────────┐       │
│    │ HTTP Fetch (requests + lxml)                  │       │
│    │  - Per-domain rate limiting                   │       │
│    │  - Session pooling                            │       │
│    │  - Robots.txt compliance                      │       │
│    │  - Multi-strategy content extraction          │       │
│    └───────────────┬───────────────────────────────┘       │
│                    │                                        │
│                    ▼                                        │
│    ┌───────────────────────────────────────────────┐       │
│    │ Playwright Fallback (if needed)               │       │
│    │  - JavaScript rendering                       │       │
│    │  - Persistent browser reuse                   │       │
│    │  - Domain learning (mark for future)          │       │
│    └───────────────────────────────────────────────┘       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. URL Classification & Filtering                          │
│    - Classify as brand-owned or third-party                 │
│    - Filter login pages                                     │
│    - Check domain diversity limits                          │
│    - Enforce ratio targets                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Results Sorting & Return                                │
│    - Core domains first (nike.com)                          │
│    - Other brand-owned URLs                                 │
│    - Third-party URLs                                       │
│    - Alphabetical within each tier                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Performance Characteristics

### Current Performance (2025-11-28)

**Typical Search** (10 pages, pool size 50):
- **Duration**: ~34.47 seconds
- **Improvement**: 73% faster than previous version (128.76s)
- **Throughput**: ~1.45 pages/second

**Performance Breakdown**:
```
Activity                          Time        % of Total
─────────────────────────────────────────────────────────
Search API requests               ~5s         14%
Page fetching (parallel)          ~25s        73%
Classification & filtering        ~3s         9%
Progress updates & logging        ~1.5s       4%
─────────────────────────────────────────────────────────
Total                             ~34.47s     100%
```

### Optimization History

| Date       | Version | Duration | Improvement | Change |
|------------|---------|----------|-------------|--------|
| 2025-11-27 | v1.0    | 128.76s  | Baseline    | Global rate limiting |
| 2025-11-28 | v2.0    | 34.47s   | **73% faster** | **Per-domain rate limiting** |

**Key Optimization**: Per-domain rate limiting
- **Problem**: Global lock serialized all requests
- **Solution**: Per-domain locks allow parallel requests to different domains
- **Impact**: 94.29s reduction (128.76s → 34.47s)

### Scalability

**Concurrent Workers**: 5 (configurable)
- Balances parallelism with system resources
- Prevents overwhelming target servers
- Respects per-domain rate limits

**Domain Diversity**:
- **Brand-controlled search**: No domain limits (collect multiple pages from brand domains)
- **Mixed/third-party search**: Max 20% of target per domain (enforces diversity)

**Pool Size Multiplier**: 5x target count
- Accounts for access-denied pages
- Handles thin content filtering
- Ensures ratio targets are met

---

## Configuration

### Environment Variables

```bash
# Search Provider Selection
SEARCH_PROVIDER=serper  # or 'brave'

# Serper Configuration
SERPER_API_KEY=<your-key>
SERPER_REQUEST_INTERVAL=1.0      # Per-domain rate limit (seconds)
SERPER_MAX_PER_REQUEST=100       # Max results per API call
SERPER_API_TIMEOUT=30            # Request timeout (seconds)

# Brave Configuration
BRAVE_API_KEY=<your-key>
BRAVE_REQUEST_INTERVAL=2.0       # Per-domain rate limit (seconds)
BRAVE_API_MAX_COUNT=20           # Max results per request
BRAVE_API_TIMEOUT=30             # Request timeout (seconds)

# Page Fetching
AR_PARALLEL_FETCH_WORKERS=5      # Concurrent fetch workers
AR_USE_PLAYWRIGHT=true           # Enable Playwright fallback
AR_FETCH_DEBUG_DIR=/tmp/ar_fetch_debug  # Debug output directory

# Content Filtering
MIN_BODY_LENGTH=200              # Minimum content length (chars)
MIN_BRAND_BODY_LENGTH=75         # Minimum for brand pages (chars)
```

### Search Strategies

**1. Brand-Controlled** (60%+ brand-owned):
```python
collection_strategy='brand_controlled'
brand_owned_ratio=100  # 100% brand-owned
```
- Discovers brand domains via LLM
- Site-restricted search queries
- No domain diversity limits
- Ideal for brand content audits

**2. Mixed** (60/40 split):
```python
collection_strategy='both'
brand_owned_ratio=60  # 60% brand, 40% third-party
```
- Balanced brand and third-party content
- Domain diversity enforcement
- Ideal for holistic trust assessment

**3. Third-Party** (100% third-party):
```python
collection_strategy='third_party'
brand_owned_ratio=0  # 0% brand, 100% third-party
```
- Only third-party sources
- Maximum domain diversity
- Ideal for reputation monitoring

---

## Error Handling

### Retry Logic

**HTTP Fetching**:
- **Max retries**: 3 (configurable per domain)
- **Backoff**: Exponential (1s, 2s, 4s)
- **Timeout**: 10s (configurable per domain)

**Playwright Fallback**:
- Triggered on HTTP failure or thin content
- Marks successful domains for future use
- Falls back to empty result on failure

### Common Issues

**1. API Rate Limits**:
- **Symptom**: 429 errors from search provider
- **Solution**: Increase `SERPER_REQUEST_INTERVAL` or reduce pool size

**2. Thin Content**:
- **Symptom**: Many pages filtered out
- **Solution**: Lower `MIN_BODY_LENGTH` or enable Playwright

**3. Access Denied**:
- **Symptom**: 403/401 errors, "Access Denied" titles
- **Solution**: Increase pool size multiplier (5x → 10x)

**4. Slow Performance**:
- **Symptom**: Search takes > 60s
- **Solution**: Check rate limiter config, verify per-domain locks are working

---

## Testing

### Performance Test

```bash
python tests/test_search_performance.py
```

**Expected Results**:
- ✅ Duration < 60s (target: ~35s)
- ✅ Collected 10 pages
- ✅ 73% faster than baseline (128.76s)

### Unit Tests

```bash
pytest tests/test_serper_search.py
pytest tests/test_brave_search.py
pytest tests/test_concurrent_search.py
```

---

## Future Improvements

### Potential Optimizations

1. **Adaptive Worker Pool**:
   - Scale workers based on domain diversity
   - More workers for diverse domains, fewer for concentrated domains

2. **Intelligent Caching**:
   - Cache search results by query
   - Cache page content by URL (with TTL)
   - Reduce redundant API calls

3. **Smarter Playwright Usage**:
   - Pre-classify domains that need JavaScript
   - Batch Playwright requests for efficiency
   - Share browser contexts across requests

4. **Advanced Rate Limiting**:
   - Respect server-specific rate limits (from headers)
   - Adaptive intervals based on response times
   - Priority queuing for critical domains

5. **Content Quality Scoring**:
   - Pre-filter low-quality pages before full fetch
   - Use meta descriptions for quick relevance checks
   - Machine learning for content quality prediction

---

## Monitoring & Debugging

### Performance Metrics

**Logged Metrics**:
- Search duration (total)
- Pages collected vs target
- Success rate (valid pages / total fetched)
- Domain diversity stats
- Ratio enforcement stats

**Example Log Output**:
```
2025-11-28 14:24:56 - webapp.services.search_orchestration - INFO - Search completed in 34.47 seconds
2025-11-28 14:24:56 - ingestion.serper_search - INFO - [SERPER] Collection complete. Collected: 10. Stats: {'total_processed': 42, 'total_fetched': 42, 'total_valid': 10, 'thin_content': 18, 'error_page': 5, 'domain_limit_reached': 9}
```

### Debug Mode

**Enable Debug Logging**:
```python
import logging
logging.getLogger('ingestion').setLevel(logging.DEBUG)
```

**Debug Output Directory**:
```bash
export AR_FETCH_DEBUG_DIR=/tmp/ar_fetch_debug
# Saves raw HTML for failed/thin-content pages
```

---

## Summary

The Authenticity Ratio search system is a **high-performance, production-ready** web search and content collection pipeline that:

✅ **Achieves 34.47s search times** (73% faster than baseline)  
✅ **Scales with per-domain rate limiting** (respects servers, maximizes parallelism)  
✅ **Handles JavaScript-heavy pages** (Playwright fallback with persistent browser)  
✅ **Enforces brand/third-party ratios** (60/40 methodology)  
✅ **Provides real-time progress updates** (Streamlit integration)  
✅ **Recovers from errors gracefully** (retry logic, fallbacks, logging)

**Key Innovation**: Per-domain rate limiting with thread-safe locks enables parallel requests to different domains while respecting individual server rate limits—the critical optimization that reduced search times by 73%.
