import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, model_validator

class ProvenanceValue(BaseModel):
    value: str
    source_url: str
    fetched_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    method: Literal["parsed", "regex", "llm"]
    confidence: float = 1.0

    @model_validator(mode="after")
    def validate_source_url(self):
        if not self.source_url or not self.source_url.strip():
            raise ValueError("Provenance field MUST have a non-empty source_url")
        return self

class BrandExtract(BaseModel):
    name: str
    profile_url: str
    website: Optional[ProvenanceValue] = None
    website_unresolved: bool = False
    instagram: Optional[ProvenanceValue] = None
    description: Optional[ProvenanceValue] = None
    country: Optional[ProvenanceValue] = None

class ContactExtract(BaseModel):
    kind: Literal["email", "form", "phone"]
    value: str
    role_priority: int = 50
    mx_status: Literal["ok", "a-fallback", "nxdomain", "no-mx", "unchecked"] = "unchecked"
    is_third_party: bool = False
    source_url: str

    @model_validator(mode="after")
    def validate_contact_source(self):
        if not self.source_url or not self.source_url.strip():
            raise ValueError("Contact MUST have a non-empty source_url")
        return self

class SourceRegistry(BaseModel):
    key: str
    name: str
    list_url: str
    render: Literal["http", "playwright", "auto"] = "http"
    brand_links: dict
    pagination: Optional[dict] = None
    profile: dict
    expected_count_hint: Optional[str] = None
    notes: Optional[str] = None
