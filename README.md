# Trust Stack Rating Tool

A comprehensive content quality assessment system that analyzes brand-linked content across digital channels using the **5D Trust Framework**. The tool provides a Trust Stack Rating (0-100 scale) and detailed insights into content authenticity, transparency, and trustworthiness.

## 🎯 What It Does

The Trust Stack Rating Tool assesses brand content across six trust dimensions:
- **Provenance**: Origin clarity, traceability, and metadata completeness
- **Verification**: Factual accuracy against trusted sources
- **Transparency**: Clarity of disclosures and attribution
- **Coherence**: Consistency across channels
- **Resonance**: Cultural fit and organic engagement patterns
- **AI Readiness**: Machine discoverability and LLM-compatible signals

Each content item receives a comprehensive rating (0-100), with a weighted average across all dimensions. The system also computes a legacy **Authenticity Ratio** metric for backward compatibility.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Required packages: `pip install -r requirements.txt`
- Optional API credentials for enhanced data sources

### Web Application (Recommended)

The easiest way to use the tool is through the interactive web application:

```bash
streamlit run webapp/app.py
```

This launches a web interface at `http://localhost:8501` with:
- **Interactive dashboards** with visualizations (charts, radar plots, histograms)
- **Brand analysis configuration** with custom parameters
- **Real-time progress tracking** during analysis
- **Results analysis** with detailed content breakdown
- **Multiple export formats** (PDF, Markdown, JSON)
- **Analysis history** to track and compare multiple runs
- **Status indicators** for available data sources

See [webapp/README.md](webapp/README.md) for detailed usage instructions.

### Command Line (Advanced)

For programmatic or batch processing:

```bash
# Run the full pipeline with custom parameters
python scripts/run_pipeline.py \
  --brand-id myBrand \
  --keywords "brand name" \
  --sources brave reddit youtube \
  --max-items 50
```

Available data sources: `brave`, `reddit`, `youtube`

## 📊 Project Architecture

### Pipeline Stages
1. **Ingestion**: Collect content from configured data sources (Brave Search, Reddit, YouTube)
2. **Normalization**: Standardize content format across sources
3. **Enrichment**: Extract metadata, detect attributes (SSL, schema markup, author info, etc.)
4. **Scoring**: Apply 5D rubric using LLM-based analysis for each dimension
5. **Classification**: Categorize content as Excellent/Good/Fair/Poor based on overall score
6. **Reporting**: Generate comprehensive reports (PDF, Markdown, JSON)
7. **Export**: Save results for analysis and comparison

### Directory Structure
```
authenticity-ratio/
├── webapp/                 # Streamlit web application
├── ingestion/              # Data collection from various sources
│   ├── brave_search.py     # Brave Search API/HTML scraping
│   ├── reddit_crawler.py   # Reddit API integration
│   ├── youtube_scraper.py  # YouTube Data API v3
│   ├── normalizer.py       # Content standardization
│   └── metadata_extractor.py  # Metadata and attribute detection
├── scoring/                # Trust Stack Rating computation
│   ├── pipeline.py         # Main scoring pipeline
│   ├── scorer.py           # 5D dimension scoring
│   ├── attribute_detector.py  # Trust attribute detection
│   ├── classifier.py       # Content classification
│   └── rubric.py           # Scoring rubric definitions
├── reporting/              # Report generation
│   ├── pdf_generator.py    # PDF report generation
│   ├── markdown_generator.py  # Markdown report generation
│   └── dashboard.py        # Dashboard utilities
├── config/                 # Configuration and settings
├── data/                   # Data storage
├── tests/                  # Unit and integration tests
├── scripts/                # Utility scripts
└── docs/                   # Documentation
```

## 🔌 Data Source Integration

### Brave Search
Always available, no API key required. Falls back to web scraping if Brave API unavailable.

**Configuration:**
```bash
export BRAVE_API_KEY="<your_key>"              # Optional API key
export BRAVE_API_AUTH="subscription-token"     # Auth method (default)
export BRAVE_REQUEST_INTERVAL=1.0              # Rate limiting (seconds)
export BRAVE_ALLOW_HTML_FALLBACK=1             # Allow HTML fallback when API unavailable
```

**Supported auth methods:**
- `subscription-token` (default) — `X-Subscription-Token` header
- `x-api-key` — `x-api-key` header
- `bearer` — `Authorization: Bearer` header
- `query-param` — API key as query parameter

**Example:**
```bash
python scripts/debug_brave.py --query "nike" --size 10
```

### Reddit
Requires API credentials for full integration.

**Configuration:**
```bash
export REDDIT_CLIENT_ID="<your_id>"
export REDDIT_CLIENT_SECRET="<your_secret>"
export REDDIT_USER_AGENT="truststack-analyzer/1.0"
```

**Usage:** Select "Reddit" as a data source in the web app or specify `--sources reddit` in CLI.

### YouTube
Requires YouTube Data API v3 key for video search and comment analysis.

**Configuration:**
```bash
export YOUTUBE_API_KEY="<your_key>"
export YOUTUBE_RATE_LIMIT=60  # requests per minute
```

**Example:**
```python
from ingestion.youtube_scraper import YouTubeScraper
yt = YouTubeScraper()
videos = yt.search_videos('nike', max_results=10)
normalized = yt.convert_videos_to_normalized(
    videos,
    brand_id='nike',
    run_id='analysis_001',
    include_comments=True
)
```

