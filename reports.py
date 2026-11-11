from __future__ import annotations

import math
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user
from backend.app.db.session import get_db
from backend.app.middleware.audit import write_audit
from backend.app.models.entities import Account, Alert, AppUser, Report, RiskScore, Txn
from backend.app.schemas.common import Page
from backend.app.schemas.report import ReportCreate, ReportOut
from backend.app.services.report_pdf import build_report_pdf

router = APIRouter(prefix="/reports", tags=["reports"])


def _new_report_id() -> str:
    return f"RPT-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"


def _to_out(report: Report) -> ReportOut:
    return ReportOut(
        report_id=report.report_id,
        alert_id=report.alert_id,
        report_type=report.report_type,
        title=report.title,
        status=report.status,
        file_path=report.file_path,
        created_by=report.created_by,
        error=report.error,
        created_at=report.created_at,
    )


@router.post("", response_model=ReportOut, status_code=201)
def create_report(
    payload: ReportCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    alert = db.get(Alert, payload.alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    txn = db.get(Txn, alert.txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="关联交易不存在")

    report = Report(
        report_id=_new_report_id(),
        alert_id=alert.alert_id,
        report_type=payload.report_type,
        title=f"可疑交易分析报告 · {alert.alert_id}",
        status="generating",
        created_by=user.username,
    )
    db.add(report)
    db.commit()

    risk = db.get(RiskScore, alert.txn_id)
    account = db.get(Account, alert.account_id)
    account_txn_count = int(
        db.scalar(select(func.count()).select_from(Txn).where(Txn.account_id == alert.account_id)) or 0
    )
    account_total_amount = float(
        db.scalar(select(func.coalesce(func.sum(Txn.amount), 0)).where(Txn.account_id == alert.account_id))
        or 0
    )

    settings = get_settings()
    out_path = settings.report_dir / f"{report.report_id}.pdf"
    try:
        build_report_pdf(
            out_path=out_path,
            report_id=report.report_id,
            alert=alert,
            txn=txn,
            risk=risk,
            account=account,
            factors=list(alert.factors),
            account_txn_count=account_txn_count,
            account_total_amount=account_total_amount,
        )
    except Exception as exc:
        report.status = "failed"
        report.error = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"报告生成失败：{exc}") from exc

    report.status = "generated"
    report.file_path = str(out_path)
    db.commit()
    db.refresh(report)
    write_audit(db, user, "export", "report", report.report_id, request, "generate_pdf")
    return _to_out(report)


@router.get("", response_model=Page[ReportOut])
def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    alert_id: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, pattern="^(generating|generated|failed)$"),
    db: Session = Depends(get_db),
    _user: AppUser = Depends(get_current_user),
):
    settings = get_settings()
    page_size = min(page_size, settings.max_page_size)
    conditions = []
    if alert_id:
        conditions.append(Report.alert_id == alert_id)
    if status:
        conditions.append(Report.status == status)

    total = int(db.scalar(select(func.count()).select_from(Report).where(*conditions)) or 0)
    rows = db.scalars(
        select(Report)
        .where(*conditions)
        .order_by(Report.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[_to_out(item) for item in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if page_size else 0,
    )


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    _user: AppUser = Depends(get_current_user),
):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return _to_out(report)


@router.get("/{report_id}/pdf")
def download_report(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if report.status != "generated" or not report.file_path:
        raise HTTPException(status_code=409, detail="报告尚未生成完成")
    path = Path(report.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在，请重新生成")
    write_audit(db, user, "export", "report", report_id, request, "download_pdf")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{report.report_id}.pdf",
    )
