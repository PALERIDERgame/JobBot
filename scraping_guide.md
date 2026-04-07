# The complete guide to scraping and API-accessing job boards for a Python bot

**JobSpy, a free open-source Python library, is the single most impactful tool for this project** — it scrapes Indeed, LinkedIn, Glassdoor, Google Jobs, and ZipRecruiter simultaneously with one function call, returning structured DataFrames. Combined with the free USAJobs API for federal positions, free Greenhouse/Lever ATS APIs for direct employer access, and targeted scraping of NYC CityJobs, this stack covers all three target categories (legal/paralegal/DA, political/government/campaign, and general professional) with minimal cost. Below is the full ranked breakdown across APIs, scrapeable sites, niche boards, and aggregator tools — all validated for Python 3.11+ on Windows with Playwright and requests.

---

## Ranked API list: 15 APIs from essential to marginal

The job API landscape shifted dramatically in 2024–2025. **Indeed's Publisher API is fully deprecated** with no new keys issued. **ZipRecruiter's search API terminated on April 1, 2025.** GitHub Jobs shut down in 2021. What remains divides into three tiers.

### Tier 1 — Essential (free, high-value, directly relevant)

**1. USAJobs API** — The only official U.S. federal government jobs API. Completely free. Returns **50+ structured fields** per listing including salary ranges, security clearance, telework eligibility, and full qualifications. Supports filtering by location (NYC), occupation series (legal/paralegal 0900-series), and agency (DOJ, federal courts). Registration requires submitting a form at developer.usajobs.gov; approval takes 1–3 days. Auth uses API key + email in headers. Up to **500 results per page, 10,000 per query**. Indispensable for federal legal and government jobs.

**2. Greenhouse Job Board API** — Free, no authentication required for GET requests. Endpoint: `boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true`. Returns job title, full HTML description, location, department, and direct apply URL. No documented rate limits on reads. Many law firms, DA offices, advocacy organizations (ACLU, political consulting firms), and legal nonprofits use Greenhouse. Build a target list of employer slugs and poll daily. **Can also submit applications programmatically** via POST with Basic Auth.

**3. Lever Postings API** — Free, no authentication for reads. Endpoint: `api.lever.co/v0/postings/{company_name}?mode=json`. Returns title, description, salary range, department, location, workplace type, and apply URL. Rate limit: **10 requests/second**. Many mid-market law firms, political organizations, and advocacy groups use Lever. Same strategy as Greenhouse: compile company slugs, poll regularly.

**4. JSearch on RapidAPI** — The best single comprehensive job search API. Sources from Google for Jobs, which indexes Indeed, LinkedIn, Glassdoor, ZipRecruiter, USAJobs, and hundreds more. Returns **40+ data fields** per listing including required experience, education, skills, benefits, and estimated salaries. Free tier provides ~100–500 requests/month (credit card required on RapidAPI). Paid Basic tier runs **$15–50/month**. Excellent for legal/government/political coverage since Google Jobs indexes government boards and niche sites.

**5. Adzuna API** — Well-maintained aggregator covering 12 countries including the US. Free tier is generous for personal projects (commercial use requires written consent after 14-day trial). Returns salary min/max, full descriptions, company, and redirect URLs. Registration is instant at developer.adzuna.com. Also provides **salary histograms and historical salary data** by region — useful for compensation research. Max 50 results per page.

### Tier 2 — Useful supplements (free, narrower scope)

**6. SerpApi Google Jobs** — Paid API that scrapes Google Jobs results into structured JSON. 250 free searches/month. Developer plan: $75/month for 5,000 searches. Official Python SDK available. Since Google Jobs aggregates from virtually every job board, this is effectively a meta-aggregator. Alternative: **DataForSEO** offers Google Jobs SERP at ~$0.0006/search (cheapest option).

**7. Jooble API** — Free aggregator covering 71+ countries with strong US coverage. Uses POST method (not GET): `POST jooble.org/api/{api_key}`. Returns title, company, location, salary, description, and URL. Instant API key upon registration. Good breadth but less structured than JSearch.

**8. The Muse API** — Free. 3,600 requests/hour with registered key. Returns curated job listings from well-known companies with company profiles, photos, and culture data. Filter by level (Entry/Mid/Senior), location, and category. Lower volume than aggregators but higher-quality employer data.

**9. Careerjet API** — Free affiliate/publisher program covering 90+ countries. Official Python library on PyPI (`careerjet-api`). Returns title, company, salary, description excerpt, and tracking URL. Requires providing end-user IP/user-agent (designed for server-side rendering). Affiliate model means URLs are click-tracking redirects.

