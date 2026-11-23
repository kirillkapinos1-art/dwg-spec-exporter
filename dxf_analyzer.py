"""Cross-platform offline DXF specification extractor and auditor built on ezdxf."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import path as ezdxf_path

from models import AuditIssue, BlockSpecItem, DrawingSpecReport, LayerMetrics

_INSUNITS_MAP = {
    0: "Unitless",
    1: "Inches",
    2: "Feet",
    3: "Miles",
    4: "Millimeters",
    5: "Centimeters",
    6: "Meters",
    7: "Kilometers",
}


def _segment_length_with_bulge(
    p1: tuple[float, float], p2: tuple[float, float], bulge: float
) -> float:
    chord = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if chord <= 1e-12:
        return 0.0
    if abs(bulge) <= 1e-9:
        return chord
    theta = 4.0 * math.atan(abs(bulge))
    sin_half = math.sin(theta / 2.0)
    if abs(sin_half) <= 1e-12:
        return chord
    radius = chord / (2.0 * sin_half)
    return radius * theta


def _polygon_area_2d(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    count = len(points)
    for idx in range(count):
        x1, y1 = points[idx]
        x2, y2 = points[(idx + 1) % count]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) * 0.5


def _measure_entity(entity: Any) -> tuple[float, float]:
    """Return (linear_length, closed_area) for supported ModelSpace CAD primitives."""
    dxftype = entity.dxftype()
    if dxftype == "LINE":
        start = entity.dxf.start
        end = entity.dxf.end
        return math.dist((start.x, start.y, start.z), (end.x, end.y, end.z)), 0.0

    if dxftype == "CIRCLE":
        radius = float(entity.dxf.radius)
        return 2.0 * math.pi * radius, math.pi * radius * radius

    if dxftype == "ARC":
        radius = float(entity.dxf.radius)
        start_deg = float(entity.dxf.start_angle)
        end_deg = float(entity.dxf.end_angle)
        delta_deg = (end_deg - start_deg) % 360.0
        if delta_deg == 0.0 and end_deg != start_deg:
            delta_deg = 360.0
        return radius * math.radians(delta_deg), 0.0

    if dxftype == "LWPOLYLINE":
        pts = list(entity.get_points("xyb"))
        if len(pts) < 2:
            return 0.0, 0.0
        total_len = 0.0
        for idx in range(len(pts) - 1):
            total_len += _segment_length_with_bulge(
                (pts[idx][0], pts[idx][1]),
                (pts[idx + 1][0], pts[idx + 1][1]),
                pts[idx][2],
            )
        area = 0.0
        if entity.closed:
            total_len += _segment_length_with_bulge(
                (pts[-1][0], pts[-1][1]),
                (pts[0][0], pts[0][1]),
                pts[-1][2],
            )
            if all(abs(p[2]) <= 1e-9 for p in pts):
                area = _polygon_area_2d([(p[0], p[1]) for p in pts])
        return total_len, area

    if dxftype == "POLYLINE":
        verts = [tuple(v.dxf.location) for v in entity.vertices]
        if len(verts) < 2:
            return 0.0, 0.0
        total_len = sum(
            math.dist(verts[i], verts[i + 1]) for i in range(len(verts) - 1)
        )
        if entity.is_closed:
            total_len += math.dist(verts[-1], verts[0])
        return total_len, 0.0

    if dxftype in ("SPLINE", "ELLIPSE"):
        try:
            cad_path = ezdxf_path.make_path(entity)
            sampled = [tuple(pt) for pt in cad_path.flattening(0.05)]
            if len(sampled) >= 2:
                return (
                    sum(
                        math.dist(sampled[i], sampled[i + 1])
                        for i in range(len(sampled) - 1)
                    ),
                    0.0,
                )
        except Exception:
            return 0.0, 0.0

    return 0.0, 0.0


def analyze_dxf(path: str | Path) -> DrawingSpecReport:
    """Analyze a .dxf file and return layer totals, block BOM, and CAD audit issues."""
    dxf_path = Path(path)
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    raw_units = int(doc.header.get("$INSUNITS", 0) or 0)
    units_label = _INSUNITS_MAP.get(raw_units, f"Code({raw_units})")

    layer_lengths: defaultdict[str, float] = defaultdict(float)
    layer_areas: defaultdict[str, float] = defaultdict(float)
    layer_types: defaultdict[str, Counter[str]] = defaultdict(Counter)
    block_counts: Counter[tuple[str, str]] = Counter()
    block_attrs: dict[tuple[str, str], str] = {}

    entity_count = 0
    text_count = 0

    for entity in msp:
        entity_count += 1
        dxftype = entity.dxftype()
        layer_name = str(getattr(entity.dxf, "layer", "0") or "0")
        layer_types[layer_name][dxftype] += 1

        if dxftype in ("TEXT", "MTEXT"):
            text_count += 1
            continue

        if dxftype == "INSERT":
            bname = str(entity.dxf.name)
            key = (bname, layer_name)
            block_counts[key] += 1
            if key not in block_attrs and entity.attribs:
                pairs = [
                    f"{attrib.dxf.tag}={attrib.dxf.text}"
                    for attrib in entity.attribs
                    if getattr(attrib.dxf, "text", "").strip()
                ]
                if pairs:
                    block_attrs[key] = "; ".join(pairs[:6])
            continue

        length, area = _measure_entity(entity)
        layer_lengths[layer_name] += length
        layer_areas[layer_name] += area

    layer_metrics: list[LayerMetrics] = []
    defined_layers = {layer.dxf.name: layer for layer in doc.layers}
    all_layer_names = sorted(set(defined_layers.keys()) | set(layer_types.keys()))

    issues: list[AuditIssue] = []
    drawing_name = dxf_path.name

    if raw_units == 0:
        issues.append(
            AuditIssue(
                drawing_name=drawing_name,
                severity="WARNING",
                code="UNITLESS_DRAWING",
                target="$INSUNITS",
                message="Drawing $INSUNITS is set to 0 (Unitless); verify scale before manufacturing.",
            )
        )

    for lname in all_layer_names:
        layer_obj = defined_layers.get(lname)
        color = int(layer_obj.color) if layer_obj is not None else 7
        linetype = str(layer_obj.dxf.linetype) if layer_obj is not None else "Continuous"
        is_on = bool(layer_obj.is_on()) if layer_obj is not None else True
        is_frozen = bool(layer_obj.is_frozen()) if layer_obj is not None else False

        breakdown_counter = layer_types.get(lname, Counter())
        count = sum(breakdown_counter.values())
        breakdown_str = ", ".join(
            f"{etype}:{cnt}" for etype, cnt in sorted(breakdown_counter.items())
        )
        layer_metrics.append(
            LayerMetrics(
                drawing_name=drawing_name,
                layer=lname,
                color=color,
                linetype=linetype,
                is_on=is_on,
                is_frozen=is_frozen,
                entity_count=count,
                total_length=round(layer_lengths[lname], 4),
                closed_area=round(layer_areas[lname], 4),
                entity_breakdown=breakdown_str,
            )
        )

        if count == 0 and lname not in ("0", "Defpoints"):
            issues.append(
                AuditIssue(
                    drawing_name=drawing_name,
                    severity="INFO",
                    code="UNUSED_LAYER",
                    target=lname,
                    message=f"Layer '{lname}' has 0 entities in ModelSpace.",
                )
            )
        elif lname == "0" and count > 0 and len(defined_layers) > 1:
            issues.append(
                AuditIssue(
                    drawing_name=drawing_name,
                    severity="WARNING",
                    code="GEOMETRY_ON_LAYER_0",
                    target="0",
                    message=f"Found {count} entity(ies) directly on layer '0'.",
                )
            )

    block_items = tuple(
        BlockSpecItem(
            drawing_name=drawing_name,
            block_name=bname,
            layer=lname,
            count=cnt,
            sample_attributes=block_attrs.get((bname, lname), ""),
        )
        for (bname, lname), cnt in sorted(block_counts.items())
    )

    return DrawingSpecReport(
        source_path=str(dxf_path),
        drawing_name=drawing_name,
        units=units_label,
        entity_count=entity_count,
        text_count=text_count,
        layers=tuple(layer_metrics),
        blocks=block_items,
        issues=tuple(issues),
    )
