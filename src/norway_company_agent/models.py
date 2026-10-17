"""Core Pydantic data models for the Signalpost agent.

Every data structure used in the system is defined here. The terminal output
is a CompanyEnvelope serialised as a single JSONL line per organisation number.

Design principles:
- Never fabricate financial values — only use data from official APIs.
- Never attribute facts to the wrong company — strict identity verification.
- Explicit availability states instead of nulls or zeros.
- Every claim backed by Evidence with source_url, retrieved_at, content_sha256.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class Evidence(BaseModel):
    """An immutable record of where a piece of information came from.

    Every claim in the envelope MUST reference at least one Evidence by id.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str = Field(default_factory=lambda: f"ev-{uuid4().hex[:8]}")
    source_url: str
    source_class: Literal[
        "official_registry",
        "official_accounts",
        "company_owned",
        "external_permitted",
        "search_discovery",
    ]
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_sha256: str
    claim_span: str | None = None
    extraction_method: str | None = None

    # -- factory ----------------------------------------------------------

    @classmethod
    def from_response(
        cls,
        url: str,
        content_bytes: bytes,
        source_class: Literal[
            "official_registry",
            "official_accounts",
            "company_owned",
            "external_permitted",
            "search_discovery",
        ],
        *,
        claim_span: str | None = None,
        extraction_method: str | None = None,
    ) -> Evidence:
        """Create an Evidence record from raw HTTP response bytes.

        Automatically computes the SHA-256 content hash and stamps the
        current UTC time.
        """
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        return cls(
            source_url=url,
            source_class=source_class,
            content_sha256=content_hash,
            claim_span=claim_span,
            extraction_method=extraction_method,
        )


# ---------------------------------------------------------------------------
# Availability & Claims
# ---------------------------------------------------------------------------

class AvailabilityState(str, Enum):
    """Explicit availability states — never represent absence as zero."""

    available = "available"
    not_available = "not_available"
    blocked = "blocked"
    not_applicable = "not_applicable"
    ambiguous = "ambiguous"
    failed = "failed"


class Claim(BaseModel):
    """A single factual claim about a company, backed by evidence."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    field: str  # e.g. 'official_website', 'ceo_name', 'revenue_nok'
    value: Any = None
    availability: AvailabilityState
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    reporting_period: str | None = None  # e.g. '2024' for financial year


# ---------------------------------------------------------------------------
# Change tracking
# ---------------------------------------------------------------------------

class ChangeRecord(BaseModel):
    """Tracks a delta between the previous and current value of a field.

    Used to make refresh idempotent — same data ⇒ no false changes.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    field: str
    previous_value: Any = None
    current_value: Any = None
    change_type: Literal["added", "updated", "removed", "unchanged"]
    first_observed: datetime
    last_observed: datetime
    evidence_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Run metadata & operations metrics
# ---------------------------------------------------------------------------

class RunMetadata(BaseModel):
    """Metadata about a single agent run."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    run_id: str
    started_at: datetime
    completed_at: datetime | None = None
    terminal_status: Literal["completed", "partial", "failed"] = "completed"


class OperationsMetrics(BaseModel):
    """Resource-consumption counters for a single run."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    requests: int = 0
    runtime_ms: int = 0
    third_party_cost_usd: float = 0.0
    pages_crawled: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0


# ---------------------------------------------------------------------------
# Terminal output envelope
# ---------------------------------------------------------------------------

