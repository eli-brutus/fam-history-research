# Russian handwriting OCR pilot

Python 3.11+ pilot infrastructure for `prebuilt-read` (Azure Document Intelligence API `2024-11-30`) and Transkribus Russian model `148545`. Optimize human-verified accuracy and coverage; no accuracy target is claimed without ground truth. Do not process the full archive or choose a final provider before reviewing pilot results.

## Current status

The repository was initially empty. Inventory, deterministic sampling, preprocessing, Azure SDK adapter, PAGE XML normalization, comparisons, HTML/CSV/JSON/Markdown reports, DOCX export, local ground-truth review, metrics and conservative resumption are implemented and tested offline. **Transkribus submission is intentionally unavailable:** its guides were verified, but the linked official API reference at `https://api-staging.transkribus.org/docs` returns a cloud proxy 403. The exact base64 `Image` schema must be verified before implementing submission; no guessed fields or alternative models are used. Preflight checks all requested providers before sending any images.

No manuscript archive or API credentials were provided. Consequently there is no inventory of the actual 126 pages and no real OCR comparison yet. Multi-frame TIFFs are inventoried but excluded with an explicit status; split them into individual pages outside the source tree before benchmarking.

## Install

```bash
cd /workspace/fam-history-research
python -m venv /workspace/ocr-venv
/workspace/ocr-venv/bin/python -m pip install -r requirements-lock.txt
/workspace/ocr-venv/bin/python -m pip install --no-deps -e .
source /workspace/ocr-venv/bin/activate
python -m pytest -q
```

`requirements-lock.txt` records the tested Python 3.12 Linux dependency environment; direct dependencies are also pinned in `pyproject.toml`. TLS and package verification remain enabled. No system service or GPU is needed. A review server is optional; offline CLI and tests are the required development workflow. Use this task's existing isolated checkout; do not create a Git worktree.

## Prepare a pilot without paid calls

Set an output directory outside the source tree. The input can be a ZIP or extracted directory. Source bytes and names, including Cyrillic, remain unchanged. Duplicate contents are represented in the manifest with folder provenance but selected only once. ZIP extraction rejects traversal, symlinks, ambiguous repeated paths and excessive decompressed sizes. The original ZIP is preserved.

```bash
python -m russian_ocr inventory --input /absolute/path/archive.zip --output-dir /workspace/ocr-output
python -m russian_ocr sample --count 12 --output-dir /workspace/ocr-output
python -m russian_ocr preprocess --sample --output-dir /workspace/ocr-output
python -m russian_ocr benchmark --providers azure,transkribus --sample --max-pages 12 --dry-run --output-dir /workspace/ocr-output
```

`reports/manifest.json` records source paths, stable IDs, SHA-256 hashes, dimensions, size, format, EXIF, frame count and status. `reports/sample.json` is reproducible using a hash ordering and round robin across folders. It does not claim to identify clear, dense or crossed-out writing. Inspect `reports/contact_sheet.png` and adjust explicitly:

```bash
python -m russian_ocr sample --path 'Мемуары/scan001.jpg' --path 'Дневник/scan003.png' --output-dir /workspace/ocr-output
```

Page-number candidates and confirmed numbers stay null until verified. Selection excludes invalid, duplicate and multi-frame images.

Minimal preprocessing applies only EXIF correction by default. Optional `--rotation 90` rotates counterclockwise; `--deskew-degrees -1.5` applies a manually determined skew correction; `--contrast 1.1`, `--grayscale`, and `--scale 1.5` are explicit experiments. No aspect-ratio rotation or automatic aggressive filtering occurs. Compare the generated `image_reference.png` (EXIF plus selected right-angle rotation) with `image_processed.png` before submitting. Both providers must receive the identical processed bytes; coordinates refer to those bytes. Every working copy has recorded settings and source/processed hashes.

## Credentials and first paid call

Copy `.env.example` to `.env` locally and securely fill only the credentials you need. Never paste credentials into chat, commit `.env`, or put secrets in setup scripts. Azure defaults to automatic language detection; `--locale ru` is a separate optional experiment. No engine confidence is invented or treated as interchangeable with the other engine's confidence.

The exact currently available Azure-only paid command is:

```bash
python -m russian_ocr benchmark --provider azure --sample --max-pages 1 --resume --output-dir /workspace/ocr-output
```

The command shows the planned number of document submissions and requires typing `YES`. `--yes` is explicit command-line authorization for unattended use; do not include it in setup/startup scripts. HTTP polling and authentication are additional requests. Actual costs depend on the provider/account. Optional OCR_AZURE_COST_PER_PAGE, OCR_TRANSKRIBUS_COST_PER_PAGE and OCR_COST_CURRENCY supply explicit per-page estimates; unset pricing remains unknown.

**The two-provider paid command is blocked until the Transkribus adapter is completed against the official API schema:**

```bash
python -m russian_ocr benchmark --providers azure,transkribus --sample --max-pages 12 --resume --output-dir /workspace/ocr-output
```

