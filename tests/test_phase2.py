import pytest
from exhibition_lead_agent.qualifier import BrandQualifier
from exhibition_lead_agent.extractors.html_decoders import (
    decode_cloudflare_email, decode_all_emails
)
from exhibition_lead_agent.extractors.contact_extractor import (
    is_junk_email, get_role_priority
)

def test_mega_brand_rejection():
    qualifier = BrandQualifier(config_path="config/qualify.yaml")

    status, reason = qualifier.qualify("Christian Louboutin", "Eyewear collection")
    assert status == "rejected"
    assert "Christian Louboutin" in reason

    status, reason = qualifier.qualify("Polo Ralph Lauren", "Classic apparel")
    assert status == "rejected"
    assert "Polo Ralph Lauren" in reason

    status, reason = qualifier.qualify("Tom Ford", "Luxury fragrance and suits")
    assert status == "rejected"
    assert "Tom Ford" in reason

def test_non_apparel_keyword_rejection():
    qualifier = BrandQualifier(config_path="config/qualify.yaml")
    status, reason = qualifier.qualify("Shining Jewels", "Handmade gold jewelry and accessories")
    assert status == "rejected"
    assert "jewelry" in reason

def test_valid_brand_qualification():
    qualifier = BrandQualifier(config_path="config/qualify.yaml")
    status, reason = qualifier.qualify("Agua Bendita", "Luxury handcrafted swimwear and resortwear")
    assert status == "qualified"

def test_cloudflare_email_decoder():
    # 'test@example.com' encoded with key 0x12 -> hex
    # key=12, 't'^12 -> '74'^'12' = '66', 'e'^12 -> '77', etc.
    # Standard Cloudflare test snippet
    html = '<a class="__cf_email__" data-cfemail="6e0b160f031e020b2e0b160f031e020b400d0103">link</a>'
    emails = decode_all_emails(html)
    assert any("info@" in e or "contact@" in e or len(e) > 0 for e in emails)

def test_mailto_decoder():
    html = '<a href="mailto:wholesale@brand.com?subject=Inquiry">Contact Wholesale</a>'
    emails = decode_all_emails(html)
    assert "wholesale@brand.com" in emails

def test_junk_email_filter():
    assert is_junk_email("sentry@wix.com") is True
    assert is_junk_email("test@example.com") is True
    assert is_junk_email("image@2x.png") is True
    assert is_junk_email("hello@brand.com") is False
    assert is_junk_email("wholesale@brand.com") is False

def test_role_priority_ranking():
    assert get_role_priority("wholesale@brand.com") == 100
    assert get_role_priority("production@brand.com") == 95
    assert get_role_priority("ceo@brand.com") == 85
    assert get_role_priority("sales@brand.com") == 70
    assert get_role_priority("info@brand.com") == 50
    assert get_role_priority("press@brand.com") == 30
    assert get_role_priority("support@brand.com") == 20
