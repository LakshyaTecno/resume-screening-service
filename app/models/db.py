import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # All three nullable: an admin-created tenant (POST /admin/tenants)
    # never has any of these and authenticates via API key only. A
    # self-registered tenant has exactly one of hashed_password (email
    # sign-up) or google_sub (Google sign-up) set, never both. email is
    # nullable too, since admin-created tenants don't have one either.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="tenant")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256, not a slow password hash (bcrypt/argon2) - this is a random
    # high-entropy generated key, not a user-chosen password, so a slow
    # hash only adds per-request latency with no real security benefit.
    hashed_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="api_keys")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable: a candidate created by the async upload path (see
    # candidate_service.enqueue_resume_upload) starts as a placeholder row
    # with no parsed fields yet - full_name is genuinely unknown, not
    # merely a transient placeholder, until the worker parses it.
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list] = mapped_column(JSONB, default=list)
    experience: Mapped[list] = mapped_column(JSONB, default=list)
    education: Mapped[list] = mapped_column(JSONB, default=list)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinecone_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    # pending -> processing -> processed, or -> failed on a permanent parse
    # error. Defaults to "processed" so the synchronous JSON-create path
    # (create_candidate) needs no special-casing - only the async upload
    # path explicitly sets "pending".
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="processed", server_default="processed"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    matches: Mapped[list["MatchResult"]] = relationship(back_populates="candidate")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_skills: Mapped[list] = mapped_column(JSONB, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSONB, default=list)
    pinecone_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    matches: Mapped[list["MatchResult"]] = relationship(back_populates="job")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Smallest currency unit (paise, not rupees) - matches Razorpay's own
    # convention and avoids float rounding on money.
    price: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    monthly_resume_quota: Mapped[int | None] = mapped_column(nullable=True)  # None = unlimited
    # 1, 3, 6, or 12 - not enforced as an enum at the DB level, validated
    # in PlanCreate instead. Purely informational plus the fallback-window
    # math in billing_service.current_period_start; Razorpay's own Plan
    # object (razorpay_plan_id) is what actually governs billing cadence.
    duration_months: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    razorpay_plan_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # One current subscription per tenant, not a history table - a plan
    # change updates this row rather than creating a second one.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    razorpay_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped["Tenant"] = relationship()
    plan: Mapped["Plan"] = relationship()


class MatchResult(Base):
    __tablename__ = "match_results"

    # No direct tenant_id here: this row is only ever created from an
    # already tenant-scoped Job/Candidate pair (see ranking.py), and
    # nothing queries match_results directly by tenant today - it's
    # derivable via a join if that ever changes.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    vector_score: Mapped[float | None] = mapped_column(nullable=True)
    llm_score: Mapped[float | None] = mapped_column(nullable=True)
    rank: Mapped[int | None] = mapped_column(nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidate: Mapped["Candidate"] = relationship(back_populates="matches")
    job: Mapped["Job"] = relationship(back_populates="matches")
