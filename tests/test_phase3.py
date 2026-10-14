import pytest
from exhibition_lead_agent.portfolio_analyzer import PortfolioAnalyzer
from exhibition_lead_agent.draft_generator import DraftGenerator

def test_evidence_validator_drops_hallucinated_segment():
    analyzer = PortfolioAnalyzer()
    digest_text = """
Product Catalog for https://www.aguabendita.com:
- Title: "Agua Bendita Sunset One-Piece Swimsuit" | Type: Swimwear | Price: $220
- Title: "Agua Bendita Floral Cover Up Resort Dress" | Type: Resortwear | Price: $180
"""

    # 1. Valid segment with verbatim evidence
    valid_raw_segments = [
        {
            "segment": "beachwear_swim",
            "evidence": ["Agua Bendita Sunset One-Piece Swimsuit"],
            "evidence_url": "https://www.aguabendita.com/products/sunset",
            "confidence": 0.95
        }
    ]
    valid_segs, dropped_cnt = analyzer.validate_segments(digest_text, valid_raw_segments)
    assert len(valid_segs) == 1
    assert dropped_cnt == 0
    assert valid_segs[0]["evidence"] == ["Agua Bendita Sunset One-Piece Swimsuit"]

    # 2. Hallucinated segment with evidence NOT in catalog digest
    hallucinated_raw_segments = [
        {
            "segment": "outerwear",
            "evidence": ["Agua Bendita Heavy Winter Down Jacket"], # Hallucinated title not in digest
            "evidence_url": "https://www.aguabendita.com/products/jacket",
            "confidence": 0.90
        }
    ]
    hallucinated_segs, dropped_cnt_h = analyzer.validate_segments(digest_text, hallucinated_raw_segments)
    assert len(hallucinated_segs) == 0 # Must be dropped!
    assert dropped_cnt_h == 2 # 1 evidence string + 1 empty segment dropped

def test_draft_generator_word_count_and_content():
    generator = DraftGenerator(offer_template_path="config/offer.md")
    draft = generator.generate_draft(
        brand_name="Agua Bendita",
        segment="beachwear_swim",
        evidence_product="Agua Bendita Sunset One-Piece Swimsuit"
    )

    body = draft["body"]
    assert "Agua Bendita" in body
    assert "Agua Bendita Sunset One-Piece Swimsuit" in body

    word_count = len(body.split())
    assert word_count < 120
