"""Pure helpers for spatial validation and proxy-label calibration.

The functions in this module deliberately avoid application I/O. They support
the local model-development workflow and do not turn the biomethane screening
score into a probability of project viability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    fbeta_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold


EPSILON = 1e-9


class ScoreCalibrator(Protocol):
    def predict(self, scores: np.ndarray) -> np.ndarray: ...


@dataclass
class _SigmoidCalibrator:
    model: LogisticRegression

    def predict(self, scores: np.ndarray) -> np.ndarray:
        values = np.asarray(scores, dtype=float).reshape(-1, 1)
        return self.model.predict_proba(values)[:, 1]


@dataclass
class _IsotonicCalibrator:
    model: IsotonicRegression

    def predict(self, scores: np.ndarray) -> np.ndarray:
        values = np.asarray(scores, dtype=float).reshape(-1)
        return np.asarray(self.model.predict(values), dtype=float)


def _binary(values: pd.Series | np.ndarray) -> np.ndarray:
    labels = np.asarray(values, dtype=int).reshape(-1)
    unique = set(np.unique(labels).tolist())
    if not unique <= {0, 1} or len(unique) < 2:
        raise ValueError("Both binary classes are required.")
    return labels


def spatial_groups(
    frame: pd.DataFrame,
    *,
    block_size_m: int = 100_000,
    x_col: str = "X_LLC",
    y_col: str = "Y_LLC",
) -> pd.Series:
    """Assign coordinate-only projected blocks without border leakage."""
    if block_size_m <= 0:
        raise ValueError("block_size_m must be positive.")
    required = [x_col, y_col]
    missing = [column for column in required if column not in frame]
    if missing:
        raise KeyError(f"Missing spatial columns: {missing}")
    if frame[required].isna().any(axis=None):
        raise ValueError("Spatial group columns must not contain null values.")

    x_block = np.floor(pd.to_numeric(frame[x_col]) / block_size_m).astype(int)
    y_block = np.floor(pd.to_numeric(frame[y_col]) / block_size_m).astype(int)
    values = x_block.astype(str) + ":" + y_block.astype(str)
    return pd.Series(values.to_numpy(), index=frame.index, name="spatial_group")


def make_spatial_folds(
    labels: pd.Series | np.ndarray,
    groups: pd.Series | np.ndarray,
    *,
    n_splits: int = 4,
    random_state: int = 42,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return stratified, group-disjoint folds and fail on unusable folds."""
    y = _binary(labels)
    group_values = np.asarray(groups).reshape(-1)
    if len(y) != len(group_values):
        raise ValueError("labels and groups must have equal length.")
    if len(np.unique(group_values)) < n_splits:
        raise ValueError("Not enough unique spatial groups for n_splits.")

    splitter = StratifiedGroupKFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=random_state,
    )
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for train_idx, valid_idx in splitter.split(np.zeros(len(y)), y, group_values):
        if set(group_values[train_idx]) & set(group_values[valid_idx]):
            raise RuntimeError("Spatial group leakage detected.")
        if len(np.unique(y[train_idx])) < 2 or len(np.unique(y[valid_idx])) < 2:
            raise ValueError("Every spatial fold must contain both classes.")
        folds.append((train_idx, valid_idx))
    return folds


