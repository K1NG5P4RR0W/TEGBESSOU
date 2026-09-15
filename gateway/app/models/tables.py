"""Modèles ORM du schéma public (§11). Source de vérité côté application.

La création physique des tables est faite par la migration Alembic V001,
écrite pour correspondre exactement à ces modèles.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

UUIDpk = UUID(as_uuid=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    totp_secret: Mapped[bytes] = mapped_column(BYTEA)
    role: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("role IN ('admin','lead','analyst','viewer')", name="users_role_chk"),
    )


class ModuleRegistry(Base):
    __tablename__ = "module_registry"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    ordering: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    enabled_by_default: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','deprecated','disabled')", name="module_registry_status_chk"
        ),
    )


class Engagement(Base):
    __tablename__ = "engagements"
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    client: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_name: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    current_phase: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUIDpk, ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "mode IN ('pentest','bug_bounty','ctf','audit_code')", name="engagements_mode_chk"
        ),
        CheckConstraint(
            "status IN ('draft','active','paused','closed')", name="engagements_status_chk"
        ),
    )


class Authorization(Base):
    __tablename__ = "authorizations"
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, primary_key=True, server_default=text("gen_random_uuid()")
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, ForeignKey("engagements.id", ondelete="CASCADE")
    )
    source_kind: Mapped[str] = mapped_column(Text)
    document_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    program_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_text_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    content_hash: Mapped[str] = mapped_column(Text)
    storage_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDpk, ForeignKey("users.id"), nullable=True
    )
    validated_at: Mapped[dt.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    __table_args__ = (
        UniqueConstraint("engagement_id", name="authorizations_engagement_uq"),
        CheckConstraint(
            "source_kind IN ('sow','program_url','program_text')", name="authorizations_source_chk"
        ),
    )


class ForbiddenTechnique(Base):
    __tablename__ = "forbidden_techniques"
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, primary_key=True, server_default=text("gen_random_uuid()")
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, ForeignKey("engagements.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(Text)
    blocks_module: Mapped[str | None] = mapped_column(
        Text, ForeignKey("module_registry.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(Text, server_default=text("'program'"))


class ScopeEntry(Base):
    __tablename__ = "scope_entries"
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, primary_key=True, server_default=text("gen_random_uuid()")
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, ForeignKey("engagements.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    disposition: Mapped[str] = mapped_column(Text)
    chain: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("kind IN ('domain','ip','cidr','contract')", name="scope_kind_chk"),
        CheckConstraint(
            "disposition IN ('in_scope','out_of_scope','exclusion')", name="scope_disp_chk"
        ),
    )


class TrafficConfig(Base):
    __tablename__ = "traffic_configs"
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, ForeignKey("engagements.id", ondelete="CASCADE"), primary_key=True
    )
    max_rps: Mapped[Decimal] = mapped_column(Numeric, server_default=text("5"))
    max_concurrency: Mapped[int] = mapped_column(Integer, server_default=text("3"))
    delay_ms: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    allowed_window: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # TSRANGE, manipulé en SQL


class CustomHeader(Base):
    __tablename__ = "custom_headers"
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, primary_key=True, server_default=text("gen_random_uuid()")
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, ForeignKey("engagements.id", ondelete="CASCADE")
    )
    header_key: Mapped[str] = mapped_column(Text)
    header_value: Mapped[str] = mapped_column(Text)


class LLMConfig(Base):
    __tablename__ = "llm_configs"
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, primary_key=True, server_default=text("gen_random_uuid()")
    )
    scope_level: Mapped[str] = mapped_column(Text)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDpk, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDpk, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    api_key_enc: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    key_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    temperature: Mapped[Decimal] = mapped_column(Numeric, server_default=text("0.2"))
    budget_cap_usd: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    fallback_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        CheckConstraint(
            "scope_level IN ('global','engagement','user')", name="llm_configs_scope_chk"
        ),
    )


class EngagementModule(Base):
    __tablename__ = "engagement_modules"
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUIDpk, ForeignKey("engagements.id", ondelete="CASCADE"), primary_key=True
    )
    module_id: Mapped[str] = mapped_column(Text, ForeignKey("module_registry.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDpk, ForeignKey("users.id"), nullable=True
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(UUIDpk, nullable=True)
    action: Mapped[str] = mapped_column(Text)
    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    prev_hash: Mapped[str] = mapped_column(Text)
    entry_hash: Mapped[str] = mapped_column(Text)


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUIDpk)
    agent: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric)
    ts: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
