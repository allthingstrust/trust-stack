"""
Trust Stack Rating Web Application
A comprehensive interface for brand content Trust Stack Rating analysis
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import glob as file_glob
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from config.settings import APIConfig, SETTINGS
from scoring.llm_client import ChatClient
from scoring.scorer import ContentScorer
from ingestion.fetch_config import get_realistic_headers, get_random_delay
from ingestion.playwright_manager import get_browser_manager
from utils.score_formatter import to_display_score, format_score_display, get_score_status

# Import utility modules
from webapp.utils.url_utils import (
    ENGLISH_DOMAIN_SUFFIXES, ENGLISH_COUNTRY_SUFFIXES, USA_DOMAIN_SUFFIXES,
    PROMOTIONAL_SUBPATHS, normalize_brand_slug, extract_hostname,
    is_english_host, is_usa_host, find_main_american_url, has_country_variants,
    add_primary_subpages, is_promotional_url, ensure_promotional_quota,
    classify_brand_url, normalize_international_url, _fallback_title,
    is_core_domain, is_login_page
)
from webapp.utils.url_verification import fetch_page_title, verify_url
from webapp.utils.logging_utils import StreamlitLogHandler, ProgressAnimator
from webapp.utils.recommendations import (
    extract_issues_from_items,
    extract_successes_from_items,
    get_remedy_for_issue,
    generate_rating_recommendation
)

# Import service modules
from webapp.services.social_search import search_social_media_channels
from webapp.services.search_orchestration import perform_initial_search, fetch_and_process_selected_urls
from core.run_manager import RunManager
from data import store

# Import page modules
# Import page modules
from webapp.pages.brand_guidelines import show_brand_guidelines_page

# Import report generator
from reporting.trust_stack_report import generate_trust_stack_report

# Configure logging for the webapp
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Trust Stack Dimension Colors (based on AllThingsTrust visual model)
DIMENSION_COLORS = {
    'verification': '#D4A574',      # Golden/mustard yellow (outer ring, top)
    'coherence': '#4A7C7E',          # Teal/dark cyan (middle ring)
    'provenance': '#C5D5C0',         # Light sage green (center)
    'resonance': '#D17B58',          # Burnt orange/terracotta (middle ring, bottom)
    'transparency': '#E8E4DC'        # Light beige/cream (outer ring, bottom)
}

# Helper Functions
def infer_brand_domains(brand_id: str) -> Dict[str, List[str]]:
    """
    Automatically infer likely brand domains from brand_id.

    Args:
        brand_id: Brand identifier (e.g., 'nike', 'coca-cola')

    Returns:
        Dict with 'domains', 'subdomains', and 'social_handles' keys
    """
    if not brand_id:
        return {'domains': [], 'subdomains': [], 'social_handles': []}

    brand_id_clean = brand_id.lower().strip()

    # Handle common brand name variations (for domains, never use spaces)
    brand_variations = []

    # If there are spaces, create hyphenated and combined versions
    if ' ' in brand_id_clean:
        brand_variations.append(brand_id_clean.replace(' ', '-'))  # red-bull
        brand_variations.append(brand_id_clean.replace(' ', ''))   # redbull
    elif '-' in brand_id_clean:
        # If there are hyphens, also try without
        brand_variations.append(brand_id_clean)                    # coca-cola
        brand_variations.append(brand_id_clean.replace('-', ''))   # cocacola
    else:
        # Simple brand name without spaces or hyphens
        brand_variations.append(brand_id_clean)                    # nike

    # Generate common domain patterns
    domains = []
    for variant in brand_variations:
        domains.extend([
            f"{variant}.com",
            f"www.{variant}.com",
        ])

    # Generate common subdomains
    subdomains = []
    for variant in brand_variations:
        subdomains.extend([
            f"blog.{variant}.com",
            f"www.{variant}.com",
            f"shop.{variant}.com",
            f"store.{variant}.com",
        ])

    # Generate social handle variations (include original for handles like "@red bull")
    social_handles = []
    # Add handles based on domain variants
    for variant in brand_variations:
        social_handles.extend([
            f"@{variant}",
            variant,
        ])
    # Also add original brand_id if different (for handles with spaces)
    if brand_id_clean not in brand_variations:
        social_handles.extend([
            f"@{brand_id_clean}",
            brand_id_clean,
        ])

    # Remove duplicates while preserving order
    domains = list(dict.fromkeys(domains))
    subdomains = list(dict.fromkeys(subdomains))
    social_handles = list(dict.fromkeys(social_handles))

    return {
        'domains': domains,
        'subdomains': subdomains,
        'social_handles': social_handles
    }


def _embed_local_images_as_base64(markdown_text: str) -> str:
    """
    Finds local image paths in markdown (e.g. ![alt](/path/to/image.png))
    and replaces them with base64 encoded data URIs.
    Resizes images to max 800px width and compresses as JPEG to reduce page weight.
    """
    import base64
    from PIL import Image
    import io

    # Regex for markdown images: ![alt](path "title") or ![alt](path)
    pattern = r'!\[(.*?)\]\((.*?)\)'
    
    def replace_match(match):
        alt_text = match.group(1)
        path = match.group(2)
        
        # Clean path (handle optional title)
        title = ""
        if ' "' in path:
            parts = path.split(' "')
            path = parts[0]
            title = ' "' + parts[1]
        elif " '" in path:
            parts = path.split(" '")
            path = parts[0]
            title = " '" + parts[1]
            
        # Check if local file
        # Assume all paths are local if they don't start with http/data
        if not path.startswith(('http://', 'https://', 'data:')):
            # Handle file:// prefix
            local_path = path.replace('file://', '')
            
            if os.path.exists(local_path):
                try:
                    # Optimize: Resize and Compress
                    with Image.open(local_path) as img:
                        # Convert to RGB if RGBA (jpeg doesn't support transparency)
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')
                            
                        # Resize if too large (max width 800px)
                        max_width = 800
                        if img.width > max_width:
                            ratio = max_width / img.width
                            new_height = int(img.height * ratio)
                            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                        
                        # Save to buffer as JPEG with compression
                        buffer = io.BytesIO()
                        img.save(buffer, format="JPEG", quality=80, optimize=True)
                        encoded_string = base64.b64encode(buffer.getvalue()).decode()
                        
                        return f'![{alt_text}](data:image/jpeg;base64,{encoded_string}{title})'
                        
                except Exception as e:
                    logger.warning(f"Error encoding/optimizing image {local_path}: {e}")
                    # Fallback to original match if encoding fails
                    return match.group(0)
            else:
                 # File not found
                 pass
        
        return match.group(0)

    try:
        return re.sub(pattern, replace_match, markdown_text)
    except Exception as e:
        logger.error(f"Error in regex substitution for images: {e}")
        return markdown_text








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





def search_urls_fallback(brand_id: str, keywords: List[str], target_count: int = 20) -> List[Dict[str, Any]]:
    """Run a quick web search fallback to collect candidate URLs, classify and verify them.

    This uses the unified search interface (ingestion.search_unified.search) and returns
    entries in the same shape as suggest_brand_urls_from_llm produces so the UI can consume them.
    """
    try:
        from ingestion.search_unified import search, validate_provider_config
    except Exception as e:
        logger.info('Search fallback not available: %s', e)
        return []

    # Validate provider readiness
    cfg = validate_provider_config()
    if not cfg.get('ready'):
        logger.info('Search provider not configured or available for fallback: %s', cfg.get('message'))
        return []

    query = ' '.join(keywords) if keywords else brand_id
    try:
        results = search(query, size=target_count)
    except Exception as e:
        logger.warning('Search fallback failed: %s', e)
        return []

    # Collect candidate URLs and classify
    candidates = []
    for r in results:
        url = r.get('url')
        if not url:
            continue
        is_primary = classify_brand_url(url, brand_id, None) == 'primary'
        candidates.append({'url': url, 'is_primary': is_primary, 'title': r.get('title', ''), 'snippet': r.get('snippet', '')})

    # Verify candidates in parallel
    verified: List[Dict[str, Any]] = []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    max_workers = min(20, max(4, len(candidates)))
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        future_to_c = {exe.submit(verify_url, c['url'], brand_id): c for c in candidates}
        for fut in as_completed(future_to_c):
            c = future_to_c[fut]
            try:
                res = fut.result()
            except Exception as e:
                logger.debug('Search fallback verification raised for %s: %s', c['url'], e)
                continue
            if res and res.get('ok'):
                title = fetch_page_title(res.get('final_url') or c['url'], brand_id)
                verified.append({
                    'url': res.get('final_url') or c['url'],
                    'is_primary': c.get('is_primary', False),
                    'verified': True,
                    'status': res.get('status'),
                    'soft_verified': res.get('soft_verified', False),
                    'verification_method': res.get('method'),
                    'title': title,
                    'evidence': None,
                    'confidence': 0,
                    'is_promotional': is_promotional_url(c['url'])
                })
            if len(verified) >= target_count:
                break

    return verified


# Page configuration
st.set_page_config(
    page_title="Trust Stack Rating Tool",
    page_icon="⭐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f0f2f6;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .info-box {
        background: #e7f3ff;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #2196F3;
        margin: 1rem 0;
        color: #1565c0;
    }
    .success-box {
        background: #e8f5e9;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #4caf50;
        margin: 1rem 0;
        color: #2e7d32;
    }
    .warning-box {
        background: #fff3e0;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #ff9800;
        margin: 1rem 0;
        color: #e65100;
    }

    /* Animated progress indicator styles */
    .progress-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 0.75rem;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        min-height: 80px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        width: 100%;
        max-width: 100%;
        overflow: hidden;
        box-sizing: border-box;
    }

    .progress-item {
        color: white;
        font-size: 1.1rem;
        font-weight: 500;
        text-align: center;
        line-height: 1.5;
        animation: fadeIn 0.3s ease-out;
    }

    .progress-item-pulsing {
        animation: waitingPulse 1s ease-in-out infinite;
    }

    @keyframes fadeIn {
        0% {
            opacity: 0;
            transform: translateY(10px);
        }
        100% {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes waitingPulse {
        0% {
            opacity: 0.8;
        }
        100% {
            opacity: 1;
        }
    }

    .progress-emoji {
        font-size: 1.5rem;
        margin-right: 0.5rem;
        display: inline-block;
        animation: emojiPulse 2s ease-in-out infinite;
    }

    @keyframes emojiPulse {
        0%, 100% {
            transform: scale(1);
        }
        50% {
            transform: scale(1.1);
        }
    }

    .progress-urls {
        margin-top: 0.75rem;
        font-size: 0.75rem;
        color: white;
        opacity: 0.4;
        text-align: center;
        max-width: 90%;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-family: monospace;
        animation: fadeIn 0.3s ease-out;
    }

    .progress-logs {
        margin-top: 0.75rem;
        margin-left: auto;
        margin-right: auto;
        font-size: 0.5rem !important;
        color: white !important;
        z-index: 10;
        opacity: 0.64 !important;
        text-align: center !important;
        width: 80%;
        max-width: 80%;
        overflow: hidden;
        font-family: monospace !important;
        line-height: 1.3 !important;
        animation: fadeIn 0.3s ease-out;
        box-sizing: border-box;
    }

    .progress-log-entry {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        word-break: normal !important;
        overflow-wrap: anywhere !important;
        max-width: 100%;
        overflow: hidden;
        font-size: 0.5rem !important;
        color: white !important;
        background: transparent !important;
        padding: 0 !important;
        border: none !important;
    }

    /* Override Streamlit's code block styling */
    .progress-logs code,
    .progress-log-entry code {
        font-size: 0.5rem !important;
        color: white !important;
        background: transparent !important;
        padding: 0 !important;
        border: none !important;
        font-family: monospace !important;
    }

    /* Trust Stack Report Styling */
    .trust-stack-header {
        font-weight: bold;
        font-size: 1rem; /* Match body text size */
    }
    .trust-stack-italic {
        font-style: italic;
    }

    /* Override all Streamlit wrapper classes within progress logs */
    .progress-logs *,
    .progress-log-entry * {
        font-size: 0.5rem !important;
        color: white !important;
        background: transparent !important;
        font-family: monospace !important;
    }

    /* Target specific Streamlit emotion cache classes */
    .progress-logs [class*="st-emotion-cache"],
    .progress-log-entry [class*="st-emotion-cache"] {
        font-size: 0.5rem !important;
        color: white !important;
        background: transparent !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
        font-family: monospace !important;
    }

    /* Override Streamlit markdown container */
    .progress-logs .stMarkdown,
    .progress-log-entry .stMarkdown {
        font-size: 0.5rem !important;
        color: white !important;
        background: transparent !important;
    }

    /* Override any p, span, div within logs */
    .progress-logs p,
    .progress-logs span,
    .progress-logs div,
    .progress-log-entry p,
    .progress-log-entry span,
    .progress-log-entry div {
        font-size: 0.5rem !important;
        color: white !important;
        background: transparent !important;
        font-family: monospace !important;
    }
</style>
""", unsafe_allow_html=True)


