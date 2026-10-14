from typing import Optional, Dict
from urllib.parse import urlparse
from bs4 import BeautifulSoup

SOCIAL_DOMAINS = {
    "instagram.com", "facebook.com", "twitter.com", "x.com",
    "linkedin.com", "pinterest.com", "tiktok.com", "youtube.com",
    "vimeo.com"
}

def extract_brand_profile(html: str, profile_url: str, source_domain: Optional[str] = None) -> Dict[str, Optional[str]]:
    """
    Extracts website, instagram, description from a brand profile page.
    """
    if not source_domain:
        source_domain = urlparse(profile_url).netloc.lower()

    soup = BeautifulSoup(html, "lxml")

    website = None
    instagram = None
    description = None

    # 1. Instagram
    insta_anchor = soup.select_one("a[href*='instagram.com']")
    if insta_anchor and insta_anchor.get("href"):
        instagram = insta_anchor.get("href").strip()

    # 2. Description
    meta_desc = soup.select_one("meta[name='description']") or soup.select_one("meta[property='og:description']")
    if meta_desc and meta_desc.get("content"):
        desc_text = meta_desc.get("content").strip()
        if desc_text:
            description = desc_text

    # 3. External Website
    anchors = soup.find_all("a", href=True)
    for a in anchors:
        href = a["href"].strip()
        if not href.startswith("http://") and not href.startswith("https://"):
            continue

        parsed_href = urlparse(href)
        netloc = parsed_href.netloc.lower().removeprefix("www.")
        source_netloc = source_domain.removeprefix("www.")

        # Ignore same domain
        if netloc == source_netloc or netloc.endswith(f".{source_netloc}"):
            continue

        # Ignore social domains
        if any(netloc == sd or netloc.endswith(f".{sd}") for sd in SOCIAL_DOMAINS):
            continue

        # Found first external non-social website link
        # Clean protocol & trailing slashes if needed or keep full URL
        website = href
        break

    return {
        "website": website,
        "instagram": instagram,
        "description": description
    }
