from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    total_txns: int
    total_accounts: int
    total_alerts: int
    high_alerts: int
    pending_alerts: int
    total_amount: float
    model_version: str


class TrendPoint(BaseModel):
    date: str
    count: int
    amount: float
    alerts: int = 0


class DistributionItem(BaseModel):
    risk_level: str
    count: int


class LatestAlert(BaseModel):
    alert_id: str
    txn_id: str
    account_id: str
    ts_initiated: datetime
    amount: float
    risk_score: float
    risk_level: str
    status: str
    summary: str | None = None


class DashboardOut(BaseModel):
    summary: DashboardSummary
    trend: list[TrendPoint] = Field(default_factory=list)
    distribution: list[DistributionItem] = Field(default_factory=list)
    latest_alerts: list[LatestAlert] = Field(default_factory=list)
