import re
import html
import json
import base64
from typing import Set
from bs4 import BeautifulSoup

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

def decode_cloudflare_email(cf_hex: str) -> str:
    """
    Decodes Cloudflare data-cfemail hex string.
    """
    try:
        r = int(cf_hex[:2], 16)
        email_chars = [chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)]
        return "".join(email_chars)
    except Exception:
        return ""

def decode_js_from_char_code(script_text: str) -> Set[str]:
    emails = set()
    matches = re.findall(r"String\.fromCharCode\(([\d\s,]+)\)", script_text)
    for m in matches:
        try:
            codes = [int(c.strip()) for c in m.split(",") if c.strip().isdigit()]
            text = "".join(chr(c) for c in codes)
            found = EMAIL_REGEX.findall(text)
            emails.update(found)
        except Exception:
            pass
    return emails

def decode_js_atob(script_text: str) -> Set[str]:
    emails = set()
    matches = re.findall(r"atob\(['\"]([A-Za-z0-9+/=]+)['\"]\)", script_text)
    for m in matches:
        try:
            decoded = base64.b64decode(m).decode("utf-8", errors="ignore")
            found = EMAIL_REGEX.findall(decoded)
            emails.update(found)
        except Exception:
            pass
    return emails

def decode_all_emails(html_content: str) -> Set[str]:
    """
    Applies all decoders from Rule 4 to extract email candidates from HTML.
    Returns set of raw extracted emails.
    """
    emails = set()

    # 1. Unescape HTML entities
    unescaped_html = html.unescape(html_content)

    # 2. Cloudflare data-cfemail
    cf_matches = re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', unescaped_html)
    for cf in cf_matches:
        decoded = decode_cloudflare_email(cf)
        if decoded and EMAIL_REGEX.match(decoded):
            emails.add(decoded)

    soup = BeautifulSoup(unescaped_html, "lxml")

    # 3. mailto: links
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            email_part = href[7:].split("?")[0].strip()
            found = EMAIL_REGEX.findall(email_part)
            emails.update(found)

    # 4. JSON-LD and microdata
    for script in soup.find_all("script", type="application/ld+json"):
        if script.string:
            try:
                data = json.loads(script.string)
                _extract_json_ld_emails(data, emails)
            except Exception:
                pass

    for elem in soup.find_all(attrs={"itemprop": "email"}):
        val = elem.get("content") or elem.get_text()
        if val:
            found = EMAIL_REGEX.findall(val)
            emails.update(found)

    # 5. JS decoders
    for script in soup.find_all("script"):
        if script.string:
            emails.update(decode_js_from_char_code(script.string))
            emails.update(decode_js_atob(script.string))

    # 6. Visible text regex fallback
    text = soup.get_text(separator=" ")
    emails.update(EMAIL_REGEX.findall(text))
    emails.update(EMAIL_REGEX.findall(unescaped_html))

    return {e.lower().strip() for e in emails if e}

def _extract_json_ld_emails(data, emails_set: Set[str]):
    if isinstance(data, dict):
        for k, v in data.items():
            if k == "email" and isinstance(v, str):
                found = EMAIL_REGEX.findall(v)
                emails_set.update(found)
            else:
                _extract_json_ld_emails(v, emails_set)
    elif isinstance(data, list):
        for item in data:
            _extract_json_ld_emails(item, emails_set)
