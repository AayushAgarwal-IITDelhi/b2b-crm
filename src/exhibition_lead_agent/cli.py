import sys
import os
import json
import random
import datetime
from typing import Optional
from urllib.parse import urlparse, urljoin
import typer
from rich.console import Console
from sqlalchemy.orm import Session

from exhibition_lead_agent.db.database import init_db, get_db
from exhibition_lead_agent.db.models import (
    ExhibitionDB, BrandDB, FieldValueDB, ContactDB, PortfolioDB, DraftDB
)
from exhibition_lead_agent.registry import RegistryLoader
from exhibition_lead_agent.crawler.fetcher import Fetcher
from exhibition_lead_agent.extractors.brand_list import extract_brand_list
from exhibition_lead_agent.extractors.brand_profile import extract_brand_profile
from exhibition_lead_agent.extractors.html_decoders import decode_all_emails
from exhibition_lead_agent.extractors.contact_extractor import (
    is_junk_email, get_role_priority, check_mx_status,
    extract_contact_links, extract_form_urls
)
from exhibition_lead_agent.qualifier import BrandQualifier
from exhibition_lead_agent.portfolio_analyzer import PortfolioAnalyzer
from exhibition_lead_agent.draft_generator import DraftGenerator
from exhibition_lead_agent.models.schema import ProvenanceValue, ContactExtract

app = typer.Typer(help="Exhibition Lead Agent CLI Toolkit")
console = Console()

@app.callback()
def main():
    pass

@app.command(name="crawl")
def crawl_cmd(source_key: str = typer.Argument(..., help="Source key from registry (e.g. cabanashow)")):
    """
    Crawl exhibition directory and profiles (Stages 1 & 2).
    """
    registry_loader = RegistryLoader()
    source = registry_loader.get(source_key)
    if not source:
        console.print(f"[bold red]Source key '{source_key}' not found in registry.[/bold red]")
        raise typer.Exit(code=1)

    init_db()
    db: Session = get_db()
    fetcher = Fetcher()

    console.print(f"[bold green]Starting crawl for {source.name} ({source.list_url})...[/bold green]")

    status, list_html, from_cache = fetcher.fetch(source.list_url)
    if status != 200 or not list_html:
        fetcher.save_snapshot(source.list_url, f"list_fetch_failed_status_{status}", list_html)
        console.print(f"[bold red]Failed to fetch list URL: status {status}[/bold red]")
        raise typer.Exit(code=1)

    brand_items = extract_brand_list(
        html=list_html,
        base_url=source.list_url,
        selector=source.brand_links.get("selector", "a[href^='/brands/']")
    )

    if not brand_items:
        fetcher.save_snapshot(source.list_url, "zero_brands_extracted", list_html)
        console.print("[bold red]Zero brands extracted from directory list page.[/bold red]")
        raise typer.Exit(code=1)

    exhibition = db.query(ExhibitionDB).filter_by(source_key=source.key).first()
    if not exhibition:
        exhibition = ExhibitionDB(name=source.name, list_url=source.list_url, source_key=source.key)
        db.add(exhibition)
        db.commit()
        db.refresh(exhibition)
    exhibition.last_crawled_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    db.commit()

    total_links_found = len(brand_items)
    console.print(f"Found [bold cyan]{total_links_found}[/bold cyan] brand links on directory list page.")

    profiles_fetched = 0
    with_website = 0
    with_instagram = 0
    with_description = 0
    website_unresolved_cnt = 0
    saved_brands = []

    for idx, item in enumerate(brand_items, 1):
        p_url = item["profile_url"]
        b_name = item["name"]

        p_status, p_html, p_cached = fetcher.fetch(p_url)
        if p_status != 200 or not p_html:
            fetcher.save_snapshot(p_url, f"profile_fetch_failed_status_{p_status}", p_html)
            continue

        profiles_fetched += 1
        extracted = extract_brand_profile(p_html, p_url)

        website = extracted["website"]
        instagram = extracted["instagram"]
        description = extracted["description"]
        unresolved = (website is None)

        if website:
            with_website += 1
        else:
            website_unresolved_cnt += 1

        if instagram:
            with_instagram += 1
        if description:
            with_description += 1

        brand = db.query(BrandDB).filter_by(profile_url=p_url).first()
        if not brand:
            brand = BrandDB(
                exhibition_id=exhibition.id,
                name=b_name,
                profile_url=p_url,
                website=website,
                website_unresolved=unresolved,
                instagram=instagram,
                description=description
            )
            db.add(brand)
            db.commit()
            db.refresh(brand)
        else:
            brand.name = b_name
            brand.website = website
            brand.website_unresolved = unresolved
            brand.instagram = instagram
            brand.description = description
            db.commit()

        saved_brands.append(brand)

        fields_to_store = [
            ("website", website),
            ("instagram", instagram),
            ("description", description)
        ]
        for f_name, f_val in fields_to_store:
            if f_val:
                prov = ProvenanceValue(
                    value=f_val,
                    source_url=p_url,
                    fetched_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                    method="parsed",
                    confidence=1.0
                )
                fv = FieldValueDB(
                    entity_type="brand",
                    entity_id=brand.id,
                    field=f_name,
                    value=prov.value,
                    source_url=prov.source_url,
                    fetched_at=prov.fetched_at,
                    method=prov.method,
                    confidence=prov.confidence
                )
                db.add(fv)
        db.commit()

        if idx % 50 == 0 or idx == total_links_found:
            console.print(f"Processed {idx}/{total_links_found} profiles...")

    console.print("\n[bold green]=== PHASE 1 CRAWL REPORT ===[/bold green]")
    console.print(f"Exhibition Source: {source.name} ({source.key})")
    console.print(f"Brand links found: {total_links_found}")
    console.print(f"Profiles fetched: {profiles_fetched}")
    console.print(f"With website: {with_website}")
    console.print(f"With Instagram: {with_instagram}")
    console.print(f"With description: {with_description}")
    console.print(f"Website unresolved: {website_unresolved_cnt}")

