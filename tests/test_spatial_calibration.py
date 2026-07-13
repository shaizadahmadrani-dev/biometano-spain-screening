from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.spatial_calibration import (
    assert_spain_quarantined,
    bootstrap_average_precision_interval,
    calibration_eligibility,
    calibration_group_split,
    capacity_threshold_diagnostics,
    classification_metrics,
    decide_calibration_promotion,
    expected_calibration_error,
    fit_calibrator,
    make_spatial_folds,
    missingness_report,
    select_fbeta_threshold,
    spatial_groups,
)


def _spatial_fixture() -> pd.DataFrame:
    rows = []
    for group_id in range(12):
        for offset in range(4):
            rows.append(
                {
                    "primary_country": "FR" if group_id < 6 else "IT",
                    "X_LLC": group_id * 100_000 + offset * 5_000,
                    "Y_LLC": (group_id % 3) * 100_000,
                    "label": int(offset == 0),
                }
            )
    return pd.DataFrame(rows)


def test_spatial_groups_are_deterministic_100km_blocks():
    frame = _spatial_fixture()
    first = spatial_groups(frame, block_size_m=100_000)
    second = spatial_groups(frame.sample(frac=1, random_state=7), block_size_m=100_000).sort_index()

    assert first.equals(second)
    assert first.nunique() == 12
    assert first.iloc[0] == "0:0"


def test_spatial_groups_do_not_split_cross_border_coordinate_blocks():
    frame = pd.DataFrame(
        {
            "primary_country": ["FR", "IT"],
            "X_LLC": [500_000, 500_000],
            "Y_LLC": [4_000_000, 4_000_000],
        }
    )

    groups = spatial_groups(frame)

    assert groups.nunique() == 1
    assert groups.tolist() == ["5:40", "5:40"]


def test_spatial_folds_are_group_disjoint_and_keep_both_classes():
    frame = _spatial_fixture()
    groups = spatial_groups(frame)
    folds = make_spatial_folds(frame["label"], groups, n_splits=4, random_state=11)

    assert len(folds) == 4
    for train_idx, valid_idx in folds:
        assert set(groups.iloc[train_idx]).isdisjoint(set(groups.iloc[valid_idx]))
        assert frame["label"].iloc[train_idx].nunique() == 2
        assert frame["label"].iloc[valid_idx].nunique() == 2


def test_calibration_split_is_group_disjoint_and_deterministic():
    frame = _spatial_fixture()
    groups = spatial_groups(frame)
    fit_idx, validation_idx = calibration_group_split(
        frame["label"], groups, n_splits=3, validation_fold=1, random_state=19
    )
    fit_again, validation_again = calibration_group_split(
        frame["label"], groups, n_splits=3, validation_fold=1, random_state=19
    )

    assert np.array_equal(fit_idx, fit_again)
    assert np.array_equal(validation_idx, validation_again)
    assert set(groups.iloc[fit_idx]).isdisjoint(set(groups.iloc[validation_idx]))
    assert frame["label"].iloc[fit_idx].nunique() == 2
    assert frame["label"].iloc[validation_idx].nunique() == 2


def test_calibrators_return_bounded_monotonic_probabilities():
    scores = np.array([-3, -2, -1, 0, 1, 2, 3, 4], dtype=float)
    labels = np.array([0, 0, 0, 0, 1, 1, 1, 1], dtype=int)

    for method in ("sigmoid", "isotonic"):
        calibrator = fit_calibrator(method, scores, labels)
        probabilities = calibrator.predict(scores)
        assert np.all((0 <= probabilities) & (probabilities <= 1))
        assert np.all(np.diff(probabilities) >= -1e-12)


def test_threshold_and_confusion_metrics_are_consistent():
    labels = np.array([0, 0, 1, 1, 1], dtype=int)
    probabilities = np.array([0.05, 0.40, 0.35, 0.80, 0.95])
    threshold = select_fbeta_threshold(labels, probabilities, beta=2.0)
    metrics = classification_metrics(labels, probabilities, threshold=threshold)

    assert 0 <= threshold <= 1
    assert metrics["tn"] + metrics["fp"] + metrics["fn"] + metrics["tp"] == 5
    assert metrics["recall"] >= metrics["precision"]
    assert metrics["f2"] >= metrics["f1"]


