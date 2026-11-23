"""Data models for CAD drawing specifications, layer metrics, and audit diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BlockSpecItem:
    """Aggregated count and sample attributes for a block reference on a layer."""

    drawing_name: str
    block_name: str
    layer: str
    count: int
    sample_attributes: str = ""


@dataclass(frozen=True, slots=True)
class LayerMetrics:
    """Geometry summary and linear/area totals for a single CAD layer."""

    drawing_name: str
    layer: str
    color: int
    linetype: str
    is_on: bool
    is_frozen: bool
    entity_count: int
    total_length: float
    closed_area: float
    entity_breakdown: str


@dataclass(frozen=True, slots=True)
class AuditIssue:
    """CAD hygiene or standardization warning discovered during inspection."""

    drawing_name: str
    severity: str
    code: str
    target: str
    message: str


@dataclass(frozen=True, slots=True)
class DrawingSpecReport:
    """Specification and audit report for a single DXF or DWG drawing."""

    source_path: str
    drawing_name: str
    units: str
    entity_count: int
    text_count: int
    layers: tuple[LayerMetrics, ...]
    blocks: tuple[BlockSpecItem, ...]
    issues: tuple[AuditIssue, ...]

    @property
    def total_length(self) -> float:
        return round(sum(layer.total_length for layer in self.layers), 4)

    @property
    def total_blocks(self) -> int:
        return sum(block.count for block in self.blocks)


@dataclass(frozen=True, slots=True)
class BatchSpecReport:
    """Combined specification across one or more analyzed CAD drawings."""

    drawings: tuple[DrawingSpecReport, ...] = field(default_factory=tuple)

    @property
    def all_layers(self) -> list[LayerMetrics]:
        items: list[LayerMetrics] = []
        for drawing in self.drawings:
            items.extend(drawing.layers)
        return items

    @property
    def all_blocks(self) -> list[BlockSpecItem]:
        items: list[BlockSpecItem] = []
        for drawing in self.drawings:
            items.extend(drawing.blocks)
        return items

    @property
    def all_issues(self) -> list[AuditIssue]:
        items: list[AuditIssue] = []
        for drawing in self.drawings:
            items.extend(drawing.issues)
        return items