@app.command(name="qualify")
def qualify_cmd(config_path: str = typer.Option("config/qualify.yaml", help="Path to qualify rules YAML")):
    """
    Run Stage 3 deterministic qualification on all extracted brands.
    """
    init_db()
    db: Session = get_db()
    qualifier = BrandQualifier(config_path=config_path)

    brands = db.query(BrandDB).all()
    if not brands:
        console.print("[bold red]No brands found in database. Run crawl first.[/bold red]")
        raise typer.Exit(code=1)

    qualified_cnt = 0
    rejected_cnt = 0
    needs_review_cnt = 0
    rejection_reasons = {}

    for brand in brands:
        status, reason = qualifier.qualify(
            name=brand.name,
            description=brand.description,
            country=brand.country
        )
        brand.qualification_status = status
        brand.qualification_reason = reason
        db.commit()

        if status == "qualified":
            qualified_cnt += 1
        elif status == "rejected":
            rejected_cnt += 1
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        elif status == "needs_review":
            needs_review_cnt += 1

    console.print("\n[bold green]=== STAGE 3 QUALIFICATION REPORT ===[/bold green]")
    console.print(f"Total Brands Evaluated: {len(brands)}")
    console.print(f"Qualified: [bold green]{qualified_cnt}[/bold green]")
    console.print(f"Rejected: [bold red]{rejected_cnt}[/bold red]")
    console.print(f"Needs Review: [bold yellow]{needs_review_cnt}[/bold yellow]")

    console.print("\n[bold yellow]Top Rejection Reasons:[/bold yellow]")
    sorted_reasons = sorted(rejection_reasons.items(), key=lambda x: x[1], reverse=True)
    for r, count in sorted_reasons[:10]:
        console.print(f" - [{count} brands] {r}")

