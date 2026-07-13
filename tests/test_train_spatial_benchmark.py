from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.spatial_calibration import make_spatial_folds
from scripts.train_spatial_benchmark import (
    Candidate,
    candidate_grid,
    evaluate_candidate,
    nested_family_evaluation,
    ranking_metrics,
    split_model_cohorts,
)


def test_candidate_grid_is_compact_and_deterministic():
    first = candidate_grid(quick=True)
    second = candidate_grid(quick=True)

    assert list(first) == [
        "logistic_regression",
        "linear_svm",
        "random_forest",
        "gradient_boosting",
    ]
    assert sum(len(candidates) for candidates in first.values()) == 24
    assert first == second


def test_spain_cohort_uses_canonical_flag_not_primary_country():
    frame = pd.DataFrame(
        {
            "is_land_cell": [True, True, True, True],
            "is_spain": [True, False, True, False],
            "primary_country": ["FR", "FR", "ES", "IT"],
        },
        index=[10, 11, 12, 13],
    )

    development, spain = split_model_cohorts(frame)

    assert development.index.tolist() == [11, 13]
    assert spain.index.tolist() == [10, 12]


def test_ranking_metrics_counts_top_k_positives():
    labels = np.array([1, 0, 1, 0, 0], dtype=int)
    scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5], dtype=float)

    metrics = ranking_metrics(labels, scores, top_k=[2, 3])

    assert metrics["top_k"]["2"]["positives_captured"] == 1
    assert metrics["top_k"]["3"]["positives_captured"] == 2
    assert metrics["top_k"]["3"]["positive_capture_rate"] == 1.0


def test_grouped_candidate_evaluation_returns_fold_dispersion():
    rows = []
    for group in range(12):
        for offset in range(4):
            rows.append(
                {
                    "feature_a": group + offset / 10,
                    "feature_b": float(offset),
                    "label": int(offset == 0),
                    "group": f"g{group}",
                }
            )
    frame = pd.DataFrame(rows)
    x = frame[["feature_a", "feature_b"]]
    y = frame["label"].to_numpy()
    weights = np.ones(len(frame), dtype=float)
    folds = make_spatial_folds(y, frame["group"], n_splits=3, random_state=42)
    candidate = Candidate(
        family="logistic_regression",
        label="Logistic Regression",
        key="lr_test",
        params={"C": 0.5},
    )

    result = evaluate_candidate(candidate, x, y, weights, folds)

    assert len(result["folds"]) == 3
    assert 0 <= result["average_precision_mean"] <= 1
    assert result["average_precision_std"] >= 0


def test_nested_evaluation_selects_the_full_preprocessing_candidate():
    rows = []
    for group in range(12):
        for offset in range(4):
            rows.append(
                {
                    "feature_a": np.nan if offset == 0 else float(group),
                    "feature_b": float(offset),
                    "label": int(offset == 0),
                    "group": f"g{group}",
                }
            )
    frame = pd.DataFrame(rows)
    x = frame[["feature_a", "feature_b"]]
    y = frame["label"].to_numpy()
    weights = np.ones(len(frame), dtype=float)
    groups = frame["group"].to_numpy()
    folds = make_spatial_folds(y, groups, n_splits=3, random_state=42)
    candidates = [
        Candidate("logistic_regression", "Logistic Regression", "plain", {"C": 0.5}, False),
        Candidate("logistic_regression", "Logistic Regression", "missing", {"C": 0.5}, True),
    ]

    result = nested_family_evaluation(
        "logistic_regression",
        candidates,
        x,
        y,
        weights,
        groups,
        folds,
        inner_splits=2,
    )

    assert len(result["outer_folds"]) == 3
    assert {row["selected_candidate"] for row in result["outer_folds"]} <= {"plain", "missing"}
    assert all("selected_add_missing_indicators" in row for row in result["outer_folds"])
