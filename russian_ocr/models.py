from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class OCRWord:
    text: str
    polygon: list[float] = field(default_factory=list)
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OCRLine:
    line_id: str
    region_id: str
    reading_order: int
    text: str
    polygon: list[float] = field(default_factory=list)
    confidence: float | None = None
    words: list[OCRWord] = field(default_factory=list)


@dataclass
class OCRDocument:
    relative_path: str
    source_hash: str
    provider: str
    model: str
    text: str
    lines: list[OCRLine]
    original_image: dict[str, Any]
    processed_image: dict[str, Any]
    processing: dict[str, Any]
    raw_result_location: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