def show_home_page():
    """Display the home/overview page"""
    st.markdown('<div class="main-header">⭐ Trust Stack Rating</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Measure and monitor brand content quality across digital channels</div>', unsafe_allow_html=True)

    st.divider()

    # What is Trust Stack Rating section
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### 📊 What is the Trust Stack Rating?")
        st.markdown("""
        The **Trust Stack Rating** is a comprehensive scoring system that evaluates brand-linked content
        across six trust dimensions. Each piece of content receives a **0-100 rating** based on
        signals detected in metadata, structure, and provenance.

        #### Rating Scale (0-100)
        - **80-100** (🟢 Excellent): High-quality, verified content
        - **60-79** (🟡 Good): Solid content with minor improvements needed
        - **40-59** (🟠 Fair): Moderate quality requiring attention
        - **0-39** (🔴 Poor): Low-quality content needing immediate review

        #### Comprehensive Rating
        ```
        Rating = Weighted average across 6 dimensions
        ```
        Each dimension contributes based on configurable weights, with detected attributes
        providing bonuses or penalties.
        """)

    with col2:
        st.markdown("### 🎯 Quick Start")
        st.markdown("""
        1. **Configure** your brand and sources
        2. **Run** the analysis pipeline
        3. **Review** Trust Stack Ratings
        4. **Export** reports for stakeholders
        """)

        if st.button("🚀 Start New Analysis", type="primary", width='stretch'):
            st.session_state['page'] = 'analyze'
            st.rerun()

    st.divider()

    # 5D Trust Dimensions
    st.markdown("### 🔍 5D Trust Dimensions")
    st.markdown("Each piece of content is scored 0-100 on five dimensions:")

    dimensions_cols = st.columns(3)

    dimensions = [
        ("Provenance", "🔗", "Origin, traceability, metadata integrity"),
        ("Verification", "✓", "Factual accuracy vs. trusted databases"),
        ("Transparency", "👁", "Disclosures, clarity, attribution"),
        ("Coherence", "🔄", "Consistency across channels and time"),
        ("Resonance", "📢", "Cultural fit, organic engagement")
    ]

    for idx, (name, icon, desc) in enumerate(dimensions):
        with dimensions_cols[idx % 3]:
            st.markdown(f"**{icon} {name}**")
            st.caption(desc)

    st.divider()

    # Pipeline overview
    st.markdown("### ⚙️ Analysis Pipeline")

    pipeline_steps = [
        ("1. Ingest", "Collect raw content and data from multiple sources\n\n_→ Purpose: Gather inputs._"),
        ("2. Normalize", "Standardize data structure, remove noise, and extract core metadata (source, title, author, date).\n\n_→ Purpose: Prepare clean, consistent inputs._"),
        ("3. Enrich", "Add contextual intelligence — provenance tags, schema markup, fact-check references, and entity recognition.\n\n_→ Purpose: Add meaning and traceability._"),
        ("4. Analyze", "Evaluate enriched content for trust-related patterns and attributes across the five dimensions (Provenance, Resonance, Coherence, Transparency, Verification).\n\n_→ Purpose: Interpret trust signals in context._"),
        ("5. Score", "Apply the 5D rubric to quantify each content item on a 0–100 scale per dimension.\n\n_→ Purpose: Turn analysis into measurable data._"),
        ("6. Synthesize", "Aggregate and weight results into an overall Trust Index or benchmark, highlighting gaps and strengths.\n\n_→ Purpose: Combine scores into a holistic rating._"),
        ("7. Report", "Generate visual outputs (PDF, dashboard, Markdown) with trust maps, insights, and recommended actions.\n\n_→ Purpose: Communicate results and next steps._")
    ]

    # Split pipeline steps into two rows for better layout and stability
    row1_steps = pipeline_steps[:4]
    row2_steps = pipeline_steps[4:]

    cols1 = st.columns(4)
    for idx, (step, desc) in enumerate(row1_steps):
        with cols1[idx]:
            st.markdown(f"**{step}**")
            st.caption(desc)
            
    st.write("") # Spacing
    
    cols2 = st.columns(3)
    for idx, (step, desc) in enumerate(row2_steps):
        with cols2[idx]:
            st.markdown(f"**{step}**")
            st.caption(desc)


