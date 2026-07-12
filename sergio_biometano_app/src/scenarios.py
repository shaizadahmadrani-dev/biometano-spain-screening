"""Simulador separado de la prioridad oficial de screening.

Los pesos son deliberadamente transparentes y se aplican sólo a señales
observadas. Un veto físico explícito siempre prevalece. Desde v49, nitratos es
un riesgo de gestión del digestato y no se convierte en veto de emplazamiento.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCENARIO_WEIGHTS: dict[str, float] = {
    "feedstock": 0.30,
    "organic_waste": 0.15,
    "gas_access": 0.20,
    "road_access": 0.15,
    "land_environment": 0.20,
}
SCENARIO_WEIGHT_NOTES = (
    "Escenario transparente: materia prima 30%, residuos 15%, gas 20%, "
    "carretera 15% y suelo/entorno 20%. Los pesos no reentrenan ni sustituyen v48."
)


def _first(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None and str(row[name]).strip() != "":
            return row[name]
    return default


def _num(value: Any) -> float | None:
    try:
        return None if value is None or str(value).strip() == "" else float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "sí", "si", "veto"}


def _is_v49(row: Mapping[str, Any]) -> bool:
    return "v49" in str(row.get("method_version", "")).casefold()


def _nitrate_veto(row: Mapping[str, Any]) -> bool:
    if _is_v49(row):
        return False
    if any(_truthy(row.get(name)) for name in (
        "nitrate_vulnerable", "nitrate_vulnerable_zone", "nitrate_zone",
        "nitrate_veto", "nitrates_hard_veto",
    )):
        return True
    try:
        if row.get("nitrate_intersection_share") is not None and float(row["nitrate_intersection_share"]) > 0:
            return True
    except (TypeError, ValueError):
        pass
    reasons = " ".join(str(row.get(name, "")) for name in ("veto_reasons", "hard_veto_reasons", "constraint_flags_v31"))
    lowered = reasons.casefold()
    return "nitr" in lowered and "unknown" not in lowered and "desconoc" not in lowered


def has_hard_veto(row: Mapping[str, Any]) -> bool:
    return _truthy(_first(row, "hard_veto", "hard_constraint_flag_v31", default=False)) or _nitrate_veto(row)


def _official_score_0_100(row: Mapping[str, Any]) -> float | None:
    field = "score_0_100" if "score_0_100" in row else "official_score" if "official_score" in row else "defensible_score_v31"
    value = _num(row.get(field))
    if value is not None and field == "defensible_score_v31" and 0 <= value <= 1:
        value *= 100
    return value


def _signal(row: Mapping[str, Any], dimension: str) -> float | None:
    aliases: dict[str, tuple[str, ...]] = {
        "feedstock": ("feedstock_score", "feedstock"),
        "organic_waste": ("organic_waste_score", "organic_waste"),
        "gas_access": ("gas_access_score", "gas_score", "gas_access", "connectivity_proxy_score_v49"),
        "road_access": ("road_access_score", "road_score", "road_access"),
        "land_environment": ("land_environment_score", "land_score", "land_environment"),
    }
    value = _num(_first(row, *aliases[dimension]))
    if value is not None:
        return max(0.0, min(100.0, value * 100 if 0 <= value <= 1 else value))
    distance_aliases = {
        "gas_access": ("gas_pipeline_distance_km_proxy", "best_gas_pipeline_dist_km", "best_gas_pipeline_dist_km_1km_v8", "gas_distance_km"),
        "road_access": ("road_distance_km", "nearest_cnig_btn100_high_capacity_road_dist_km_1km_v8"),
    }
    distance = _num(_first(row, *distance_aliases.get(dimension, ())))
    if distance is not None:
        return max(0.0, min(100.0, 100.0 * (1.0 - distance / 100.0)))
    return None


def score_scenario(row: Mapping[str, Any], weights: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Calculate a bounded illustrative score without changing robust v48."""
    selected = dict(weights or SCENARIO_WEIGHTS)
    if not selected or any(value < 0 for value in selected.values()) or sum(selected.values()) <= 0:
        raise ValueError("Los pesos del escenario deben ser no negativos y sumar más de cero.")
    total_weight = sum(selected.values())
    selected = {key: value / total_weight for key, value in selected.items()}
    signals = {dimension: _signal(row, dimension) for dimension in selected}
    observed = {key: value for key, value in signals.items() if value is not None}
    observed_weight = sum(selected[key] for key in observed)
    score = 0.0 if not observed else sum(signals[key] * selected[key] for key in observed) / observed_weight
    score = round(max(0.0, min(100.0, score)), 2)
    missing = [key for key, value in signals.items() if value is None]
    veto = has_hard_veto(row)
    v49 = _is_v49(row)
    if veto:
        score = 0.0
        status = "descartado por filtro físico" if v49 else "descartado preliminar"
        label = "Escenario: descartado por filtro físico; el resultado no puede sobreescribirlo."
    else:
        status = ("prioridad media de investigación" if missing else "prioridad alta de investigación") if v49 else ("requiere revisión" if missing else "candidato de screening")
        label = "Escenario exploratorio: ordena señales disponibles; no declara viabilidad ni prefactibilidad."
    return {
        "score_type": "escenario",
        "scenario_score_0_100": score,
        "scenario_score": score,
        "official_score": _official_score_0_100(row),
        "official_score_0_100": _official_score_0_100(row),
        "hard_veto": veto,
        "status": status,
        "label": label,
        "weights": selected,
        "weight_note": SCENARIO_WEIGHT_NOTES,
        "signals": signals,
        "missing_dimensions": missing,
        "caveat": (
            "Este valor es un escenario y no modifica la prioridad oficial, no completa gates críticos ni autoriza una planta."
            if v49 else
            "Este valor es un escenario y no modifica el score oficial robusto v48 ni autoriza una planta."
        ),
    }


calculate_scenario_score = score_scenario
run_scenario = score_scenario
scenario_score = score_scenario
calculate_scenario = score_scenario


__all__ = ["SCENARIO_WEIGHTS", "SCENARIO_WEIGHT_NOTES", "has_hard_veto", "score_scenario", "calculate_scenario_score", "run_scenario", "scenario_score", "calculate_scenario"]
