from difflib import SequenceMatcher
from collections import Counter
from .metrics import whitespace


def compare(left: str, right: str) -> dict:
    a, b = whitespace(left).split(), whitespace(right).split()
    differences = [{"kind": tag, "azure": a[i:j], "transkribus": b[k:l]}
                   for tag, i, j, k, l in SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if tag != "equal"]
    lines_a, lines_b = left.splitlines(), right.splitlines()
    line_alignment = [{"kind": tag, "azure": lines_a[i:j], "transkribus": lines_b[k:l]}
                      for tag, i, j, k, l in SequenceMatcher(None, lines_a, lines_b, autojunk=False).get_opcodes()]
    repeated = {name: [line for line, count in Counter(text.splitlines()).items() if line.strip() and count > 1]
                for name, text in (("azure", left), ("transkribus", right))}
    return {"scored": False, "differences": differences, "line_alignment": line_alignment,
            "suspected_duplicate_lines": repeated,
            "warnings": [f"{name}: empty transcription" for name, text in (("azure", left), ("transkribus", right)) if not text.strip()],
            "note": "Disagreements indicate review candidates; agreement does not measure accuracy. Coverage requires visual or ground-truth review."}
