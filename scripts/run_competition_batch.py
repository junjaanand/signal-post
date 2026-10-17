#!/usr/bin/env python3
"""Signalpost competition batch runner — The single command entry point.

Usage:
  python scripts/run_competition_batch.py \
    --organisations input-companies.jsonl \
    --output out/envelopes.jsonl \
    --report out/run-report.json \
    --run-id official-run-01 \
    --concurrency 15
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add src/ to path so imports work cleanly from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from norway_company_agent.batch import run_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("signalpost")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Signalpost company research agent on a batch of Norwegian companies."
    )
    parser.add_argument(
        "--organisations",
        type=Path,
        required=True,
        help="Path to file with input organisation numbers (JSONL, JSON, or TXT).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("out/envelopes.jsonl"),
        help="Path to output terminal JSONL envelopes.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("out/run-report.json"),
        help="Path to output summary run report.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="run-001",
        help="Unique identifier for this batch run.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=15,
        help="Concurrent company workers.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional prior snapshot manifest for refresh diff comparison.",
    )
    parser.add_argument(
        "--bulk",
        type=Path,
        default=None,
        help="Optional local Brønnøysund bulk CSV snapshot path.",
    )
    parser.add_argument(
        "--profiles-output",
        type=Path,
        default=None,
        help="Optional path for raw profile cache.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help="Expected company count for validation.",
    )
    return parser.parse_args()


import re


def load_organisations(path: Path) -> list[str]:
    """Load org numbers from JSONL, JSON, CSV, or plain text list with BOM tolerance."""
    if not path.exists():
        logger.error(f"Input file not found: {path}")
        sys.exit(1)

    orgs: list[str] = []
    text = path.read_text(encoding="utf-8-sig").strip()

    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        org = item.get("organisation_number") or item.get("orgnr") or item.get("id")
                    else:
                        org = str(item)
                    if org:
                        clean = re.sub(r"\D", "", str(org))
                        if len(clean) == 9:
                            orgs.append(clean)
                return orgs
        except json.JSONDecodeError:
            pass

    # JSONL, CSV, or line-by-line text
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("{"):
            try:
                row = json.loads(line)
                org = row.get("organisation_number") or row.get("orgnr") or row.get("id")
                if org:
                    clean = re.sub(r"\D", "", str(org))
                    if len(clean) == 9:
                        orgs.append(clean)
            except json.JSONDecodeError:
                pass
        else:
            # Plain org number or comma/semicolon-separated row
            parts = re.split(r"[,;\t]", line)
            for part in parts:
                clean = re.sub(r"\D", "", part)
                if len(clean) == 9:
                    orgs.append(clean)
                    break

    return orgs


def main() -> None:
    args = parse_args()
    orgs = load_organisations(args.organisations)

    if not orgs:
        logger.error(f"No valid organisation numbers found in {args.organisations}")
        sys.exit(1)

    logger.info(f"Loaded {len(orgs)} companies to research (run_id: {args.run_id})")

    report = asyncio.run(
        run_batch(
            organisations=orgs,
            run_id=args.run_id,
            output_path=args.output,
            report_path=args.report,
            concurrency=args.concurrency,
            prior_manifest_path=args.manifest,
            bulk_path=args.bulk,
        )
    )

    print("\n" + "=" * 60)
    print("SIGNALPOST BATCH RUN COMPLETED")
    print("=" * 60)
    print(f"Companies Requested: {report['companies_requested']}")
    print(f"Companies Completed: {report['companies_completed']}")
    print(f"Available Claims:    {report['total_available_claims']}")
    print(f"Average Claims/Co:   {report['average_claims_per_company']}")
    print(f"Outbound Requests:   {report['total_outbound_requests']}")
    print(f"Total Runtime:       {report['total_runtime_seconds']}s")
    print(f"Output Envelope:     {report['output_file']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
