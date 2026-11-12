from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user
from backend.app.db.session import get_db
from backend.app.middleware.audit import write_audit
from backend.app.models.entities import Alert, AppUser, RiskScore, Txn
from backend.app.api.transactions import _txn_detail
from backend.app.schemas.alert import (
    AlertDetail,
    AlertListItem,
    AlertStatusUpdate,
    FactorOut,
    FlowLink,
    FlowNode,
    FlowOut,
    TimelinePoint,
)
from backend.app.schemas.common import Page

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _f(value: Decimal | float | None) -> float:
    return float(value or 0)


def _conditions(
    risk_level: str | None,
    status: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    q: str | None,
):
    conditions = []
    if risk_level:
        conditions.append(Alert.risk_level == risk_level)
    if status:
        conditions.append(Alert.status == status)
    if date_from:
        conditions.append(Txn.ts_initiated >= date_from)
    if date_to:
        conditions.append(Txn.ts_initiated <= date_to)
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                Alert.alert_id.ilike(like),
                Alert.txn_id.ilike(like),
                Alert.account_id.ilike(like),
                Txn.counterparty_name.ilike(like),
            )
        )
    return conditions


@router.get("", response_model=Page[AlertListItem])
def list_alerts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    risk_level: str | None = Query(default=None, pattern="^(high|mid|low)$"),
    status: str | None = Query(default=None, pattern="^(pending|confirmed|dismissed)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = Query(default=None, max_length=64),
    sort: str = Query(default="priority", pattern="^(priority|risk_desc|time_desc)$"),
    db: Session = Depends(get_db),
    _user: AppUser = Depends(get_current_user),
):
    settings = get_settings()
    page_size = min(page_size, settings.max_page_size)
    conditions = _conditions(risk_level, status, date_from, date_to, q)

    total = int(
        db.scalar(
            select(func.count())
            .select_from(Alert)
            .join(
                Txn,
                and_(Alert.txn_id == Txn.txn_id, Alert.account_id == Txn.account_id),
            )
            .where(*conditions)
        )
        or 0
    )

    order_by = {
        "priority": (Alert.priority.asc(), Alert.created_at.desc()),
        "risk_desc": (Alert.risk_score.desc(), Alert.priority.asc()),
        "time_desc": (Txn.ts_initiated.desc(), Alert.priority.asc()),
    }[sort]

    rows = db.execute(
        select(Alert, Txn)
        .join(Txn, and_(Alert.txn_id == Txn.txn_id, Alert.account_id == Txn.account_id))
        .where(*conditions)
        .order_by(*order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        AlertListItem(
            alert_id=alert.alert_id,
            txn_id=alert.txn_id,
            account_id=alert.account_id,
            ts_initiated=txn.ts_initiated,
            amount=_f(txn.amount),
            counterparty_name=txn.counterparty_name,
            risk_score=alert.risk_score,
            risk_level=alert.risk_level,
            priority=alert.priority,
            tags=alert.tags or [],
            status=alert.status,
            summary=alert.summary,
            created_at=alert.created_at,
        )
        for alert, txn in rows
    ]
    return Page(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if page_size else 0,
    )


def _timeline(db: Session, account_id: str, anchor: datetime, days: int) -> list[TimelinePoint]:
    start = anchor - timedelta(days=days - 1)
    rows = db.execute(
        select(
            func.date(Txn.ts_initiated).label("day"),
            func.count().label("cnt"),
            func.sum(Txn.amount).label("amount"),
        )
        .where(Txn.account_id == account_id, Txn.ts_initiated >= start, Txn.ts_initiated <= anchor)
        .group_by(func.date(Txn.ts_initiated))
        .order_by(func.date(Txn.ts_initiated))
    ).all()
    by_day = {str(row.day): (int(row.cnt), _f(row.amount)) for row in rows}

    points: list[TimelinePoint] = []
    cursor = start.date() if isinstance(start, datetime) else start
    end = anchor.date() if isinstance(anchor, datetime) else anchor
    alert_day = end.isoformat()
    while cursor <= end:
        key = cursor.isoformat()
        count, amount = by_day.get(key, (0, 0.0))
        points.append(
            TimelinePoint(date=key, count=count, amount=amount, has_alert=key == alert_day)
        )
        cursor += timedelta(days=1)
    return points


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(
    alert_id: str,
    request: Request,
    days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    txn = db.get(Txn, (alert.txn_id, alert.account_id))
    if txn is None:
        raise HTTPException(status_code=404, detail="关联交易不存在")
    risk = db.get(RiskScore, (alert.txn_id, alert.account_id))
    write_audit(db, user, "view", "alert", alert_id, request)

    detail = _txn_detail(db, txn, risk, alert)
    return AlertDetail(
        alert_id=alert.alert_id,
        txn_id=alert.txn_id,
        account_id=alert.account_id,
        risk_score=alert.risk_score,
        risk_level=alert.risk_level,
        priority=alert.priority,
        tags=alert.tags or [],
        status=alert.status,
        summary=alert.summary,
        note=alert.note,
        assignee=alert.assignee,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        txn=detail,
        factors=[
            FactorOut(
                rank=f.rank,
                feature=f.feature,
                feature_label=f.feature_label,
                value=f.value,
                shap_value=f.shap_value,
                direction=f.direction,
            )
            for f in alert.factors
        ],
        timeline=_timeline(db, alert.account_id, txn.ts_initiated, days),
    )


@router.get("/{alert_id}/factors", response_model=list[FactorOut])
def get_factors(alert_id: str, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    return [
        FactorOut(
            rank=f.rank,
            feature=f.feature,
            feature_label=f.feature_label,
            value=f.value,
            shap_value=f.shap_value,
            direction=f.direction,
        )
        for f in alert.factors
    ]


@router.get("/{alert_id}/timeline", response_model=list[TimelinePoint])
def get_timeline(
    alert_id: str,
    days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    txn = db.get(Txn, (alert.txn_id, alert.account_id))
    if txn is None:
        raise HTTPException(status_code=404, detail="关联交易不存在")
    return _timeline(db, alert.account_id, txn.ts_initiated, days)


@router.get("/{alert_id}/flow", response_model=FlowOut)
def get_flow(alert_id: str, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")

    rows = db.execute(
        select(Txn.category, Txn.counterparty_name, func.sum(Txn.amount).label("amount"))
        .where(Txn.account_id == alert.account_id, Txn.direction == "outbound")
        .group_by(Txn.category, Txn.counterparty_name)
        .order_by(func.sum(Txn.amount).desc())
        .limit(40)
    ).all()
    if not rows:
        rows = db.execute(
            select(Txn.category, Txn.counterparty_name, func.sum(Txn.amount).label("amount"))
            .where(Txn.account_id == alert.account_id)
            .group_by(Txn.category, Txn.counterparty_name)
            .order_by(func.sum(Txn.amount).desc())
            .limit(40)
        ).all()

    nodes: dict[str, FlowNode] = {
        f"账户 {alert.account_id[:8]}": FlowNode(
            name=f"账户 {alert.account_id[:8]}", value=0, kind="account"
        )
    }
    links: list[FlowLink] = []
    category_totals: dict[str, float] = {}
    for category, counterparty, amount in rows:
        value = _f(amount)
        category = category or "未分类"
        counterparty = counterparty or "未知对手方"
        category_key = f"类别 {category}"
        counterparty_key = f"对手方 {counterparty}"
        nodes.setdefault(category_key, FlowNode(name=category_key, value=0, kind="category"))
        nodes.setdefault(counterparty_key, FlowNode(name=counterparty_key, value=0, kind="counterparty"))
        nodes[category_key].value += value
        nodes[counterparty_key].value += value
        category_totals[category] = category_totals.get(category, 0) + value
        links.append(FlowLink(source=f"账户 {alert.account_id[:8]}", target=category_key, value=value))
        links.append(FlowLink(source=category_key, target=counterparty_key, value=value))

    nodes[f"账户 {alert.account_id[:8]}"].value = sum(category_totals.values())
    return FlowOut(nodes=list(nodes.values()), links=links)


@router.patch("/{alert_id}/status", response_model=AlertDetail)
def update_status(
    alert_id: str,
    payload: AlertStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    alert.status = payload.status
    if payload.note is not None:
        alert.note = payload.note
    if payload.assignee is not None:
        alert.assignee = payload.assignee
    db.commit()
    db.refresh(alert)
    write_audit(db, user, "dispose", "alert", alert_id, request, f"status={payload.status}")
    return get_alert(alert_id, request, 30, db, user)
