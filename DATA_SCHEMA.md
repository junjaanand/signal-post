# Data Schema & Output Contract

Every input organisation number produces **exactly one terminal JSONL line** complying with the following schema.

## Terminal Envelope Schema

```json
{
  "organisation_number": "993578843",
  "run": {
    "run_id": "run-001",
    "started_at": "2026-10-17T10:50:00Z",
    "completed_at": "2026-10-17T10:50:05Z",
    "terminal_status": "completed"
  },
  "claims": [
    {
      "field": "legal_name",
      "value": "EQUINOR ASA",
      "availability": "available",
      "confidence": 1.0,
      "evidence_ids": ["ev-1a2b3c4d"],
      "reporting_period": null
    },
    {
      "field": "annual_revenue_nok",
      "value": 112345000000.0,
      "availability": "available",
      "confidence": 1.0,
      "evidence_ids": ["ev-5e6f7a8b"],
      "reporting_period": "2024"
    }
  ],
  "evidence": [
    {
      "id": "ev-1a2b3c4d",
      "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/993578843",
      "source_class": "official_registry",
      "retrieved_at": "2026-10-17T10:50:02Z",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "claim_span": "Navn: EQUINOR ASA, Org: 993578843",
      "extraction_method": "brreg_enhetsregisteret_api"
    }
  ],
  "changes": [],
  "errors": [],
  "operations": {
    "requests": 5,
    "runtime_ms": 3200,
    "third_party_cost_usd": 0.0,
    "pages_crawled": 3
  },
  "summary": "Equinor ASA is a leading energy company registered in Stavanger, Norway..."
}
```

## Availability States
- `available`: Discovered and verified.
- `not_available`: Verified absent / not found in queried sources.
- `blocked`: Remote source denied access (HTTP 403, 429).
- `not_applicable`: Field is irrelevant for this legal entity type (e.g., parent org on independent company).
- `ambiguous`: Candidate found but failed identity verification threshold.
- `failed`: Pipeline exception or fatal parse error on this entity.