@app.command(name="contacts")
def contacts_cmd(limit: int = typer.Option(50, help="Max qualified brands to extract contacts for (0 for all)")):
    """
    Run Stage 4 contact extraction on qualified brands with websites.
    """
    init_db()
    db: Session = get_db()
    fetcher = Fetcher(request_budget=5000)

    query = db.query(BrandDB).filter_by(qualification_status="qualified").filter(BrandDB.website.isnot(None))
    if limit > 0:
        query = query.limit(limit)
    qualified_brands = query.all()

    if not qualified_brands:
        console.print("[bold red]No qualified brands with website found.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"Starting contact extraction for [bold cyan]{len(qualified_brands)}[/bold cyan] qualified brands...")

    bucket_counts = {"email": 0, "form_only": 0, "manual": 0}
    mx_counts = {"ok": 0, "a-fallback": 0, "nxdomain": 0, "no-mx": 0, "unchecked": 0}
    extracted_emails_list = []

    target_paths = [
        "", "/contact", "/contact-us", "/pages/contact",
        "/wholesale", "/pages/wholesale", "/about", "/impressum", "/trade", "/stockists"
    ]

    for idx, brand in enumerate(qualified_brands, 1):
        parsed_web = urlparse(brand.website)
        base_domain = parsed_web.netloc.lower()
        if not base_domain:
            continue

        base_url = f"{parsed_web.scheme}://{parsed_web.netloc}"
        found_contacts = []
        found_form_url = None

        urls_to_visit = [urljoin(base_url, p) for p in target_paths]

        hp_url = urls_to_visit[0]
        try:
            hp_status, hp_html, _ = fetcher.fetch(hp_url, ignore_robots=True)
            if hp_status == 200 and hp_html:
                discovered_links = extract_contact_links(hp_html, base_url)
                urls_to_visit.extend(discovered_links)
        except Exception:
            pass

        urls_to_visit = list(dict.fromkeys(urls_to_visit))

        for page_url in urls_to_visit:
            try:
                status, html, _ = fetcher.fetch(page_url, ignore_robots=True)
                if status != 200 or not html:
                    continue

                forms = extract_form_urls(html, page_url)
                if forms and not found_form_url:
                    found_form_url = forms[0]

                raw_emails = decode_all_emails(html)
                for email_val in raw_emails:
                    if is_junk_email(email_val):
                        continue

                    domain_part = email_val.split("@")[1]
                    mx_res = check_mx_status(domain_part)
                    mx_counts[mx_res] = mx_counts.get(mx_res, 0) + 1

                    if mx_res in ("ok", "a-fallback"):
                        priority = get_role_priority(email_val)
                        contact_data = ContactExtract(
                            kind="email",
                            value=email_val,
                            role_priority=priority,
                            mx_status=mx_res,
                            is_third_party=(domain_part != base_domain),
                            source_url=page_url
                        )
                        found_contacts.append(contact_data)

                if any(c.role_priority >= 80 and not c.is_third_party for c in found_contacts):
                    break

            except Exception:
                continue

        if found_contacts:
            brand.contact_bucket = "email"
            bucket_counts["email"] += 1
            found_contacts.sort(key=lambda x: x.role_priority, reverse=True)
            for c in found_contacts:
                db_contact = ContactDB(
                    brand_id=brand.id,
                    kind=c.kind,
                    value=c.value,
                    role_priority=c.role_priority,
                    mx_status=c.mx_status,
                    is_third_party=c.is_third_party,
                    source_url=c.source_url
                )
                db.add(db_contact)
                extracted_emails_list.append((brand.name, c.value, c.source_url))
        elif found_form_url:
            brand.contact_bucket = "form_only"
            bucket_counts["form_only"] += 1
            db_contact = ContactDB(
                brand_id=brand.id,
                kind="form",
                value=found_form_url,
                role_priority=50,
                mx_status="unchecked",
                is_third_party=False,
                source_url=found_form_url
            )
            db.add(db_contact)
        else:
            brand.contact_bucket = "manual"
            clean_host = base_domain.removeprefix("www.")
            brand.manual_search_string = f'site:{clean_host} "@{clean_host}"'
            bucket_counts["manual"] += 1

        db.commit()

        if idx % 10 == 0 or idx == len(qualified_brands):
            console.print(f"Extracted contacts for {idx}/{len(qualified_brands)} brands...")

    console.print("\n[bold green]=== STAGE 4 CONTACT EXTRACTION REPORT ===[/bold green]")
    console.print("Contact Bucket Counts:")
    console.print(f" - Email: [bold green]{bucket_counts['email']}[/bold green]")
    console.print(f" - Form Only: [bold yellow]{bucket_counts['form_only']}[/bold yellow]")
    console.print(f" - Manual: [bold red]{bucket_counts['manual']}[/bold red]")

    console.print("\nMX Status Distribution:")
    for status_k, status_v in mx_counts.items():
        console.print(f" - {status_k}: {status_v}")

@app.command(name="portfolio")
def portfolio_cmd(limit: int = typer.Option(20, help="Max brands to analyze portfolio for")):
    """
    Run Stage 5 portfolio classification and verbatim evidence extraction.
    """
    init_db()
    db: Session = get_db()
    analyzer = PortfolioAnalyzer()

    brands = db.query(BrandDB).filter_by(qualification_status="qualified").filter(BrandDB.website.isnot(None)).limit(limit).all()
    if not brands:
        console.print("[bold red]No qualified brands with website found.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"Analyzing portfolios for [bold cyan]{len(brands)}[/bold cyan] qualified brands...")

    has_data_cnt = 0
    segment_dist = {}
    total_dropped = 0
    sample_outputs = []

    for idx, brand in enumerate(brands, 1):
        digest, product_items = analyzer.gather_product_digest(brand.website)
        res = analyzer.analyze(digest, product_items)

        segments = res.get("segments", [])
        dropped = res.get("dropped_segments", 0)
        total_dropped += dropped

        if segments:
            has_data_cnt += 1
            for seg in segments:
                s_name = seg["segment"]
                segment_dist[s_name] = segment_dist.get(s_name, 0) + 1

            sample_outputs.append((brand.name, segments, brand.website))

        # Save to DB
        pf = PortfolioDB(
            brand_id=brand.id,
            segments_json=json.dumps(segments),
            price_tier=res.get("price_tier", "unknown"),
            evidence_json=json.dumps([s.get("evidence", []) for s in segments]),
            confidence=1.0,
            content_hash=res.get("content_hash", "none"),
            model=res.get("model", "fallback")
        )
        db.add(pf)
        db.commit()

        if idx % 5 == 0 or idx == len(brands):
            console.print(f"Analyzed portfolio for {idx}/{len(brands)} brands...")

    console.print("\n[bold green]=== STAGE 5 PORTFOLIO ANALYSIS REPORT ===[/bold green]")
    console.print(f"Brands with Product Data: [bold cyan]{has_data_cnt}/{len(brands)}[/bold cyan]")
    console.print(f"Total Segments Dropped by Validation: [bold red]{total_dropped}[/bold red]")
    console.print("\nSegment Distribution:")
    for seg_k, seg_v in segment_dist.items():
        console.print(f" - {seg_k}: {seg_v}")

    console.print("\n[bold yellow]Sample 10 Portfolio Outputs (with Verbatim Evidence):[/bold yellow]")
    for b_name, segs, w_url in sample_outputs[:10]:
        console.print(f" - Brand: [bold]{b_name}[/bold] ({w_url})")
        for s in segs:
            ev_str = ", ".join(s.get("evidence", []))
            console.print(f"   Segment: [bold green]{s['segment']}[/bold green] | Evidence: \"{ev_str}\"")

@app.command(name="drafts")
def drafts_cmd(limit: int = typer.Option(20, help="Max drafts to generate")):
    """
    Run Stage 6 cold email draft generation.
    """
    init_db()
    db: Session = get_db()
    generator = DraftGenerator()

    brands = db.query(BrandDB).filter_by(contact_bucket="email").limit(limit).all()
    if not brands:
        console.print("[bold red]No brands in 'email' contact bucket found.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"Generating drafts for [bold cyan]{len(brands)}[/bold cyan] brands...")
    drafts_list = []

    for brand in brands:
        contact = db.query(ContactDB).filter_by(brand_id=brand.id, kind="email").order_by(ContactDB.role_priority.desc()).first()
        portfolio = db.query(PortfolioDB).filter_by(brand_id=brand.id).order_by(PortfolioDB.id.desc()).first()

        segments = json.loads(portfolio.segments_json) if portfolio and portfolio.segments_json else []
        if segments:
            seg_name = segments[0]["segment"]
            ev_product = segments[0]["evidence"][0] if segments[0].get("evidence") else "apparel collection"
        else:
            seg_name = "custom apparel"
            ev_product = f"{brand.name} collection"

        draft_res = generator.generate_draft(
            brand_name=brand.name,
            segment=seg_name,
            evidence_product=ev_product
        )

        draft_db = DraftDB(
            brand_id=brand.id,
            contact_id=contact.id if contact else None,
            subject=draft_res["subject"],
            body=draft_res["body"],
            status="draft"
        )
        db.add(draft_db)
        db.commit()

        drafts_list.append((brand.name, contact.value if contact else "N/A", draft_res["subject"], draft_res["body"], ev_product))

    console.print("\n[bold green]=== STAGE 6 DRAFTS REPORT ===[/bold green]")
    console.print(f"Total Drafts Generated: {len(drafts_list)}")
    console.print("\n[bold yellow]Sample 10 Draft Emails (with Verbatim Evidence Context):[/bold yellow]")
    for b_name, email_v, subj, body, ev_p in drafts_list[:10]:
        console.print(f"\n--------------------------------------------------")
        console.print(f"Brand: [bold]{b_name}[/bold] | Contact: [cyan]{email_v}[/cyan]")
        console.print(f"Evidence Product: [italic]\"{ev_p}\"[/italic]")
        console.print(f"Subject: [bold]{subj}[/bold]")
        console.print(f"Body:\n{body}")

@app.command(name="ui")
def ui_cmd(host: str = "127.0.0.1", port: int = 8000):
    """
    Launch Stage 7 Review Web UI (FastAPI).
    """
    import uvicorn
    from exhibition_lead_agent.web_ui import app as web_app
    console.print(f"[bold green]Starting Review UI on http://{host}:{port}...[/bold green]")
    uvicorn.run(web_app, host=host, port=port)

if __name__ == "__main__":
    app()
