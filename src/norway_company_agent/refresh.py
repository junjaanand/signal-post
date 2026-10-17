"""Refresh diff engine — idempotent before/after change tracking.

CRITICAL RULES:
- Re-running the exact same data must produce ZERO changes (idempotence).
- Changed values must emit typed ChangeRecord entries.
- Earlier evidence must be preserved, never overwritten.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from norway_company_agent.models import ChangeRecord

logger = logging.getLogger(__name__)


def compute_envelope_diff(
    prior_envelope: dict[str, Any],
    current_envelope: dict[str, Any],
) -> list[ChangeRecord]:
    """Compare a previous envelope snapshot with current envelope.

    Emits typed ChangeRecord instances for material changes.
    Guaranteed idempotent: identical snapshots produce an empty change list.
    """
    changes: list[ChangeRecord] = []
    now = datetime.now(timezone.utc)

    # Index claims by field name
    prior_claims = {
        c.get("field"): c
        for c in prior_envelope.get("claims", [])
        if isinstance(c, dict) and c.get("field")
    }
    current_claims = {
        c.get("field"): c
        for c in current_envelope.get("claims", [])
        if isinstance(c, dict) and c.get("field")
    }

    all_fields = set(prior_claims.keys()) | set(current_claims.keys())

    for field in sorted(all_fields):
        p_claim = prior_claims.get(field)
        c_claim = current_claims.get(field)

        # 1. New field added
        if not p_claim and c_claim:
            c_val = c_claim.get("value")
            if c_val is not None:
                changes.append(
                    ChangeRecord(
                        field=field,
                        previous_value=None,
                        current_value=c_val,
                        change_type="added",
                        first_observed=now,
                        last_observed=now,
                        evidence_ids=c_claim.get("evidence_ids", []),
                    )
                )

        # 2. Existing field removed
        elif p_claim and not c_claim:
            p_val = p_claim.get("value")
            if p_val is not None:
                changes.append(
                    ChangeRecord(
                        field=field,
                        previous_value=p_val,
                        current_value=None,
                        change_type="removed",
                        first_observed=now,
                        last_observed=now,
                        evidence_ids=p_claim.get("evidence_ids", []),
                    )
                )

        # 3. Field value changed
        elif p_claim and c_claim:
            p_val = p_claim.get("value")
            c_val = c_claim.get("value")

            # Check for value divergence (ignoring float rounding noise)
            if _values_differ(p_val, c_val):
                changes.append(
                    ChangeRecord(
                        field=field,
                        previous_value=p_val,
                        current_value=c_val,
                        change_type="updated",
                        first_observed=now,
                        last_observed=now,
                        evidence_ids=c_claim.get("evidence_ids", []),
                    )
                )

    return changes


def _values_differ(val_a: Any, val_b: Any) -> bool:
    """Compare two claim values with tolerance for numerical equivalence."""
    if val_a is None and val_b is None:
        return False
    if val_a is None or val_b is None:
        return True

    # Numeric comparison with small epsilon
    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
        return abs(float(val_a) - float(val_b)) > 1e-4

    # String comparison (normalized)
    if isinstance(val_a, str) and isinstance(val_b, str):
        return val_a.strip() != val_b.strip()

    # Generic fallback
    return val_a != val_b


# ---------------------------------------------------------------------------
# Evaluator Replay Dataset Diff Harness
# ---------------------------------------------------------------------------

TRACKED_FIELDS: dict[str, tuple[str, ...]] = {
    "registry.name": ("name",),
    "registry.legal_form": ("legal_form",),
    "registry.employees": ("employees",),
    "registry.municipality": ("municipality",),
    "registry.website": ("website",),
    "registry.latest_submitted_accounts": ("latest_submitted_accounts",),
    "financials.records": ("evidence", "financials", "value", "records"),
    "financial_history.years": ("evidence", "financial_history", "value", "years"),
    "roles.roles": ("evidence", "roles", "value", "roles"),
    "locations.locations": ("evidence", "locations", "value", "locations"),
    "website.title": ("evidence", "website", "value", "title"),
    "website.description": ("evidence", "website", "value", "description"),
    "website.social_links": ("evidence", "website", "value", "social_links"),
}


def _read_field_path(value: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _evidence_for(profile: dict[str, Any], field: str) -> dict[str, Any]:
    module = field.split(".", 1)[0]
    records = profile.get("evidence", {})
    if module == "registry":
        return records.get("registry_live") or records.get("registry", {})
    return records.get(module, {})


def diff_profile(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    old_org = previous.get("organisation_number")
    new_org = current.get("organisation_number")
    if not old_org or old_org != new_org:
        raise ValueError("Refresh comparison requires the same exact organisation number")
    changes = []
    for field, path in TRACKED_FIELDS.items():
        old_value = _read_field_path(previous, path)
        new_value = _read_field_path(current, path)
        if old_value == new_value:
            continue
        record = _evidence_for(current, field)
        previous_record = _evidence_for(previous, field)
        changes.append({
            "organisation_number": new_org,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "source_url": record.get("source_url"),
            "retrieved_at": record.get("retrieved_at"),
            "effective_at": record.get("effective_at") or record.get("as_of"),
            "source_class": record.get("source_class") or record.get("source_type"),
            "old_content_sha256": previous_record.get("content_sha256"),
            "new_content_sha256": record.get("content_sha256"),
            "status": record.get("status"),
        })
    return changes


def diff_datasets(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    old_by_org = {row["organisation_number"]: row for row in previous}
    new_by_org = {row["organisation_number"]: row for row in current}
    if set(old_by_org) != set(new_by_org):
        raise ValueError("Refresh datasets must have identical organisation-number membership")
    return [
        change
        for org in sorted(old_by_org)
        for change in diff_profile(old_by_org[org], new_by_org[org])
    ]

