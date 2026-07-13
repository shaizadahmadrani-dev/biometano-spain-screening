"""Informes PDF auditables de una celda de screening.

El módulo es deliberadamente independiente de Streamlit. Primero construye un
contrato de datos determinista y después lo renderiza; así se pueden verificar
las afirmaciones del informe sin tener que inspeccionar un PDF binario.
"""

from __future__ import annotations

import io
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from .explanations import summarize_cell


NOT_VERIFIED = "No verificado"
DEFAULT_CRITICAL_GATES = (
    "contrato y disponibilidad de sustrato",
    "calidad y potencial metanogénico del sustrato",
    "capacidad real de conexión gasista",
    "capacidad real de conexión eléctrica",
    "parcela y situación catastral",
    "compatibilidad urbanística",
    "plan de digestato y balance N/P",
    "agua y vertido",
    "tramitación ambiental",
    "offtake y certificación",
    "economía CAPEX/OPEX",
)

TIER_LABELS = {
    "A_prioritaria": "A · prioridad alta para revisión",
    "B_viable_revisar": "B · priorizada para revisión",
    "C_degradar_revisar": "C · revisión reforzada",
    "D_descartar_preliminar": "D · descarte preliminar",
    "A_prioritaria_condicionada": "A · prioridad robusta condicionada",
    "B_prioritaria_revisar": "B · prioridad para revisión",
    "C_revision_reforzada": "C · revisión reforzada",
}
SOURCE_LABELS = {
    "land_cover": "Cobertura del suelo",
    "roads": "Carreteras",
    "electricity_visual_layer": "Infraestructura eléctrica visual",
    "gas_corridor": "Corredor gasista",
    "operating_plants": "Plantas operativas",
    "nitrates": "Zonas vulnerables a nitratos",
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {"", "nan", "none", "null", "unknown", "desconocido"}
    if isinstance(value, float):
        return math.isnan(value)
    return False


def _first(data: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in data and not _is_missing(data[name]):
            return data[name]
    return default


def _as_list(value: Any) -> list[str]:
    if _is_missing(value):
        return []
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        value = value.tolist()
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
        else:
            return [stripped]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item).strip() for item in value if not _is_missing(item) and str(item).strip()]
    return [str(value).strip()]


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _number(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def _is_true(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes", "sí", "si", "y"}
    return bool(value)


def _decimal(value: Any, decimals: int = 2) -> str:
    number = _number(value)
    if number is None:
        return NOT_VERIFIED
    return f"{number:.{decimals}f}".replace(".", ",")


def _distance(value: Any) -> str:
    formatted = _decimal(value)
    return formatted if formatted == NOT_VERIFIED else f"{formatted} km"


def _percentage(value: Any) -> str:
    number = _number(value)
    if number is None:
        return NOT_VERIFIED
    return f"{number * 100:.0f}%".replace(".", ",")


def _index(value: Any) -> str:
    formatted = _decimal(value)
    return formatted if formatted == NOT_VERIFIED else f"{formatted} / 1"


def _yes_no_detected(value: Any) -> str:
    if _is_missing(value):
        return NOT_VERIFIED
    return "Sí" if _is_true(value) else "No detectada en la cartografía disponible"


def _deduplicate(items: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _technical_indicator(
    indicator: str,
    value: str,
    evidence: str,
    interpretation: str,
) -> dict[str, str]:
    return {
        "indicator": indicator,
        "value": value,
        "evidence": evidence or NOT_VERIFIED,
        "interpretation": interpretation,
    }


def _natura_value(cell: Mapping[str, Any]) -> str:
    intersects = _first(cell, "natura2000_intersects")
    share = _first(cell, "natura2000_share", "natura2000_area_share_1km_v7")
    distance = _first(cell, "natura2000_distance_km", "nearest_natura2000_dist_km_1km_v7")
    values = []
    if not _is_missing(intersects):
        values.append(f"Intersección: {_yes_no_detected(intersects)}")
    if not _is_missing(share):
        values.append(f"superficie: {_percentage(share)}")
    if not _is_missing(distance):
        values.append(f"distancia: {_distance(distance)}")
    return "; ".join(values) or NOT_VERIFIED


def _nitrate_value(cell: Mapping[str, Any]) -> str:
    intersects = _first(cell, "nitrate_intersects", "nitrate_vulnerable")
    share = _first(cell, "nitrate_intersection_share", "nitrate_share")
    zone = _first(cell, "nitrate_zone_name")
    values = []
    if not _is_missing(intersects):
        values.append(f"Intersección: {_yes_no_detected(intersects)}")
    if not _is_missing(share):
        values.append(f"superficie: {_percentage(share)}")
    if not _is_missing(zone):
        values.append(f"zona: {zone}")
    return "; ".join(values) or NOT_VERIFIED


def _plant_value(cell: Mapping[str, Any]) -> str:
    distance = _first(cell, "nearest_operating_biomethane_plant_distance_km")
    name = _first(cell, "nearest_operating_biomethane_plant_name")
    if _is_missing(distance) and _is_missing(name):
        return NOT_VERIFIED
    values = []
    if not _is_missing(distance):
        values.append(_distance(distance))
    if not _is_missing(name):
        values.append(str(name))
    return " · ".join(values)


def _terrain_value(cell: Mapping[str, Any]) -> str:
    elevation = _first(cell, "copdem_elevation_median_m_v47")
    median = _first(cell, "copdem_slope_median_deg_v47")
    p90 = _first(cell, "copdem_slope_p90_deg_v47")
    values = []
    if not _is_missing(elevation):
        values.append(f"elevación mediana: {_decimal(elevation, 1)} m")
    if not _is_missing(median):
        values.append(f"pendiente mediana: {_decimal(median, 1)}°")
    if not _is_missing(p90):
        values.append(f"pendiente p90: {_decimal(p90, 1)}°")
    return "; ".join(values) or NOT_VERIFIED


def _hydrology_value(cell: Mapping[str, Any]) -> str:
    status = _first(cell, "hydrology_status")
    review = _first(cell, "hydrology_review_class_v24")
    distance = _first(cell, "igr_es063_cauce_centroid_dist_km_v24")
    values = []
    if not _is_missing(status):
        values.append(str(status))
    if not _is_missing(review):
        values.append(str(review).replace("_", " "))
    if not _is_missing(distance):
        values.append(f"cauce publicado: {_distance(distance)}")
    return "; ".join(values) or NOT_VERIFIED


def _flood_value(cell: Mapping[str, Any]) -> str:
    intersects = _first(cell, "snczi_q100_intersects_v47")
    status = _first(cell, "snczi_q100_status_v47")
    if _is_missing(intersects) and _is_missing(status):
        return NOT_VERIFIED
    if not _is_missing(status):
        return str(status)
    return _yes_no_detected(intersects)


def _screening_evidence(cell: Mapping[str, Any], name: str, default: str = "proxy") -> str:
    evidence = _as_mapping(_first(cell, "screening_evidence", default={}))
    target = name.casefold()
    for key, value in evidence.items():
        if str(key).casefold() == target and not _is_missing(value):
            return str(value)
    return default


def _technical_indicators(cell: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        _technical_indicator(
            "Índice macro de materia prima",
            _index(_first(cell, "feedstock_score")),
            "proxy macro",
            "Orienta la búsqueda; requiere inventario local, cantidad, estacionalidad y contrato.",
        ),
        _technical_indicator(
            "Índice de residuos orgánicos",
            _index(_first(cell, "organic_waste_score")),
            "proxy macro",
            "Orienta la búsqueda; requiere caracterización, trazabilidad y potencial metanogénico.",
        ),
        _technical_indicator(
            "Distancia al corredor gasista",
            _distance(_first(cell, "gas_pipeline_distance_km_proxy", "best_gas_pipeline_dist_km_1km_v8")),
            _screening_evidence(cell, "corredor gasista"),
            "Proximidad geométrica: no acredita capacidad, punto de inyección ni coste de conexión.",
        ),
        _technical_indicator(
            "Distancia a carretera",
            _distance(_first(cell, "road_distance_km", "nearest_cnig_btn100_high_capacity_road_dist_km_1km_v8")),
            _screening_evidence(cell, "acceso viario"),
            "Proximidad geométrica: no confirma acceso parcelario, servidumbres ni capacidad logística.",
        ),
        _technical_indicator(
            "Distancia a subestación eléctrica",
            _distance(_first(cell, "electric_substation_distance_km_proxy", "electric_substation_distance_proxy_km")),
            _screening_evidence(cell, "corredor eléctrico", default=NOT_VERIFIED),
            "Proximidad geométrica: no acredita capacidad disponible ni condiciones de conexión.",
        ),
        _technical_indicator(
            "Distancia a línea eléctrica",
            _distance(_first(cell, "electric_line_distance_km_proxy")),
            _screening_evidence(cell, "corredor eléctrico", default=NOT_VERIFIED),
            "Referencia territorial; tensión, titularidad, capacidad y coste deben confirmarse.",
        ),
        _technical_indicator(
            "Planta de biometano operativa más próxima",
            _plant_value(cell),
            "inventario reconciliado",
            "Sirve como contexto sectorial; no demuestra saturación ni disponibilidad de recursos.",
        ),
        _technical_indicator(
            "Suelo agrícola en la celda",
            _percentage(_first(cell, "cropland_share")),
            _screening_evidence(cell, "cobertura del suelo", default="verificado parcial"),
            "Cobertura superficial; no equivale a clase catastral, propiedad ni compatibilidad urbanística.",
        ),
        _technical_indicator(
            "Suelo urbanizado en la celda",
            _percentage(_first(cell, "built_up_share")),
            _screening_evidence(cell, "cobertura del suelo", default="verificado parcial"),
            "Cobertura superficial; exige comprobación urbanística y parcelaria de detalle.",
        ),
        _technical_indicator(
            "Natura 2000",
            _natura_value(cell),
            _screening_evidence(cell, "Natura 2000", default="verificado parcial"),
            "La intersección o proximidad activa revisión ambiental; la geometría debe contrastarse.",
        ),
        _technical_indicator(
            "Zona vulnerable a nitratos",
            _nitrate_value(cell),
            _screening_evidence(cell, "nitratos", default="verificado parcial"),
            "Activa revisión del digestato y balance N/P; no es un veto universal de emplazamiento.",
        ),
        _technical_indicator(
            "Terreno y pendiente",
            _terrain_value(cell),
            _screening_evidence(cell, "terreno", default=NOT_VERIFIED),
            "Indicador topográfico de screening; requiere levantamiento y estudio geotécnico.",
        ),
        _technical_indicator(
            "Hidrología publicada",
            _hydrology_value(cell),
            _screening_evidence(cell, "hidrología publicada", default=NOT_VERIFIED),
            "Cobertura publicada no exhaustiva; requiere estudio hidrológico y permisos de agua.",
        ),
        _technical_indicator(
            "Inundabilidad publicada Q100",
            _flood_value(cell),
            _screening_evidence(cell, "hidrología publicada", default=NOT_VERIFIED),
            "No detectar intersección en la capa publicada no demuestra ausencia de riesgo.",
        ),
        _technical_indicator(
            "Estabilidad del ranking del modelo",
            str(_first(cell, "model_rank_confidence_v48", default=NOT_VERIFIED)),
            "variación entre modelos",
            "Describe estabilidad del ranking, no confianza en que el proyecto vaya a ser viable.",
        ),
    ]


def _gate_rows(cell: Mapping[str, Any]) -> list[dict[str, str]]:
    evidence = _as_mapping(_first(cell, "prefeasibility_evidence", default={}))
    missing_items = _as_list(_first(cell, "missing_critical_gates", default=[]))
    failed_items = _as_list(_first(cell, "failed_critical_gates", default=[]))
    missing = {item.casefold() for item in missing_items}
    failed = {item.casefold() for item in failed_items}
    gates = _deduplicate([*DEFAULT_CRITICAL_GATES, *evidence.keys(), *missing_items, *failed_items])
    rows = []
    for gate in gates:
        key = gate.casefold()
        supplied = next((value for name, value in evidence.items() if str(name).casefold() == key), None)
        if key in failed:
            status, detail = "No superado", "El dataset marca este gate como no superado; requiere expediente de contraste."
        elif key in missing:
            status, detail = "Pendiente", NOT_VERIFIED
        elif not _is_missing(supplied):
            status, detail = "Evidencia aportada", str(supplied)
        else:
            status, detail = NOT_VERIFIED, NOT_VERIFIED
        rows.append({"gate": gate, "status": status, "evidence": detail})
    return rows


def _coordinate_links(lat: float | None, lon: float | None) -> dict[str, str]:
    if lat is None or lon is None:
        return {"openstreetmap": "", "google_maps": ""}
    latitude, longitude = f"{lat:.6f}", f"{lon:.6f}"
    return {
        "openstreetmap": f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=15/{latitude}/{longitude}",
        "google_maps": f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}",
    }


def build_point_report_data(
    cell: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the auditable semantic contract rendered by the PDF."""

    manifest = dict(manifest or {})
    summary = summarize_cell(cell)
    lat = _number(_first(cell, "lat", "latitude"))
    lon = _number(_first(cell, "lon", "longitude"))
    score = _number(_first(cell, "score_0_100", "official_score", "screening_priority_score_v49"))
    resolution = _number(_first(cell, "source_resolution_km"))
    grid_level = str(_first(cell, "grid_level", default=NOT_VERIFIED))
    scope_key = "refined_1km" if resolution == 1 or "1 km" in grid_level.casefold() else "national_5km"
    scope = _as_mapping(manifest.get("scope")).get(scope_key, NOT_VERIFIED)
    hard_veto = _is_true(_first(cell, "hard_veto", default=False))
    veto_reasons = _as_list(_first(cell, "veto_reasons", default=[]))
    tier = str(_first(cell, "original_tier", "tier", "robust_tier_v48", default=NOT_VERIFIED))
    strengths = _deduplicate([*_as_list(summary.get("strengths")), *_as_list(_first(cell, "key_drivers", default=[]))])
    weaknesses = _deduplicate([*_as_list(summary.get("weaknesses")), *_as_list(summary.get("review_reasons"))])
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sources = [
        f"{SOURCE_LABELS.get(str(key), str(key).replace('_', ' ').title())}: {value}"
        for key, value in _as_mapping(manifest.get("source_vintages")).items()
    ]
    limitations = _deduplicate([
        "Este informe prioriza investigación territorial; no es una declaración de probabilidad, viabilidad, permiso, propiedad, capacidad de conexión ni rentabilidad.",
        "La distancia a gas, electricidad y carreteras es un proxy geométrico que debe contrastarse con titulares y administraciones.",
        "La ausencia de una intersección en una capa publicada no prueba que el condicionante no exista.",
        "Las zonas vulnerables a nitratos exigen revisar el digestato y el balance N/P; no son un veto universal de emplazamiento.",
        *_as_list(manifest.get("limitations")),
    ])
    evidence_completeness = _number(summary.get("screening_evidence_completeness"))
    prefeasibility_completeness = _number(summary.get("prefeasibility_evidence_completeness"))
    return {
        "title": "Informe detallado del punto de screening",
        "generated_at": stamp,
        "identity": {
            "cell_id": str(summary.get("cell_id", NOT_VERIFIED)),
            "province": str(summary.get("province", NOT_VERIFIED)),
            "ccaa": str(summary.get("ccaa", NOT_VERIFIED)),
            "grid_level": grid_level,
            "resolution": f"{_decimal(resolution, 0)} km" if resolution is not None else NOT_VERIFIED,
            "coordinates": f"{lat:.6f}, {lon:.6f}" if lat is not None and lon is not None else NOT_VERIFIED,
            "scope": str(scope),
            "priority_level": TIER_LABELS.get(tier, tier.replace("_", " ")),
        },
        "executive": {
            "priority": f"{score:.0f}/100" if score is not None else NOT_VERIFIED,
            "screening_status": str(summary.get("screening_status", NOT_VERIFIED)),
            "screening_evidence": f"{evidence_completeness * 100:.0f}%" if evidence_completeness is not None else NOT_VERIFIED,
            "prefeasibility": str(summary.get("prefeasibility_status", NOT_VERIFIED)),
            "prefeasibility_evidence": f"{prefeasibility_completeness * 100:.0f}%" if prefeasibility_completeness is not None else NOT_VERIFIED,
            "digestate_risk": str(summary.get("digestate_risk", NOT_VERIFIED)),
            "physical_exclusion": (
                f"Detectada: {'; '.join(veto_reasons) or 'motivo no detallado'}"
                if hard_veto else "No detectada en los filtros disponibles"
            ),
        },
        "official_statement": str(summary.get("official_statement", "")),
        "strengths": strengths or ["No se han identificado fortalezas verificadas en el snapshot."],
        "weaknesses": weaknesses or ["No se han documentado alertas adicionales; los gates externos siguen siendo obligatorios."],
        "technical_indicators": _technical_indicators(cell),
        "critical_gates": _gate_rows(cell),
        "mandatory_external_checks": _as_list(summary.get("mandatory_external_checks")),
        "map_links": _coordinate_links(lat, lon),
        "provenance": {
            "method_version": str(_first(cell, "method_version", default=manifest.get("method_version", NOT_VERIFIED))),
            "data_date": str(_first(cell, "data_date", default=manifest.get("as_of", NOT_VERIFIED))),
            "target": str(manifest.get("target", _first(cell, "target_statement", default=NOT_VERIFIED))),
            "sources": sources or ["No se han indicado fuentes en el manifest."],
        },
        "limitations": limitations,
    }


def _paragraph(text: Any, style: Any) -> Any:
    from reportlab.platypus import Paragraph

    return Paragraph(xml_escape(str(text)).replace("\n", "<br/>"), style)


def _rich_paragraph(markup: str, style: Any) -> Any:
    """Render markup assembled exclusively from escaped values and fixed tags."""
    from reportlab.platypus import Paragraph

    return Paragraph(markup, style)


def _bullet_list(items: Sequence[str], style: Any) -> list[Any]:
    return [_paragraph(f"• {item}", style) for item in items]


def point_report_pdf_bytes(
    cell: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
    *,
    generated_at: str | None = None,
) -> bytes:
    """Render a four-section point report as PDF bytes."""

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("La exportación PDF requiere reportlab.") from exc

    report = build_point_report_data(cell, manifest, generated_at=generated_at)
    navy = colors.HexColor("#102A43")
    blue = colors.HexColor("#176B87")
    pale_blue = colors.HexColor("#EAF4F7")
    pale_gold = colors.HexColor("#FFF6D8")
    line = colors.HexColor("#B8C6D1")
    text_color = colors.HexColor("#243B53")
    muted = colors.HexColor("#526D82")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=1.45 * cm,
        bottomMargin=1.25 * cm,
        title=f"Informe de punto {report['identity']['cell_id']}",
        author="Explorador nacional de biometano",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PointTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=20, leading=24, textColor=navy, alignment=TA_LEFT, spaceAfter=5,
    )
    subtitle = ParagraphStyle(
        "PointSubtitle", parent=styles["BodyText"], fontSize=9, leading=12,
        textColor=muted, spaceAfter=8,
    )
    section = ParagraphStyle(
        "PointSection", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, leading=16, textColor=navy, spaceBefore=5, spaceAfter=6,
    )
    body = ParagraphStyle(
        "PointBody", parent=styles["BodyText"], fontSize=8.3, leading=11,
        textColor=text_color, spaceAfter=3,
    )
    small = ParagraphStyle(
        "PointSmall", parent=body, fontSize=7.2, leading=9, textColor=muted,
    )
    table_head = ParagraphStyle(
        "PointTableHead", parent=body, fontName="Helvetica-Bold", fontSize=7.3,
        leading=9, textColor=colors.white,
    )
    metric_label = ParagraphStyle(
        "MetricLabel", parent=small, fontName="Helvetica-Bold", textColor=muted,
    )
    metric_value = ParagraphStyle(
        "MetricValue", parent=body, fontName="Helvetica-Bold", fontSize=10,
        leading=12, textColor=navy,
    )

    def page_header_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(line)
        canvas.setLineWidth(0.4)
        canvas.line(1.35 * cm, height - 0.92 * cm, width - 1.35 * cm, height - 0.92 * cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(muted)
        canvas.drawString(1.35 * cm, height - 0.72 * cm, "EXPLORADOR NACIONAL DE BIOMETANO · INFORME DE SCREENING")
        canvas.drawRightString(width - 1.35 * cm, 0.65 * cm, f"Página {document.page}")
        canvas.drawString(1.35 * cm, 0.65 * cm, str(report["identity"]["cell_id"]))
        canvas.restoreState()

    def styled_table(data: list[list[Any]], widths: list[float], *, header: bool = True) -> Any:
        table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.35, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header:
            commands.extend([
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FA")]),
            ])
        table.setStyle(TableStyle(commands))
        return table

    identity = report["identity"]
    executive = report["executive"]
    story: list[Any] = [
        _paragraph(report["title"], title_style),
        _paragraph(
            f"Celda {identity['cell_id']} · {identity['province']} · {identity['ccaa']} · generado {report['generated_at']}",
            subtitle,
        ),
    ]
    warning = Table(
        [[_paragraph(
            "LECTURA CORRECTA — La puntuación ordena dónde adquirir evidencia. No es probabilidad, viabilidad, permiso ni capacidad de conexión confirmada.",
            body,
        )]],
        colWidths=[18.1 * cm],
    )
    warning.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale_gold),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#D4A72C")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([warning, Spacer(1, 8), _paragraph("1. Resumen ejecutivo", section)])

    metric_items = [
        ("Prioridad relativa", executive["priority"]),
        ("Estado de screening", executive["screening_status"]),
        ("Evidencia de screening", executive["screening_evidence"]),
        ("Prefactibilidad", executive["prefeasibility"]),
        ("Evidencia de prefactibilidad", executive["prefeasibility_evidence"]),
        ("Riesgo de digestato", executive["digestate_risk"]),
    ]
    metric_cells = [
        [
            _rich_paragraph(
                f"{xml_escape(label)}<br/><font size='10'><b>{xml_escape(str(value))}</b></font>",
                metric_label,
            )
            for label, value in metric_items[:3]
        ],
        [
            _rich_paragraph(
                f"{xml_escape(label)}<br/><font size='10'><b>{xml_escape(str(value))}</b></font>",
                metric_label,
            )
            for label, value in metric_items[3:]
        ],
    ]
    metrics = Table(metric_cells, colWidths=[6.03 * cm] * 3)
    metrics.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, line),
        ("BACKGROUND", (0, 0), (-1, -1), pale_blue),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([metrics, Spacer(1, 7)])

    location_data = [
        [_paragraph("Campo", table_head), _paragraph("Valor", table_head)],
        [_paragraph("Escala", body), _paragraph(f"{identity['grid_level']} · {identity['resolution']}", body)],
        [_paragraph("Coordenadas", body), _paragraph(identity["coordinates"], body)],
        [_paragraph("Nivel de prioridad", body), _paragraph(identity["priority_level"], body)],
        [_paragraph("Exclusión física", body), _paragraph(executive["physical_exclusion"], body)],
        [_paragraph("Alcance", body), _paragraph(identity["scope"], body)],
    ]
    story.extend([
        styled_table(location_data, [4.2 * cm, 13.9 * cm]),
        Spacer(1, 7),
        _paragraph("Declaración oficial del screening", section),
        _paragraph(report["official_statement"], body),
        _paragraph("Fortalezas observadas", section),
        *_bullet_list(report["strengths"][:7], body),
        _paragraph("Alertas y debilidades", section),
        *_bullet_list(report["weaknesses"][:7], body),
    ])
    links = report["map_links"]
    if links["openstreetmap"]:
        story.extend([
            Spacer(1, 3),
            _paragraph("Seguimiento cartográfico", section),
            _rich_paragraph(
                f'<link href="{links["openstreetmap"]}" color="#176B87">Abrir coordenadas en OpenStreetMap</link>'
                f' · <link href="{links["google_maps"]}" color="#176B87">Abrir en Google Maps</link>',
                body,
            ),
            _paragraph("Los enlaces ubican el centro de la celda; no identifican una parcela ni acreditan disponibilidad del suelo.", small),
        ])

    story.extend([PageBreak(), _paragraph("2. Indicadores técnicos y territoriales", title_style)])
    story.append(_paragraph(
        "Cada indicador conserva su nivel de evidencia. Los valores proxy sirven para ordenar comprobaciones, no para cerrar decisiones de ingeniería o permisos.",
        subtitle,
    ))
    technical_data = [[
        _paragraph("Indicador", table_head),
        _paragraph("Valor", table_head),
        _paragraph("Evidencia", table_head),
        _paragraph("Interpretación", table_head),
    ]]
    for item in report["technical_indicators"]:
        technical_data.append([
            _paragraph(item["indicator"], small),
            _paragraph(item["value"], small),
            _paragraph(item["evidence"], small),
            _paragraph(item["interpretation"], small),
        ])
    story.append(styled_table(technical_data, [3.45 * cm, 3.5 * cm, 2.6 * cm, 8.55 * cm]))

    story.extend([PageBreak(), _paragraph("3. Gates críticos de prefactibilidad", title_style)])
    story.append(_paragraph(
        "Un punto no pasa a prefactibilidad por tener una prioridad alta. Los gates siguientes requieren evidencia externa y trazable; 'No verificado' nunca significa favorable.",
        subtitle,
    ))
    gate_data = [[
        _paragraph("Gate", table_head), _paragraph("Estado", table_head), _paragraph("Evidencia registrada", table_head),
    ]]
    for item in report["critical_gates"]:
        gate_data.append([
            _paragraph(item["gate"], body), _paragraph(item["status"], body), _paragraph(item["evidence"], body),
        ])
    story.extend([
        styled_table(gate_data, [6.6 * cm, 3.1 * cm, 8.4 * cm]),
        Spacer(1, 8),
        _paragraph("Comprobaciones externas obligatorias", section),
        *_bullet_list(report["mandatory_external_checks"], small),
    ])

    story.extend([PageBreak(), _paragraph("4. Procedencia, alcance y límites", title_style)])
    provenance = report["provenance"]
    provenance_data = [
        [_paragraph("Campo", table_head), _paragraph("Valor", table_head)],
        [_paragraph("Versión del método", body), _paragraph(provenance["method_version"], body)],
        [_paragraph("Fecha del snapshot", body), _paragraph(provenance["data_date"], body)],
        [_paragraph("Variable objetivo", body), _paragraph(provenance["target"], body)],
        [_paragraph("Fecha de generación", body), _paragraph(report["generated_at"], body)],
    ]
    story.extend([
        styled_table(provenance_data, [4.3 * cm, 13.8 * cm]),
        Spacer(1, 8),
        _paragraph("Fuentes y antigüedad", section),
        *_bullet_list(provenance["sources"], body),
        Spacer(1, 5),
        _paragraph("Limitaciones de uso", section),
        *_bullet_list(report["limitations"], body),
        Spacer(1, 8),
    ])
    closing = Table(
        [[_paragraph(
            "SIGUIENTE PASO RECOMENDADO — Usar este documento como checklist de adquisición de evidencia: parcela y urbanismo, contratos de sustrato, conexiones reales, digestato, agua, evaluación ambiental y economía del proyecto.",
            body,
        )]],
        colWidths=[18.1 * cm],
    )
    closing.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale_blue),
        ("BOX", (0, 0), (-1, -1), 0.7, blue),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(closing)
    doc.build(story, onFirstPage=page_header_footer, onLaterPages=page_header_footer)
    return buffer.getvalue()


def safe_point_report_filename(cell_id: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(cell_id)).encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-._") or "sin-identificador"
    return f"informe_punto_{token}.pdf"


def export_point_report_pdf(
    cell: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
    *,
    destination: str | Path | None = None,
    generated_at: str | None = None,
) -> bytes | Path:
    payload = point_report_pdf_bytes(cell, manifest, generated_at=generated_at)
    if destination is None:
        return payload
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


__all__ = [
    "build_point_report_data",
    "point_report_pdf_bytes",
    "export_point_report_pdf",
    "safe_point_report_filename",
]
