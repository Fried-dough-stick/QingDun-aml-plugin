from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.schemas.transaction import TxnDetail


class FactorOut(BaseModel):
    rank: int
    feature: str
    feature_label: str
    value: float
    shap_value: float
    direction: str


class AlertListItem(BaseModel):
    alert_id: str
    txn_id: str
    account_id: str
    ts_initiated: datetime
    amount: float
    counterparty_name: str | None = None
    risk_score: float
    risk_level: str
    priority: int
    tags: list[str] = Field(default_factory=list)
    status: str
    summary: str | None = None
    created_at: datetime


class TimelinePoint(BaseModel):
    date: str
    count: int
    amount: float
    has_alert: bool = False


class AlertDetail(BaseModel):
    alert_id: str
    txn_id: str
    account_id: str
    risk_score: float
    risk_level: str
    priority: int
    tags: list[str] = Field(default_factory=list)
    status: str
    summary: str | None = None
    note: str | None = None
    assignee: str | None = None
    created_at: datetime
    updated_at: datetime
    txn: TxnDetail
    factors: list[FactorOut] = Field(default_factory=list)
    timeline: list[TimelinePoint] = Field(default_factory=list)


class AlertStatusUpdate(BaseModel):
    status: Literal["pending", "confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=2000)
    assignee: str | None = Field(default=None, max_length=64)


class FlowNode(BaseModel):
    name: str
    value: float
    kind: str


class FlowLink(BaseModel):
    source: str
    target: str
    value: float


class FlowOut(BaseModel):
    nodes: list[FlowNode] = Field(default_factory=list)
    links: list[FlowLink] = Field(default_factory=list)
