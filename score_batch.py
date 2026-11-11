"""批量打分并入队：python -m backend.ml.score_batch --parquet ..."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from xgboost import Booster, DMatrix

from backend.app.db.session import SessionLocal
from backend.app.models.entities import Alert, AlertFactor, Report, RiskScore, Txn
from backend.ml.config import (
    ALERT_RULE_CUTOFF,
    ALERT_TOP_K,
    FACTOR_TOP_N,
    FEATURE_META_PATH,
    FINAL_SCORE_MODEL_WEIGHT,
    FINAL_SCORE_RULE_WEIGHT,
    MODEL_FEATURES,
    MODEL_PATH,
    RULES,
    RISK_HIGH,
    RISK_MID,
)
from backend.ml.feature_builder import load_feature_meta, load_dataset, transform

SCORE_COLUMNS = [
    "transaction_id",
    "account_id",
    "timestamp_initiated",
    "amount",
    "currency",
    "channel",
    "direction",
    "category",
    "mcc",
    "counterparty.name",
    "is_authorized",
    "spoofing_intensity",
    "velocity_features.txn_count_1h",
    "velocity_features.txn_count_24h",
    "velocity_features.txn_count_7d",
    "velocity_features.txn_count_30d",
    "velocity_features.amount_sum_24h",
    "velocity_features.amount_max_24h",
    "velocity_features.amount_zscore",
    "velocity_features.unique_counterparties_24h",
    "velocity_features.unique_countries_7d",
]


def _load_input(paths: list[Path] | None, limit: int | None) -> pd.DataFrame:
    if paths:
        frames = []
        for path in paths:
            frames.append(pd.read_parquet(path, columns=SCORE_COLUMNS))
        df = pd.concat(frames, ignore_index=True)
        raw_rows = len(df)
        df = df.drop_duplicates(subset="transaction_id", keep="first").reset_index(drop=True)
        if raw_rows != len(df):
            print(f"按 transaction_id 去重：{raw_rows:,} → {len(df):,}")
        if limit:
            df = df.head(limit).copy()
        df["timestamp_initiated"] = pd.to_datetime(df["timestamp_initiated"], utc=True, errors="coerce")
        return df
    return load_dataset(limit=limit)


def _rule_scores(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    scores = np.zeros(len(df), dtype=np.float32)
    hits = np.zeros((len(df), len(RULES)), dtype=bool)
    for index, (_label, column, threshold, weight) in enumerate(RULES):
        if column not in df.columns:
            continue
        if column == "is_authorized":
            hit = ~df[column].astype(bool).to_numpy()
        else:
            values = pd.to_numeric(df[column], errors="coerce").fillna(0).to_numpy()
            hit = values > threshold if column == "spoofing_intensity" else values >= threshold
        hits[:, index] = hit
        scores += np.where(hit, weight, 0.0)
    return np.clip(scores, 0.0, 1.0).astype(np.float32), hits


def _rule_hits(row: pd.Series) -> list[str]:
    hits = []
    for label, column, threshold, _weight in RULES:
        if column not in row:
            continue
        if column == "is_authorized":
            if not bool(row[column]):
                hits.append(label)
            continue
        value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").fillna(0).iloc[0]
        if (value > threshold) if column == "spoofing_intensity" else (value >= threshold):
            hits.append(label)
    return hits


def _risk_level(score: float) -> str:
    if score >= RISK_HIGH:
        return "high"
    if score >= RISK_MID:
        return "mid"
    return "low"


def _alert_id(txn_id: str) -> str:
    return "ALT-" + hashlib.sha1(txn_id.encode("utf-8")).hexdigest()[:12].upper()


def _demo_status(alert_id: str) -> str:
    bucket = int(hashlib.sha1(f"{alert_id}:status".encode("utf-8")).hexdigest()[:8], 16) % 100
    return "confirmed" if bucket < 15 else "pending"


def _model_scores(df: pd.DataFrame, encoders: dict, batch_size: int) -> tuple[np.ndarray, Booster | None]:
    if not MODEL_PATH.exists():
        print(f"[降级] 模型文件不存在：{MODEL_PATH}，本次只按规则打分")
        return np.zeros(len(df), dtype=np.float32), None

    booster = Booster()
    booster.load_model(str(MODEL_PATH))
    X = transform(df, encoders)
    probs = np.zeros(len(X), dtype=np.float32)
    for start in range(0, len(X), batch_size):
        end = min(start + batch_size, len(X))
        matrix = DMatrix(X.iloc[start:end], feature_names=MODEL_FEATURES)
        probs[start:end] = booster.predict(matrix).astype(np.float32)
    return probs, booster


def _contributions(booster: Booster, X: pd.DataFrame) -> np.ndarray:
    matrix = DMatrix(X, feature_names=MODEL_FEATURES)
    return booster.predict(matrix, pred_contribs=True)


def _write_risk_scores(
    df: pd.DataFrame,
    rule: np.ndarray,
    model: np.ndarray,
    final: np.ndarray,
    hit_matrix: np.ndarray,
    reset: bool,
) -> None:
    with SessionLocal() as db:
        if reset:
            db.query(RiskScore).delete()
            db.commit()
        existing = {row[0] for row in db.execute(select(RiskScore.txn_id)).all()}
        known_txns = {row[0] for row in db.execute(select(Txn.txn_id)).all()}
        batch: list[dict] = []
        written = 0
        skipped = 0
        for i, txn_id in enumerate(df["transaction_id"].astype(str)):
            if txn_id in existing:
                continue
            if txn_id not in known_txns:
                skipped += 1
                continue
            batch.append(
                {
                    "txn_id": txn_id,
                    "rule_score": float(rule[i]),
                    "model_score": float(model[i]),
                    "final_score": float(final[i]),
                    "risk_level": _risk_level(float(final[i])),
                    "model_version": "xgb-v1",
                    "rule_hits": [RULES[j][0] for j in np.flatnonzero(hit_matrix[i])] if rule[i] > 0 else [],
                }
            )
            if len(batch) >= 20_000:
                db.bulk_insert_mappings(RiskScore, batch)
                db.commit()
                written += len(batch)
                batch.clear()
        if batch:
            db.bulk_insert_mappings(RiskScore, batch)
            db.commit()
            written += len(batch)
    print(f"risk_score 写入 {written:,} 行（已存在则跳过，txn 表缺失 {skipped:,} 行）")


def _write_alerts(
    df: pd.DataFrame,
    selected: np.ndarray,
    X_all: pd.DataFrame,
    rule: np.ndarray,
    model: np.ndarray,
    final: np.ndarray,
    booster: Booster | None,
    reset: bool,
) -> None:
    with SessionLocal() as db:
        if reset:
            db.query(Report).delete()
            db.query(AlertFactor).delete()
            db.query(Alert).delete()
            db.commit()

        existing = {row[0] for row in db.execute(select(Alert.alert_id)).all()}
        selected_df = df.iloc[selected].reset_index(drop=True)
        X_selected = X_all.iloc[selected].reset_index(drop=True)
        meta = load_feature_meta(FEATURE_META_PATH)
        labels_map = meta["feature_labels"]

        if booster is not None and len(selected_df):
            contribs = _contributions(booster, X_selected)
        else:
            contribs = None

        order = np.argsort(-final[selected])
        rank_of = {int(pos): rank + 1 for rank, pos in enumerate(order)}

        valid_txn_ids: set[str] = set()
        txn_ids = selected_df["transaction_id"].astype(str).tolist()
        for start in range(0, len(txn_ids), 500):
            chunk = txn_ids[start : start + 500]
            valid_txn_ids.update(row[0] for row in db.execute(select(Txn.txn_id).where(Txn.txn_id.in_(chunk))).all())
        missing = len(txn_ids) - len(valid_txn_ids)
        if missing:
            print(f"[警告] {missing} 条候选交易不在 txn 表中，已跳过；请先执行数据入库")

        alert_rows: list[dict] = []
        factor_rows: list[dict] = []
        for pos, row in selected_df.iterrows():
            txn_id = str(row["transaction_id"])
            if txn_id not in valid_txn_ids:
                continue
            alert_id = _alert_id(txn_id)
            if alert_id in existing:
                continue
            hits = _rule_hits(row)
            factor_pairs: list[tuple[str, float, float, str]] = []
            if contribs is not None:
                contrib = contribs[pos][:-1]
                order_idx = np.argsort(-np.abs(contrib))[:FACTOR_TOP_N]
                for feature_idx in order_idx:
                    feature = MODEL_FEATURES[int(feature_idx)]
                    value = float(X_selected.iloc[pos][feature])
                    shap_value = float(contrib[int(feature_idx)])
                    factor_pairs.append((feature, value, shap_value, "up" if shap_value >= 0 else "down"))
            else:
                for feature in MODEL_FEATURES[:FACTOR_TOP_N]:
                    factor_pairs.append((feature, float(X_selected.iloc[pos][feature]), 0.0, "up"))

            labels = [labels_map.get(f, f) for f, *_ in factor_pairs[:3]]
            alert_rows.append(
                {
                    "alert_id": alert_id,
                    "txn_id": txn_id,
                    "account_id": str(row["account_id"]),
                    "risk_score": round(float(final[selected[pos]]), 6),
                    "risk_level": _risk_level(float(final[selected[pos]])),
                    "priority": rank_of[pos],
                    "tags": labels,
                    "status": _demo_status(alert_id),
                    "summary": (
                        f"账户 {str(row['account_id'])[:8]} 单笔 {float(row['amount']):,.2f} "
                        f"{row.get('currency', 'USD')}，综合风险 {float(final[selected[pos]]):.3f}。"
                        + (f"命中规则：{'、'.join(hits)}。" if hits else "未命中硬规则，由模型排序入队。")
                    ),
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            for rank, (feature, value, shap_value, direction) in enumerate(factor_pairs, start=1):
                factor_rows.append(
                    {
                        "alert_id": alert_id,
                        "rank": rank,
                        "feature": feature,
                        "feature_label": labels_map.get(feature, feature),
                        "value": value,
                        "shap_value": shap_value,
                        "direction": direction,
                    }
                )

        db.bulk_insert_mappings(Alert, alert_rows)
        db.commit()
        db.bulk_insert_mappings(AlertFactor, factor_rows)
        db.commit()

    print(f"alert 写入 {len(alert_rows):,} 条，alert_factor 写入 {len(factor_rows):,} 条")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量打分、写 risk_score 并生成预警队列")
    parser.add_argument("--parquet", nargs="*", default=None)
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=ALERT_TOP_K)
    parser.add_argument("--rule-cutoff", type=float, default=ALERT_RULE_CUTOFF)
    parser.add_argument("--batch-size", type=int, default=50_000)
    parser.add_argument("--reset", action="store_true", help="清空 risk_score/alert/factor/report 后重写")
    parser.add_argument("--no-risk", action="store_true", help="不写 risk_score，只生成预警")
    args = parser.parse_args()

    meta = load_feature_meta(FEATURE_META_PATH)
    encoders = meta["categorical"]
    missing = sorted(set(meta["features"]) - set(MODEL_FEATURES))
    if missing:
        raise ValueError(f"feature_meta 与代码特征不一致：{missing}")

    paths = [Path(item) for item in args.parquet] if args.parquet else None
    df = _load_input(paths, args.max_rows or None)
    print(f"待打分：{len(df):,} 行")

    rule, hit_matrix = _rule_scores(df)
    model, booster = _model_scores(df, encoders, args.batch_size)
    final = FINAL_SCORE_RULE_WEIGHT * rule + FINAL_SCORE_MODEL_WEIGHT * model
    final = np.clip(final, 0.0, 1.0).astype(np.float32)

    if not args.no_risk:
        _write_risk_scores(df, rule, model, final, hit_matrix, args.reset)

    top_k = min(args.top_k, len(df))
    top_idx = np.argsort(-final)[:top_k]
    rule_idx = np.where(rule >= args.rule_cutoff)[0]
    selected = np.unique(np.concatenate([top_idx, rule_idx]))
    print(f"入队：top {top_k:,} + 规则≥{args.rule_cutoff} 共 {len(selected):,} 条")

    X_all = transform(df, encoders)
    _write_alerts(df, selected, X_all, rule, model, final, booster, args.reset)

    counts = {}
    with SessionLocal() as db:
        for level, count in db.execute(select(Alert.risk_level, func.count()).group_by(Alert.risk_level)).all():
            counts[level] = int(count)
        status_total = int(db.scalar(select(func.count()).select_from(Alert)) or 0)
    print(f"预警总数 {status_total:,}，风险分布 {json.dumps(counts, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
