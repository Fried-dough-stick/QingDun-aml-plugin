from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="analyst", nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), default="分析师", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Account(Base):
    __tablename__ = "account"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    txns: Mapped[list["Txn"]] = relationship(back_populates="account", lazy="noload")


class Txn(Base):
    __tablename__ = "txn"

    txn_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.account_id"), index=True, nullable=False)
    ts_initiated: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    direction: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    mcc: Mapped[float | None] = mapped_column(Float, nullable=True)
    counterparty_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    counterparty_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    counterparty_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_authorized: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="completed", nullable=False)
    spoofing_intensity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    txn_count_1h: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    txn_count_24h: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    txn_count_7d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    txn_count_30d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount_sum_24h: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0, nullable=False)
    amount_sum_7d: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0, nullable=False)
    amount_sum_30d: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0, nullable=False)
    amount_max_24h: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0, nullable=False)
    avg_amount_30d: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0, nullable=False)
    std_amount_30d: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    amount_zscore: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unique_counterparties_24h: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_counterparties_7d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_countries_7d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    location_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    account: Mapped[Account] = relationship(back_populates="txns", lazy="joined")
    risk: Mapped["RiskScore | None"] = relationship(back_populates="txn", uselist=False, lazy="joined")

    __table_args__ = (
        Index("ix_txn_account_ts", "account_id", "ts_initiated"),
        Index("ix_txn_channel_ts", "channel", "ts_initiated"),
    )


class RiskScore(Base):
    __tablename__ = "risk_score"

    txn_id: Mapped[str] = mapped_column(ForeignKey("txn.txn_id"), primary_key=True)
    rule_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), default="xgb-v1", nullable=False)
    rule_hits: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    txn: Mapped[Txn] = relationship(back_populates="risk")

    __table_args__ = (
        Index("ix_risk_level_score", "risk_level", "final_score"),
    )


class Alert(Base):
    __tablename__ = "alert"

    alert_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    txn_id: Mapped[str] = mapped_column(ForeignKey("txn.txn_id"), unique=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    tags: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    factors: Mapped[list["AlertFactor"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan", order_by="AlertFactor.rank", lazy="selectin"
    )
    txn: Mapped[Txn] = relationship(lazy="joined")

    __table_args__ = (
        Index("ix_alert_status_priority", "status", "priority"),
        Index("ix_alert_level_score", "risk_level", "risk_score"),
    )


class AlertFactor(Base):
    __tablename__ = "alert_factor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alert.alert_id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_label: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    shap_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), default="up", nullable=False)

    alert: Mapped[Alert] = relationship(back_populates="factors")

    __table_args__ = (
        UniqueConstraint("alert_id", "rank", name="uq_alert_factor_rank"),
    )


class Report(Base):
    __tablename__ = "report"

    report_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alert.alert_id"), index=True, nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), default="alert", nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="generated", index=True, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    alert: Mapped[Alert] = relationship(lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    object_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)


class ModelRun(Base):
    __tablename__ = "model_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON, default=dict, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvalLabel(Base):
    __tablename__ = "eval_label"

    txn_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    suspicion_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_false_positive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    laundering_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
