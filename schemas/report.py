from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReportCreate(BaseModel):
    alert_id: str = Field(min_length=1, max_length=32)
    report_type: str = Field(default="alert", max_length=32)


class ReportOut(BaseModel):
    report_id: str
    alert_id: str
    report_type: str
    title: str
    status: str
    file_path: str | None = None
    created_by: str | None = None
    error: str | None = None
    created_at: datetime
