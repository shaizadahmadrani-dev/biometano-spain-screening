"""Spatially validated biomethane benchmark with Spain held out.

Run from the repository root with the isolated model environment::

    python -m scripts.train_spatial_benchmark --input <private-table.parquet>

The script writes aggregate public-safe evidence only. The full feature table
and row-level Spanish scores remain local and ignored by git.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from scripts.spatial_calibration import (
    assert_spain_quarantined,
    bootstrap_average_precision_interval,
    calibration_eligibility,
    capacity_threshold_diagnostics,
    make_spatial_folds,
    missingness_report,
    spatial_groups,
)
from scripts.train_benchmark import (
    MED_FEATURES,
    MED_LABEL,
    MED_WEIGHT,
    SPAIN_LABEL,
    numeric_frame,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "modeling" / "biometano_grid5km_curated_v4_attributes.parquet"
DOCS = ROOT / "docs"
MODELS = ROOT / "models"
LOCAL_DATA = ROOT / "data" / "modeling"
RANDOM_STATE = 42
TOP_K = [10, 25, 50, 100, 250]

OUT_METRICS = DOCS / "model_benchmark_v5_metrics.json"
OUT_REPORT = DOCS / "model_benchmark_v5_report.md"
OUT_MISSINGNESS = DOCS / "model_benchmark_v5_missingness.csv"
OUT_THRESHOLDS = DOCS / "model_benchmark_v5_threshold_diagnostics.csv"
OUT_IMPORTANCE = DOCS / "model_benchmark_v5_feature_importance.csv"
OUT_MODEL = MODELS / "benchmark_classifiers_mediterranean_proxy_v5.joblib"
OUT_LOCAL_SCORES = LOCAL_DATA / "biometano_spain_model_benchmark_v5_scores.parquet"


@dataclass(frozen=True)
class Candidate:
    family: str
    label: str
    key: str
    params: dict[str, Any]
    add_missing_indicators: bool = False


def candidate_grid(*, quick: bool) -> dict[str, list[Candidate]]:
    trees = 80 if quick else 250
    gb_estimators = [40, 60, 80] if quick else [120, 160, 220]
    grids = {
        "logistic_regression": [
            Candidate("logistic_regression", "Logistic Regression", f"lr_c_{c}", {"C": c})
            for c in [0.05, 0.5, 2.0]
        ],
        "linear_svm": [
            Candidate("linear_svm", "Linear SVM", f"svm_c_{c}", {"C": c})
            for c in [0.05, 0.5, 2.0]
        ],
        "random_forest": [
            Candidate(
                "random_forest",
                "Random Forest",
                "rf_depth10_leaf15_sqrt",
                {"n_estimators": trees, "max_depth": 10, "min_samples_leaf": 15, "max_features": "sqrt"},
            ),
            Candidate(
                "random_forest",
                "Random Forest",
                "rf_depth14_leaf5_sqrt",
                {"n_estimators": trees, "max_depth": 14, "min_samples_leaf": 5, "max_features": "sqrt"},
            ),
            Candidate(
                "random_forest",
                "Random Forest",
                "rf_depth14_leaf15_07",
                {"n_estimators": trees, "max_depth": 14, "min_samples_leaf": 15, "max_features": 0.7},
            ),
        ],
        "gradient_boosting": [
            Candidate(
                "gradient_boosting",
                "Gradient Boosting",
                f"gb_{gb_estimators[0]}_lr005_depth2_sub085",
                {"n_estimators": gb_estimators[0], "learning_rate": 0.05, "max_depth": 2, "subsample": 0.85},
            ),
            Candidate(
                "gradient_boosting",
                "Gradient Boosting",
                f"gb_{gb_estimators[1]}_lr005_depth3_sub085",
                {"n_estimators": gb_estimators[1], "learning_rate": 0.05, "max_depth": 3, "subsample": 0.85},
            ),
            Candidate(
                "gradient_boosting",
                "Gradient Boosting",
                f"gb_{gb_estimators[2]}_lr003_depth2_sub1",
                {"n_estimators": gb_estimators[2], "learning_rate": 0.03, "max_depth": 2, "subsample": 1.0},
            ),
        ],
    }
    return {
        family: [
            Candidate(
                family=candidate.family,
                label=candidate.label,
                key=f"{candidate.key}_miss{int(add_indicators)}",
                params=candidate.params,
                add_missing_indicators=add_indicators,
            )
            for candidate in candidates
            for add_indicators in (False, True)
        ]
        for family, candidates in grids.items()
    }


def make_pipeline(candidate: Candidate) -> Pipeline:
    steps: list[tuple[str, object]] = [
        (
            "imputer",
            SimpleImputer(
                strategy="median",
                add_indicator=candidate.add_missing_indicators,
            ),
        )
    ]
    if candidate.family == "logistic_regression":
        steps.extend(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=float(candidate.params["C"]),
                        max_iter=3_000,
                        solver="lbfgs",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        )
    elif candidate.family == "linear_svm":
        steps.extend(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    LinearSVC(
                        C=float(candidate.params["C"]),
                        max_iter=10_000,
                        dual="auto",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        )
    elif candidate.family == "random_forest":
        steps.append(
            (
                "model",
                RandomForestClassifier(
                    **candidate.params,
                    n_jobs=-1,
                    random_state=RANDOM_STATE,
                ),
            )
        )
    elif candidate.family == "gradient_boosting":
        steps.append(
            (
                "model",
                GradientBoostingClassifier(
                    **candidate.params,
                    random_state=RANDOM_STATE,
                ),
            )
        )
    else:
        raise ValueError(f"Unknown model family: {candidate.family}")
    return Pipeline(steps)


def score_model(model: Pipeline, x: pd.DataFrame) -> np.ndarray:
    estimator = model.named_steps["model"]
    if hasattr(estimator, "predict_proba"):
        return np.asarray(model.predict_proba(x)[:, 1], dtype=float)
    if hasattr(estimator, "decision_function"):
        return np.asarray(model.decision_function(x), dtype=float)
    raise TypeError(f"{type(estimator).__name__} has no ranking score.")


def ranking_metrics(y: np.ndarray, scores: np.ndarray, *, top_k: list[int]) -> dict[str, Any]:
    order = np.argsort(-scores, kind="mergesort")
    positives = int(y.sum())
    top: dict[str, dict[str, float | int]] = {}
    for requested in top_k:
        k = min(int(requested), len(y))
        captured = int(y[order[:k]].sum())
        top[str(requested)] = {
            "selected": k,
            "positives_captured": captured,
            "positive_capture_rate": float(captured / positives) if positives else 0.0,
        }
    return {
        "rows": int(len(y)),
        "positives": positives,
        "prevalence": float(y.mean()),
        "average_precision": float(average_precision_score(y, scores)),
        "roc_auc": float(roc_auc_score(y, scores)),
        "top_k": top,
    }


def fit_fold(
    candidate: Candidate,
    x: pd.DataFrame,
    y: np.ndarray,
    weights: np.ndarray,
    train_idx: np.ndarray,
    valid_idx: np.ndarray,
) -> tuple[Pipeline, np.ndarray]:
    model = make_pipeline(candidate)
    model.fit(x.iloc[train_idx], y[train_idx], model__sample_weight=weights[train_idx])
    return model, score_model(model, x.iloc[valid_idx])


def evaluate_candidate(
    candidate: Candidate,
    x: pd.DataFrame,
    y: np.ndarray,
    weights: np.ndarray,
    folds: list[tuple[np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    fold_rows: list[dict[str, Any]] = []
    for fold_id, (train_idx, valid_idx) in enumerate(folds):
        _, scores = fit_fold(
            candidate,
            x,
            y,
            weights,
            train_idx,
            valid_idx,
        )
        metrics = ranking_metrics(y[valid_idx], scores, top_k=[100, 250])
        fold_rows.append({"fold": fold_id, **metrics})
    ap_values = [float(row["average_precision"]) for row in fold_rows]
    auc_values = [float(row["roc_auc"]) for row in fold_rows]
    return {
        "candidate_key": candidate.key,
        "params": candidate.params,
        "add_missing_indicators": candidate.add_missing_indicators,
        "folds": fold_rows,
        "average_precision_mean": float(np.mean(ap_values)),
        "average_precision_std": float(np.std(ap_values, ddof=0)),
        "average_precision_min": float(np.min(ap_values)),
        "roc_auc_mean": float(np.mean(auc_values)),
        "roc_auc_std": float(np.std(auc_values, ddof=0)),
    }


def select_candidate(
    candidates: list[Candidate],
    x: pd.DataFrame,
    y: np.ndarray,
    weights: np.ndarray,
    folds: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[Candidate, list[dict[str, Any]]]:
    evaluations = [evaluate_candidate(candidate, x, y, weights, folds) for candidate in candidates]
    by_key = {candidate.key: candidate for candidate in candidates}
    best = sorted(
        evaluations,
        key=lambda row: (
            -float(row["average_precision_mean"]),
            float(row["average_precision_std"]),
            -float(row["average_precision_min"]),
            str(row["candidate_key"]),
        ),
    )[0]
    return by_key[str(best["candidate_key"])], evaluations


def nested_family_evaluation(
    family: str,
    candidates: list[Candidate],
    x: pd.DataFrame,
    y: np.ndarray,
    weights: np.ndarray,
    groups: np.ndarray,
    outer_folds: list[tuple[np.ndarray, np.ndarray]],
    *,
    inner_splits: int,
) -> dict[str, Any]:
    outer_rows: list[dict[str, Any]] = []
    for outer_id, (train_idx, valid_idx) in enumerate(outer_folds):
        print(f"[{family}] outer fold {outer_id + 1}/{len(outer_folds)}", flush=True)
        inner_folds = make_spatial_folds(
            y[train_idx],
            groups[train_idx],
            n_splits=inner_splits,
            random_state=RANDOM_STATE + outer_id + 1,
        )
        selected, inner_evaluations = select_candidate(
            candidates,
            x.iloc[train_idx].reset_index(drop=True),
            y[train_idx],
            weights[train_idx],
            inner_folds,
        )
        _, scores = fit_fold(
            selected,
            x,
            y,
            weights,
            train_idx,
            valid_idx,
        )
        outer_rows.append(
            {
                "fold": outer_id,
                "selected_candidate": selected.key,
                "selected_params": selected.params,
                "selected_add_missing_indicators": selected.add_missing_indicators,
                "inner_selection": inner_evaluations,
                **ranking_metrics(y[valid_idx], scores, top_k=[100, 250]),
            }
        )

    ap_values = [float(row["average_precision"]) for row in outer_rows]
    auc_values = [float(row["roc_auc"]) for row in outer_rows]
    return {
        "family": family,
        "label": candidates[0].label,
        "outer_folds": outer_rows,
        "outer_average_precision_mean": float(np.mean(ap_values)),
        "outer_average_precision_std": float(np.std(ap_values, ddof=0)),
        "outer_average_precision_min": float(np.min(ap_values)),
        "outer_roc_auc_mean": float(np.mean(auc_values)),
        "outer_roc_auc_std": float(np.std(auc_values, ddof=0)),
    }


def missingness_artifact(development: pd.DataFrame, spain: pd.DataFrame) -> pd.DataFrame:
    dev = missingness_report(
        development,
        features=MED_FEATURES,
        country_col="primary_country",
        high_missing_threshold=0.30,
    ).rename(
        columns={
            "missing_rate": "development_missing_rate",
            "high_missingness": "development_high_missingness",
        }
    )
    es = missingness_report(
        spain,
        features=MED_FEATURES,
        country_col="primary_country",
        high_missing_threshold=0.30,
    )[["feature", "missing_rate", "high_missingness"]].rename(
        columns={
            "missing_rate": "spain_missing_rate",
            "high_missingness": "spain_high_missingness",
        }
    )
    report = dev.merge(es, on="feature", validate="one_to_one")
    report["development_spain_gap"] = (
        report["development_missing_rate"] - report["spain_missing_rate"]
    ).abs()
    report["review_required_over_20pp"] = report["development_spain_gap"].gt(0.20)
    report["all_missing_development"] = report["development_missing_rate"].eq(1.0)
    report["all_missing_spain"] = report["spain_missing_rate"].eq(1.0)
    return report.sort_values(
        ["review_required_over_20pp", "development_spain_gap", "development_missing_rate"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def feature_importance(model: Pipeline) -> pd.DataFrame:
    imputer = model.named_steps["imputer"]
    names = imputer.get_feature_names_out(MED_FEATURES).tolist()
    estimator = model.named_steps["model"]
    if hasattr(estimator, "coef_"):
        values = np.asarray(estimator.coef_[0], dtype=float)
        kind = "scaled_coefficient"
    elif hasattr(estimator, "feature_importances_"):
        values = np.asarray(estimator.feature_importances_, dtype=float)
        kind = "tree_impurity_importance"
    else:
        return pd.DataFrame(columns=["feature", "importance_type", "value", "abs_value"])
    return pd.DataFrame(
        {
            "feature": names,
            "importance_type": kind,
            "value": values,
            "abs_value": np.abs(values),
        }
    ).sort_values("abs_value", ascending=False)


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        values = []
        for column in columns:
            value = row[column]
            values.append(f"{value:.4f}" if isinstance(value, float) else str(value))
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, separator, *body])


def write_report(metrics: dict[str, Any], missingness: pd.DataFrame) -> None:
    comparison = []
    for family, result in metrics["models"].items():
        transfer = result["spain_transfer"]
        comparison.append(
            {
                "modelo": result["label"],
                "AP_CV": result["nested_cv"]["outer_average_precision_mean"],
                "std_AP": result["nested_cv"]["outer_average_precision_std"],
                "AP_Espana": transfer["average_precision"],
                "AUC_Espana": transfer["roc_auc"],
                "top100": transfer["top_k"]["100"]["positives_captured"],
                "top250": transfer["top_k"]["250"]["positives_captured"],
                "seleccionado": "sí" if family == metrics["champion_family"] else "no",
            }
        )
    missing_review = missingness.loc[missingness["review_required_over_20pp"]]
    promotion = metrics["deployment_promotion"]
    reason_labels = {
        "Spain AP gain is below the material effect gate": (
            "la AP en España no alcanza el efecto mínimo (20% relativo y 0,005 absoluto)"
        ),
        "Spain AP bootstrap lower bound does not exceed v4": (
            "el límite inferior bootstrap del 95% para AP no supera la referencia v4"
        ),
        "Spain top-250 capture is worse than the v4 reference": (
            "la recuperación top-250 en España empeora frente a v4"
        ),
        "No new independent temporal or adjudicated confirmation set exists": (
            "no existe un nuevo conjunto temporal o adjudicado de confirmación independiente"
        ),
        "Required features have near-total missingness in Spain": (
            "hay variables requeridas con al menos un 95% de valores ausentes en España"
        ),
    }
    translated_reasons = []
    for reason in promotion["reasons"]:
        if reason.startswith("Required features are entirely missing in Spain:"):
            translated_reasons.append(
                "hay variables requeridas totalmente ausentes en España:"
                + reason.split(":", maxsplit=1)[1]
            )
        else:
            translated_reasons.append(reason_labels.get(reason, reason))
    OUT_REPORT.write_text(
        f"""# Benchmark espacial v5 del modelo de biometano

