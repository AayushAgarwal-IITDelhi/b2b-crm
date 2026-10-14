import os
import jinja2
from typing import Dict, Any, Optional

class DraftGenerator:
    def __init__(self, offer_template_path: str = "config/offer.md"):
        self.offer_template_path = offer_template_path
        self.template_content = self.load_template()

    def load_template(self) -> str:
        if os.path.exists(self.offer_template_path):
            with open(self.offer_template_path, "r", encoding="utf-8") as f:
                return f.read()
        return "Hi team at {{brand_name}},\n\nWe produce custom apparel for international fashion brands. We noticed your collection featuring {{evidence_product}} and would love to support your upcoming production runs.\n\nBest regards,\nCustom Garment Manufacturing Team"

    def generate_draft(self, brand_name: str, segment: str, evidence_product: str) -> Dict[str, str]:
        """
        Generates personalized cold email draft under 120 words in manufacturer voice.
        """
        template = jinja2.Template(self.template_content)
        formatted_segment = segment.replace("_", " ")
        body = template.render(
            brand_name=brand_name,
            evidence_segment=formatted_segment,
            evidence_product=evidence_product
        )

        subject = f"Custom Apparel Manufacturing Partnership for {brand_name}"
        return {
            "subject": subject,
            "body": body.strip()
        }
