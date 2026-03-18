"""Post-processing helpers for assistant response text."""

from __future__ import annotations

import re

OPEN_TO_CLOSE = {
    "「": "」",
    "『": "』",
    "【": "】",
    "(": ")",
    "（": "）",
    "[": "]",
    "［": "］",
}
CLOSE_TO_OPEN = {close: open_ for open_, close in OPEN_TO_CLOSE.items()}


def clean_assistant_response(text: str) -> str:
    """Remove obvious stray symbols without rewriting the content."""

    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"\s+([。！？!?、，．…])", r"\1", cleaned)
    cleaned = _trim_unmatched_edge_brackets(cleaned)
    cleaned = re.sub(r"[\[\]【】「」『』()（）［］]+([。！？!?…]+)$", r"\1", cleaned)
    cleaned = re.sub(r"([。！？!?])\1+", r"\1", cleaned)
    cleaned = re.sub(r"[、】【][、】【]+", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned or (text or "").strip()


def _trim_unmatched_edge_brackets(text: str) -> str:
    cleaned = text

    while cleaned:
        first = cleaned[0]
        if first in CLOSE_TO_OPEN:
            cleaned = cleaned[1:].lstrip()
            continue
        if first in OPEN_TO_CLOSE and cleaned.count(first) > cleaned.count(OPEN_TO_CLOSE[first]):
            cleaned = cleaned[1:].lstrip()
            continue
        break

    while cleaned:
        last = cleaned[-1]
        if last in OPEN_TO_CLOSE:
            cleaned = cleaned[:-1].rstrip()
            continue
        if last in CLOSE_TO_OPEN and cleaned.count(CLOSE_TO_OPEN[last]) < cleaned.count(last):
            cleaned = cleaned[:-1].rstrip()
            continue
        break

    return cleaned
