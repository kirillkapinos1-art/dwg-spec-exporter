"""Command-line interface for extracting DXF/DWG specifications to Excel and Markdown."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autocad_com import analyze_dwg_via_com
from dxf_analyzer import analyze_dxf
from excel_exporter import export_excel, export_markdown_summary
from models import BatchSpecReport, DrawingSpecReport


def collect_drawings(
    input_path: str | Path,
    *,
    recursive: bool = False,
    use_com: bool = False,
) -> list[Path]:
    """Find .dxf (or .dwg when use_com=True) files from a file or directory path."""
    target = Path(input_path)
    if not target.exists():
        raise FileNotFoundError(f"Input path not found: {target}")

    allowed_exts = {".dwg", ".dxf"} if use_com else {".dxf"}
    if target.is_file():
        if target.suffix.lower() not in allowed_exts:
            raise ValueError(
                f"Unsupported extension '{target.suffix}'. "
                f"Use .dxf offline or pass --com for .dwg on Windows AutoCAD."
            )
        return [target]

    iterator = target.rglob("*") if recursive else target.glob("*")
    files = sorted(
        p for p in iterator if p.is_file() and p.suffix.lower() in allowed_exts
    )
    if not files:
        raise FileNotFoundError(
            f"No matching {'/'.join(sorted(allowed_exts))} files found in {target}"
        )
    return files


def run_export(
    input_path: str | Path,
    *,
    out_xlsx: str | Path,
    out_md: str | Path | None = None,
    pdf_dir: str | Path | None = None,
    recursive: bool = False,
    use_com: bool = False,
) -> BatchSpecReport:
    """Analyze matching drawings and write Excel (and optional Markdown/PDF) reports."""
    files = collect_drawings(input_path, recursive=recursive, use_com=use_com)
    reports: list[DrawingSpecReport] = []
    for file_path in files:
        if use_com:
            reports.append(analyze_dwg_via_com(file_path, pdf_out_dir=pdf_dir))
        else:
            reports.append(analyze_dxf(file_path))

    batch = BatchSpecReport(drawings=tuple(reports))
    export_excel(batch, out_xlsx)
    if out_md is not None:
        export_markdown_summary(batch, out_md)
    return batch


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Audit DXF/DWG drawings and export BOM/layer specifications to Excel (.xlsx)."
    )
    parser.add_argument("input_path", help="Path to a .dxf/.dwg file or folder of drawings")
    parser.add_argument("--out", default="specification.xlsx", help="Output .xlsx workbook path")
    parser.add_argument("--md", default="", help="Optional Markdown summary report path")
    parser.add_argument("--recursive", action="store_true", help="Scan subdirectories")
    parser.add_argument(
        "--com",
        action="store_true",
        help="Use live Windows AutoCAD COM mode to read .dwg files directly",
    )
    parser.add_argument(
        "--pdf-dir",
        default="",
        help="Optional directory to export PDFs when running in --com mode",
    )
    args = parser.parse_args(argv)

    try:
        batch = run_export(
            args.input_path,
            out_xlsx=args.out,
            out_md=args.md or None,
            pdf_dir=args.pdf_dir or None,
            recursive=args.recursive,
            use_com=args.com,
        )
        print(
            f"Analyzed {len(batch.drawings)} drawing(s) -> {args.out} "
            f"(blocks={sum(d.total_blocks for d in batch.drawings)}, "
            f"issues={len(batch.all_issues)})"
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
