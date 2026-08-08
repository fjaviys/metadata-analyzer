"""
report_generator.py — Informe PDF del análisis con reportlab.

Secciones: portada, resumen ejecutivo, estadísticas detalladas, tablas por
carpetas (nivel 1 y nivel 2, orden descendente por nº de archivos) y
recomendaciones.

IMPORTANTE (reportlab): NUNCA usar caracteres Unicode de subíndice/superíndice
(²³…). Para exponentes o índices usar etiquetas <sub>/<super> dentro de Paragraph.
Aquí no necesitamos exponentes, pero la utilidad `superscript()`/`subscript()` deja
constancia del patrón correcto por si se amplía el informe.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

_ACCENT = colors.HexColor("#2563eb")
_MUTED = colors.HexColor("#64748b")
_BG = colors.HexColor("#f1f5f9")
_OK = colors.HexColor("#16a34a")
_WARN = colors.HexColor("#dc2626")


def superscript(text: str) -> str:
    """Devuelve markup válido para reportlab (NUNCA Unicode)."""
    return f"<super>{text}</super>"


def subscript(text: str) -> str:
    return f"<sub>{text}</sub>"


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("CoverTitle", parent=ss["Title"], fontSize=26,
                          textColor=_ACCENT, spaceAfter=6))
    ss.add(ParagraphStyle("CoverSub", parent=ss["Normal"], fontSize=12,
                          textColor=_MUTED, spaceAfter=2))
    ss.add(ParagraphStyle("H2", parent=ss["Heading2"], textColor=_ACCENT,
                          spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8,
                          textColor=_MUTED))
    ss.add(ParagraphStyle("Cell", parent=ss["Normal"], fontSize=8, leading=10))
    return ss


def _kv_table(pairs, styles, col_widths=(6 * cm, 9 * cm)):
    data = [[Paragraph(f"<b>{k}</b>", styles["Cell"]), Paragraph(str(v), styles["Cell"])]
            for k, v in pairs]
    t = Table(data, colWidths=list(col_widths))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _BG),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _folder_table(rows, styles, title):
    header = ["Carpeta", "Archivos", "A corregir", "Corruptos", "Sin fecha EXIF"]
    data = [[Paragraph(f"<b>{h}</b>", styles["Cell"]) for h in header]]
    for r in rows:
        data.append([
            Paragraph(str(r.get("folder", "")), styles["Cell"]),
            str(r.get("total", 0)),
            str(r.get("needs_correction", 0)),
            str(r.get("corrupt", 0)),
            str(r.get("no_exif_date", 0)),
        ])
    t = Table(data, colWidths=[7 * cm, 2.2 * cm, 2.4 * cm, 2.2 * cm, 3 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _BG]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _recommendations(summary: dict) -> list[str]:
    recs: list[str] = []
    total = summary.get("total_files", 0) or 0
    needs = summary.get("needs_correction", 0) or 0
    corrupt = summary.get("corrupt", 0) or 0
    no_exif = summary.get("without_exif_date", 0) or 0

    if total == 0:
        return ["No se han encontrado archivos multimedia en la carpeta analizada."]

    pct = round(needs / total * 100, 1) if total else 0
    recs.append(f"{needs} de {total} archivos ({pct}%) requieren corrección de fecha.")
    if corrupt:
        recs.append(f"{corrupt} archivos tienen fechas EXIF corruptas (fuera de rango); "
                    f"se recomienda limpiarlas para que Immich no las use.")
    if no_exif:
        recs.append(f"{no_exif} archivos no tienen fecha EXIF fiable; cuando existe fecha "
                    f"en el nombre o la carpeta, se propone usarla.")
    recs.append("Ejecuta primero la corrección en modo DRY-RUN para revisar los cambios "
                "antes de escribir sobre los archivos.")
    recs.append("Se realizará un backup automático de cada archivo antes de modificarlo.")
    return recs


def generate_report(
    summary: dict,
    level1_folders: list[dict],
    level2_folders: list[dict],
    output_path: str,
    root: Optional[str] = None,
    precision_breakdown: Optional[dict] = None,
    duplicates_count: int = 0,
    max_folder_rows: int = 40,
) -> str:
    """
    Genera el PDF y devuelve la ruta. `summary` es AnalysisResult.summary_dict()
    (o equivalente). Las listas de carpetas deben venir ya ordenadas desc.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title="Metadata Analyzer — Informe de análisis",
    )
    story = []
    root = root or summary.get("root", "(desconocida)")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ---- Portada ----
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("Metadata Analyzer", styles["CoverTitle"]))
    story.append(Paragraph("Informe de análisis de metadatos", styles["CoverSub"]))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(f"<b>Carpeta analizada:</b> {root}", styles["CoverSub"]))
    story.append(Paragraph(f"<b>Generado:</b> {generated}", styles["CoverSub"]))
    story.append(Paragraph(f"<b>Total de archivos:</b> {summary.get('total_files', 0)}",
                          styles["CoverSub"]))
    story.append(PageBreak())

    # ---- Resumen ejecutivo ----
    story.append(Paragraph("Resumen ejecutivo", styles["H2"]))
    story.append(_kv_table([
        ("Total de archivos", summary.get("total_files", 0)),
        ("Fotos", summary.get("photos", 0)),
        ("Vídeos", summary.get("videos", 0)),
        ("Con fecha EXIF fiable", summary.get("with_exif_date", 0)),
        ("Sin fecha EXIF fiable", summary.get("without_exif_date", 0)),
        ("Fechas corruptas", summary.get("corrupt", 0)),
        ("Con inconsistencias", summary.get("inconsistent", 0)),
        ("Requieren corrección", summary.get("needs_correction", 0)),
        ("Duplicados detectados", duplicates_count),
        ("Errores de lectura", summary.get("read_errors", 0)),
    ], styles))

    # ---- Recomendaciones ----
    story.append(Paragraph("Recomendaciones", styles["H2"]))
    for rec in _recommendations(summary):
        story.append(Paragraph(f"• {rec}", styles["Normal"]))
        story.append(Spacer(1, 2))

    # ---- Precisión de la corrección propuesta ----
    if precision_breakdown:
        story.append(Paragraph("Precisión de las fechas propuestas", styles["H2"]))
        story.append(_kv_table(
            [(k, v) for k, v in sorted(precision_breakdown.items(),
                                       key=lambda kv: kv[1], reverse=True)],
            styles))

    story.append(PageBreak())

    # ---- Carpetas nivel 1 ----
    story.append(Paragraph("Estadísticas por carpeta — nivel 1", styles["H2"]))
    if level1_folders:
        story.append(_folder_table(level1_folders[:max_folder_rows], styles, "nivel 1"))
    else:
        story.append(Paragraph("Sin datos.", styles["Normal"]))

    # ---- Carpetas nivel 2 ----
    story.append(Paragraph("Estadísticas por carpeta — nivel 2", styles["H2"]))
    if level2_folders:
        story.append(_folder_table(level2_folders[:max_folder_rows], styles, "nivel 2"))
    else:
        story.append(Paragraph("Sin datos.", styles["Normal"]))

    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "Informe generado automáticamente por Metadata Analyzer. Las correcciones "
        "requieren confirmación explícita y se realizan con backup y verificación.",
        styles["Small"]))

    doc.build(story)
    return output_path


__all__ = ["generate_report", "superscript", "subscript"]
