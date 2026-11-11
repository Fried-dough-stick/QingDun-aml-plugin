from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

RAW_DATA_DIR = BASE_DIR / "data" / "raw"
ARTIFACT_DIR = BASE_DIR / "artifacts"
OUTPUT_DIR = BASE_DIR / "outputs"

MODEL_PATH = ARTIFACT_DIR / "xgb_model.json"
FEATURE_META_PATH = ARTIFACT_DIR / "feature_meta.json"
METRICS_PATH = ARTIFACT_DIR / "metrics.json"
MODEL_COMPARISON_PATH = ARTIFACT_DIR / "model_comparison.csv"
TOPK_PATH = ARTIFACT_DIR / "topk_precision.csv"
PR_CURVE_PATH = ARTIFACT_DIR / "pr_curve.json"

RANDOM_STATE = 42
TEST_SIZE = 0.3
TIME_CUTOFF = "2024-05-31"

XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.1,
    "eval_metric": "logloss",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
    "tree_method": "hist",
}

FINAL_SCORE_RULE_WEIGHT = 0.3
FINAL_SCORE_MODEL_WEIGHT = 0.7

RISK_HIGH = 0.8
RISK_MID = 0.5

ALERT_TOP_K = 3000
ALERT_RULE_CUTOFF = 0.67
FACTOR_TOP_N = 8

VELOCITY_FEATURES = [
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

CATEGORICAL_FEATURES = ["channel", "direction"]

MODEL_FEATURES = (
    VELOCITY_FEATURES
    + ["mcc", "spoofing_intensity", "channel", "direction", "is_authorized"]
)

FEATURE_LABELS = {
    "velocity_features.txn_count_1h": "近1小时交易笔数",
    "velocity_features.txn_count_24h": "近24小时交易笔数",
    "velocity_features.txn_count_7d": "近7天交易笔数",
    "velocity_features.txn_count_30d": "近30天交易笔数",
    "velocity_features.amount_sum_24h": "近24小时金额合计",
    "velocity_features.amount_max_24h": "近24小时单笔金额峰值",
    "velocity_features.amount_zscore": "近30天金额Z分数",
    "velocity_features.unique_counterparties_24h": "近24小时对手方数",
    "velocity_features.unique_countries_7d": "近7天国家/地区数",
    "mcc": "商户类别码MCC",
    "spoofing_intensity": "设备仿冒强度",
    "channel": "交易渠道",
    "direction": "资金方向",
    "is_authorized": "是否授权",
}

# (标签, 判定字段, 阈值, 权重)。规则只使用交易自身特征，不接触真值标签。
RULES = [
    ("未授权交易", "is_authorized", 0, 0.35),
    ("1小时交易频次≥5", "velocity_features.txn_count_1h", 5, 0.25),
    ("24小时交易频次≥8", "velocity_features.txn_count_24h", 8, 0.20),
    ("30天金额Z分数≥5", "velocity_features.amount_zscore", 5.0, 0.20),
    ("24小时金额合计≥10000", "velocity_features.amount_sum_24h", 10000.0, 0.15),
    ("24小时单笔峰值≥5000", "velocity_features.amount_max_24h", 5000.0, 0.15),
    ("24小时对手方数≥6", "velocity_features.unique_counterparties_24h", 6, 0.15),
    ("设备/环境仿冒信号", "spoofing_intensity", 0.0, 0.20),
]
