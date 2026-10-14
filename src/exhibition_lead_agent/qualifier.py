import re
import os
import yaml
from typing import Tuple, Dict, Any

class BrandQualifier:
    def __init__(self, config_path: str = "config/qualify.yaml"):
        self.config_path = config_path
        self.excluded_keywords = []
        self.excluded_mega_brands = []
        self.excluded_countries = []
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.excluded_keywords = data.get("excluded_keywords", [])
                self.excluded_mega_brands = data.get("excluded_mega_brands", [])
                self.excluded_countries = data.get("excluded_countries", [])

    def qualify(self, name: str, description: str = "", country: str = "") -> Tuple[str, str]:
        """
        Returns (status, reason).
        status: qualified | rejected | needs_review
        """
        if not name or not name.strip():
            return "rejected", "Missing brand name"

        # 1. Check mega-brands with word-boundary matching
        for mega in self.excluded_mega_brands:
            pattern = rf"\b{re.escape(mega)}\b"
            if re.search(pattern, name, re.IGNORECASE):
                return "rejected", f"Excluded mega-brand matching: '{mega}'"

        desc_lower = (description or "").lower()

        # 2. Check non-apparel keywords in description/name
        combined_text = f"{name} {description or ''}".lower()
        matched_keywords = []
        for kw in self.excluded_keywords:
            kw_pattern = rf"\b{re.escape(kw)}\b"
            if re.search(kw_pattern, combined_text):
                matched_keywords.append(kw)

        if matched_keywords:
            return "rejected", f"Non-apparel brand keywords matched: {', '.join(matched_keywords)}"

        # 3. Check excluded countries
        if country and self.excluded_countries:
            for exc_c in self.excluded_countries:
                if exc_c.lower() == country.lower():
                    return "rejected", f"Excluded brand country: '{country}'"

        # 4. Check manufacturing location in excluded country -> needs_review (switching opportunity)
        if self.excluded_countries:
            for exc_c in self.excluded_countries:
                if f"made in {exc_c.lower()}" in desc_lower or f"manufactured in {exc_c.lower()}" in desc_lower:
                    return "needs_review", f"Manufactures in excluded country '{exc_c}' (potential switching opportunity)"

        return "qualified", "Brand meets all qualification criteria"
