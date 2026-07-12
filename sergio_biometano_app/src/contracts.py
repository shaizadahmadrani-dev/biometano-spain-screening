"""Stable data contracts for the Sergio national screening app.

The module intentionally has no pandas/geospatial dependency.  It is imported by
the UI and by focused tests in environments where the preparation dependencies
are not installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


METHOD_VERSION = "sergio-national-v48"
METHOD_VERSION_V49 = "sergio-national-v49-evidence"
UNKNOWN = "no verificado"

# The compact export keeps these fields first; additional source fields may be
# retained after them for diagnostics without changing the app-facing contract.
IDENTITY_COLUMNS = ("cell_id", "lon", "lat", "province", "ccaa")
RESULT_COLUMNS = (
    "score_0_100",
    "original_tier",
    "original_v31_tier",
    "robust_tier_v48",
    "screening_status",
)
RESTRICTION_COLUMNS = ("hard_veto", "veto_reasons", "review_reasons")
EVIDENCE_COLUMNS = (
    "nitrate_intersection_share",
    "nitrate_zone_name",
    "electric_substation_distance_proxy_km",
    "gas_pipeline_distance_km_proxy",
    "hydrology_status",
    "hydrology_coverage",
    "copdem_slope_median_deg_v47",
    "snczi_q100_intersects_v47",
    "snczi_q100_area_share_bbox_proxy_v47",
    "model_rank_confidence_v48",
    "key_drivers",
)
QUALITY_COLUMNS = ("data_completeness", "missing_checks", "method_version", "data_date")

V49_DECISION_COLUMNS = (
    "grid_level",
    "national_universe",
    "screening_priority_score_v49",
    "screening_status",
    "digestate_risk",
    "screening_evidence_completeness",
    "prefeasibility_status",
    "prefeasibility_evidence_completeness",
    "missing_critical_gates",
    "failed_critical_gates",
    "target_statement",
)

REQUIRED_COMPACT_COLUMNS = IDENTITY_COLUMNS + RESULT_COLUMNS + RESTRICTION_COLUMNS + EVIDENCE_COLUMNS + QUALITY_COLUMNS


@dataclass(frozen=True)
class SourcePaths:
    """Discovered input sources.

    A missing optional source is represented by ``None`` and is surfaced as
    ``no verificado`` by preparation; it is never silently treated as clear.
    """

    project_root: Path
    v48_csv: Optional[Path] = None
    v31_csv: Optional[Path] = None
    v22_geoparquet: Optional[Path] = None
    nitrate_geojson: Optional[Path] = None
    natura2000_geojson: Optional[Path] = None
    electric_substations: Optional[Path] = None
    electric_lines: Optional[Path] = None
    electric_substations_member: Optional[str] = None
    electric_lines_member: Optional[str] = None
    operating_plants: Optional[Path] = None
    gas_pipelines: Tuple[Path, ...] = ()


@dataclass(frozen=True)
class NitrateAssessment:
    """Cell-level nitrate evidence and the resulting hard-veto decision."""

    intersects: Optional[bool]
    share: Optional[float]
    zone_name: Optional[str]
    hard_veto: bool
    veto_reasons: Tuple[str, ...] = ()
    missing_checks: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PreparationResult:
    """Paths and metrics written by :func:`prepare_dataset`."""

    cells_csv: Path
    cells_parquet: Optional[Path]
    manifest_json: Path
    map_layers_dir: Path
    metrics: dict
