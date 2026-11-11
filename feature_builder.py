from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.ml.config import (
    BASE_DIR,
    CATEGORICAL_FEATURES,
    FEATURE_LABELS,
    FEATURE_META_PATH,
    MODEL_FEATURES,
    VELOCITY_FEATURES,
)


def default_parquet_paths() -> list[Path]:
    raw_dir = BASE_DIR / "data" / "raw"
    paths = sorted(raw_dir.glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(
            f"没有找到 parquet 文件，请把 VynFi AML-100K 的 parquet 放到 {raw_dir}"
        )
    return paths


def load_dataset(paths: list[Path | str] | None = None, limit: int | None = None) -> pd.DataFrame:
    if paths is None:
        paths = default_parquet_paths()
    frames = [pd.read_parquet(path) for path in paths]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    if "transaction_id" in df.columns:
        df = df.drop_duplicates(subset="transaction_id", keep="first").reset_index(drop=True)
    if limit:
        df = df.head(limit).copy()
    if "timestamp_initiated" in df.columns:
        df["timestamp_initiated"] = pd.to_datetime(df["timestamp_initiated"], utc=True, errors="coerce")
    return df


def fit_encoders(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    encoders: dict[str, dict[str, int]] = {}
    for column in CATEGORICAL_FEATURES:
        if column not in df.columns:
            encoders[column] = {}
            continue
        values = sorted(df[column].dropna().astype(str).unique().tolist())
        encoders[column] = {value: index for index, value in enumerate(values)}
    return encoders


def _numeric(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.astype(int)
    if series.dtype == object:
        return pd.to_numeric(series, errors="coerce").fillna(0.0)
    return series.fillna(0.0)


def build_feature_frame(
    df: pd.DataFrame,
    encoders: dict[str, dict[str, int]] | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    if encoders is None:
        encoders = fit_encoders(df)

    columns: dict[str, pd.Series] = {}
    for feature in MODEL_FEATURES:
        if feature not in df.columns:
            columns[feature] = pd.Series(0.0, index=df.index)
            continue
        if feature in CATEGORICAL_FEATURES:
            mapping = encoders.get(feature, {})
            columns[feature] = df[feature].astype(str).map(mapping).fillna(-1).astype(int)
        else:
            columns[feature] = _numeric(df[feature])

    return pd.DataFrame(columns, index=df.index, columns=MODEL_FEATURES), encoders


def fit_transform(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    return build_feature_frame(df, encoders=None)


def transform(df: pd.DataFrame, encoders: dict[str, dict[str, int]]) -> pd.DataFrame:
    return build_feature_frame(df, encoders=encoders)[0]


def save_feature_meta(
    encoders: dict[str, dict[str, int]],
    path: Path = FEATURE_META_PATH,
    *,
    rows: int,
    version: str = "xgb-v1",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "version": version,
        "features": MODEL_FEATURES,
        "feature_labels": FEATURE_LABELS,
        "categorical": encoders,
        "fill_value": 0,
        "trained_rows": int(rows),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_feature_meta(path: Path = FEATURE_META_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"特征元数据不存在：{path}，请先运行 python -m backend.ml.train")
    return json.loads(path.read_text(encoding="utf-8"))


def feature_labels() -> dict[str, str]:
    return dict(FEATURE_LABELS)


def label_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    required = ["is_suspicious"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise KeyError(f"缺少标签列：{missing}")
    return df


def prepare_scoring_frame(df: pd.DataFrame, encoders: dict[str, dict[str, int]]) -> pd.DataFrame:
    """批量打分的输入整理：解析时间、金额并生成模型矩阵。"""
    if "timestamp_initiated" in df.columns:
        df = df.copy()
        df["timestamp_initiated"] = pd.to_datetime(df["timestamp_initiated"], utc=True, errors="coerce")
    for column in VELOCITY_FEATURES:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return transform(df, encoders)
