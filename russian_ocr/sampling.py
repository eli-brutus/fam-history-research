from collections import defaultdict
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
from .storage import write_json


def select(manifest: dict, count: int = 12, paths: list[str] | None = None) -> list[dict]:
    if count < 1:
        raise ValueError("Sample count must be positive")
    candidates = [p for p in manifest["pages"] if p["status"] == "inventoried" and not p["duplicate_of"]]
    if paths:
        lookup = {p["relative_path"]: p for p in candidates}
        if len(paths) != len(set(paths)) or set(paths) - lookup.keys():
            raise ValueError("Explicit paths must be unique, valid, nonduplicate scans")
        return [lookup[p] for p in paths]
    groups = defaultdict(list)
    for page in sorted(candidates, key=lambda p: p["id"]):
        groups[page["folder"]].append(page)
    result = []
    while groups and len(result) < count:
        for folder in sorted(list(groups)):
            result.append(groups[folder].pop(0))
            if not groups[folder]:
                del groups[folder]
            if len(result) == count:
                break
    return result


def save_sample(manifest: dict, output: Path, count: int, paths: list[str] | None = None) -> list[dict]:
    pages = select(manifest, count, paths)
    write_json(output / "reports" / "sample.json", {"pages": pages, "selection": "explicit" if paths else "deterministic folder round robin; visually verify representativeness"})
    if not pages:
        raise ValueError("No valid unique scans")
    width, cell_h, columns = 300, 370, 3
    sheet = Image.new("RGB", (width * columns, cell_h * ((len(pages) + columns - 1) // columns)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, page in enumerate(pages):
        with Image.open(Path(manifest["root"]) / page["relative_path"]) as source:
            thumb = ImageOps.contain(ImageOps.exif_transpose(source).convert("RGB"), (width - 10, cell_h - 55))
        x, y = (i % columns) * width, (i // columns) * cell_h
        sheet.paste(thumb, (x, y))
        draw.text((x + 3, y + cell_h - 50), f"{i+1}: {page['relative_path'][:65]}", fill="black")
    sheet.save(output / "reports" / "contact_sheet.png")
    return pages