def test_expected_calibration_error_detects_miscalibration():
    labels = np.array([0, 0, 1, 1], dtype=int)
    calibrated = np.array([0.01, 0.10, 0.90, 0.99])
    reversed_probabilities = 1 - calibrated

    assert expected_calibration_error(labels, calibrated, n_bins=4) < 0.11
    assert expected_calibration_error(labels, reversed_probabilities, n_bins=4) > 0.80


def test_missingness_report_flags_high_missing_features_by_country():
    frame = pd.DataFrame(
        {
            "primary_country": ["FR", "FR", "IT", "IT"],
            "mostly_missing": [np.nan, np.nan, np.nan, 1.0],
            "complete": [1.0, 2.0, 3.0, 4.0],
        }
    )
    report = missingness_report(
        frame,
        features=["mostly_missing", "complete"],
        country_col="primary_country",
        high_missing_threshold=0.50,
    )

    mostly = report.loc[report["feature"].eq("mostly_missing")].iloc[0]
    complete = report.loc[report["feature"].eq("complete")].iloc[0]
    assert mostly["missing_rate"] == 0.75
    assert bool(mostly["high_missingness"]) is True
    assert mostly["missing_rate_FR"] == 1.0
    assert mostly["missing_rate_IT"] == 0.5
    assert complete["missing_rate"] == 0.0


def test_calibration_gate_rejects_cosmetic_improvements():
    calibration = decide_calibration_promotion(
        raw_metrics={"brier": 0.10, "average_precision": 0.20},
        calibrated_metrics={"brier": 0.11, "average_precision": 0.21},
        relative_ap_tolerance=0.02,
    )
    assert calibration["promote"] is False
    assert "brier" in calibration["reasons"]


def test_spain_quarantine_fails_closed_for_selection_rows():
    frame = pd.DataFrame(
        {
            "primary_country": ["FR", "IT", "ES"],
            "is_spain": [False, False, True],
            "value": [1, 2, 3],
        },
        index=[10, 11, 12],
    )

    assert_spain_quarantined(frame, pd.Index([10, 11]))
    try:
        assert_spain_quarantined(frame, pd.Index([10, 12]))
    except ValueError as exc:
        assert "Spain" in str(exc)
    else:
        raise AssertionError("Spain leakage must fail closed")


def test_calibration_is_blocked_without_adjudicated_negatives():
    frame = pd.DataFrame(
        {
            "weak_label": [1, 0, 0, 1],
            "adjudicated": [True, False, False, True],
        }
    )
    result = calibration_eligibility(
        frame,
        outcome_col="weak_label",
        adjudicated_col="adjudicated",
    )

    assert result["eligible"] is False
    assert result["status"] == "blocked_weak_labels"
    assert result["adjudicated_negatives"] == 0


def test_capacity_diagnostics_match_manual_top_k_confusion():
    labels = np.array([1, 0, 1, 0, 0], dtype=int)
    scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5], dtype=float)
    diagnostics = capacity_threshold_diagnostics(labels, scores, capacities=[2, 3])

    top_two = diagnostics.loc[diagnostics["capacity"].eq(2)].iloc[0]
    assert top_two["tp"] == 1
    assert top_two["fp"] == 1
    assert top_two["fn"] == 1
    assert top_two["tn"] == 2
    assert top_two["status"] == "weak_label_reference_only"


def test_bootstrap_ap_interval_is_deterministic_and_bounded():
    labels = np.array([1, 1, 1, 0, 0, 0, 0, 0], dtype=int)
    scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2])

    first = bootstrap_average_precision_interval(labels, scores, n_bootstrap=200, random_state=7)
    second = bootstrap_average_precision_interval(labels, scores, n_bootstrap=200, random_state=7)

    assert first == second
    assert 0 <= first["lower"] <= first["estimate"] <= first["upper"] <= 1