For cloud calls, add the exact Azure resource hostname to restricted network settings. The cloud secret system reserves names beginning `AZURE_`; the application additionally supports `OCR_AZURE_ENDPOINT` and `OCR_AZURE_KEY` as cloud aliases. Use an approved alias binding scoped to the exact resource host, never embed a key. Transkribus needs `TRANSKRIBUS_USERNAME`, `TRANSKRIBUS_PASSWORD`, the documented token endpoint on `account.readcoop.eu`, and its configured API hostname. No credentials are needed for development or automated tests.

## Review, ground truth and exports

```bash
python -m russian_ocr report --sample --output-dir /workspace/ocr-output
streamlit run russian_ocr/review_app.py --server.address 127.0.0.1 --server.headless true -- /workspace/ocr-output
```

Open generated HTML locally or use the local Streamlit review app. The HTML uses embedded images, scroll/zoom, exact escaped transcripts, disagreement highlights and expandable line/word coordinates. Highlighted disagreement does not mean unreadable text. Missing-region warnings are review candidates, not a claim of measured visual coverage. Toggle line boxes in the HTML report to review Azure (blue) and Transkribus (red) coordinates against the exact OCR working copy; original appearance remains the default. Coordinates are also available as structured data in the app. Static HTML can download a ground-truth draft; the review app saves locally and regenerates scores after human verification.

Output mirrors source folders under `pages/<folder>/<stem>-<stable-id>/`. Each successful provider has complete raw and normalized JSON, a Word file and receipt. Reports are `comparison.csv`, `comparison.json`, `comparison.md`, `benchmark_summary.html` and per-page `comparison.html`. Word documents include every returned transcript line and the OCR working image, with a separate low-provider-confidence review list. Files stay outside the source tree and are ignored by Git by default; use ignored `data/` when working inside the repository.

Ground-truth format (stored as each page's `ground_truth.json`):

```json
{
  "source_sha256": "the exact manifest checksum",
  "verified": true,
  "text": "Complete human-verified transcript, preserving original spelling."
}
```

To import references, name files `<page_id>.json` in a directory and run:

```bash
python -m russian_ocr evaluate --ground-truth /absolute/reference-directory --output-dir /workspace/ocr-output
```

CER/WER use Levenshtein alignment after collapsing whitespace only; case, punctuation, Cyrillic, names, dates and author mistakes are preserved. Reported insertions/deletions/substitutions are explicit. Text recovered is `100 * unchanged aligned reference characters / reference characters`; inserted characters are reported separately. Correct word counts and word recovery are also supplied. Empty references have undefined error rates. Unverified or wrong-checksum references stay unscored. Missing reference line candidates are reported from line alignment. To score crossed-out text, corrections, names or dates separately, add manually aligned verified annotations to ground_truth.json: each annotation has id, label, text, verified and provider_text (mapping provider names to the exact recognized passage). Only verified annotations are scored; their reference and provider text must be manually matched to the same source passage. The app preserves imported annotations when saving the full reference. No automatic interpretation of author deletions or corrections occurs.

## Restart and safety

Completed receipts are reused by source checksum, processed checksum/settings, provider, model/API and locale. `--resume` is supported; reuse is conservative by default even without it. An interrupted receipt has an ambiguous billable state and blocks resubmission. Inspect it before deliberately using `--force`. Existing OCR artifacts are archived before forced submissions. Do not use `--force` as a routine recovery step. Process one page/provider at a time. Azure SDK handles bounded HTTP retries and polling; whole-document submissions are never retried by the pipeline after ambiguous failure. Failures are isolated per page and return a nonzero exit code; logged errors exclude request bodies and credentials. Atomic writes prevent half-written reports or results. Changed source and processed hashes are rejected.

## Documentation verified on 2026-10-12

- [Azure SDK 1.0.2 reference](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-documentintelligence-readme): official local-stream `begin_analyze_document(model_id, body=stream)` and API `2024-11-30`; also checked the installed SDK signature.
- [Azure language support](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr): multilingual auto-detection and optional locale; do not assume forced locale improves accuracy.
- [Transkribus authentication](https://docs.transkribus.org/start/auth): OpenID Connect password/refresh grants with client ID `processing-api-client`, Scholar plan or above.
- [First job](https://docs.transkribus.org/start/first-job), [recognition](https://docs.transkribus.org/processing/text-recognition), [job lifecycle](https://docs.transkribus.org/processing/how-jobs-work): configured API currently documented at `https://api-staging.transkribus.org`; `/v2/processes`, `config.textRecognition.htrId`, one image up to 20 MB, statuses CREATED/WAITING/RUNNING/FINISHED/FAILED/CANCELLED, inline/ZIP/PAGE XML outputs and 24-hour result retention.
- Exact base64 and result schemas in the linked API reference remain inaccessible (proxy 403). Implementing the Transkribus HTTP adapter, token refresh, bounded polling, immediate ZIP/PAGE persistence and mocked job tests remains required. Model `148545` accessibility cannot be verified without authenticated API access. No substitution is allowed.

See `TEST_REPORT.md` for current validation and remaining acceptance gaps. This is tested pilot infrastructure, not a completed real two-provider benchmark.
