"""Optional Windows COM bridge for live AutoCAD .dwg extraction and PDF export."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from models import AuditIssue, BlockSpecItem, DrawingSpecReport, LayerMetrics

_INSUNITS_MAP = {
    0: "Unitless",
    1: "Inches",
    2: "Feet",
    4: "Millimeters",
    5: "Centimeters",
    6: "Meters",
}


class AutoCADUnavailableError(RuntimeError):
    """Raised when pywin32 or a running AutoCAD COM server is unavailable."""


def _connect_autocad() -> Any:
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise AutoCADUnavailableError(
            "pywin32 is required for live AutoCAD COM mode (Windows only)."
        ) from exc

    pythoncom.CoInitialize()
    for prog_id in ("AutoCAD.Application", "AutoCAD.Application.26", "AutoCAD.Application.25"):
        try:
            return win32com.client.GetActiveObject(prog_id)
        except Exception:
            continue
    raise AutoCADUnavailableError(
        "No running Autodesk AutoCAD instance found. Open AutoCAD or analyze .dxf offline."
    )


def analyze_dwg_via_com(
    dwg_path: str | Path,
    *,
    pdf_out_dir: str | Path | None = None,
) -> DrawingSpecReport:
    """Open a .dwg read-only in running AutoCAD via COM, extract BOM/layers, and optionally export PDF."""
    acad = _connect_autocad()
    target_path = Path(dwg_path).resolve()
    doc = acad.Documents.Open(str(target_path), True)
    try:
        raw_units = int(doc.GetVariable("INSUNITS") or 0)
        units = _INSUNITS_MAP.get(raw_units, f"Code({raw_units})")

        layer_lengths: defaultdict[str, float] = defaultdict(float)
        layer_areas: defaultdict[str, float] = defaultdict(float)
        layer_types: defaultdict[str, Counter[str]] = defaultdict(Counter)
        block_counts: Counter[tuple[str, str]] = Counter()
        block_attrs: dict[tuple[str, str], str] = {}

        entity_count = 0
        text_count = 0
        msp = doc.ModelSpace
        for idx in range(int(msp.Count)):
            ent = msp.Item(idx)
            entity_count += 1
            etype = str(getattr(ent, "ObjectName", "Unknown"))
            lname = str(getattr(ent, "Layer", "0") or "0")
            layer_types[lname][etype] += 1

            if etype in ("AcDbText", "AcDbMText"):
                text_count += 1
            elif etype == "AcDbBlockReference":
                bname = str(getattr(ent, "EffectiveName", None) or getattr(ent, "Name", "Block"))
                key = (bname, lname)
                block_counts[key] += 1
                if key not in block_attrs and getattr(ent, "HasAttributes", False):
                    pairs = [
                        f"{att.TagString}={att.TextString}"
                        for att in ent.GetAttributes()
                        if str(att.TextString).strip()
                    ]
                    if pairs:
                        block_attrs[key] = "; ".join(pairs[:6])
            elif etype in ("AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDbArc"):
                layer_lengths[lname] += float(getattr(ent, "Length", 0.0) or 0.0)
                layer_areas[lname] += float(getattr(ent, "Area", 0.0) or 0.0)
            elif etype == "AcDbCircle":
                layer_lengths[lname] += float(getattr(ent, "Circumference", 0.0) or 0.0)
                layer_areas[lname] += float(getattr(ent, "Area", 0.0) or 0.0)

        layer_metrics: list[LayerMetrics] = []
        issues: list[AuditIssue] = []
        for idx in range(int(doc.Layers.Count)):
            layer = doc.Layers.Item(idx)
            lname = str(layer.Name)
            breakdown = layer_types.get(lname, Counter())
            cnt = sum(breakdown.values())
            layer_metrics.append(
                LayerMetrics(
                    drawing_name=target_path.name,
                    layer=lname,
                    color=int(layer.Color),
                    linetype=str(layer.Linetype),
                    is_on=bool(layer.LayerOn),
                    is_frozen=bool(layer.Freeze),
                    entity_count=cnt,
                    total_length=round(layer_lengths[lname], 4),
                    closed_area=round(layer_areas[lname], 4),
                    entity_breakdown=", ".join(f"{k}:{v}" for k, v in sorted(breakdown.items())),
                )
            )
            if cnt == 0 and lname not in ("0", "Defpoints"):
                issues.append(
                    AuditIssue(
                        drawing_name=target_path.name,
                        severity="INFO",
                        code="UNUSED_LAYER",
                        target=lname,
                        message=f"Layer '{lname}' has 0 entities in ModelSpace.",
                    )
                )

        if pdf_out_dir is not None:
            out_dir = Path(pdf_out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            pdf_stem = str((out_dir / target_path.stem).resolve())
            empty_ss = doc.SelectionSets.Add(f"SPEC_EXP_{math.floor(10000)}")
            try:
                doc.Export(pdf_stem, "PDF", empty_ss)
            finally:
                empty_ss.Delete()

        blocks = tuple(
            BlockSpecItem(
                drawing_name=target_path.name,
                block_name=bname,
                layer=lname,
                count=cnt,
                sample_attributes=block_attrs.get((bname, lname), ""),
            )
            for (bname, lname), cnt in sorted(block_counts.items())
        )
        return DrawingSpecReport(
            source_path=str(target_path),
            drawing_name=target_path.name,
            units=units,
            entity_count=entity_count,
            text_count=text_count,
            layers=tuple(layer_metrics),
            blocks=blocks,
            issues=tuple(issues),
        )
    finally:
        doc.Close(False)
