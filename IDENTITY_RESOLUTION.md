# Identity Resolution & Verification Gates

The Signalpost challenge heavily penalizes wrong-company publications. A material wrong-company match contaminates the entire profile and prevents the run from becoming official.

## Candidate Generation vs. Publication Proof

```text
[ Brønnøysund Registry ]
           │
           ├─► Registry-listed Homepage URL ─────┐
           └─► Corporate Name & Address          │
                                                 ▼
[ Brave Search / External Discovery ] ──► [ Candidate URLs ]
                                                 │
                                                 ▼
                                     [ Identity Verification Gate ]
                                                 │
                                                 ├─► Verified (≥0.50) ──► Published
                                                 └─► Ambiguous (<0.50) ─► Discarded / Flagged Ambiguous
```

- **Candidate Discovery**: Search engines (Brave Search) and links generate candidate URLs. Candidates are NEVER claims.
- **Publication Proof**: A candidate must be fetched and independently corroborated by the exact legal entity before any fact derived from it is published.

## Scoring Confidence Model

| Signal | Weight | Notes |
| :--- | :--- | :--- |
| **Exact 9-Digit Org Number on Page** | **+0.70** | Gold standard proof (footer, terms, imprint, MVA registration). |
| **Domain Matches Registry Homepage** | **+0.35** | Registered domain matches Brønnøysund bulk entity record. |
| **Address Corroboration** | **+0.20** | Postal code + city, or street address found on contact page. |
| **Fuzzy Legal Name Similarity (≥0.85)** | **+0.20** | Corporate suffixes stripped; token set ratio comparison. |
| **Fuzzy Legal Name Similarity (≥0.65)** | **+0.10** | Moderate match. |

### Decision Gate
- **Verified ($\ge 0.50$)**: Allowed into the published profile.
- **Ambiguous ($< 0.50$)**: Flagged as `ambiguous` or `not_available`. Never published under the company profile.
