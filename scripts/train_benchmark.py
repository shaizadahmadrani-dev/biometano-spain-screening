from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "modeling"
DOCS = ROOT / "docs" / "generated"
MODELS = ROOT / "models"
INPUT_ATTRS = PROCESSED / "biometano_grid5km_curated_v4_attributes.parquet"

SPAIN_LABEL = "label_has_operating_biomethane_plant_spain_v3"
MED_LABEL = "label_has_biomethane_mediterranean_weighted_v4"
MED_WEIGHT = "sample_weight_mediterranean_v4"
MED_TRAIN_COUNTRIES = ["ES", "FR", "IT"]

LANDCOVER_SHARE_FEATURES = [
    "worldcover2021_share_tree_cover_sample25",
    "worldcover2021_share_shrubland_sample25",
    "worldcover2021_share_grassland_sample25",
    "worldcover2021_share_cropland_sample25",
    "worldcover2021_share_built_up_sample25",
    "worldcover2021_share_bare_sparse_vegetation_sample25",
    "worldcover2021_share_permanent_water_sample25",
    "worldcover2021_share_herbaceous_wetland_sample25",
]

MED_FEATURES = [
    "LAND_PC",
    "TOT_P_2021",
    "DIST_COAST",
    "DIST_BORD",
    "bovine_lsu_2023",
    "poultry_lsu_2023",
    "arable_main_area_ths_ha_2024",
    "cereals_production_ths_t_2024",
    "manure_tonnes_2020_mnr_exp_lq_sl",
    "manure_tonnes_2020_mnr_exp_so",
    "wwtp_count_cell",
    "wwtp_capacity_sum_pe_cell",
    "wwtp_load_entering_sum_pe_cell",
    "wwtp_wastewater_treated_sum_cell",
    "nearest_wwtp_dist_km",
    "nearest_wwtp_capacity_pe",
    "nearest_wwtp_load_entering_pe",
    "bio1_annual_mean_temp_c",
    "bio5_max_temp_warmest_month_c",
    "bio6_min_temp_coldest_month_c",
    "bio12_annual_precip_mm",
    "bio15_precipitation_seasonality",
    "nearest_ggit_operating_gas_pipeline_dist_km_mediterranean_v4",
    *LANDCOVER_SHARE_FEATURES,
]

OUT_METRICS = DOCS / "model_benchmark_v4_metrics.json"
OUT_REPORT = DOCS / "model_benchmark_v4_report.md"
OUT_EXPLAIN = DOCS / "model_benchmark_v4_explainability.md"
OUT_FEATURES = PROCESSED / "model_benchmark_v4_feature_importance.csv"
OUT_SPAIN_SCORES = PROCESSED / "biometano_spain_model_benchmark_v4_scores.parquet"
OUT_TOP_LONG = PROCESSED / "biometano_spain_model_benchmark_v4_top_candidates_long.csv"
OUT_MODELS = MODELS / "benchmark_classifiers_mediterranean_proxy_v4.joblib"

TOP_K = [10, 25, 50, 100, 250]
RANDOM_STATE = 42


def rank01(series: pd.Series, high_good: bool = True) -> pd.Series:
    ranks = pd.to_numeric(series, errors="coerce").rank(pct=True, method="average")
    if not high_good:
        ranks = 1 - ranks
    return ranks.fillna(0.0).clip(0, 1)


def numeric_frame(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for feature in features:
        if feature not in df.columns:
            out[feature] = np.nan
        elif str(df[feature].dtype) == "boolean" or df[feature].dtype == bool:
            out[feature] = df[feature].fillna(False).astype(bool).astype(float)
        else:
            out[feature] = pd.to_numeric(df[feature], errors="coerce")
    return out


def topk_capture(
    df: pd.DataFrame,
    score_col: str,
    label_col: str,
    ks: list[int],
) -> dict[str, int]:
    land = df[df["is_land_cell"].fillna(False).astype(bool)].sort_values(
        score_col,
        ascending=False,
    )
    y = land[label_col].fillna(False).astype(bool)
    return {f"top_{k}_positives": int(y.head(k).sum()) for k in ks}


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    pipeline_factory: Callable[[], Pipeline]
    explanation: str


def ensure_dirs() -> None:
    for directory in [DOCS, PROCESSED, MODELS]:
        directory.mkdir(parents=True, exist_ok=True)


def make_logistic_regression() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=3000, C=0.5)),
        ]
    )


