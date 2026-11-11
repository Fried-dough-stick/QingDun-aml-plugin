from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "青盾 2.0 反洗钱风险分析站")
        self.env = os.getenv("APP_ENV", "dev")
        self.debug = _bool("APP_DEBUG", True)
        self.secret_key = os.getenv("APP_SECRET_KEY", "dev-only-change-me")
        self.access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
        self.auth_mode = os.getenv("AUTH_MODE", "demo").strip().lower()
        self.demo_username = os.getenv("DEMO_USERNAME", "demo")
        self.demo_password = os.getenv("DEMO_PASSWORD", "demo123456")

        self.database_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'qingdun.db'}")

        self.data_dir = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
        self.model_path = Path(os.getenv("MODEL_PATH", str(BASE_DIR / "artifacts" / "xgb_model.json")))
        self.feature_meta_path = Path(
            os.getenv("FEATURE_META_PATH", str(BASE_DIR / "artifacts" / "feature_meta.json"))
        )
        self.report_dir = Path(os.getenv("REPORT_DIR", str(BASE_DIR / "outputs" / "reports")))
        self.frontend_dir = Path(os.getenv("FRONTEND_DIR", str(BASE_DIR / "frontend")))
        self.cors_origins = [
            item.strip()
            for item in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
            if item.strip()
        ]

        self.default_page_size = int(os.getenv("DEFAULT_PAGE_SIZE", "20"))
        self.max_page_size = int(os.getenv("MAX_PAGE_SIZE", "100"))
        self.max_export_rows = int(os.getenv("MAX_EXPORT_ROWS", "200000"))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