def show_analyze_page():
    """Display the analysis configuration and execution page"""
    st.markdown('<div class="main-header">🚀 Run Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Configure and execute Trust Stack Rating analysis</div>', unsafe_allow_html=True)

    st.divider()

    # Configuration form
    with st.container(): # Form removed to allow interactive Brand ID inputs (e.g. Enter key)
        col1, col2 = st.columns(2)

        with col1:
            brand_id = st.text_input(
                "Brand ID*",
                value="",
                placeholder="e.g., nike or mastercard",
                help="Unique identifier for the brand (e.g., 'nike', 'coca-cola'). Press enter to add guidelines."
            )
            
            # Brand Guidelines Check (inline)
            if brand_id:
                from utils.document_processor import BrandGuidelinesProcessor
                import tempfile
                
                processor = BrandGuidelinesProcessor()
                brand_id_normalized = brand_id.lower().strip().replace(' ', '_')
                guidelines = processor.load_guidelines(brand_id_normalized)
                metadata = processor.load_metadata(brand_id_normalized)
                
                # Check if we should ignore these guidelines for this session
                ignore_key = f"ignore_guidelines_{brand_id_normalized}"
                
                if guidelines:
                    # Guidelines found - show toggle
                    word_count = metadata.get('word_count', 0) if metadata else 0
                    
                    use_guidelines = st.toggle(
                        "Use brand guidelines for coherence analysis",
                        value=True,
                        key=f"use_guidelines_{brand_id_normalized}",
                        help="Toggle off to exclude these guidelines from this analysis"
                    )
                    
                    # Apply opacity styling based on toggle state
                    opacity_style = "" if use_guidelines else "opacity: 0.5;"
                    
                    st.markdown(f'<div style="{opacity_style}">', unsafe_allow_html=True)
                    st.success(f"✅ Guidelines found ({word_count:,} words)")
                    
                    # Preview option
                    with st.expander("📋 View guidelines preview", expanded=False):
                        st.text_area("", guidelines, height=400, disabled=True, label_visibility="collapsed")
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Store in session state
                    st.session_state['use_guidelines'] = use_guidelines
                    st.session_state['brand_id_for_guidelines'] = brand_id_normalized
                else:
                    # No guidelines - show upload option
                    st.warning("⚠️ No brand guidelines found")
                    st.caption("Upload guidelines for brand-specific coherence analysis")
                    
                    with st.expander("📤 Upload Guidelines", expanded=False):
                        uploaded_file = st.file_uploader(
                            "Choose file (PDF, DOCX, or TXT)",
                            type=['pdf', 'docx', 'txt'],
                            key=f"inline_guidelines_upload_{brand_id_normalized}",
                            help="Upload your brand voice and style guidelines"
                        )
                        
                        if uploaded_file:
                            if st.button("Upload", key=f"inline_upload_btn_{brand_id_normalized}"):
                                with st.spinner("Processing document..."):
                                    try:
                                        # Save to temp file
                                        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                                            tmp_file.write(uploaded_file.getvalue())
                                            tmp_path = tmp_file.name
                                        
                                        # Extract text
                                        text = processor.extract_text(tmp_path)
                                        
                                        # Clean up temp file
                                        os.unlink(tmp_path)
                                        
                                        # Save guidelines
                                        metadata = processor.save_guidelines(
                                            brand_id=brand_id_normalized,
                                            text=text,
                                            original_filename=uploaded_file.name,
                                            file_size=uploaded_file.size
                                        )
                                        
                                        st.success(f"✅ Guidelines uploaded! ({metadata['word_count']:,} words)")
                                        
                                        # Clear ignore flag if it exists so they show up immediately
                                        if f"ignore_guidelines_{brand_id_normalized}" in st.session_state:
                                            del st.session_state[f"ignore_guidelines_{brand_id_normalized}"]
                                            
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Error processing document: {str(e)}")
                    
                    # No guidelines available
                    st.session_state['use_guidelines'] = False
                    st.session_state['brand_id_for_guidelines'] = brand_id_normalized

            keywords = st.text_input(
                "Search Keywords*",
                value="",
                placeholder="Space-separated keywords (e.g., 'brand sustainability')",
                help="Space-separated keywords to search for (e.g., 'nike swoosh'). Required to build the search query."
            )

            # Headless Mode Toggle
            current_headless = SETTINGS.get('headless_mode', True)
            new_headless = st.toggle(
                "Run in Headless Mode (Background)",
                value=current_headless,
                help="If enabled, the browser runs in the background. Disable to see the browser window for debugging.",
            )
            
            # If toggle changed, update settings and restart browser
            if new_headless != current_headless:
                SETTINGS['headless_mode'] = new_headless
                # Restart browser to apply change
                manager = get_browser_manager()
                if manager.is_started:
                    st.toast(f"Restarting browser in {'headless' if new_headless else 'headed'} mode...", icon="🔄")
                    manager.close()
                    # It will auto-restart on next fetch


            max_items = st.number_input(
                "Max Items to Analyze",
                min_value=5,
                max_value=100,
                value=20,
                step=5,
                help="Maximum number of content items to analyze"
            )

        with col2:
            st.markdown("**Data Sources**")

            cfg = APIConfig()

            # Search Provider Selection
            st.markdown("**Web Search Provider**")

            # Check which providers are available
            brave_available = bool(cfg.brave_api_key)
            serper_available = bool(cfg.serper_api_key)

            # Determine default provider
            default_provider = 'serper' if serper_available else 'brave'

            # Create provider options
            provider_options = []
            provider_labels = []

            if brave_available:
                provider_options.append('brave')
                provider_labels.append('🌐 Brave')

            if serper_available:
                provider_options.append('serper')
                provider_labels.append('🔍 Serper')

            if not provider_options:
                st.error("⚠️ No search provider API keys configured. Please set BRAVE_API_KEY or SERPER_API_KEY.")
                search_provider = None
            elif len(provider_options) == 1:
                # Only one provider available, show as info
                search_provider = provider_options[0]
                st.info(f"Using {provider_labels[0]} (only available provider)")
            else:
                # Multiple providers available, let user choose
                default_index = provider_options.index(default_provider) if default_provider in provider_options else 0
                search_provider = st.radio(
                    "Select search provider:",
                    options=provider_options,
                    format_func=lambda x: '🌐 Brave' if x == 'brave' else '🔍 Serper',
                    index=default_index,
                    horizontal=True,
                    help="Choose between Brave Search or Serper (Google) for web search"
                )

            # Web search settings
            use_web_search = st.checkbox(
                "🌐 Enable Web Search",
                value=True,
                disabled=False,
                help="Enable web search to find and collect URLs for analysis."
            )
            # Use max_items for web pages to fetch (removed separate input to avoid confusion)
            web_pages = max_items if use_web_search else max_items

            # Visual Analysis
            visual_analysis_available = bool(cfg.google_api_key)
            use_visual_analysis = st.checkbox(
                "📸 Enable Visual Analysis",
                value=visual_analysis_available,
                disabled=not visual_analysis_available,
                help="Requires Gemini API Key. Captures screenshots and scores design/branding capability."
            )

            # Reddit
            reddit_available = bool(cfg.reddit_client_id and cfg.reddit_client_secret)
            use_reddit = st.checkbox(
                "🔴 Reddit",
                value=False,
                disabled=not reddit_available,
                help="Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET" if not reddit_available else "Search Reddit posts and comments"
            )

            # YouTube
            youtube_available = bool(cfg.youtube_api_key)
            use_youtube = st.checkbox(
                "📹 YouTube",
                value=False,
                disabled=not youtube_available,
                help="Requires YOUTUBE_API_KEY" if not youtube_available else "Search YouTube videos and comments"
            )
            include_comments = st.checkbox("Include YouTube comments", value=False) if use_youtube else False

            st.divider()

            # Manual Social Media Uploads (Modal with Paste Support)
            if 'uploaded_social_files' not in st.session_state:
                st.session_state['uploaded_social_files'] = {}
            
            # Button to open the upload modal
            if st.button("📸 Upload Social Media Screenshots", help="Upload or paste screenshots for LinkedIn, Instagram, X"):
                upload_social_modal()

            # Display count of uploaded files
            if st.session_state.get('uploaded_social_files'):
                st.success(f"✅ {len(st.session_state['uploaded_social_files'])} screenshots ready for analysis")
                # Show list of uploaded files with clear button
                with st.expander("View Uploaded Screenshots"):
                    for platform, file_data in st.session_state['uploaded_social_files'].items():
                        st.text(f"{platform.title()}: {file_data['name']}")
                    
                    if st.button("Clear All Screenshots"):
                        st.session_state['uploaded_social_files'] = {}
                        st.rerun()

        st.divider()

        # URL Collection Strategy - Simplified Interface
        with st.expander("⚙️ URL Collection Strategy", expanded=False):
            st.markdown("**Choose which URLs to collect:**")

            # Initialize session state for collection strategy if not exists
            if 'collection_strategy' not in st.session_state:
                st.session_state['collection_strategy'] = 'brand_controlled'

            collection_strategy = st.radio(
                "Collection Type",
                options=["brand_controlled", "third_party", "both"],
                format_func=lambda x: {
                    "brand_controlled": "🏢 Brand-Controlled Only",
                    "third_party": "🌐 3rd Party Only",
                    "both": "⚖️ Both (Balanced Collection)"
                }[x],
                index=["brand_controlled", "third_party", "both"].index(st.session_state['collection_strategy']),
                help="Select which type of URLs to collect for analysis",
                key='collection_strategy_radio'
            )

            # Update session state
            st.session_state['collection_strategy'] = collection_strategy

            # Show different help text based on selection
            if collection_strategy == "brand_controlled":
                st.info("📝 **Collecting only from brand-owned domains** (website, blog, social media). Domains auto-detected from brand ID.")
            elif collection_strategy == "third_party":
                st.info("📝 **Collecting only from external sources** (news, reviews, forums, social media).")
            else:  # both
                st.info("📝 **Collecting from both brand-owned and 3rd party sources** for holistic assessment (recommended 60/40 ratio).")

            # Only show ratio slider when "Both" is selected
            if collection_strategy == "both":
                st.markdown("**Adjust Collection Ratio:**")
                col_ratio1, col_ratio2 = st.columns(2)
                with col_ratio1:
                    brand_owned_ratio = st.slider(
                        "Brand-Owned Ratio (%)",
                        min_value=0,
                        max_value=100,
                        value=60,
                        step=5,
                        help="Percentage of URLs from brand-owned domains"
                    )
                with col_ratio2:
                    third_party_ratio = 100 - brand_owned_ratio
                    st.metric("3rd Party Ratio (%)", f"{third_party_ratio}%")
                    st.caption("Auto-calculated")
            else:
                # Set ratio to 100/0 or 0/100 based on selection
                if collection_strategy == "brand_controlled":
                    brand_owned_ratio = 100
                else:  # third_party
                    brand_owned_ratio = 0

            st.divider()

            # Auto-infer brand domains from brand_id
            if collection_strategy in ["brand_controlled", "both"]:
                # Automatically infer brand domains
                inferred = infer_brand_domains(brand_id)

                st.info(f"🤖 **Auto-detected brand domains:** {', '.join(inferred['domains'][:3])}{'...' if len(inferred['domains']) > 3 else ''}")

                # Advanced override option
                with st.expander("⚙️ Advanced: Customize Brand Domains (Optional)", expanded=False):
                    st.caption("The system automatically detects brand domains. Only customize if you need specific overrides.")

                    brand_domains_input = st.text_input(
                        "Additional Brand Domains",
                        value="",
                        placeholder="Leave empty to use auto-detected domains",
                        help="Comma-separated list. Leave empty to use auto-detected domains."
                    )

                    brand_subdomains_input = st.text_input(
                        "Additional Subdomains",
                        value="",
                        placeholder="e.g., blog.nike.com, help.nike.com",
                        help="Comma-separated list of specific brand subdomains to add"
                    )

                    brand_social_handles_input = st.text_input(
                        "Additional Social Handles",
                        value="",
                        placeholder="e.g., @nikerunning, nikebasketball",
                        help="Comma-separated list of additional brand social media handles"
                    )

                # Use auto-detected or manual override
                if brand_domains_input.strip():
                    brand_domains = [d.strip() for d in brand_domains_input.split(',') if d.strip()]
                else:
                    brand_domains = inferred['domains']

                # Combine auto-detected with additional manual entries
                if brand_subdomains_input.strip():
                    manual_subdomains = [d.strip() for d in brand_subdomains_input.split(',') if d.strip()]
                    brand_subdomains = list(dict.fromkeys(inferred['subdomains'] + manual_subdomains))
                else:
                    brand_subdomains = inferred['subdomains']

                if brand_social_handles_input.strip():
                    manual_handles = [h.strip() for h in brand_social_handles_input.split(',') if h.strip()]
                    brand_social_handles = list(dict.fromkeys(inferred['social_handles'] + manual_handles))
                else:
                    brand_social_handles = inferred['social_handles']

                # Show confirmation
                if collection_strategy == "brand_controlled":
                    st.success(f"✓ Brand-controlled collection enabled with {len(brand_domains)} auto-detected domains")
            else:
                # No brand identification needed for 3rd party only
                brand_domains = []
                brand_subdomains = []
                brand_social_handles = []

        # DEBUG: Verify this section renders
        st.markdown("---")
        st.markdown("### 🤖 AI Model Configuration")

        # LLM Model Selection
        with st.expander("🤖 LLM Model Selection", expanded=True):
            st.markdown("**Choose which AI model to use for generating executive summaries and recommendations:**")

            # 1. Search/Discovery Model
            search_model = st.selectbox(
                "Search/Discovery Model",
                [
                    "gpt-4o-mini",
                    "gpt-4o",
                    "claude-sonnet-4-5-20250929",
                    "claude-opus-4-5-20251101",
                    "claude-3-5-sonnet-20240620",
                    "gemini-1.5-pro",
                    "deepseek-chat"
                ],
                index=0,
                help="Model used for discovering brand domains and URLs.",
                key="search_model_select"
            )

            col1, col2 = st.columns(2)

            with col1:
                summary_model = st.selectbox(
                    "Executive Summary Model",
                    options=[
                        "gpt-4o-mini",
                        "gpt-3.5-turbo",
                        "gpt-4o",
                        "claude-sonnet-4-5-20250929",
                        "claude-opus-4-5-20251101",
                        "claude-sonnet-4-20250514",
                        "claude-3-5-haiku-20241022",
                        "claude-3-haiku-20240307",
                        "gemini-1.5-pro",
                        "gemini-1.5-flash",
                        "deepseek-chat",
                        "deepseek-reasoner"
                    ],
                    index=0,  # default to gpt-4o-mini
                    help="Model for generating the main executive summary. Higher-tier models (GPT-4o) produce more detailed, actionable insights."
                )

            with col2:
                recommendations_model = st.selectbox(
                    "Recommendations Model",
                    options=[
                        "gpt-4o-mini",
                        "gpt-3.5-turbo",
                        "gpt-4o",
                        "claude-sonnet-4-5-20250929",
                        "claude-opus-4-5-20251101",
                        "claude-sonnet-4-20250514",
                        "claude-3-5-haiku-20241022",
                        "claude-3-haiku-20240307",
                        "gemini-1.5-pro",
                        "gemini-1.5-flash",
                        "deepseek-chat",
                        "deepseek-reasoner"
                    ],
                    index=0,  # default to gpt-4o-mini
                    help="Model for generating detailed recommendations section in markdown reports."
                )

            # Model information
            model_tiers = {
                'gpt-3.5-turbo': '💰 Budget',
                'gpt-4o-mini': '⚖️ Balanced',
                'gpt-4o': '⭐ Premium',
                'claude-sonnet-4-5-20250929': '⭐ Premium',
                'claude-opus-4-5-20251101': '⭐ Premium',
                'claude-sonnet-4-20250514': '⭐ Premium',
                'claude-3-5-haiku-20241022': '💰 Budget',
                'claude-3-haiku-20240307': '💰 Budget',
                'gemini-1.5-flash': '💰 Budget',
                'gemini-1.5-pro': '⚖️ Balanced',
                'deepseek-chat': '💰 Budget',
                'deepseek-reasoner': '⚖️ Balanced'
            }

            st.info(f"💡 **Selection**: Search: {model_tiers.get(search_model, '')} {search_model} | Summary: {model_tiers.get(summary_model, '')} {summary_model} | Recommendations: {model_tiers.get(recommendations_model, '')} {recommendations_model}")
            st.caption("💡 **Tip**: Use premium models (Claude Sonnet 4, GPT-4o) for highest quality summaries with specific, actionable recommendations.")
            
            # Smart Cache Toggle
            reuse_data = st.checkbox(
                "Use existing brand data (Smart Cache)", 
                value=True, 
                help="Reuse compatible data from previous runs (last 24h) to speed up analysis and reduce costs."
            )
            
            # Maintenance Section
            with st.expander("🛠️ Maintenance", expanded=False):
                st.caption("Manage local storage and data retention.")
                days_to_keep = st.number_input("Keep history (days)", min_value=1, value=30, step=1, help="Delete analysis runs older than this.")
                
                if st.button("🗑️ Prune Old Data"):
                    try:
                        with store.session_scope(store.get_engine()) as session:
                            deleted_count = store.prune_old_runs(session, days_to_keep=days_to_keep)
                        st.success(f"Cleaned up {deleted_count} old analysis runs.")
                    except Exception as e:
                        st.error(f"Pruning failed: {e}")

        st.divider()

        col_search, col_submit, col_clear = st.columns([1, 1, 3])
        with col_search:
            search_urls = st.button("🔍 Search for URLs", width='stretch')
        with col_submit:
            submit = st.button("▶️ Run Analysis", type="primary", width='stretch')
        with col_clear:
            if st.button("Clear Results", width='stretch'):
                st.session_state['last_run'] = None
                st.session_state['found_urls'] = None
                # clear any fallback indicator
                if 'llm_search_fallback' in st.session_state:
                    del st.session_state['llm_search_fallback']
                if 'llm_search_fallback_count' in st.session_state:
                    del st.session_state['llm_search_fallback_count']
                st.rerun()

    # Create progress container placeholder immediately after buttons (Below CTA)
    # This ensures progress appears here, and not below the URLs
    if 'progress_container_placeholder' not in st.session_state or st.session_state.get('progress_container_placeholder') is None:
        st.session_state['progress_container_placeholder'] = st.empty()

    # Create progress bar placeholder immediately after progress container
    if 'progress_bar_placeholder' not in st.session_state or st.session_state.get('progress_bar_placeholder') is None:
        st.session_state['progress_bar_placeholder'] = st.empty()

    # Handle URL search
    if search_urls:
        # Validate inputs
        if not brand_id or not keywords:
            st.error("⚠️ Brand ID and Keywords are required")
            return

        # Build sources list
        sources = []
        if use_web_search:
            sources.append('web')
        if use_reddit:
            sources.append('reddit')
        if use_youtube:
            sources.append('youtube')

        if not sources:
            st.error("⚠️ Please select at least one data source")
            return

        # Search for URLs without running analysis
        perform_initial_search(brand_id, keywords.split(), sources, web_pages, search_provider,
                       brand_domains, brand_subdomains, brand_social_handles,
                       collection_strategy, brand_owned_ratio, search_model=search_model)

    # Display found URLs for selection
    if 'found_urls' in st.session_state and st.session_state['found_urls']:
        st.markdown("### 📋 Found URLs")

        found_urls = st.session_state['found_urls']

        # Separate URLs into brand-owned and third-party
        brand_owned_urls = [u for u in found_urls if u.get('is_brand_owned', False)]
        third_party_urls = [u for u in found_urls if not u.get('is_brand_owned', False)]

        # Overall select/deselect buttons
        col_sel_all, col_desel_all, col_stats = st.columns([1, 1, 2])
        with col_sel_all:
            if st.button("✓ Select All"):
                for url_data in found_urls:
                    url_data['selected'] = True
                st.rerun()
        with col_desel_all:
            if st.button("✗ Deselect All"):
                for url_data in found_urls:
                    url_data['selected'] = False
                st.rerun()
        with col_stats:
            st.info(f"📊 Selected {sum(1 for u in found_urls if u.get('selected', True))} of {len(found_urls)} URLs")

        st.divider()

        # Brand-Owned URLs Section
        if brand_owned_urls:
            st.markdown("#### 🏢 Brand-Owned URLs")
            st.caption(f"{len(brand_owned_urls)} URLs from brand domains")

            for idx, url_data in enumerate(brand_owned_urls):
                col1, col2 = st.columns([1, 10])
                with col1:
                    url_data['selected'] = st.checkbox(
                        "Select",
                        value=url_data.get('selected', True),
                        key=f"brand_url_{idx}",
                        label_visibility="collapsed"
                    )
                with col2:
                    # Tier badge with platform-specific emoji for social media
                    tier = url_data.get('source_tier', 'unknown')
                    platform = url_data.get('platform', '')

                    # Use platform-specific emoji if this is a social media channel
                    if platform:
                        platform_emoji_map = {
                            'Instagram': '📸',
                            'LinkedIn': '💼',
                            'Twitter': '🐦',
                            'X (Twitter)': '✖️'
                        }
                        tier_emoji = platform_emoji_map.get(platform, '📱')
                        tier_label = platform
                    else:
                        tier_emoji = {
                            'primary_website': '🏠',
                            'content_hub': '📚',
                            'direct_to_consumer': '🛒',
                            'brand_social': '📱'
                        }.get(tier, '📄')
                        tier_label = tier.replace('_', ' ').title()

                    # Show title with tier and soft-verify badge if present
                    short_title = url_data.get('title', url_data.get('url', ''))[:70]
                    ellips = '...' if len(url_data.get('title', '')) > 70 else ''
                    title_line = f"**{short_title}{ellips}** {tier_emoji} `{tier_label}`"

                    # Add core domain badge
                    if url_data.get('is_core_domain'):
                        title_line += " ⭐ `Core Domain`"

                    if url_data.get('soft_verified'):
                        # Show a clear soft-verified badge with method (DNS resolution, etc.)
                        method = url_data.get('verification_method') or url_data.get('method') or 'soft-verified'
                        title_line += f" ⚠️ *Soft-verified ({method})*"

                    st.markdown(title_line)
                    # Show URL and optionally verification status
                    status = url_data.get('status')
                    if status:
                        st.caption(f"🔗 {url_data['url']} — HTTP {status}")
                    else:
                        st.caption(f"🔗 {url_data['url']}")

            st.divider()

        # Third-Party URLs Section
        if third_party_urls:
            st.markdown("#### 🌐 Third-Party URLs")
            st.caption(f"{len(third_party_urls)} URLs from external sources")

            for idx, url_data in enumerate(third_party_urls):
                col1, col2 = st.columns([1, 10])
                with col1:
                    url_data['selected'] = st.checkbox(
                        "Select",
                        value=url_data.get('selected', True),
                        key=f"third_party_url_{idx}",
                        label_visibility="collapsed"
                    )
                with col2:
                    # Tier badge
                    tier = url_data.get('source_tier', 'unknown')
                    tier_emoji = {
                        'news_media': '📰',
                        'user_generated': '👥',
                        'expert_professional': '🎓',
                        'marketplace': '🏪'
                    }.get(tier, '🌐')
                    tier_label = tier.replace('_', ' ').title()

                    # Show title with tier and soft-verify badge if present
                    short_title = url_data.get('title', url_data.get('url', ''))[:70]
                    ellips = '...' if len(url_data.get('title', '')) > 70 else ''
                    title_line = f"**{short_title}{ellips}** {tier_emoji} `{tier_label}`"
                    if url_data.get('soft_verified'):
                        method = url_data.get('verification_method') or url_data.get('method') or 'soft-verified'
                        title_line += f" ⚠️ *Soft-verified ({method})*"

                    st.markdown(title_line)
                    status = url_data.get('status')
                    if status:
                        st.caption(f"🔗 {url_data['url']} — HTTP {status}")
                    else:
                        st.caption(f"🔗 {url_data['url']}")
    
    if submit:
        # Validate inputs
        if not brand_id or not keywords:
            st.error("⚠️ Brand ID and Keywords are required")
            return

        # Build sources list
        sources = []
        if use_web_search:
            sources.append('web')
        if use_reddit:
            sources.append('reddit')
        if use_youtube:
            sources.append('youtube')

        if not sources:
            st.error("⚠️ Please select at least one data source")
            return

        # Check if URLs were searched and selected
        selected_urls = None
        if 'found_urls' in st.session_state and st.session_state['found_urls']:
            selected_urls = [u for u in st.session_state['found_urls'] if u.get('selected', True)]
            if not selected_urls:
                st.error("⚠️ Please select at least one URL to analyze")
                return

        # Fetch content for selected URLs
        if selected_urls:
            selected_urls = fetch_and_process_selected_urls(selected_urls)

        # Run pipeline via RunManager
        # Initialize progress indicator (same format as web search)
        if 'progress_container_placeholder' in st.session_state and st.session_state['progress_container_placeholder'] is not None:
            progress_container = st.session_state['progress_container_placeholder']
        else:
            progress_container = st.empty()
        
        progress_animator = ProgressAnimator(container=progress_container)
        if 'progress_bar_placeholder' in st.session_state and st.session_state['progress_bar_placeholder'] is not None:
            progress_bar = st.session_state['progress_bar_placeholder'].progress(0)
        else:
            progress_bar = st.progress(0)
        
        try:
            progress_animator.show("Initializing analysis pipeline...", "🚀")
            progress_bar.progress(5)
            
            engine = store.init_db()
            # Initialize scoring pipeline
            scorer = ContentScorer(use_attribute_detection=True)
            manager = RunManager(engine=engine, scoring_pipeline=scorer)
            
            progress_animator.show("Preparing assets for analysis...", "📦")
            progress_bar.progress(10)
            
            # Prepare assets from selected URLs if any
            assets_config = []
            if selected_urls:
                for url_data in selected_urls:
                    assets_config.append({
                        "url": url_data.get('url'),
                        "title": url_data.get('title'),
                        "source_type": "web", # Default to web for now
                        "metadata": url_data,
                        "html": url_data.get('html'), # Pass HTML for metadata extraction
                        # Pass visual analysis data at top level for RunManager
                        "screenshot_path": url_data.get('screenshot_path'),
                        "visual_analysis": url_data.get('visual_analysis')
                    })
            
            # Process uploaded social screenshots
            uploaded_social_files = st.session_state.get('uploaded_social_files', {})
            
            if uploaded_social_files:
                import tempfile
                import shutil
                
                temp_dir = os.path.join(PROJECT_ROOT, 'data', 'temp_uploads')
                os.makedirs(temp_dir, exist_ok=True)
                
                for platform, file_data in uploaded_social_files.items():
                    try:
                        # Create unique filename
                        timestamp = int(time.time())
                        filename = f"{brand_id}_{platform}_{timestamp}_{file_data['name']}"
                        file_path = os.path.join(temp_dir, filename)
                        
                        # Save file
                        with open(file_path, "wb") as f:
                            f.write(file_data['buffer'])
                            
                        # Add to assets config
                        platform_names = {
                            'linkedin': 'LinkedIn', 
                            'instagram': 'Instagram', 
                            'x': 'X (Twitter)'
                        }
                        
                        platform_urls = {
                            'linkedin': f'https://www.linkedin.com/company/{brand_id}',
                            'instagram': f'https://www.instagram.com/{brand_id}',
                            'x': f'https://x.com/{brand_id}'
                        }
                        
                        assets_config.append({
                            "url": platform_urls.get(platform, f'https://{platform}.com/{brand_id}'),
                            "title": f"{brand_id} on {platform_names.get(platform, platform)} (Manual Upload)",
                            "source_type": "social",
                            "channel": "social",
                            "raw_content": f"Manual upload of {platform_names.get(platform, platform)} profile for {brand_id}.",
                            "normalized_content": f"Manual upload of {platform_names.get(platform, platform)} profile for {brand_id}.",
                            "screenshot_path": f"file://{file_path}", # Use file:// protocol for local files
                            # "visual_analysis": True, # Removed: Avoid conflating request with result field
                            "meta_info": {
                                "manual_upload": True,
                                "force_visual_analysis": True, # Explicit flag for scorer
                                "platform": platform_names.get(platform, platform)
                            }
                        })
                        logger.info(f"Added manual upload for {platform}: {file_path}")
                        
                    except Exception as e:
                        logger.error(f"Failed to process upload for {platform}: {e}")
                        st.warning(f"⚠️ Failed to process {platform} upload: {e}")

            progress_animator.show(f"Configuring analysis for {brand_id}...", "⚙️")
            progress_bar.progress(20)
            
            run_config = {
                "sources": sources,
                "keywords": keywords.split(),
                "limit": max_items,
                "assets": assets_config if assets_config else None,
                "reuse_data": reuse_data,  # Pass UI toggle value
                "brand_name": brand_id, # Use ID as name for now
                "scenario_name": "Web Analysis",

                "scenario_description": f"Analysis of {brand_id} via {', '.join(sources)} (Visual: {'On' if use_visual_analysis else 'Off'})",
                "scenario_config": {
                    "include_comments": include_comments,
                    "search_provider": search_provider,
                    "brand_domains": brand_domains,
                    "brand_subdomains": brand_subdomains,
                    "brand_social_handles": brand_social_handles,
                    "summary_model": summary_model,
                    "recommendations_model": recommendations_model,
                    "search_model": search_model # Added search_model here
                },
                "visual_analysis_enabled": use_visual_analysis,
            }

            progress_animator.show("Scoring content across 5 trust dimensions...", "🔍")
            progress_bar.progress(30)
            # Run analysis
            # Temporarily enable visual analysis if requested
            original_visual_setting = SETTINGS.get('visual_analysis_enabled', False)
            if use_visual_analysis:
                SETTINGS['visual_analysis_enabled'] = True
                
            try:
                run = manager.run_analysis(brand_id, "web", run_config)
            finally:
                # Restore original setting
                if use_visual_analysis:
                    SETTINGS['visual_analysis_enabled'] = original_visual_setting
            
            progress_animator.show("Analysis completed! Generating report...", "✨")
            progress_bar.progress(90)
                
            # Adapt Run object to legacy dict format for UI compatibility
            # This ensures show_results_page works without major rewrite
            # Use centralized builder (includes visual analysis fix)
            report_data = manager.build_report_data(run.id)
            
            # Inject UI-specific model metadata
            report_data["llm_model"] = summary_model
            report_data["recommendations_model"] = recommendations_model
            
            legacy_run_data = {
                "run_id": run.external_id,
                "brand_id": run.brand.slug,
                "timestamp": run.started_at.isoformat(),
                "sources": sources,
                "scoring_report": report_data,
                "authenticity_ratio": report_data.get("authenticity_ratio")
            }
            
            # Log blocked URLs if any
            blocked_urls = report_data.get('blocked_urls', [])
            if blocked_urls:
                logger.info(f"Detected {len(blocked_urls)} blocked URLs due to anti-bot protection")

            # Generate PDF report
            progress_animator.show("Generating PDF report...", "📄")
            progress_bar.progress(90)
            
            try:
                from reporting.pdf_generator import PDFReportGenerator
                
                # Create output directory for reports
                output_dir = os.path.join(PROJECT_ROOT, 'output', 'webapp_runs')
                os.makedirs(output_dir, exist_ok=True)
                
                run_dir = os.path.join(output_dir, f"{run.brand.slug}_{run.external_id}")
                os.makedirs(run_dir, exist_ok=True)
                
                pdf_path = os.path.join(run_dir, f'ar_report_{run.brand.slug}_{run.external_id}.pdf')
                
                # Generate PDF using the scoring report data
                pdf_generator = PDFReportGenerator()
                pdf_generator.generate_report(legacy_run_data["scoring_report"], pdf_path)
                
                # Add path to run data
                legacy_run_data["pdf_path"] = pdf_path
                logger.info(f"Generated PDF report: {pdf_path}")
            except Exception as pdf_err:
                logger.warning(f"PDF generation failed: {pdf_err}")
                # Continue without PDF - the download button will show as disabled

            progress_animator.show("Analysis complete! ✅", "✨")
            progress_bar.progress(100)
            
            # Clear progress indicators before showing results
            progress_bar.empty()
            progress_animator.clear()
            
            # Ensure progress container placeholder is also cleared
            if 'progress_container_placeholder' in st.session_state:
                try:
                    if st.session_state['progress_container_placeholder'] is not None:
                        st.session_state['progress_container_placeholder'].empty()
                except:
                    pass
                del st.session_state['progress_container_placeholder']

            # Ensure progress bar placeholder is executed
            if 'progress_bar_placeholder' in st.session_state:
                try:
                    if st.session_state['progress_bar_placeholder'] is not None:
                        st.session_state['progress_bar_placeholder'].empty()
                except:
                    pass
                del st.session_state['progress_bar_placeholder']

            st.session_state['last_run'] = legacy_run_data
            st.session_state['page'] = 'results'
            st.rerun()
            
        except Exception as e:
            # Clear progress on error
            try:
                progress_bar.empty()
                progress_animator.clear()
            except:
                pass
            st.error(f"Analysis failed: {str(e)}")
            logger.exception("RunManager analysis failed")
        finally:
            # Ensure browser is closed to free resources
            try:
                get_browser_manager().close()
            except Exception as e:
                logger.warning(f"Failed to close browser manager: {e}")