class CompanyEnvelope(BaseModel):
    """THE terminal output — one per organisation number, serialised as JSONL.

    Competition rule: every input org number MUST produce exactly one envelope.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    organisation_number: str
    run: RunMetadata
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    changes: list[ChangeRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    operations: OperationsMetrics = Field(default_factory=OperationsMetrics)
    summary: str | None = None

    # -- helpers ----------------------------------------------------------

    def add_claim(
        self,
        field: str,
        value: Any,
        availability: AvailabilityState,
        confidence: float,
        evidence: Evidence | list[Evidence] | None = None,
        *,
        reporting_period: str | None = None,
    ) -> Claim:
        """Add a claim and its supporting evidence in one call.

        If the Evidence objects are not yet in ``self.evidence`` they are
        appended automatically (de-duplicated by id).
        """
        if evidence is None:
            ev_list: list[Evidence] = []
        elif isinstance(evidence, Evidence):
            ev_list = [evidence]
        else:
            ev_list = list(evidence)

        # De-duplicate evidence
        existing_ids = {e.id for e in self.evidence}
        for ev in ev_list:
            if ev.id not in existing_ids:
                self.evidence.append(ev)
                existing_ids.add(ev.id)

        claim = Claim(
            field=field,
            value=value,
            availability=availability,
            confidence=confidence,
            evidence_ids=[ev.id for ev in ev_list],
            reporting_period=reporting_period,
        )
        self.claims.append(claim)
        return claim

    def to_jsonl_line(self) -> str:
        """Serialise the envelope as a single-line JSON string (no trailing newline)."""
        return self.model_dump_json()


# ---------------------------------------------------------------------------
# Registry data models (Brønnøysund / Enhetsregisteret)
# ---------------------------------------------------------------------------

class RegistryEntity(BaseModel):
    """Parsed company record from the Brønnøysund Register Centre API."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    organisation_number: str
    name: str
    legal_form: str | None = None  # e.g. 'AS', 'ASA', 'ENK'
    legal_form_description: str | None = None
    registration_date: str | None = None
    status: str | None = None
    nace_code: str | None = None
    nace_description: str | None = None
    homepage: str | None = None  # registered website
    postal_address: dict | None = None
    business_address: dict | None = None
    num_employees: int | None = None
    municipality: str | None = None
    county: str | None = None
    is_bankrupt: bool = False
    is_under_liquidation: bool = False
    last_annual_accounts_year: int | None = None


class RoleHolder(BaseModel):
    """A person holding a role in a company (e.g. CEO, board member)."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    name: str
    role_type: str  # e.g. 'Daglig leder', 'Styreleder', 'Styremedlem'
    from_date: str | None = None
    to_date: str | None = None


class FinancialRecord(BaseModel):
    """Annual financial figures for a company.

    Values are sourced exclusively from official accounts — never fabricated.
    None means the figure was not available, NOT zero.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    year: int
    revenue_nok: float | None = None
    operating_profit_nok: float | None = None
    net_income_nok: float | None = None
    total_assets_nok: float | None = None
    total_equity_nok: float | None = None
    total_debt_nok: float | None = None
    num_employees: int | None = None
    currency: str = "NOK"


class SubUnit(BaseModel):
    """A sub-unit (virksomhet / underenhet) of a parent organisation."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    organisation_number: str
    name: str
    address: dict | None = None
    nace_code: str | None = None
    nace_description: str | None = None
    num_employees: int | None = None


# ---------------------------------------------------------------------------
# Internal aggregated profile
# ---------------------------------------------------------------------------

class CompanyProfile(BaseModel):
    """Internal aggregated data before envelope generation.

    This model collects all discovered information about a company from
    every source, before it is flattened into claims and evidence.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    entity: RegistryEntity
    roles: list[RoleHolder] = Field(default_factory=list)
    financials: list[FinancialRecord] = Field(default_factory=list)
    subunits: list[SubUnit] = Field(default_factory=list)
    group_parent: str | None = None
    group_subsidiaries: list[str] = Field(default_factory=list)
    verified_website: str | None = None
    website_verified: bool = False
    crawled_pages: dict[str, str] = Field(default_factory=dict)  # url -> extracted text
    structured_data: dict = Field(default_factory=dict)  # JSON-LD, OG data
    news_items: list[dict] = Field(default_factory=list)
    job_listings: list[dict] = Field(default_factory=list)
