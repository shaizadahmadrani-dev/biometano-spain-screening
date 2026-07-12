"""Filtros, búsqueda y comparación sin dependencias de Streamlit."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _rows(cells: Any) -> tuple[list[dict[str, Any]], Any]:
    if hasattr(cells, "to_dict") and hasattr(cells, "columns"):
        return [dict(row) for row in cells.to_dict(orient="records")], cells
    return [dict(row) for row in cells], None


def _restore(rows: list[dict[str, Any]], original: Any) -> Any:
    if original is None:
        return rows
    try:
        import pandas as pd
        return pd.DataFrame(rows, columns=list(original.columns))
    except ImportError:
        return rows


def _first(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None and str(row[name]).strip() != "":
            return row[name]
    return default


def _number(value: Any) -> float | None:
    try:
        return None if value is None or str(value).strip() == "" else float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "sí", "si", "veto"}


def _is_v49(row: Mapping[str, Any]) -> bool:
    return "v49" in str(row.get("method_version", "")).casefold()


def _has_hard_veto(row: Mapping[str, Any]) -> bool:
    # v49 stores physical exclusions explicitly. Nitrate evidence is a
    # digestate-management risk and must never be re-inferred as a site veto.
    if _is_v49(row):
        return _truthy(_first(row, "hard_veto", default=False))
    if _truthy(_first(row, "hard_veto", "hard_constraint_flag_v31", default=False)):
        return True
    for key in ("nitrate_vulnerable", "nitrate_vulnerable_zone", "nitrate_zone", "nitrate_intersection", "nitrate_vulnerable_intersection", "nitrates_intersection", "nitrate_veto", "nitrates_hard_veto"):
        if _truthy(row.get(key)):
            return True
    share = _number(row.get("nitrate_intersection_share"))
    if share is not None and share > 0:
        return True
    reasons = " ".join(str(_first(row, key, default="")) for key in ("veto_reasons", "constraint_flags_v31"))
    return "nitr" in reasons.casefold() and "desconoc" not in reasons.casefold() and "unknown" not in reasons.casefold()


def filter_cells(
    cells: Iterable[Mapping[str, Any]] | Any,
    *,
    province: str | None = None,
    ccaa: str | None = None,
    tier: str | None = None,
    status: str | None = None,
    screening_status: str | None = None,
    hard_veto: bool | None = None,
    include_vetoed: bool = True,
    min_score: float | None = None,
    max_score: float | None = None,
    query: str | None = None,
) -> Any:
    """Filter cells using case-insensitive exact facets and broad text search."""
    rows, original = _rows(cells)
    terms = [part.casefold() for part in (query or "").split() if part.strip()]
    wanted_status = screening_status if screening_status is not None else status
    result: list[dict[str, Any]] = []
    for row in rows:
        if province and str(_first(row, "province", "province_name_v31", default="")).casefold() != province.casefold():
            continue
        if ccaa and str(_first(row, "ccaa", "province_nuts2_name_v31", "NUTS2024_2_name", default="")).casefold() != ccaa.casefold():
            continue
        if tier and str(_first(row, "tier", "robust_tier_v48", "original_tier", "original_v31_tier", "defensible_tier_v31", default="")).casefold() != tier.casefold():
            continue
        row_status = str(_first(row, "screening_status", "status", default="")).casefold()
        if wanted_status and row_status != wanted_status.casefold():
            continue
        veto = _has_hard_veto(row)
        if not include_vetoed and veto:
            continue
        if hard_veto is not None and veto != hard_veto:
            continue
        score_field = "score_0_100" if "score_0_100" in row else "official_score" if "official_score" in row else "defensible_score_v31"
        score = _number(row.get(score_field))
        if score_field == "defensible_score_v31" and score is not None and 0 <= score <= 1:
            score *= 100
        if min_score is not None and (score is None or score < min_score):
            continue
        if max_score is not None and (score is None or score > max_score):
            continue
        if terms:
            haystack = " ".join(str(value) for value in row.values()).casefold()
            if not all(term in haystack for term in terms):
                continue
        result.append(row)
    return _restore(result, original)


def search_cells(cells: Iterable[Mapping[str, Any]] | Any, query: str) -> Any:
    return filter_cells(cells, query=query)


def comparison_table(cells: Iterable[Mapping[str, Any]] | Any, cell_ids: Iterable[str] | None = None, *, limit: int = 5) -> Any:
    """Build a compact comparison table, capped at five cells by contract."""
    rows, original = _rows(cells)
    if cell_ids is not None:
        wanted = {str(item) for item in cell_ids}
        rows = [row for row in rows if str(_first(row, "cell_id", "cell_id_v22", "cell_1km_id_v22")) in wanted]
    rows = rows[: max(0, min(5, limit))]
    columns = (
        "cell_id", "province", "ccaa", "score_0_100", "official_score",
        "tier", "screening_status", "screening_evidence_completeness",
        "prefeasibility_status", "prefeasibility_evidence_completeness", "digestate_risk",
        "hard_veto", "veto_reasons", "review_reasons", "missing_checks",
        "missing_critical_gates", "data_completeness",
    )
    compact = []
    for row in rows:
        compact.append({
            key: _first(row, key, {
                "cell_id": "cell_id_v22", "province": "province_name_v31", "ccaa": "province_nuts2_name_v31",
                "score_0_100": "defensible_score_v31", "official_score": "defensible_score_v31",
                "tier": "defensible_tier_v31", "hard_veto": "hard_constraint_flag_v31",
                "veto_reasons": "constraint_flags_v31",
            }.get(key, key), default=None)
            for key in columns
        })
        score_field = "score_0_100" if "score_0_100" in row else "official_score" if "official_score" in row else "defensible_score_v31"
        score = _number(row.get(score_field))
        if score_field == "defensible_score_v31" and score is not None and 0 <= score <= 1:
            score *= 100
        compact[-1]["score_0_100"] = score
        compact[-1]["official_score"] = score
        compact[-1]["tier"] = _first(
            row,
            "tier",
            "robust_tier_v48",
            "original_tier",
            "original_v31_tier",
            "defensible_tier_v31",
            default=None,
        )
        compact[-1]["hard_veto"] = _has_hard_veto(row)
    if original is not None:
        try:
            import pandas as pd
            return pd.DataFrame(compact, columns=list(columns))
        except ImportError:
            pass
    return compact


filter_candidates = filter_cells
apply_filters = filter_cells
build_comparison_table = comparison_table
compare_cells = comparison_table
build_comparison = comparison_table


__all__ = ["filter_cells", "filter_candidates", "apply_filters", "search_cells", "comparison_table", "build_comparison_table", "compare_cells", "build_comparison"]
