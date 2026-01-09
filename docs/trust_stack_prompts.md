# Trust Stack Scoring Prompts Location Guide

This document outlines the locations of the prompts used to score each dimension of the Trust Stack.

## Overview

The scoring logic is primarily contained within `scoring/scorer.py`, which uses a combination of **inline prompts** (defined directly in the method) and **imported prompts** (from the `prompts/` module).

| Dimension | Method/File | Prompt Type | Location |
|-----------|-------------|-------------|----------|
| **Provenance** | `ContentScorer._score_provenance` | Inline | `scoring/scorer.py` |
| **Verification** | `verification_manager.verify_content` | Imported | `prompts/verification.py` |
| **Transparency** | `ContentScorer._score_transparency` | Inline | `scoring/scorer.py` |
| **Coherence** | `ContentScorer._score_coherence` | Inline | `scoring/scorer.py` |
| **Resonance** | `ContentScorer._score_resonance` | Inline | `scoring/scorer.py` |

## Detailed Breakdown

### 1. Provenance
*   **File:** [`scoring/scorer.py`](../scoring/scorer.py)
*   **Method:** `_score_provenance`
*   **Description:** The prompt is defined inline within this method. It asks the LLM to evaluate if the content origin is clear and trustworthy based on title, body, author, source, and platform ID.

### 2. Verification
*   **File:** [`prompts/verification.py`](../prompts/verification.py)
*   **Used By:** `scoring/verification_manager.py` (which is called by `scoring/scorer.py`)
*   **Key components:**
    *   `CLAIM_EXTRACTION_SYSTEM` & `build_claim_extraction_prompt`: Used to extract verifiable claims from the content.
    *   `VERIFICATION_SYSTEM` & `build_verification_prompt`: Used to verify those claims against search results.

### 3. Transparency
*   **File:** [`scoring/scorer.py`](../scoring/scorer.py)
*   **Method:** `_score_transparency`
*   **Description:** The prompt is defined inline within this method. It asks the LLM to identify specific issues like missing privacy policies, unclear disclosures, or hidden agendas.

### 4. Coherence
*   **File:** [`scoring/scorer.py`](../scoring/scorer.py)
*   **Method:** `_score_coherence`
*   **Description:** The prompt is defined inline within this method. It utilizes brand guidelines (if available) and linguistic analysis (passive voice, readability) to score the consistency of voice and messaging.

### 5. Resonance
*   **File:** [`scoring/scorer.py`](../scoring/scorer.py)
*   **Method:** `_score_resonance`
*   **Description:** The prompt is defined inline within this method. It evaluates how well the content connects with the target audience. The final score is a weighted combination of this LLM score (70%) and engagement metrics (30%).

## Shared & Feedback Prompts

Additional prompts used for generating feedback and suggestions across dimensions are centralized:

*   **File:** [`prompts/scoring.py`](../prompts/scoring.py)
*   **Contents:**
    *   `SCORING_SYSTEM`: The system prompt used for scoring contexts.
    *   `build_feedback_prompt_low_score`: Generates the prompt for identifying specific issues when a score is low (< 0.9).
    *   `build_feedback_prompt_high_score`: Generates the prompt for suggesting optimizations when a score is high (>= 0.9).