### Tier 3 — Niche or limited (free but narrow coverage)

**10. Jobicy API** — Free, no auth, no key. Endpoint: `jobicy.com/api/v2/remote-jobs`. Returns full HTML descriptions, salary ranges, and job level. Limited to **remote jobs only** with max 50–100 listings. Cannot poll more than once per hour. 6-hour publication delay.

**11. Remotive API** — Free at `remotive.com/api/remote-jobs`. Remote tech jobs only. Max **2 requests/minute**, recommended 4x/day max. 24-hour delay on free tier. Good for remote legal-tech or remote policy roles but minimal government coverage.

**12. Arbeitnow API** — Free, no auth. Endpoint: `arbeitnow.com/api/job-board-api`. 100 results per page with pagination. **Europe-focused** (primarily Germany). Minimal US coverage. Only useful for remote/worldwide positions.

**13. FindWork API** — Free with token auth. 60 requests/minute. Tech/developer focused, aggregates from Hacker News Who's Hiring, RemoteOK, and similar. ~444 new jobs per month. Not relevant for legal/political roles.

### Unavailable or impractical

- **Indeed Publisher API** — Deprecated. No new keys. Remaining Indeed APIs require formal ATS partnership agreements.
- **ZipRecruiter Search API** — Terminated April 1, 2025. Remaining APIs are ATS-integration-only.
- **LinkUp API** — Enterprise-only, aimed at hedge funds and HR analytics firms. Custom pricing requires sales contact.
- **Reed API** — Free and well-documented but **UK jobs only**. No US coverage.
- **GitHub Jobs API** — Shut down August 2021.
- **Coresignal, JobsPikr, TheirStack** — Enterprise-priced data feeds ($500+/month). Not practical for individual developers.

---

## Ranked scraping list: major sites from easiest to hardest

The scraping landscape in 2026 is defined by one critical tool: **JobSpy** (`pip install python-jobspy`), which handles Indeed, LinkedIn, Glassdoor, Google Jobs, and ZipRecruiter simultaneously through a single Python call. For sites JobSpy doesn't cover, Playwright with stealth plugins is the fallback.

### 1. SimplyHired — Anti-bot: 2/5 (easiest major board)

Basic rate limiting and IP blocking only. No Cloudflare or DataDome. **No login required.** Full descriptions accessible on individual listing pages. ~40–50% of listings show salary estimates. Recruiter emails rarely visible. **`requests` + BeautifulSoup works** without headless browsers. Clean URL pagination: `simplyhired.com/search?q=paralegal&l=New+York&pn=2`. Same parent company as Indeed (Recruit Holdings) so job overlap is significant. Proxies recommended only for high-volume scraping. Best starting point for testing scraping logic.

### 2. ZipRecruiter — Anti-bot: 3/5

Cloudflare bot management blocks default Playwright/Selenium. No login required. **~50–60% of listings show salary** (better than most competitors). Job descriptions accessible on individual pages. Recruiter email rarely visible. JobSpy handles ZipRecruiter natively. For custom scraping: Playwright + stealth plugin + residential proxies needed. URL-based pagination: `/jobs-search/2?search=...&location=...`. Moderate difficulty — JavaScript rendering required.

### 3. Indeed — Anti-bot: 4/5 (but JobSpy circumvents it)

**Cloudflare Turnstile**, TLS fingerprinting, IP reputation scoring, and behavioral analysis. Standard Playwright gets blocked within minutes. No login required. Search results show snippets only; full descriptions require clicking through, but job data is embedded in JavaScript variables (`window._initialData`) extractable via regex. **~30–40% show salary.** Recruiter emails almost never visible. **JobSpy is the recommended approach** — its maintainers report Indeed has "no rate limiting" via their method. For DIY: use `httpx` with realistic headers, extract embedded JSON from HTML, rotate residential proxies. Python's default `requests` library gets flagged by TLS fingerprinting — use `curl_cffi` or `tls-client` instead. Pagination via `&start=10,20,30...` with ~1,000 result cap.

### 4. Glassdoor — Anti-bot: 4/5

