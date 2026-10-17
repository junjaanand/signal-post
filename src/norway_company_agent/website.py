"""Website discovery, identity verification, and deterministic crawling.

Finds company websites, checks them against the identity gate, and crawls
priority paths (/about, /careers, /kontakt, /nyheter) to extract clean text
and structured metadata (JSON-LD, OpenGraph).
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin, urlparse

import extruct
import trafilatura
from w3lib.html import get_base_url

from norway_company_agent.config import BRAVE_API_KEY, BRAVE_SEARCH_URL
from norway_company_agent.http import ThrottledClient
from norway_company_agent.identity import (
    IdentityVerdict,
    extract_registered_domain,
    verify_website_identity,
)
from norway_company_agent.models import Evidence

logger = logging.getLogger(__name__)

# Key company pages to crawl for business facts, jobs, and leadership
PRIORITY_PATHS = [
    "/",
    "/om-oss",
    "/om",
    "/about",
    "/about-us",
    "/kontakt",
    "/kontakt-oss",
    "/contact",
    "/karriere",
    "/jobb",
    "/ledige-stillinger",
    "/careers",
    "/jobs",
    "/nyheter",
    "/aktuelt",
    "/presse",
    "/news",
    "/ledelse",
    "/styre",
    "/team",
    "/ansatte",
]

# Blacklisted directory/social domains that should never be treated as official websites
BLOCKED_DOMAINS = {
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "proff.no",
    "purehelp.no",
    "1881.no",
    "gulesider.no",
    "eniro.no",
    "wikipedia.org",
    "brreg.no",
    "kartverket.no",
    "finn.no",
}


async def resolve_official_website(
    org_number: str,
    legal_name: str,
    registry_homepage: str | None,
    registry_address: dict[str, Any] | None,
    web_client: ThrottledClient,
    brave_client: ThrottledClient | None = None,
) -> tuple[str | None, bool, IdentityVerdict | None, Evidence | None]:
    """Find and strictly verify the official website for a company.

    Returns: (verified_url, is_verified, verdict, evidence)
    """
    clean_org = org_number.strip().replace(" ", "").replace("-", "")

    # 1. Primary Strategy: Check registry-listed homepage from Brønnøysund
    if registry_homepage:
        candidate_url = registry_homepage.strip()
        if not candidate_url.startswith(("http://", "https://")):
            candidate_url = f"https://{candidate_url}"

        domain = extract_registered_domain(candidate_url)
        if domain and domain not in BLOCKED_DOMAINS:
            try:
                resp = await web_client.get(candidate_url)
                if resp and resp.ok:
                    page_text = extract_page_text(resp.text)
                    verdict = verify_website_identity(
                        org_number=clean_org,
                        legal_name=legal_name,
                        registry_address=registry_address,
                        page_text=page_text,
                        page_url=resp.final_url,
                        registry_homepage=registry_homepage,
                    )
                    if verdict.verified:
                        evidence = Evidence.from_response(
                            url=resp.final_url,
                            content_bytes=resp.content,
                            source_class="company_owned",
                            claim_span=f"Offisiell hjemmeside bekreftet: {resp.final_url}",
                            extraction_method="verified_registry_homepage",
                        )
                        return resp.final_url, True, verdict, evidence
            except Exception as e:
                logger.debug(f"{clean_org}: Registry website check failed ({candidate_url}): {e}")

    # 2. Secondary Strategy: Brave Search fallback (transient candidate discovery)
    if BRAVE_API_KEY and brave_client:
        try:
            query = f'"{legal_name}" site:.no'
            headers = {
                "X-Subscription-Token": BRAVE_API_KEY,
                "Accept": "application/json",
            }
            resp = await brave_client.get(
                BRAVE_SEARCH_URL,
                params={"q": query, "count": 5},
                headers=headers,
            )
            if resp and resp.ok:
                data = resp.json()
                results = data.get("web", {}).get("results", []) if isinstance(data, dict) else []
                for res in results[:3]:
                    candidate = res.get("url")
                    if not candidate:
                        continue
                    cand_domain = extract_registered_domain(candidate)
                    if not cand_domain or cand_domain in BLOCKED_DOMAINS:
                        continue

                    # Fetch and verify candidate directly
                    try:
                        cand_resp = await web_client.get(candidate)
                        if cand_resp and cand_resp.ok:
                            cand_text = extract_page_text(cand_resp.text)
                            verdict = verify_website_identity(
                                org_number=clean_org,
                                legal_name=legal_name,
                                registry_address=registry_address,
                                page_text=cand_text,
                                page_url=cand_resp.final_url,
                                registry_homepage=registry_homepage,
                            )
                            if verdict.verified:
                                evidence = Evidence.from_response(
                                    url=cand_resp.final_url,
                                    content_bytes=cand_resp.content,
                                    source_class="company_owned",
                                    claim_span=f"Brave Search bekreftet: {cand_resp.final_url}",
                                    extraction_method="brave_search_candidate_verified",
                                )
                                return cand_resp.final_url, True, verdict, evidence
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"{clean_org}: Brave search candidate discovery failed: {e}")

    return None, False, None, None


def extract_page_text(html: str) -> str:
    """Extract clean, boilerplate-free text using Trafilatura."""
    if not html:
        return ""
    try:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
            deduplicate=True,
        )
        return text or ""
    except Exception:
        return ""


def extract_structured_data(html: str, url: str) -> dict[str, Any]:
    """Extract embedded JSON-LD, OpenGraph, and Microdata using extruct."""
    if not html:
        return {}
    try:
        base_url = get_base_url(html, url)
        data = extruct.extract(
            html,
            base_url=base_url,
            syntaxes=["json-ld", "opengraph", "microdata"],
            errors="ignore",
        )
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug(f"Structured data extraction error for {url}: {e}")
        return {}


async def crawl_verified_site(
    base_url: str,
    web_client: ThrottledClient,
    max_pages: int = 4,
) -> list[dict[str, Any]]:
    """Crawl high-priority paths of a verified official company site.

    Returns a list of page dicts containing:
    - url: final resolved URL
    - path: path crawled
    - text: clean readable body text
    - structured_data: JSON-LD/OpenGraph dict
    - evidence: Evidence record
    """
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    parsed_base = urlparse(base_url)
    origin = f"{parsed_base.scheme}://{parsed_base.netloc}"

    for path in PRIORITY_PATHS:
        if len(results) >= max_pages:
            break

        target_url = urljoin(origin, path)
        norm_url = target_url.rstrip("/")
        if norm_url in seen_urls:
            continue
        seen_urls.add(norm_url)

        try:
            resp = await web_client.get(target_url)
            if not resp or not resp.ok:
                continue

            content_type = resp.headers.get("content-type", "").lower()
            if "html" not in content_type and "text" not in content_type:
                continue

            text = extract_page_text(resp.text)
            if not text or len(text) < 40:
                continue

            structured = extract_structured_data(resp.text, resp.final_url)
            evidence = Evidence.from_response(
                url=resp.final_url,
                content_bytes=resp.content,
                source_class="company_owned",
                claim_span=text[:300],
                extraction_method="company_site_crawler",
            )

            results.append({
                "url": resp.final_url,
                "path": path,
                "text": text,
                "structured_data": structured,
                "evidence": evidence,
            })
        except Exception as e:
            logger.debug(f"Failed to crawl {target_url}: {e}")
            continue

    return results
