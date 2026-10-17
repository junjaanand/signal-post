"""Google News RSS connector for discovering dated public activity.

Queries the free, public Google News RSS feed for Norwegian companies.
No API key required. Links are preserved with publication dates and titles.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import feedparser

from norway_company_agent.config import GOOGLE_NEWS_RSS_URL
from norway_company_agent.models import Evidence

logger = logging.getLogger(__name__)


def fetch_company_news(
    company_name: str,
    country: str = "NO",
    language: str = "no",
    max_results: int = 5,
    when_days: int = 180,
) -> list[dict[str, Any]]:
    """Fetch recent news articles about a company via Google News RSS.

    Returns a list of dicts with:
    - title: article headline
    - source: news publisher name
    - published_date: publication date string
    - url: article link
    - evidence: Evidence record
    """
    if not company_name or len(company_name.strip()) < 3:
        return []

    # Clean corporate suffixes that rarely appear in news headlines
    clean_name = company_name.strip()
    for suff in [" AS", " ASA", " ANS", " DA", " ENK", " NUF"]:
        if clean_name.endswith(suff):
            clean_name = clean_name[:-len(suff)].strip()

    try:
        query = f'"{clean_name}" when:{when_days}d'
        encoded = quote(query)
        rss_url = f"{GOOGLE_NEWS_RSS_URL}?q={encoded}&hl={language}&gl={country}&ceid={country}:{language}"

        feed = feedparser.parse(rss_url)
        articles: list[dict[str, Any]] = []

        for entry in feed.entries[:max_results]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")
            source_dict = entry.get("source", {})
            source_name = source_dict.get("title") if isinstance(source_dict, dict) else "Ukjent kilde"

            if not title or not link:
                continue

            evidence = Evidence.from_response(
                url=link,
                content_bytes=title.encode("utf-8"),
                source_class="external_permitted",
                claim_span=f"Overskrift: {title} ({source_name}, {published})",
                extraction_method="google_news_rss_connector",
            )

            articles.append({
                "title": title,
                "source": source_name,
                "published_date": published,
                "url": link,
                "evidence": evidence,
            })

        return articles

    except Exception as e:
        logger.debug(f"News RSS fetch failed for '{company_name}': {e}")
        return []
