"""训练与离线评估入口：python -m backend.ml.train"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    matthews_corrcoef,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier

from backend.ml.config import (
    ARTIFACT_DIR,
    FEATURE_META_PATH,
    METRICS_PATH,
    MODEL_COMPARISON_PATH,
    MODEL_FEATURES,
    MODEL_PATH,
    PR_CURVE_PATH,
    RANDOM_STATE,
    TEST_SIZE,
    TIME_CUTOFF,
    TOPK_PATH,
    XGB_PARAMS,
)
from backend.ml.feature_builder import (
    fit_encoders,
    load_dataset,
    save_feature_meta,
    transform,
)


def _evaluate(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    return {
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "pr_auc": round(float(average_precision_score(y_true, y_prob)), 4),
        "mcc": round(float(matthews_corrcoef(y_true, y_pred)), 4),
    }


def _weights(y: np.ndarray) -> float:
    positive = int(y.sum())
    negative = int(len(y) - positive)
    return max(negative / max(positive, 1), 1.0)


def _fit_xgb(X_train: pd.DataFrame, y_train: np.ndarray) -> XGBClassifier:
    model = XGBClassifier(**{**XGB_PARAMS, "scale_pos_weight": _weights(y_train)})
    model.fit(X_train, y_train)
    return model


def _split_group(df: pd.DataFrame):
    splitter = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE)
    train_idx, test_idx = next(splitter.split(df, groups=df["account_id"]))
    return df.iloc[train_idx], df.iloc[test_idx]


def _split_time(df: pd.DataFrame):
    cutoff = pd.Timestamp(TIME_CUTOFF, tz="UTC")
    train = df[df["timestamp_initiated"] <= cutoff]
    test = df[df["timestamp_initiated"] > cutoff]
    if len(train) == 0 or len(test) == 0:
        raise ValueError(f"时间切分失败：cutoff={TIME_CUTOFF}，训练 {len(train)} 行，测试 {len(test)} 行")
    return train, test


def _train_comparison(train: pd.DataFrame, test: pd.DataFrame, skip_mlp: bool):
    encoders = fit_encoders(train)
    X_train = transform(train, encoders)
    X_test = transform(test, encoders)
    y_train = train["is_suspicious"].astype(int).to_numpy()
    y_test = test["is_suspicious"].astype(int).to_numpy()

    xgb_model = _fit_xgb(X_train, y_train)
    models: list[tuple[str, object]] = [
        (
            "逻辑回归",
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE),
        ),
        (
            "随机森林",
            RandomForestClassifier(
                n_estimators=100,
                class_weight="balanced_subsample",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            ),
        ),
        ("XGBoost", xgb_model),
    ]

    if not skip_mlp:
        rng = np.random.default_rng(RANDOM_STATE)
        cap = min(len(X_train), 60_000)
        sample_idx = rng.choice(len(X_train), size=cap, replace=False) if len(X_train) > cap else np.arange(len(X_train))
        models.append(
            (
                "多层感知机",
                MLPClassifier(
                    hidden_layer_sizes=(64, 32),
                    max_iter=60,
                    early_stopping=True,
                    random_state=RANDOM_STATE,
                ),
            )
        )
        mlp_X, mlp_y = X_train.iloc[sample_idx], y_train[sample_idx]
    else:
        mlp_X = mlp_y = None

    rows: list[dict] = []
    for name, model in models:
        if name == "多层感知机":
            model.fit(mlp_X, mlp_y)
        elif name != "XGBoost":
            model.fit(X_train, y_train)
        prob = model.predict_proba(X_test)[:, 1]
        metrics = _evaluate(y_test, prob)
        rows.append({"模型": name, "划分": "按账户分组", **metrics})
        print(f"[分组切分] {name}: F1={metrics['f1']} AUC={metrics['auc']} PR-AUC={metrics['pr_auc']} MCC={metrics['mcc']}")

    return rows, xgb_model, X_test, y_test, xgb_model.predict_proba(X_test)[:, 1]


def _topk(y_true: np.ndarray, y_prob: np.ndarray) -> list[dict]:
    order = np.argsort(y_prob)[::-1]
    total_positive = int(y_true.sum())
    rows = []
    for k in [50, 100, 200, 500, 1000, 2000, 5000]:
        k = min(k, len(y_true))
        hit = int(y_true[order[:k]].sum())
        rows.append(
            {
                "K": k,
                "命中可疑数": hit,
                "召回率": round(hit / total_positive, 4) if total_positive else 0.0,
                "精确率": round(hit / k, 4),
            }
        )
    return rows


def _pr_curve(y_true: np.ndarray, y_prob: np.ndarray) -> list[dict]:
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    step = max(len(precision) // 200, 1)
    points = []
    for i in range(0, len(precision), step):
        points.append(
            {
                "precision": round(float(precision[i]), 4),
                "recall": round(float(recall[i]), 4),
                "threshold": round(float(thresholds[min(i, len(thresholds) - 1)]), 6),
            }
        )
    return points


def main() -> None:
    parser = argparse.ArgumentParser(description="训练 XGBoost 并生成离线对比指标")
    parser.add_argument("--parquet", nargs="*", default=None, help="parquet 文件路径，默认读 data/raw/*.parquet")
    parser.add_argument("--max-rows", type=int, default=0, help="只取前 N 行，0 表示全部")
    parser.add_argument("--skip-mlp", action="store_true", help="跳过最慢的多层感知机")
    args = parser.parse_args()

    paths = [Path(item) for item in args.parquet] if args.parquet else None
    df = load_dataset(paths, limit=args.max_rows or None)
    required = set(MODEL_FEATURES + ["is_suspicious", "account_id", "transaction_id", "timestamp_initiated"])
    missing = sorted(required - set(df.columns))
    if missing:
        raise KeyError(f"数据缺少字段：{missing}")

    positive = int(df["is_suspicious"].sum())
    print(f"数据：{len(df):,} 行，可疑 {positive} 行（{positive / len(df):.4%}），账户 {df.account_id.nunique():,}")

    train_g, test_g = _split_group(df)
    print(f"按账户分组切分：训练 {len(train_g):,}，测试 {len(test_g):,}")
    comparison, xgb_group, X_test_group, y_test_group, prob_group = _train_comparison(
        train_g, test_g, args.skip_mlp
    )

    time_metrics = None
    time_rows = None
    try:
        train_t, test_t = _split_time(df)
        print(f"时间切分（≤{TIME_CUTOFF}）：训练 {len(train_t):,}，测试 {len(test_t):,}")
        enc_t = fit_encoders(train_t)
        X_train_t, X_test_t = transform(train_t, enc_t), transform(test_t, enc_t)
        y_train_t = train_t["is_suspicious"].astype(int).to_numpy()
        y_test_t = test_t["is_suspicious"].astype(int).to_numpy()
        xgb_time = _fit_xgb(X_train_t, y_train_t)
        time_metrics = _evaluate(y_test_t, xgb_time.predict_proba(X_test_t)[:, 1])
        time_rows = len(train_t), len(test_t)
        comparison.append({"模型": "XGBoost", "划分": f"时间切分≤{TIME_CUTOFF}", **time_metrics})
        print(
            f"[时间切分] XGBoost: F1={time_metrics['f1']} AUC={time_metrics['auc']} "
            f"PR-AUC={time_metrics['pr_auc']} MCC={time_metrics['mcc']}"
        )
    except ValueError as exc:
        print(f"[跳过时间切分] {exc}")

    topk = _topk(y_test_group, prob_group)
    pr_points = _pr_curve(y_test_group, prob_group)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(comparison).to_csv(MODEL_COMPARISON_PATH, index=False, encoding="utf-8-sig")
    pd.DataFrame(topk).to_csv(TOPK_PATH, index=False, encoding="utf-8-sig")
    PR_CURVE_PATH.write_text(json.dumps(pr_points, ensure_ascii=False), encoding="utf-8")

    # 生产模型用全量数据重训，写库前不再有“未见类别”问题。
    encoders = fit_encoders(df)
    X_full = transform(df, encoders)
    y_full = df["is_suspicious"].astype(int).to_numpy()
    xgb_full = _fit_xgb(X_full, y_full)
    xgb_full.get_booster().save_model(MODEL_PATH)
    save_feature_meta(encoders, FEATURE_META_PATH, rows=len(df))

    metrics = {
        "model_version": "xgb-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": {
            "rows": int(len(df)),
            "accounts": int(df["account_id"].nunique()),
            "suspicious": positive,
            "suspicious_rate": round(positive / len(df), 6),
            "time_start": str(df["timestamp_initiated"].min()),
            "time_end": str(df["timestamp_initiated"].max()),
        },
        "features": MODEL_FEATURES,
        "xgb_params": {key: value for key, value in XGB_PARAMS.items() if key != "n_jobs"},
        "group_split": {
            "train_rows": int(len(train_g)),
            "test_rows": int(len(test_g)),
            "metrics": comparison[2] | {"模型": "XGBoost"},
        },
        "time_split": (
            {
                "cutoff": TIME_CUTOFF,
                "train_rows": int(time_rows[0]),
                "test_rows": int(time_rows[1]),
                "metrics": time_metrics,
            }
            if time_metrics
            else {"cutoff": TIME_CUTOFF, "skipped": "当前数据量下单侧为空"}
        ),
        "topk": topk,
        "notes": [
            "按账户分组切分用于评估，避免同一账户同时出现在训练和测试。",
            "生产模型使用全量数据重训，feature_meta.json 的编码映射也来自全量数据。",
            "分类指标阈值固定 0.5；业务风险等级另按 final_score 的 0.8/0.5 划分。",
        ],
    }
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"模型：{MODEL_PATH}")
    print(f"特征元数据：{FEATURE_META_PATH}")
    print(f"指标：{METRICS_PATH}")


if __name__ == "__main__":
    main()
