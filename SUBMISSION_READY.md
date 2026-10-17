# 🚀 SIGNALPOST SUBMISSION DOSSIER

**Participant**: Varun Anand Junja  
**Email**: `varunjunja5@gmail.com`  
**Submission Deadline**: October 17, 2026, 10:29 PM / 11:59 PM IST  
**Pinned Git Commit Hash**: `a79ea38140d9f5616ad8eb8b474f4fc65d2803ba`  

---

## 1. Unstop Submission Form

When submitting on Unstop under **"Signalpost project URL (for this challenge only)"**, paste:
```text
https://github.com/<your-github-username>/signalpost/commit/a79ea38140d9f5616ad8eb8b474f4fc65d2803ba
```
*(Replace `<your-github-username>` with your actual GitHub handle once you push the repository).*

---

## 2. Official Email Submission (`submit@builderr.ai`)

Copy and send this email:

**To**: `submit@builderr.ai`  
**Subject**: `Signalpost Round 1 submission - SignalpostAgent-v1.0`

```text
Hi Builderr Team,

Here is our official submission for the Signalpost Company Intelligence Challenge:

- Agent name: SignalpostAgent-v1.0
- Repository URL: https://github.com/<your-github-username>/signalpost
- Exact commit hash: a79ea38140d9f5616ad8eb8b474f4fc65d2803ba
- 100-company smoke-test result / report URL: https://github.com/<your-github-username>/signalpost/blob/a79ea38140d9f5616ad8eb8b474f4fc65d2803ba/out/smoke-report.json
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

## 3. GitHub Push Commands

To push this project to your GitHub account:

```bash
# 1. Create a new repository on GitHub named 'signalpost' (public)
# 2. In your terminal inside d:\signalpost:
git remote add origin https://github.com/<your-github-username>/signalpost.git
git branch -M main
git push -u origin main
```
