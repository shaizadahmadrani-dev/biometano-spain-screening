"""Aplicación Streamlit para explorar el sistema de evidencia v49 de biometano."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from sergio_biometano_app.src.explanations import summarize_cell
    from sergio_biometano_app.src.exports import csv_bytes, pdf_bytes
    from sergio_biometano_app.src.filters import comparison_table, filter_cells
    from sergio_biometano_app.src.map_view import build_map
    from sergio_biometano_app.src.point_reports import point_report_pdf_bytes, safe_point_report_filename
    from sergio_biometano_app.src.scenarios import SCENARIO_WEIGHTS, score_scenario
except ModuleNotFoundError:
    # The handoff ZIP can be extracted under any folder name.
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from src.explanations import summarize_cell
    from src.exports import csv_bytes, pdf_bytes
    from src.filters import comparison_table, filter_cells
    from src.map_view import build_map
    from src.point_reports import point_report_pdf_bytes, safe_point_report_filename
    from src.scenarios import SCENARIO_WEIGHTS, score_scenario

DATA_DIR = APP_DIR / "data"
NATIONAL_PARQUET_PATH = DATA_DIR / "sergio_cells_v49_national_5km.parquet"
REFINED_PARQUET_PATH = DATA_DIR / "sergio_cells_v49_refined_1km.parquet"
MANIFEST_PATH = DATA_DIR / "provenance_manifest_v49.json"
LAYERS_DIR = DATA_DIR / "map_layers"
MODEL_AUDIT_PATH = APP_DIR / "AUDITORIA_CRITICA_MODELO.md"
STATUS_ORDER = (
    "prioridad alta de investigación",
    "prioridad media de investigación",
    "prioridad baja de investigación",
    "descartado por filtro físico",
)
STATUS_LABELS = {
    "prioridad alta de investigación": "Prioridad alta",
    "prioridad media de investigación": "Prioridad media",
    "prioridad baja de investigación": "Prioridad baja",
    "descartado por filtro físico": "Exclusión física",
}
TIER_LABELS = {
    "A_prioritaria": "A · prioridad alta para revisión",
    "B_viable_revisar": "B · priorizada para revisión",
    "C_degradar_revisar": "C · revisión reforzada",
    "D_descartar_preliminar": "D · descarte preliminar",
    "A_prioritaria_condicionada": "A · prioridad robusta condicionada",
    "B_prioritaria_revisar": "B · prioridad para revisión",
    "C_revision_reforzada": "C · revisión reforzada",
}
SCENARIO_LABELS = {
    "feedstock": "Materia prima",
    "organic_waste": "Residuos orgánicos",
    "gas_access": "Acceso a gas",
    "road_access": "Acceso viario",
    "land_environment": "Suelo y entorno",
}


def _list_value(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return [str(item) for item in decoded if str(item).strip()]
    return [item.strip() for item in str(value).replace(";", "|").split("|") if item.strip()]


@st.cache_data(show_spinner="Cargando snapshot Parquet…")
def load_snapshot(path: str, mtime_ns: int) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if frame.empty:
        raise ValueError("El snapshot Parquet está vacío.")
    for column in ("score_0_100", "lon", "lat", "data_completeness"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("hard_veto", "nitrate_intersects"):
        if column in frame:
            frame[column] = frame[column].map(lambda value: str(value).lower() in {"true", "1", "yes", "sí", "si"} if not isinstance(value, bool) else value)
    return frame


@st.cache_data(show_spinner=False)
def load_manifest(path: str, mtime_ns: int) -> dict[str, Any]:
    if not Path(path).exists():
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _format_score(value: Any) -> str:
    return "no verificado" if pd.isna(value) else f"{float(value):.0f}/100"


def _format_percentage(value: Any) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "no verificado"


def _display_tier(value: Any) -> str:
    raw = str(value or "no verificado")
    return TIER_LABELS.get(raw, raw.replace("_", " "))


def _nearest(frame: pd.DataFrame, lat: float, lon: float) -> pd.Series | None:
    valid = frame.dropna(subset=["lat", "lon"]).copy()
    if valid.empty:
        return None
    distances = (valid["lat"] - lat).pow(2) + ((valid["lon"] - lon) * math.cos(math.radians(lat))).pow(2)
    return valid.loc[distances.idxmin()]


def _parse_coordinates(value: str) -> tuple[float, float] | None:
    parts = [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    if len(parts) != 2:
        return None
    try:
        first, second = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if -90 <= first <= 90 and -180 <= second <= 180:
        return first, second
    if -180 <= first <= 180 and -90 <= second <= 90:
        return second, first
    return None


def _cell_record(row: pd.Series) -> dict[str, Any]:
    result = row.to_dict()
    if "tier" not in result and "original_tier" in result:
        result["tier"] = result["original_tier"]
    for key in (
        "veto_reasons", "review_reasons", "missing_checks", "key_drivers",
        "missing_critical_gates", "failed_critical_gates",
    ):
        result[key] = _list_value(result.get(key))
    return result


def _available_layer_labels() -> list[str]:
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
    available = [label for label, names in candidates.items() if any((LAYERS_DIR / name).exists() for name in names)]
    available.append("Inundación SNCZI T100 (oficial)")
    return available


def _show_status_card(label: str, count: int, status: str) -> None:
    color = {
        "prioridad alta de investigación": "#31c58d",
        "prioridad media de investigación": "#4db6ff",
        "prioridad baja de investigación": "#f0b44d",
        "descartado por filtro físico": "#ff6b6b",
        "no verificado": "#d7a84a",
    }.get(status, "#7f93a0")
    st.markdown(f"<div class='status-card' style='border-top-color:{color}'><div>{label}</div><strong>{count:,}</strong><small>{status}</small></div>", unsafe_allow_html=True)


def _status_callout(summary: dict[str, Any]) -> tuple[str, str]:
    status = str(summary.get("screening_status", "no verificado")).strip().lower()
    if summary.get("hard_veto"):
        return "error", "EXCLUSIÓN FÍSICA · Esta celda queda fuera del screening por una restricción física explícita."
    if "descart" in status:
        return "error", "DESCARTE PRELIMINAR · No supera las reglas conservadoras del screening."
    if status == "prioridad alta de investigación":
        return "success", "PRIORIDAD ALTA · Conviene adquirir evidencia aquí primero; NO equivale a prefactible ni viable."
    if status == "prioridad media de investigación":
        return "info", "PRIORIDAD MEDIA · Hay señales útiles, pero faltan datos o existen condicionantes por resolver."
    if status == "prioridad baja de investigación":
        return "warning", "PRIORIDAD BAJA · Con los proxies actuales, otras zonas merecen investigarse antes."
    if status == "prioritario condicionado":
        return "info", "PRIORIDAD CONDICIONADA · Destaca en el ranking, pero necesita verificaciones externas."
    if status == "candidato de screening":
        return "success", "Candidato de screening; no equivale a viabilidad ni autorización."
    if "revis" in status or summary.get("review_reasons") or summary.get("missing_checks"):
        return "warning", "Requiere revisión. Lo desconocido no equivale a cumplimiento."
    return "warning", "Estado no verificado; no debe interpretarse como cumplimiento."


def _render_detail(row: pd.Series, manifest: dict[str, Any]) -> None:
    cell = _cell_record(row)
    summary = summarize_cell(cell)
    st.subheader("Detalle de la celda seleccionada")
    st.markdown(f"### {summary['cell_id']} · {summary['province']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prioridad relativa v49", _format_score(summary["score_0_100"]))
    c2.metric("Estado de investigación", str(summary["screening_status"]))
    c3.metric("Evidencia de screening", _format_percentage(summary["screening_evidence_completeness"]))
    c4.metric("Prefactibilidad", str(summary["prefeasibility_status"]))
    callout_kind, callout_text = _status_callout(summary)
    getattr(st, callout_kind)(callout_text)
    st.info(summary["official_statement"])
    left, right = st.columns(2)
    with left:
        st.markdown("**Fortalezas observadas**")
        for item in summary["strengths"]:
            st.write(f"• {item}")
        st.markdown("**Penalizaciones o debilidades**")
        for item in summary["weaknesses"]:
            st.write(f"• {item}")
    with right:
        st.markdown("**Vetos**")
        st.write("• " + "\n• ".join(summary["vetoes"]) if summary["vetoes"] else "Ninguno registrado")
        st.markdown("**Advertencias del screening**")
        st.write("• " + "\n• ".join(summary["review_reasons"]) if summary["review_reasons"] else "Ninguna registrada")
        st.markdown("**Gestión del digestato**")
        st.write(f"• Riesgo asociado a nitratos: {summary['digestate_risk']}")
        st.markdown("**Controles pendientes**")
        st.write("• " + "\n• ".join(summary["missing"]) if summary["missing"] else "No hay controles pendientes registrados")
        st.markdown("**Gates críticos de prefactibilidad pendientes**")
        st.write("• " + "\n• ".join(summary["missing_critical_gates"]) if summary["missing_critical_gates"] else "Ninguno pendiente")
        if summary["failed_critical_gates"]:
            st.markdown("**Gates críticos no superados**")
            st.write("• " + "\n• ".join(summary["failed_critical_gates"]))
        st.markdown("**Validaciones externas obligatorias**")
        st.write("• " + "\n• ".join(summary["mandatory_external_checks"]))
        st.markdown("**Drivers**")
        st.write("• " + "\n• ".join(summary["strengths"][:4]))
        st.markdown("**Terreno, inundación e incertidumbre**")
        slope = cell.get("copdem_slope_median_deg_v47")
        flood_share = cell.get("snczi_q100_area_share_bbox_proxy_v47")
        st.write(f"• Pendiente mediana Copernicus: {float(slope):.1f}°" if slope is not None and not pd.isna(slope) else "• Pendiente: no verificada")
        st.write(f"• SNCZI Q100 (proxy de área): {float(flood_share):.1%}" if flood_share is not None and not pd.isna(flood_share) else "• SNCZI Q100: no verificado")
        st.write(f"• Acuerdo de ranking entre modelos: {cell.get('model_rank_confidence_v48', 'no verificado')}")
        st.write(f"• Evidencia de prefactibilidad completada: {_format_percentage(summary['prefeasibility_evidence_completeness'])}")
    with st.expander("Provenance y datos del snapshot"):
        st.json({"método": manifest.get("method_version", cell.get("method_version", "no verificado")), "fecha": manifest.get("as_of", cell.get("data_date", "no verificado")), "fuentes": manifest.get("source_vintages", {}), "alcance": manifest.get("scope", "no verificado"), "objetivo": manifest.get("target", "prioridad de investigación")})


def _render_scenario(row: pd.Series) -> None:
    st.subheader("Simulador de escenario")
    st.caption("ESCENARIO separado de la prioridad v49. Sirve para explorar pesos; no rellena gates críticos, no reentrena el modelo ni autoriza una planta.")
    columns = st.columns(5)
    weights: dict[str, float] = {}
    for column, (dimension, weight) in zip(columns, SCENARIO_WEIGHTS.items()):
        weights[dimension] = column.slider(
            SCENARIO_LABELS.get(dimension, dimension.replace("_", " ").title()),
            0,
            100,
            int(weight * 100),
            5,
            key=f"scenario_{dimension}",
        ) / 100
    if sum(weights.values()) <= 0:
        st.error("El escenario necesita al menos un peso mayor que cero.")
        return
    result = score_scenario(_cell_record(row), weights=weights)
    c1, c2, c3 = st.columns(3)
    c1.metric("Prioridad oficial v49", _format_score(result["official_score"]))
    c2.metric("Score del escenario", f"{result['scenario_score_0_100']:.1f}/100")
    c3.metric("Estado del escenario", result["status"])
    st.warning(result["label"] + " " + result["caveat"])
    if result["missing_dimensions"]:
        st.caption("Dimensiones sin dato: " + ", ".join(result["missing_dimensions"]) + ".")


def main() -> None:
    st.set_page_config(page_title="Explorador nacional de biometano", page_icon="🌿", layout="wide", initial_sidebar_state="auto")
    st.markdown("""<style>
    :root{--ink:#e7f0eb;--muted:#aabbb3;--paper:#0b1117;--surface:#111a22;--surface2:#16232c;--line:#273a43;--green:#31c58d;--amber:#f0b44d;--red:#ff6b6b}
    .stApp{background:radial-gradient(circle at 15% 0%,#13251f 0,#0b1117 34rem);color:var(--ink)}
    [data-testid="stSidebar"]{background:#0d171d;border-right:1px solid var(--line)}
    [data-testid="stSidebar"] label,[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,[data-testid="stSidebar"] .stCaption p,[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:#dce9e2!important}
    [data-testid="stSidebar"] [data-baseweb="select"] > div,[data-testid="stSidebar"] [data-baseweb="input"] > div{background:#111a22!important;border-color:#3d5661!important;color:#e7f0eb!important}
    [data-testid="stSidebar"] [data-baseweb="select"] span,[data-testid="stSidebar"] [data-baseweb="select"] svg,[data-testid="stSidebar"] input{color:#e7f0eb!important;fill:#e7f0eb!important;-webkit-text-fill-color:#e7f0eb!important}
    [data-testid="stSidebar"] [data-baseweb="select"] div{color:#e7f0eb!important}
    [data-testid="stSidebar"] input::placeholder{color:#91a59b!important;-webkit-text-fill-color:#91a59b!important;opacity:1}
    [data-baseweb="popover"] [role="listbox"]{background:#111a22!important;border:1px solid #3d5661!important}
    [data-baseweb="popover"] [role="option"],[data-baseweb="popover"] [role="option"] span{color:#e7f0eb!important;background:#111a22!important}
    [data-baseweb="popover"] [role="option"]:hover{background:#1c303a!important}
    [data-testid="stDeployButton"],[data-testid="stToolbar"],#MainMenu,footer{display:none!important}
    .block-container{padding-top:1.1rem;padding-bottom:2.5rem;max-width:1500px}
    .hero{background:linear-gradient(125deg,#12362b 0%,#10232a 60%,#111a22 100%);color:white;border:1px solid #285344;border-radius:18px;padding:1.25rem 1.45rem;margin-bottom:1rem;box-shadow:0 16px 42px rgba(0,0,0,.28)}
    .hero h1{color:white!important;margin:0;font-size:2.1rem;line-height:1.1}.hero p{margin:.45rem 0 0;color:#cce3d8}.hero .tag{display:inline-block;margin-top:.7rem;margin-right:.4rem;padding:.25rem .55rem;border:1px solid #4f8e76;border-radius:999px;color:#eaf5ef;background:rgba(49,197,141,.08);font-size:.78rem}
    .status-card{background:linear-gradient(160deg,var(--surface2),var(--surface));border:1px solid var(--line);border-top:5px solid #7f93a0;border-radius:12px;padding:.78rem .85rem;margin:.2rem 0;min-height:118px;box-shadow:0 8px 22px rgba(0,0,0,.20)}
    .status-card strong{display:block;font-size:1.65rem;color:var(--ink)}.status-card small{color:var(--muted)}
    .mobile-note{color:var(--muted);font-size:.9rem}.map-legend{display:flex;gap:.9rem;flex-wrap:wrap;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:.5rem .7rem;margin:.35rem 0 .65rem}.legend-item{font-size:.82rem;color:#c5d4cd}.legend-dot{display:inline-block;width:.7rem;height:.7rem;border-radius:50%;margin-right:.3rem}
    .quality-banner{background:linear-gradient(90deg,#17242b,#142119);border:1px solid #355343;border-left:5px solid var(--amber);border-radius:12px;padding:.8rem 1rem;margin:.5rem 0 1rem;color:#dce9e2}.quality-banner strong{color:#ffd27b}
    [data-testid="stMetric"],[data-testid="stExpander"],div[data-testid="stDataFrame"]{background:rgba(17,26,34,.58);border-color:var(--line)}
    a{color:#62d8a7!important}
    h1,h2,h3{color:var(--ink)!important}
    @media(max-width:700px){.block-container{padding:.65rem}.hero{padding:1rem;border-radius:14px}.hero h1{font-size:1.55rem}.status-card{padding:.55rem;min-height:auto}.stMetric{padding:.2rem}.map-legend{gap:.45rem}}
    </style>""", unsafe_allow_html=True)
    manifest = load_manifest(
        str(MANIFEST_PATH),
        MANIFEST_PATH.stat().st_mtime_ns if MANIFEST_PATH.exists() else 0,
    )
    with st.sidebar:
        st.header("Escala de análisis")
        scale = st.radio(
            "Selecciona el nivel territorial",
            ("Cobertura nacional · 5 km", "Refinamiento priorizado · 1 km"),
            help="5 km permite comparar toda España. 1 km solo refina el universo que v48 había priorizado.",
        )
    parquet_path = NATIONAL_PARQUET_PATH if scale.startswith("Cobertura") else REFINED_PARQUET_PATH
    if not parquet_path.exists():
        st.error(f"No se encuentra el snapshot v49 requerido: {parquet_path.name}.")
        st.stop()
    try:
        cells = load_snapshot(str(parquet_path), parquet_path.stat().st_mtime_ns)
    except Exception as exc:
        st.error(f"No se pudo leer el snapshot Parquet: {exc}")
        st.stop()
    grid_level = str(cells.get("grid_level", pd.Series(["no verificado"])).iloc[0])
    national_scope = bool(cells.get("national_universe", pd.Series([False])).iloc[0])
    st.markdown(
        f"""<section class="hero"><h1>Explorador nacional de biometano</h1>
        <p>Prioriza dónde adquirir evidencia de prefactibilidad, sin confundir ranking con viabilidad.</p>
        <span class="tag">{len(cells):,} celdas · {grid_level}</span><span class="tag">Mapa interactivo</span><span class="tag">Evidencia y gates visibles</span></section>""",
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.header("Buscar y filtrar")
        st.caption("Ajusta el mapa sin modificar la prioridad oficial v49.")
        query = st.text_input("Celda, provincia o texto", placeholder="Ej.: Cádiz o CR...")
        coordinates = st.text_input("Coordenadas", placeholder="lat, lon")
        provinces = sorted(str(value) for value in cells["province"].dropna().unique()) if "province" in cells else []
        ccaas = sorted(str(value) for value in cells["ccaa"].dropna().unique()) if "ccaa" in cells else []
        tier_source = "robust_tier_v48" if "robust_tier_v48" in cells else "original_tier"
        tiers = sorted(str(value) for value in cells.get(tier_source, pd.Series(dtype=str)).dropna().unique())
        statuses = [value for value in STATUS_ORDER if value in set(cells.get("screening_status", pd.Series(dtype=str)).astype(str))]
        province = st.selectbox("Provincia", ["Todas"] + provinces)
        ccaa = st.selectbox("Comunidad autónoma", ["Todas"] + ccaas)
        tier = st.selectbox(
            "Nivel heredado del ranking v48",
            ["Todos"] + tiers,
            format_func=lambda value: value if value == "Todos" else _display_tier(value),
        )
        status = st.selectbox("Estado", ["Todos"] + statuses)
        min_score, max_score = st.slider("Rango de prioridad relativa (0–100)", 0, 100, (0, 100))
        veto_filter = st.selectbox("Veto duro", ["Todos", "Solo con veto", "Sin veto"])
        available_layers = _available_layer_labels()
        map_layers = st.multiselect(
            "Capas disponibles",
            available_layers,
            default=[],
            placeholder="Selecciona capas",
        )
        if not available_layers:
            st.caption("No hay capas opcionales exportadas en este snapshot.")
        else:
            st.caption(
                "Natura 2000 muestra límites simplificados. Suelo construido usa WorldCover 2021 y no equivale a suelo urbanístico. "
                "Materia prima es un índice relativo macro y no suministro contratado."
            )
    filtered = filter_cells(cells, province=None if province == "Todas" else province, ccaa=None if ccaa == "Todas" else ccaa, tier=None if tier == "Todos" else tier, screening_status=None if status == "Todos" else status, min_score=min_score, max_score=max_score, hard_veto=True if veto_filter == "Solo con veto" else False if veto_filter == "Sin veto" else None, query=query or None)
    filtered = filtered if isinstance(filtered, pd.DataFrame) else pd.DataFrame(filtered)
    coordinate_target = _parse_coordinates(coordinates) if coordinates else None
    if coordinate_target:
        nearest = _nearest(cells, *coordinate_target)
        if nearest is not None:
            filtered = pd.DataFrame([nearest])
            st.sidebar.success(f"Celda más cercana: {nearest.get('cell_id', 'sin ID')}")
    st.markdown("<div class='mobile-note'>Consejo: en móvil, abre el panel lateral para filtros y toca un marcador para ver su ficha.</div>", unsafe_allow_html=True)
    st.subheader("Resumen del ámbito seleccionado")
    if national_scope:
        st.warning("Alcance: cobertura territorial nacional de 21.519 celdas de 5 km. Sirve para comparar España, pero NO representa parcelas ni acredita restricciones físicas, permisos o capacidad de red.")
    else:
        st.warning("Alcance: refinamiento de 30.450 celdas de 1 km dentro del universo previamente priorizado. NO es una malla exhaustiva de España ni una selección de parcelas viables.")
    evidence_mean = pd.to_numeric(cells.get("screening_evidence_completeness", pd.Series(dtype=float)), errors="coerce").mean()
    physical_count = int(cells.get("hard_veto", pd.Series(False, index=cells.index)).fillna(False).astype(bool).sum())
    nitrate_count = int(cells.get("digestate_risk", pd.Series("", index=cells.index)).astype(str).eq("alto").sum())
    prefeasible_count = int(cells.get("prefeasibility_status", pd.Series("", index=cells.index)).astype(str).eq("prefactible").sum())
    st.markdown(
        f"""<div class="quality-banner"><strong>Lectura correcta: prioridad para investigar, no probabilidad de éxito.</strong><br>
        Evidencia de screening disponible: <strong>{_format_percentage(evidence_mean)}</strong>. Exclusiones físicas explícitas: <strong>{physical_count:,}</strong>. Riesgo alto de gestión del digestato: <strong>{nitrate_count:,}</strong>.<br>
        <strong>Control anti-autoengaño:</strong> celdas declaradas prefactibles sin dossier completo: <strong>{prefeasible_count:,}</strong>. Proximidad a redes o carreteras NO demuestra capacidad, permiso ni coste asumible.</div>""",
        unsafe_allow_html=True,
    )
    cards = st.columns(4)
    for column, status_value in zip(cards, STATUS_ORDER):
        count = int((cells.get("screening_status", pd.Series(dtype=str)).astype(str) == status_value).sum())
        with column:
            _show_status_card(STATUS_LABELS[status_value], count, status_value)
    if "snczi_q100_intersects_v47" in cells:
        flood_intersections = int(cells["snczi_q100_intersects_v47"].fillna(False).astype(bool).sum())
        st.info(
            f"SNCZI Q100 publicada intersecta {flood_intersections:,} celdas refinadas. "
            "No detectar intersección NO demuestra ausencia de riesgo: la cartografía publicada no es exhaustiva."
        )
    else:
        st.info("La cobertura nacional de 5 km todavía no acredita inundabilidad parcelaria; debe comprobarse al refinar cada zona.")
    st.caption(f"Mostrando {len(filtered):,} de {len(cells):,} celdas tras filtros. Snapshot: {manifest.get('as_of', 'no verificado')} · método: {manifest.get('method_version', 'no verificado')}.")
    is_national = province == "Todas" and ccaa == "Todas"
    map_object, map_meta = build_map(filtered, national=is_national, max_markers=250 if is_national else 700, layers_dir=LAYERS_DIR, show_layers=map_layers)
    st.subheader("Mapa de screening")
    st.caption(
        "Fondo estándar: oscuro. Abre el icono de capas del mapa para cambiar a Satélite con relieve o Topográfico con relieve."
    )
    st.markdown(
        """<div class="map-legend">
        <span class="legend-item"><span class="legend-dot" style="background:#31c58d"></span>Prioridad alta de investigación</span>
        <span class="legend-item"><span class="legend-dot" style="background:#4db6ff"></span>Prioridad media</span>
        <span class="legend-item"><span class="legend-dot" style="background:#f0b44d"></span>Prioridad baja</span>
        <span class="legend-item"><span class="legend-dot" style="background:#ff6b6b"></span>Exclusión física</span>
        <span class="legend-item">⚠ El color no expresa viabilidad ni permiso</span></div>""",
        unsafe_allow_html=True,
    )
    map_caption = (
        f"Vista nacional agregada: {map_meta['markers_rendered']:,} agrupaciones; "
        "al tocar una se abre su celda representativa de mayor prioridad."
        if is_national
        else f"Vista filtrada: {map_meta['markers_rendered']:,} celdas individuales (límite 700)."
    )
    st.caption(
        map_caption
        + " Verde/azul/ámbar ordenan la adquisición de evidencia. Rojo identifica una exclusión física explícita. "
        + "Las zonas de nitratos se muestran como riesgo de digestato, no como veto universal."
    )
    top_preview = filtered[~filtered.get("hard_veto", pd.Series(False, index=filtered.index)).fillna(False).astype(bool)]
    top_preview = top_preview.sort_values("score_0_100", ascending=False, na_position="last").head(10)
    with st.expander("Ver las 10 celdas sin exclusión física con mayor prioridad dentro de los filtros"):
        preview_columns = [column for column in ("cell_id", "province", "ccaa", "score_0_100", "screening_status", "digestate_risk", "prefeasibility_status") if column in top_preview]
        preview = top_preview[preview_columns].copy()
        st.dataframe(preview, use_container_width=True, hide_index=True)
    map_result = st_folium(map_object, height=560, use_container_width=True, returned_objects=["last_object_clicked"])
    selected_id = None
    clicked = (map_result or {}).get("last_object_clicked") or {}
    if clicked.get("lat") is not None and clicked.get("lng") is not None:
        clicked_row = _nearest(filtered, float(clicked["lat"]), float(clicked["lng"]))
        if clicked_row is not None:
            selected_id = str(clicked_row.get("cell_id"))
    if selected_id is None and not filtered.empty:
        default_pool = filtered
        if "hard_veto" in filtered:
            non_veto = filtered[~filtered["hard_veto"].fillna(False).astype(bool)]
            if not non_veto.empty:
                default_pool = non_veto
        if "score_0_100" in default_pool:
            default_pool = default_pool.sort_values("score_0_100", ascending=False, na_position="last")
        selected_id = str(default_pool.iloc[0].get("cell_id"))
    selected = None
    if selected_id is not None and "cell_id" in cells:
        matching = cells[cells["cell_id"].astype(str) == selected_id]
        if not matching.empty:
            selected = matching.iloc[0]
    if selected is None:
        st.info("Selecciona una celda con los filtros o tocando un marcador.")
        return
    _render_detail(selected, manifest)
    _render_scenario(selected)
    st.subheader("Comparar hasta cinco celdas")
    compare_pool = filtered.sort_values("score_0_100", ascending=False, na_position="last").head(1000)
    if selected_id not in set(compare_pool["cell_id"].astype(str)):
        compare_pool = pd.concat([pd.DataFrame([selected]), compare_pool], ignore_index=True)
    compare_options = compare_pool["cell_id"].astype(str).drop_duplicates().tolist()
    st.caption(
        f"Selector limitado a {len(compare_options):,} resultados filtrados/priorizados para mantener la app fluida."
    )
    compare_ids = st.multiselect(
        "Celdas",
        options=compare_options,
        default=[selected_id],
        max_selections=5,
    )
    compared = comparison_table(cells, compare_ids, limit=5)
    if isinstance(compared, pd.DataFrame) and "tier" in compared:
        compared["tier"] = compared["tier"].map(_display_tier)
        for column in ("veto_reasons", "review_reasons", "missing_checks", "missing_critical_gates"):
            if column in compared:
                compared[column] = compared[column].map(lambda value: " · ".join(_list_value(value)) or "—")
    st.dataframe(compared, use_container_width=True, hide_index=True)
    st.subheader("Exportaciones")
    export_rows = cells[cells["cell_id"].astype(str).isin(compare_ids or [selected_id])]
    export_records = [_cell_record(row) for _, row in export_rows.iterrows()]
    selected_record = _cell_record(selected)
    snapshot = summarize_cell(selected_record)
    source_lines = [f"{key}: {value}" for key, value in manifest.get("source_vintages", {}).items()]
    caveats = [
        "La prioridad v49 ordena dónde adquirir evidencia; no es probabilidad, viabilidad ni autorización.",
        "La cobertura 5 km es nacional; el refinamiento 1 km solo cubre el universo previamente priorizado.",
        "Las zonas vulnerables a nitratos exigen revisar el plan de digestato; no son un veto universal.",
        "La proximidad a gas o electricidad no demuestra capacidad disponible.",
    ]
    e1, e2, e3 = st.columns(3)
    with e1:
        st.download_button("Descargar CSV", data=csv_bytes(export_records), file_name="sergio_biometano_comparacion.csv", mime="text/csv")
    with e2:
        st.download_button(
            "Ficha breve PDF",
            data=pdf_bytes(snapshot, sources=source_lines, caveats=caveats),
            file_name=f"sergio_{selected_id}.pdf",
            mime="application/pdf",
        )
    with e3:
        st.download_button(
            "Informe detallado PDF",
            data=point_report_pdf_bytes(selected_record, manifest),
            file_name=safe_point_report_filename(selected_id),
            mime="application/pdf",
            help="Informe multipágina del punto seleccionado con indicadores, gates, fuentes y límites.",
        )
    with st.expander("Metodología y fuentes"):
        st.markdown("""**Qué significa:** v49 combina una cobertura nacional de 5 km con un refinamiento de 1 km limitado al universo priorizado. El score es un ranking relativo para decidir dónde investigar primero; no es probabilidad ni declaración de viabilidad.\n\n**Separación de decisiones:** prioridad, calidad de evidencia, prefactibilidad y economía se muestran por separado. Una celda solo puede ser `prefactible` cuando todos los gates críticos estén verificados.\n\n**Regla de nitratos:** la intersección con una zona vulnerable activa riesgo alto de gestión del digestato y revisión del balance de nitrógeno. No es un veto universal de emplazamiento.\n\n**Fuentes y fecha:** consulta el manifest. Las distancias a gas, carretera o electricidad son proxies y deben contrastarse con capacidad, costes y permisos oficiales.""")
        st.json(manifest or {"estado": "manifest no disponible"})
        if manifest.get("source_vintages"):
            st.markdown("**Antigüedad de las fuentes**")
            st.table(
                pd.DataFrame(
                    [
                        {"Capa": key.replace("_", " ").title(), "Referencia": value}
                        for key, value in manifest["source_vintages"].items()
                    ]
                )
            )
    with st.expander("Auditoría crítica del modelo y de los datos"):
        st.warning("DICTAMEN: útil para ordenar revisiones territoriales; insuficiente para aprobar una parcela, una inversión o un permiso.")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Plantas operativas etiquetadas", "24")
        a2.metric("ROC AUC de ranking", "0,804")
        a3.metric("Average Precision", "0,0153")
        a4.metric("Negativos reales", "0")
        st.markdown(
            """- **No existe una probabilidad calibrada de viabilidad.** Solo hay 24 plantas operativas etiquetadas y ninguna muestra fiable de negativos reales.
- La malla 1 km no era nacional: procede de 1.218 padres de 5 km preseleccionados. Por eso v49 incorpora cobertura nacional explícita a 5 km.
- Varias señales de materia prima son proxies macro repetidos entre hijos; no son contratos ni toneladas aseguradas.
- Nitratos pasa de veto automático a riesgo de digestato. Los filtros físicos explícitos se mantienen separados.
- Gas, electricidad, hidrología, Catastro, urbanismo y economía requieren evidencia de proyecto. Distancia no equivale a capacidad.
- La decisión correcta es adquirir evidencia, comparar y descartar progresivamente; no prometer viabilidad."""
        )
        if MODEL_AUDIT_PATH.exists():
            st.download_button(
                "Descargar auditoría completa",
                MODEL_AUDIT_PATH.read_bytes(),
                file_name="AUDITORIA_CRITICA_MODELO.md",
                mime="text/markdown",
            )


if __name__ == "__main__":
    main()
