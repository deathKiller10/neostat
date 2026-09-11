"""Rule-based, explainable confidence scoring -- never LLM-generated. A field's
confidence is source_confidence * grounding_multiplier, optionally reduced further by
document_service if the field turns out to be an operand in a failing financial check.

source_confidence: 0.99 for a native PDF text layer (effectively no OCR error), or the
Tesseract word confidence for the OCR token that matches the value, falling back to the
page's overall mean OCR confidence when no single token matches (this happens when an
amount is split across tokens, e.g. a currency symbol in its own token).

grounding_multiplier: 1.0 when the value is found in the page's source text, 0.35
when it can't be found at all -- a strong signal the LLM may have hallucinated it.
"""

from backend.app.services.extraction_service import PreparedPage
from backend.app.utils.numbers import parse_number, value_grounded_in_text

GROUNDED_MULTIPLIER = 1.0
UNGROUNDED_MULTIPLIER = 0.35
VALIDATION_FAIL_PENALTY = 0.85
NUMERIC_MATCH_TOLERANCE_RATIO = 0.001


def _match_ocr_word_confidence(value: float, words) -> float | None:
    tolerance = max(0.01, abs(value) * NUMERIC_MATCH_TOLERANCE_RATIO)
    for word in words:
        parsed = parse_number(word.text)
        if parsed is not None and abs(parsed - value) <= tolerance:
            return word.confidence
    return None


def numeric_field_confidence(value: float | None, page: PreparedPage) -> tuple[float, bool | None]:
    if value is None:
        return 0.0, None

    grounded = value_grounded_in_text(value, page.text)

    if page.text_source == "native_text":
        source_confidence = 0.99
    else:
        source_confidence = _match_ocr_word_confidence(value, page.ocr_words)
        if source_confidence is None:
            source_confidence = page.ocr_mean_confidence or 0.0

    multiplier = GROUNDED_MULTIPLIER if grounded else UNGROUNDED_MULTIPLIER
    return round(source_confidence * multiplier, 4), grounded


def text_field_confidence(value: str | None, page: PreparedPage) -> float:
    if value is None:
        return 0.0
    return 0.99 if page.text_source == "native_text" else round(page.ocr_mean_confidence or 0.0, 4)


def compute_overall_confidence(field_confidences: dict[str, float], key_fields: set[str]) -> float:
    if not field_confidences:
        return 0.0
    weighted_sum = 0.0
    total_weight = 0.0
    for name, conf in field_confidences.items():
        weight = 2.0 if name in key_fields else 1.0
        weighted_sum += weight * conf
        total_weight += weight
    return round(weighted_sum / total_weight, 4) if total_weight else 0.0