def make_random_forest() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=250,
                    max_depth=14,
                    min_samples_leaf=5,
                    n_jobs=-1,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def make_gradient_boosting() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                GradientBoostingClassifier(
                    n_estimators=160,
                    learning_rate=0.05,
                    max_depth=3,
                    subsample=0.85,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def make_linear_svm() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", LinearSVC(C=0.5, max_iter=10000, random_state=RANDOM_STATE)),
        ]
    )


MODEL_SPECS = [
    ModelSpec(
        key="logistic_regression",
        label="Logistic Regression",
        pipeline_factory=make_logistic_regression,
        explanation="Baseline lineal, molt explicable; dona probabilitats calibrables.",
    ),
    ModelSpec(
        key="random_forest",
        label="Random Forest",
        pipeline_factory=make_random_forest,
        explanation="Ensemble d'arbres; captura no-linearitats i interaccions, menys transparent que logística.",
    ),
    ModelSpec(
        key="gradient_boosting",
        label="Gradient Boosting",
        pipeline_factory=make_gradient_boosting,
        explanation="Arbres seqüencials; sovint fort en dades tabulars, però pot sobreajustar si els labels són febles.",
    ),
    ModelSpec(
        key="linear_svm",
        label="Linear SVM",
        pipeline_factory=make_linear_svm,
        explanation="Marge lineal robust per ranking; no dona probabilitat directa sense calibració extra.",
    ),
]


def training_mask(df: pd.DataFrame, *, exclude_spain: bool) -> pd.Series:
    mask = df["primary_country"].isin(MED_TRAIN_COUNTRIES) & df["is_land_cell"].fillna(False).astype(bool)
    if exclude_spain:
        mask &= ~df["is_spain"].fillna(False).astype(bool)
    return mask


def score_model(model: Pipeline, df: pd.DataFrame) -> pd.Series:
    x = numeric_frame(df, MED_FEATURES)
    estimator = model.named_steps["model"]
    if hasattr(estimator, "predict_proba"):
        scores = model.predict_proba(x)[:, 1]
    elif hasattr(estimator, "decision_function"):
        scores = model.decision_function(x)
    else:
        raise TypeError(f"Model {type(estimator).__name__} has no probability or decision score.")
    return pd.Series(scores, index=df.index)


def fit_model(df: pd.DataFrame, spec: ModelSpec, *, exclude_spain: bool) -> tuple[Pipeline, pd.Series, dict]:
    mask = training_mask(df, exclude_spain=exclude_spain)
    train = df.loc[mask].copy()
    y = train[MED_LABEL].fillna(False).astype(bool).astype(int)
    weights = train[MED_WEIGHT].fillna(0.05).astype(float)
    if y.nunique() != 2:
        raise RuntimeError(f"{spec.key} training does not have both classes.")

    model = spec.pipeline_factory()
    model.fit(numeric_frame(train, MED_FEATURES), y, model__sample_weight=weights)
    scores = score_model(model, df)
    fit_info = {
        "training_scope": "FR/IT transfer to Spain" if exclude_spain else "ES/FR/IT calibration model",
        "training_countries": sorted(train["primary_country"].dropna().astype(str).unique().tolist()),
        "train_rows": int(len(train)),
        "train_positive_cells_unweighted": int(y.sum()),
        "train_positive_weight_sum": float(weights[y.eq(1)].sum()),
        "train_negative_weight_sum": float(weights[y.eq(0)].sum()),
        "positive_cells_by_tier": train.loc[y.eq(1), "label_tier_mediterranean_v4"].value_counts().to_dict(),
    }
    return model, scores, fit_info


def evaluate_spain(df: pd.DataFrame, scores: pd.Series, score_col: str) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score

    mask = df["is_spain"].fillna(False).astype(bool) & df["is_land_cell"].fillna(False).astype(bool)
    y = df.loc[mask, SPAIN_LABEL].fillna(False).astype(bool).astype(int)
    p = scores.loc[mask]
    tmp = df.loc[mask, ["GRD_ID", "is_land_cell", SPAIN_LABEL]].copy()
    tmp[score_col] = p
    return {
        "spain_average_precision": float(average_precision_score(y, p)),
        "spain_roc_auc": float(roc_auc_score(y, p)),
        "spain_topk": topk_capture(tmp, score_col, SPAIN_LABEL, TOP_K),
    }


