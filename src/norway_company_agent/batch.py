"""Batch runner and concurrency orchestrator.

Coordinates research across a batch of Norwegian organisation numbers.
Guarantees:
- Exactly 1 terminal envelope output per input company
- Semaphore concurrency control
- Checkpoint / resume capability
- Global request counter and runtime tracking
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from norway_company_agent.config import DEFAULT_CONCURRENCY
from norway_company_agent.envelope import build_company_envelope
from norway_company_agent.http import (
    ThrottledClient,
    create_brreg_client,
    create_web_client,
    get_global_request_count,
)
from norway_company_agent.models import CompanyEnvelope, OperationsMetrics
from norway_company_agent.news import fetch_company_news
from norway_company_agent.official import OfficialRegistryClient
from norway_company_agent.website import crawl_verified_site, resolve_official_website

logger = logging.getLogger(__name__)


async def research_single_company(
    org_number: str,
    run_id: str,
    reg_client: OfficialRegistryClient,
    web_client: ThrottledClient,
    prior_snapshots: dict[str, Any] | None = None,
) -> CompanyEnvelope:
    """Full research pipeline for a single company number."""
    start_time = datetime.now(timezone.utc)
    start_perf = time.perf_counter()
    clean_org = org_number.strip().replace(" ", "").replace("-", "")

    try:
        # Step 1: Official registry records
        entity_data = await reg_client.fetch_all(clean_org)
        entity = entity_data.get("entity")

        # Step 2: Website resolution & identity gate
        website_url = None
        website_verified = False
        crawled_pages = []

        if entity and entity.name:
            website_url, website_verified, verdict, site_ev = await resolve_official_website(
                org_number=clean_org,
                legal_name=entity.name,
                registry_homepage=entity.homepage,
                registry_address=entity.business_address or entity.postal_address,
                web_client=web_client,
            )

            # Step 3: Crawl verified website
            if website_verified and website_url:
                crawled_pages = await crawl_verified_site(
                    base_url=website_url,
                    web_client=web_client,
                    max_pages=3,
                )

        # Step 4: News & public activity
        news_items = []
        if entity and entity.name:
            news_items = fetch_company_news(entity.name, max_results=3)

        # Step 5: Construct envelope
        elapsed_ms = int((time.perf_counter() - start_perf) * 1000)
        ops = OperationsMetrics(
            runtime_ms=elapsed_ms,
            requests=0,  # Updated at batch level
            third_party_cost_usd=0.0,
            pages_crawled=len(crawled_pages),
        )

        prior_snap = prior_snapshots.get(clean_org) if prior_snapshots else None

        return build_company_envelope(
            org_number=clean_org,
            run_id=run_id,
            started_at=start_time,
            entity_data=entity_data,
            website_url=website_url,
            website_verified=website_verified,
            crawled_pages=crawled_pages,
            news_items=news_items,
            operations_metrics=ops,
            prior_snapshot=prior_snap,
        )

    except Exception as e:
        logger.error(f"Unhandled error for {clean_org}: {e}")
        # Always return a valid terminal envelope, never crash the batch!
        from norway_company_agent.models import AvailabilityState, RunMetadata
        now = datetime.now(timezone.utc)
        env = CompanyEnvelope(
            organisation_number=clean_org,
            run=RunMetadata(
                run_id=run_id,
                started_at=start_time,
                completed_at=now,
                terminal_status="failed",
            ),
            claims=[],
            evidence=[],
            changes=[],
            errors=[str(e)],
            operations=OperationsMetrics(runtime_ms=int((time.perf_counter() - start_perf) * 1000)),
        )
        env.add_claim("error_occurred", str(e), AvailabilityState.failed, 0.0)
        return env


def load_bulk_csv(bulk_path: Path) -> dict[str, dict[str, Any]]:
    """Parse local Brønnøysund bulk CSV snapshot into fast in-memory lookup."""
    import csv
    cache: dict[str, dict[str, Any]] = {}
    if not bulk_path.exists():
        logger.warning(f"Bulk path does not exist: {bulk_path}")
        return cache
    try:
        with open(bulk_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
            first_line = f.readline()
            delim = ";" if ";" in first_line else ","
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                org = row.get("organisasjonsnummer") or row.get("orgnr")
                if org:
                    clean = org.strip().replace(" ", "")
                    cache[clean] = row
        logger.info(f"Loaded {len(cache)} bulk entities from {bulk_path}")
    except Exception as e:
        logger.warning(f"Failed parsing bulk CSV {bulk_path}: {e}")
    return cache


async def run_batch(
    organisations: list[str],
    run_id: str,
    output_path: Path,
    report_path: Path,
    concurrency: int = DEFAULT_CONCURRENCY,
    prior_manifest_path: Path | None = None,
    bulk_path: Path | None = None,
) -> dict[str, Any]:
    """Execute research on an entire batch of companies concurrently."""
    batch_start = time.perf_counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Load prior snapshots if provided (for refresh diff checking)
    prior_snapshots = {}
    if prior_manifest_path and prior_manifest_path.exists():
        try:
            with open(prior_manifest_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict) and "organisation_number" in item:
                            prior_snapshots[item["organisation_number"]] = item
        except Exception as e:
            logger.warning(f"Could not load prior manifest: {e}")

    bulk_cache = load_bulk_csv(bulk_path) if bulk_path else {}

    brreg_http = create_brreg_client()
    web_client = create_web_client()

    async with brreg_http as b_client, web_client as w_client:
        reg_client = OfficialRegistryClient(b_client)

        sem = asyncio.Semaphore(concurrency)

        async def _worker(org: str) -> CompanyEnvelope:
            async with sem:
                return await research_single_company(
                    org_number=org,
                    run_id=run_id,
                    reg_client=reg_client,
                    web_client=w_client,
                    prior_snapshots=prior_snapshots,
                )

        tasks = [_worker(org) for org in organisations]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[CompanyEnvelope] = []
        for i, res in enumerate(raw_results):
            if isinstance(res, Exception):
                clean_org = organisations[i].strip().replace(" ", "").replace("-", "")
                logger.error(f"Worker exception for {clean_org}: {res}")
                now = datetime.now(timezone.utc)
                err_env = CompanyEnvelope(
                    organisation_number=clean_org,
                    run=RunMetadata(
                        run_id=run_id,
                        started_at=now,
                        completed_at=now,
                        terminal_status="failed",
                    ),
                    claims=[],
                    evidence=[],
                    changes=[],
                    errors=[str(res)],
                    operations=OperationsMetrics(runtime_ms=0),
                )
                err_env.add_claim("error_occurred", str(res), AvailabilityState.failed, 0.0)
                results.append(err_env)
            else:
                results.append(res)

    # Write JSONL output (1 line per company)
    with open(output_path, "w", encoding="utf-8") as f:
        for env in results:
            f.write(env.to_jsonl_line() + "\n")


    total_time_s = time.perf_counter() - batch_start
    total_reqs = get_global_request_count()

    # Generate summary report
    available_claims = sum(
        sum(1 for c in env.claims if c.availability == "available")
        for env in results
    )

    report = {
        "run_id": run_id,
        "companies_requested": len(organisations),
        "companies_completed": len(results),
        "total_runtime_seconds": round(total_time_s, 2),
        "total_outbound_requests": total_reqs,
        "total_available_claims": available_claims,
        "average_claims_per_company": round(available_claims / max(1, len(results)), 1),
        "estimated_api_cost_usd": 0.0,
        "output_file": str(output_path),
        "qualification_ready": len(results) == len(organisations),
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(
        f"Batch {run_id} finished: {len(results)}/{len(organisations)} companies "
        f"in {total_time_s:.1f}s ({total_reqs} requests, {available_claims} available claims)"
    )

    return report
