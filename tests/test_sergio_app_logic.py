from pathlib import Path

import numpy as np

from sergio_biometano_app.src.explanations import summarize_cell
from sergio_biometano_app.src.exports import _snapshot_lines, export_pdf
from sergio_biometano_app.src.filters import comparison_table, filter_cells
from sergio_biometano_app.src.scenarios import score_scenario
from sergio_biometano_app.app import _status_callout


def base_cell(**overrides):
    cell = {
        "cell_id": "ES-001",
        "province": "Badajoz",
        "ccaa": "Extremadura",
        "official_score": 82,
        "tier": "A",
        "screening_status": "candidato de screening",
        "feedstock_score": 0.8,
        "organic_waste_score": 0.7,
        "best_gas_pipeline_dist_km": 8,
        "road_distance_km": 6,
        "land_environment_score": 0.7,
        "nitrate_vulnerable": False,
        "cadastral_verified": True,
        "grid_capacity_verified": None,
        "planning_verified": None,
    }
    cell.update(overrides)
    return cell


def test_nitrate_is_hard_veto_and_uses_defensible_wording():
    summary = summarize_cell(base_cell(nitrate_vulnerable=True))
    assert summary["hard_veto"] is True
    assert "Veto duro" in summary["official_statement"]
    assert "descartada preliminarmente" in summary["official_statement"]
    assert "viable" not in summary["official_statement"].lower()


def test_official_score_and_scenario_stay_separate_and_bounded():
    result = score_scenario(base_cell(official_score=91), weights={"feedstock": 1})
    assert result["score_type"] == "escenario"
    assert result["official_score"] == 91
    assert result["scenario_score_0_100"] == 80
    assert "no modifica el score oficial" in result["caveat"]


def test_missing_data_is_not_verified_not_compliant():
    summary = summarize_cell(base_cell(cadastral_verified=None, nitrate_vulnerable=None))
    assert summary["missing_checks"]
    assert all("No verificado" in item for item in summary["missing"])
    assert "cumplimiento" not in " ".join(summary["missing"]).lower()


def test_parquet_array_columns_do_not_create_fake_vetoes():
    summary = summarize_cell(
        base_cell(
            hard_veto=False,
            veto_reasons=np.array([], dtype=object),
            missing_checks=np.array(["hidrología: no verificado"], dtype=object),
        )
    )
    assert summary["hard_veto"] is False
    assert summary["veto_reasons"] == []
    assert summary["missing_checks"] == ["hidrología: no verificado"]


def test_soft_review_reasons_never_become_hard_veto():
    summary = summarize_cell(
        base_cell(
            hard_veto=False,
            veto_reasons=["gas_pipeline_gt10km"],
            review_reasons=["gas_pipeline_gt10km"],
        )
    )
    assert summary["hard_veto"] is False
    assert summary["veto_reasons"] == []
    assert summary["review_reasons"] == ["gas_pipeline_gt10km"]


def test_explicit_empty_missing_checks_preserves_candidate_status_copy():
    summary = summarize_cell(
        base_cell(
            screening_status="candidato de screening",
            missing_checks=[],
            review_reasons=[],
        )
    )
    assert summary["decision_label"].startswith("Candidato de screening")
    assert summary["mandatory_external_checks"]


def test_ui_callout_uses_canonical_screening_status():
    kind, _ = _status_callout(
        {"screening_status": "requiere revisión", "hard_veto": False, "missing_checks": [], "review_reasons": []}
    )
    assert kind == "warning"
    kind, _ = _status_callout(
        {"screening_status": "descartado preliminar", "hard_veto": False, "missing_checks": [], "review_reasons": []}
    )
    assert kind == "error"
    kind, _ = _status_callout(
        {"screening_status": "candidato de screening", "hard_veto": False, "missing_checks": [], "review_reasons": []}
    )
    assert kind == "success"
    kind, text = _status_callout(
        {"screening_status": "prioritario condicionado", "hard_veto": False, "missing_checks": [], "review_reasons": []}
    )
    assert kind == "info"
    assert "condicionada" in text.lower()


def test_filters_and_comparison_are_case_insensitive_and_capped():
    cells = [
        base_cell(cell_id="A", province="Badajoz", candidate_notes="only-a"),
        base_cell(cell_id="B", province="Cádiz", official_score=55),
        base_cell(cell_id="C", province="Badajoz", official_score=40),
        base_cell(cell_id="D", province="Badajoz", official_score=30),
        base_cell(cell_id="E", province="Badajoz", official_score=20),
        base_cell(cell_id="F", province="Badajoz", official_score=10),
    ]
    filtered = filter_cells(cells, province="badajoz", min_score=35, query="only-a")
    assert [row["cell_id"] for row in filtered] == ["A"]
    compared = comparison_table(cells, limit=99)
    assert len(compared) == 5


def test_comparison_preserves_original_v31_tier_alias():
    rows = [{"cell_id": "x", "original_tier": "B_viable_revisar", "score_0_100": 75}]
    result = comparison_table(rows, ["x"])
    assert result[0]["tier"] == "B_viable_revisar"


def test_pdf_is_generated_as_one_page_snapshot(tmp_path: Path):
    payload = export_pdf(
        summarize_cell(base_cell()),
        sources=["v31 CSV", "Manifest de procedencia"],
        caveats=["No es autorización ni viabilidad."],
    )
    assert isinstance(payload, bytes)
    assert payload.startswith(b"%PDF")
    target = tmp_path / "snapshot.pdf"
    returned = export_pdf(summarize_cell(base_cell()), destination=target)
    assert returned == target
    assert target.read_bytes().startswith(b"%PDF")


def test_pdf_labels_do_not_expose_legacy_viable_tier_wording():
    lines = _snapshot_lines({"tier": "B_viable_revisar", "official_score": 80})
    assert "viable" not in " ".join(lines).lower()
