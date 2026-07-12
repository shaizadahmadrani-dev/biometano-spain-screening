"""Folium map rendering for the Sergio national explorer."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from html import escape
from pathlib import Path
from typing import Any

import folium
from folium.plugins import Fullscreen

STATUS_COLORS = {
    "prioridad alta de investigación": "#31c58d",
    "prioridad media de investigación": "#4db6ff",
    "prioridad baja de investigación": "#f0b44d",
    "descartado por filtro físico": "#ff6b6b",
    "candidato de screening": "#31c58d",
    "prioritario condicionado": "#4db6ff",
    "requiere revisión": "#f0b44d",
    "descartado preliminar": "#ff6b6b",
    "no verificado": "#d7a84a",
}


def _rows(cells: Any) -> list[dict[str, Any]]:
    if hasattr(cells, "to_dict") and hasattr(cells, "columns"):
        return [dict(row) for row in cells.to_dict(orient="records")]
    return [dict(row) for row in cells]


def _number(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "si", "sí", "veto"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_text(item) for item in value)
    return str(value)


def _html(value: Any) -> str:
    return escape(_text(value), quote=True)


def status_color(row: Mapping[str, Any]) -> str:
    if _truthy(row.get("hard_veto")):
        return STATUS_COLORS[
            "descartado por filtro físico"
            if "v49" in _text(row.get("method_version")).casefold()
            else "descartado preliminar"
        ]
    return STATUS_COLORS.get(_text(row.get("screening_status")), STATUS_COLORS["no verificado"])


def _popup(row: Mapping[str, Any], *, aggregate_count: int | None = None) -> folium.Popup:
    score = _number(row.get("score_0_100"))
    score_text = f"{score:.0f}/100" if score is not None else "no verificado"
    cell_id = _html(row.get("cell_id")) or "sin identificador"
    province = _html(row.get("province")) or "no verificada"
    status = _html(row.get("screening_status")) or "no verificado"
    veto = "Sí — veto duro" if _truthy(row.get("hard_veto")) else "No"
    extra = f"<br><b>Celdas agrupadas:</b> {aggregate_count}" if aggregate_count else ""
    if aggregate_count:
        extra += (
            f"<br><b>Con veto:</b> {int(row.get('aggregate_veto_count', 0) or 0)}"
            f"<br><b>Prioridad alta:</b> {int(row.get('aggregate_high_count', row.get('aggregate_candidate_count', 0)) or 0)}"
            f"<br><b>Prioridad media:</b> {int(row.get('aggregate_medium_count', row.get('aggregate_conditioned_count', 0)) or 0)}"
            f"<br><b>Prioridad baja/revisión:</b> {int(row.get('aggregate_low_count', row.get('aggregate_review_count', 0)) or 0)}"
        )
    html = (
        "<div style='font-family:Arial;min-width:210px;background:#111a22;color:#e7f0eb;padding:10px;border-radius:8px'>"
        f"<b>{cell_id}</b><br><b>Provincia:</b> {province}<br>"
        f"<b>Estado:</b> {status}<br><b>Score oficial:</b> {score_text}<br>"
        f"<b>Veto duro:</b> {veto}<br>"
        f"<b>Pendiente mediana:</b> {_html(row.get('copdem_slope_median_deg_v47')) or 'no verificada'}°<br>"
        f"<b>Acuerdo entre modelos:</b> {_html(row.get('model_rank_confidence_v48')) or 'no verificado'}{extra}</div>"
    )
    return folium.Popup(html, max_width=330)


def _numeric_sort(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(row) for row in rows),
        key=lambda row: (_number(row.get("score_0_100")) is not None, _number(row.get("score_0_100")) or -1),
        reverse=True,
    )


def _aggregate(rows: Iterable[Mapping[str, Any]], *, step: float = 0.25) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        lat, lon = _number(row.get("lat")), _number(row.get("lon"))
        if lat is None or lon is None:
            continue
        buckets.setdefault((round(lat / step), round(lon / step)), []).append(dict(row))
    aggregated: list[dict[str, Any]] = []
    for bucket_rows in buckets.values():
        is_v49 = any("v49" in _text(item.get("method_version")).casefold() for item in bucket_rows)
        non_veto_rows = [item for item in bucket_rows if not _truthy(item.get("hard_veto"))]
        representative = _numeric_sort((non_veto_rows or bucket_rows) if is_v49 else bucket_rows)[0]
        representative_cell_id = _text(representative.get("cell_id"))
        scores = [_number(item.get("score_0_100")) for item in bucket_rows]
        scores = [value for value in scores if value is not None]
        representative["score_0_100"] = max(scores) if scores else None
        representative["aggregate_count"] = len(bucket_rows)
        representative["representative_cell_id"] = representative_cell_id
        representative["cell_id"] = f"Agrupación ({len(bucket_rows)} celdas)"
        veto_count = sum(_truthy(item.get("hard_veto")) for item in bucket_rows)
        candidate_count = sum(_text(item.get("screening_status")) == "candidato de screening" for item in bucket_rows)
        conditioned_count = sum(_text(item.get("screening_status")) == "prioritario condicionado" for item in bucket_rows)
        high_count = sum(_text(item.get("screening_status")) == "prioridad alta de investigación" for item in bucket_rows)
        medium_count = sum(_text(item.get("screening_status")) == "prioridad media de investigación" for item in bucket_rows)
        low_count = sum(_text(item.get("screening_status")) == "prioridad baja de investigación" for item in bucket_rows)
        review_count = len(bucket_rows) - veto_count - candidate_count - conditioned_count
        representative["aggregate_veto_count"] = veto_count
        representative["aggregate_candidate_count"] = candidate_count
        representative["aggregate_conditioned_count"] = conditioned_count
        representative["aggregate_review_count"] = max(0, review_count)
        representative["aggregate_high_count"] = high_count
        representative["aggregate_medium_count"] = medium_count
        representative["aggregate_low_count"] = low_count
        if is_v49 and veto_count < len(bucket_rows):
            status_counts = (
                ("prioridad alta de investigación", high_count),
                ("prioridad media de investigación", medium_count),
                ("prioridad baja de investigación", low_count),
            )
            tie_priority = {status: -index for index, (status, _) in enumerate(status_counts)}
            dominant_status, dominant_count = max(
                status_counts,
                key=lambda item: (item[1], tie_priority[item[0]]),
            )
            if dominant_count:
                representative["screening_status"] = dominant_status
                representative["aggregate_dominant_status"] = dominant_status
        if veto_count == len(bucket_rows):
            representative["hard_veto"] = True
            representative["screening_status"] = "descartado por filtro físico" if is_v49 else "descartado preliminar"
            representative["veto_reasons"] = ["todas las celdas de la agrupación tienen veto duro"]
        elif veto_count:
            # A national bucket is context, not a candidate. A single vetoed
            # child must not paint every neighbouring non-veto cell red.
            representative["hard_veto"] = False
            if not is_v49:
                representative["screening_status"] = "requiere revisión"
            representative["veto_reasons"] = []
            representative["review_reasons"] = [
                f"agrupación mixta: {veto_count} de {len(bucket_rows)} celdas con veto duro"
            ]
        aggregated.append(representative)
    return _numeric_sort(aggregated)


def _spatially_balanced_sample(
    rows: Iterable[Mapping[str, Any]],
    *,
    max_rows: int,
    step: float = 0.75,
) -> list[dict[str, Any]]:
    """Bound markers without dropping whole regions or islands.

    Every coarse geographic bucket contributes its highest-priority marker
    before a second marker is taken from any bucket. If even the number of
    buckets exceeds the limit, buckets are sampled evenly west-to-east.
    """
    ordered = _numeric_sort(rows)
    if max_rows <= 0:
        return []
    if len(ordered) <= max_rows:
        return ordered
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in ordered:
        lat, lon = _number(row.get("lat")), _number(row.get("lon"))
        if lat is None or lon is None:
            continue
        buckets.setdefault((round(lon / step), round(lat / step)), []).append(row)
    keys = sorted(buckets)
    if len(keys) > max_rows:
        if max_rows == 1:
            keys = [keys[len(keys) // 2]]
        else:
            keys = [keys[round(index * (len(keys) - 1) / (max_rows - 1))] for index in range(max_rows)]
    selected: list[dict[str, Any]] = []
    depth = 0
    while len(selected) < max_rows:
        added = False
        for key in keys:
            if depth < len(buckets[key]):
                selected.append(buckets[key][depth])
                added = True
                if len(selected) == max_rows:
                    break
        if not added:
            break
        depth += 1
    return selected


def _add_optional_layers(
    map_object: folium.Map,
    layers_dir: Path | None,
    selected_layers: Iterable[str] = (),
) -> dict[str, bool]:
    if not layers_dir or not layers_dir.exists():
        return {}
    candidates = {
        "Nitratos": ("nitrate_zones.geojson", "nitrates.geojson", "nitrate.geojson"),
        "Gasoductos": ("gas_pipelines.geojson", "gas.geojson"),
        "Carreteras": ("roads.geojson", "high_capacity_roads.geojson"),
        "Líneas eléctricas": ("electrical_lines.geojson", "electric_lines.geojson"),
        "Subestaciones": ("substations.geojson",),
        "Plantas de biometano": ("operating_plants.geojson", "biomethane_plants.geojson", "plants.geojson"),
        "Natura 2000": ("natura2000_sites.geojson",),
        "Suelo construido (proxy WorldCover)": ("built_up_proxy.geojson",),
        "Materia prima alta (proxy macro)": ("feedstock_proxy.geojson",),
    }
    colors = {
        "Nitratos": "#ff5964",
        "Gasoductos": "#b69cff",
        "Carreteras": "#e6b85c",
        "Líneas eléctricas": "#4dd6e7",
        "Subestaciones": "#20b8d0",
        "Plantas de biometano": "#42d392",
        "Natura 2000": "#72df72",
        "Suelo construido (proxy WorldCover)": "#ff5ca8",
        "Materia prima alta (proxy macro)": "#ff9f43",
    }
    polygon_styles = {
        "Natura 2000": {"weight": 0.8, "fillOpacity": 0.04},
        "Suelo construido (proxy WorldCover)": {"weight": 0.45, "fillOpacity": 0.22},
        "Materia prima alta (proxy macro)": {"weight": 0.45, "fillOpacity": 0.16},
    }
    selected = set(selected_layers)
    available: dict[str, bool] = {}
    for label, names in candidates.items():
        path = next((layers_dir / name for name in names if (layers_dir / name).exists()), None)
        available[label] = path is not None
        if path is None or label not in selected:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            point_marker = None
            if label in {"Subestaciones", "Plantas de biometano"}:
                point_marker = folium.CircleMarker(
                    radius=4 if label == "Subestaciones" else 6,
                    color=colors[label],
                    fill=True,
                    fill_color=colors[label],
                    fill_opacity=0.85,
                    weight=1,
                )
            tooltip_fields = {
                "Natura 2000": (["site_name", "site_code", "site_type"], ["Espacio", "Código", "Tipo"]),
                "Suelo construido (proxy WorldCover)": (["cell_id", "built_up_share"], ["Celda", "Fracción construida"]),
                "Materia prima alta (proxy macro)": (["cell_id", "feedstock_score"], ["Celda", "Índice relativo"]),
            }.get(label)
            folium.GeoJson(
                payload,
                name=label,
                marker=point_marker,
                tooltip=(
                    folium.GeoJsonTooltip(fields=tooltip_fields[0], aliases=tooltip_fields[1], localize=True, sticky=False)
                    if tooltip_fields and payload.get("features")
                    else None
                ),
                style_function=lambda _feature, color=colors[label], layer_style=polygon_styles.get(label, {}): {
                    "color": color,
                    "weight": layer_style.get("weight", 2),
                    "fillOpacity": layer_style.get("fillOpacity", 0.16),
                },
            ).add_to(map_object)
        except (OSError, ValueError):
            available[label] = False
    snczi_label = "Inundación SNCZI T100 (oficial)"
    available[snczi_label] = True
    if snczi_label in selected:
        folium.WmsTileLayer(
            url="https://wms.mapama.gob.es/sig/agua/ZI_LaminasQ100",
            layers="NZ.RiskZone",
            styles="Agua_Zi_laminas_q100",
            fmt="image/png",
            transparent=True,
            name=snczi_label,
            overlay=True,
            control=True,
            show=True,
        ).add_to(map_object)
    return available


def build_map(
    cells: Any,
    *,
    national: bool = True,
    max_markers: int = 400,
    layers_dir: str | Path | None = None,
    show_layers: Iterable[str] = (),
) -> tuple[folium.Map, dict[str, Any]]:
    """Build a bounded map and metadata for the Streamlit UI."""
    rows = [row for row in _rows(cells) if _number(row.get("lat")) is not None and _number(row.get("lon")) is not None]
    map_object = folium.Map(
        location=[40.2, -3.7],
        zoom_start=6 if national else 8,
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr="© OpenStreetMap contributors © CARTO",
        name="Oscuro (estándar)",
        overlay=False,
        control=True,
        show=True,
        max_zoom=20,
        subdomains="abcd",
    ).add_to(map_object)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics",
        name="Satélite con relieve",
        overlay=False,
        control=True,
        show=False,
        max_zoom=19,
    ).add_to(map_object)
    folium.TileLayer(
        tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="Map data © OpenStreetMap contributors, SRTM | Map style © OpenTopoMap",
        name="Topográfico con relieve",
        overlay=False,
        control=True,
        show=False,
        max_zoom=17,
        subdomains="abc",
    ).add_to(map_object)
    Fullscreen(position="topright", title="Pantalla completa").add_to(map_object)
    display_rows = (
        _spatially_balanced_sample(_aggregate(rows), max_rows=max_markers)
        if national
        else _numeric_sort(rows)[:max_markers]
    )
    marker_group = folium.FeatureGroup(name="Celdas del screening", show=True).add_to(map_object)
    for row in display_rows:
        lat, lon = float(row["lat"]), float(row["lon"])
        count = int(row.get("aggregate_count", 0) or 0)
        color = status_color(row)
        tooltip = (
            f"{_html(row.get('cell_id', 'sin ID'))} · {_html(row.get('province'))} · "
            f"prioridad {_number(row.get('score_0_100')) or 'no verificado'}"
        )
        if count:
            tooltip += f" · {count} celdas"
        folium.CircleMarker(location=[lat, lon], radius=7 if count else 5, color=color, fill=True, fill_color=color, fill_opacity=0.82, weight=1, tooltip=tooltip, popup=_popup(row, aggregate_count=count or None)).add_to(marker_group)
    available = _add_optional_layers(
        map_object,
        Path(layers_dir) if layers_dir else None,
        show_layers,
    )
    folium.LayerControl(collapsed=True).add_to(map_object)
    bounds = None
    if display_rows:
        bounds = [[min(float(row["lat"]) for row in display_rows), min(float(row["lon"]) for row in display_rows)], [max(float(row["lat"]) for row in display_rows), max(float(row["lon"]) for row in display_rows)]]
        map_object.fit_bounds(bounds, padding=(18, 18))
    return map_object, {
        "rows_available": len(rows),
        "markers_rendered": len(display_rows),
        "aggregated": national,
        "bounds": bounds,
        "layers": available,
        "basemaps": ["Oscuro (estándar)", "Satélite con relieve", "Topográfico con relieve"],
        "default_basemap": "Oscuro (estándar)",
    }


render_map = build_map

__all__ = ["STATUS_COLORS", "build_map", "render_map", "status_color"]