def feature_rows(model: Pipeline, spec: ModelSpec) -> list[dict]:
    estimator = model.named_steps["model"]
    if hasattr(estimator, "coef_"):
        values = np.asarray(estimator.coef_[0], dtype=float)
        return [
            {
                "model": spec.key,
                "feature": feature,
                "importance_type": "scaled_coefficient",
                "value": float(value),
                "abs_value": float(abs(value)),
                "direction": "positive" if value >= 0 else "negative",
            }
            for feature, value in zip(MED_FEATURES, values)
        ]
    if hasattr(estimator, "feature_importances_"):
        values = np.asarray(estimator.feature_importances_, dtype=float)
        return [
            {
                "model": spec.key,
                "feature": feature,
                "importance_type": "tree_feature_importance",
                "value": float(value),
                "abs_value": float(abs(value)),
                "direction": "importance",
            }
            for feature, value in zip(MED_FEATURES, values)
        ]
    return []


def dataframe_to_markdown(df: pd.DataFrame, *, float_digits: int = 4) -> str:
    """Small local markdown writer to avoid optional pandas/tabulate dependency."""
    if df.empty:
        return "_No rows_"
    rendered = df.copy()
    for col in rendered.columns:
        if pd.api.types.is_float_dtype(rendered[col]):
            rendered[col] = rendered[col].map(lambda value: f"{value:.{float_digits}f}")
        else:
            rendered[col] = rendered[col].astype(str)
    header = "| " + " | ".join(rendered.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(rendered.columns)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rendered.to_numpy(dtype=str)]
    return "\n".join([header, sep, *body])


