import json

from sergio_biometano_app.src.explanations import summarize_cell
from sergio_biometano_app.src.filters import filter_cells
from sergio_biometano_app.src.map_view import STATUS_COLORS, _aggregate, status_color
from sergio_biometano_app.src.scenarios import has_hard_veto, score_scenario


def v49_row(**overrides):
    row = {
        "cell_id": "CRS3035RES1000mN2263000E3362000",
        "method_version": "sergio-national-v49-evidence",
        "screening_status": "prioridad alta de investigación",
        "prefeasibility_status": "no iniciada",
        "score_0_100": 84.0,
        "hard_veto": False,
        "nitrate_intersects": True,
        "nitrate_intersection_share": 0.3,
        "digestate_risk": "alto",
        "veto_reasons": json.dumps([]),
        "review_reasons": json.dumps(["riesgo alto de digestato por zona vulnerable a nitratos"]),
        "missing_checks": json.dumps(["capacidad real de conexión gasista"]),
        "missing_critical_gates": json.dumps(["contrato de suministro", "economía del proyecto"]),
        "feedstock_score": 0.8,
        "organic_waste_score": 0.7,
        "gas_pipeline_distance_km_proxy": 5.0,
        "road_distance_km": 4.0,
    }
    row.update(overrides)
    return row


def test_v49_nitrate_does_not_become_hard_veto_in_filters_or_scenario():
    row = v49_row()
    assert has_hard_veto(row) is False
    assert len(filter_cells([row], hard_veto=False)) == 1
    result = score_scenario(row)
    assert result["hard_veto"] is False
    assert result["scenario_score_0_100"] > 0


def test_legacy_v48_nitrate_semantics_remain_compatible():
    row = v49_row(method_version="sergio-national-v48", hard_veto=True)
    assert has_hard_veto(row) is True


def test_v49_explanation_separates_priority_digestate_and_prefeasibility():
    summary = summarize_cell(v49_row())
    assert summary["hard_veto"] is False
    assert summary["digestate_risk"] == "alto"
    assert summary["prefeasibility_status"] == "no iniciada"
    assert "contrato de suministro" in summary["missing_critical_gates"]
    assert "digestato" in " ".join(summary["review_reasons"]).lower()
    assert "prioridad" in summary["official_statement"].lower()
    assert "probabilidad" in summary["official_statement"].lower()


def test_v49_status_colors_are_explicit_and_physical_exclusion_wins():
    assert status_color(v49_row()) == STATUS_COLORS["prioridad alta de investigación"]
    assert status_color(v49_row(screening_status="prioridad media de investigación")) == STATUS_COLORS[
        "prioridad media de investigación"
    ]
    excluded = v49_row(hard_veto=True, screening_status="descartado por filtro físico")
    assert status_color(excluded) == STATUS_COLORS["descartado por filtro físico"]


def test_v49_national_bucket_color_uses_dominant_priority_not_best_child():
    rows = [
        v49_row(cell_id="high", lat=40.0, lon=-3.0, score_0_100=99, screening_status="prioridad alta de investigación"),
        v49_row(cell_id="low-1", lat=40.01, lon=-3.01, score_0_100=40, screening_status="prioridad baja de investigación"),
        v49_row(cell_id="low-2", lat=40.02, lon=-3.02, score_0_100=35, screening_status="prioridad baja de investigación"),
    ]
    bucket = _aggregate(rows, step=0.25)[0]
    assert bucket["representative_cell_id"] == "high"
    assert bucket["screening_status"] == "prioridad baja de investigación"
    assert bucket["aggregate_low_count"] == 2