Fecha UTC: {metrics['created_at_utc']}

## Qué se ha validado

Se comparan Logistic Regression, Random Forest, Gradient Boosting y Linear SVM
mediante validación cruzada espacial anidada en Francia e Italia. `is_spain` es
la frontera canónica: toda celda española permanece fuera de selección, ajuste
de hiperparámetros, preprocessing y calibración. Se evalúa al final como prueba
de transferencia, pero se reconoce que España ya fue utilizada históricamente
en v4 y no equivale a una nueva confirmación independiente.

## Resultados

{markdown_table(comparison, ['modelo', 'AP_CV', 'std_AP', 'AP_Espana', 'AUC_Espana', 'top100', 'top250', 'seleccionado'])}

El modelo preseleccionado exclusivamente por CV espacial es
**{metrics['champion_label']}**. Su AP en España es
`{metrics['champion_spain']['average_precision']:.6f}` frente a
`{metrics['baseline_v4_best_spain_ap']:.6f}` del mejor benchmark v4.
El intervalo bootstrap estratificado del 95% para la AP es
`[{metrics['champion_spain']['average_precision_bootstrap_95']['lower']:.6f},
{metrics['champion_spain']['average_precision_bootstrap_95']['upper']:.6f}]`.

## Calibración y umbral

Estado: **{metrics['calibration']['status']}**. No se publica una probabilidad
calibrada porque las celdas sin planta conocida son negativos débiles, no
casos negativos confirmados. Brier, log loss y curvas de fiabilidad sobre esas
etiquetas podrían parecer precisos y, aun así, ser conceptualmente falsos.

