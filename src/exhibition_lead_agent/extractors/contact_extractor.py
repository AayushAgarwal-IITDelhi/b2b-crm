import re
from typing import List, Optional, Tuple, Set
from urllib.parse import urlparse, urljoin
import dns.resolver
import tldextract
from bs4 import BeautifulSoup

from exhibition_lead_agent.extractors.html_decoders import decode_all_emails

JUNK_KEYWORDS = {
    "sentry", "placeholder", "example.com", "domain.com", "email.com",
    "yourname", "test@", "@2x", "library@", "schema.org", "wix.com",
    "shopify.com", "wordpress.org", "sentry.io", "klaviyo.com",
    "intercom.io", "noreply", "no-reply", "bounce", "privacy", "abuse",
    "postmaster", "mailer-daemon"
}

ROLE_PRIORITIES = [
    (re.compile(r"wholesale|trade|b2b|sourcing", re.I), 100),
    (re.compile(r"production|manufacturing|factory", re.I), 95),
    (re.compile(r"founder|owner|ceo", re.I), 85),
    (re.compile(r"sales|partnerships|order|orders", re.I), 70),
    (re.compile(r"design|studio", re.I), 60),
    (re.compile(r"info|hello|contact|enquiries", re.I), 50),
    (re.compile(r"press|media|pr", re.I), 30),
    (re.compile(r"support|customercare|help|service", re.I), 20),
]

FREE_MAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com"}

def is_junk_email(email: str) -> bool:
    email_lower = email.lower()
    if any(k in email_lower for k in JUNK_KEYWORDS):
        return True
    if any(email_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js"]):
        return True
    return False

def get_role_priority(email: str) -> int:
    username = email.split("@")[0].lower()
    for pattern, priority in ROLE_PRIORITIES:
        if pattern.search(username):
            return priority
    return 50 # Default priority

def check_mx_status(domain: str) -> str:
    """
    Checks MX DNS status for domain.
    Returns: ok | a-fallback | nxdomain | no-mx
    """
    try:
        answers = dns.resolver.resolve(domain, "MX")
        if answers:
            return "ok"
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        pass
    except dns.resolver.NXDOMAIN:
        return "nxdomain"
    except Exception:
        pass

    # Check A record fallback
    try:
        a_answers = dns.resolver.resolve(domain, "A")
        if a_answers:
            return "a-fallback"
    except Exception:
        pass

    return "no-mx"

def is_personal_email(email: str) -> bool:
    username = email.split("@")[0].lower()
    # Check firstname.lastname pattern
    return bool(re.match(r"^[a-z]+\.[a-z]+$", username))

def extract_form_urls(html_content: str, page_url: str) -> List[str]:
    soup = BeautifulSoup(html_content, "lxml")
    forms = soup.find_all("form")
    form_urls = []
    if forms:
        form_urls.append(page_url)
    return form_urls

def extract_contact_links(html_content: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html_content, "lxml")
    links = []
    contact_keywords = ["contact", "wholesale", "trade", "about"]

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text().strip().lower()
        if any(kw in href.lower() or kw in text for kw in contact_keywords):
            full_url = urljoin(base_url, href)
            # Only keep same domain links
            if urlparse(full_url).netloc.lower() == urlparse(base_url).netloc.lower():
                links.append(full_url)
    return list(dict.fromkeys(links))
