from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user
from backend.app.db.session import get_db
from backend.app.middleware.audit import write_audit
from backend.app.models.entities import Alert, AppUser, RiskScore, Txn
from backend.app.schemas.common import Page
from backend.app.schemas.transaction import RiskOut, TxnDetail, TxnListItem, TxnRiskOut

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _f(value: Decimal | float | None) -> float:
    return float(value or 0)


def _base_query(
    date_from: datetime | None,
    date_to: datetime | None,
    min_amount: float | None,
    max_amount: float | None,
    channel: str | None,
    direction: str | None,
    risk_level: str | None,
    q: str | None,
):
    conditions = []
    if date_from:
        conditions.append(Txn.ts_initiated >= date_from)
    if date_to:
        conditions.append(Txn.ts_initiated <= date_to)
    if min_amount is not None:
        conditions.append(Txn.amount >= min_amount)
    if max_amount is not None:
        conditions.append(Txn.amount <= max_amount)
    if channel:
        conditions.append(Txn.channel == channel)
    if direction:
        conditions.append(Txn.direction == direction)
    if risk_level:
        conditions.append(RiskScore.risk_level == risk_level)
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                Txn.txn_id.ilike(like),
                Txn.account_id.ilike(like),
                Txn.counterparty_name.ilike(like),
            )
        )
    return conditions


@router.get("", response_model=Page[TxnListItem])
def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_amount: float | None = Query(default=None, ge=0),
    max_amount: float | None = Query(default=None, ge=0),
    channel: str | None = None,
    direction: str | None = None,
    risk_level: str | None = Query(default=None, pattern="^(high|mid|low)$"),
    q: str | None = Query(default=None, max_length=64),
    sort: str = Query(default="ts_desc", pattern="^(ts_desc|ts_asc|amount_desc|risk_desc)$"),
    db: Session = Depends(get_db),
    _user: AppUser = Depends(get_current_user),
):
    settings = get_settings()
    page_size = min(page_size, settings.max_page_size)
    conditions = _base_query(
        date_from, date_to, min_amount, max_amount, channel, direction, risk_level, q
    )

    count_stmt = (
        select(func.count())
        .select_from(Txn)
        .outerjoin(RiskScore, RiskScore.txn_id == Txn.txn_id)
        .where(*conditions)
    )
    total = int(db.scalar(count_stmt) or 0)

    order_by = {
        "ts_desc": Txn.ts_initiated.desc(),
        "ts_asc": Txn.ts_initiated.asc(),
        "amount_desc": Txn.amount.desc(),
        "risk_desc": RiskScore.final_score.desc().nullslast(),
    }[sort]

    rows = db.execute(
        select(Txn, RiskScore)
        .outerjoin(RiskScore, RiskScore.txn_id == Txn.txn_id)
        .where(*conditions)
        .order_by(order_by, Txn.txn_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        TxnListItem(
            txn_id=txn.txn_id,
            account_id=txn.account_id,
            ts_initiated=txn.ts_initiated,
            amount=_f(txn.amount),
            currency=txn.currency,
            direction=txn.direction,
            channel=txn.channel,
            category=txn.category,
            counterparty_name=txn.counterparty_name,
            counterparty_country=txn.counterparty_country,
            risk_score=float(risk.final_score) if risk else None,
            risk_level=risk.risk_level if risk else None,
        )
        for txn, risk in rows
    ]
    return Page(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if page_size else 0,
    )


def _txn_detail(db: Session, txn: Txn, risk: RiskScore | None, alert: Alert | None) -> TxnDetail:
    return TxnDetail(
        txn_id=txn.txn_id,
        account_id=txn.account_id,
        ts_initiated=txn.ts_initiated,
        amount=_f(txn.amount),
        currency=txn.currency,
        direction=txn.direction,
        channel=txn.channel,
        category=txn.category,
        mcc=txn.mcc,
        counterparty_type=txn.counterparty_type,
        counterparty_name=txn.counterparty_name,
        counterparty_country=txn.counterparty_country,
        is_authorized=txn.is_authorized,
        status=txn.status,
        spoofing_intensity=txn.spoofing_intensity,
        txn_count_1h=txn.txn_count_1h,
        txn_count_24h=txn.txn_count_24h,
        txn_count_7d=txn.txn_count_7d,
        txn_count_30d=txn.txn_count_30d,
        amount_sum_24h=_f(txn.amount_sum_24h),
        amount_sum_7d=_f(txn.amount_sum_7d),
        amount_sum_30d=_f(txn.amount_sum_30d),
        amount_max_24h=_f(txn.amount_max_24h),
        avg_amount_30d=_f(txn.avg_amount_30d),
        std_amount_30d=txn.std_amount_30d,
        amount_zscore=txn.amount_zscore,
        unique_counterparties_24h=txn.unique_counterparties_24h,
        unique_counterparties_7d=txn.unique_counterparties_7d,
        unique_countries_7d=txn.unique_countries_7d,
        risk=(
            RiskOut(
                txn_id=risk.txn_id,
                rule_score=risk.rule_score,
                model_score=risk.model_score,
                final_score=risk.final_score,
                risk_level=risk.risk_level,
                model_version=risk.model_version,
                rule_hits=risk.rule_hits or [],
            )
            if risk
            else None
        ),
        alert_id=alert.alert_id if alert else None,
    )


@router.get("/{txn_id}", response_model=TxnDetail)
def get_transaction(
    txn_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    txn = db.get(Txn, txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="交易不存在")
    risk = db.get(RiskScore, txn_id)
    alert = db.scalar(select(Alert).where(Alert.txn_id == txn_id))
    write_audit(db, user, "view", "txn", txn_id, request)
    return _txn_detail(db, txn, risk, alert)


@router.get("/{txn_id}/risk", response_model=TxnRiskOut)
def get_transaction_risk(txn_id: str, db: Session = Depends(get_db)):
    risk = db.get(RiskScore, txn_id)
    if risk is None:
        return TxnRiskOut(txn_id=txn_id, risk=None, factors=[], message="该交易尚未打分")
    alert = db.scalar(select(Alert).where(Alert.txn_id == txn_id))
    factors = []
    if alert:
        factors = [
            {
                "rank": factor.rank,
                "feature": factor.feature,
                "feature_label": factor.feature_label,
                "value": factor.value,
                "shap_value": factor.shap_value,
                "direction": factor.direction,
            }
            for factor in alert.factors
        ]
    return TxnRiskOut(
        txn_id=txn_id,
        risk=RiskOut(
            txn_id=risk.txn_id,
            rule_score=risk.rule_score,
            model_score=risk.model_score,
            final_score=risk.final_score,
            risk_level=risk.risk_level,
            model_version=risk.model_version,
            rule_hits=risk.rule_hits or [],
        ),
        factors=factors,
    )
