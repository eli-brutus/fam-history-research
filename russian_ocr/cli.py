import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sys
from dotenv import load_dotenv
from .inventory import inventory
from .sampling import save_sample
from .preprocessing import preprocess, Settings
from .storage import read_json, write_json, page_dir, digest, fingerprint, protect_source
from .reporting import generate

LOG = logging.getLogger("russian_ocr")


def emit(event: str, **fields) -> None:
    import json
    LOG.info(json.dumps({"event": event, **fields}, ensure_ascii=False))


def selected(output: Path, maximum: int | None = None) -> tuple[dict, list[dict]]:
    manifest = read_json(output / "reports" / "manifest.json")
    if Path(manifest["source"]).is_dir():
        protect_source(Path(manifest["source"]), output)
    sample = read_json(output / "reports" / "sample.json")["pages"]
    if maximum is not None and maximum < 1:
        raise ValueError("max-pages must be positive")
    return manifest, sample[:maximum] if maximum else sample


def benchmark(output: Path, providers: list[str], maximum: int | None, dry_run: bool, resume: bool,
              force: bool, yes: bool, locale: str | None) -> dict:
    if resume and force:
        raise ValueError("--resume and --force are mutually exclusive")
    if len(providers) != len(set(providers)) or set(providers) - {"azure", "transkribus"}:
        raise ValueError("Providers must be azure and/or transkribus, without duplicates")
    manifest, pages = selected(output, maximum)
    jobs = []
    reused = 0
    for page in pages:
        source = Path(manifest["root"]) / page["relative_path"]
        if digest(source) != page["sha256"]:
            raise ValueError("Source changed since inventory; inventory and select again")
        directory = page_dir(output, page)
        image = directory / "image_processed.png"
        metadata = read_json(directory / "image_processed.json")
        if digest(image) != metadata["sha256"] or metadata["source_sha256"] != page["sha256"]:
            raise ValueError("Processed image metadata mismatch; preprocess again")
        for provider in providers:
            model = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_MODEL", "prebuilt-read") if provider == "azure" else os.getenv("TRANSKRIBUS_MODEL_ID", "148545")
            api = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_VERSION", "2024-11-30") if provider == "azure" else "v2"
            cache_key = fingerprint({"source": page["sha256"], "processed": metadata["sha256"], "settings": metadata["settings"],
                                     "provider": provider, "model": model, "api": api, "locale": locale if provider == "azure" else None})
            receipt = directory / f"{provider}_receipt.json"
            if receipt.exists() and not force:
                state = read_json(receipt)
                if state.get("cache_key") == cache_key and state.get("status") == "succeeded" and all((directory / f"{provider}_{kind}.json").exists() for kind in ("raw", "normalized")):
                    reused += 1
                    continue
                raise ValueError("Existing or interrupted OCR result requires explicit --force; inspect receipts to avoid duplicate charges")
            jobs.append((page, provider, model, api, image, metadata, cache_key, receipt))
    summary = {"planned_document_submissions": len(jobs), "pages": len(pages), "reused": reused,
               "dry_run": dry_run, "note": "Polling and authentication are additional HTTP requests; account-specific charges are unknown."}
    print(summary)
    if dry_run or not jobs:
        return summary
    # Preflight all providers before any provider can incur a charge.
    clients = {}
    rates = {}
    for provider in providers:
        value = os.getenv(f"OCR_{provider.upper()}_COST_PER_PAGE")
        if value is not None:
            import math
            rates[provider] = float(value)
            if not math.isfinite(rates[provider]) or rates[provider] < 0:
                raise ValueError("Configured cost per page must be finite and nonnegative")
    for provider in sorted(set(job[1] for job in jobs)):
        if provider == "azure":
            from .providers.azure import AzureOCRProvider
            clients[provider] = AzureOCRProvider(locale)
        else:
            from .providers.transkribus import TranskribusOCRProvider
            clients[provider] = TranskribusOCRProvider()
    if not yes and input(f"Submit {len(jobs)} potentially billable document analyses? Type YES: ") != "YES":
        raise ValueError("Paid submissions cancelled")
    failures = 0
    for page, provider, model, api, image, metadata, key, receipt in jobs:
        if force and receipt.exists():
            import shutil
            archive = receipt.parent / "history" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + provider)
            archive.mkdir(parents=True, exist_ok=False)
            for existing in receipt.parent.glob(f"{provider}_*"):
                if existing.is_file():
                    shutil.copy2(existing, archive / existing.name)
            if (receipt.parent / f"{provider}.docx").exists():
                shutil.copy2(receipt.parent / f"{provider}.docx", archive / f"{provider}.docx")
        record = {"cache_key": key, "provider": provider, "model": model, "api_version": api,
                  "relative_path": page["relative_path"], "status": "submitting", "at": datetime.now(timezone.utc).isoformat()}
        write_json(receipt, record)
        try:
            document, raw = clients[provider].recognize(image, page, metadata)
            if provider in rates:
                document.processing["cost_estimate"] = {"amount": rates[provider], "currency": os.getenv("OCR_COST_CURRENCY", "unspecified"), "basis": "user-configured per-page price"}
            write_json(receipt.parent / f"{provider}_raw.json", raw)
            write_json(receipt.parent / f"{provider}_normalized.json", document.to_dict())
            record["status"] = "succeeded"
        except Exception as error:
            # Error messages may include request details; record only a safe type.
            failures += 1
            record.update(status="failed_or_unknown", error_type=type(error).__name__)
            emit("provider_failure", provider=provider, page_id=page["id"], error_type=type(error).__name__)
        write_json(receipt, record)
    generate(output, pages)
    if failures:
        raise RuntimeError(f"{failures} submissions failed or have unknown status; inspect receipts before retrying")
    return summary


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Russian handwriting pilot; no paid calls by default")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("inventory", "sample", "preprocess", "benchmark", "report", "evaluate"):
        p = sub.add_parser(command)
        p.add_argument("--output-dir", type=Path, default=Path("data/output"))
        if command == "inventory":
            p.add_argument("--input", type=Path, required=True)
        elif command == "sample":
            p.add_argument("--count", type=int, default=12)
            p.add_argument("--path", action="append")
        elif command == "preprocess":
            p.add_argument("--rotation", type=int, default=0)
            p.add_argument("--deskew-degrees", type=float, default=0)
            p.add_argument("--contrast", type=float, default=1)
            p.add_argument("--scale", type=float, default=1)
            p.add_argument("--grayscale", action="store_true")
            p.add_argument("--sample", action="store_true")
        elif command == "benchmark":
            p.add_argument("--providers", "--provider", default="azure,transkribus")
            p.add_argument("--max-pages", type=int, default=12)
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--resume", action="store_true")
            p.add_argument("--force", action="store_true")
            p.add_argument("--yes", action="store_true", help="Explicit authorization for displayed billable submission count")
            p.add_argument("--locale", choices=["ru"])
            p.add_argument("--sample", action="store_true")
        elif command == "evaluate":
            p.add_argument("--ground-truth", type=Path, help="Directory of <page_id>.json verified references")
        else:
            p.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    try:
        if args.command == "inventory":
            result = inventory(args.input, output)
            emit("inventory_complete", pages=len(result["pages"]), unique_pages=result["unique_pages"])
        elif args.command == "sample":
            pages = save_sample(read_json(output / "reports" / "manifest.json"), output, args.count, args.path)
            emit("sample_complete", pages=len(pages))
        elif args.command == "preprocess":
            manifest, pages = selected(output)
            settings = Settings(args.rotation, args.deskew_degrees, args.contrast, args.grayscale, args.scale)
            for page in pages:
                source = Path(manifest["root"]) / page["relative_path"]
                if digest(source) != page["sha256"]:
                    raise ValueError("Source changed; repeat inventory")
                preprocess(source, page_dir(output, page) / "image_processed.png", settings)
                preprocess(source, page_dir(output, page) / "image_reference.png", Settings(rotation=settings.rotation))
            emit("preprocessing_complete", pages=len(pages), settings=asdict(settings))
        elif args.command == "benchmark":
            benchmark(output, args.providers.split(","), args.max_pages, args.dry_run, args.resume, args.force, args.yes, args.locale)
        else:
            _, pages = selected(output)
            if args.command == "evaluate" and args.ground_truth:
                for page in pages:
                    reference = args.ground_truth / f"{page['id']}.json"
                    if reference.exists():
                        truth = read_json(reference)
                        if truth.get("verified") is not True or truth.get("source_sha256") != page["sha256"] or not isinstance(truth.get("text"), str):
                            raise ValueError("Ground truth must be human-verified and match the source checksum")
                        write_json(page_dir(output, page) / "ground_truth.json", truth)
            rows = generate(output, pages)
            emit("reports_complete", pages=len(rows), scored=sum(row["scored"] for row in rows))
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
