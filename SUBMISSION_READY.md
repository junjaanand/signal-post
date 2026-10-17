# 🚀 SIGNALPOST SUBMISSION DOSSIER

**Participant**: Varun Anand Junja  
**Email**: `varunjunja5@gmail.com`  
**Submission Deadline**: October 17, 2026, 10:29 PM / 11:59 PM IST  
**GitHub Repository**: `https://github.com/junjaanand/signal-post`  
**Default Branch**: `main`

---

## 1. Unstop Submission Form Instructions

When submitting on Unstop under **"Signalpost project URL (for this challenge only)"**:
Paste the direct URL to the latest commit on the `main` branch:
```text
https://github.com/junjaanand/signal-post/commit/<LATEST_COMMIT_HASH>
```
*(On GitHub, open the repository and click the latest commit on `main` to copy the exact URL).*

---

## 2. Official Email Submission (`submit@builderr.ai`)

Send an email to **`submit@builderr.ai`** with the following template:

**To**: `submit@builderr.ai`  
**Subject**: `Signalpost Round 1 submission - SignalpostAgent-v1.0`

```text
Hi Builderr Team,

Here is our official submission for the Signalpost Company Intelligence Challenge:

- Agent name: SignalpostAgent-v1.0
- Repository URL: https://github.com/junjaanand/signal-post
- Exact commit hash: <INSERT_LATEST_COMMIT_HASH>
- 100-company smoke-test report URL: https://github.com/junjaanand/signal-post/blob/main/out/smoke-report.json
- One-command run instruction:

  uv run python scripts/run_competition_batch.py --organisations $INPUT_FILE --output $OUTPUT_FILE --report $REPORT_FILE --run-id $RUN_ID --concurrency 15

- Models / APIs / licences:
  - Runtime: Python 3.12+, uv package manager
  - Official APIs: Brønnøysundregistrene (Enhetsregisteret & Regnskapsregisteret) under NLOD 2.0
  - Text & Structured Data Extraction: Trafilatura (Apache-2.0) and extruct (BSD-3-Clause)
  - Public Activity: Google News RSS syndication feed
  - Optional Synthesis: Gemini 2.5 Flash / Brave Search API (transient discovery)
  - Code Licence: MIT
- Expected cost per official run: $0.00 base (maximum $4.30 with full external LLM synthesis per 1,000 companies)
- Contact for results: Varun Anand Junja (varunjunja5@gmail.com)

Best regards,
Varun Anand Junja
```

---

## 3. Local Verification & Reproducibility Summary

- **Offline Replay Evaluation**: Passed (1.0 Precision, 1.0 Recall, 100% evidence completeness) via `scripts/run_refresh_replay.py`.
- **Pydantic v2 Schema Compliance**: Passed via `scripts/validate_models.py`.
- **100-Company Live Smoke Test**: Completed (100/100 envelopes, 1,979 claims, 1,348 facts, $0.00 cost) via `out/smoke-report.json`.
- **Interactive Offline Dashboard**: Available at `out/showcase.html`.