def detect_brand_owned_url(url: str, brand_id: str, brand_domains: List[str] = None, brand_subdomains: List[str] = None, brand_social_handles: List[str] = None) -> Dict[str, Any]:
    """
    Detect if a URL is a brand-owned property using the domain classifier.

    Returns:
        Dict with keys: is_brand_owned (bool), source_type (str), source_tier (str), reason (str)
    """
    try:
        from ingestion.domain_classifier import classify_url, URLCollectionConfig, URLSourceType

        # Create config for classification
        if brand_domains:
            config = URLCollectionConfig(
                brand_owned_ratio=0.6,
                third_party_ratio=0.4,
                brand_domains=brand_domains or [],
                brand_subdomains=brand_subdomains or [],
                brand_social_handles=brand_social_handles or []
            )
        else:
            # Fallback to simple heuristic if no domains provided
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower().replace('www.', '')
            is_owned = brand_id.lower() in domain
            return {
                'is_brand_owned': is_owned,
                'source_type': 'brand_owned' if is_owned else 'third_party',
                'source_tier': 'primary_website' if is_owned else 'user_generated',
                'reason': f"Simple heuristic: {brand_id} {'found' if is_owned else 'not found'} in domain"
            }

        # Use domain classifier
        classification = classify_url(url, config)
        return {
            'is_brand_owned': classification.source_type == URLSourceType.BRAND_OWNED,
            'source_type': classification.source_type.value,
            'source_tier': classification.tier.value if classification.tier else 'unknown',
            'reason': classification.reason
        }
    except Exception as e:
        # Fallback on error
        return {
            'is_brand_owned': False,
            'source_type': 'unknown',
            'source_tier': 'unknown',
            'reason': f"Classification error: {str(e)}"
        }


