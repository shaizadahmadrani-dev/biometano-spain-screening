from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn


ROOT = Path(__file__).resolve().parents[1]


def test_v5_metrics_preserve_spain_quarantine_and_fail_closed_calibration():
    metrics = json.loads(
        (ROOT / "docs" / "model_benchmark_v5_metrics.json").read_text(encoding="utf-8")
    )

    assert metrics["status"] == "full_spatial_validation"
    assert metrics["outer_splits"] == 4
    assert metrics["inner_splits"] == 3
    assert metrics["selection_scope"] == ["FR", "IT", "is_spain=False"]
    assert metrics["transfer_scope"] == ["is_spain=True"]
    assert metrics["calibration"]["status"] == "blocked_weak_labels"
    assert metrics["deployment_promotion"]["promote"] is False
    assert metrics["threshold_status"] == "weak_label_reference_only"
    assert len(metrics["missingness_summary"]["near_total_missing_spain"]) == 4


def test_v5_compact_artifacts_match_the_metrics_contract():
    missingness = pd.read_csv(ROOT / "docs" / "model_benchmark_v5_missingness.csv")
    thresholds = pd.read_csv(ROOT / "docs" / "model_benchmark_v5_threshold_diagnostics.csv")
    schema = json.loads(
        (ROOT / "data" / "modeling" / "model_features.json").read_text(encoding="utf-8")
    )

    assert len(missingness) == len(schema["features"]) == 31
    assert {"X_LLC", "Y_LLC"} <= set(schema["control_columns"])
    assert missingness["review_required_over_20pp"].sum() == 12
    assert set(thresholds["status"]) == {"weak_label_reference_only"}
    assert thresholds["capacity"].tolist() == [10, 25, 50, 100, 250]


def test_v5_model_bundle_is_explicitly_a_rejected_ranking_model():
    bundle = joblib.load(
        ROOT / "models" / "benchmark_classifiers_mediterranean_proxy_v5.joblib"
    )

    assert bundle["training_countries"] == ["FR", "IT"]
    assert bundle["score_semantics"] == "ranking_score_not_probability"
    assert bundle["calibration_status"] == "blocked_weak_labels"
    assert bundle["deployment_promotion"]["promote"] is False
    assert bundle["sklearn_version"] == sklearn.__version__
    probe = pd.DataFrame(bundle["verification_probe"]["frame"])
    model = bundle["model"]
    estimator = model.named_steps["model"]
    if hasattr(estimator, "predict_proba"):
        actual = model.predict_proba(probe)[:, 1]
    else:
        actual = model.decision_function(probe)
    np.testing.assert_allclose(
        actual,
        bundle["verification_probe"]["expected_scores"],
        rtol=0,
        atol=1e-12,
    )
