"""Inventory sources without renaming them. ZIP extraction is bounded and safe."""
from pathlib import Path, PurePosixPath
import stat
import zipfile
from PIL import Image
from .storage import digest, fingerprint, write_json, protect_source

EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def extract_zip(archive: Path, destination: Path, max_bytes: int = 4 * 1024**3) -> Path:
    destination = destination.resolve()
    total = 0
    with zipfile.ZipFile(archive) as z:
        members = []
        names = set()
        for entry in z.infolist():
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename
                    or (path.parts and ":" in path.parts[0])
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError(f"Unsafe ZIP entry: {entry.filename}")
            if entry.is_dir():
                continue
            total += entry.file_size
            if total > max_bytes:
                raise ValueError("ZIP exceeds extraction size limit")
            if path.suffix.lower() not in EXTENSIONS:
                continue
            if str(path) in names:
                raise ValueError(f"Ambiguous repeated ZIP path: {path}")
            names.add(str(path))
            target = destination.joinpath(*path.parts)
            if destination not in target.resolve().parents:
                raise ValueError("ZIP entry escapes destination")
            members.append((entry, target))
        # Validate every entry before writing any files.
        for entry, target in members:
            data = z.read(entry)  # Validates ZIP CRC.
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError(f"Refusing to overwrite existing file: {target}")
            else:
                from .storage import atomic_write
                atomic_write(target, data)
    return destination


def inventory(source: Path, output: Path) -> dict:
    source = source.resolve()
    output = output.resolve()
    if source.is_dir():
        protect_source(source, output)
        root = source
    elif source.is_file() and source.suffix.lower() == ".zip":
        root = extract_zip(source, output / "extracted" / digest(source)[:16])
    else:
        raise ValueError("Input must be an existing directory or ZIP archive")
    pages = []
    seen: dict[str, str] = {}
    for file in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if not file.is_file() or file.suffix.lower() not in EXTENSIONS:
            continue
        if file.is_symlink() or root not in file.resolve().parents:
            raise ValueError(f"Source symlinks are not supported: {file}")
        relative = file.relative_to(root).as_posix()
        checksum = digest(file)
        page = {"relative_path": relative, "folder": str(Path(relative).parent),
                "filename": file.name, "sha256": checksum,
                "id": fingerprint([relative, checksum]), "size_bytes": file.stat().st_size,
                "candidate_page_number": None, "confirmed_page_number": None,
                "duplicate_of": seen.get(checksum), "status": "inventoried"}
        try:
            with Image.open(file) as image:
                page.update(width=image.width, height=image.height, format=image.format,
                            exif_orientation=image.getexif().get(274), frames=getattr(image, "n_frames", 1))
            with Image.open(file) as verification:
                verification.verify()
            if page["frames"] > 1:
                page["status"] = "unsupported_multipage_image"
        except (OSError, ValueError) as error:
            page.update(status="invalid_image", error=type(error).__name__)
        if page["status"] == "inventoried":
            seen.setdefault(checksum, relative)
        pages.append(page)
    result = {"source": str(source), "root": str(root), "pages": pages,
              "unique_pages": sum(p["status"] == "inventoried" and not p["duplicate_of"] for p in pages)}
    write_json(output / "reports" / "manifest.json", result)
    return result
