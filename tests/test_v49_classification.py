from sergio_biometano_app.src.classification_v49 import (
    METHOD_VERSION_V49,
    classify_v49,
    diversify_top_k,
    parent_5km_id,
)


def base_row(**overrides):
    row = {
        "cell_id": "CRS3035RES1000mN2263000E3362000",
        "score_0_100": 84,
        "robust_tier_v48": "A_prioritaria_condicionada",
        "model_rank_confidence_v48": "media",
        "nitrate_intersects": False,
        "copdem_slope_median_deg_v47": 3.2,
        "hydrology_status": "verificado parcial nacional",
        "gas_pipeline_distance_km_proxy": 4.0,
        "electric_substation_distance_km_proxy": 6.0,
        "road_distance_km": 2.0,
        "cropland_share": 0.8,
        "built_up_share": 0.04,
        "natura2000_distance_km": 3.0,
        "hard_veto": False,
        "veto_reasons": [],
        "review_reasons": [],
    }
    row.update(overrides)
    return row


def test_nitrate_is_digestate_risk_not_automatic_site_veto():
    result = classify_v49(
        base_row(
            nitrate_intersects=True,
            nitrate_intersection_share=0.2,
            hard_veto=True,
            veto_reasons=[
                "intersección con zona vulnerable a nitratos",
                "zona de nitratos: Zona A",
            ],
        )
    )
    assert result["hard_veto"] is False
    assert result["digestate_risk"] == "alto"
    assert result["screening_status"] == "prioridad alta de investigación"
    assert any("digestato" in reason for reason in result["review_reasons"])
    assert not result["veto_reasons"]


def test_non_nitrate_physical_exclusion_is_preserved():
    result = classify_v49(
        base_row(
            hard_veto=True,
            veto_reasons=["hard_built_up_ge30pct"],
            constraint_flags=["hard_built_up_ge30pct"],
        )
    )
    assert result["hard_veto"] is True
    assert result["screening_status"] == "descartado por filtro físico"
    assert result["prefeasibility_status"] == "descartada"


def test_project_completeness_is_never_full_when_critical_gates_are_unknown():
    result = classify_v49(base_row())
    assert result["screening_evidence_completeness"] == 1.0
    assert result["prefeasibility_evidence_completeness"] == 0.0
    assert result["data_completeness"] == 1.0
    assert len(result["missing_critical_gates"]) >= 10
    assert result["prefeasibility_status"] == "no iniciada"


def test_prefeasibility_requires_every_critical_gate():
    verified = {
        "supply_contract_verified": True,
        "feedstock_quality_verified": True,
        "gas_capacity_verified": True,
        "electricity_capacity_verified": True,
        "cadastral_verified": True,
        "planning_verified": True,
        "digestate_plan_verified": True,
        "water_permit_verified": True,
        "environmental_permit_verified": True,
        "offtake_verified": True,
        "economics_verified": True,
    }
    result = classify_v49(base_row(**verified))
    assert result["prefeasibility_evidence_completeness"] == 1.0
    assert result["prefeasibility_status"] == "prefactible"
    assert result["missing_critical_gates"] == []


def test_failed_critical_gate_discards_prefeasibility_not_screening_priority():
    result = classify_v49(base_row(planning_verified=False))
    assert result["prefeasibility_status"] == "descartada"
    assert "compatibilidad urbanística" in result["failed_critical_gates"]
    assert result["screening_status"] == "prioridad alta de investigación"


def test_parent_id_groups_twenty_five_one_km_children():
    assert parent_5km_id("CRS3035RES1000mN2263000E3362000") == "CRS3035RES5000mN2260000E3360000"
    assert parent_5km_id("CRS3035RES5000mN2260000E3360000") == "CRS3035RES5000mN2260000E3360000"


def test_diverse_top_k_keeps_one_child_per_parent_and_region():
    rows = [
        {"cell_id": "a", "parent_5km_id": "p1", "province": "X", "score_0_100": 99},
        {"cell_id": "b", "parent_5km_id": "p1", "province": "X", "score_0_100": 98},
        {"cell_id": "c", "parent_5km_id": "p2", "province": "X", "score_0_100": 97},
        {"cell_id": "d", "parent_5km_id": "p3", "province": "Y", "score_0_100": 96},
    ]
    selected = diversify_top_k(rows, k_per_region=2)
    assert [row["cell_id"] for row in selected] == ["a", "c", "d"]
    assert all(row["method_version"] == METHOD_VERSION_V49 for row in selected)
