# App Architecture Overview

## Introduction
The Trust Stack Rating Web Application is a comprehensive tool designed to analyze and rate the authenticity of digital brands. It ingests content from various sources (Web, Reddit, YouTube), normalizes it, scores it across 5 dimensions of trust (Provenance, Resonance, Coherence, Transparency, Verification), and generates detailed reports.

## High-Level Architecture

The application follows a linear pipeline architecture orchestrated by a central analysis engine. The frontend is built with Streamlit, providing an interactive interface for users to trigger analyses and view results.

```mermaid
graph TD
    User[User] -->|Interacts| UI[Streamlit Web App]
    UI -->|Triggers| Engine[Analysis Engine]
    
    subgraph "Ingestion Layer"
        Engine -->|Calls| Search[Unified Search (Brave/Serper)]
        Engine -->|Calls| Reddit[Reddit Crawler]
        Engine -->|Calls| YouTube[YouTube Scraper]
        Search -->|Fetches| Pages[Web Pages]
    end
    
    subgraph "Processing Layer"
        Pages & Reddit & YouTube -->|Raw Content| Normalizer[Content Normalizer]
        Normalizer -->|NormalizedContent| Scorer[Scoring Pipeline]
    end
    
    subgraph "Scoring Layer"
        Scorer -->|Scores| Dimensions[5D Scorer]
        Dimensions -->|Classifies| Classifier[Content Classifier]
        Classifier -->|Refines| LLM[LLM Analysis]
    end
    
    subgraph "Reporting Layer"
        LLM -->|Final Scores| ReportGen[Report Generators]
        ReportGen -->|Generates| PDF[PDF Report]
        ReportGen -->|Generates| MD[Markdown Report]
    end
    
    ReportGen -->|Returns| UI
```

## Core Components

### 1. Frontend (Streamlit)
*   **Location**: `webapp/app.py`
*   **Role**: The entry point for the application. It handles user authentication (if any), input collection (brand ID, keywords, sources), and visualization of results.
*   **Key Features**:
    *   Interactive configuration of analysis parameters.
    *   Real-time progress tracking using `ProgressAnimator`.
    *   Visualization of Trust Stack scores using Plotly.
    *   Display of generated reports and downloadable assets.

### 2. Orchestration (Analysis Engine)
*   **Location**: `webapp/services/analysis_engine.py`
*   **Role**: The central coordinator of the analysis workflow. It ties together ingestion, normalization, scoring, and reporting.
*   **Key Responsibilities**:
    *   Initializing pipeline components.
    *   Managing the execution flow.
    *   Handling errors and logging.
    *   Persisting run data to disk (`output/webapp_runs/`).

### 3. Ingestion Layer
*   **Location**: `ingestion/`
*   **Role**: Responsible for gathering data from external sources.
*   **Key Modules**:
    *   **Unified Search** (`ingestion/search_unified.py`): Abstracts the underlying search provider (Brave or Serper), allowing for easy switching.
    *   **Page Fetcher** (`ingestion/page_fetcher.py`): Retrieves the full content of web pages found via search.
    *   **Platform Crawlers**: `reddit_crawler.py` and `youtube_scraper.py` handle platform-specific API interactions and scraping.

### 4. Normalization Layer
*   **Location**: `ingestion/normalizer.py`
*   **Role**: Standardizes raw content into a common format for analysis.
*   **Key Processes**:
    *   **Cleaning**: Removes HTML tags, excessive whitespace, and noise.
    *   **Metadata Enrichment**: Extracts additional context like modality (text/image/video), channel, and platform type.
    *   **Deduplication**: Uses SimHash to identify and remove duplicate content, preserving the version with higher engagement.
    *   **Validation**: Filters content based on length constraints.

### 5. Scoring Layer
*   **Location**: `scoring/`
*   **Role**: The core analytical engine.
*   **Key Modules**:
    *   **Pipeline** (`scoring/pipeline.py`): Manages the scoring workflow.
    *   **Scorer** (`scoring/scorer.py`): Calculates scores for the 5 Trust Dimensions:
        *   **Provenance**: Source origin and history.
        *   **Resonance**: Engagement and impact.
        *   **Coherence**: Consistency and alignment.
        *   **Transparency**: Openness and clarity.
        *   **Verification**: Factual accuracy and validation.
    *   **Classifier** (`scoring/classifier.py`): Categorizes content as Authentic, Suspect, or Inauthentic based on calculated scores.
    *   **LLM Client** (`scoring/llm.py`): Uses Large Language Models (e.g., GPT-4) for advanced semantic analysis and refinement of scores, particularly for "Suspect" items (Triage).

### 6. Reporting Layer
*   **Location**: `reporting/`
*   **Role**: Transforms analysis results into human-readable formats.
*   **Key Modules**:
    *   `trust_stack_report.py`: Generates the comprehensive Trust Stack Report.
    *   `pdf_generator.py`: Creates PDF versions of the report.
    *   `markdown_generator.py`: Creates Markdown versions of the report.

## Data Flow

1.  **Input**: User provides a Brand ID and keywords.
2.  **Discovery**: The system may use LLMs to discover brand domains (`webapp/services/brand_discovery.py`).
3.  **Collection**:
    *   Search queries are executed via `search_unified.py`.
    *   Web pages are fetched and parsed.
    *   Social media content is retrieved via specific crawlers.
4.  **Normalization**: Raw data is converted to `NormalizedContent` objects. Duplicates are removed.
5.  **Scoring**:
    *   Each `NormalizedContent` item is scored against the 5 dimensions.
    *   Rules and heuristics (Rubric) are applied.
    *   Items are classified (Authentic/Suspect/Inauthentic).
    *   Ambiguous items may be sent to an LLM for "Triage" and re-scoring.
6.  **Aggregation**: Individual scores are aggregated to calculate the overall **Authenticity Ratio** and **Trust Stack Rating**.
7.  **Output**: Final scores and reports are generated and displayed to the user.

## Key Data Models

*   **`NormalizedContent`** (`data/models.py`): The standard unit of content. Contains `title`, `body`, `meta` (metadata), `src` (source), and enhanced fields like `modality` and `channel`.
*   **`ContentScores`** (`data/models.py`): Stores the calculated scores for a content item, including the 5 dimension scores (`score_provenance`, etc.) and the final classification.
*   **`TrustStackRating`** (`data/models.py`): Represents the aggregated rating for a digital property or the brand as a whole.

## Configuration

*   **Settings**: `config/settings.py` contains global configuration defaults.
*   **Environment Variables**: API keys (e.g., `OPENAI_API_KEY`, `BRAVE_API_KEY`, `SERPER_API_KEY`) and provider selections (`SEARCH_PROVIDER`) are managed via `.env` files and environment variables.
