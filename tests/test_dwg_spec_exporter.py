"""End-to-end tests generating real DXF drawings and verifying Excel BOM/layer output."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf
from openpyxl import load_workbook

from cli import run_export
from dxf_analyzer import analyze_dxf


def _create_sample_dxf(path: Path) -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # Millimeters

    doc.layers.add("WALLS", color=7)
    doc.layers.add("DOORS", color=3)
    doc.layers.add("UNUSED_TEMP", color=1)

    door_blk = doc.blocks.new(name="DOOR_900")
    door_blk.add_line((0, 0), (0, 900))
    door_blk.add_attdef("CODE", insert=(100, 100), dxfattribs={"height": 50})

    msp = doc.modelspace()
    # Closed 4000x5000 room -> perimeter 18000, area 20,000,000
    msp.add_lwpolyline(
        [(0, 0), (4000, 0), (4000, 5000), (0, 5000)],
        close=True,
        dxfattribs={"layer": "WALLS"},
    )
    msp.add_line((0, 0), (3500, 0), dxfattribs={"layer": "WALLS"})
    msp.add_circle((1000, 1000), radius=100.0, dxfattribs={"layer": "WALLS"})
    # Geometry directly on layer 0 triggers hygiene warning.
    msp.add_arc((500, 500), radius=200.0, start_angle=0.0, end_angle=90.0, dxfattribs={"layer": "0"})

    ref1 = msp.add_blockref("DOOR_900", (1000, 0), dxfattribs={"layer": "DOORS"})
    ref1.add_auto_attribs({"CODE": "D1"})
    ref2 = msp.add_blockref("DOOR_900", (2500, 0), dxfattribs={"layer": "DOORS"})
    ref2.add_auto_attribs({"CODE": "D1"})

    msp.add_mtext("Room A-101", dxfattribs={"layer": "WALLS"})

    doc.saveas(str(path))
    return path


def test_analyze_dxf_lengths_areas_blocks_and_audit(tmp_path: Path) -> None:
    dxf_path = _create_sample_dxf(tmp_path / "plan.dxf")
    report = analyze_dxf(dxf_path)

    assert report.units == "Millimeters"
    assert report.text_count == 1
    assert report.total_blocks == 2
    assert len(report.blocks) == 1
    assert report.blocks[0].block_name == "DOOR_900"
    assert report.blocks[0].count == 2
    assert "CODE=D1" in report.blocks[0].sample_attributes

    walls = next(layer for layer in report.layers if layer.layer == "WALLS")
    expected_walls_len = 18000.0 + 3500.0 + (2.0 * math.pi * 100.0)
    expected_walls_area = 20_000_000.0 + (math.pi * 100.0 * 100.0)
    assert math.isclose(walls.total_length, expected_walls_len, rel_tol=1e-4)
    assert math.isclose(walls.closed_area, expected_walls_area, rel_tol=1e-4)

    issue_codes = {issue.code for issue in report.issues}
    assert "UNUSED_LAYER" in issue_codes
    assert "GEOMETRY_ON_LAYER_0" in issue_codes


def test_cli_batch_excel_and_markdown_export(tmp_path: Path) -> None:
    drawings_dir = tmp_path / "drawings"
    drawings_dir.mkdir()
    _create_sample_dxf(drawings_dir / "floor_1.dxf")
    _create_sample_dxf(drawings_dir / "floor_2.dxf")

    out_xlsx = tmp_path / "out" / "spec.xlsx"
    out_md = tmp_path / "out" / "spec.md"

    batch = run_export(drawings_dir, out_xlsx=out_xlsx, out_md=out_md)
    assert len(batch.drawings) == 2
    assert out_xlsx.exists()
    assert out_md.exists()

    wb = load_workbook(str(out_xlsx))
    assert wb.sheetnames == ["Summary", "Blocks BOM", "Layers & Lengths", "Audit Issues"]

    ws_sum = wb["Summary"]
    assert ws_sum["A1"].value == "Drawing"
    assert ws_sum["A2"].value == "floor_1.dxf"
    assert ws_sum["A3"].value == "floor_2.dxf"
    assert ws_sum["A4"].value == "TOTAL"
    assert ws_sum["E4"].value == "=SUM(E2:E3)"

    ws_bom = wb["Blocks BOM"]
    assert ws_bom["A1"].value == "Drawing"
    assert ws_bom["B2"].value == "DOOR_900"
    assert ws_bom["D2"].value == 2
    assert ws_bom["D4"].value == "=SUM(D2:D3)"

    md_text = out_md.read_text(encoding="utf-8")
    assert "DOOR_900" in md_text
    assert "UNUSED_LAYER" in md_text
