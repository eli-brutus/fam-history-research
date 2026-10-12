from pathlib import Path
import base64
import csv
import html
import io
import json
from .alignment import compare
from .metrics import evaluate
from .storage import read_json, write_json, atomic_write, page_dir, digest
from .docx_export import export


def generate(output: Path, pages: list[dict]) -> list[dict]:
    rows = []
    links = []
    for page in pages:
        directory = page_dir(output, page)
        documents = {provider: read_json(directory / f"{provider}_normalized.json")
                     for provider in ("azure", "transkribus") if (directory / f"{provider}_normalized.json").exists()}
        if not documents:
            continue
        texts = {provider: doc["text"] for provider, doc in documents.items()}
        comparison = compare(texts.get("azure", ""), texts.get("transkribus", ""))
        comparison["missing_results"] = [p for p in ("azure", "transkribus") if p not in documents]
        ground_path = directory / "ground_truth.json"
        truth = read_json(ground_path) if ground_path.exists() else None
        verified = truth is not None and truth.get("verified") is True and truth.get("source_sha256") == page["sha256"]
        scores = {provider: evaluate(truth["text"], text) for provider, text in texts.items()} if verified else {}
        annotation_scores = []
        if verified:
            for annotation in truth.get("annotations", []):
                if annotation.get("verified") is True:
                    annotation_scores.append({"label": annotation["label"], "id": annotation["id"],
                                              "scores": {provider: evaluate(annotation["text"], transcript)
                                                         for provider, transcript in annotation.get("provider_text", {}).items()
                                                         if provider in documents}})
        row = {"relative_path": page["relative_path"], "page_id": page["id"], "comparison": comparison, "scores": scores,
               "scored": verified, "durations": {p: d["processing"].get("duration_seconds") for p, d in documents.items()},
               "cost_estimates": {p: d["processing"].get("cost_estimate") for p, d in documents.items()},
               "annotation_scores": annotation_scores,
               "cost_note": "Estimates require explicit current provider/account price per submitted page; charges are not inferred from transcript length."}
        rows.append(row)
        image_path = directory / "image_processed.png"
        for provider, document in documents.items():
            if document["processed_image"].get("sha256") != digest(image_path):
                raise ValueError("OCR result belongs to a different processed image; rerun or restore its working copy before reporting")
        reference_path = directory / "image_reference.png"
        image = base64.b64encode((reference_path if reference_path.exists() else image_path).read_bytes()).decode()
        working_image = base64.b64encode(image_path.read_bytes()).decode()
        width = next(iter(documents.values()))["processed_image"]["width"]
        height = next(iter(documents.values()))["processed_image"]["height"]
        polygons = []
        for provider, document in documents.items():
            for line in document["lines"]:
                coordinates = line.get("polygon", [])
                if coordinates and len(coordinates) % 2 == 0:
                    points = " ".join(f"{float(coordinates[i])},{float(coordinates[i+1])}" for i in range(0, len(coordinates), 2))
                    polygons.append(f'<polygon points="{points}" fill="none" stroke="{"#1261a0" if provider == "azure" else "#a03030"}" stroke-width="2"><title>{html.escape(provider + ": " + line["text"])}</title></polygon>')
        transcript_columns = []
        for provider in ("azure", "transkribus"):
            text = texts.get(provider, "No provider result available")
            other = "transkribus" if provider == "azure" else "azure"
            disagreed = set()
            if other in texts:
                for difference in comparison["differences"]:
                    disagreed.update(difference[provider])
            # Preserve exact whitespace and original text, adding visual review marks only.
            import re
            rendered = "".join(f"<mark>{html.escape(token)}</mark>" if token in disagreed else html.escape(token)
                               for token in re.split(r"(\s+)", text))
            coordinates = json.dumps(documents.get(provider, {}).get("lines", []), ensure_ascii=False, indent=2)
            score = html.escape(json.dumps(scores.get(provider), ensure_ascii=False)) if verified else "Unscored: human-verified reference required"
            transcript_columns.append(f"<section><h2>{provider}</h2><p>{score}</p><pre>{rendered}</pre><details><summary>Coordinates and confidence</summary><pre>{html.escape(coordinates)}</pre></details></section>")
            if provider in documents:
                export(documents[provider], image_path, directory / f"{provider}.docx")
        body = f"""<!doctype html><meta charset="utf-8"><title>{html.escape(page['relative_path'])}</title>
<style>body{{font-family:system-ui}}.columns{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1em}}section{{min-width:0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.scan{{height:75vh;overflow:auto}}img{{width:100%;display:block}}mark{{background:#fff0a0}}#zoom-wrap{{position:relative}}#boxes{{position:absolute;inset:0;width:100%;height:100%;display:none}}</style>
<h1>{html.escape(page['relative_path'])}</h1><p>Source SHA-256: {page['sha256']}</p>
<p>Scan preview preserves original appearance and applies only EXIF and chosen reading rotation (falls back to OCR copy for older outputs). Confirm orientation before paid calls. Coordinates refer to the OCR working image, available as image_processed.png. Highlighted words disagree; they are not necessarily errors.</p>
<div class="columns"><section><label>Zoom <input id="zoom" type="range" min="50" max="400" value="100"></label><label><input id="overlay" type="checkbox"> Show OCR working image and line boxes (Azure blue, Transkribus red)</label><div class="scan"><div id="zoom-wrap"><img id="scan" src="data:image/png;base64,{image}"><svg id="boxes" viewBox="0 0 {width} {height}" preserveAspectRatio="none">{''.join(polygons)}</svg></div></div></section>{''.join(transcript_columns)}</div>
<h2>Coverage and review</h2><pre>{html.escape(json.dumps(comparison, ensure_ascii=False, indent=2))}</pre>
<p>For persisted verified ground truth, use the local review app. This static report downloads a draft for manual import; no accuracy is claimed.</p>
<textarea id="truth" rows="12" style="width:100%">{html.escape(truth['text'] if truth else '')}</textarea><button id="download">Download ground-truth draft</button>
<script id="page-meta" type="application/json">{json.dumps({'source_sha256': page['sha256']})}</script>
<script>document.getElementById('zoom').oninput=e=>document.getElementById('zoom-wrap').style.width=e.target.value+'%';document.getElementById('overlay').onchange=e=>{{document.getElementById('scan').src='data:image/png;base64,'+(e.target.checked?'{working_image}':'{image}');document.getElementById('boxes').style.display=e.target.checked?'block':'none';}};document.getElementById('download').onclick=()=>{{const meta=JSON.parse(document.getElementById('page-meta').textContent);const data={{...meta,text:document.getElementById('truth').value,verified:false}};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{{type:'application/json'}}));const a=document.createElement('a');a.href=url;a.download='ground_truth.json';a.click();URL.revokeObjectURL(url);}};</script>"""
        atomic_write(directory / "comparison.html", body)
        href = "../" + (directory / "comparison.html").relative_to(output).as_posix()
        from urllib.parse import quote
        links.append(f'<li><a href="{html.escape(quote(href))}">{html.escape(page["relative_path"])}</a> — {"scored" if verified else "unscored"}</li>')
        write_json(directory / "comparison.json", row)
    write_json(output / "reports" / "comparison.json", rows)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["relative_path", "provider", "CER", "WER", "text_recovered_percent", "duration_seconds", "scored"])
    for row in rows:
        for provider in row["durations"]:
            score = row["scores"].get(provider, {})
            # Avoid spreadsheet formula execution through manuscript filenames.
            name = row["relative_path"]
            if name.startswith(("=", "+", "-", "@")):
                name = "'" + name
            writer.writerow([name, provider, score.get("CER"), score.get("WER"), score.get("text_recovered_percent"), row["durations"][provider], row["scored"]])
    atomic_write(output / "reports" / "comparison.csv", buffer.getvalue())
    atomic_write(output / "reports" / "comparison.md", "# Pilot comparison\n\nAccuracy requires human-verified ground truth.\n\n" + "\n".join(f"- {r['relative_path']}: {'scored' if r['scored'] else 'unscored'}" for r in rows))
    atomic_write(output / "reports" / "benchmark_summary.html", '<!doctype html><meta charset="utf-8"><h1>Pilot comparison</h1><p>Accuracy requires human-verified ground truth; engine agreement is not accuracy. Missing regions require visual review.</p><ul>' + ''.join(links) + '</ul>')
    return rows
