from __future__ import annotations

import pandas as pd

from backend.ml.config import MODEL_FEATURES
from backend.ml.feature_builder import build_feature_frame, fit_encoders, transform


def _sample(channel: str = "online") -> pd.DataFrame:
    row = {feature: 0 for feature in MODEL_FEATURES}
    row.update(
        {
            "channel": channel,
            "direction": "outbound",
            "is_authorized": True,
            "velocity_features.txn_count_24h": 3,
            "velocity_features.amount_sum_24h": "123.45",
        }
    )
    return pd.DataFrame([row, row.copy()])


def test_transform_is_deterministic_and_ordered():
    df = _sample()
    encoders = fit_encoders(df)
    first = transform(df, encoders)
    second = transform(df, encoders)
    assert list(first.columns) == MODEL_FEATURES
    pd.testing.assert_frame_equal(first, second)
    assert first["velocity_features.amount_sum_24h"].iloc[0] == 123.45


def test_unseen_category_maps_to_minus_one():
    train = _sample("online")
    encoders = fit_encoders(train)
    unseen = _sample("branch_not_in_train")
    matrix = transform(unseen, encoders)
    assert matrix["channel"].iloc[0] == -1


def test_missing_feature_filled_with_zero():
    df = _sample().drop(columns=["mcc"])
    X, _ = build_feature_frame(df)
    assert X["mcc"].iloc[0] == 0
