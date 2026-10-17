#!/usr/bin/env python3
"""Fetch 100 active Norwegian companies directly from Enhetsregisteret API for the smoke test."""

import json
from pathlib import Path
import httpx

output_path = Path("tests/fixtures/smoke-100-companies.txt")
output_path.parent.mkdir(parents=True, exist_ok=True)

url = "https://data.brreg.no/enhetsregisteret/api/enheter?organisasjonsform=AS&size=100"
headers = {"Accept": "application/json"}

print(f"Fetching 100 active Norwegian companies from {url}...")
resp = httpx.get(url, headers=headers, timeout=30)
resp.raise_for_status()

data = resp.json()
enheter = data.get("_embedded", {}).get("enheter", [])

org_numbers = [e["organisasjonsnummer"] for e in enheter if "organisasjonsnummer" in e]

with open(output_path, "w", encoding="utf-8") as f:
    for org in org_numbers:
        f.write(f"{org}\n")

print(f"Successfully wrote {len(org_numbers)} company organisation numbers to {output_path}")
