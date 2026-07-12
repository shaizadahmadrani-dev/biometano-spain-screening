import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Polygon

from sergio_biometano_app.prepare_layers import (
    export_map_layers,
    filter_high_capacity_roads,
    simplify_projected,
)


def test_high_capacity_filter_keeps_only_explicit_proxy_rows():
    roads = gpd.GeoDataFrame(
        {"is_high_capacity_road_proxy": [True, False, "1", "no"]},
        geometry=[LineString([(0, 0), (1, 1)])] * 4,
        crs="EPSG:4326",
    )
    filtered = filter_high_capacity_roads(roads)
    assert len(filtered) == 2
    assert filtered["is_high_capacity_road_proxy"].tolist() == [True, "1"]


def test_simplification_returns_wgs84_without_changing_selected_schema():
    frame = gpd.GeoDataFrame(
        {"zone_name": ["Zona A"], "zone_code": ["A"], "source": ["MITECO 2025"]},
        geometry=[Polygon([(0, 0), (0.001, 0), (0.001, 0.001), (0, 0.001)])],
        crs="EPSG:4326",
    )
    result = simplify_projected(frame, "nitrate_zones")
    assert result.crs.to_epsg() == 4326
    assert list(result.columns) == list(frame.columns)
    assert result.iloc[0]["zone_name"] == "Zona A"


def test_manifest_marks_missing_sources_explicitly(tmp_path: Path):
    manifest = export_map_layers(
        tmp_path,
        {
            "project_root": tmp_path,
            "nitrate_geojson": None,
            "gas_pipelines": (),
            "electric_lines": None,
            "electric_substations": None,
            "operating_plants": None,
        },
        tmp_path,
    )
    assert manifest["status"] == "partial"
    assert manifest["layers"]["nitrate_zones"]["status"] == "missing"
    assert manifest["layers"]["nitrate_zones"]["feature_count"] == 0
    assert "ausente" in manifest["layers"]["nitrate_zones"]["caveat"]


def test_export_filters_roads_and_keeps_small_provenance_schema(tmp_path: Path):
    roads_path = tmp_path / "processed" / "cnig_btn100_roads_2021.geoparquet"
    roads_path.parent.mkdir()
    roads = gpd.GeoDataFrame(
        {"ETIQUETA": ["A", "B"], "is_high_capacity_road_proxy": [True, False], "source": ["BTN", "BTN"]},
        geometry=[LineString([(0, 0), (1, 1)])] * 2,
        crs="EPSG:4326",
    )
    roads.to_parquet(roads_path)
    manifest = export_map_layers(
        tmp_path / "out",
        {"project_root": tmp_path, "nitrate_geojson": None, "gas_pipelines": (), "electric_lines": None, "electric_substations": None, "operating_plants": None},
        tmp_path,
    )
    entry = manifest["layers"]["high_capacity_roads"]
    assert entry["status"] == "ok"
    assert entry["feature_count"] == 1
    payload = json.loads((tmp_path / "out" / "high_capacity_roads.geojson").read_text(encoding="utf-8"))
    assert set(payload["features"][0]["properties"]) == {"name", "road_type", "is_high_capacity_road_proxy", "source"}


def test_export_adds_natura_built_up_and_feedstock_proxy_layers(tmp_path: Path):
    processed = tmp_path / "processed"
    raw = tmp_path / "raw"
    processed.mkdir()
    raw.mkdir()
    cells_path = processed / "cells.geoparquet"
    natura_path = raw / "natura.geojson"
    cells = gpd.GeoDataFrame(
        {
            "cell_1km_id_v22": ["a", "b", "c"],
            "worldcover2021_share_built_up_1km_sample25_v7": [0.04, 0.10, 0.40],
            "feedstock_score": [0.10, 0.50, 0.50],
        },
        geometry=[
            Polygon([(0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01)]),
            Polygon([(0.02, 0), (0.03, 0), (0.03, 0.01), (0.02, 0.01)]),
            Polygon([(0.04, 0), (0.05, 0), (0.05, 0.01), (0.04, 0.01)]),
        ],
        crs="EPSG:4326",
    )
    cells.to_parquet(cells_path)
    natura = gpd.GeoDataFrame(
        {"site_code": ["ES0001"], "site_name": ["Espacio A"], "tipo": ["ZEC"]},
        geometry=[Polygon([(0, 0), (0.1, 0), (0.1, 0.1), (0, 0.1)])],
        crs="EPSG:4326",
    )
    natura.to_file(natura_path, driver="GeoJSON")
    manifest = export_map_layers(
        tmp_path / "out",
        {
            "project_root": tmp_path,
            "v22_geoparquet": cells_path,
            "natura2000_geojson": natura_path,
            "nitrate_geojson": None,
            "gas_pipelines": (),
            "electric_lines": None,
            "electric_substations": None,
            "operating_plants": None,
        },
        tmp_path,
    )
    assert manifest["layers"]["natura2000_sites"]["feature_count"] == 1
    assert manifest["layers"]["built_up_proxy"]["feature_count"] == 2
    assert manifest["layers"]["feedstock_proxy"]["feature_count"] == 2
    assert "no clasificación urbanística" in manifest["layers"]["built_up_proxy"]["caveat"]
    assert "proxy macro" in manifest["layers"]["feedstock_proxy"]["caveat"]
