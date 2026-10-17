# Signalpost Research Agent Policy

## Research Objective
The agent's mission is to construct decision-useful, verifiable company intelligence profiles for Norwegian corporate entities from public and permitted sources.

## Core Tenets

### 1. Evidence Supremacy
Every published claim must point to a specific, durable `Evidence` object. The evidence encapsulates:
- The immutable source URL
- The UTC retrieval timestamp
- The cryptographic SHA-256 hash of the response content
- The exact character span or selector corroborating the fact

### 2. Abstention over Hallucination
- When an entity's website cannot be verified with sufficient confidence ($\ge 0.50$), the website claim MUST be published as `ambiguous` or `not_available`.
- Unofficial scrapers and search engine ranking snippets are treated exclusively as candidate discovery signals; they are never valid proof for a factual claim.
- Missing values are explicitly recorded using the `not_available` availability state and are never converted to zero or empty strings.

### 3. Financial Integrity
- All revenue, operating result, net income, asset, and equity values are parsed strictly from official regulatory filings via the Norwegian Regnskapsregisteret API.
- Language models are never used to generate, estimate, or modify financial numbers.
