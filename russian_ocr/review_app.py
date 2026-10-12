"""Run with streamlit run russian_ocr/review_app.py -- /absolute/output."""
from pathlib import Path
import sys
import streamlit as st
from russian_ocr.storage import read_json, write_json, page_dir
from russian_ocr.reporting import generate


def main() -> None:
    st.set_page_config(layout="wide")
    st.title("Russian handwriting pilot review")
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "data/output").resolve()
    if not (output / "reports" / "sample.json").exists():
        st.info("No pilot sample yet. Run inventory, sample and preprocess; then reopen the review app with the output directory.")
        return
    sample = read_json(output / "reports" / "sample.json")["pages"]
    by_path = {p["relative_path"]: p for p in sample}
    selected = st.selectbox("Source page", list(by_path))
    page = by_path[selected]
    directory = page_dir(output, page)
    columns = st.columns(3)
    with columns[0]:
        st.caption("Original appearance with verified reading orientation; coordinates refer to the separate OCR working copy")
        zoom = st.slider("Image width (pixels)", 300, 2000, 700)
        image = directory / "image_reference.png"
        st.image(str(image if image.exists() else directory / "image_processed.png"), width=zoom)
    for column, provider in zip(columns[1:], ("azure", "transkribus")):
        with column:
            st.subheader(provider)
            path = directory / f"{provider}_normalized.json"
            if path.exists():
                document = read_json(path)
                st.text(document["text"])
                with st.expander("Coordinates and confidence"):
                    st.json(document["lines"])
            else:
                st.info("No provider result")
    truth_path = directory / "ground_truth.json"
    truth = read_json(truth_path) if truth_path.exists() else {}
    text = st.text_area("Reference transcription; preserve spelling, punctuation and author errors", truth.get("text", ""), height=300, key=page["id"])
    verified = st.checkbox("I have checked the full reference against the scan", value=truth.get("verified", False), key=page["id"] + "verified")
    st.caption("Scores require this human verification. Ground truth is bound to the source checksum.")
    if st.button("Save reference and regenerate reports"):
        write_json(truth_path, {**truth, "text": text, "verified": verified, "source_sha256": page["sha256"]})
        rows = generate(output, sample)
        st.success("Saved locally")
        st.json(next((row["scores"] for row in rows if row["page_id"] == page["id"]), {}))


if __name__ == "__main__":
    main()
