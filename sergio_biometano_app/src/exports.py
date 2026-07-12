"""Exportaciones deterministas de snapshot para Sergio."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, Mapping):
        return [dict(data)]
    if hasattr(data, "to_dict") and hasattr(data, "columns"):
        return [dict(row) for row in data.to_dict(orient="records")]
    return [dict(row) for row in data]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_text(item) for item in value)
    return str(value)


def _items(value: Iterable[str] | str | None) -> list[str]:
    if value is None:
        return []
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        value = value.tolist()
    return [value] if isinstance(value, str) else list(value)


def csv_bytes(rows: Iterable[Mapping[str, Any]] | Mapping[str, Any] | Any) -> bytes:
    records = _rows(rows)
    fieldnames: list[str] = []
    for row in records:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(str(key))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in records:
        writer.writerow({key: _text(row.get(key)) for key in fieldnames})
    return buffer.getvalue().encode("utf-8-sig")


def export_csv(rows: Iterable[Mapping[str, Any]] | Mapping[str, Any] | Any, destination: str | Path | None = None) -> bytes | Path:
    payload = csv_bytes(rows)
    if destination is None:
        return payload
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _snapshot_lines(snapshot: Mapping[str, Any] | Any) -> list[str]:
    if isinstance(snapshot, Mapping):
        is_v49 = "v49" in str(snapshot.get("method_version", "")).casefold()
        tier_labels = {
            "A_prioritaria": "A · prioridad alta para revisión",
            "B_viable_revisar": "B · priorizada para revisión",
            "C_degradar_revisar": "C · revisión reforzada",
            "D_descartar_preliminar": "D · descarte preliminar",
        }
        score_label = "Prioridad relativa v49" if is_v49 else "Prioridad robusta v48"
        preferred = (
            ("cell_id", "Celda"), ("province", "Provincia"), ("ccaa", "CCAA"),
            ("official_score", score_label), ("tier", "Nivel de prioridad"),
            ("decision_label", "Estado"), ("screening_status", "Screening"),
            ("screening_evidence_completeness", "Evidencia de screening"),
            ("prefeasibility_status", "Prefactibilidad"),
            ("prefeasibility_evidence_completeness", "Evidencia de prefactibilidad"),
            ("digestate_risk", "Riesgo de digestato"),
            ("hard_veto", "Veto duro"), ("review_reasons", "Advertencias del screening"),
            ("missing_checks", "Controles no verificados"),
            ("missing_critical_gates", "Gates críticos pendientes"),
            ("mandatory_external_checks", "Validaciones externas obligatorias"),
            ("method_version", "Versión del método"), ("data_date", "Fecha del snapshot"),
        )
        lines = []
        for key, label in preferred:
            if key not in snapshot:
                continue
            value = snapshot.get(key)
            if key == "tier":
                value = tier_labels.get(str(value), str(value).replace("_", " "))
            lines.append(f"{label}: {_text(value)}")
        return lines[:18]
    return [f"Snapshot: {_text(snapshot)}"]


def pdf_bytes(
    snapshot: Mapping[str, Any] | Any,
    *,
    sources: Iterable[str] = (),
    caveats: Iterable[str] = (),
    title: str = "Explorador nacional de biometano — snapshot",
    generated_at: str | None = None,
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("La exportación PDF requiere reportlab.") from exc

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=1.2 * cm, leftMargin=1.2 * cm,
        topMargin=1.0 * cm, bottomMargin=1.0 * cm,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("SnapshotTitle", parent=styles["Title"], fontSize=15, leading=18, spaceAfter=6)
    body = ParagraphStyle("SnapshotBody", parent=styles["BodyText"], fontSize=8, leading=10, spaceAfter=2)
    small = ParagraphStyle("SnapshotSmall", parent=body, fontSize=7, leading=8)
    story = [Paragraph(xml_escape(title), title_style)]
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    is_v49 = isinstance(snapshot, Mapping) and "v49" in str(snapshot.get("method_version", "")).casefold()
    method_note = (
        "Prioridad v49: orden para adquirir evidencia, no probabilidad, prefactibilidad ni autorización."
        if is_v49 else
        "Prioridad v48: reranking de screening, no probabilidad ni autorización."
    )
    story.append(Paragraph(xml_escape(f"Generado: {stamp} · {method_note}"), small))
    story.append(Spacer(1, 4))
    data = [[Paragraph("Campo", body), Paragraph("Valor", body)]]
    for line in _snapshot_lines(snapshot):
        key, _, value = line.partition(": ")
        data.append([Paragraph(xml_escape(key), body), Paragraph(xml_escape(value or "—"), body)])
    table = Table(data, colWidths=[4.5 * cm, 13.5 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b9c4cf")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f4f7f9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([table, Spacer(1, 5), Paragraph("Fuentes", body)])
    source_lines = _items(sources)[:8] or ["No se han indicado fuentes en este snapshot."]
    story.extend(Paragraph(xml_escape(f"• {_text(source)}"), small) for source in source_lines)
    story.append(Spacer(1, 3))
    story.append(Paragraph("Caveats y límites", body))
    caveat_lines = _items(caveats)[:8] or [
        "La celda es una prioridad de investigación; no equivale a viabilidad, permiso ni capacidad de conexión confirmada."
    ]
    story.extend(Paragraph(xml_escape(f"• {_text(caveat)}"), small) for caveat in caveat_lines)
    doc.build(story)
    return buffer.getvalue()


def export_pdf(
    snapshot: Mapping[str, Any] | Any,
    sources: Iterable[str] = (),
    caveats: Iterable[str] = (),
    destination: str | Path | None = None,
    **kwargs: Any,
) -> bytes | Path:
    payload = pdf_bytes(snapshot, sources=sources, caveats=caveats, **kwargs)
    if destination is None:
        return payload
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


build_csv_export = export_csv
build_pdf_export = export_pdf
export_snapshot_pdf = export_pdf


__all__ = ["csv_bytes", "export_csv", "pdf_bytes", "export_pdf", "build_csv_export", "build_pdf_export", "export_snapshot_pdf"]
