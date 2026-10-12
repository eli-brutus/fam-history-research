"""Atomic local storage; no manuscript data leaves the machine here."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def atomic_write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".ocr-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data.encode("utf-8") if isinstance(data, str) else data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def page_dir(output: Path, page: dict) -> Path:
    source = Path(page["relative_path"])
    return output / "pages" / source.parent / f"{source.stem}-{page['id'][:12]}"


def protect_source(source: Path, output: Path) -> None:
    if output.resolve() == source.resolve() or source.resolve() in output.resolve().parents:
        raise ValueError("Output must be outside the source root")
