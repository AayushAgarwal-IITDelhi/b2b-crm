import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text, Float, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class ExhibitionDB(Base):
    __tablename__ = "exhibitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    list_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    last_crawled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    brands = relationship("BrandDB", back_populates="exhibition", cascade="all, delete-orphan")

class BrandDB(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exhibition_id: Mapped[int] = mapped_column(ForeignKey("exhibitions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    website: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    website_unresolved: Mapped[bool] = mapped_column(Boolean, default=False)
    instagram: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    qualification_status: Mapped[str] = mapped_column(String(50), default="unqualified") # qualified | rejected | needs_review | unqualified
    qualification_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_bucket: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # email | form_only | manual
    manual_search_string: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    exhibition = relationship("ExhibitionDB", back_populates="brands")
    contacts = relationship("ContactDB", back_populates="brand", cascade="all, delete-orphan")
    portfolios = relationship("PortfolioDB", back_populates="brand", cascade="all, delete-orphan")
    drafts = relationship("DraftDB", back_populates="brand", cascade="all, delete-orphan")

class FieldValueDB(Base):
    __tablename__ = "field_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False) # brand | contact | portfolio
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False) # NON-NEGOTIABLE
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    method: Mapped[str] = mapped_column(String(50), nullable=False) # parsed | regex | llm
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    __table_args__ = (
        Index("idx_field_values_entity", "entity_type", "entity_id"),
    )

class ContactDB(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False) # email | form | phone
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    role_priority: Mapped[int] = mapped_column(Integer, default=50)
    mx_status: Mapped[str] = mapped_column(String(50), default="unchecked") # ok | a-fallback | nxdomain | no-mx | unchecked
    is_third_party: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False) # NON-NEGOTIABLE

    brand = relationship("BrandDB", back_populates="contacts")
    drafts = relationship("DraftDB", back_populates="contact")

class PortfolioDB(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    segments_json: Mapped[str] = mapped_column(Text, nullable=False)
    price_tier: Mapped[str] = mapped_column(String(50), default="unknown") # budget|mid|premium|luxury|unknown
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    brand = relationship("BrandDB", back_populates="portfolios")

class DraftDB(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), nullable=False)
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft") # draft | approved | rejected | sent
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    brand = relationship("BrandDB", back_populates="drafts")
    contact = relationship("ContactDB", back_populates="drafts")

class FetchLogDB(Base):
    __tablename__ = "fetch_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class SnapshotDB(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
