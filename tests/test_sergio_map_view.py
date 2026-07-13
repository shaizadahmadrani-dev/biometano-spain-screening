import json
from pathlib import Path

from sergio_biometano_app.src.map_view import _aggregate, _spatially_balanced_sample, build_map, status_color


def test_public_bundle_contains_all_selectable_map_layers():
    layers_dir = Path(__file__).parents[1] / "sergio_biometano_app" / "data" / "map_layers"
    expected = {
        "built_up_proxy.geojson",
        "electric_lines.geojson",
        "feedstock_proxy.geojson",
        "gas_pipelines.geojson",
        "high_capacity_roads.geojson",
        "natura2000_sites.geojson",
        "nitrate_zones.geojson",
        "operating_plants.geojson",
        "substations.geojson",
    }

    assert {path.name for path in layers_dir.glob("*.geojson")} == expected
    for name in expected:
        payload = json.loads((layers_dir / name).read_text(encoding="utf-8"))
        assert payload["type"] == "FeatureCollection"
        assert payload["features"], f"{name} must contain at least one feature"


def test_mixed_national_bucket_is_review_not_hard_veto():
    rows = [
        {"cell_id": "v", "lat": 40.0, "lon": -3.0, "score_0_100": 90, "hard_veto": True, "screening_status": "descartado preliminar"},
        {"cell_id": "r", "lat": 40.01, "lon": -3.01, "score_0_100": 80, "hard_veto": False, "screening_status": "requiere revisión"},
    ]
    bucket = _aggregate(rows, step=0.25)[0]
    assert bucket["hard_veto"] is False
    assert bucket["screening_status"] == "requiere revisión"
    assert bucket["aggregate_veto_count"] == 1
    assert status_color(bucket) != status_color(rows[0])
    assert bucket["lat"] == 40.0
    assert bucket["lon"] == -3.0
    assert bucket["representative_cell_id"] == "v"


def test_national_marker_limit_preserves_geographic_extremes():
    rows = [
        {"cell_id": "canary", "lat": 28.1, "lon": -16.5, "score_0_100": 20},
        {"cell_id": "west", "lat": 42.0, "lon": -9.0, "score_0_100": 30},
        {"cell_id": "center-high", "lat": 40.4, "lon": -3.7, "score_0_100": 99},
        {"cell_id": "east", "lat": 41.4, "lon": 2.1, "score_0_100": 40},
    ]
    selected = _spatially_balanced_sample(rows, max_rows=3, step=0.75)
    selected_ids = {row["cell_id"] for row in selected}
    assert {"canary", "east"} <= selected_ids
    assert len(selected) == 3


def test_all_veto_bucket_remains_red():
    rows = [
        {"cell_id": "a", "lat": 40.0, "lon": -3.0, "score_0_100": 90, "hard_veto": True, "screening_status": "descartado preliminar"},
        {"cell_id": "b", "lat": 40.01, "lon": -3.01, "score_0_100": 80, "hard_veto": True, "screening_status": "descartado preliminar"},
    ]
    bucket = _aggregate(rows, step=0.25)[0]
    assert bucket["hard_veto"] is True
    assert bucket["aggregate_veto_count"] == 2


def test_electric_lines_and_substations_are_separate_layers(tmp_path):
    empty = {"type": "FeatureCollection", "features": []}
    (tmp_path / "electric_lines.geojson").write_text(json.dumps(empty), encoding="utf-8")
    (tmp_path / "substations.geojson").write_text(json.dumps(empty), encoding="utf-8")
    _, metadata = build_map([], layers_dir=tmp_path)
    assert metadata["layers"]["Líneas eléctricas"] is True
    assert metadata["layers"]["Subestaciones"] is True


def test_unselected_optional_layers_are_not_embedded(tmp_path):
    feature = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-3, 40]}, "properties": {}}],
    }
    (tmp_path / "substations.geojson").write_text(json.dumps(feature), encoding="utf-8")
    map_without, _ = build_map([], layers_dir=tmp_path, show_layers=[])
    map_with, _ = build_map([], layers_dir=tmp_path, show_layers=["Subestaciones"])
    assert "substations" not in map_without.get_root().render().lower()
    assert len(map_with.get_root().render()) > len(map_without.get_root().render())


def test_popup_escapes_untrusted_text():
    map_object, _ = build_map(
        [{"cell_id": "<script>alert(1)</script>", "province": "<img src=x>", "lat": 40, "lon": -3, "score_0_100": 50}],
        national=False,
    )
    html = map_object.get_root().render()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_map_uses_dark_basemap_and_readable_popup():
    map_object, _ = build_map(
        [{"cell_id": "dark", "province": "Badajoz", "lat": 40, "lon": -3, "score_0_100": 70}],
        national=False,
    )
    html = map_object.get_root().render().lower()
    assert "basemaps.cartocdn.com/dark_all" in html
    assert "background:#111a22" in html


def test_map_offers_satellite_and_topographic_relief_basemaps():
    map_object, metadata = build_map([], national=True)
    html = map_object.get_root().render().lower()
    assert metadata["default_basemap"] == "Oscuro (estándar)"
    assert metadata["basemaps"] == ["Oscuro (estándar)", "Satélite con relieve", "Topográfico con relieve"]
    assert "world_imagery/mapserver/tile" in html
    assert "tile.opentopomap.org" in html


def test_conditioned_priority_has_its_own_blue_colour():
    conditioned = {"screening_status": "prioritario condicionado", "hard_veto": False}
    review = {"screening_status": "requiere revisión", "hard_veto": False}
    assert status_color(conditioned) != status_color(review)


def test_official_snczi_wms_is_only_embedded_when_selected(tmp_path):
    map_without, meta_without = build_map([], layers_dir=tmp_path, show_layers=[])
    map_with, meta_with = build_map(
        [], layers_dir=tmp_path, show_layers=["Inundación SNCZI T100 (oficial)"]
    )
    assert "zi_laminasq100" not in map_without.get_root().render().lower()
    assert "zi_laminasq100" in map_with.get_root().render().lower()
    assert meta_without["layers"]["Inundación SNCZI T100 (oficial)"] is True
    assert meta_with["layers"]["Inundación SNCZI T100 (oficial)"] is True


def test_natura_urban_and_feedstock_are_selectable_layers(tmp_path):
    empty = {"type": "FeatureCollection", "features": []}
    for name in ("natura2000_sites.geojson", "built_up_proxy.geojson", "feedstock_proxy.geojson"):
        (tmp_path / name).write_text(json.dumps(empty), encoding="utf-8")
    map_object, metadata = build_map(
        [],
        layers_dir=tmp_path,
        show_layers=["Natura 2000", "Suelo construido (proxy WorldCover)", "Materia prima alta (proxy macro)"],
    )
    html = map_object.get_root().render()
    assert metadata["layers"]["Natura 2000"] is True
    assert metadata["layers"]["Suelo construido (proxy WorldCover)"] is True
    assert metadata["layers"]["Materia prima alta (proxy macro)"] is True
    assert "Natura 2000" in html
