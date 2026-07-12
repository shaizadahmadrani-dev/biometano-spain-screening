"""Pure v49 rules for evidence acquisition and prefeasibility.

v49 deliberately does not predict project viability.  It keeps national
screening priority, evidence quality and candidate-specific prefeasibility as
separate outputs so that a favourable proxy cannot compensate for a missing
critical gate.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


METHOD_VERSION_V49 = "sergio-national-v49-evidence"

STATUS_HIGH = "prioridad alta de investigación"
STATUS_MEDIUM = "prioridad media de investigación"
STATUS_LOW = "prioridad baja de investigación"
STATUS_PHYSICAL_EXCLUSION = "descartado por filtro físico"

SCREENING_STATUS_ORDER = (
    STATUS_HIGH,
    STATUS_MEDIUM,
    STATUS_LOW,
    STATUS_PHYSICAL_EXCLUSION,
)

SCREENING_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "terreno": ("copdem_slope_median_deg_v47", "terrain_slope_deg"),
    "hidrología publicada": ("hydrology_status", "snczi_q100_status_v47"),
    "nitratos": ("nitrate_intersects", "nitrate_intersection_share"),
    "corredor gasista": ("gas_pipeline_distance_km_proxy", "best_gas_pipeline_dist_km_1km_v8"),
    "corredor eléctrico": ("electric_substation_distance_km_proxy", "electric_line_distance_km_proxy"),
    "acceso viario": ("road_distance_km", "nearest_cnig_btn100_high_capacity_road_dist_km_1km_v8"),
    "cobertura del suelo": ("cropland_share", "built_up_share"),
    "Natura 2000": ("natura2000_distance_km", "natura2000_area_share_1km_v7"),
}

PREFEASIBILITY_GATES: dict[str, tuple[str, ...]] = {
    "contrato y disponibilidad de sustrato": ("supply_contract_verified",),
    "calidad y potencial metanogénico del sustrato": ("feedstock_quality_verified",),
    "capacidad real de conexión gasista": ("gas_capacity_verified",),
    "capacidad real de conexión eléctrica": ("electricity_capacity_verified", "grid_capacity_verified"),
    "parcela y situación catastral": ("cadastral_verified",),
    "compatibilidad urbanística": ("planning_verified",),
    "plan de digestato y balance N/P": ("digestate_plan_verified",),
    "agua y vertido": ("water_permit_verified",),
    "tramitación ambiental": ("environmental_permit_verified",),
    "offtake y certificación": ("offtake_verified",),
    "economía CAPEX/OPEX": ("economics_verified",),
}

_GRID_ID = re.compile(r"^CRS3035RES(?P<resolution>\d+)mN(?P<north>\d+)E(?P<east>\d+)$")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null", "unknown", "no verificado"} else text


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        value = value.tolist()
    if isinstance(value, str):
        return [item.strip() for item in value.replace("|", ";").split(";") if _clean(item)]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if _clean(item)]
    return [str(value).strip()] if _clean(value) else []


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text not in result:
            result.append(text)
    return result


def _number(value: Any) -> float | None:
    try:
        return None if _clean(value) == "" else float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    text = _clean(value).casefold()
    if text in {"true", "1", "yes", "sí", "si", "verificado", "pass", "aprobado"}:
        return True
    if text in {"false", "0", "no", "fallo", "failed", "rechazado"}:
        return False
    return None


def _first_present(row: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in row and _clean(row[name]) != "":
            return row[name]
    return None


def _is_nitrate_reason(reason: str) -> bool:
    lowered = reason.casefold()
    return "nitr" in lowered or "zona vulnerable" in lowered


def parent_5km_id(cell_id: Any) -> str:
    """Return the deterministic 5 km parent for a GISCO-style grid ID."""

    text = _clean(cell_id)
    match = _GRID_ID.match(text)
    if not match:
        return text
    north = int(match.group("north"))
    east = int(match.group("east"))
    parent_north = north - north % 5000
    parent_east = east - east % 5000
    return f"CRS3035RES5000mN{parent_north}E{parent_east}"


def screening_evidence(row: Mapping[str, Any]) -> dict[str, str]:
    """Describe which national screening dimensions contain usable evidence."""

    evidence: dict[str, str] = {}
    for label, fields in SCREENING_DIMENSIONS.items():
        value = _first_present(row, fields)
        if value is None:
            evidence[label] = "desconocido"
        elif label in {"corredor gasista", "corredor eléctrico", "acceso viario"}:
            evidence[label] = "proxy"
        else:
            evidence[label] = "verificado parcial"
    return evidence


def prefeasibility_evidence(row: Mapping[str, Any]) -> dict[str, bool | None]:
    """Read tri-state candidate-specific gates without inventing missing data."""

    return {
        label: _bool(_first_present(row, fields))
        for label, fields in PREFEASIBILITY_GATES.items()
    }


def _priority_status(row: Mapping[str, Any], hard_veto: bool) -> str:
    if hard_veto:
        return STATUS_PHYSICAL_EXCLUSION
    score = _number(row.get("score_0_100"))
    if score is None:
        robust = _number(row.get("robust_score_v48"))
        score = robust * 100 if robust is not None and 0 <= robust <= 1 else robust
    score = score or 0.0
    tier = _clean(row.get("robust_tier_v48") or row.get("original_tier")).casefold()
    confidence = _clean(row.get("model_rank_confidence_v48")).casefold()
    if score >= 80 and (tier.startswith("a") or "prioritaria" in tier or not tier) and confidence != "baja":
        return STATUS_HIGH
    if score >= 60 or tier.startswith(("a", "b")):
        return STATUS_MEDIUM
    return STATUS_LOW


def classify_v49(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized v49 record while preserving the input fields."""

    output = dict(row)
    original_vetoes = _as_list(row.get("veto_reasons"))
    constraint_flags = _as_list(row.get("constraint_flags")) or _as_list(row.get("constraint_flags_v31"))
    non_nitrate_vetoes = [reason for reason in original_vetoes if not _is_nitrate_reason(reason)]
    hard_constraint_flags = [
        flag for flag in constraint_flags if flag.casefold().startswith("hard_") and not _is_nitrate_reason(flag)
    ]
    non_nitrate_vetoes = _unique((*non_nitrate_vetoes, *hard_constraint_flags))
    inherited_hard = _bool(row.get("hard_veto")) is True or _bool(row.get("hard_constraint_flag_v31")) is True
    had_only_nitrate_evidence = bool(original_vetoes) and not non_nitrate_vetoes
    if inherited_hard and not original_vetoes and not hard_constraint_flags:
        non_nitrate_vetoes = ["restricción física heredada no especificada"]
    hard_veto = bool(non_nitrate_vetoes) and not had_only_nitrate_evidence

    nitrate_flag = _bool(_first_present(row, ("nitrate_intersects", "nitrate_vulnerable", "nitrate_intersection")))
    nitrate_share = _number(row.get("nitrate_intersection_share"))
    if nitrate_flag is True or (nitrate_share is not None and nitrate_share > 0):
        digestate_risk = "alto"
    elif nitrate_flag is False or nitrate_share == 0:
        digestate_risk = "estándar"
    else:
        digestate_risk = "desconocido"

    review_reasons = _as_list(row.get("review_reasons"))
    review_reasons = [reason for reason in review_reasons if not _is_nitrate_reason(reason)]
    if digestate_risk == "alto":
        review_reasons.append("zona vulnerable a nitratos: requiere plan de digestato y balance N/P")
    elif digestate_risk == "desconocido":
        review_reasons.append("riesgo de nitratos y digestato no verificado")
    review_reasons = _unique(review_reasons)

    screening = screening_evidence(row)
    known_screening = sum(value != "desconocido" for value in screening.values())
    screening_completeness = round(known_screening / len(screening), 3)
    prefeasibility = prefeasibility_evidence(row)
    observed_gates = sum(value is not None for value in prefeasibility.values())
    prefeasibility_completeness = round(observed_gates / len(prefeasibility), 3)
    missing_gates = [label for label, value in prefeasibility.items() if value is None]
    failed_gates = [label for label, value in prefeasibility.items() if value is False]

    if hard_veto or failed_gates:
        prefeasibility_status = "descartada"
    elif observed_gates == len(prefeasibility) and all(prefeasibility.values()):
        prefeasibility_status = "prefactible"
    elif observed_gates:
        prefeasibility_status = "en revisión"
    else:
        prefeasibility_status = "no iniciada"

    cell_id = row.get("cell_id") or row.get("cell_1km_id_v22") or row.get("GRD_ID")
    output.update(
        method_version=METHOD_VERSION_V49,
        parent_5km_id=parent_5km_id(cell_id),
        hard_veto=hard_veto,
        veto_reasons=non_nitrate_vetoes,
        review_reasons=review_reasons,
        digestate_risk=digestate_risk,
        screening_status=_priority_status(row, hard_veto),
        screening_evidence=screening,
        screening_evidence_completeness=screening_completeness,
        prefeasibility_evidence=prefeasibility,
        prefeasibility_evidence_completeness=prefeasibility_completeness,
        prefeasibility_status=prefeasibility_status,
        missing_critical_gates=missing_gates,
        failed_critical_gates=failed_gates,
        missing_checks=missing_gates,
        # Backwards-compatible UI field; explicitly means screening evidence.
        data_completeness=screening_completeness,
        target_statement="prioridad para adquirir evidencia de prefactibilidad; no probabilidad ni permiso",
    )
    return output


