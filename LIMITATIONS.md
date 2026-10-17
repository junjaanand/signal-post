# Limitations, Licences & Source Restrictions

## Data Rights & Licensing

### 1. Brønnøysundregistrene
- **Data Source**: Enhetsregisteret & Regnskapsregisteret
- **Licence**: Norwegian Licence for Open Government Data (NLOD 2.0)
- **Scope**: All public entity details, addresses, NACE codes, management roles, filed annual accounts, and subunit workplaces are open data.
- **Handling**: Personal birth dates are strictly excluded and discarded at ingestion.

### 2. Company Websites & Company-Owned Assets
- **Scope**: Public sitemaps, `/about`, `/contact`, `/careers`, and `/news` pages.
- **Access Pattern**: Deterministic static crawling via Trafilatura and extruct, strictly adhering to robots.txt conventions and conservative per-domain rate limits (1 req/s).
- **Attribution**: Only published when the company identity is verified through org number matching or multi-factor corroboration.

### 3. Google News RSS
- **Scope**: Public syndication feeds queried per company for recent announcements.
- **Rate Limit**: Conservative request spacing to prevent throttling.

### 4. Restricted Platforms
- **LinkedIn / Meta / Glassdoor / Indeed**: Direct automated scraping of these platforms is strictly prohibited by this agent. Job data is discovered directly from company-owned career portals (`/careers`, `/jobb`) rather than unofficial third-party scrapers.

## Known Edge Cases & Handling
- **Non-filing entities**: Sole proprietorships (ENK) and non-commercial associations (FLI) rarely file public annual accounts. The agent records financial fields as `not_available` rather than manufacturing numbers or substituting zero.
- **JavaScript Single-Page Apps**: Websites built entirely as client-side JavaScript applications without pre-rendered HTML fall back to metadata and official registry signals.