# search_social_media_channels function moved to webapp/services/social_search.py


# _is_valid_social_profile function moved to webapp/services/social_search.py

# search_for_urls function moved to webapp/services/search_orchestration.py

# run_analysis function moved to webapp/services/analysis_engine.py

def programmatic_quick_run(urls: List[str], output_dir: str = None, brand_id: str = 'brand') -> Dict[str, Any]:
    """Programmatic helper used by tests to run the pipeline for a set of URLs.

    This function delegates to scripts.run_pipeline.run_pipeline_for_contents and
    returns the resulting dict. Tests may monkeypatch that function to simulate
    pipeline behavior.
    """
    try:
        from scripts.run_pipeline import run_pipeline_for_contents
    except Exception as e:
        raise RuntimeError(f"Could not import run_pipeline_for_contents: {e}")

    out_dir = output_dir or os.path.join(PROJECT_ROOT, 'output')
    os.makedirs(out_dir, exist_ok=True)

    # Delegate to pipeline runner
    result = run_pipeline_for_contents(urls, output_dir=out_dir, brand_id=brand_id)
    return result


def show_results_page():
    """Display analysis results with visualizations"""

    # Load last run or selected run
    run_data = st.session_state.get('last_run')

    # Safety check: Ensure progress container is cleared
    if 'progress_container' in st.session_state and st.session_state['progress_container'] is not None:
        try:
            st.session_state['progress_container'].empty()
        except:
            pass
        st.session_state['progress_container'] = None
        
    # Also clear the placeholder itself to remove the purple box
    if 'progress_container_placeholder' in st.session_state:
        try:
            if st.session_state['progress_container_placeholder'] is not None:
                st.session_state['progress_container_placeholder'].empty()
        except:
            pass
        # Remove it completely so it doesn't re-render empty space
        del st.session_state['progress_container_placeholder']

    if not run_data:
        st.warning("⚠️ No analysis results available. Please run an analysis first.")
        if st.button("← Back to Analysis"):
            st.session_state['page'] = 'analyze'
            st.rerun()
        return

    report = run_data.get('scoring_report', {})
    items = report.get('items', [])

    # Calculate average comprehensive rating (convert to 0-10 scale for display)
    if items:
        avg_rating_internal = sum(item.get('final_score', 0) for item in items) / len(items)
        avg_rating_internal = avg_rating_internal / 100  # Convert from 0-100 to 0-1
        avg_rating_display = to_display_score(avg_rating_internal)
    else:
        avg_rating_internal = 0
        avg_rating_display = 0

    # Calculate rating distribution
    excellent = sum(1 for item in items if item.get('final_score', 0) >= 80)
    good = sum(1 for item in items if 60 <= item.get('final_score', 0) < 80)
    fair = sum(1 for item in items if 40 <= item.get('final_score', 0) < 60)
    poor = sum(1 for item in items if item.get('final_score', 0) < 40)

    # Header with Download Report CTA
    header_col, download_col = st.columns([3, 1])
    with header_col:
        st.markdown('<div class="main-header">⭐ Trust Stack Results</div>', unsafe_allow_html=True)
    with download_col:
        # Download Report button - links to PDF
        pdf_path = run_data.get('pdf_path')
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                st.download_button(
                    label="📄 Download Report",
                    data=f,
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf",
                    key="header_download_report"
                )
        else:
            st.button("📄 Download Report", disabled=True, help="PDF not available yet")
    
    # Date
    from datetime import datetime
    current_date = datetime.now().strftime("%B %d, %Y")
    st.markdown(f"**Date:** {current_date}")
    st.markdown("")  # Spacing
    
    # Brand Header Section
    brand_id = run_data.get("brand_id", "Unknown Brand")
    brand_name_display = brand_id.replace('_', ' ').replace('-', ' ').title()
    
    st.markdown(f"### {brand_name_display}")
    
    # NOTE: Data Source(s) URL display removed - URLs are surfaced in
    # the Content Items Detail table and throughout the report
    
    st.markdown("")  # Spacing
    
    # Try to infer content types and generate description
    content_types = set()
    sample_titles = []
    sample_descriptions = []
    
    for item in items[:10]:  # Sample first 10 items
        meta = item.get('meta', {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta) if meta else {}
            except:
                meta = {}
        
        # Collect titles and descriptions for brand description
        title = meta.get('title') or meta.get('og:title') or ''
        description = meta.get('description') or meta.get('og:description') or ''
        
        if title:
            sample_titles.append(title)
        if description:
            sample_descriptions.append(description)
        
        # Infer content type from metadata
        if meta.get('og:type') == 'article' or 'blog' in str(meta.get('url', '')).lower():
            content_types.add('articles')
        elif 'product' in str(meta.get('og:type', '')).lower() or '/product' in str(meta.get('url', '')).lower():
            content_types.add('product pages')
        elif meta.get('twitter:card'):
            content_types.add('social media content')
    
    # Generate brand description using LLM or fallback
    brand_description = ""
    
    # Try to use LLM for brand description if we have sample content
    # Try to use LLM for brand description if we have items (URLs) or sample content
    summary_model_used = report.get('llm_model', 'gpt-4o-mini')
    if items:
        try:
            from scoring.scoring_llm_client import LLMScoringClient
            
            # Prepare context for the summary: list of URLs and sample content
            urls_list = []
            for item in items[:20]:
                m = item.get('meta', {})
                if isinstance(m, str):
                    try:
                        m = json.loads(m)
                    except:
                        m = {}
                u = m.get('source_url') or m.get('url') or m.get('link')
                if u:
                    urls_list.append(u)
            
            urls_text = '\n'.join(urls_list)
            # Use whatever sample text we have, or just a placeholder if none
            sample_text = ' '.join(sample_descriptions[:5])[:1000] if sample_descriptions else "No content snippets available."
            
            prompt = f"""You are writing a summary for a "Trust Stack" analysis report for {brand_id}.
Instead of a generic brand description, write a 2-3 sentence summary of the SPECIFIC websites and content that were analyzed in this report.

CRITICAL INSTRUCTIONS:
- Be specific about the types of pages analyzed (e.g. "Analysis covers the main corporate homepage, investor relations site, and 3 product pages...").
- Use a professional but engaging and personable tone. Avoid robotic language.
- Mention specific details from the URLs or content if possible.
- Do NOT say "The report analyzes..." repeatedly. vary your sentence structure.

Analyzed URLs:
{urls_text}

Content Samples:
{sample_text}

Summary of Analyzed Content:"""
            
            client = LLMScoringClient()
            brand_description = client.generate(
                prompt=prompt,
                model=summary_model_used,
                max_tokens=200,
                temperature=0.7
            ).strip()
            
            # Debug: Show if LLM generation succeeded
            if brand_description:
                logger.info(f"Generated brand description via LLM: {brand_description}")
        except Exception as e:
            # Log the error so we can see what's failing
            logger.warning(f"Brand description LLM generation failed: {e}")
            # Fallback to simple description
            pass
    else:
        # Debug: Log if we don't have items
        logger.info(f"No items available for brand description. Items: {len(items)}")
    
    # Fallback description if LLM fails
    if not brand_description:
        if content_types:
            types_str = ', '.join(sorted(content_types))
            brand_description = f"The website {brand_name_display} offers {types_str}."
        else:
            brand_description = f"The website {brand_name_display} provides various content and offerings."
    
    # Add content type info
    if content_types:
        types_str = ', '.join(sorted(content_types))
        full_description = f"{brand_description} This report evaluates **{len(items)} content items** ({types_str}) across five trust dimensions."
    else:
        full_description = f"{brand_description} This report evaluates **{len(items)} content items** across five trust dimensions."
    
    st.markdown(full_description)
    
    # Display blocked URLs warning if any
    blocked_urls = report.get('blocked_urls', [])
    if blocked_urls:
        with st.expander(f"⚠️ **{len(blocked_urls)} URL(s) Blocked by Anti-Bot Protection**", expanded=False):
            st.markdown("""
<div style="background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
    <p style="margin: 0; color: #856404;">
        <strong>What happened:</strong> Some websites use sophisticated anti-bot protection 
        (like Akamai, Cloudflare, or PerimeterX) that blocked our automated analysis.
        These sites could not provide content for scoring.
    </p>
</div>
""", unsafe_allow_html=True)
            
            st.markdown("**Affected URLs:**")
            for blocked in blocked_urls:
                st.markdown(f"- 🚫 [{blocked.get('title', 'Unknown')}]({blocked.get('url', '#')}) — *{blocked.get('reason', 'Access Denied')}*")
            
            st.markdown("""
---
**What you can do:**
- These sites' scores are based on limited data (fallback heuristics)
- For accurate analysis, consider accessing these sites manually or using alternative data sources
- Social media profiles and subdomain sites often have less restrictive access
""")
    
    st.divider()

    # =========================================================================
    # TRUST STACK REPORT SECTION
    # =========================================================================
    
    # Check if we already have the generated report in the run data
    trust_stack_text = run_data.get('trust_stack_report_text')
    
    if not trust_stack_text or "CUSTOM GPT" in trust_stack_text or "CUSTOM GTP" in trust_stack_text:
        with st.spinner("Generating detailed Trust Stack Analysis..."):
            try:
                # Generate the report text using the new module
                trust_stack_text = generate_trust_stack_report(report, model=summary_model_used)
                
                # Store it in run_data and session state so we don't re-generate on every rerun
                run_data['trust_stack_report_text'] = trust_stack_text
                st.session_state['last_run'] = run_data
                
                # Optionally save to disk if we can find the file
                # (This is a best-effort attempt to persist the generated text)
                if '_file_path' in run_data:
                    try:
                        with open(run_data['_file_path'], 'w') as f:
                            json.dump(run_data, f, indent=2, default=str)
                    except Exception as e:
                        logger.warning(f"Could not save generated report text to file: {e}")
                        
            except Exception as e:
                st.error(f"Failed to generate Trust Stack Report: {e}")
                trust_stack_text = "Error generating report."

    # Render the Markdown Report
    # Pre-process to embed local images
    trust_stack_text_processed = _embed_local_images_as_base64(trust_stack_text)
    st.markdown(trust_stack_text_processed, unsafe_allow_html=True)

    st.divider()

    st.divider()

    # Content Items Detail
    st.markdown("### 📝 Content Items Detail")

    appendix = report.get('appendix', [])

    if items:
        # Create DataFrame for display
        items_data = []
        for item in items:
            # Parse meta if it's a JSON string
            meta = item.get('meta', {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except:
                    meta = {}
            elif meta is None:
                meta = {}

            score = item.get('final_score', 0)

            # Determine rating band
            if score >= 80:
                rating_band = '🟢 Excellent'
            elif score >= 60:
                rating_band = '🟡 Good'
            elif score >= 40:
                rating_band = '🟠 Fair'
            else:
                rating_band = '🔴 Poor'

            items_data.append({
                'Source': item.get('source', '').upper(),
                'Title': meta.get('title', meta.get('name', ''))[:50] + '...' if meta.get('title') or meta.get('name') else 'N/A',
                'Score': f"{score:.1f}",
                'Rating': rating_band,
                'URL': meta.get('source_url', meta.get('url', 'N/A'))
            })

        df = pd.DataFrame(items_data)

        # Color-code by rating band
        def color_rating(val):
            if '🟢' in val:
                return 'background-color: #d4edda; color: #155724'
            elif '🟡' in val:
                return 'background-color: #d1ecf1; color: #0c5460'
            elif '🟠' in val:
                return 'background-color: #fff3cd; color: #856404'
            elif '🔴' in val:
                return 'background-color: #f8d7da; color: #721c24'
            return ''

        styled_df = df.style.map(color_rating, subset=['Rating'])
        # Use a unique key based on run ID to prevent state issues (setIn error)
        # when columns change between runs
        st.dataframe(
            styled_df, 
            width='stretch', 
            height=400,
            key=f"items_detail_{run_data.get('run_id', 'unknown')}_{len(items)}"
        )

        # Detailed view expander
        with st.expander("🔎 View Detailed Breakdown"):
            for idx, item_detail in enumerate(appendix[:20]):  # Limit to first 20 for performance
                # Parse meta if it's a JSON string
                meta = item_detail.get('meta', {})
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except:
                        meta = {}
                elif meta is None:
                    meta = {}

                st.markdown(f"**Item {idx + 1}: {meta.get('title', 'Untitled')}**")

                col_a, col_b = st.columns([1, 2])

                with col_a:
                    item_score = item_detail.get('final_score', 0)
                    if item_score >= 80:
                        rating_band = '🟢 Excellent'
                    elif item_score >= 60:
                        rating_band = '🟡 Good'
                    elif item_score >= 40:
                        rating_band = '🟠 Fair'
                    else:
                        rating_band = '🔴 Poor'

                    st.write(f"**Source:** {item_detail.get('source', 'N/A')}")
                    st.write(f"**Rating Score:** {item_score:.1f}/100")
                    st.write(f"**Rating Band:** {rating_band}")

                with col_b:
                    st.write("**Dimension Scores:**")
                    dims = item_detail.get('dimension_scores', {})
                    dim_cols = st.columns(3)
                    for idx2, (dim_name, score) in enumerate(dims.items()):
                        if score is not None:
                            with dim_cols[idx2 % 3]:
                                st.metric(dim_name.title(), f"{score*100:.1f}/100")
                
                # Show screenshot if available
                screenshot_path = meta.get('screenshot_path') or item_detail.get('screenshot_path')
                if screenshot_path:
                    try:
                        # Handle file:// paths for local display
                        if screenshot_path.startswith('file://'):
                            local_path = screenshot_path.replace('file://', '')
                            if os.path.exists(local_path):
                                st.image(local_path, caption="Page Screenshot", width="stretch")
                        else:
                            st.image(screenshot_path, caption="Page Screenshot", width="stretch")
                    except Exception as e:
                        st.caption(f"Screenshot not available: {e}")

                st.divider()

    st.divider()

    # Legacy AR Metrics (optional)
    with st.expander("📊 Legacy Metrics (Authenticity Ratio)"):
        st.caption("These metrics are provided for backward compatibility. The primary focus is Trust Stack Ratings.")

        ar_data = report.get('authenticity_ratio', {})

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                label="Core AR",
                value=f"{ar_data.get('authenticity_ratio_pct', 0):.1f}%"
            )

        with col2:
            st.metric(
                label="Extended AR",
                value=f"{ar_data.get('extended_ar_pct', 0):.1f}%"
            )

        with col3:
            st.metric(
                label="Authentic Items",
                value=f"{ar_data.get('authentic_items', 0):,}"
            )

        with col4:
            st.metric(
                label="Inauthentic Items",
                value=f"{ar_data.get('inauthentic_items', 0):,}"
            )

        st.caption("**Note:** AR classifies content as Authentic/Suspect/Inauthentic using fixed thresholds. Trust Stack Ratings provide more nuanced 0-100 scores across 6 dimensions.")

    st.divider()

    # Export section
    st.markdown("### 📥 Export Reports")

    col1, col2, col3 = st.columns(3)

    with col1:
        pdf_path = run_data.get('pdf_path')
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                st.download_button(
                    label="📄 Download PDF Report",
                    data=f,
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf",
                    width='stretch'
                )

    with col2:
        md_path = run_data.get('md_path')
        if md_path and os.path.exists(md_path):
            with open(md_path, 'r') as f:
                st.download_button(
                    label="📝 Download Markdown Report",
                    data=f.read(),
                    file_name=os.path.basename(md_path),
                    mime="text/markdown",
                    width='stretch'
                )

    with col3:
        # Export raw data as JSON
        st.download_button(
            label="💾 Download Raw Data (JSON)",
            data=json.dumps(report, indent=2, default=str),
            file_name=f"trust_stack_data_{run_data.get('brand_id')}_{run_data.get('run_id')}.json",
            mime="application/json",
            width='stretch'
        )


def show_history_page():
    """Display analysis history with enhanced features"""
    st.markdown('<div class="main-header">📚 Rating History</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">View and manage past analysis runs</div>', unsafe_allow_html=True)

    st.divider()

    # Find all past runs
    output_dir = os.path.join(PROJECT_ROOT, 'output', 'webapp_runs')

    if not os.path.exists(output_dir):
        st.info("📭 No analysis history found. Run your first analysis to get started!")
        if st.button("🚀 Run Your First Analysis"):
            st.session_state['page'] = 'analyze'
            st.rerun()
        return

    # Scan for run data files
    run_files = file_glob.glob(os.path.join(output_dir, '*', '_run_data.json'))

    if not run_files:
        st.info("📭 No analysis history found. Run your first analysis to get started!")
        if st.button("🚀 Run Your First Analysis"):
            st.session_state['page'] = 'analyze'
            st.rerun()
        return

    # Load and display runs
    runs = []
    for run_file in run_files:
        try:
            with open(run_file, 'r') as f:
                run_data = json.load(f)
                # Add file path for reference
                run_data['_file_path'] = run_file
                runs.append(run_data)
        except Exception as e:
            logger.warning(f"Failed to load run data from {run_file}: {e}")
            continue

    if not runs:
        st.warning("⚠️ Found run files but couldn't load any valid data. The files may be corrupted.")
        return

    # Sort by timestamp (newest first)
    runs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Total Runs", len(runs))
    with col2:
        unique_brands = len(set(r.get('brand_id', 'Unknown') for r in runs))
        st.metric("🏢 Brands Analyzed", unique_brands)
    with col3:
        total_items = sum(r.get('total_items', 0) for r in runs)
        st.metric("📝 Total Items", f"{total_items:,}")
    with col4:
        # Calculate average rating across all runs
        all_ratings = []
        for run in runs:
            report = run.get('scoring_report', {})
            items = report.get('items', [])
            if items:
                avg = sum(item.get('final_score', 0) for item in items) / len(items) * 100
                all_ratings.append(avg)
        if all_ratings:
            overall_avg = sum(all_ratings) / len(all_ratings)
            st.metric("⭐ Avg Rating", f"{overall_avg:.1f}/100")
        else:
            st.metric("⭐ Avg Rating", "N/A")

    st.divider()

    # Filter options
    with st.expander("🔍 Filter Options", expanded=False):
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            brands = sorted(set(r.get('brand_id', 'Unknown') for r in runs))
            selected_brand = st.selectbox("Filter by Brand", ["All"] + brands)
        with filter_col2:
            sources_all = sorted(set(src for r in runs for src in r.get('sources', [])))
            selected_source = st.selectbox("Filter by Source", ["All"] + sources_all)

    # Apply filters
    filtered_runs = runs
    if selected_brand != "All":
        filtered_runs = [r for r in filtered_runs if r.get('brand_id') == selected_brand]
    if selected_source != "All":
        filtered_runs = [r for r in filtered_runs if selected_source in r.get('sources', [])]

    st.write(f"**Showing {len(filtered_runs)} of {len(runs)} runs**")

    # Display runs in a more visual way
    for idx, run in enumerate(filtered_runs):
        report = run.get('scoring_report', {})
        items = report.get('items', [])
        dimension_breakdown = report.get('dimension_breakdown', {})

        # Calculate average rating for this run
        if items:
            avg_rating = sum(item.get('final_score', 0) for item in items) / len(items) * 100
        else:
            avg_rating = 0

        # Determine rating badge
        if avg_rating >= 80:
            rating_badge = "🟢 Excellent"
            badge_color = "#28a745"
        elif avg_rating >= 60:
            rating_badge = "🟡 Good"
            badge_color = "#ffc107"
        elif avg_rating >= 40:
            rating_badge = "🟠 Fair"
            badge_color = "#fd7e14"
        else:
            rating_badge = "🔴 Poor"
            badge_color = "#dc3545"

        # Format timestamp
        try:
            timestamp = datetime.fromisoformat(run.get('timestamp', '')).strftime('%B %d, %Y at %I:%M %p')
        except:
            timestamp = run.get('timestamp', 'Unknown')

        # Create card-style display
        with st.container():
            # Header row
            header_col1, header_col2, header_col3 = st.columns([3, 2, 1])

            with header_col1:
                st.markdown(f"### 🏢 {run.get('brand_id', 'Unknown Brand')}")
                st.caption(f"📅 {timestamp}")

            with header_col2:
                st.markdown(f"<h3 style='color: {badge_color}; text-align: center;'>{rating_badge}</h3>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center; font-size: 24px; margin: 0;'><b>{avg_rating:.1f}/100</b></p>", unsafe_allow_html=True)

            with header_col3:
                st.write("")  # Spacing
                if st.button("📊 View", key=f"view_{idx}", width='stretch'):
                    st.session_state['last_run'] = run
                    st.session_state['page'] = 'results'
                    st.rerun()

            # Details row
            detail_col1, detail_col2, detail_col3, detail_col4 = st.columns(4)

            with detail_col1:
                st.metric("📝 Items", run.get('total_items', 0))

            with detail_col2:
                keywords = run.get('keywords', [])
                st.write("**🔍 Keywords:**")
                st.caption(', '.join(keywords[:3]) + ('...' if len(keywords) > 3 else ''))

            with detail_col3:
                sources = run.get('sources', [])
                st.write("**📊 Sources:**")
                st.caption(', '.join(sources))

            with detail_col4:
                # Show top dimension
                if dimension_breakdown:
                    dim_avgs = {k: v.get('average', 0) * 100 for k, v in dimension_breakdown.items()}
                    if dim_avgs:
                        top_dim = max(dim_avgs, key=dim_avgs.get)
                        st.write("**⭐ Top Dimension:**")
                        st.caption(f"{top_dim.title()} ({dim_avgs[top_dim]:.0f})")

            # Download reports section
            download_col1, download_col2, download_col3 = st.columns([2, 1, 1])

            with download_col1:
                # Show models used
                llm_model = report.get('llm_model', 'Unknown')
                rec_model = report.get('recommendations_model', 'Unknown')
                st.caption(f"🤖 Models: {llm_model} / {rec_model}")

            with download_col2:
                # PDF download
                pdf_path = run.get('pdf_path')
                if pdf_path and os.path.exists(pdf_path):
                    with open(pdf_path, 'rb') as f:
                        st.download_button(
                            label="📄 PDF",
                            data=f.read(),
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf",
                            key=f"pdf_{idx}",
                            width='stretch'
                        )

            with download_col3:
                # Markdown download
                md_path = run.get('md_path')
                if md_path and os.path.exists(md_path):
                    with open(md_path, 'r') as f:
                        st.download_button(
                            label="📋 MD",
                            data=f.read(),
                            file_name=os.path.basename(md_path),
                            mime="text/markdown",
                            key=f"md_{idx}",
                            width='stretch'
                        )

            st.divider()

@st.dialog("Upload Social Media Screenshots")
def upload_social_modal():
    st.write("Upload or paste screenshots for login-walled sites.")
    
    from streamlit_paste_button import paste_image_button as pbutton
    import io
    from PIL import Image

    # Initialize container for uploaded files if not exists
    if 'uploaded_social_files' not in st.session_state:
        st.session_state['uploaded_social_files'] = {}

    # Define platforms
    platforms = [
        {'key': 'linkedin', 'label': 'LinkedIn', 'icon': '💼'},
        {'key': 'instagram', 'label': 'Instagram', 'icon': '📸'},
        {'key': 'x', 'label': 'X (Twitter)', 'icon': '✖️'}
    ]

    # Create columns for each platform
    cols = st.columns(3)

    for idx, platform in enumerate(platforms):
        key = platform['key']
        with cols[idx]:
            st.markdown(f"### {platform['icon']} {platform['label']}")
            
            # Show current status
            current_file = st.session_state['uploaded_social_files'].get(key)
            if current_file:
                st.success(f"File ready")
                st.caption(f"{current_file['name'][:15]}...")
                if st.button("🗑️ Remove", key=f"remove_{key}"):
                    del st.session_state['uploaded_social_files'][key]
                    st.rerun()
            else:
                st.info("No file")

            # Upload Tab
            uploaded_file = st.file_uploader("Upload", type=['png', 'jpg', 'jpeg'], key=f"modal_upload_{key}", label_visibility="collapsed")
            if uploaded_file:
                # Update if new
                if not current_file or current_file['name'] != uploaded_file.name:
                    st.session_state['uploaded_social_files'][key] = {
                        'name': uploaded_file.name,
                        'type': uploaded_file.type,
                        'buffer': uploaded_file.getvalue()
                    }
                    st.rerun()

            # Paste Button
            paste_result = pbutton(
                label="📋 Paste",
                background_color="#1a2d42",
                hover_background_color="#e0e2e6",
                key=f"paste_btn_{key}"
            )
            
            if paste_result.image_data is not None:
                 img = paste_result.image_data
                 buf = io.BytesIO()
                 img.save(buf, format='PNG')
                 byte_im = buf.getvalue()
                 
                 timestamp = int(time.time())
                 fname = f"pasted_{key}.png"
                 
                 # Only update if different content/name
                 if not current_file or current_file['buffer'] != byte_im:
                     st.session_state['uploaded_social_files'][key] = {
                        'name': fname,
                        'type': "image/png",
                        'buffer': byte_im
                    }
                     st.rerun()

    st.divider()
    if st.button("Done", type="primary", width="stretch"):
        st.rerun()


def main():
    """Main application entry point"""

    # Initialize session state
    if 'page' not in st.session_state:
        st.session_state['page'] = 'home'

    # Sidebar navigation
    with st.sidebar:
        if st.button("🏠 Home", width='stretch'):
            st.session_state['page'] = 'home'
            st.rerun()

        if st.button("🚀 Run Analysis", width='stretch'):
            st.session_state['page'] = 'analyze'
            st.rerun()

        if st.button("📊 View Results", width='stretch'):
            st.session_state['page'] = 'results'
            st.rerun()

        if st.button("📚 History", width='stretch'):
            st.session_state['page'] = 'history'
            st.rerun()
        
        if st.button("📋 Brand Guidelines", width='stretch'):
            st.session_state['page'] = 'guidelines'
            st.rerun()

        st.divider()


        st.caption("Trust Stack Rating v2.0")
        st.caption("5D Trust Framework")

    # Route to appropriate page
    page = st.session_state.get('page', 'home')

    if page == 'home':
        show_home_page()
    elif page == 'analyze':
        show_analyze_page()
    elif page == 'results':
        show_results_page()
    elif page == 'history':
        show_history_page()
    elif page == 'guidelines':
        show_brand_guidelines_page()


if __name__ == '__main__':
    main()
