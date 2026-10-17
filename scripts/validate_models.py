"""Quick validation of all Pydantic models."""
from datetime import datetime, timezone
from norway_company_agent.models import (
    Evidence, AvailabilityState, Claim, ChangeRecord,
    RunMetadata, OperationsMetrics, CompanyEnvelope,
    RegistryEntity, RoleHolder, FinancialRecord, SubUnit, CompanyProfile,
)

# 1. Evidence.from_response
ev = Evidence.from_response("https://data.brreg.no/enhetsregisteret/api/enheter/123456789", b'{"name":"Test"}', "official_registry")
assert ev.id.startswith("ev-"), f"Bad id: {ev.id}"
assert len(ev.content_sha256) == 64, "SHA-256 must be 64 hex chars"
print(f"OK Evidence: {ev.id}, sha256={ev.content_sha256[:16]}...")

# 2. CompanyEnvelope + add_claim + to_jsonl_line
envelope = CompanyEnvelope(
    organisation_number="123456789",
    run=RunMetadata(run_id="run-test", started_at=datetime.now(timezone.utc)),
)
claim = envelope.add_claim("company_name", "Test AS", AvailabilityState.available, 1.0, ev)
assert len(envelope.claims) == 1
assert len(envelope.evidence) == 1
line = envelope.to_jsonl_line()
assert "\n" not in line, "JSONL must be single-line"
print(f"OK Envelope JSONL: {line[:100]}...")

# 3. RegistryEntity
entity = RegistryEntity(organisation_number="123456789", name="Test AS", legal_form="AS")
print(f"OK RegistryEntity: {entity.name}")

# 4. CompanyProfile
profile = CompanyProfile(entity=entity)
assert profile.roles == []
assert profile.financials == []
print(f"OK CompanyProfile: {profile.entity.name}")

# 5. FinancialRecord - None means not available, NOT zero
fin = FinancialRecord(year=2024, revenue_nok=1_000_000.0)
assert fin.net_income_nok is None, "Absent financials must be None, not zero"
print(f"OK FinancialRecord: year={fin.year}, revenue={fin.revenue_nok}")

print("\nAll models validated successfully!")
