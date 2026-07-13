import re
from pathlib import Path

from sergio_biometano_app.src.point_reports import (
    build_point_report_data,
    export_point_report_pdf,
    point_report_pdf_bytes,
    safe_point_report_filename,
)


def point_cell(**overrides):
    cell = {
        "cell_id": "CRS3035RES1000mN1660000E2875000",
        "grid_level": "refinamiento 1 km",
        "source_resolution_km": 1,
        "lon": -6.1559186,
        "lat": 36.6375519,
        "province": "Cádiz",
        "ccaa": "Andalucía",
        "score_0_100": 80,
        "original_tier": "B_viable_revisar",
        "screening_status": "prioridad alta de investigación",
        "screening_evidence_completeness": 1.0,
        "prefeasibility_status": "no iniciada",
        "prefeasibility_evidence_completeness": 0.0,
        "hard_veto": False,
        "veto_reasons": [],
        "review_reasons": ["zona vulnerable a nitratos: revisar digestato"],
        "key_drivers": ["gas próximo", "residuos orgánicos favorables"],
        "feedstock_score": 0.24,
        "organic_waste_score": 0.98,
        "gas_pipeline_distance_km_proxy": 9.48,
        "road_distance_km": 2.14,
        "electric_substation_distance_km_proxy": 1.89,
        "electric_line_distance_km_proxy": 0.59,
        "cropland_share": 0.16,
        "built_up_share": 0.08,
        "natura2000_share": 0.0,
        "natura2000_distance_km": 1.17,
        "nitrate_intersects": True,
        "nitrate_intersection_share": 1.0,
        "nitrate_zone_name": "Valle del Guadalete",
        "digestate_risk": "alto",
        "copdem_elevation_median_m_v47": 63.264,
        "copdem_slope_median_deg_v47": 8.3705,
        "copdem_slope_p90_deg_v47": 18.9004,
        "snczi_q100_intersects_v47": False,
        "snczi_q100_status_v47": "no detectado en cartografía publicada; no equivale a ausencia de riesgo",
        "screening_evidence": '{"corredor gasista":"proxy","corredor eléctrico":"proxy","hidrología publicada":"verificado parcial"}',
        "missing_critical_gates": ["capacidad real de conexión gasista", "compatibilidad urbanística"],
        "failed_critical_gates": ["parcela y situación catastral"],
        "missing_checks": ["capacidad real de conexión gasista", "compatibilidad urbanística"],
        "prefeasibility_evidence": '{"contrato y disponibilidad de sustrato":"carta de interés"}',
        "method_version": "sergio-national-v49-evidence",
        "data_date": "2026-07-10",
    }
    cell.update(overrides)
    return cell


def manifest():
    return {
        "method_version": "sergio-national-v49-evidence",
        "as_of": "2026-07-10",
        "target": "prioridad para adquirir evidencia de prefactibilidad",
        "scope": {"refined_1km": "universo priorizado, no cobertura nacional exhaustiva"},
        "source_vintages": {
            "roads": "CNIG/IGN BTN100 2021",
            "gas_corridor": "GGIT/OSM heterogéneo; no capacidad",
        },
        "limitations": ["La distancia a infraestructura no acredita capacidad."],
        "not_claimed": ["probabilidad", "viabilidad", "permiso", "capacidad de conexión"],
    }


def _indicator(report, name):
    return next(item for item in report["technical_indicators"] if item["indicator"] == name)


def _gate(report, name):
    return next(item for item in report["critical_gates"] if item["gate"] == name)


def test_report_data_separates_priority_evidence_and_prefeasibility():
    report = build_point_report_data(point_cell(hard_veto="false"), manifest(), generated_at="2026-07-13 20:00 UTC")
    assert report["identity"]["coordinates"] == "36.637552, -6.155919"
    assert report["executive"]["priority"] == "80/100"
    assert report["executive"]["screening_evidence"] == "100%"
    assert report["executive"]["prefeasibility"] == "no iniciada"
    assert report["executive"]["physical_exclusion"] == "No detectada en los filtros disponibles"
    assert "viable" not in report["identity"]["priority_level"].lower()
    assert report["provenance"]["sources"][0].startswith("Carreteras:")


def test_report_marks_missing_failed_and_supplied_gates_without_inventing_compliance():
    report = build_point_report_data(point_cell(), manifest())
    assert _gate(report, "capacidad real de conexión gasista")["status"] == "Pendiente"
    assert _gate(report, "compatibilidad urbanística")["status"] == "Pendiente"
    assert _gate(report, "parcela y situación catastral")["status"] == "No superado"
    supplied = _gate(report, "contrato y disponibilidad de sustrato")
    assert supplied["status"] == "Evidencia aportada"
    assert supplied["evidence"] == "carta de interés"
    assert all(item["status"] != "Cumplido" for item in report["critical_gates"])


def test_report_explains_infrastructure_and_nitrates_as_proxies_not_permissions():
    report = build_point_report_data(point_cell(), manifest())
    gas = _indicator(report, "Distancia al corredor gasista")
    electricity = _indicator(report, "Distancia a subestación eléctrica")
    nitrates = _indicator(report, "Zona vulnerable a nitratos")
    assert gas["value"] == "9,48 km"
    assert "no acredita capacidad" in gas["interpretation"].lower()
    assert "no acredita capacidad" in electricity["interpretation"].lower()
    assert "no es un veto universal" in nitrates["interpretation"].lower()


def test_missing_technical_values_are_no_verificado_not_no_constraint():
    cell = point_cell(
        gas_pipeline_distance_km_proxy=None,
        electric_substation_distance_km_proxy=None,
        snczi_q100_intersects_v47=None,
        snczi_q100_status_v47=None,
    )
    report = build_point_report_data(cell, manifest())
    assert _indicator(report, "Distancia al corredor gasista")["value"] == "No verificado"
    assert _indicator(report, "Distancia a subestación eléctrica")["value"] == "No verificado"
    assert _indicator(report, "Inundabilidad publicada Q100")["value"] == "No verificado"


def test_report_exposes_coordinate_follow_up_links_and_safe_filename():
    report = build_point_report_data(point_cell(), manifest())
    assert "36.637552" in report["map_links"]["openstreetmap"]
    assert "-6.155919" in report["map_links"]["google_maps"]
    assert safe_point_report_filename("ES/001: Cádiz") == "informe_punto_ES-001-Cadiz.pdf"


def test_detailed_report_is_a_multi_page_pdf_and_can_be_saved(tmp_path: Path):
    payload = point_report_pdf_bytes(point_cell(), manifest(), generated_at="2026-07-13 20:00 UTC")
    assert payload.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", payload)) >= 4
    target = tmp_path / "point-report.pdf"
    returned = export_point_report_pdf(point_cell(), manifest(), destination=target)
    assert returned == target
    assert target.read_bytes().startswith(b"%PDF")
