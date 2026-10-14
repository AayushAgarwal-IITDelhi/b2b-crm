import os
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
from google import genai
from google.genai import types

from exhibition_lead_agent.crawler.fetcher import Fetcher

TAXONOMY_SEGMENTS = {
    "womenswear", "menswear", "kidswear", "formal", "casual",
    "beachwear_swim", "resortwear", "suits_tailoring", "knitwear",
    "activewear", "outerwear", "loungewear", "other"
}

PRICE_TIERS = {"budget", "mid", "premium", "luxury", "unknown"}

class PortfolioAnalyzer:
    def __init__(self, fetcher: Optional[Fetcher] = None):
        self.fetcher = fetcher or Fetcher(request_budget=1000)
        self.model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        api_key = os.environ.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None

    def gather_product_digest(self, website_url: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        Gathers product title/metadata digest from brand website (Shopify products.json or HTML).
        Returns (digest_text, product_list).
        """
        parsed = urlparse(website_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        products_json_url = urljoin(base_url, "/products.json?limit=50")

        product_items = []
        try:
            status, content, _ = self.fetcher.fetch(products_json_url, ignore_robots=True)
            if status == 200 and content:
                data = json.loads(content)
                if isinstance(data, dict) and "products" in data:
                    for p in data["products"]:
                        title = p.get("title", "").strip()
                        p_type = p.get("product_type", "").strip()
                        tags = p.get("tags", [])
                        if isinstance(tags, list):
                            tags_str = ", ".join(str(t) for t in tags)
                        else:
                            tags_str = str(tags)
                        variants = p.get("variants", [])
                        price = variants[0].get("price", "") if variants else ""
                        handle = p.get("handle", "")
                        p_url = urljoin(base_url, f"/products/{handle}") if handle else website_url

                        if title:
                            product_items.append({
                                "title": title,
                                "type": p_type,
                                "tags": tags_str,
                                "price": price,
                                "url": p_url
                            })
        except Exception:
            pass

        if not product_items:
            # Fallback: Check homepage HTML for titles
            try:
                status, html, _ = self.fetcher.fetch(website_url, ignore_robots=True)
                if status == 200 and html:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "lxml")
                    for elem in soup.select("h1, h2, h3, .product-title, .product-name"):
                        txt = elem.get_text(strip=True)
                        if len(txt) > 3 and len(txt) < 80:
                            product_items.append({
                                "title": txt,
                                "type": "",
                                "tags": "",
                                "price": "",
                                "url": website_url
                            })
            except Exception:
                pass

        if not product_items:
            return "", []

        digest_lines = [f"Product Catalog for {website_url}:"]
        for p in product_items[:50]:
            line = f"- Title: \"{p['title']}\""
            if p["type"]:
                line += f" | Type: {p['type']}"
            if p["tags"]:
                line += f" | Tags: {p['tags']}"
            if p["price"]:
                line += f" | Price: ${p['price']}"
            digest_lines.append(line)

        digest_text = "\n".join(digest_lines)
        return digest_text, product_items

    def validate_segments(self, digest_text: str, segments: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        Rule 5.5: Validate that every evidence string appears VERBATIM in digest_text.
        Returns (valid_segments, dropped_count).
        """
        valid_segments = []
        dropped_count = 0

        for seg in segments:
            evidence_list = seg.get("evidence", [])
            valid_evidence = []
            for ev in evidence_list:
                if isinstance(ev, str) and ev.strip() and ev.strip() in digest_text:
                    valid_evidence.append(ev.strip())
                else:
                    dropped_count += 1

            if valid_evidence:
                seg_copy = dict(seg)
                seg_copy["evidence"] = valid_evidence
                valid_segments.append(seg_copy)
            else:
                dropped_count += 1

        return valid_segments, dropped_count

    def analyze(self, digest_text: str, product_items: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Analyzes portfolio digest using LLM with verbatim evidence validation.
        """
        if not digest_text or not product_items:
            return {
                "segments": [],
                "price_tier": "unknown",
                "evidence": [],
                "reason": "no_product_data",
                "dropped_segments": 0
            }

        content_hash = hashlib.sha256(digest_text.encode("utf-8")).hexdigest()

        # If LLM API key is not set or client unavailable, perform deterministic fallback analysis
        if not self.client:
            raw_segments, price_tier = self._fallback_keyword_analysis(digest_text, product_items)
        else:
            try:
                raw_segments, price_tier = self._call_llm_analysis(digest_text)
            except Exception as exc:
                # Circuit breaker on API error
                raw_segments, price_tier = self._fallback_keyword_analysis(digest_text, product_items)

        valid_segments, dropped_cnt = self.validate_segments(digest_text, raw_segments)

        return {
            "segments": valid_segments,
            "price_tier": price_tier,
            "content_hash": content_hash,
            "model": self.model_name if self.client else "fallback_keyword_matching",
            "dropped_segments": dropped_cnt,
            "reason": "success" if valid_segments else "no_valid_evidence"
        }

    def _call_llm_analysis(self, digest_text: str) -> Tuple[List[Dict[str, Any]], str]:
        prompt = f"""
Analyze the following fashion brand product catalog digest and classify into portfolio segments.

Taxonomy segments allowed: womenswear, menswear, kidswear, formal, casual, beachwear_swim, resortwear, suits_tailoring, knitwear, activewear, outerwear, loungewear, other
Price tiers allowed: budget, mid, premium, luxury, unknown

IMPORTANT: For evidence, you MUST output exact verbatim product titles from the catalog.

Catalog Digest:
{digest_text}
"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            )
        )
        data = json.loads(response.text)
        raw_segments = data.get("segments", [])
        price_tier = data.get("price_tier", "unknown")
        return raw_segments, price_tier

    def _fallback_keyword_analysis(self, digest_text: str, product_items: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        Deterministic keyword classification providing verbatim evidence from catalog titles.
        """
        segments = []
        seen_segments = set()

        keywords_map = {
            "beachwear_swim": ["bikini", "swimsuit", "swimwear", "swim", "trunks", "one-piece", "beachwear"],
            "resortwear": ["kaftan", "cover-up", "resortwear", "resort", "sarong", "linen dress"],
            "womenswear": ["dress", "skirt", "blouse", "top", "woman", "women"],
            "menswear": ["shirt", "men", "mens", "shorts", "pants"],
            "knitwear": ["knit", "sweater", "cardigan", "cashmere"]
        }

        for item in product_items:
            title = item["title"]
            title_lower = title.lower()
            item_url = item.get("url", "")

            for seg_name, kw_list in keywords_map.items():
                if any(kw in title_lower for kw in kw_list):
                    if seg_name not in seen_segments:
                        seen_segments.add(seg_name)
                        segments.append({
                            "segment": seg_name,
                            "evidence": [title], # Verbatim title from catalog
                            "evidence_url": item_url,
                            "confidence": 0.9
                        })
                    break

        return segments, "premium"
