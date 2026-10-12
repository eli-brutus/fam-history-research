"""Whitespace-normalized, case-sensitive edit metrics against verified references."""
from rapidfuzz.distance import Levenshtein


def whitespace(text: str) -> str:
    return " ".join(text.split())


def counts(reference, hypothesis) -> dict:
    operations = Levenshtein.editops(reference, hypothesis)
    inserted = sum(o.tag == "insert" for o in operations)
    deleted = sum(o.tag == "delete" for o in operations)
    substituted = sum(o.tag == "replace" for o in operations)
    correct = len(reference) - deleted - substituted
    return {"reference_count": len(reference), "insertions": inserted, "deletions": deleted,
            "substitutions": substituted, "correct": correct,
            "error_rate": (inserted + deleted + substituted) / len(reference) if reference else None,
            "recovered_percent": 100 * correct / len(reference) if reference else None}


def evaluate(reference: str, hypothesis: str) -> dict:
    ref, hyp = whitespace(reference), whitespace(hypothesis)
    chars, words = counts(ref, hyp), counts(ref.split(), hyp.split())
    from difflib import SequenceMatcher
    reference_lines, hypothesis_lines = reference.splitlines(), hypothesis.splitlines()
    missing_lines = [reference_lines[i:j] for tag, i, j, k, l in SequenceMatcher(None, reference_lines, hypothesis_lines, autojunk=False).get_opcodes() if tag == "delete"]
    return {"CER": chars["error_rate"], "WER": words["error_rate"], "characters": chars, "words": words,
            "missing_reference_line_candidates": missing_lines,
            "text_recovered_percent": chars["recovered_percent"],
            "definition": "100 * unchanged aligned reference characters / reference characters; insertions reported separately; normalized whitespace, case and punctuation preserved"}
