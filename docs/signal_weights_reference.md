# Signal Weights Reference (v5.1)

This document shows the weight of each signal per dimension, based on `scoring/config/trust_signals.yml`.

---

## Dimension Weights (Overall Score)

| Dimension      | Weight |
|----------------|--------|
| Provenance     | 25%    |
| Verification   | 25%    |
| Coherence      | 20%    |
| Resonance      | 15%    |
| Transparency   | 15%    |

---

## Provenance (25% of overall)

| Signal ID             | Label                       | Weight | Requirement  | Knockout |
|-----------------------|-----------------------------|--------|--------------|----------|
| prov_author_bylines   | Clear Authorship/Bylines    | 20%    | Core         | No       |
| prov_metadata_c2pa    | C2PA/Content Credentials    | 20%    | Amplifier    | No       |
| prov_source_clarity   | Source Attribution          | 20%    | Core         | Yes      |
| prov_date_freshness   | Content Freshness           | 20%    | Amplifier    | No       |
| prov_domain_trust     | Domain Trust & History      | 20%    | Core         | Yes      |

**Total: 100%**

---

## Resonance (15% of overall)

| Signal ID             | Label                    | Weight | Requirement  | Knockout |
|-----------------------|--------------------------|--------|--------------|----------|
| res_cultural_fit      | Cultural/Audience Fit    | 40%    | Core         | No       |
| res_personalization   | Personalization Signals  | 30%    | Amplifier    | No       |
| res_engagement_metrics| Organic Engagement       | 30%    | Amplifier    | No       |
| res_readability       | Readability              | 30%    | Core         | No       |

**Total: 130%** *(Note: weights exceed 100% - normalized during aggregation)*

---

## Coherence (20% of overall)

| Signal ID             | Label                      | Weight | Requirement  | Knockout |
|-----------------------|----------------------------|--------|--------------|----------|
| coh_voice_consistency | Voice Consistency          | 40%    | Core         | No       |
| coh_design_patterns   | Visual/Design Coherence    | 30%    | Core         | No       |
| coh_technical_health  | Technical Health           | 30%    | Amplifier    | No       |
| coh_cross_channel     | Cross-Channel Alignment    | 30%    | Core         | Yes      |

**Total: 130%** *(Note: weights exceed 100% - normalized during aggregation)*

---

## Transparency (15% of overall)

| Signal ID             | Label                  | Weight | Requirement  | Knockout |
|-----------------------|------------------------|--------|--------------|----------|
| trans_disclosures     | Clear Disclosures      | 40%    | Core         | No       |
| trans_ai_labeling     | AI Usage Disclosure    | 30%    | Core         | Yes      |
| trans_contact_info    | Contact/Business Info  | 30%    | Amplifier    | No       |

**Total: 100%**

---

## Verification (25% of overall)

| Signal ID             | Label                  | Weight | Requirement  | Knockout |
|-----------------------|------------------------|--------|--------------|----------|
| ver_fact_accuracy     | Factual Accuracy       | 40%    | Core         | No       |
| ver_trust_badges      | Trust Badges/Certs     | 30%    | Amplifier    | No       |
| ver_social_proof      | External Social Proof  | 30%    | Amplifier    | No       |

**Total: 100%**

---

## Key Definitions

- **Core**: Required signals that must be present for a high score
- **Amplifier**: Optional signals that boost the score when present
- **Knockout**: If true and score falls below threshold (0.30), the dimension score is capped at 4.0/10

---

## Scoring Caps (from rubric.json)

| Condition                | Cap Applied |
|--------------------------|-------------|
| Core signal missing      | 6.0/10      |
| Knockout signal fails    | 4.0/10      |
| Coverage < 50%           | 6.0/10      |
| Coverage 50-80%          | 8.0/10      |
