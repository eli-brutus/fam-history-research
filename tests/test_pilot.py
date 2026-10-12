import io
import json
from pathlib import Path
import zipfile
import pytest
from PIL import Image
from docx import Document
from russian_ocr.inventory import inventory, extract_zip
from russian_ocr.sampling import select, save_sample
from russian_ocr.preprocessing import preprocess, Settings
from russian_ocr.storage import page_dir, write_json, read_json, digest
from russian_ocr.providers.azure import normalize
from russian_ocr.metrics import evaluate
from russian_ocr.alignment import compare
from russian_ocr.cli import benchmark
from russian_ocr.reporting import generate


def image_bytes(color="white"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def pilot(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    for folder, name, color in [("Мемуары", "стр.1.png", "white"), ("Дневник", "стр.2.png", "blue"), ("Мемуары", "копия.png", "white")]:
        file = source / folder / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(image_bytes(color))
    manifest = inventory(source, output)
    pages = save_sample(manifest, output, 12)
    for page in pages:
        preprocess(source / page["relative_path"], page_dir(output, page) / "image_processed.png", Settings())
    return source, output, manifest, pages


def test_inventory_unicode_duplicates_source_unchanged(pilot):
    source, output, manifest, pages = pilot
    assert manifest["unique_pages"] == 2
    assert len(manifest["pages"]) == 3
    assert sum(p["duplicate_of"] is not None for p in manifest["pages"]) == 1
    assert all(digest(source / p["relative_path"]) == p["sha256"] for p in manifest["pages"])
    assert any("Мемуары" in p["relative_path"] for p in pages)
    assert all(p["confirmed_page_number"] is None for p in pages)


@pytest.mark.parametrize("name", ["../evil.png", "/evil.png", "a/../../evil.png", "C:/evil.png", "a\\evil.png"])
def test_zip_traversal_rejected_before_writes(tmp_path, name):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("good.png", image_bytes())
        z.writestr(name, image_bytes())
    with pytest.raises(ValueError):
        extract_zip(archive, tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_zip_preserves_folders_and_duplicates(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("Мемуары/лист.png", image_bytes())
        z.writestr("Дневник/копия.png", image_bytes())
    result = inventory(archive, tmp_path / "output")
    assert result["unique_pages"] == 1
    assert len(result["pages"]) == 2
    assert Path(result["root"], "Мемуары/лист.png").exists()
    assert inventory(archive, tmp_path / "output")["pages"] == result["pages"]


def test_zip_size_limit(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("x.png", image_bytes())
    with pytest.raises(ValueError, match="size limit"):
        extract_zip(archive, tmp_path / "out", max_bytes=1)


def test_output_inside_source_rejected(pilot):
    source, _, _, _ = pilot
    with pytest.raises(ValueError):
        inventory(source, source / "results")


def test_deterministic_sampling_across_folders(pilot):
    _, _, manifest, pages = pilot
    assert select(manifest, 12) == select({**manifest, "pages": list(reversed(manifest["pages"]))}, 12)
    assert len({p["folder"] for p in pages}) == 2
    path = pages[0]["relative_path"]
    assert select(manifest, paths=[path]) == [pages[0]]
    with pytest.raises(ValueError):
        select(manifest, paths=["missing.png"])


def test_exif_orientation_and_manual_rotation(tmp_path):
    source = tmp_path / "source.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (40, 60)).save(source, exif=exif)
    checksum = digest(source)
    meta = preprocess(source, tmp_path / "out.png", Settings())
    assert (meta["width"], meta["height"]) == (60, 40)
    rotated = preprocess(source, tmp_path / "rotated.png", Settings(rotation=90))
    assert (rotated["width"], rotated["height"]) == (40, 60)
    assert digest(source) == checksum


def test_aspect_ratio_does_not_rotate(pilot):
    _, output, _, pages = pilot
    metadata = read_json(page_dir(output, pages[0]) / "image_processed.json")
    assert (metadata["width"], metadata["height"]) == (40, 60)


@pytest.mark.parametrize("settings", [Settings(rotation=45), Settings(scale=0), Settings(deskew_degrees=90), Settings(contrast=-1)])
def test_invalid_preprocessing(pilot, settings):
    source, output, _, pages = pilot
    with pytest.raises(ValueError):
        preprocess(source / pages[0]["relative_path"], output / "x.png", settings)


def test_azure_normalization_preserves_raw_words_languages(pilot):
    _, output, _, pages = pilot
    page = pages[0]
    metadata = read_json(page_dir(output, page) / "image_processed.json")
    raw = {"content": "Иван", "languages": [{"locale": "ru", "confidence": .9}],
           "pages": [{"pageNumber": 1, "lines": [{"content": "Иван", "polygon": [0, 0, 20, 0, 20, 10, 0, 10], "spans": [{"offset": 0, "length": 4}]}],
                      "words": [{"content": "Иван", "confidence": .7, "span": {"offset": 0, "length": 4}, "polygon": [0, 0, 10, 10]}]}]}
    document = normalize(raw, page, metadata, 1, "prebuilt-read", "2024-11-30").to_dict()
    assert document["text"] == "Иван"
    assert document["lines"][0]["words"][0]["confidence"] == .7
    assert document["lines"][0]["confidence"] is None
    assert document["metadata"]["languages"] == raw["languages"]
    assert raw["pages"][0]["words"][0]["content"] == "Иван"


def test_empty_azure_response(pilot):
    _, _, _, pages = pilot
    document = normalize({}, pages[0], {}, 1, "prebuilt-read", "2024-11-30")
    assert document.text == "" and document.lines == []
    assert compare("", "") ["warnings"]


def test_metrics_known_edits_and_no_invented_score():
    assert evaluate("Иван  жил\nздесь", "Иван жил здесь")["CER"] == 0
    assert evaluate("кот", "кит")["characters"]["substitutions"] == 1
    assert evaluate("a b", "a")["words"]["deletions"] == 1
    assert evaluate("a", "a b")["words"]["insertions"] == 1
    assert evaluate("", "a")["CER"] is None
    assert evaluate("кот", "") ["text_recovered_percent"] == 0
    assert compare("Иван", "Иван")["scored"] is False


def test_alignment_duplicates_and_disagreement():
    result = compare("Иван\nИван\nжил здесь", "Иван\nжил там")
    assert result["differences"]
    assert result["suspected_duplicate_lines"]["azure"] == ["Иван"]
    assert result["line_alignment"]


def test_dry_run_never_constructs_provider(pilot, monkeypatch):
    from russian_ocr.providers import azure
    monkeypatch.setattr(azure, "AzureOCRProvider", lambda *a: pytest.fail("No provider allowed during dry run"))
    _, output, _, pages = pilot
    result = benchmark(output, ["azure", "transkribus"], 1, True, True, False, False, None)
    assert result["planned_document_submissions"] == 2
    assert result["pages"] == 1
    assert not list(output.rglob("*_receipt.json"))


def test_paid_execution_cache_report_docx_and_ground_truth(pilot, monkeypatch):
    from russian_ocr.providers import azure
    _, output, _, pages = pilot
    calls = []
    monkeypatch.setenv("OCR_AZURE_COST_PER_PAGE", "0.01")
    monkeypatch.setenv("OCR_COST_CURRENCY", "USD")

    class MockProvider:
        def __init__(self, locale):
            pass
        def recognize(self, image, page, metadata):
            calls.append(digest(image))
            raw = {"content": "Иван жил здесь.\nВесь текст.", "pages": []}
            return normalize(raw, page, metadata, .1, "prebuilt-read", "2024-11-30"), raw

    monkeypatch.setattr(azure, "AzureOCRProvider", MockProvider)
    benchmark(output, ["azure"], 1, False, True, False, True, None)
    assert len(calls) == 1
    result = benchmark(output, ["azure"], 1, False, True, False, True, None)
    assert result["reused"] == 1 and len(calls) == 1
    directory = page_dir(output, pages[0])
    doc = Document(directory / "azure.docx")
    assert "Весь текст." in "\n".join(p.text for p in doc.paragraphs)
    assert (directory / "azure_raw.json").exists()
    assert "Unscored" in (directory / "comparison.html").read_text()
    assert read_json(output / "reports" / "comparison.json")[0]["scored"] is False
    assert read_json(output / "reports" / "comparison.json")[0]["cost_estimates"]["azure"]["amount"] == .01
    truth = {"text": "Иван жил здесь.\nВесь текст.", "verified": True, "source_sha256": pages[0]["sha256"]}
    write_json(directory / "ground_truth.json", truth)
    rows = generate(output, pages[:1])
    assert rows[0]["scores"]["azure"]["WER"] == 0
    truth["source_sha256"] = "wrong"
    write_json(directory / "ground_truth.json", truth)
    assert generate(output, pages[:1])[0]["scored"] is False
    benchmark(output, ["azure"], 1, False, False, True, True, None)
    assert len(calls) == 2
    assert len(list((directory / "history").rglob("azure_raw.json"))) == 1


def test_annotation_scoring_and_svg_boxes(pilot):
    _, output, _, pages = pilot
    page = pages[0]
    directory = page_dir(output, page)
    metadata = read_json(directory / "image_processed.json")
    raw = {"content": "кот", "pages": [{"lines": [{"content": "кот", "polygon": [0, 0, 30, 0, 30, 10, 0, 10]}]}]}
    document = normalize(raw, page, metadata, 1, "prebuilt-read", "2024-11-30").to_dict()
    write_json(directory / "azure_normalized.json", document)
    write_json(directory / "ground_truth.json", {"verified": True, "text": "кот", "source_sha256": page["sha256"],
               "annotations": [{"id": "crossed-1", "label": "crossed_out", "verified": True, "text": "кот", "provider_text": {"azure": "кит"}}]})
    rows = generate(output, pages[:1])
    assert rows[0]["annotation_scores"][0]["scores"]["azure"]["CER"] == pytest.approx(1/3)
    text = (directory / "comparison.html").read_text()
    assert '<polygon points="0.0,0.0 30.0,0.0 30.0,10.0 0.0,10.0"' in text


def test_interrupted_receipt_requires_force(pilot):
    _, output, _, pages = pilot
    write_json(page_dir(output, pages[0]) / "azure_receipt.json", {"status": "submitting"})
    with pytest.raises(ValueError, match="--force"):
        benchmark(output, ["azure"], 1, True, True, False, False, None)


def test_transkribus_preflight_prevents_any_paid_calls(pilot, monkeypatch):
    from russian_ocr.providers import azure
    monkeypatch.setattr(azure, "AzureOCRProvider", lambda *args: object())
    _, output, _, _ = pilot
    with pytest.raises(RuntimeError, match="API reference"):
        benchmark(output, ["azure", "transkribus"], 1, False, True, False, True, None)
    assert not list(output.rglob("*_receipt.json"))


def test_changed_processed_image_rejected(pilot):
    _, output, _, pages = pilot
    (page_dir(output, pages[0]) / "image_processed.png").write_bytes(image_bytes("red"))
    with pytest.raises(ValueError, match="metadata mismatch"):
        benchmark(output, ["azure"], 1, True, True, False, False, None)


def test_azure_sdk_local_bytes_call(pilot, monkeypatch):
    from russian_ocr.providers import azure
    _, output, _, pages = pilot
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://example.test")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "mock-key")
    seen = {}

    class Result:
        def as_dict(self):
            return {"content": "Иван", "pages": []}
    class Poller:
        def result(self, timeout):
            assert timeout == 600
            return Result()
    class Client:
        def __init__(self, endpoint, credential, **kwargs):
            assert kwargs["api_version"] == "2024-11-30"
        def begin_analyze_document(self, model, body, **kwargs):
            seen.update(model=model, data=body.read(), locale=kwargs["locale"])
            return Poller()
    monkeypatch.setattr(azure, "DocumentIntelligenceClient", Client)
    provider = azure.AzureOCRProvider()
    directory = page_dir(output, pages[0])
    document, raw = provider.recognize(directory / "image_processed.png", pages[0], read_json(directory / "image_processed.json"))
    assert seen["data"] == (directory / "image_processed.png").read_bytes()
    assert seen["model"] == "prebuilt-read" and seen["locale"] is None
    assert document.text == "Иван"


def test_preprocessing_preserves_old_versions_and_rejects_source_target(pilot):
    source, output, _, pages = pilot
    path = source / pages[0]["relative_path"]
    target = page_dir(output, pages[0]) / "image_processed.png"
    checksum = digest(target)
    preprocess(path, target, Settings(rotation=90))
    assert (target.parent / "image_versions" / f"{checksum}.png").exists()
    with pytest.raises(ValueError, match="source image"):
        preprocess(path, path, Settings())


def test_page_xml_normalization_and_entity_safety(pilot):
    from russian_ocr.normalization import page_xml
    _, _, _, pages = pilot
    xml = '''<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"><Page imageFilename="x.png" imageWidth="40" imageHeight="60"><TextRegion id="r1"><Coords points="0,0 40,0 40,60 0,60"/><TextLine id="l1"><Coords points="1,1 20,1 20,10 1,10"/><Word id="w1"><TextEquiv conf="0.7"><Unicode>Иван</Unicode></TextEquiv></Word><TextEquiv><Unicode>Иван жил здесь.</Unicode></TextEquiv></TextLine></TextRegion></Page></PcGts>'''.encode()
    result = page_xml(xml, pages[0], {}, "148545", 1, "job1").to_dict()
    assert result["text"] == "Иван жил здесь."
    assert result["lines"][0]["words"][0]["confidence"] == .7
    assert result["lines"][0]["confidence"] is None
    assert result["processing"]["job_id"] == "job1"
    malicious = b'<!DOCTYPE PcGts [<!ENTITY secret SYSTEM "file:///etc/passwd">]><PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"><Page>&secret;</Page></PcGts>'
    with pytest.raises(ValueError, match="DOCTYPE"):
        page_xml(malicious, pages[0], {}, "148545", 1, "job1")
