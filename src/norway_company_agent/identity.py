"""Entity identity verification gate.

This module determines whether a discovered website, domain, or profile belongs to
the exact legal entity identified by the organisation number.

CRITICAL RULES:
- Zero wrong-company publications! A wrong-company fact blocks qualification.
- It is ALWAYS better to return 'ambiguous' or 'not_available' than to publish
  under the wrong company.
- Search rank and snippets are candidate generators, NEVER claim evidence.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from rapidfuzz import fuzz
import tldextract


def normalize_org_number(org: str) -> str:
    """Strip spaces, dashes, and non-digit characters from an org number."""
    return re.sub(r"\D", "", org)


def org_number_on_page(org_number: str, page_text: str) -> bool:
    """Check if the exact 9-digit org number appears on the page.

    Handles common Norwegian formatting:
    - 923 609 016
    - 923609016
    - NO 923 609 016 MVA
    - Org.nr: 923609016
    - Organisasjonsnummer: 923 609 016
    """
    clean = normalize_org_number(org_number)
    if len(clean) != 9:
        return False

    # 1. Direct unspaced match in text with whitespace/dashes removed
    cleaned_page = re.sub(r"[\s\-.]", "", page_text)
    if clean in cleaned_page:
        return True

    # 2. Norwegian 3-3-3 spaced format: '923 609 016'
    spaced = f"{clean[:3]} {clean[3:6]} {clean[6:9]}"
    if spaced in page_text:
        return True

    # 3. Regex with optional prefixes and separators
    pattern = rf"(?:org(?:\.?\s*nr)?|organisasjonsnummer|mva)[\s:.]*(?:no\s*)?{clean[:3]}[\s.-]?{clean[3:6]}[\s.-]?{clean[6:9]}"
    if re.search(pattern, page_text, re.IGNORECASE):
        return True

    return False


def name_similarity(legal_name: str, target_name: str) -> float:
    """Compute normalized fuzzy similarity between legal name and discovered name.
    
    Strips corporate suffixes (AS, ASA, ENK, etc.) before comparing.
    Returns 0.0 to 1.0.
    """
    if not legal_name or not target_name:
        return 0.0

    suffixes = [
        "as", "asa", "ans", "da", "enk", "sa", "nuf", "ba",
        "holding", "group", "norge", "norway", "ltd", "inc", "gmbh"
    ]

    def _clean(n: str) -> str:
        s = n.strip().lower()
        # Remove punctuation
        s = re.sub(r"[^\w\s]", "", s)
        words = s.split()
        filtered = [w for w in words if w not in suffixes]
        return " ".join(filtered) if filtered else s

    c_legal = _clean(legal_name)
    c_target = _clean(target_name)

    if not c_legal or not c_target:
        return 0.0

    # Token set ratio handles word reordering and partial matches well
    return fuzz.token_set_ratio(c_legal, c_target) / 100.0


def address_matches_page(
    registry_address: dict[str, Any] | None, page_text: str
) -> bool:
    """Check if official registered address details appear on the webpage."""
    if not registry_address or not page_text:
        return False

    page_lower = page_text.lower()
    matches = 0

    # Check 4-digit Norwegian postal code
    postnummer = str(registry_address.get("postnummer", "")).strip()
    if postnummer and len(postnummer) == 4 and postnummer in page_text:
        matches += 1

    # Check postal place (city/town)
    poststed = str(registry_address.get("poststed", "")).strip().lower()
    if poststed and len(poststed) > 2 and poststed in page_lower:
        matches += 1

    # Check street address line
    adresse_val = registry_address.get("adresse")
    if isinstance(adresse_val, list):
        street_str = " ".join(str(a) for a in adresse_val).strip().lower()
    else:
        street_str = str(adresse_val or "").strip().lower()

    if street_str and len(street_str) > 4:
        # Check if prominent street word + number appears
        words = [w for w in street_str.split() if len(w) > 3]
        for w in words:
            if w in page_lower:
                matches += 1
                break

    # Postal code + city, or street + city = strong match
    return matches >= 2


def extract_registered_domain(url: str) -> str:
    """Extract the clean registered domain (e.g., 'equinor.com') using tldextract."""
    if not url:
        return ""
    ext = tldextract.extract(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    return ""


class IdentityVerdict:
    """Decision outcome of the identity verification gate."""

    def __init__(
        self,
        verified: bool,
        confidence: float,
        signals: list[str],
        rejection_reason: str | None = None,
    ) -> None:
        self.verified = verified
        self.confidence = confidence
        self.signals = signals
        self.rejection_reason = rejection_reason

    def __repr__(self) -> str:
        status = "VERIFIED" if self.verified else "REJECTED"
        return f"IdentityVerdict({status}, conf={self.confidence:.2f}, signals={self.signals})"


def verify_website_identity(
    org_number: str,
    legal_name: str,
    registry_address: dict[str, Any] | None,
    page_text: str,
    page_url: str,
    registry_homepage: str | None = None,
) -> IdentityVerdict:
    """Evaluate whether page content proves ownership by the queried entity.

    Strict rules:
    - Gold standard: 9-digit org number explicitly present on page -> Verified.
    - Silver standard: Domain matches Brønnøysund registry homepage AND name/address corroborated -> Verified.
    - Bronze standard: Strong name similarity (>0.85) AND verified address match -> Verified.
    - Otherwise: Rejected (classified as ambiguous or not_available).
    """
    signals: list[str] = []
    confidence = 0.0

    # 1. Check for exact organisation number on page
    if org_number_on_page(org_number, page_text):
        signals.append("exact_org_number_on_page")
        confidence += 0.70

    # 2. Check if domain matches Brønnøysund registry-listed homepage
    if registry_homepage:
        reg_domain = extract_registered_domain(registry_homepage)
        page_domain = extract_registered_domain(page_url)
        if reg_domain and page_domain and reg_domain == page_domain:
            signals.append(f"domain_matches_registry:{reg_domain}")
            confidence += 0.35

    # 3. Check legal name similarity in page header/footer/title
    sample_text = page_text[:3000] + " " + page_text[-2000:]
    sim = name_similarity(legal_name, sample_text)
    if sim >= 0.85:
        signals.append(f"high_name_similarity:{sim:.2f}")
        confidence += 0.20
    elif sim >= 0.65:
        signals.append(f"moderate_name_similarity:{sim:.2f}")
        confidence += 0.10

    # 4. Check address corroboration
    if address_matches_page(registry_address, page_text):
        signals.append("address_corroborated")
        confidence += 0.20

    # Verification threshold: requires confidence >= 0.50
    # Examples that pass:
    # - Org number found (0.70) -> Pass
    # - Registry domain (0.35) + high name (0.20) = 0.55 -> Pass
    # - Registry domain (0.35) + address (0.20) = 0.55 -> Pass
    # - High name (0.20) + address (0.20) = 0.40 -> Fail (conservative, avoids similarly named local businesses)
    verified = confidence >= 0.50

    rejection = None
    if not verified:
        rejection = (
            f"Insufficient identity confidence ({confidence:.2f} < 0.50). "
            f"Signals observed: {signals or ['none']}"
        )

    return IdentityVerdict(
        verified=verified,
        confidence=min(1.0, confidence),
        signals=signals,
        rejection_reason=rejection,
    )
