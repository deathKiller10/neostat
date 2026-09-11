"""Runs the financial arithmetic checks from the assignment spec against extracted
data. Line items are matched to formula operands by normalized label + a synonym map,
not by row position, because LLM output doesn't guarantee row order matches any fixed
schema. Every check that can't find one of its operands returns NOT_APPLICABLE rather
than guessing a zero -- a missing figure is not the same as a zero figure.
"""

import re

_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")

LABEL_SYNONYMS: dict[str, list[str]] = {
    "total_assets": ["total assets", "total"],
    "total_capital_and_liabilities": ["total capital and liabilities", "total"],
    "interest_earned": ["interest earned"],
    "other_income": ["other income"],
    "total_income": ["total income"],
    "interest_expended": ["interest expended"],
    "operating_expenses": ["operating expenses"],
    "provisions_and_contingencies": ["provisions and contingencies", "provisions contingencies"],
    "total_expenditure": ["total expenditure"],
    "net_profit_before_minority_interest": [
        "consolidated net profit before minority interest",
        "net profit before minority interest",
        "profit before minority interest",
    ],
    "minority_interest": ["minority interest", "less minority interest"],
    "net_profit_attributable_to_group": [
        "net profit attributable to the group",
        "net profit attributable to group",
        "consolidated profit attributable to group",
    ],
    "current_profit": ["profit for the year", "net profit for the year"],
    "brought_forward_profit": [
        "balance brought forward",
        "brought forward from previous year",
        "profit brought forward from previous year",
    ],
    "total_available_for_appropriation": ["total available for appropriation", "amount available for appropriation"],
    "operating_activities": [
        "net cash flow used in from operating activities",
        "net cash generated from operating activities",
        "cash flow from operating activities",
        "net cash used in operating activities",
    ],
    "investing_activities": ["investing activities"],
    "financing_activities": ["financing activities"],
    "fx_adjustment": ["effect of exchange fluctuation", "foreign exchange translation", "exchange fluctuation"],
    "net_increase_in_cash": [
        "net increase decrease in cash and cash equivalents",
        "net increase in cash and cash equivalents",
        "net increase decrease in cash",
    ],
    "opening_cash": [
        "cash and cash equivalents at the beginning",
        "cash and bank balances at beginning of the year",
    ],
    "cash_acquired_on_amalgamation": ["cash acquired on amalgamation"],
    "closing_cash": [
        "cash and cash equivalents at the end",
        "cash and bank balances at end of the year",
    ],
}


def normalize_label(label: str | None) -> str:
    if not label:
        return ""
    label = label.lower()
    label = _PUNCTUATION_RE.sub(" ", label)
    return _WHITESPACE_RE.sub(" ", label).strip()


def find_line_item_value(
    line_items: list[dict], period: str, candidates: list[str], section_contains: str | None = None
) -> tuple[float | None, str | None]:
    """An exact normalized-label match always wins over a substring match, so a row
    like "Minority interest" isn't shadowed by a longer row that happens to contain
    the same phrase, e.g. "...profit before minority interest". Among substring
    matches (no exact label match found), the shortest label wins as the closest fit.
    """
    exact_item = None
    best_partial_item = None
    best_partial_len: int | None = None
    for item in line_items:
        if section_contains and section_contains not in normalize_label(item.get("section")):
            continue
        label_norm = normalize_label(item.get("label"))
        if label_norm in candidates:
            exact_item = item
            continue
        for candidate in candidates:
            if candidate in label_norm and (best_partial_len is None or len(label_norm) < best_partial_len):
                best_partial_item = item
                best_partial_len = len(label_norm)

    best_item = exact_item or best_partial_item
    if best_item is None:
        return None, None
    period_field = best_item.get("values", {}).get(period)
    value = period_field.get("value") if period_field else None
    return value, best_item.get("label")


def sum_section_components(
    line_items: list[dict], period: str, section_contains: str, exclude_labels: set[str] | None = None
) -> dict[str, float]:
    exclude_labels = exclude_labels or {"total"}
    components: dict[str, float] = {}
    for item in line_items:
        if section_contains not in normalize_label(item.get("section")):
            continue
        if normalize_label(item.get("label")) in exclude_labels:
            continue
        period_field = item.get("values", {}).get(period)
        value = period_field.get("value") if period_field else None
        if value is not None:
            components[item["label"]] = value
    return components


def evaluate_check(name, formula, operands, calc_fn, reported_value, abs_tol, rel_tol) -> dict:
    if reported_value is None or not operands or any(v is None for v in operands.values()):
        return {
            "name": name,
            "formula": formula,
            "operands": operands,
            "calculated_value": None,
            "reported_value": reported_value,
            "variance": None,
            "status": "NOT_APPLICABLE",
        }
    calculated = calc_fn(operands)
    variance = round(calculated - reported_value, 2)
    tolerance = max(abs_tol, rel_tol * abs(reported_value))
    status = "PASS" if abs(variance) <= tolerance else "FAIL"
    return {
        "name": name,
        "formula": formula,
        "operands": operands,
        "calculated_value": round(calculated, 2),
        "reported_value": round(reported_value, 2),
        "variance": variance,
        "status": status,
    }


def get_field_value(extracted_data: dict, key: str) -> float | None:
    field = extracted_data.get(key)
    return field.get("value") if field else None
