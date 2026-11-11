from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.schemas.common import ORMModel


class TxnListItem(BaseModel):
    txn_id: str
    account_id: str
    ts_initiated: datetime
    amount: float
    currency: str
    direction: str
    channel: str
    category: str
    counterparty_name: str | None = None
    counterparty_country: str | None = None
    risk_score: float | None = None
    risk_level: str | None = None


class RiskOut(ORMModel):
    txn_id: str
    rule_score: float
    model_score: float
    final_score: float
    risk_level: str
    model_version: str
    rule_hits: list[str] = Field(default_factory=list)


class TxnDetail(BaseModel):
    txn_id: str
    account_id: str
    ts_initiated: datetime
    amount: float
    currency: str
    direction: str
    channel: str
    category: str
    mcc: float | None = None
    counterparty_type: str | None = None
    counterparty_name: str | None = None
    counterparty_country: str | None = None
    is_authorized: bool
    status: str
    spoofing_intensity: float
    txn_count_1h: int
    txn_count_24h: int
    txn_count_7d: int
    txn_count_30d: int
    amount_sum_24h: float
    amount_sum_7d: float
    amount_sum_30d: float
    amount_max_24h: float
    avg_amount_30d: float
    std_amount_30d: float
    amount_zscore: float
    unique_counterparties_24h: int
    unique_counterparties_7d: int
    unique_countries_7d: int
    risk: RiskOut | None = None
    alert_id: str | None = None


class TxnRiskOut(BaseModel):
    txn_id: str
    risk: RiskOut | None
    factors: list[dict] = Field(default_factory=list)
    message: str | None = None
