import re

_CURRENCY_TOKENS = ("₹", "`", "RM", "Rs.", "Rs", "MYR", "INR", "USD", "$", "€", "£")
_NIL_TOKENS = {"-", "–", "—", "--"}
_NUMBER_TOKEN_RE = re.compile(r"\(?-?[\d][\d,]*\.?\d*\)?")


def parse_number(raw) -> float | None:
    """Parses financial figures from these documents into a float, or None if the
    text isn't a number at all. Handles the formatting quirks specific to this
    dataset: brackets mean negative (HDFC statements show "(1,546.40)" for -1546.40),
    a bare dash means a nil balance (0.0, not missing), and the OCR text layer
    sometimes renders the rupee sign as a backtick.
    """
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return float(raw)

    text = str(raw).strip()
    if not text:
        return None

    for token in _CURRENCY_TOKENS:
        text = text.replace(token, "")
    text = text.strip()

    if text in _NIL_TOKENS:
        return 0.0

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    text = text.replace(",", "").strip()

    if text[:1] in ("-", "–", "—"):
        negative = True
        text = text[1:].strip()

    if not text or not re.fullmatch(r"\d+(\.\d+)?", text):
        return None

    value = float(text)
    return -value if negative else value


def extract_numbers_from_text(text: str) -> list[float]:
    """Pulls every numeric token out of raw OCR/text-layer text, parsed with the
    same bracket/comma rules as parse_number. Used by the grounding check to confirm
    an extracted value actually appears somewhere in the source.
    """
    values = []
    for match in _NUMBER_TOKEN_RE.finditer(text):
        parsed = parse_number(match.group())
        if parsed is not None:
            values.append(parsed)
    return values


def value_grounded_in_text(value: float, text: str, tolerance: float = 0.01) -> bool:
    return any(abs(candidate - value) <= tolerance for candidate in extract_numbers_from_text(text))
