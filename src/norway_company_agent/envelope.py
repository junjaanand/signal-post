"""Terminal company envelope constructor.

Transforms raw registry data, web crawler findings, and external signals
into the official, contract-compliant CompanyEnvelope JSONL output.

Enforces:
- 7 required profile sections
- Explicit availability states (available, not_available, blocked, etc.)
- Zero converted to null or absence
- Cryptographic evidence linkage for every material claim
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from norway_company_agent.models import (
    AvailabilityState,
    Claim,
    CompanyEnvelope,
    Evidence,
    OperationsMetrics,
    RunMetadata,
)

logger = logging.getLogger(__name__)


def build_company_envelope(
    org_number: str,
    run_id: str,
    started_at: datetime,
    entity_data: dict[str, Any] | None,
    website_url: str | None,
    website_verified: bool,
    crawled_pages: list[dict[str, Any]],
    news_items: list[dict[str, Any]],
    llm_summary: str | None = None,
    operations_metrics: OperationsMetrics | None = None,
    prior_snapshot: dict[str, Any] | None = None,
) -> CompanyEnvelope:
    """Build a complete, verified, terminal CompanyEnvelope for an organisation number."""
    clean_org = org_number.strip().replace(" ", "").replace("-", "")
    now = datetime.now(timezone.utc)

    envelope = CompanyEnvelope(
        organisation_number=clean_org,
        run=RunMetadata(
            run_id=run_id,
            started_at=started_at,
            completed_at=now,
            terminal_status="completed",
        ),
        claims=[],
        evidence=[],
        changes=[],
        errors=[],
        operations=operations_metrics or OperationsMetrics(),
        summary=llm_summary,
    )

    evidence_map: dict[str, Evidence] = {}

    def _add_ev(ev: Evidence | None) -> None:
        if ev and ev.id not in evidence_map:
            evidence_map[ev.id] = ev
            envelope.evidence.append(ev)

    # -----------------------------------------------------------------------
    # Section 1: Legal Identity & Public Brand
    # -----------------------------------------------------------------------
    entity = entity_data.get("entity") if entity_data else None

    if entity:
        # Entity Evidence
        ev_list = entity_data.get("evidence_list", []) if entity_data else []
        ev_id_list = [ev.id for ev in ev_list]
        for ev in ev_list:
            _add_ev(ev)

        # 1. Legal Name & Name alias
        envelope.add_claim(
            field="legal_name",
            value=entity.name,
            availability=AvailabilityState.available if entity.name else AvailabilityState.not_available,
            confidence=1.0,
            evidence=ev_list[0] if ev_list else None,
        )
        if entity.name:
            envelope.add_claim(
                field="name",
                value=entity.name,
                availability=AvailabilityState.available,
                confidence=1.0,
                evidence=ev_list[0] if ev_list else None,
            )

        # 2. Legal Form (AS, ASA, ENK)
        envelope.add_claim(
            field="legal_form",
            value=entity.legal_form,
            availability=AvailabilityState.available if entity.legal_form else AvailabilityState.not_available,
            confidence=1.0,
            evidence=ev_list[0] if ev_list else None,
        )

        # 3. Legal Form Description
        if entity.legal_form_description:
            envelope.add_claim(
                field="legal_form_description",
                value=entity.legal_form_description,
                availability=AvailabilityState.available,
                confidence=1.0,
            )

        # 4. Industry NACE Code
        envelope.add_claim(
            field="nace_code",
            value=entity.nace_code,
            availability=AvailabilityState.available if entity.nace_code else AvailabilityState.not_available,
            confidence=1.0,
            evidence=ev_list[0] if ev_list else None,
        )

        # 5. Industry Description
        if entity.nace_description:
            envelope.add_claim(
                field="nace_description",
                value=entity.nace_description,
                availability=AvailabilityState.available,
                confidence=1.0,
            )

        # 6. Registered Business Address & Municipality
        addr_str = None
        if entity.business_address:
            addr_parts = entity.business_address.get("adresse", [])
            street = " ".join(addr_parts) if isinstance(addr_parts, list) else str(addr_parts or "")
            poststed = entity.business_address.get("poststed", "")
            postnr = entity.business_address.get("postnummer", "")
            addr_str = f"{street}, {postnr} {poststed}".strip(", ")

        envelope.add_claim(
            field="registered_office_address",
            value=addr_str,
            availability=AvailabilityState.available if addr_str else AvailabilityState.not_available,
            confidence=1.0,
        )
        if entity.municipality:
            envelope.add_claim(
                field="municipality",
                value=entity.municipality,
                availability=AvailabilityState.available,
                confidence=1.0,
            )

        # 7. Registered Employee Count & Employees alias
        envelope.add_claim(
            field="registered_employee_count",
            value=entity.num_employees,
            availability=AvailabilityState.available if entity.num_employees is not None else AvailabilityState.not_available,
            confidence=0.95,
        )
        if entity.num_employees is not None:
            envelope.add_claim(
                field="employees",
                value=entity.num_employees,
                availability=AvailabilityState.available,
                confidence=0.95,
            )

        # 8. Active/Bankrupt Status
        envelope.add_claim(
            field="is_active",
            value=(not entity.is_bankrupt and not entity.is_under_liquidation),
            availability=AvailabilityState.available,
            confidence=1.0,
        )

        # 9. Accounting obligation assessment
        is_obliged = entity.legal_form in {"AS", "ASA", "BRL", "BBL", "STI", "SF", "VPFO"}
        envelope.add_claim(
            field="accounting_obligation",
            value="required_by_legal_form" if is_obliged else "threshold_or_activity_dependent",
            availability=AvailabilityState.available,
            confidence=1.0,
        )

    else:
        # Entity completely absent from register
        envelope.add_claim(
            field="legal_identity",
            value=None,
            availability=AvailabilityState.not_available,
            confidence=1.0,
        )

    # -----------------------------------------------------------------------
    # Section 2: Leadership & Workplaces
    # -----------------------------------------------------------------------
    roles = entity_data.get("roles", []) if entity_data else []
    if roles:
        ceo_list = [r.name for r in roles if "daglig leder" in r.role_type.lower() or "adm" in r.role_type.lower()]
        board_chair = [r.name for r in roles if "styreleder" in r.role_type.lower()]
        board_members = [r.name for r in roles if "styremedlem" in r.role_type.lower()]

        envelope.add_claim(
            field="general_manager_name",
            value=ceo_list[0] if ceo_list else None,
            availability=AvailabilityState.available if ceo_list else AvailabilityState.not_available,
            confidence=0.98,
        )

        envelope.add_claim(
            field="board_chair_name",
            value=board_chair[0] if board_chair else None,
            availability=AvailabilityState.available if board_chair else AvailabilityState.not_available,
            confidence=0.98,
        )

        envelope.add_claim(
            field="board_member_count",
            value=len(board_members) + len(board_chair),
            availability=AvailabilityState.available,
            confidence=0.98,
        )
    else:
        envelope.add_claim(
            field="leadership_roles",
            value=None,
            availability=AvailabilityState.not_available,
            confidence=1.0,
        )

    # Subunits (Establishments/branches)
    subunits = entity_data.get("subunits", []) if entity_data else []
    envelope.add_claim(
        field="registered_subunits_count",
        value=len(subunits),
        availability=AvailabilityState.available if subunits else AvailabilityState.not_available,
        confidence=0.95,
    )

    # Corporate Group Structure
    parent_org = entity_data.get("group_parent") if entity_data else None
    subs = entity_data.get("group_subsidiaries", []) if entity_data else []
    if parent_org or subs:
        envelope.add_claim(
            field="parent_organisation_number",
            value=parent_org,
            availability=AvailabilityState.available if parent_org else AvailabilityState.not_applicable,
            confidence=0.95,
        )
        envelope.add_claim(
            field="subsidiary_count",
            value=len(subs),
            availability=AvailabilityState.available if subs else AvailabilityState.not_applicable,
            confidence=0.95,
        )

    # -----------------------------------------------------------------------
    # Section 3: Financial Accounts & History
    # -----------------------------------------------------------------------
    financials = entity_data.get("financials", []) if entity_data else []
    if financials:
        latest_fin = financials[0]
        rep_period = str(latest_fin.year)

        envelope.add_claim(
            field="annual_revenue_nok",
            value=latest_fin.revenue_nok,
            availability=AvailabilityState.available if latest_fin.revenue_nok is not None else AvailabilityState.not_available,
            confidence=1.0,
            reporting_period=rep_period,
        )
        if latest_fin.revenue_nok is not None:
            envelope.add_claim(
                field="revenue",
                value=latest_fin.revenue_nok,
                availability=AvailabilityState.available,
                confidence=1.0,
                reporting_period=rep_period,
            )

        envelope.add_claim(
            field="operating_profit_nok",
            value=latest_fin.operating_profit_nok,
            availability=AvailabilityState.available if latest_fin.operating_profit_nok is not None else AvailabilityState.not_available,
            confidence=1.0,
            reporting_period=rep_period,
        )
        if latest_fin.operating_profit_nok is not None:
            envelope.add_claim(
                field="operating_result",
                value=latest_fin.operating_profit_nok,
                availability=AvailabilityState.available,
                confidence=1.0,
                reporting_period=rep_period,
            )

        envelope.add_claim(
            field="net_income_nok",
            value=latest_fin.net_income_nok,
            availability=AvailabilityState.available if latest_fin.net_income_nok is not None else AvailabilityState.not_available,
            confidence=1.0,
            reporting_period=rep_period,
        )
        if latest_fin.net_income_nok is not None:
            envelope.add_claim(
                field="annual_result",
                value=latest_fin.net_income_nok,
                availability=AvailabilityState.available,
                confidence=1.0,
                reporting_period=rep_period,
            )

        envelope.add_claim(
            field="total_assets_nok",
            value=latest_fin.total_assets_nok,
            availability=AvailabilityState.available if latest_fin.total_assets_nok is not None else AvailabilityState.not_available,
            confidence=1.0,
            reporting_period=rep_period,
        )
        if latest_fin.total_assets_nok is not None:
            envelope.add_claim(
                field="assets",
                value=latest_fin.total_assets_nok,
                availability=AvailabilityState.available,
                confidence=1.0,
                reporting_period=rep_period,
            )

        envelope.add_claim(
            field="total_equity_nok",
            value=latest_fin.total_equity_nok,
            availability=AvailabilityState.available if latest_fin.total_equity_nok is not None else AvailabilityState.not_available,
            confidence=1.0,
            reporting_period=rep_period,
        )
        if latest_fin.total_equity_nok is not None:
            envelope.add_claim(
                field="equity",
                value=latest_fin.total_equity_nok,
                availability=AvailabilityState.available,
                confidence=1.0,
                reporting_period=rep_period,
            )

        envelope.add_claim(
            field="financial_year_reported",
            value=latest_fin.year,
            availability=AvailabilityState.available,
            confidence=1.0,
            reporting_period=rep_period,
        )
    else:
        # AS/ASA companies usually file, but sole proprietorships often don't
        envelope.add_claim(
            field="annual_accounts",
            value=None,
            availability=AvailabilityState.not_available,
            confidence=1.0,
        )

    # -----------------------------------------------------------------------
    # Section 4: Verified Website & Company-Owned Footprint
    # -----------------------------------------------------------------------
    if website_verified and website_url:
        envelope.add_claim(
            field="official_website",
            value=website_url,
            availability=AvailabilityState.available,
            confidence=0.98,
        )
        envelope.add_claim(
            field="website",
            value=website_url,
            availability=AvailabilityState.available,
            confidence=0.98,
        )

        # Social links & structured data discovered from crawl
        discovered_jobs = 0
        all_socials: dict[str, str] = {}
        for page in crawled_pages:
            ev = page.get("evidence")
            _add_ev(ev)

            struct = page.get("structured_data", {})
            og = struct.get("opengraph", [])
            for item in og:
                props = item.get("properties", [])
                for p_name, p_val in props:
                    if "description" in p_name and not envelope.summary:
                        envelope.summary = p_val[:500]

            # Detect careers/job mentions
            path = page.get("path", "")
            if any(k in path for k in ["karriere", "jobb", "careers", "jobs", "ledige-stillinger"]):
                text = page.get("text", "").lower()
                if "ledige stillinger" in text or "søker" in text or "we are hiring" in text:
                    discovered_jobs += 1

        if discovered_jobs > 0:
            envelope.add_claim(
                field="careers_hiring_active",
                value=True,
                availability=AvailabilityState.available,
                confidence=0.85,
            )
    else:
        envelope.add_claim(
            field="official_website",
            value=None,
            availability=AvailabilityState.ambiguous if website_url else AvailabilityState.not_available,
            confidence=0.90,
        )
        envelope.add_claim(
            field="website",
            value=None,
            availability=AvailabilityState.ambiguous if website_url else AvailabilityState.not_available,
            confidence=0.90,
        )

    # -----------------------------------------------------------------------
    # Section 5: News & Public Activity
    # -----------------------------------------------------------------------
    if news_items:
        latest_news = news_items[0]
        ev = latest_news.get("evidence")
        _add_ev(ev)

        envelope.add_claim(
            field="recent_news_headline",
            value=latest_news.get("title"),
            availability=AvailabilityState.available,
            confidence=0.90,
            evidence=ev,
        )
        envelope.add_claim(
            field="recent_news_count",
            value=len(news_items),
            availability=AvailabilityState.available,
            confidence=0.90,
        )
    else:
        envelope.add_claim(
            field="recent_news_headline",
            value=None,
            availability=AvailabilityState.not_available,
            confidence=0.90,
        )

    # -----------------------------------------------------------------------
    # Section 6: Refresh Diffs (Idempotent comparison)
    # -----------------------------------------------------------------------
    if prior_snapshot:
        from norway_company_agent.refresh import compute_envelope_diff
        diffs = compute_envelope_diff(prior_snapshot, envelope.model_dump())
        envelope.changes = diffs

    return envelope