Los cortes top-k se conservan únicamente como
`weak_label_reference_only`: describen qué habría ocurrido al revisar una
capacidad fija de celdas, pero NO son un umbral de construir/no construir.

## Valores ausentes

Se auditaron {len(missingness)} variables. Hay {len(missing_review)} con una
diferencia de ausencia superior a 20 puntos porcentuales entre FR/IT y España.
No se elimina ninguna automáticamente: cada desplazamiento queda marcado para
revisión y la imputación mediana se compara de forma explícita con indicadores
de ausencia. Esta opción forma parte de cada candidato y se selecciona dentro
del inner CV; no se activa después mirando los outer folds.

Variables totalmente ausentes en España:
`{', '.join(metrics['missingness_summary']['all_missing_spain']) or 'ninguna'}`.
Variables con al menos un 95% de valores ausentes en España:
`{', '.join(metrics['missingness_summary']['near_total_missing_spain']) or 'ninguna'}`.
La ausencia casi total también bloquea la promoción: unas pocas celdas de
frontera no convierten una variable en nacionalmente disponible.

## Stacking

Estado: **{metrics['stacking']['status']}**. El stacking queda formalmente fuera
del alcance de esta iteración porque los modelos base no transfieren de forma
estable y reutilizar España para decidir si conservarlo convertiría el test en
parte del ajuste.

