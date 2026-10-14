# Exhibition Lead Agent

An automated, rule-governed lead extraction and personalized cold email drafting system built for garment manufacturers seeking to partner with international fashion brands exhibiting at trade shows.

---

## Key Features & Non-Negotiable Guardrails

1. **Zero Fabrication**: No values (websites, emails, handles, or counts) are ever fabricated. Missing data is stored as `null` with a clear reason.
2. **Strict Field Provenance**: Every field (`website`, `instagram`, `description`, `contacts`) records `source_url`, `fetched_at`, `method` (`parsed`, `regex`, `llm`), and `confidence`. Entries without a `source_url` are prohibited.
3. **Deterministic First, LLM Last**: Brand directories, profiles, and contacts are extracted purely with deterministic HTML decoders. LLMs are used only for catalog segmentation and drafting.
4. **Verified Contact Extraction**: Emails are collected using multiple HTML decoders (`mailto:`, Cloudflare hex `data-cfemail`, JSON-LD, microdata, JavaScript `fromCharCode`/`atob`, text) and validated with DNS MX record lookups (`ok`, `a-fallback`, `nxdomain`, `no-mx`).
5. **Verbatim Evidence Validation**: Product categories/segments require verbatim evidence from the brand's live product catalog (via Shopify `/products.json` or HTML). Hallucinated segments are dropped.
6. **No Per-Site Hardcoded Logic**: Exhibition parsers are defined purely via declarative YAML in `sources/`.
7. **Polite Crawling**: Respects `robots.txt`, identifies itself via custom User-Agent, waits 2–3s per host, handles rate limits with exponential backoff, and hashes requests to local SQLite cache (`.crawl_cache.db`) so subsequent runs make zero network calls.
8. **Human Review Dashboard**: Built-in FastAPI web UI for inspecting lead provenance, approving/rejecting drafts, and exporting approved drafts to CSV.

---

## Directory Structure

```text
exhibition_lead_agent/
├── config/
│   ├── qualify.yaml           # Excluded keywords (non-apparel) and mega-brands
│   └── offer.md               # Email template in custom garment manufacturer voice
├── sources/
│   └── cabanashow.yaml        # Exhibition crawling rules for Cabana Show
├── src/
│   └── exhibition_lead_agent/
│       ├── cli.py             # Typer CLI application
│       ├── registry.py        # YAML configuration loader
│       ├── qualifier.py       # Stage 3 deterministic brand qualifier
│       ├── portfolio_analyzer.py # Stage 5 product catalog & verbatim evidence validator
│       ├── draft_generator.py # Stage 6 personalized email drafting
│       ├── web_ui.py          # Stage 7 FastAPI Review Dashboard & CSV exporter
│       ├── crawler/           # Polite fetcher, robots.txt validator, disk cache
│       ├── db/                # SQLAlchemy database models & setup
│       ├── extractors/        # HTML decoders (mailto, Cloudflare, JS, JSON-LD), contacts, lists
│       └── models/            # Pydantic v2 schemas with provenance enforcement
├── tests/
│   ├── fixtures/              # Real HTML snapshots from live exhibition pages
│   ├── test_phase1.py         # Provenance schema, crawler fixtures, code audit
│   ├── test_phase2.py         # Qualifier, email decoders, junk filter, MX verification
│   └── test_phase3.py         # Verbatim evidence validator & draft generator tests
├── pyproject.toml             # Project dependencies & build config
├── .env.example               # Template environment configuration
└── README.md
```

---

## Installation & Setup

### Prerequisites
- Python 3.10+ (Recommended: Python 3.12)
- Virtual environment tool (`venv` or `uv`)

### 1. Clone & Set Up Virtual Environment

```bash
# Clone the repository
git clone <your-repo-url>
cd exhibition_lead_agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (including test suite)
pip install -e ".[dev]"
```

### 2. Environment Variables (Optional)

```bash
cp .env.example .env
```
*Note: If `GEMINI_API_KEY` is not provided, the portfolio analyzer gracefully falls back to deterministic keyword catalog matching with verbatim evidence extraction.*

---

## Usage Guide (CLI Workflow)

Run each stage using the Typer CLI:

### 1. Crawl Exhibition Directory & Brand Profiles (Stages 1 & 2)
Scrapes the exhibition directory and individual brand profile pages:
```bash
python -m exhibition_lead_agent.cli crawl cabanashow
```

### 2. Qualify Brands (Stage 3)
Filters out non-apparel brands (jewelry, eyewear, candles, fragrances, footwear, bags, hats) and mega-brands (e.g. Ralph Lauren, Louboutin, Max Mara):
```bash
python -m exhibition_lead_agent.cli qualify
```

### 3. Extract Contacts & Verify MX Records (Stage 4)
Visits brand websites and contact pages to decode email addresses and verify their mail servers:
```bash
# Extract contacts for qualified brands (use --limit 0 to process all)
python -m exhibition_lead_agent.cli contacts --limit 50
```

### 4. Analyze Portfolios with Verbatim Evidence (Stage 5)
Extracts product catalogs and classifies segments (e.g., womenswear, beachwear_swim, resortwear, menswear):
```bash
python -m exhibition_lead_agent.cli portfolio --limit 20
```

### 5. Generate Cold Email Drafts (Stage 6)
Generates personalized emails referencing the brand's verified products in a manufacturer voice:
```bash
python -m exhibition_lead_agent.cli drafts --limit 20
```

### 6. Review Leads & Export CSV (Stage 7)
Launches the web dashboard:
```bash
python -m exhibition_lead_agent.cli ui --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser to inspect field provenance, approve/reject drafts, and export approved leads via `/export/csv`.

---

## Running the Automated Test Suite

```bash
pytest
```
The test suite includes 14 unit and integration tests verifying:
- Mandatory source URLs for provenance
- HTML email decoders (Cloudflare hex, JSON-LD, mailto)
- Verbatim evidence validation (rejecting hallucinated items)
- Mega-brand and non-apparel keyword exclusions
- AST/grep code audit ensuring zero fabricated URLs or values

---

## Adding a New Exhibition Source

To support another exhibition, create a new YAML configuration under `sources/<source_key>.yaml`:

```yaml
key: new_exhibition
name: New Exhibition Name
list_url: https://example.com/brand-directory
render: http
brand_links:
  selector: "a[href*='/brand/']"
  name_from: text
  url_from: href
profile:
  website:
    rule: first_external_link_not_social_not_same_domain
  instagram:
    selector: "a[href*='instagram.com']"
  description:
    selector: "meta[name='description']"
```
Once added, simply run:
```bash
python -m exhibition_lead_agent.cli crawl new_exhibition
```
