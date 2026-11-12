from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import Alert, RiskScore, Txn
from backend.app.schemas.dashboard import (
    DashboardOut,
    DashboardSummary,
    DistributionItem,
    LatestAlert,
    TrendPoint,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _as_float(value: Decimal | float | None) -> float:
    return float(value or 0)


def _summary(db: Session) -> DashboardSummary:
    total_txns = db.scalar(select(func.count()).select_from(Txn)) or 0
    total_accounts = db.scalar(select(func.count(func.distinct(Txn.account_id)))) or 0
    total_alerts = db.scalar(select(func.count()).select_from(Alert)) or 0
    high_alerts = (
        db.scalar(select(func.count()).select_from(Alert).where(Alert.risk_level == "high")) or 0
    )
    pending_alerts = (
        db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "pending")) or 0
    )
    total_amount = db.scalar(select(func.sum(Txn.amount))) or 0
    model_version = db.scalar(select(RiskScore.model_version).limit(1)) or "xgb-v1"
    return DashboardSummary(
        total_txns=int(total_txns),
        total_accounts=int(total_accounts),
        total_alerts=int(total_alerts),
        high_alerts=int(high_alerts),
        pending_alerts=int(pending_alerts),
        total_amount=_as_float(total_amount),
        model_version=model_version,
    )


def _trend(db: Session, days: int) -> list[TrendPoint]:
    anchor = db.scalar(select(func.max(Txn.ts_initiated)))
    if anchor is None:
        return []
    if isinstance(anchor, str):
        anchor = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
    start = anchor - timedelta(days=days - 1)

    rows = db.execute(
        select(
            func.date(Txn.ts_initiated).label("day"),
            func.count().label("cnt"),
            func.sum(Txn.amount).label("amount"),
        )
        .where(Txn.ts_initiated >= start)
        .group_by(func.date(Txn.ts_initiated))
        .order_by(func.date(Txn.ts_initiated))
    ).all()
    by_day = {str(row.day): (int(row.cnt), _as_float(row.amount)) for row in rows}

    alert_rows = db.execute(
        select(func.date(Txn.ts_initiated).label("day"), func.count().label("cnt"))
        .select_from(Alert)
        .join(Txn, and_(Alert.txn_id == Txn.txn_id, Alert.account_id == Txn.account_id))
        .where(Txn.ts_initiated >= start)
        .group_by(func.date(Txn.ts_initiated))
    ).all()
    alerts_by_day = {str(row.day): int(row.cnt) for row in alert_rows}

    points: list[TrendPoint] = []
    cursor = start.date() if isinstance(start, datetime) else start
    end = anchor.date() if isinstance(anchor, datetime) else anchor
    while cursor <= end:
        key = cursor.isoformat()
        count, amount = by_day.get(key, (0, 0.0))
        points.append(
            TrendPoint(date=key, count=count, amount=amount, alerts=alerts_by_day.get(key, 0))
        )
        cursor += timedelta(days=1)
    return points


def _distribution(db: Session) -> list[DistributionItem]:
    rows = db.execute(
        select(RiskScore.risk_level, func.count().label("cnt")).group_by(RiskScore.risk_level)
    ).all()
    counts = {str(row.risk_level): int(row.cnt) for row in rows}
    return [
        DistributionItem(risk_level=level, count=counts.get(level, 0))
        for level in ("high", "mid", "low")
    ]


def _latest_alerts(db: Session, limit: int) -> list[LatestAlert]:
    rows = db.execute(
        select(Alert, Txn)
        .join(Txn, and_(Alert.txn_id == Txn.txn_id, Alert.account_id == Txn.account_id))
        .order_by(Alert.priority.asc(), Alert.created_at.desc())
        .limit(limit)
    ).all()
    return [
        LatestAlert(
            alert_id=alert.alert_id,
            txn_id=alert.txn_id,
            account_id=alert.account_id,
            ts_initiated=txn.ts_initiated,
            amount=_as_float(txn.amount),
            risk_score=alert.risk_score,
            risk_level=alert.risk_level,
            status=alert.status,
            summary=alert.summary,
        )
        for alert, txn in rows
    ]


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db)):
    return _summary(db)


@router.get("/trend", response_model=list[TrendPoint])
def trend(days: int = Query(default=30, ge=7, le=365), db: Session = Depends(get_db)):
    return _trend(db, days)


@router.get("/distribution", response_model=list[DistributionItem])
def distribution(db: Session = Depends(get_db)):
    return _distribution(db)


@router.get("/latest-alerts", response_model=list[LatestAlert])
def latest_alerts(limit: int = Query(default=8, ge=1, le=50), db: Session = Depends(get_db)):
    return _latest_alerts(db, limit)


@router.get("", response_model=DashboardOut)
def dashboard(
    days: int = Query(default=30, ge=7, le=365),
    limit: int = Query(default=8, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return DashboardOut(
        summary=_summary(db),
        trend=_trend(db, days),
        distribution=_distribution(db),
        latest_alerts=_latest_alerts(db, limit),
    )
