"""Real Azure test requires separate explicit opt-in, credentials and a chosen scan."""
import os
from pathlib import Path
import pytest
from russian_ocr.providers.azure import AzureOCRProvider
from russian_ocr.storage import digest
from russian_ocr.preprocessing import preprocess, Settings


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_PAID_OCR_TESTS") != "1", reason="Paid integration test is explicitly disabled")
def test_real_azure_opt_in(tmp_path):
    source = Path(os.environ["OCR_INTEGRATION_IMAGE"])
    image = tmp_path / "working.png"
    metadata = preprocess(source, image, Settings())
    document, raw = AzureOCRProvider().recognize(image, {"relative_path": source.name, "sha256": digest(source)}, metadata)
    assert isinstance(raw, dict)
    assert document.processing["status"] == "succeeded"
    assert document.processing["api_version"] == "2024-11-30"
