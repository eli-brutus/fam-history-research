import os
import time
from pathlib import Path
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from ..models import OCRDocument, OCRLine, OCRWord


def normalize(raw: dict, page: dict, processed: dict, duration: float, model: str, api_version: str) -> OCRDocument:
    lines = []
    for page_index, provider_page in enumerate(raw.get("pages", [])):
        words = provider_page.get("words", [])
        for line_index, line in enumerate(provider_page.get("lines", [])):
            spans = line.get("spans", [])
            included = [word for word in words if any(s["offset"] <= word.get("span", {}).get("offset", -1)
                       and word.get("span", {}).get("offset", -1) + word.get("span", {}).get("length", 0) <= s["offset"] + s["length"] for s in spans)]
            lines.append(OCRLine(f"p{page_index+1}-l{line_index+1}", f"p{page_index+1}", len(lines), line.get("content", ""),
                         line.get("polygon", []), line.get("confidence"),
                         [OCRWord(w.get("content", ""), w.get("polygon", []), w.get("confidence"), {"span": w.get("span")}) for w in included]))
    return OCRDocument(page["relative_path"], page["sha256"], "azure", model,
                       raw.get("content", ""), lines, page, processed,
                       {"duration_seconds": duration, "status": "succeeded", "api_version": api_version},
                       "azure_raw.json", {"languages": raw.get("languages", []), "pages": raw.get("pages", []),
                                          "styles": raw.get("styles", [])})


class AzureOCRProvider:
    name = "azure"

    def __init__(self, locale: str | None = None):
        endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") or os.environ.get("OCR_AZURE_ENDPOINT")
        key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY") or os.environ.get("OCR_AZURE_KEY")
        if not endpoint or not key:
            raise ValueError("Azure endpoint and key are required; configure them securely in .env or environment settings")
        self.model = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_MODEL", "prebuilt-read")
        self.api_version = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_API_VERSION", "2024-11-30")
        self.locale = locale
        self.client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key), api_version=self.api_version,
                                                  retry_total=3, connection_timeout=30, read_timeout=60)

    def recognize(self, image: Path, page: dict, processed: dict) -> tuple[OCRDocument, dict]:
        start = time.monotonic()
        with image.open("rb") as stream:
            poller = self.client.begin_analyze_document(self.model, body=stream, locale=self.locale,
                                                        content_type="application/octet-stream")
        # Do not retry the entire submission after ambiguous failure: it may incur charges.
        result = poller.result(timeout=600)
        raw = result.as_dict()
        document = normalize(raw, page, processed, time.monotonic() - start, self.model, self.api_version)
        document.processing["locale"] = self.locale
        return document, raw
