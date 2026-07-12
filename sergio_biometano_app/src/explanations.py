"""Explicaciones auditables para los universos v48 y v49.

Este módulo no conoce Streamlit ni hace I/O. Acepta tanto el contrato
normalizado de la app como columnas históricas v31, porque la procedencia de
cada indicador debe seguir siendo visible en la ficha.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


OFFICIAL_SCORE_NOTE = (
    "El score robusto v48 es una prioridad relativa de screening (0–100), "
    "no una probabilidad de éxito, una autorización ni una declaración de viabilidad."
)
V49_SCORE_NOTE = (
    "La puntuación v49 prioriza dónde adquirir evidencia de prefactibilidad; "
    "no es una probabilidad, viabilidad, permiso ni capacidad de conexión confirmada."
)
NOT_VERIFIED = "No verificado: no hay dato suficiente para confirmar este control."
NITRATE_VETO = (
    "Veto duro: la celda intersecta una zona vulnerable a nitratos; "
    "queda descartada preliminarmente para esta pantalla."
)
STATUS_CAVEAT = (
    "La celda pertenece al universo candidato v48; cualquier decisión exige "
    "revisión urbanística, ambiental, de propiedad, conexión y visita de campo."
)
V49_STATUS_CAVEAT = (
    "La cobertura nacional 5 km es un cribado territorial y el refinamiento 1 km "
    "solo cubre el universo priorizado; ninguno sustituye una comprobación parcelaria."
)
MANDATORY_EXTERNAL_CHECKS = [
    "Contrato, cantidad anual y estacionalidad del suministro de sustratos.",
    "Calidad, trazabilidad y potencial bioquímico de los sustratos.",
    "Capacidad real y condiciones de conexión gasista.",
    "Capacidad real y condiciones de conexión eléctrica.",
    "Propiedad, Catastro, disponibilidad de parcela y servidumbres.",
    "Compatibilidad urbanística, PGOU y distancias reglamentarias.",
    "Plan de digestato, balance de nitrógeno y superficie receptora.",
    "Permisos de agua e hidrología de detalle.",
    "Tramitación ambiental, emisiones y aceptación local.",
    "Contrato o salida comercial del biometano y coproductos.",
    "CAPEX, OPEX, logística y economía completa del proyecto.",
]


def _value(cell: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in cell and cell[name] is not None and str(cell[name]).strip() != "":
            return cell[name]
    return default


def _number(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "sí", "si", "y", "veto"}


def _is_unknown(value: Any) -> bool:
    return value is None or str(value).strip().lower() in {
        "", "nan", "none", "null", "unknown", "desconocido", "no verificado",
    }


def _is_v49(cell: Mapping[str, Any]) -> bool:
    return "v49" in str(cell.get("method_version", "")).casefold()


def _as_list(value: Any) -> list[str]:
    if _is_unknown(value):
        return []
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        value = value.tolist()
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                return [str(part).strip() for part in decoded if not _is_unknown(part)]
        return [part.strip() for part in value.replace("|", ";").split(";") if part.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(part).strip() for part in value if not _is_unknown(part)]
    return [str(value).strip()]


def _nitrate_veto(cell: Mapping[str, Any]) -> bool:
    if _is_v49(cell):
        return False
    direct_fields = (
        "nitrate_vulnerable", "nitrate_vulnerable_zone", "nitrate_zone",
        "nitrate_intersection", "nitrate_vulnerable_intersection",
        "nitrates_intersection", "nitrates_hard_veto", "nitrate_hard_veto", "nitrate_veto",
    )
    if any(_is_true(cell.get(field)) for field in direct_fields):
        return True
    share = _number(cell.get("nitrate_intersection_share"))
    if share is not None and share > 0:
        return True
    reason_text = " ".join(
        _as_list(_value(cell, "veto_reasons", "hard_veto_reasons", "constraint_flags_v31"))
    ).lower()
    return "nitr" in reason_text and not any(token in reason_text for token in ("unknown", "desconoc", "no verificado"))


def _hard_veto_reasons(cell: Mapping[str, Any]) -> list[str]:
    hard = _is_true(_value(cell, "hard_veto", "hard_constraint_flag_v31", default=False))
    nitrate = _nitrate_veto(cell)
    if not hard and not nitrate:
        return []
    reasons = _as_list(_value(cell, "veto_reasons", "hard_veto_reasons"))
    if hard and not reasons:
        reasons = _as_list(_value(cell, "constraint_flags_v31"))
    if nitrate and not any("nitr" in reason.lower() for reason in reasons):
        reasons.insert(0, "zona vulnerable a nitratos")
    if hard and not reasons:
        reasons.append("restricción dura marcada por la fuente v31")
    return reasons


def _missing_checks(cell: Mapping[str, Any]) -> list[str]:
    for field in ("missing_checks", "missing", "unverified_checks"):
        if field in cell:
            return _as_list(cell.get(field))
    missing: list[str] = []
    nitrate_fields = (
        "nitrate_vulnerable", "nitrate_vulnerable_zone", "nitrate_intersection",
        "nitrate_vulnerable_intersection", "nitrates_intersection", "nitrate_intersection_share",
    )
    nitrate_verified = any(field in cell and not _is_unknown(cell.get(field)) for field in nitrate_fields)
    if not nitrate_verified:
        missing.append("intersección con zona vulnerable a nitratos")
    for field, label in (
        ("cadastral_verified", "parcela y situación catastral"),
        ("grid_capacity_verified", "capacidad real de conexión eléctrica/gasista"),
        ("planning_verified", "compatibilidad urbanística"),
        ("hydrology_verified", "comprobación hidrológica detallada"),
    ):
        if field not in cell or _is_unknown(cell.get(field)):
            missing.append(label)
    return missing


def _label_for_status(cell: Mapping[str, Any], reasons: list[str], missing: list[str]) -> str:
    if reasons:
        return "Descartado preliminar: existe al menos un veto duro."
    status = str(_value(cell, "screening_status", "status", default="")).strip().lower()
    if _is_v49(cell):
        if status == "prioridad alta de investigación":
            return "Prioridad alta para adquirir evidencia; la prefactibilidad aún no está demostrada."
        if status == "prioridad media de investigación":
            return "Prioridad media para adquirir evidencia y resolver condicionantes."
        if status == "prioridad baja de investigación":
            return "Prioridad baja de investigación con los proxies actuales."
        if "descart" in status:
            return "Descartado por un filtro físico explícito del screening."
    if "descart" in status:
        return "Descartado preliminar según el screening."
    if status == "prioritario condicionado":
        return "Prioridad condicionada: destaca en el ranking, pero necesita verificaciones externas."
    if missing or "revis" in status:
        return "Requiere revisión: faltan verificaciones oficiales."
    return "Candidato de screening: no equivale a viable ni autorizado."


def _strengths(cell: Mapping[str, Any]) -> list[str]:
    strengths: list[str] = []
    feedstock = _number(_value(cell, "feedstock_score", "feedstock"))
    waste = _number(_value(cell, "organic_waste_score", "organic_waste"))
    gas = _number(_value(cell, "gas_pipeline_distance_km_proxy", "best_gas_pipeline_dist_km", "best_gas_pipeline_dist_km_1km_v8", "gas_distance_km"))
    road = _number(_value(cell, "road_distance_km", "nearest_cnig_btn100_high_capacity_road_dist_km_1km_v8"))
    if feedstock is not None and feedstock >= 0.6:
        strengths.append("Señal favorable de disponibilidad de materia prima.")
    if waste is not None and waste >= 0.6:
        strengths.append("Señal favorable de residuos orgánicos aprovechables.")
    if gas is not None and gas <= 10:
        strengths.append(f"Proximidad orientativa a gasoducto ({gas:g} km).")
    if road is not None and road <= 10:
        strengths.append(f"Acceso viario orientativo relativamente próximo ({road:g} km).")
    if not strengths:
        strengths.append("No se identifica una fortaleza cuantitativa suficiente con los datos disponibles.")
    return strengths


def _weaknesses(cell: Mapping[str, Any], missing: list[str]) -> list[str]:
    weaknesses: list[str] = []
    built = _number(_value(cell, "built_up_share", "worldcover2021_share_built_up_1km_sample25_v7"))
    water = _number(_value(cell, "water_wetland_share", "worldcover2021_share_permanent_water_1km_sample25_v7"))
    gas = _number(_value(cell, "gas_pipeline_distance_km_proxy", "best_gas_pipeline_dist_km", "best_gas_pipeline_dist_km_1km_v8", "gas_distance_km"))
    slope = _number(_value(cell, "copdem_slope_median_deg_v47"))
    if built is not None and built >= 0.2:
        weaknesses.append("La señal de suelo construido puede dificultar la implantación.")
    if water is not None and water > 0:
        weaknesses.append("Existe señal de agua o humedal que requiere comprobación ambiental.")
    if gas is not None and gas > 25:
        weaknesses.append(f"La distancia orientativa a gasoducto es elevada ({gas:g} km).")
    if slope is not None and slope >= 10:
        weaknesses.append(f"La pendiente mediana Copernicus es elevada para screening ({slope:.1f}°).")
    if _is_true(_value(cell, "snczi_q100_intersects_v47")):
        weaknesses.append("La celda intersecta cartografía publicada SNCZI Q100; requiere estudio de inundabilidad.")
    if str(_value(cell, "model_rank_confidence_v48", default="")).lower() == "baja":
        weaknesses.append("Los cuatro clasificadores discrepan; la prioridad de ranking es inestable.")
    if missing:
        weaknesses.append("Hay controles pendientes; lo desconocido se trata como no verificado, no como cumplimiento.")
    if not weaknesses:
        weaknesses.append("El screening no sustituye las comprobaciones oficiales pendientes.")
    return weaknesses


def summarize_cell(cell: Mapping[str, Any]) -> dict[str, Any]:
    """Return a Spanish, defensible summary of one candidate cell."""
    reasons = _hard_veto_reasons(cell)
    missing = _missing_checks(cell)
    score_field = "score_0_100" if "score_0_100" in cell else "official_score" if "official_score" in cell else "defensible_score_v31"
    score = _number(_value(cell, score_field))
    if score_field == "defensible_score_v31" and score is not None and 0 <= score <= 1:
        score *= 100
    score = max(0.0, min(100.0, score)) if score is not None else None
    official_status = _value(cell, "screening_status", "status", default="no verificado")
    review_reasons = _as_list(_value(cell, "review_reasons", "review_questions"))
    v49 = _is_v49(cell)
    digestate_risk = str(_value(cell, "digestate_risk", default="no verificado"))
    if v49 and digestate_risk == "alto" and not any("digestato" in reason.casefold() for reason in review_reasons):
        review_reasons.append("Riesgo alto de gestión del digestato por intersección con zona vulnerable a nitratos.")
    missing_critical_gates = _as_list(_value(cell, "missing_critical_gates"))
    failed_critical_gates = _as_list(_value(cell, "failed_critical_gates"))
    score_note = V49_SCORE_NOTE if v49 else OFFICIAL_SCORE_NOTE
    summary = {
        "cell_id": _value(cell, "cell_id", "cell_id_v22", "cell_1km_id_v22", default="sin identificador"),
        "province": _value(cell, "province", "province_name_v31", default="no verificada"),
        "ccaa": _value(cell, "ccaa", "province_nuts2_name_v31", "NUTS2024_2_name", default="no verificada"),
        "score_0_100": score,
        "official_score_0_100": score,
        "official_score": score,
        "official_score_note": score_note,
        "tier": _value(cell, "tier", "original_tier", "original_v31_tier", "defensible_tier_v31", default="no verificado"),
        "screening_status": official_status,
        "decision_label": _label_for_status(cell, reasons, missing),
        "hard_veto": bool(reasons),
        "vetoes": [NITRATE_VETO if "nitr" in reason.lower() else f"Veto duro: {reason}." for reason in reasons],
        "veto_reasons": reasons,
        "strengths": _strengths(cell),
        "weaknesses": _weaknesses(cell, missing),
        "missing_checks": missing,
        "missing": [f"{NOT_VERIFIED} ({item})" for item in missing],
        "review_reasons": review_reasons,
        "mandatory_external_checks": list(MANDATORY_EXTERNAL_CHECKS),
        "digestate_risk": digestate_risk,
        "prefeasibility_status": _value(cell, "prefeasibility_status", default="no iniciada" if v49 else "no verificado"),
        "screening_evidence_completeness": _value(cell, "screening_evidence_completeness", "data_completeness", default="no verificado"),
        "prefeasibility_evidence_completeness": _value(cell, "prefeasibility_evidence_completeness", default="no verificado"),
        "missing_critical_gates": missing_critical_gates,
        "failed_critical_gates": failed_critical_gates,
        "data_completeness": _value(cell, "data_completeness", default="no verificado"),
        "method_version": _value(cell, "method_version", default="no verificado"),
        "data_date": _value(cell, "data_date", default="no verificada"),
        "official_statement": (
            f"Prioridad de investigación: {official_status}. {score_note}"
            if v49 else
            NITRATE_VETO if _nitrate_veto(cell) else
            f"Resultado oficial: {official_status}. {score_note}"
        ),
        "scenario_statement": "El simulador, si se usa, es un escenario separado y no modifica este resultado oficial.",
        "caveats": [V49_STATUS_CAVEAT if v49 else STATUS_CAVEAT],
    }
    return summary


build_cell_summary = summarize_cell
explain_cell = summarize_cell
build_cell_explanation = summarize_cell
cell_summary = summarize_cell


__all__ = [
    "OFFICIAL_SCORE_NOTE", "V49_SCORE_NOTE", "NOT_VERIFIED", "NITRATE_VETO", "STATUS_CAVEAT", "V49_STATUS_CAVEAT",
    "summarize_cell", "build_cell_summary", "explain_cell", "build_cell_explanation", "cell_summary",
]