def diversify_top_k(
    rows: Iterable[Mapping[str, Any]],
    *,
    k_per_region: int = 25,
    region_field: str = "province",
) -> list[dict[str, Any]]:
    """Select at most one cell per 5 km parent and K parents per region."""

    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (_number(row.get("score_0_100")) or 0.0),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    seen_parents: set[tuple[str, str]] = set()
    region_counts: dict[str, int] = {}
    for row in ordered:
        region = _clean(row.get(region_field)) or "no verificada"
        parent = _clean(row.get("parent_5km_id")) or parent_5km_id(row.get("cell_id"))
        key = (region, parent)
        if key in seen_parents or region_counts.get(region, 0) >= max(0, k_per_region):
            continue
        row["parent_5km_id"] = parent
        row["method_version"] = METHOD_VERSION_V49
        selected.append(row)
        seen_parents.add(key)
        region_counts[region] = region_counts.get(region, 0) + 1
    return selected


__all__ = [
    "METHOD_VERSION_V49",
    "PREFEASIBILITY_GATES",
    "SCREENING_DIMENSIONS",
    "SCREENING_STATUS_ORDER",
    "STATUS_HIGH",
    "STATUS_MEDIUM",
    "STATUS_LOW",
    "STATUS_PHYSICAL_EXCLUSION",
    "classify_v49",
    "diversify_top_k",
    "parent_5km_id",
    "prefeasibility_evidence",
    "screening_evidence",
]
