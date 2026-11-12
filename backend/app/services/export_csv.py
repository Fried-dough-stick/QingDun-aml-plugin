from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Iterator

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.models.entities import Alert, RiskScore, Txn


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if hasattr(value, "as_tuple"):
        return f"{float(value):.2f}"
    return str(value)


def stream_transactions_csv(
    db: Session, conditions: list, max_rows: int
) -> Iterator[str]:
    header = [
        "交易ID",
        "账户ID",
        "交易时间",
        "金额",
        "币种",
        "方向",
        "渠道",
        "类别",
        "对手方",
        "风险分",
        "风险等级",
    ]
    yield "\ufeff" + ",".join(header) + "\r\n"

    stmt = (
        select(Txn, RiskScore)
        .outerjoin(
            RiskScore,
            and_(RiskScore.txn_id == Txn.txn_id, RiskScore.account_id == Txn.account_id),
        )
        .where(*conditions)
        .order_by(Txn.ts_initiated.desc())
        .limit(max_rows)
    )
    result = db.execute(stmt).yield_per(2000)
    out = io.StringIO()
    writer = csv.writer(out)
    for txn, risk in result:
        writer.writerow(
            [
                txn.txn_id,
                txn.account_id,
                _fmt(txn.ts_initiated),
                f"{float(txn.amount):.2f}",
                txn.currency,
                txn.direction,
                txn.channel,
                txn.category,
                txn.counterparty_name or "",
                f"{float(risk.final_score):.4f}" if risk else "",
                risk.risk_level if risk else "",
            ]
        )
        yield out.getvalue()
        out.seek(0)
        out.truncate(0)


def stream_alerts_csv(db: Session, conditions: list, max_rows: int) -> Iterator[str]:
    header = [
        "预警ID",
        "交易ID",
        "账户ID",
        "交易时间",
        "金额",
        "风险分",
        "风险等级",
        "优先级",
        "状态",
        "标签",
        "摘要",
    ]
    yield "\ufeff" + ",".join(header) + "\r\n"

    stmt = (
        select(Alert, Txn)
        .join(Txn, and_(Alert.txn_id == Txn.txn_id, Alert.account_id == Txn.account_id))
        .where(*conditions)
        .order_by(Alert.priority.asc())
        .limit(max_rows)
    )
    result = db.execute(stmt).yield_per(2000)
    out = io.StringIO()
    writer = csv.writer(out)
    for alert, txn in result:
        writer.writerow(
            [
                alert.alert_id,
                alert.txn_id,
                alert.account_id,
                _fmt(txn.ts_initiated),
                f"{float(txn.amount):.2f}",
                f"{alert.risk_score:.4f}",
                alert.risk_level,
                alert.priority,
                alert.status,
                "、".join(alert.tags or []),
                (alert.summary or "").replace("\n", " "),
            ]
        )
        yield out.getvalue()
        out.seek(0)
        out.truncate(0)
