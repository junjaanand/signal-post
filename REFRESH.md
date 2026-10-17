# Refresh Architecture & Diff Semantics

## Refresh Policy
Signalpost evaluations test idempotence and change tracking:
1. Re-running the agent against unchanged sources must produce zero new change events and zero duplicate records.
2. Observed differences must be emitted as typed `ChangeRecord` objects with timestamps and evidence pointers.
3. Earlier snapshots and evidence must be preserved, never overwritten.

## ChangeRecord Schema

```json
{
  "field": "annual_revenue_nok",
  "previous_value": 105000000000.0,
  "current_value": 112345000000.0,
  "change_type": "updated",
  "first_observed": "2026-10-17T09:00:00Z",
  "last_observed": "2026-10-17T09:00:00Z",
  "evidence_ids": ["ev-9a8b7c6d"]
}
```

### Change Types
- `added`: A field that was previously unavailable now has a verified value.
- `updated`: A field value has changed beyond numerical rounding noise ($> 10^{-4}$).
- `removed`: A previously available field is no longer present or valid.
- `unchanged`: Value is identical across snapshots (filtered out from changes list).