def write_report(metrics: dict, feature_importance: pd.DataFrame) -> None:
    rows = []
    for key, result in metrics["models"].items():
        honest = result["no_spain_transfer_eval_on_spain"]
        calib = result["spain_in_sample_calibration"]
        rows.append(
            {
                "model": result["label"],
                "calib_ap": calib["spain_average_precision"],
                "calib_auc": calib["spain_roc_auc"],
                "transfer_ap": honest["spain_average_precision"],
                "transfer_auc": honest["spain_roc_auc"],
                "transfer_top100": honest["spain_topk"]["top_100_positives"],
                "transfer_top250": honest["spain_topk"]["top_250_positives"],
            }
        )
    summary = pd.DataFrame(rows).sort_values(["transfer_ap", "transfer_top250"], ascending=[False, False])
    table = dataframe_to_markdown(summary, float_digits=4)

    best = metrics["recommended_reading"]
    OUT_REPORT.write_text(
        f"""# Benchmark classificadors v4

Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Models comparats

- Logistic Regression
- Random Forest
- Gradient Boosting
- Linear SVM

## Resultat resum

{table}

## Lectura

- La columna important és `transfer_ap`: entrenar sense Espanya i avaluar contra Espanya.
- El calibratge amb Espanya dins del training **no és validació independent**.
- Random Forest fa `1.0000` en calibratge in-sample: això és senyal clar d'overfit/memorització, no una victòria real.
- Tot i que Random Forest lidera l'AP de transferència, no s'hauria d'usar com a model final sense validació espacial/country-blocked addicional.
- En aquest problema de screening, AP i top-k són més accionables que ROC AUC; un AUC alt no garanteix una bona shortlist territorial.
- Lectura recomanada: **{best}**.

## Caveat

Això continua sent un benchmark de screening amb labels forts ES/FR i proxy Itàlia. No és decisió final d'ubicació.
""",
        encoding="utf-8",
    )

    top_features = (
        feature_importance.sort_values(["model", "abs_value"], ascending=[True, False])
        .groupby("model")
        .head(12)
        .copy()
    )
    OUT_EXPLAIN.write_text(
        "# Explainability benchmark v4\n\n"
        "Top features per model. En models lineals, el signe indica direcció després d'escalar; en arbres, és importància relativa.\n\n"
        "Caveat: en arbres, `feature_importances_` és importància relativa basada en splits/impuresa; no és efecte causal ni estabilitat garantida, especialment amb variables correlacionades.\n\n"
        + dataframe_to_markdown(top_features, float_digits=5)
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ensure_dirs()
    if not INPUT_ATTRS.exists():
        raise FileNotFoundError(
            f"Missing curated feature table: {INPUT_ATTRS}. "
            "See data/modeling/README.md for the required schema and licensing note."
        )
    df = pd.read_parquet(INPUT_ATTRS)
    spain_mask = df["is_spain"].fillna(False).astype(bool)
    land_mask = spain_mask & df["is_land_cell"].fillna(False).astype(bool)
    spain_scores = df.loc[spain_mask, ["GRD_ID", SPAIN_LABEL, "is_land_cell", "primary_country"]].copy()

    metrics: dict = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "label": MED_LABEL,
        "weight": MED_WEIGHT,
        "features": MED_FEATURES,
        "training_countries": MED_TRAIN_COUNTRIES,
        "spain_positive_cells": int(df.loc[land_mask, SPAIN_LABEL].fillna(False).sum()),
        "models": {},
        "warnings": [
            "Spain in-sample calibration is not independent validation.",
            "No-Spain transfer to Spain is the honest comparison anchor.",
            "Italy is proxy_medium from OSM; Greece is not trained because coverage is too sparse.",
            "Unlabeled cells are weak negatives, not proven true negatives.",
            "Linear SVM scores are margins, not calibrated probabilities.",
        ],
    }
    fitted_models = {}
    all_feature_rows: list[dict] = []

    for spec in MODEL_SPECS:
        full_model, full_scores, full_fit = fit_model(df, spec, exclude_spain=False)
        transfer_model, transfer_scores, transfer_fit = fit_model(df, spec, exclude_spain=True)

        full_col = f"{spec.key}_calibration_score"
        transfer_col = f"{spec.key}_transfer_score"
        spain_scores.loc[:, full_col] = full_scores.loc[spain_scores.index]
        spain_scores.loc[:, transfer_col] = transfer_scores.loc[spain_scores.index]
        rank_col = f"{spec.key}_transfer_rank01"
        spain_scores.loc[:, rank_col] = 0.0
        spain_scores.loc[land_mask.loc[spain_scores.index], rank_col] = rank01(spain_scores.loc[land_mask.loc[spain_scores.index], transfer_col])

        metrics["models"][spec.key] = {
            "label": spec.label,
            "explanation": spec.explanation,
            "full_fit": full_fit,
            "transfer_fit": transfer_fit,
            "spain_in_sample_calibration": evaluate_spain(df, full_scores, full_col),
            "no_spain_transfer_eval_on_spain": evaluate_spain(df, transfer_scores, transfer_col),
        }
        fitted_models[spec.key] = {
            "full_model": full_model,
            "transfer_model": transfer_model,
        }
        all_feature_rows.extend(feature_rows(transfer_model, spec))

    comparison = []
    for key, result in metrics["models"].items():
        honest = result["no_spain_transfer_eval_on_spain"]
        comparison.append(
            (
                key,
                honest["spain_average_precision"],
                honest["spain_topk"]["top_250_positives"],
                honest["spain_roc_auc"],
            )
        )
    best_ap_key = sorted(comparison, key=lambda item: (item[1], item[2], item[3]), reverse=True)[0][0]
    best_top250_key = sorted(comparison, key=lambda item: (item[2], item[1], item[3]), reverse=True)[0][0]
    best_auc_key = sorted(comparison, key=lambda item: (item[3], item[1], item[2]), reverse=True)[0][0]
    metrics["best_by_transfer_ap"] = metrics["models"][best_ap_key]["label"]
    metrics["best_by_transfer_top250"] = metrics["models"][best_top250_key]["label"]
    metrics["best_by_transfer_auc"] = metrics["models"][best_auc_key]["label"]
    metrics["champion_selection"] = "none"
    metrics["recommended_reading"] = (
        "No hi ha guanyador net. "
        f"{metrics['best_by_transfer_ap']} té la millor AP de transferència, "
        f"{metrics['best_by_transfer_top250']} recupera més positius al top-250, "
        f"i {metrics['best_by_transfer_auc']} té millor ROC AUC. "
        "La recomanació defensable és auditar els top candidats i els filtres territorials, no triar un champion final."
    )

    top_rows = []
    for spec in MODEL_SPECS:
        score_col = f"{spec.key}_transfer_score"
        cols = [
            "GRD_ID",
            SPAIN_LABEL,
            "is_land_cell",
            score_col,
            f"{spec.key}_transfer_rank01",
        ]
        top = spain_scores.loc[spain_scores["is_land_cell"].fillna(False).astype(bool), cols].copy()
        top = top.sort_values(score_col, ascending=False).head(250)
        top.insert(0, "model", spec.key)
        top.insert(1, "candidate_rank", range(1, len(top) + 1))
        top_rows.append(top)

    top_long = pd.concat(top_rows, ignore_index=True)
    features = pd.DataFrame(all_feature_rows)
    spain_scores.to_parquet(OUT_SPAIN_SCORES, index=False)
    top_long.to_csv(OUT_TOP_LONG, index=False, encoding="utf-8")
    features.to_csv(OUT_FEATURES, index=False, encoding="utf-8")
    OUT_METRICS.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(metrics, features)
    joblib.dump(
        {
            "models": fitted_models,
            "metrics": metrics,
            "features": MED_FEATURES,
            "label": MED_LABEL,
            "weight": MED_WEIGHT,
        },
        OUT_MODELS,
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
