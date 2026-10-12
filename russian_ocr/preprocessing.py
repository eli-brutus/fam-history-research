from dataclasses import dataclass, asdict
from pathlib import Path
import io
from PIL import Image, ImageOps, ImageEnhance
from .storage import atomic_write, write_json, digest


@dataclass(frozen=True)
class Settings:
    rotation: int = 0
    deskew_degrees: float = 0.0
    contrast: float = 1.0
    grayscale: bool = False
    scale: float = 1.0


def preprocess(source: Path, target: Path, settings: Settings) -> dict:
    if source.resolve() == target.resolve():
        raise ValueError("Preprocessing must not overwrite the source image")
    if settings.rotation not in {0, 90, 180, 270}:
        raise ValueError("Rotation must be 0, 90, 180 or 270 degrees counterclockwise")
    if abs(settings.deskew_degrees) > 15 or not 0 < settings.scale <= 4 or not 0 < settings.contrast <= 4:
        raise ValueError("Deskew must be within 15 degrees; scale/contrast in (0, 4]")
    with Image.open(source) as original:
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError("Split multi-frame TIFFs into individual pages before benchmarking")
        image = ImageOps.exif_transpose(original).convert("RGB")
    if settings.rotation:
        image = image.rotate(settings.rotation, expand=True)
    if settings.deskew_degrees:
        image = image.rotate(settings.deskew_degrees, expand=True, fillcolor="white", resample=Image.Resampling.BICUBIC)
    if settings.grayscale:
        image = ImageOps.grayscale(image)
    if settings.contrast != 1:
        image = ImageEnhance.Contrast(image).enhance(settings.contrast)
    if settings.scale != 1:
        image = image.resize((max(1, round(image.width * settings.scale)), max(1, round(image.height * settings.scale))), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    if target.exists() and target.read_bytes() != buffer.getvalue():
        old_hash = digest(target)
        version = target.parent / "image_versions" / f"{old_hash}.png"
        atomic_write(version, target.read_bytes())
        if target.with_suffix(".json").exists():
            atomic_write(version.with_suffix(".json"), target.with_suffix(".json").read_bytes())
    atomic_write(target, buffer.getvalue())
    metadata = {"settings": asdict(settings), "sha256": digest(target), "source_sha256": digest(source),
                "width": image.width, "height": image.height, "format": "PNG", "path": str(target)}
    write_json(target.with_suffix(".json"), metadata)
    return metadata
