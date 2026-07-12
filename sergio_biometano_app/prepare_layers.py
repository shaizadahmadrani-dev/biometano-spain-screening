"""Optional, lightweight GeoJSON exports for Sergio's map.

This module keeps geospatial I/O outside the pure cell-preparation contract.  A
missing optional source is represented in the returned manifest and never
causes the national cell export to fail.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional


OUTPUT_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:3035"

LAYER_NAMES = (
    "nitrate_zones",
    "gas_pipelines",
    "high_capacity_roads",
    "electric_lines",
    "substations",
    "operating_plants",
    "natura2000_sites",
    "built_up_proxy",
    "feedstock_proxy",
)

_SIMPLIFY_TOLERANCE_METRES = {
    "nitrate_zones": 100.0,
    "gas_pipelines": 25.0,
    "high_capacity_roads": 25.0,
    "electric_lines": 25.0,
    "substations": 0.0,
    "operating_plants": 0.0,
    "natura2000_sites": 500.0,
    "built_up_proxy": 0.0,
    "feedstock_proxy": 0.0,
}

BUILT_UP_SHARE_THRESHOLD = 0.10
FEEDSTOCK_HIGH_QUANTILE = 0.95


def _source_value(sources: Any, name: str) -> Any:
    if isinstance(sources, Mapping):
        return sources.get(name)
    return getattr(sources, name, None)


def _relative_source(path: Optional[Path], project_root: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    if project_root is not None:
        try:
            return str(path.resolve().relative_to(project_root.resolve()))
        except ValueError:
            pass
    return str(path)


def _layer_source(sources: Any, layer_name: str) -> Optional[Path]:
    if layer_name == "nitrate_zones":
        value = _source_value(sources, "nitrate_geojson")
    elif layer_name == "gas_pipelines":
        paths = _source_value(sources, "gas_pipelines") or ()
        value = next(
            (path for path in paths if Path(path).name == "gas_pipeline_osm_spain_curated.geoparquet"),
            None,
        )
    elif layer_name == "high_capacity_roads":
        value = Path("processed/cnig_btn100_roads_2021.geoparquet")
    elif layer_name == "electric_lines":
        value = _source_value(sources, "electric_lines")
    elif layer_name == "substations":
        value = _source_value(sources, "electric_substations")
    elif layer_name == "operating_plants":
        value = _source_value(sources, "operating_plants")
    elif layer_name == "natura2000_sites":
        value = _source_value(sources, "natura2000_geojson")
    elif layer_name in {"built_up_proxy", "feedstock_proxy"}:
        value = _source_value(sources, "v22_geoparquet")
    else:
        value = None
    return Path(value) if value is not None else None


def _resolve_source(path: Optional[Path], project_root: Optional[Path], sources: Any, layer_name: str) -> Optional[Path]:
    if path is None:
        return None
    if path.is_absolute():
        return path
    # The roads path is deliberately relative because it is not part of the
    # existing SourcePaths contract.  Other paths are already rooted by source
    # discovery, but resolving them here also supports small test fixtures.
    if project_root is not None:
        return project_root / path
    source_root = _source_value(sources, "project_root")
    return (Path(source_root) / path) if source_root else path


def _read_vector(path: Path, *, member: Optional[str] = None):
    import geopandas as gpd  # type: ignore

    if path.suffix.lower() in {".parquet", ".geoparquet"}:
        return gpd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        import pandas as pd  # type: ignore

        frame = pd.read_csv(path)
        lon = next((column for column in ("final_longitude", "longitude", "lon") if column in frame.columns), None)
        lat = next((column for column in ("final_latitude", "latitude", "lat") if column in frame.columns), None)
        if not lon or not lat:
            raise ValueError("CSV no contiene coordenadas de longitud/latitud")
        return gpd.GeoDataFrame(
            frame,
            geometry=gpd.points_from_xy(frame[lon], frame[lat]),
            crs=OUTPUT_CRS,
        )
    if path.suffix.lower() == ".zip" and member:
        return gpd.read_file(f"zip://{path}!{member}")
    return gpd.read_file(path)


def _column(frame: Any, candidates: tuple[str, ...], default: Any = None):
    for candidate in candidates:
        if candidate in frame.columns:
            return frame[candidate]
    return default


def _selected_frame(frame: Any, fields: Mapping[str, tuple[str, ...]], defaults: Mapping[str, Any]):
    import geopandas as gpd  # type: ignore

    selected = gpd.GeoDataFrame(index=frame.index, geometry=frame.geometry, crs=frame.crs)
    for output_name, candidates in fields.items():
        values = _column(frame, candidates)
        selected[output_name] = values if values is not None else defaults.get(output_name)
    return selected


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "si", "sí"}


def filter_high_capacity_roads(frame: Any):
    """Keep only the explicit BTN100 high-capacity road proxy rows."""

    if "is_high_capacity_road_proxy" not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame.loc[frame["is_high_capacity_road_proxy"].map(_truthy)].copy()


def simplify_projected(frame: Any, layer_name: str):
    """Simplify in a metric CRS and return WGS84 GeoJSON-ready geometry."""

    if frame.empty:
        return frame.copy()
    working = frame.copy()
    caveat = ""
    if working.crs is None:
        working = working.set_crs(OUTPUT_CRS, allow_override=True)
        caveat = " CRS absent; se asumió EPSG:4326."
    metric = working.to_crs(METRIC_CRS)
    tolerance = _SIMPLIFY_TOLERANCE_METRES.get(layer_name, 25.0)
    if tolerance > 0:
        metric["geometry"] = metric.geometry.simplify(tolerance, preserve_topology=True)
    result = metric.to_crs(OUTPUT_CRS)
    result.attrs["crs_caveat"] = caveat
    return result


def _prepare_layer(frame: Any, layer_name: str):
    if layer_name == "nitrate_zones":
        return _selected_frame(
            frame,
            {"zone_name": ("zone_name", "nom_zv", "name"), "zone_code": ("zone_code", "cod_zv", "code", "id"), "source": ("source",)},
            {"source": "MITECO 2025"},
        )
    if layer_name == "gas_pipelines":
        return _selected_frame(
            frame,
            {"name": ("name",), "operator": ("operator",), "substance": ("substance", "pipeline_substance"), "source": ("source",)},
            {"source": "OSM España curado"},
        )
    if layer_name == "high_capacity_roads":
        filtered = filter_high_capacity_roads(frame)
        return _selected_frame(
            filtered,
            {"name": ("ETIQUETA", "name", "ID_VIAL"), "road_type": ("tipo_0605_coarse_desc", "TIPO_0605"), "is_high_capacity_road_proxy": ("is_high_capacity_road_proxy",), "source": ("source",)},
            {"source": "BTN100 2021"},
        )
    if layer_name == "electric_lines":
        return _selected_frame(
            frame,
            {"feature_id": ("ID", "ID_BD", "ID_CODIGO"), "line_type": ("TIPO_0702",), "source": ("source",)},
            {"source": "BTN100 2015"},
        )
    if layer_name == "substations":
        return _selected_frame(
            frame,
            {"feature_id": ("ID", "ID_BD", "ID_CODIGO"), "source": ("source",)},
            {"source": "BTN100 2015"},
        )
    if layer_name == "operating_plants":
        return _selected_frame(
            frame,
            {"name": ("name", "plant_name"), "type": ("type", "plant_type"), "source": ("source",), "confidence": ("confidence", "reconciliation_confidence")},
            {"source": "registro de plantas operativas"},
        )
    if layer_name == "natura2000_sites":
        return _selected_frame(
            frame,
            {
                "site_code": ("site_code", "codigo", "code"),
                "site_name": ("site_name", "nombre", "name"),
                "site_type": ("tipo", "site_type", "type"),
                "plan_name": ("nom_plan", "plan_name"),
                "source": ("source",),
            },
            {"source": "MITECO Red Natura 2000"},
        )
    if layer_name == "built_up_proxy":
        import pandas as pd  # type: ignore

        column = "worldcover2021_share_built_up_1km_sample25_v7"
        values = pd.to_numeric(frame.get(column), errors="coerce")
        filtered = frame.loc[values >= BUILT_UP_SHARE_THRESHOLD].copy()
        filtered["built_up_share"] = values.loc[filtered.index]
        return _selected_frame(
            filtered,
            {
                "cell_id": ("cell_1km_id_v22", "cell_id"),
                "built_up_share": ("built_up_share",),
                "source": ("source",),
            },
            {"source": "ESA WorldCover 2021; proxy de superficie construida"},
        )
    if layer_name == "feedstock_proxy":
        import pandas as pd  # type: ignore

        values = pd.to_numeric(frame.get("feedstock_score"), errors="coerce")
        threshold = float(values.quantile(FEEDSTOCK_HIGH_QUANTILE))
        filtered = frame.loc[values >= threshold].copy()
        filtered["feedstock_score"] = values.loc[filtered.index]
        filtered["relative_threshold"] = threshold
        return _selected_frame(
            filtered,
            {
                "cell_id": ("cell_1km_id_v22", "cell_id"),
                "feedstock_score": ("feedstock_score",),
                "relative_threshold": ("relative_threshold",),
                "source": ("source",),
            },
            {"source": "índice de materia prima v48; proxy macro relativo"},
        )
    raise KeyError(layer_name)


def _write_geojson(frame: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(frame.to_json(drop_id=True))
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def export_map_layers(output_dir: Path, sources: Any, project_root: Optional[Path] = None) -> dict[str, Any]:
    """Export selected optional layers and return a provenance manifest."""

    output_dir = Path(output_dir)
    project_root = Path(project_root) if project_root is not None else Path(_source_value(sources, "project_root") or output_dir)
    layer_manifest: dict[str, Any] = {}
    error_count = 0
    exported_count = 0
    source_cache: dict[tuple[str, Optional[str]], Any] = {}
    for layer_name in LAYER_NAMES:
        source = _layer_source(sources, layer_name)
        resolved = _resolve_source(source, project_root, sources, layer_name)
        entry: dict[str, Any] = {
            "status": "missing",
            "feature_count": 0,
            "source": _relative_source(resolved, project_root),
            "caveat": "fuente ausente; capa opcional no exportada",
        }
        if resolved is None or not resolved.exists():
            layer_manifest[layer_name] = entry
            continue
        try:
            member = None
            if layer_name == "electric_lines":
                member = _source_value(sources, "electric_lines_member")
            elif layer_name == "substations":
                member = _source_value(sources, "electric_substations_member")
            cache_key = (str(resolved.resolve()), member)
            if cache_key not in source_cache:
                source_cache[cache_key] = _read_vector(resolved, member=member)
            frame = source_cache[cache_key]
            prepared = simplify_projected(_prepare_layer(frame, layer_name), layer_name)
            destination = output_dir / f"{layer_name}.geojson"
            _write_geojson(prepared, destination)
            exported_count += 1
            entry.update(
                status="ok",
                feature_count=int(len(prepared)),
                path=str(destination.relative_to(output_dir)),
                caveat=(
                    "geometría simplificada en EPSG:3035 y devuelta a EPSG:4326. "
                    + ("Proximidad física es un proxy, no capacidad." if layer_name in {"gas_pipelines", "high_capacity_roads"} else "")
                    + (" WorldCover indica superficie construida, no clasificación urbanística." if layer_name == "built_up_proxy" else "")
                    + (" Índice relativo de materia prima; proxy macro, no suministro contratado." if layer_name == "feedstock_proxy" else "")
                    + (" Límite simplificado para visualización; la geometría oficial debe consultarse antes de decidir." if layer_name == "natura2000_sites" else "")
                    + str(prepared.attrs.get("crs_caveat", ""))
                ).strip(),
            )
        except Exception as exc:  # optional layers must not abort cell preparation
            error_count += 1
            entry.update(status="error", reason=f"{type(exc).__name__}: {exc}", caveat="fuente encontrada pero no se pudo exportar")
        layer_manifest[layer_name] = entry
    overall = "error" if error_count and not exported_count else "partial" if error_count or any(item["status"] == "missing" for item in layer_manifest.values()) else "ok"
    return {"status": overall, "layers": layer_manifest}