## Decisión de promoción

Promoción a la app: **{'sí' if promotion['promote'] else 'no'}**.
Motivos: {', '.join(translated_reasons) if translated_reasons else 'cumple las puertas predefinidas'}.
Si no supera la puerta, la app conserva el ranking v49; el resultado v5 queda
como evidencia de validación, no se fuerza una mejora cosmética.

## Límites

- El target es presencia observada/proxy de plantas, no viabilidad de proyecto.
- No hay negativos confirmados ni validación parcelaria, de conexión o permiso.
- Italia aporta etiquetas proxy de confianza media.
- España contiene 26 celdas positivas; la incertidumbre de las métricas es alta.
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--outer-splits", type=int, default=4)
    parser.add_argument("--inner-splits", type=int, default=3)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use fewer trees for a smoke run; never use quick outputs for publication.",
    )
    return parser.parse_args()


def split_model_cohorts(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return FR/IT development and canonical Spanish-domain land cohorts."""
    required = {"is_land_cell", "is_spain", "primary_country"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"Missing cohort columns: {missing}")
    land = frame["is_land_cell"].fillna(False).astype(bool)
    is_spain = frame["is_spain"].fillna(False).astype(bool)
    development = frame.loc[
        land & ~is_spain & frame["primary_country"].isin(["FR", "IT"])
    ].copy()
    spain = frame.loc[land & is_spain].copy()
    assert_spain_quarantined(development, development.index)
    if set(development.index) & set(spain.index):
        raise RuntimeError("Development and Spain transfer rows overlap.")
    return development, spain


def main() -> int:
    args = parse_args()
    for directory in [DOCS, MODELS, LOCAL_DATA]:
        directory.mkdir(parents=True, exist_ok=True)
    if not args.input.exists():
        raise FileNotFoundError(f"Private curated table not found: {args.input}")

    frame = pd.read_parquet(args.input)
    required = {
        "primary_country",
        "is_land_cell",
        "is_spain",
        "X_LLC",
        "Y_LLC",
        MED_LABEL,
        MED_WEIGHT,
        SPAIN_LABEL,
        *MED_FEATURES,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

    development, spain = split_model_cohorts(frame)

    x_dev = numeric_frame(development, MED_FEATURES).reset_index(drop=True)
    y_dev = development[MED_LABEL].fillna(False).astype(bool).astype(int).to_numpy()
    weights_dev = pd.to_numeric(development[MED_WEIGHT], errors="coerce").fillna(0.05).to_numpy(dtype=float)
    groups_dev = spatial_groups(development).to_numpy()
    all_missing_development = x_dev.columns[x_dev.isna().all()].tolist()
    if all_missing_development:
        raise RuntimeError(
            "Required features are entirely missing in development: "
            f"{all_missing_development}"
        )
    outer_folds = make_spatial_folds(
        y_dev,
        groups_dev,
        n_splits=args.outer_splits,
        random_state=RANDOM_STATE,
    )

    grids = candidate_grid(quick=args.quick)
    nested_results: dict[str, dict[str, Any]] = {}
    final_candidates: dict[str, Candidate] = {}
    final_selection: dict[str, list[dict[str, Any]]] = {}
    for family, candidates in grids.items():
        nested_results[family] = nested_family_evaluation(
            family,
            candidates,
            x_dev,
            y_dev,
            weights_dev,
            groups_dev,
            outer_folds,
            inner_splits=args.inner_splits,
        )
        selected, selection_rows = select_candidate(
            candidates,
            x_dev,
            y_dev,
            weights_dev,
            outer_folds,
        )
        final_candidates[family] = selected
        final_selection[family] = selection_rows

    champion_family = sorted(
        nested_results,
        key=lambda family: (
            -nested_results[family]["outer_average_precision_mean"],
            nested_results[family]["outer_average_precision_std"],
            -nested_results[family]["outer_average_precision_min"],
            family,
        ),
    )[0]
    champion_candidate = final_candidates[champion_family]

    champion_selection_rows = final_selection[champion_family]
    best_without_indicators = sorted(
        (row for row in champion_selection_rows if not row["add_missing_indicators"]),
        key=lambda row: -float(row["average_precision_mean"]),
    )[0]
    best_with_indicators = sorted(
        (row for row in champion_selection_rows if row["add_missing_indicators"]),
        key=lambda row: -float(row["average_precision_mean"]),
    )[0]

    x_spain = numeric_frame(spain, MED_FEATURES)
    y_spain = spain[SPAIN_LABEL].fillna(False).astype(bool).astype(int).to_numpy()
    model_results: dict[str, dict[str, Any]] = {}
    fitted_models: dict[str, Pipeline] = {}
    score_columns: dict[str, np.ndarray] = {}
    for family, selected in final_candidates.items():
        model = make_pipeline(selected)
        model.fit(x_dev, y_dev, model__sample_weight=weights_dev)
        scores = score_model(model, x_spain)
        fitted_models[family] = model
        score_columns[family] = scores
        model_results[family] = {
            "label": selected.label,
            "selected_candidate": selected.key,
            "selected_params": selected.params,
            "add_missing_indicators": selected.add_missing_indicators,
            "nested_cv": nested_results[family],
            "full_development_selection": final_selection[family],
            "spain_transfer": ranking_metrics(y_spain, scores, top_k=TOP_K),
        }

    champion_spain = model_results[champion_family]["spain_transfer"]
    champion_spain["average_precision_bootstrap_95"] = bootstrap_average_precision_interval(
        y_spain,
        score_columns[champion_family],
        n_bootstrap=1_000,
        confidence=0.95,
        random_state=RANDOM_STATE,
    )
    thresholds = capacity_threshold_diagnostics(
        y_spain,
        score_columns[champion_family],
        capacities=TOP_K,
    )
    calibration = calibration_eligibility(
        development,
        outcome_col=MED_LABEL,
        adjudicated_col=None,
    )
    missingness = missingness_artifact(development, spain)
    all_missing_spain = missingness.loc[
        missingness["all_missing_spain"], "feature"
    ].astype(str).tolist()
    near_total_missing_spain = missingness.loc[
        missingness["spain_missing_rate"].ge(0.95), "feature"
    ].astype(str).tolist()

    baseline = json.loads((DOCS / "model_benchmark_v4_metrics.json").read_text(encoding="utf-8"))
    baseline_ap = max(
        float(result["no_spain_transfer_eval_on_spain"]["spain_average_precision"])
        for result in baseline["models"].values()
    )
    baseline_top250 = max(
        int(result["no_spain_transfer_eval_on_spain"]["spain_topk"]["top_250_positives"])
        for result in baseline["models"].values()
    )
    champion_top250 = int(champion_spain["top_k"]["250"]["positives_captured"])
    minimum_ap_gain = max(0.005, baseline_ap * 0.20)
    required_ap = baseline_ap + minimum_ap_gain
    ap_interval_lower = float(champion_spain["average_precision_bootstrap_95"]["lower"])
    promotion_reasons: list[str] = []
    if float(champion_spain["average_precision"]) < required_ap:
        promotion_reasons.append("Spain AP gain is below the material effect gate")
    if ap_interval_lower <= baseline_ap:
        promotion_reasons.append("Spain AP bootstrap lower bound does not exceed v4")
    if champion_top250 < baseline_top250:
        promotion_reasons.append("Spain top-250 capture is worse than the v4 reference")
    if all_missing_spain:
        promotion_reasons.append(
            "Required features are entirely missing in Spain: " + ", ".join(all_missing_spain)
        )
    if near_total_missing_spain:
        promotion_reasons.append("Required features have near-total missingness in Spain")
    if args.quick:
        promotion_reasons.append("quick mode is not publishable")
    promotion_reasons.append("No new independent temporal or adjudicated confirmation set exists")

    metrics: dict[str, Any] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "quick_smoke" if args.quick else "full_spatial_validation",
        "random_state": RANDOM_STATE,
        "spatial_block_m": 100_000,
        "outer_splits": args.outer_splits,
        "inner_splits": args.inner_splits,
        "selection_scope": ["FR", "IT", "is_spain=False"],
        "transfer_scope": ["is_spain=True"],
        "development_rows": int(len(development)),
        "development_positive_cells": int(y_dev.sum()),
        "development_spatial_groups": int(len(np.unique(groups_dev))),
        "development_positive_groups": int(len(np.unique(groups_dev[y_dev == 1]))),
        "spain_rows": int(len(spain)),
        "spain_positive_cells": int(y_spain.sum()),
        "features": MED_FEATURES,
        "label": MED_LABEL,
        "weight": MED_WEIGHT,
        "models": model_results,
        "champion_family": champion_family,
        "champion_label": model_results[champion_family]["label"],
        "champion_spain": champion_spain,
        "missing_indicator_comparison": {
            "selected_inside_inner_cv": champion_candidate.add_missing_indicators,
            "best_without_indicators": best_without_indicators,
            "best_with_indicators": best_with_indicators,
            "contract": "Preprocessing is part of each candidate and selected inside inner CV.",
        },
        "calibration": calibration,
        "stacking": {
            "status": "deferred_out_of_scope",
            "reason": (
                "The optional stack is withheld because base-model transfer is unstable and "
                "Spain cannot be reused safely as a model-selection set."
            ),
        },
        "threshold_status": "weak_label_reference_only",
        "missingness_summary": {
            "features_audited": int(len(missingness)),
            "features_over_20pp_shift": int(missingness["review_required_over_20pp"].sum()),
            "all_missing_development": all_missing_development,
            "all_missing_spain": all_missing_spain,
            "near_total_missing_spain": near_total_missing_spain,
        },
        "baseline_v4_best_spain_ap": baseline_ap,
        "baseline_v4_best_spain_top250": baseline_top250,
        "deployment_promotion": {
            "promote": not promotion_reasons,
            "reasons": promotion_reasons,
            "gate": {
                "minimum_relative_ap_gain": 0.20,
                "minimum_absolute_ap_gain": 0.005,
                "required_ap": required_ap,
                "bootstrap_lower_must_exceed_v4": True,
                "top250_not_worse": True,
                "no_all_or_near_total_missing_required_features": True,
                "new_independent_confirmation_required": True,
            },
        },
        "warnings": [
            "Spain was quarantined by is_spain and not used for model family, hyperparameter or preprocessing selection.",
            "Unlabeled cells are weak negatives, not confirmed true negatives.",
            "No calibrated probability or decisional binary threshold is emitted.",
            "Feature importance is associative, not causal.",
            "Spain is a historically reused transfer anchor, not a new independent confirmation set.",
        ],
    }

    local_scores = spain[["GRD_ID", SPAIN_LABEL, "primary_country", "is_spain"]].reset_index(drop=True)
    for family, scores in score_columns.items():
        local_scores[f"{family}_score"] = scores
        local_scores[f"{family}_rank01"] = pd.Series(scores).rank(pct=True, method="average").to_numpy()

    OUT_METRICS.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    missingness.to_csv(OUT_MISSINGNESS, index=False, encoding="utf-8")
    thresholds.to_csv(OUT_THRESHOLDS, index=False, encoding="utf-8")
    feature_importance(fitted_models[champion_family]).to_csv(OUT_IMPORTANCE, index=False, encoding="utf-8")
    local_scores.to_parquet(OUT_LOCAL_SCORES, index=False)
    verification_probe = pd.DataFrame(
        [
            {feature: 0.0 for feature in MED_FEATURES},
            {feature: 1.0 for feature in MED_FEATURES},
            {feature: np.nan for feature in MED_FEATURES},
        ],
        columns=MED_FEATURES,
    )
    joblib.dump(
        {
            "model": fitted_models[champion_family],
            "candidate": {
                "family": champion_candidate.family,
                "label": champion_candidate.label,
                "key": champion_candidate.key,
                "params": champion_candidate.params,
                "add_missing_indicators": champion_candidate.add_missing_indicators,
            },
            "features": MED_FEATURES,
            "label": MED_LABEL,
            "training_countries": ["FR", "IT"],
            "calibration_status": calibration["status"],
            "deployment_promotion": metrics["deployment_promotion"],
            "score_semantics": "ranking_score_not_probability",
            "sklearn_version": sklearn.__version__,
            "verification_probe": {
                "frame": verification_probe.to_dict(orient="list"),
                "expected_scores": score_model(
                    fitted_models[champion_family], verification_probe
                ).tolist(),
            },
            "metrics_path": OUT_METRICS.name,
        },
        OUT_MODEL,
    )
    write_report(metrics, missingness)
    print(json.dumps({
        "champion": metrics["champion_label"],
        "spain_ap": champion_spain["average_precision"],
        "spain_auc": champion_spain["roc_auc"],
        "calibration": calibration["status"],
        "promote": metrics["deployment_promotion"]["promote"],
        "artifacts": [str(OUT_METRICS), str(OUT_REPORT), str(OUT_MODEL)],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
