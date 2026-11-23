"""Styled Excel (.xlsx) and Markdown specification exporters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from models import BatchSpecReport

_HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_TOTAL_FONT = Font(bold=True, size=11)
_THIN_SIDE = Side(style="thin", color="D0D7DE")
_CELL_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)


def _finalize_sheet_style(
    ws: Any,
    col_count: int,
    *,
    number_cols: set[int] | None = None,
    bold_last_row: bool = False,
) -> None:
    """Apply header styling, borders, number formatting, and column widths."""
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 24
    for col_idx in range(1, col_count + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _CELL_BORDER

    num_cols = number_cols or set()
    for row_idx in range(2, ws.max_row + 1):
        is_total = bold_last_row and row_idx == ws.max_row
        for col_idx in range(1, col_count + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = _CELL_BORDER
            if col_idx in num_cols:
                cell.number_format = "#,##0.00"
            if is_total:
                cell.font = _TOTAL_FONT

    for col_idx in range(1, col_count + 1):
        col_letter = get_column_letter(col_idx)
        max_len = max(
            len(str(ws.cell(row=r, column=col_idx).value or ""))
            for r in range(1, ws.max_row + 1)
        )
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 52)


def export_excel(report: BatchSpecReport, output_path: str | Path) -> Path:
    """Write a multi-sheet styled .xlsx specification workbook."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    # 1. Summary sheet
    ws_sum = wb.active
    ws_sum.title = "Summary"
    sum_headers = [
        "Drawing",
        "Units",
        "Entities",
        "Text Notes",
        "Block Count",
        "Total Length",
        "Audit Issues",
    ]
    ws_sum.append(sum_headers)
    for drawing in report.drawings:
        ws_sum.append(
            [
                drawing.drawing_name,
                drawing.units,
                drawing.entity_count,
                drawing.text_count,
                drawing.total_blocks,
                drawing.total_length,
                len(drawing.issues),
            ]
        )
    if report.drawings:
        last = len(report.drawings) + 1
        ws_sum.append(
            [
                "TOTAL",
                "",
                f"=SUM(C2:C{last})",
                f"=SUM(D2:D{last})",
                f"=SUM(E2:E{last})",
                f"=SUM(F2:F{last})",
                f"=SUM(G2:G{last})",
            ]
        )
    _finalize_sheet_style(
        ws_sum, len(sum_headers), number_cols={6}, bold_last_row=bool(report.drawings)
    )

    # 2. Blocks BOM sheet
    ws_bom = wb.create_sheet("Blocks BOM")
    bom_headers = ["Drawing", "Block Name", "Layer", "Quantity", "Attributes"]
    ws_bom.append(bom_headers)
    blocks = report.all_blocks
    for item in blocks:
        ws_bom.append(
            [
                item.drawing_name,
                item.block_name,
                item.layer,
                item.count,
                item.sample_attributes,
            ]
        )
    if blocks:
        last = len(blocks) + 1
        ws_bom.append(["TOTAL", "", "", f"=SUM(D2:D{last})", ""])
    _finalize_sheet_style(ws_bom, len(bom_headers), bold_last_row=bool(blocks))

    # 3. Layers & Lengths sheet
    ws_layers = wb.create_sheet("Layers & Lengths")
    layer_headers = [
        "Drawing",
        "Layer",
        "Color",
        "Linetype",
        "On",
        "Frozen",
        "Entities",
        "Total Length",
        "Closed Area",
        "Breakdown",
    ]
    ws_layers.append(layer_headers)
    layers = report.all_layers
    for item in layers:
        ws_layers.append(
            [
                item.drawing_name,
                item.layer,
                item.color,
                item.linetype,
                "Yes" if item.is_on else "No",
                "Yes" if item.is_frozen else "No",
                item.entity_count,
                item.total_length,
                item.closed_area,
                item.entity_breakdown,
            ]
        )
    if layers:
        last = len(layers) + 1
        ws_layers.append(
            [
                "TOTAL",
                "",
                "",
                "",
                "",
                "",
                f"=SUM(G2:G{last})",
                f"=SUM(H2:H{last})",
                f"=SUM(I2:I{last})",
                "",
            ]
        )
    _finalize_sheet_style(
        ws_layers,
        len(layer_headers),
        number_cols={8, 9},
        bold_last_row=bool(layers),
    )

    # 4. Audit Issues sheet
    ws_audit = wb.create_sheet("Audit Issues")
    audit_headers = ["Drawing", "Severity", "Code", "Target", "Message"]
    ws_audit.append(audit_headers)
    for issue in report.all_issues:
        ws_audit.append(
            [
                issue.drawing_name,
                issue.severity,
                issue.code,
                issue.target,
                issue.message,
            ]
        )
    _finalize_sheet_style(ws_audit, len(audit_headers))

    wb.save(str(target))
    return target


def export_markdown_summary(report: BatchSpecReport, output_path: str | Path) -> Path:
    """Write a readable Markdown summary of drawings, BOM, and audit warnings."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# CAD Specification & Audit Report", ""]
    for drawing in report.drawings:
        lines.append(
            f"## {drawing.drawing_name} ({drawing.units}) — "
            f"{drawing.entity_count} entities, {drawing.total_blocks} blocks, "
            f"length {drawing.total_length:.2f}"
        )
        if drawing.blocks:
            lines.append("\n| Block | Layer | Qty | Sample Attributes |")
            lines.append("| :--- | :--- | ---: | :--- |")
            for blk in drawing.blocks:
                lines.append(
                    f"| `{blk.block_name}` | `{blk.layer}` | {blk.count} | {blk.sample_attributes or '—'} |"
                )
        if drawing.issues:
            lines.append("\n**Audit Issues:**")
            for issue in drawing.issues:
                lines.append(f"- **[{issue.severity}]** `{issue.target}` ({issue.code}): {issue.message}")
        lines.append("")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target
