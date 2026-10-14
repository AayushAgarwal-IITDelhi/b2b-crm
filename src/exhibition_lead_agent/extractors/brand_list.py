from typing import List, Dict
from urllib.parse import urljoin
from bs4 import BeautifulSoup

def extract_brand_list(html: str, base_url: str, selector: str = "a[href^='/brands/']") -> List[Dict[str, str]]:
    """
    Extracts brand links from exhibition directory HTML.
    Returns list of dicts: [{'name': '...', 'profile_url': '...'}]
    """
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select(selector)
    seen_urls = set()
    brands = []

    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        name = a.get_text(strip=True)
        if not name:
            continue
        brands.append({
            "name": name,
            "profile_url": full_url
        })

    return brands