def calibration_group_split(
    labels: pd.Series | np.ndarray,
    groups: pd.Series | np.ndarray,
    *,
    n_splits: int = 3,
    validation_fold: int = 0,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    folds = make_spatial_folds(
        labels,
        groups,
        n_splits=n_splits,
        random_state=random_state,
    )
    if not 0 <= validation_fold < len(folds):
        raise ValueError("validation_fold is outside the available fold range.")
    return folds[validation_fold]


def assert_spain_quarantined(
    frame: pd.DataFrame,
    selection_index: pd.Index | np.ndarray,
    *,
    spain_col: str = "is_spain",
) -> None:
    """Fail closed if any Spanish row enters model-development operations."""
    if spain_col not in frame:
        raise KeyError(f"Missing canonical Spain flag: {spain_col}")
    selected = frame.loc[pd.Index(selection_index), spain_col].fillna(False).astype(bool)
    if selected.any():
        raise ValueError("Spain is quarantined from selection, calibration and threshold fitting.")


def bootstrap_average_precision_interval(
    labels: pd.Series | np.ndarray,
    scores: pd.Series | np.ndarray,
    *,
    n_bootstrap: int = 1_000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> dict[str, float | int]:
    """Return a deterministic stratified-bootstrap AP interval."""
    y = _binary(labels)
    raw_scores = np.asarray(scores, dtype=float).reshape(-1)
    if len(y) != len(raw_scores) or not np.isfinite(raw_scores).all():
        raise ValueError("Scores must be finite and aligned with labels.")
    if n_bootstrap <= 0 or not 0 < confidence < 1:
        raise ValueError("Invalid bootstrap count or confidence level.")

    positive_idx = np.flatnonzero(y == 1)
    negative_idx = np.flatnonzero(y == 0)
    rng = np.random.default_rng(random_state)
    samples = np.empty(n_bootstrap, dtype=float)
    for sample_id in range(n_bootstrap):
        sampled = np.concatenate(
            [
                rng.choice(positive_idx, size=len(positive_idx), replace=True),
                rng.choice(negative_idx, size=len(negative_idx), replace=True),
            ]
        )
        samples[sample_id] = average_precision_score(y[sampled], raw_scores[sampled])

    alpha = (1 - confidence) / 2
    return {
        "estimate": float(average_precision_score(y, raw_scores)),
        "lower": float(np.quantile(samples, alpha)),
        "upper": float(np.quantile(samples, 1 - alpha)),
        "confidence": float(confidence),
        "n_bootstrap": int(n_bootstrap),
    }


def calibration_eligibility(
    frame: pd.DataFrame,
    *,
    outcome_col: str,
    adjudicated_col: str | None,
) -> dict[str, object]:
    """Require adjudicated positives and negatives before probability claims."""
    if outcome_col not in frame:
        raise KeyError(f"Missing outcome column: {outcome_col}")
    if not adjudicated_col or adjudicated_col not in frame:
        return {
            "eligible": False,
            "status": "blocked_weak_labels",
            "reason": "No adjudication field is available.",
            "adjudicated_rows": 0,
            "adjudicated_positives": 0,
            "adjudicated_negatives": 0,
        }

    adjudicated = frame[adjudicated_col].fillna(False).astype(bool)
    labels = pd.to_numeric(frame.loc[adjudicated, outcome_col], errors="coerce")
    if labels.isna().any() or not set(labels.astype(int).unique()) <= {0, 1}:
        raise ValueError("Adjudicated outcomes must be binary and non-null.")
    positives = int(labels.eq(1).sum())
    negatives = int(labels.eq(0).sum())
    eligible = positives > 0 and negatives > 0
    return {
        "eligible": eligible,
        "status": "eligible" if eligible else "blocked_weak_labels",
        "reason": (
            "Adjudicated positive and negative outcomes are available."
            if eligible
            else "Adjudicated positive and negative outcomes are both required."
        ),
        "adjudicated_rows": int(len(labels)),
        "adjudicated_positives": positives,
        "adjudicated_negatives": negatives,
    }


def capacity_threshold_diagnostics(
    labels: pd.Series | np.ndarray,
    scores: pd.Series | np.ndarray,
    *,
    capacities: list[int],
) -> pd.DataFrame:
    """Describe exact top-k shortlists without promoting a binary threshold."""
    y = _binary(labels)
    raw_scores = np.asarray(scores, dtype=float).reshape(-1)
    if len(y) != len(raw_scores) or not np.isfinite(raw_scores).all():
        raise ValueError("Scores must be finite and aligned with labels.")
    if not capacities or any(int(capacity) <= 0 for capacity in capacities):
        raise ValueError("capacities must contain positive integers.")

    order = np.argsort(-raw_scores, kind="mergesort")
    rows: list[dict[str, float | int | str]] = []
    for requested_capacity in capacities:
        capacity = min(int(requested_capacity), len(y))
        selected = np.zeros(len(y), dtype=bool)
        selected[order[:capacity]] = True
        prediction = selected.astype(int)
        tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
        rows.append(
            {
                "capacity": capacity,
                "score_cutoff": float(raw_scores[order[capacity - 1]]),
                "selected_rows": capacity,
                "tn": int(tn),
                "fp": int(fp),
                "fn": int(fn),
                "tp": int(tp),
                "precision": float(precision_score(y, prediction, zero_division=0)),
                "recall": float(recall_score(y, prediction, zero_division=0)),
                "f1": float(f1_score(y, prediction, zero_division=0)),
                "f2": float(fbeta_score(y, prediction, beta=2.0, zero_division=0)),
                "status": "weak_label_reference_only",
            }
        )
    return pd.DataFrame(rows)


def fit_calibrator(
    method: str,
    scores: np.ndarray,
    labels: pd.Series | np.ndarray,
    *,
    sample_weight: np.ndarray | pd.Series | None = None,
) -> ScoreCalibrator:
    raw_scores = np.asarray(scores, dtype=float).reshape(-1)
    y = _binary(labels)
    if len(raw_scores) != len(y) or not np.isfinite(raw_scores).all():
        raise ValueError("Scores must be finite and aligned with labels.")
    weights = None if sample_weight is None else np.asarray(sample_weight, dtype=float)

    if method == "sigmoid":
        model = LogisticRegression(C=1_000.0, solver="lbfgs", random_state=42)
        model.fit(raw_scores.reshape(-1, 1), y, sample_weight=weights)
        return _SigmoidCalibrator(model)
    if method == "isotonic":
        model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        model.fit(raw_scores, y, sample_weight=weights)
        return _IsotonicCalibrator(model)
    raise ValueError(f"Unknown calibration method: {method}")


def expected_calibration_error(
    labels: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    *,
    n_bins: int = 10,
    sample_weight: np.ndarray | pd.Series | None = None,
) -> float:
    y = np.asarray(labels, dtype=int).reshape(-1)
    probability = np.clip(np.asarray(probabilities, dtype=float).reshape(-1), 0, 1)
    if n_bins <= 0 or len(y) != len(probability):
        raise ValueError("Invalid bin count or unaligned inputs.")
    weights = np.ones(len(y), dtype=float) if sample_weight is None else np.asarray(sample_weight, dtype=float)
    if len(weights) != len(y) or np.any(weights < 0):
        raise ValueError("sample_weight must be aligned and non-negative.")
    total_weight = float(weights.sum())
    if total_weight <= 0:
        raise ValueError("sample_weight must have positive total weight.")

    bin_ids = np.minimum((probability * n_bins).astype(int), n_bins - 1)
    error = 0.0
    for bin_id in range(n_bins):
        mask = bin_ids == bin_id
        if not mask.any():
            continue
        bin_weight = float(weights[mask].sum())
        observed = float(np.average(y[mask], weights=weights[mask]))
        predicted = float(np.average(probability[mask], weights=weights[mask]))
        error += (bin_weight / total_weight) * abs(observed - predicted)
    return float(error)


def select_fbeta_threshold(
    labels: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    *,
    beta: float = 2.0,
    maximum_candidates: int = 400,
) -> float:
    y = _binary(labels)
    probability = np.clip(np.asarray(probabilities, dtype=float).reshape(-1), 0, 1)
    if len(y) != len(probability) or beta <= 0:
        raise ValueError("Invalid probabilities or beta.")
    unique = np.unique(probability)
    if len(unique) > maximum_candidates:
        unique = np.unique(np.quantile(unique, np.linspace(0, 1, maximum_candidates)))
    candidates = np.unique(np.concatenate(([0.0], unique, [1.0])))

    best: tuple[float, float, float, float] | None = None
    best_threshold = 0.5
    for threshold in candidates:
        prediction = (probability >= threshold).astype(int)
        fbeta = fbeta_score(y, prediction, beta=beta, zero_division=0)
        recall = recall_score(y, prediction, zero_division=0)
        precision = precision_score(y, prediction, zero_division=0)
        key = (float(fbeta), float(recall), float(precision), -float(threshold))
        if best is None or key > best:
            best = key
            best_threshold = float(threshold)
    return best_threshold


def classification_metrics(
    labels: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    *,
    threshold: float,
    sample_weight: np.ndarray | pd.Series | None = None,
    n_bins: int = 10,
) -> dict[str, float | int]:
    y = _binary(labels)
    probability = np.clip(np.asarray(probabilities, dtype=float).reshape(-1), EPSILON, 1 - EPSILON)
    if len(y) != len(probability) or not 0 <= threshold <= 1:
        raise ValueError("Invalid probabilities or threshold.")
    weights = None if sample_weight is None else np.asarray(sample_weight, dtype=float)
    prediction = (probability >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    return {
        "rows": int(len(y)),
        "positives": int(y.sum()),
        "threshold": float(threshold),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "precision": float(precision_score(y, prediction, zero_division=0)),
        "recall": float(recall_score(y, prediction, zero_division=0)),
        "f1": float(f1_score(y, prediction, zero_division=0)),
        "f2": float(fbeta_score(y, prediction, beta=2.0, zero_division=0)),
        "average_precision": float(average_precision_score(y, probability, sample_weight=weights)),
        "roc_auc": float(roc_auc_score(y, probability, sample_weight=weights)),
        "brier": float(brier_score_loss(y, probability, sample_weight=weights)),
        "log_loss": float(log_loss(y, probability, sample_weight=weights, labels=[0, 1])),
        "ece": expected_calibration_error(y, probability, n_bins=n_bins, sample_weight=weights),
    }


def missingness_report(
    frame: pd.DataFrame,
    *,
    features: list[str],
    country_col: str,
    high_missing_threshold: float = 0.30,
) -> pd.DataFrame:
    if not 0 <= high_missing_threshold <= 1:
        raise ValueError("high_missing_threshold must be between 0 and 1.")
    missing_features = [feature for feature in features if feature not in frame]
    if missing_features or country_col not in frame:
        raise KeyError(f"Missing columns: {missing_features or [country_col]}")

    countries = sorted(frame[country_col].dropna().astype(str).unique().tolist())
    rows: list[dict[str, float | str | bool]] = []
    for feature in features:
        rate = float(frame[feature].isna().mean())
        row: dict[str, float | str | bool] = {
            "feature": feature,
            "missing_rate": rate,
            "high_missingness": bool(rate >= high_missing_threshold),
        }
        for country in countries:
            mask = frame[country_col].astype(str).eq(country)
            row[f"missing_rate_{country}"] = float(frame.loc[mask, feature].isna().mean())
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["missing_rate", "feature"], ascending=[False, True]).reset_index(drop=True)


def decide_calibration_promotion(
    *,
    raw_metrics: dict[str, float],
    calibrated_metrics: dict[str, float],
    relative_ap_tolerance: float = 0.02,
) -> dict[str, object]:
    reasons: list[str] = []
    if calibrated_metrics["brier"] >= raw_metrics["brier"] - EPSILON:
        reasons.append("brier")
    minimum_ap = raw_metrics["average_precision"] * (1 - relative_ap_tolerance)
    if calibrated_metrics["average_precision"] < minimum_ap - EPSILON:
        reasons.append("average_precision")
    return {"promote": not reasons, "reasons": reasons}

