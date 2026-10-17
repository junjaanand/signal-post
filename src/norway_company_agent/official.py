"""Brønnøysundregistrene official registry API client.

Fetches authoritative identity, roles, financials, subunits, and group structures
from the free, public Norwegian government APIs. No API key required.

APIs used:
- Enhetsregisteret (entities): https://data.brreg.no/enhetsregisteret/api/enheter/{org}
- Roles: https://data.brreg.no/enhetsregisteret/api/enheter/{org}/roller
- Normalized accounts: https://data.brreg.no/regnskapsregisteret/regnskap/{org}
- Filing years: https://data.brreg.no/regnskapsregisteret/regnskap/aarsregnskap/kopi/{org}/aar
- Subunits: https://data.brreg.no/enhetsregisteret/api/underenheter?overordnetEnhet={org}
- Group structure: https://data.brreg.no/enhetsregisteret/api/konsernstruktur/{org}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from norway_company_agent.config import (
    ENHETSREGISTERET_URL,
    REGNSKAPSREGISTERET_URL,
)
from norway_company_agent.http import ThrottledClient, create_brreg_client
from norway_company_agent.models import (
    Evidence,
    FinancialRecord,
    RegistryEntity,
    RoleHolder,
    SubUnit,
)

logger = logging.getLogger(__name__)


class OfficialRegistryClient:
    """Client for fetching data from Brønnøysundregistrene APIs."""

    def __init__(self, client: ThrottledClient | None = None) -> None:
        self.client = client or create_brreg_client()

    # -----------------------------------------------------------------------
    # Entity Identity
    # -----------------------------------------------------------------------

    async def fetch_entity(
        self, org_number: str
    ) -> tuple[RegistryEntity | None, Evidence | None]:
        """Fetch primary entity identity from Enhetsregisteret."""
        clean_org = org_number.strip().replace(" ", "").replace("-", "")
        url = f"{ENHETSREGISTERET_URL}/enheter/{clean_org}"

        try:
            resp = await self.client.get(url)
            if not resp or not resp.ok:
                if resp and resp.status_code in (404, 410):
                    logger.debug(f"{clean_org}: Entity not found (HTTP {resp.status_code})")
                return None, None

            data = resp.json()
            if not data or not isinstance(data, dict):
                return None, None

            evidence = Evidence.from_response(
                url=resp.final_url,
                content_bytes=resp.content,
                source_class="official_registry",
                claim_span=f"Navn: {data.get('navn', '')}, Org: {clean_org}",
                extraction_method="brreg_enhetsregisteret_api",
            )

            # Parse postal and business addresses
            postal = data.get("postadresse")
            business = data.get("forretningsadresse")

            municipality = None
            county = None
            if business:
                municipality = business.get("kommune")
                county = business.get("kommunenummer")
            elif postal:
                municipality = postal.get("kommune")
                county = postal.get("kommunenummer")

            # Parse latest accounts year safely
            last_accounts_year = None
            raw_year = data.get("sisteInnsendteAarsregnskap")
            if raw_year:
                try:
                    last_accounts_year = int(str(raw_year).strip()[:4])
                except (ValueError, TypeError):
                    pass

            entity = RegistryEntity(
                organisation_number=clean_org,
                name=data.get("navn", ""),
                legal_form=data.get("organisasjonsform", {}).get("kode"),
                legal_form_description=data.get("organisasjonsform", {}).get("beskrivelse"),
                registration_date=data.get("registreringsdatoEnhetsregisteret"),
                status="active" if not data.get("konkurs") and not data.get("underAvvikling") else "inactive",
                nace_code=data.get("naeringskode1", {}).get("kode"),
                nace_description=data.get("naeringskode1", {}).get("beskrivelse"),
                homepage=data.get("hjemmeside"),
                postal_address=postal,
                business_address=business,
                num_employees=data.get("antallAnsatte"),
                municipality=municipality,
                county=county,
                is_bankrupt=bool(data.get("konkurs", False)),
                is_under_liquidation=bool(data.get("underAvvikling", False)),
                last_annual_accounts_year=last_accounts_year,
            )

            return entity, evidence

        except Exception as e:
            logger.warning(f"{clean_org}: fetch_entity failed: {e}")
            return None, None

    # -----------------------------------------------------------------------
    # Roles & Board
    # -----------------------------------------------------------------------

    async def fetch_roles(
        self, org_number: str
    ) -> tuple[list[RoleHolder], Evidence | None]:
        """Fetch management and board roles from Enhetsregisteret.
        
        NOTE: Dates of birth are strictly discarded per competition rules.
        """
        clean_org = org_number.strip().replace(" ", "").replace("-", "")
        url = f"{ENHETSREGISTERET_URL}/enheter/{clean_org}/roller"

        try:
            resp = await self.client.get(url)
            if not resp or not resp.ok:
                return [], None

            data = resp.json()
            if not data or not isinstance(data, dict):
                return [], None

            evidence = Evidence.from_response(
                url=resp.final_url,
                content_bytes=resp.content,
                source_class="official_registry",
                claim_span=f"Roller for {clean_org}",
                extraction_method="brreg_roller_api",
            )

            roles: list[RoleHolder] = []
            rollegrupper = data.get("rollegrupper", [])

            for gruppe in rollegrupper:
                gruppe_roller = gruppe.get("roller", [])
                for r in gruppe_roller:
                    # Skip people who have departed
                    if r.get("fratraadt", False):
                        continue

                    # Role title
                    role_type = r.get("type", {}).get("beskrivelse") or r.get("type", {}).get("kode", "Ukjent")

                    # Person name (or entity name if corporate director)
                    person = r.get("person")
                    enhet = r.get("enhet")

                    name = None
                    if person and isinstance(person, dict):
                        person_navn = person.get("navn", {})
                        if isinstance(person_navn, dict):
                            fornavn = person_navn.get("fornavn", "")
                            etternavn = person_navn.get("etternavn", "")
                            name = f"{fornavn} {etternavn}".strip()
                    elif enhet and isinstance(enhet, dict):
                        raw_enhet_name = enhet.get("navn")
                        if isinstance(raw_enhet_name, list):
                            name = " ".join(str(n) for n in raw_enhet_name).strip()
                        else:
                            name = str(raw_enhet_name).strip() if raw_enhet_name else None

                    raw_from = r.get("valgtAv", {}).get("fraDato") if isinstance(r.get("valgtAv"), dict) else None
                    if raw_from is None:
                        raw_from = r.get("rekkefolge")

                    from_date_str = str(raw_from) if raw_from is not None else None

                    if name and role_type:
                        roles.append(
                            RoleHolder(
                                name=name,
                                role_type=role_type,
                                from_date=from_date_str,
                                to_date=None,
                            )
                        )

            return roles, evidence

        except Exception as e:
            logger.warning(f"{clean_org}: fetch_roles failed: {e}")
            return [], None

    # -----------------------------------------------------------------------
    # Financials (Regnskapsregisteret)
    # -----------------------------------------------------------------------

    async def fetch_financials(
        self, org_number: str
    ) -> tuple[list[FinancialRecord], Evidence | None]:
        """Fetch filed annual accounts from Regnskapsregisteret.
        
        CRITICAL: Never fabricate financial values. Return only what is filed.
        """
        clean_org = org_number.strip().replace(" ", "").replace("-", "")
        url = f"{REGNSKAPSREGISTERET_URL}/{clean_org}"

        try:
            resp = await self.client.get(url)
            if not resp or not resp.ok:
                return [], None

            data = resp.json()
            if not data:
                return [], None

            evidence = Evidence.from_response(
                url=resp.final_url,
                content_bytes=resp.content,
                source_class="official_accounts",
                claim_span=f"Årsregnskap for {clean_org}",
                extraction_method="brreg_regnskap_api",
            )

            # Response is typically a list of annual accounts, newest first
            records_raw = data if isinstance(data, list) else [data]
            financials: list[FinancialRecord] = []

            for rec in records_raw:
                if not isinstance(rec, dict):
                    continue

                # Determine year
                year = None
                periode = rec.get("regnskapsperiode", {})
                if isinstance(periode, dict):
                    til_dato = periode.get("tilDato", "")
                    if til_dato and len(til_dato) >= 4:
                        try:
                            year = int(til_dato[:4])
                        except ValueError:
                            pass

                if not year:
                    raw_year = rec.get("aarsregnskapAar") or rec.get("aar")
                    if raw_year:
                        try:
                            year = int(raw_year)
                        except (ValueError, TypeError):
                            pass

                if not year:
                    continue

                # Extract financial metrics deterministically
                revenue = self._extract_amount(rec, [
                    "resultatregnskapResultat.driftsresultat.driftsinntekter.sumDriftsinntekter",
                    "resultatregnskapResultat.driftsresultat.driftsinntekter.salgsinntekter",
                    "sumInntekter",
                    "salgsinntekter",
                    "driftsinntekter",
                ])

                operating_profit = self._extract_amount(rec, [
                    "resultatregnskapResultat.driftsresultat.driftsresultat",
                    "driftsresultat",
                    "resultatAvDrift",
                ])

                net_income = self._extract_amount(rec, [
                    "resultatregnskapResultat.ordinaertResultatForSkattekostnad",
                    "resultatregnskapResultat.aarsresultat",
                    "aarsresultat",
                    "resultatForSkatt",
                ])

                total_assets = self._extract_amount(rec, [
                    "balanseEiendeler.sumEiendeler",
                    "sumEiendeler",
                ])

                total_equity = self._extract_amount(rec, [
                    "balanseEgenkapitalGjeld.egenkapital.sumEgenkapital",
                    "sumEgenkapital",
                ])

                total_debt = self._extract_amount(rec, [
                    "balanseEgenkapitalGjeld.gjeld.sumGjeld",
                    "sumGjeld",
                ])

                # If debt not explicitly listed, calculate assets - equity
                if total_debt is None and total_assets is not None and total_equity is not None:
                    total_debt = max(0.0, total_assets - total_equity)

                num_employees = None
                raw_emp = rec.get("antallAnsatte")
                if raw_emp is not None:
                    try:
                        num_employees = int(raw_emp)
                    except (ValueError, TypeError):
                        pass

                financials.append(
                    FinancialRecord(
                        year=year,
                        revenue_nok=revenue,
                        operating_profit_nok=operating_profit,
                        net_income_nok=net_income,
                        total_assets_nok=total_assets,
                        total_equity_nok=total_equity,
                        total_debt_nok=total_debt,
                        num_employees=num_employees,
                        currency="NOK",
                    )
                )

            # Sort descending by year
            financials.sort(key=lambda f: f.year, reverse=True)
            return financials, evidence

        except Exception as e:
            logger.warning(f"{clean_org}: fetch_financials failed: {e}")
            return [], None

    def _extract_amount(self, data: dict, key_paths: list[str]) -> float | None:
        """Safely extract a float amount using dot-separated fallback key paths."""
        for path in key_paths:
            current: Any = data
            parts = path.split(".")
            found = True
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    found = False
                    break
            if found and current is not None:
                try:
                    val = float(current)
                    return val
                except (ValueError, TypeError):
                    pass
        return None

    # -----------------------------------------------------------------------
    # Subunits (Workplaces / Branches)
    # -----------------------------------------------------------------------

    async def fetch_subunits(
        self, org_number: str
    ) -> tuple[list[SubUnit], Evidence | None]:
        """Fetch registered workplaces/establishments from Enhetsregisteret."""
        clean_org = org_number.strip().replace(" ", "").replace("-", "")
        url = f"{ENHETSREGISTERET_URL}/underenheter?overordnetEnhet={clean_org}"

        try:
            resp = await self.client.get(url)
            if not resp or not resp.ok:
                return [], None

            data = resp.json()
            if not data or not isinstance(data, dict):
                return [], None

            underenheter = (
                data.get("_embedded", {}).get("underenheter", [])
                or data.get("underenheter", [])
            )

            if not underenheter:
                return [], None

            evidence = Evidence.from_response(
                url=resp.final_url,
                content_bytes=resp.content,
                source_class="official_registry",
                claim_span=f"{len(underenheter)} underenheter for {clean_org}",
                extraction_method="brreg_underenheter_api",
            )

            subunits: list[SubUnit] = []
            for u in underenheter:
                if not isinstance(u, dict):
                    continue
                subunits.append(
                    SubUnit(
                        organisation_number=u.get("organisasjonsnummer", ""),
                        name=u.get("navn", ""),
                        address=u.get("beliggenhetsadresse") or u.get("postadresse"),
                        nace_code=u.get("naeringskode1", {}).get("kode") if isinstance(u.get("naeringskode1"), dict) else None,
                        nace_description=u.get("naeringskode1", {}).get("beskrivelse") if isinstance(u.get("naeringskode1"), dict) else None,
                        num_employees=u.get("antallAnsatte"),
                    )
                )

            return subunits, evidence

        except Exception as e:
            logger.warning(f"{clean_org}: fetch_subunits failed: {e}")
            return [], None

    # -----------------------------------------------------------------------
    # Corporate Group Structure
    # -----------------------------------------------------------------------

    async def fetch_group_structure(
        self, org_number: str
    ) -> tuple[str | None, list[str], Evidence | None]:
        """Fetch parent and subsidiary corporate links."""
        clean_org = org_number.strip().replace(" ", "").replace("-", "")
        url = f"{ENHETSREGISTERET_URL}/konsernstruktur/{clean_org}"

        try:
            resp = await self.client.get(url)
            if not resp or not resp.ok:
                return None, [], None

            data = resp.json()
            if not data or not isinstance(data, dict):
                return None, [], None

            evidence = Evidence.from_response(
                url=resp.final_url,
                content_bytes=resp.content,
                source_class="official_registry",
                claim_span=f"Konsernstruktur for {clean_org}",
                extraction_method="brreg_konsernstruktur_api",
            )

            parent_org = None
            mor = data.get("morselskap")
            if mor and isinstance(mor, dict):
                parent_org = mor.get("organisasjonsnummer")

            subsidiary_orgs: list[str] = []
            døtre = data.get("datterselskaper", [])
            for d in døtre:
                if isinstance(d, dict) and d.get("organisasjonsnummer"):
                    subsidiary_orgs.append(d["organisasjonsnummer"])

            return parent_org, subsidiary_orgs, evidence

        except Exception as e:
            logger.warning(f"{clean_org}: fetch_group_structure failed: {e}")
            return None, [], None

    # -----------------------------------------------------------------------
    # Unified Fetch
    # -----------------------------------------------------------------------

    async def fetch_all(self, org_number: str) -> dict[str, Any]:
        """Fetch all official registry records concurrently."""
        clean_org = org_number.strip().replace(" ", "").replace("-", "")

        entity_task = self.fetch_entity(clean_org)
        roles_task = self.fetch_roles(clean_org)
        fin_task = self.fetch_financials(clean_org)
        sub_task = self.fetch_subunits(clean_org)
        group_task = self.fetch_group_structure(clean_org)

        (
            (entity, ev_entity),
            (roles, ev_roles),
            (financials, ev_fin),
            (subunits, ev_sub),
            (parent, subs, ev_group),
        ) = await asyncio.gather(
            entity_task, roles_task, fin_task, sub_task, group_task,
            return_exceptions=False,
        )

        evidence_list: list[Evidence] = []
        for ev in [ev_entity, ev_roles, ev_fin, ev_sub, ev_group]:
            if ev is not None:
                evidence_list.append(ev)

        return {
            "entity": entity,
            "roles": roles,
            "financials": financials,
            "subunits": subunits,
            "group_parent": parent,
            "group_subsidiaries": subs,
            "evidence_list": evidence_list,
        }
