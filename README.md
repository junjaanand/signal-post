# Signalpost Company Intelligence Agent

An autonomous, evidence-grounded AI agent designed for the **Signalpost Challenge** hosted on [Builderr.ai](https://builderr.ai/challenges/signalpost).

The agent takes a Norwegian organisation number (*organisasjonsnummer*), queries authoritative official registries (Enhetsregisteret and Regnskapsregisteret), discovers and verifies the company's official online footprint, crawls priority web pages, collects recent dated public activity, and outputs a terminal JSONL envelope with cryptographic SHA-256 evidence for every published claim.

---

## Key Highlights

- **Authoritative Identity Anchoring**: Zero hallucinations on legal names, NACE industry codes, registered addresses, and corporate structures directly from the Brønnøysund Register Centre.
- **Strict Identity Gate**: Evaluates candidate websites using a multi-factor confidence model (exact org number on page, domain registry match, address corroboration). Never attributes facts to the wrong entity.
- **Deterministic Financial Extraction**: All financial metrics (revenue, operating profit, net income, assets, equity) are pulled from official filed accounts with exact reporting periods. Never fabricated.
- **Explicit Availability States**: Complies with the competition contract using `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous`, and `failed`. Absence is never converted to zero.
- **Idempotent Refresh**: Rerunning against unchanged data produces zero false changes, with earlier evidence preserved.
- **Resource Efficient**: Asynchronous pipeline using `httpx` and `asyncio.Semaphore` staying well under the 45-minute and 2,000-request limits per 1,000-company batch.

---

## Quickstart

### Prerequisites
- Python 3.12+
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `winget install astral-sh.uv`)

### 1. Install Dependencies
```bash
uv sync
```

### 2. Run the Agent (The One Evaluator Command)
```bash
uv run python scripts/run_competition_batch.py \
  --organisations tests/fixtures/batch-orgs-1.txt \
  --output out/envelopes.jsonl \
  --report out/run-report.json \
  --run-id smoke-001 \
  --concurrency 15
```

---

## Repository Structure

```text
├── README.md                    # Setup and evaluator run instructions
├── AGENT.md                     # Research policy and abstention rules
├── IDENTITY_RESOLUTION.md       # Candidate verification gates
├── DATA_SCHEMA.md               # Envelope, claim, and evidence schemas
├── REFRESH.md                   # Snapshot scheduling and diff semantics
├── LIMITATIONS.md               # Known gaps, licences, and source restrictions
├── OUTPUT_CONTRACT.md           # Minimal competition output contract
├── pyproject.toml               # Project manifest and dependencies
├── uv.lock                      # Pinned reproducible lockfile
├── select_entry_batch.py        # Batch selector from public universe
│
├── scripts/
│   ├── run_competition_batch.py # Official CLI entry point
│   └── run_refresh_replay.py    # Deterministic replay qualification runner
│
├── src/norway_company_agent/
│   ├── config.py                # Endpoints, rate limits, and model config
│   ├── models.py                # Pydantic v2 schemas (Envelope, Claim, Evidence)
│   ├── http.py                  # Async ThrottledClient with retry & telemetry
│   ├── official.py              # Brønnøysundregistrene API client
│   ├── identity.py              # Multi-signal entity verification gate
│   ├── website.py               # Website resolver, Trafilatura & extruct crawler
│   ├── news.py                  # Google News RSS public activity connector
│   ├── envelope.py              # Terminal envelope constructor
│   ├── refresh.py               # Idempotent diff engine
│   └── batch.py                 # Concurrency orchestrator & batch runner
│
└── tests/
    └── fixtures/                # Sample batches and snapshot replay files
```

---

## Declared Models & Third-Party APIs

| Service | Purpose | Declared Cost |
| :--- | :--- | :--- |
| **Brønnøysundregistrene APIs** | Official entity identity, roles, financials, subunits | \$0.00 (Free public API under NLOD 2.0) |
| **Trafilatura / extruct** | Local HTML text and JSON-LD structured data extraction | \$0.00 (Open-source, self-hosted) |
| **Google News RSS** | Free public activity and news headline discovery | \$0.00 (Public feed) |
| **Brave Search API** *(Optional)* | Website discovery fallback for missing registry URLs | ~\$0.25 per 100 companies |
| **Gemini 2.5 Flash** *(Optional)* | Synthesis summaries of verified company facts | ~\$0.18 per 100 companies |

**Expected Cost per Official 1,000-Company Run**: **\$0.00 - \$4.30** (Well within the \$10.00 limit).

---

## Contact

- **Participant**: Varun Anand Junja (`varunjunja5@gmail.com`)
- **Submission Date**: October 17, 2026
