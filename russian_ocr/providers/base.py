from pathlib import Path
from typing import Protocol
from ..models import OCRDocument


class OCRProvider(Protocol):
    name: str
    model: str
    api_version: str

    def recognize(self, image: Path, page: dict, processed: dict) -> tuple[OCRDocument, dict]: ...
