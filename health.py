from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.entities import Alert, RiskScore, Txn

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    settings = get_settings()
    db.execute(text("SELECT 1"))
    txn_count = db.scalar(select(func.count()).select_from(Txn)) or 0
    alert_count = db.scalar(select(func.count()).select_from(Alert)) or 0
    scored_count = db.scalar(select(func.count()).select_from(RiskScore)) or 0
    model_ready = settings.model_path.exists() and scored_count > 0
    return {
        "status": "ok",
        "mode": "model+rule" if model_ready else "rule_only",
        "model_version": "xgb-v1",
        "model_file": str(settings.model_path),
        "txn_count": int(txn_count),
        "alert_count": int(alert_count),
        "scored_count": int(scored_count),
    }


@router.get("/config")
def config():
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "env": settings.env,
        "auth_mode": settings.auth_mode,
        "model_version": "xgb-v1",
        "default_page_size": settings.default_page_size,
        "max_page_size": settings.max_page_size,
        "max_export_rows": settings.max_export_rows,
    }
