"""PAGE XML normalization preserves raw XML separately; no inferred confidence."""
from lxml import etree
from .models import OCRDocument, OCRLine, OCRWord


def page_xml(xml: bytes, page: dict, processed: dict, model: str, duration: float, job_id: str) -> OCRDocument:
    root = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    if root.getroottree().docinfo.doctype:
        raise ValueError("DOCTYPE is not permitted in PAGE XML")
    namespace = etree.QName(root).namespace
    if not namespace or "pagecontent" not in namespace or etree.QName(root).localname != "PcGts":
        raise ValueError("Result is not PAGE XML")
    ns = {"p": namespace}

    def text(element):
        equivalents = element.findall("p:TextEquiv", ns)
        equivalent = min(equivalents, key=lambda e: int(e.get("index", "0"))) if equivalents else None
        if equivalent is None:
            return "", None
        content = equivalent.find("p:Unicode", ns)
        confidence = equivalent.get("conf")
        return (content.text or "") if content is not None else "", float(confidence) if confidence is not None else None

    def polygon(element):
        coords = element.find("p:Coords", ns)
        if coords is None:
            return []
        return [float(value) for point in coords.get("points", "").split() for value in point.split(",")]

    references = root.findall(".//p:ReadingOrder//p:RegionRefIndexed", ns)
    order = {r.get("regionRef"): int(r.get("index", "0")) for r in references}
    regions = root.findall(".//p:TextRegion", ns)
    regions.sort(key=lambda r: order.get(r.get("id"), len(order)))
    lines = []
    region_metadata = []
    for region in regions:
        region_id = region.get("id", f"r{len(region_metadata)}")
        region_metadata.append({"region_id": region_id, "polygon": polygon(region), "custom": region.get("custom")})
        for line in region.findall("p:TextLine", ns):
            content, confidence = text(line)
            words = []
            for word in line.findall("p:Word", ns):
                word_text, word_conf = text(word)
                words.append(OCRWord(word_text, polygon(word), word_conf, {"id": word.get("id")}))
            lines.append(OCRLine(line.get("id", f"l{len(lines)}"), region_id, len(lines), content, polygon(line), confidence, words))
    return OCRDocument(page["relative_path"], page["sha256"], "transkribus", model, "\n".join(line.text for line in lines),
                       lines, page, processed, {"duration_seconds": duration, "job_id": job_id, "status": "FINISHED"},
                       "transkribus_raw.json", {"regions": region_metadata, "page_xml": "transkribus_page.xml"})
