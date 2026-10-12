# Validation report — 2026-10-12

Current command: `/workspace/ocr-venv/bin/python -m pytest -q`

**29 passed, 1 skipped.** No paid calls, authentication requests or manuscript uploads ran. The paid Azure integration test is disabled unless `RUN_PAID_OCR_TESTS=1` is explicitly supplied with credentials and `OCR_INTEGRATION_IMAGE`.

Verified:

- Safe ZIP extraction, size limits, path traversal rejection before writes, Cyrillic paths, content duplicates, folder provenance and repeated inventory.
- Deterministic sampling across folders, explicit selection, source integrity and null unverified page numbers.
- EXIF correction, manual rotation, absence of aspect-ratio rotation, settings validation, original protection and preservation of previous working image versions.
- Azure local-byte submission using a mocked official SDK client, raw content/word/language normalization, absent confidence and empty results.
- Standard PAGE XML line/word/region normalization and rejection of document entities.
- Whitespace-only normalization, known character/word edit counts, empty-reference behavior, unscored disagreements and duplicate-line review candidates.
- Dry-run without provider construction or API calls, page limits, complete mocked Azure output, cache reuse, forced-rerun archival, user-configured cost estimates, ambiguous receipt protection, changed-image rejection and preflight failure before any paid two-provider submission.
- HTML/CSV/JSON/Markdown generation, SVG line boxes, complete transcript content in DOCX, ground-truth source-checksum validation and separate manually aligned annotation scores.

Additional current-instance validation:

- Tested Python 3.12.14, dependency installation, editable package installation and `pip check`.
- Executed the saved reusable installation script successfully, including tests; final suite rerun after the image-version preservation change.
- Created a synthetic demonstration at `/workspace/ocr-demo/output`; generated both provider-labelled mock transcripts and Word files. These are fixtures, not actual OCR service responses.
- Used Streamlit AppTest to load the review UI, enter and verify a reference, save it, and confirm regenerated Azure WER of zero for the exact mock text.
- Started the Streamlit server, checked its internal health response and stopped it after validation. Processes are not assumed to survive publication.
- Executed CLI dry-run for one synthetic page, displaying two planned provider submissions with no paid calls.
- Verified official Azure SDK 1.0.2 documentation, API version and installed method signature; read official Azure language support documentation.
- Read current official Transkribus authentication, first-job, image, recognition and job lifecycle guides.

Remaining acceptance gaps:

1. The official linked Transkribus API reference at `api-staging.transkribus.org/docs` returns cloud proxy 403. The adapter remains intentionally unimplemented pending exact base64/result schema verification. Token refresh, retries, polling, job resumption, immediate ZIP/PAGE download, credits errors and mocked HTTP job tests still need implementation.
2. No real manuscript archive was provided; its manifest, representative sample and contact sheet cannot be generated. Existing demonstration artifacts are explicitly synthetic.
3. No API credentials are present. No real API calls or model-access verification succeeded or were attempted. No accuracy or 90% recovery claim is made.
4. HTML reports expose coordinates and line-box overlays, but coverage warnings are heuristic and require human review; automated visual detection of missed handwritten regions is not implemented. Correction/crossed-out scores require manually aligned verified annotations.
5. Cost estimates remain unknown until optional account-specific per-page pricing is supplied. Human review of difficult, dense, low-contrast and corrected pages is required before paid sampling.

Reusable install_script and start_skill were saved in the cloud configuration draft, together with documentation/authentication/API domain additions. Saving is not publication, and restoration in a new task has not been tested. Review and save environment settings, apply the needed API-reference network access, then publish when the required setup is complete.
