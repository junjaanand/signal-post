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