Cloudflare protection, CAPTCHAs, and aggressive login modal overlays after 1–2 page views. **Effectively requires login** for full descriptions. ~60–70% of listings have salary estimates (Glassdoor's competitive advantage). Recruiter emails never visible. Dynamic CSS class names change frequently, breaking HTML parsers. JobSpy supports Glassdoor but reliability varies. Best DIY approach: intercept internal GraphQL/JSON API calls via browser DevTools, replicate those requests with proper headers/cookies. Primarily useful for salary research rather than job discovery.

### 5. LinkedIn — Anti-bot: 5/5 (hardest, but guest API exists)

Custom ML-based bot detection, rate limiting, IP blocking, CAPTCHA challenges, browser fingerprinting. **However, LinkedIn has a public guest API** that doesn't require login: `linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=paralegal&location=New+York&start=0`. Returns HTML parseable with BeautifulSoup. Rate-limits kick in around page 10 with a single IP — residential proxy rotation essential. **~15–25% show salary.** Recruiter info never visible on public pages. Max ~250 results via guest API (10 pages × 25). JobSpy handles LinkedIn with proxy support. **Legal gray area**: the 9th Circuit ruled public data scraping isn't CFAA-violating (hiQ Labs case), but LinkedIn continues litigating. Never log into an account to scrape.

### 6. Google for Jobs — Anti-bot: 5/5 (never scrape directly)

Google's own anti-scraping system with CAPTCHAs, IP bans, and active litigation (Google sued SerpApi in December 2025). **Do not scrape Google directly.** Use: JobSpy (has Google Jobs support), SerpApi ($75/month for 5K searches), or DataForSEO ($0.0006/search). Google Jobs is the best meta-aggregator since it indexes Indeed, LinkedIn, Glassdoor, USAJobs, government boards, and law firm career pages simultaneously. Worth accessing through a third-party service.

### Sites to skip

**Monster and CareerBuilder** merged in September 2024 and filed Chapter 11 bankruptcy in June 2025. Revenue fell 40%. Both are being acquired by JobGet Inc. Listings have declined sharply — not worth building against. **Handshake** requires a valid .edu account with university SSO/2FA — inaccessible for general use. **Dice** is tech-only (irrelevant for legal/political).

---

## Niche boards for legal, political, DA, and NYC government

### DA offices and prosecutors

**NYC CityJobs (cityjobs.nyc.gov)** is the single best source for all NYC DA positions. Currently lists **27 Manhattan DA jobs, 44 Bronx DA, 14 Brooklyn DA, and 7 Richmond County DA** positions plus **171 total Legal Affairs category jobs** across all city agencies. No login required. It's a JavaScript SPA hosted on Azure — use Playwright to scrape or intercept the internal JSON API calls the SPA makes. Salary ranges appear on every listing. Scraping difficulty: **3/5.**

**Manhattan DA** specifically posts to four channels: CityJobs (primary), an Oracle Cloud ATS portal (support staff), an ApplicantStack portal (ADA positions at dany.applicantstack.com), and cross-posts to Indeed/LinkedIn. CityJobs covers most positions.

**DAASNY (daasny.com/?page_id=180)** — The District Attorneys Association of New York aggregates DA jobs statewide on a simple WordPress page. Scraping difficulty: **1/5** (basic HTML). Small volume but uniquely focused.

For federal prosecutor positions, **USAJobs API** filtered by agency (DOJ) and location (New York) captures US Attorney's office openings for SDNY and EDNY.

### Paralegal and legal jobs

**ABA Career Center (jobs.americanbar.org)** — American Bar Association's official board. No login to browse. Powered by YM Careers (standard server-rendered HTML). Covers all practice areas including criminal, government, and nonprofit. Scraping difficulty: **2/5.**

**NLADA Job Board (nlada.org/job-board)** — National Legal Aid & Defender Association. No login required. Standard HTML/CMS. Lists Legal Aid Society, Bronx Defenders, and similar NYC public defense positions. Scraping difficulty: **2/5.**

**NY Courts Careers (ww2.nycourts.gov/careers)** — NYS Unified Court System. No login. Court attorneys, law clerks, paralegals, clerical positions. Older HTML with PDF job descriptions (requiring text extraction). Filterable by NYC/Long Island. Scraping difficulty: **2/5.**

**PSJD (psjd.org)** — NALP's public interest legal job board. Thousands of government and public interest legal jobs. Requires login (free for law school affiliates; ~$20–40 for individual subscription). Scraping difficulty: **3/5.**

**NYC Bar Association Career Center** — NYC-specific legal positions. No login to browse. Powered by Association Career Network. Scraping difficulty: **2/5.**

**LawCrossing** aggregates from 10,000+ websites but requires a **paid subscription** to view full listings — scraping difficulty: **4/5** due to the paywall. Not recommended unless subscribing.

### Political campaigns and advocacy organizations

**GAIN Power Career Center (careercenter.gainpower.org)** — Successor to Democratic GAIN (closed 2020). Over 100,000 activists, 5,000+ employers across 50 states. Filters by state (including NY) and job type (Legal, Digital, Field, etc.). No login to browse. Modern JS-rendered platform. Scraping difficulty: **3/5.**

**Idealist.org** — Merged with VolunteerMatch in 2025. 1.3M monthly visitors, 250,000+ organizations. Has a dedicated legal jobs section. **Critically, Idealist offers an official API & Integrations service** (visible on their site navigation) worth investigating for programmatic access. No login to browse. JavaScript SPA with interceptable internal API calls. Scraping difficulty: **3/5.** Very high NYC relevance for legal aid, civil rights, policy organizations.

**Jobs That Are Left (leftjobs.com)** — Primary progressive/Democratic job listing resource, operated by GAIN Power. Available as website, Google Group, and Substack newsletter. Scraping difficulty: **3/5** for the web board.

**Political Job Hunt (politicaljobhunt.com)** — Associated with Political Wire. ~462 current political jobs. Publicly browsable, no login. Scraping difficulty: **2/5.**

**Arena (arena.run)** — Job bank + training for progressive political careers. Free for seekers. **Inclusv (inclusv.com)** — BIPOC political professionals. **Democracy Jobs (democracyjobs.org)** — Nonpartisan democracy-focused 501(c)(3) jobs with visible salary ranges. All publicly browsable, scraping difficulty: **2/5** each.

**Tom Manatos Jobs** and **Brad Traverse Jobs** are subscription-based ($5+/month), DC-focused job newsletters. **Not scrapeable** without subscription. Most political job lists outside of GAIN Power and Idealist are email-based — consider email parsing as an approach.

### NYC government (beyond USAJobs)

**CityJobs.nyc.gov** — ~1,998 current listings across 80+ agencies. This is THE definitive source. Filter by agency (DA offices, Law Department, Mayor's Office, Campaign Finance Board). JavaScript SPA with internal JSON endpoints discoverable via browser DevTools network tab.

**StateJobsNY (statejobs.ny.gov)** — All NY state agency jobs including Attorney General's office, state courts, and state agencies with NYC offices. No login to browse. Scraping difficulty: **3/5.**

**GovernmentJobs.com (NEOGOV)** — Largest public sector job board (13,000+ government organizations). However, its ToS **explicitly prohibits scraping** and NYC's city government doesn't use it (CityJobs is separate). Scraping difficulty: **5/5.** More relevant for suburban/county government positions in the NYC metro area.

**NYC Law Department** — ~1,000 attorneys + 880 support staff. Currently 11 listings on CityJobs. Uses LawCruit for attorney applications. Published salary bands from $87,737 to $188,235.

---

## Aggregator tools and services that bypass scraping entirely

### JobSpy — the cornerstone tool

**JobSpy** (`pip install python-jobspy`, GitHub: speedyapply/JobSpy) is an open-source library with 3,000+ stars that scrapes Indeed, LinkedIn, Glassdoor, Google Jobs, and ZipRecruiter concurrently through one function call. Returns a pandas DataFrame with standardized fields (title, company, job_url, location, salary, description, date_posted). Supports proxy rotation, date filtering, and location-based search. **Indeed scraping via JobSpy reportedly has no rate limiting.** LinkedIn requires residential proxies. Works on Python 3.10+ and Windows. This single tool replaces the need to build individual scrapers for the five largest job boards.

```python
from jobspy import scrape_jobs
jobs = scrape_jobs(
    site_name=["indeed", "linkedin", "google", "zip_recruiter"],
    search_term="paralegal",
    google_search_term="paralegal jobs in New York, NY",
    location="New York, NY",
    results_wanted=50,
    hours_old=72,
    country_indeed='USA'
)
```

### Apify pre-built actors

Apify's marketplace includes **2,000+ pre-built scrapers** with a free tier ($5/month credits). The standout is the **Career Site Job Listing API by Fantastic.jobs** — it scrapes 175,000+ company career sites across **54 ATS platforms** (Workday, Greenhouse, Lever, iCIMS, BambooHR, JazzHR, and more). Returns up to 60 fields per job with AI taxonomy filtering including Legal and Government & Public Sector categories. Indexes **1.8M+ jobs monthly.** Available via Apify ($5/month free credits, Starter $39/month) or RapidAPI (free trial).

Individual Apify actors exist for Greenhouse, Lever, Workday, iCIMS, LinkedIn, Indeed, Glassdoor, Talent.com, and SimplyHired — each pre-built and maintained.

### OpenJobRadar — free career page monitoring

**OpenJobRadar (openjobradar.com)** is a free tool supporting 14+ ATS platforms that auto-detects ATS type and pulls structured job data. Features unlimited company monitoring, keyword filters (must-have/exclusion), email notifications, and CSV bulk import. Supports Greenhouse, Lever, Workday, Ashby, BambooHR, SmartRecruiters, iCIMS, Jobvite, JazzHR, with Playwright fallback for custom pages. **Completely free, no premium tier.** Ideal for monitoring specific target employers (DA offices, law firms, political organizations).

### Craigslist RSS feeds

Craigslist offers **built-in RSS feeds** at the bottom of any search results page — legal, free, and lightweight. Subscribe to NYC legal (`newyork.craigslist.org/search/lgl`) and government job categories via any RSS reader. **Do not scrape Craigslist directly** — they won a $60.5M judgment against 3Taps for scraping and aggressively block bots.

### ATS direct APIs worth polling

Beyond Greenhouse and Lever (covered in the API section), these ATS platforms expose public job data:

- **Ashby** (jobs.ashbyhq.com) — Public API, used by tech startups and some political orgs
- **SmartRecruiters** — Public job board API, used broadly
- **Workable** — Public API available

**Workday** and **iCIMS** do not expose public APIs and require headless browser scraping with network request interception. Workday is particularly important since many large employers (city/state agencies, major law firms, Fortune 500 companies) use it. Apify has dedicated Workday and iCIMS scrapers.

---

## Recommended architecture for the bot

The optimal strategy layers free tools first, then adds paid services only where gaps remain.

**Layer 1 — Free, build immediately:** JobSpy for the five major boards (Indeed, LinkedIn, Google Jobs, ZipRecruiter, Glassdoor). USAJobs API for federal government. Greenhouse and Lever APIs for target employers. DAASNY and ABA Career Center with `requests` + BeautifulSoup. Craigslist RSS for NYC legal/government feeds. OpenJobRadar for target employer monitoring with email alerts.

**Layer 2 — Free with Playwright:** CityJobs.nyc.gov (intercept internal JSON API from the SPA). StateJobsNY. NY Courts Careers (HTML + PDF parsing). Idealist.org (investigate their official API first). GAIN Power Career Center. Political Job Hunt and Democracy Jobs.

**Layer 3 — Low-cost enhancements:** Adzuna API (free tier for salary data and supplemental coverage). Jooble API (free, broader aggregation). SerpApi or DataForSEO for structured Google Jobs access when JobSpy's Google scraping is insufficient. Apify free tier for Workday/iCIMS ATS scraping via pre-built actors.

**Technical stack summary:**

- **`python-jobspy`** — Primary multi-site scraper
- **`requests` + `BeautifulSoup`** — Simple HTML sites (SimplyHired, ABA, NLADA, DAASNY, niche boards)
- **`httpx`** — Async HTTP for high-throughput API calls
- **`playwright` + `playwright-stealth`** — JavaScript SPAs (CityJobs, Workday, iCIMS). Note: playwright-stealth was deprecated February 2025; use **Nodriver** or **SeleniumBase UC Mode** for Cloudflare bypass if playwright-stealth fails
- **`curl_cffi`** or **`tls-client`** — Avoid TLS fingerprint detection (Python's `requests` library has a distinctive JA3 fingerprint that gets flagged)
- **Residential proxies** — Essential for LinkedIn via JobSpy; recommended for Indeed at scale (IPRoyal, WebShare, or Bright Data)
- **`pdfplumber`** or **`PyPDF2`** — Extract text from NY Courts PDF job postings

## Conclusion

The job API ecosystem has contracted sharply — Indeed and ZipRecruiter's search APIs are gone, leaving **JSearch, Adzuna, and USAJobs** as the three most valuable remaining APIs for a NYC-focused legal/political/government job bot. But the real breakthrough is JobSpy, which makes the API closures largely irrelevant by scraping the five biggest boards through one Python call. For niche coverage, **CityJobs.nyc.gov alone contains 171 legal affairs positions** including all five NYC DA offices, making it the single highest-value scraping target. The Greenhouse and Lever APIs provide free, structured, no-auth access to thousands of employers' job boards — including many law firms, advocacy organizations, and political groups — making ATS-direct polling a powerful complement to board scraping. The most underutilized resource is **OpenJobRadar**, a completely free tool that monitors employer career pages across 14 ATS platforms with alerts, eliminating the need to build and maintain scrapers for individual target employers. The combination of JobSpy + USAJobs API + CityJobs scraping + Greenhouse/Lever polling + OpenJobRadar monitoring covers all three target categories comprehensively at zero cost.