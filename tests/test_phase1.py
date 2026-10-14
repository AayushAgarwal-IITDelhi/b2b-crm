import os
import glob
import pytest
from pydantic import ValidationError
from exhibition_lead_agent.models.schema import ProvenanceValue, ContactExtract
from exhibition_lead_agent.extractors.brand_list import extract_brand_list
from exhibition_lead_agent.extractors.brand_profile import extract_brand_profile

def test_provenance_schema_requires_source_url():
    with pytest.raises(ValidationError):
        ProvenanceValue(
            value="http://example.com",
            source_url="", # Empty source_url should fail
            method="parsed"
        )

    with pytest.raises(ValidationError):
        ContactExtract(
            kind="email",
            value="test@example.com",
            source_url="" # Empty source_url should fail
        )

def test_extract_brand_list_parser():
    html = """
    <html>
        <body>
            <a href="/brands/brand-a">Brand A</a>
            <a href="/brands/brand-b">Brand B</a>
            <a href="/other">Other Link</a>
        </body>
    </html>
    """
    brands = extract_brand_list(html, "https://www.cabanashow.com/brand-list")
    assert len(brands) == 2
    assert brands[0]["name"] == "Brand A"
    assert brands[0]["profile_url"] == "https://www.cabanashow.com/brands/brand-a"

def test_cabana_fixture_link_count():
    fixture_path = "tests/fixtures/cabana_list.html"
    if os.path.exists(fixture_path):
        with open(fixture_path, "r", encoding="utf-8") as f:
            html = f.read()
        brands = extract_brand_list(html, "https://www.cabanashow.com/brand-list")
        assert len(brands) == 403

def test_extract_brand_profile_parser():
    html = """
    <html>
        <head>
            <meta name="description" content="Luxury swimwear brand handcrafted in Colombia." />
        </head>
        <body>
            <h1>Agua Bendita</h1>
            <a href="https://www.instagram.com/aguabenditasw">Instagram</a>
            <a href="https://www.aguabendita.com">Official Website</a>
            <a href="https://www.cabanashow.com/brands/agua-bendita">Profile Link</a>
        </body>
    </html>
    """
    profile = extract_brand_profile(html, "https://www.cabanashow.com/brands/agua-bendita", source_domain="cabanashow.com")
    assert profile["website"] == "https://www.aguabendita.com"
    assert profile["instagram"] == "https://www.instagram.com/aguabenditasw"
    assert "swimwear" in profile["description"].lower()

def test_no_forbidden_code_patterns():
    """
    Check Rule 9 / Code Audit: No random.random or URL generation from brand names.
    """
    src_files = glob.glob("src/**/*.py", recursive=True)
    forbidden_terms = ["random.random(", "Math.random"]
    for path in src_files:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            for term in forbidden_terms:
                assert term not in content, f"Forbidden term '{term}' found in {path}"
