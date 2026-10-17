"""
Signalpost Agent — centralised configuration.

All tunables, API base URLs, and environment-sourced secrets live here so
every other module can ``from norway_company_agent.config import …``.
"""

from __future__ import annotations

import os

# ── Brønnøysund Register Centre ──────────────────────────────────────────────
BRREG_BASE_URL: str = "https://data.brreg.no"
ENHETSREGISTERET_URL: str = f"{BRREG_BASE_URL}/enhetsregisteret/api"
REGNSKAPSREGISTERET_URL: str = f"{BRREG_BASE_URL}/regnskapsregisteret/regnskap"

# ── External search / news ───────────────────────────────────────────────────
BRAVE_SEARCH_URL: str = "https://api.search.brave.com/res/v1/web/search"
GOOGLE_NEWS_RSS_URL: str = "https://news.google.com/rss/search"

# ── Concurrency & performance ────────────────────────────────────────────────
DEFAULT_CONCURRENCY: int = 20
DEFAULT_TIMEOUT: int = 30  # seconds

# ── Batch limits (competition rules) ─────────────────────────────────────────
MAX_REQUESTS_PER_BATCH: int = 2_000
MAX_COST_PER_BATCH: float = 10.0

# ── Rate limits ──────────────────────────────────────────────────────────────
BRREG_RATE_LIMIT_PER_MIN: int = 25  # conservative to avoid 429s

# ── Identity ─────────────────────────────────────────────────────────────────
USER_AGENT: str = (
    "SignalpostAgent/1.0 "
    "(company-research-challenge; +https://builderr.ai/challenges/signalpost)"
)

# ── LLM ──────────────────────────────────────────────────────────────────────
GEMINI_MODEL: str = "gemini-2.5-flash"

# ── API keys (loaded from environment) ───────────────────────────────────────
BRAVE_API_KEY: str = os.environ.get("BRAVE_API_KEY", "")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