### Optional: Playwright for Enhanced Rendering
For JavaScript-heavy pages, install and enable Playwright:

```bash
pip install playwright
playwright install
export AR_USE_PLAYWRIGHT=1
```

## 🎛️ Configuration

### Environment Variables
Create a `.env` file in the project root:

```bash
# LLM Configuration
OPENAI_API_KEY=<your_key>
RECOMMENDATIONS_MODEL=gpt-4o-mini      # gpt-4o, gpt-4o-mini, gpt-3.5-turbo
LLM_MODEL=gpt-3.5-turbo               # For summary generation

# Data Sources
BRAVE_API_KEY=<optional>
REDDIT_CLIENT_ID=<optional>
REDDIT_CLIENT_SECRET=<optional>
YOUTUBE_API_KEY=<optional>

# AWS (for cloud storage)
AWS_ACCESS_KEY_ID=<optional>
AWS_SECRET_ACCESS_KEY=<optional>
AWS_REGION=us-east-1
```

See `.env.example` for a complete template.

## 💡 Model Selection Guide

The system supports different LLM models for recommendations:
- `gpt-4o` — Highest quality, slower, more expensive (for executive reports)
- `gpt-4o-mini` — **Recommended** for most use cases (balanced quality/cost)
- `gpt-3.5-turbo` — Fastest and cheapest (for development/testing)

See [MODEL_SELECTION_GUIDE.md](MODEL_SELECTION_GUIDE.md) for detailed guidance.

## 📈 Database
Results can be stored in AWS Athena with S3 backend for at-scale analysis. Configure in `config/settings.py`.

Results are also saved locally to `output/webapp_runs/` for easy access.

## 🧪 Development

### Setup
```bash
# Clone the repository
git clone https://github.com/andrewdeutsch/authenticity-ratio.git
cd authenticity-ratio

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env with your credentials
cp .env.example .env
# Edit .env with your API keys
```

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_scoring.py

# Run with verbose output
pytest -v
```

### Code Quality
```bash
# Format with Black
black .

# Lint with Flake8
flake8 .

# Type checking (if using mypy)
mypy .
```

## 📖 Output & Reports

### Web App Results
When you run an analysis through the web app, results are saved to:
```
output/webapp_runs/{brand_id}_{run_id}/
├── _run_data.json           # Complete run data (JSON)
├── ar_report_{id}.pdf       # PDF report with visualizations
└── ar_report_{id}.md        # Markdown report
```

### Report Contents
- **Dashboard**: Overall rating, distribution, dimension breakdown
- **Content Analysis**: Table of all analyzed items with individual scores
- **5D Breakdown**: Detailed scores for each dimension
- **Recommendations**: LLM-generated actionable insights
- **Authenticity Ratio**: Legacy AR metrics (Authentic/Suspect/Inauthentic counts)

### Rating Scale
- **80-100** (🟢 Excellent): High-quality, verified content with strong trust signals
- **60-79** (🟡 Good): Solid content with minor improvements needed
- **40-59** (🟠 Fair): Moderate quality requiring attention
- **0-39** (🔴 Poor): Low-quality content needing immediate review

## 🐛 Troubleshooting

### "No content collected from any source"
- Verify API credentials are set and valid
- Try different keywords that match your brand
- Check network connectivity
- For Brave: ensure search terms return results

### "Missing API credentials"
- Set required environment variables in `.env`
- Restart the web app after adding credentials
- Check sidebar status indicators for which sources are available

### "Analysis takes a long time"
- Reduce `max_items` parameter (start with 10-20)
- Use only necessary data sources
- Consider using faster LLM models (gpt-3.5-turbo)

### "Visualizations not displaying"
- Ensure plotly and pandas are installed: `pip install plotly pandas`
- Clear browser cache and restart app
- Check browser console for errors

### LLM Generation Failures
- Verify `OPENAI_API_KEY` is valid
- Check OpenAI account has sufficient quota
- System will fall back to structured recommendations if LLM fails
- Check logs for specific API errors

## 📚 Documentation

- [Webapp README](webapp/README.md) — Web application detailed guide
- [Model Selection Guide](MODEL_SELECTION_GUIDE.md) — LLM model comparison
- [AR Methodology](docs/AR_METHODOLOGY.md) — Detailed scoring methodology
- [Deployment Guide](docs/DEPLOYMENT.md) — Production deployment
- [API Reference](docs/API_REFERENCE.md) — Code API documentation

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run `pytest` and `black` to ensure code quality
6. Submit a pull request

## 📝 Version History

**Current Version**: Trust Stack Rating v2.0

**Key Evolution**:
- v1.0: Original Authenticity Ratio (AR) KPI with 5D framework
- v2.0: Trust Stack Rating with 5D dimensions + interactive web app

See git history for detailed changelog.

## 📄 License

This project is proprietary. See LICENSE file for details.

---

**Questions?** Check the [docs/](docs/) directory or open an issue on GitHub.


## 🧭 PR creation guidance

If you see a `failed to create PR` message when using the automation, make sure you have staged and committed your latest changes first. The `make_pr` helper only works on a clean branch with at least one new commit. See [docs/PR_GUIDE.md](docs/PR_GUIDE.md) for a short checklist and a note that tests should be run in this hosted workspace (the helper does not run them for you).
