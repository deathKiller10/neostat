"""Merges the per-page raw LLM extractions (schemas/extraction.py) into the
extracted_data shape the API returns: every scalar becomes {value, confidence,
page_number, source_text, grounded}. Multi-page documents merge by taking the first
page that filled a given scalar field, and concatenating list fields (line items,
periods) across pages -- these sample documents are single-page, so in practice this
just formats one page's result, but the merge keeps multi-page inputs correct too.
"""

from pydantic import BaseModel

from backend.app.services.confidence import (
    compute_overall_confidence,
    numeric_field_confidence,
    text_field_confidence,
)
from backend.app.services.extraction_service import PreparedPage

INVOICE_STR_FIELDS = ["shop_name", "registration_number", "gst_id", "invoice_number", "invoice_date", "currency"]
INVOICE_NUM_FIELDS = [
    "subtotal",
    "tax_amount",
    "discount",
    "gst_taxable_amount",
    "gst_amount",
    "total_amount",
    "cash_paid",
    "change_given",
]
INVOICE_KEY_FIELDS = {"invoice_number", "total_amount"}

FINANCIAL_STR_FIELDS = ["statement_title", "entity_name", "period_end", "currency", "units"]
FINANCIAL_KEY_FIELDS = {"statement_title", "entity_name", "period_end"}

PageResults = list[tuple[PreparedPage, BaseModel]]


def _empty_field() -> dict:
    return {"value": None, "confidence": 0.0, "page_number": None, "source_text": None, "grounded": None}


def _first_str_field(name: str, page_results: PageResults) -> dict:
    for page, raw in page_results:
        field = getattr(raw, name)
        if field.value is not None:
            conf = text_field_confidence(field.value, page)
            return {
                "value": field.value,
                "confidence": conf,
                "page_number": page.page_number,
                "source_text": field.source_text,
                "grounded": None,
            }
    return _empty_field()


def _first_num_field(name: str, page_results: PageResults) -> dict:
    for page, raw in page_results:
        field = getattr(raw, name)
        if field.value is not None:
            conf, grounded = numeric_field_confidence(field.value, page)
            return {
                "value": field.value,
                "confidence": conf,
                "page_number": page.page_number,
                "source_text": field.source_text,
                "grounded": grounded,
            }
    return _empty_field()


def build_invoice_extracted_data(page_results: PageResults) -> tuple[dict, float]:
    extracted: dict = {}
    field_confidences: dict[str, float] = {}

    for name in INVOICE_STR_FIELDS:
        field = _first_str_field(name, page_results)
        extracted[name] = field
        if field["value"] is not None:
            field_confidences[name] = field["confidence"]

    for name in INVOICE_NUM_FIELDS:
        field = _first_num_field(name, page_results)
        extracted[name] = field
        if field["value"] is not None:
            field_confidences[name] = field["confidence"]

    is_incl = _empty_field()
    for page, raw in page_results:
        if raw.is_tax_inclusive.value is not None:
            conf = text_field_confidence(str(raw.is_tax_inclusive.value), page)
            is_incl = {
                "value": raw.is_tax_inclusive.value,
                "confidence": conf,
                "page_number": page.page_number,
                "source_text": raw.is_tax_inclusive.source_text,
                "grounded": None,
            }
            break
    extracted["is_tax_inclusive"] = is_incl

    line_items = []
    for page, raw in page_results:
        for item in raw.line_items:
            line_items.append(
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "amount": item.amount,
                    "page_number": page.page_number,
                    "source_text": item.source_text,
                }
            )
    extracted["line_items"] = line_items

    overall = compute_overall_confidence(field_confidences, INVOICE_KEY_FIELDS)
    return extracted, overall


def build_financial_extracted_data(page_results: PageResults) -> tuple[dict, float]:
    extracted: dict = {}
    field_confidences: dict[str, float] = {}

    for name in FINANCIAL_STR_FIELDS:
        field = _first_str_field(name, page_results)
        extracted[name] = field
        if field["value"] is not None:
            field_confidences[name] = field["confidence"]

    periods: list[str] = []
    for _, raw in page_results:
        for period in raw.periods:
            if period not in periods:
                periods.append(period)
    extracted["periods"] = periods

    line_items = []
    for page, raw in page_results:
        for item in raw.line_items:
            values = {}
            for period, value in item.values.items():
                if value is None:
                    values[period] = _empty_field()
                    continue
                conf, grounded = numeric_field_confidence(value, page)
                values[period] = {
                    "value": value,
                    "confidence": conf,
                    "page_number": page.page_number,
                    "source_text": item.source_text,
                    "grounded": grounded,
                }
                field_confidences[f"{item.label}:{period}"] = conf
            line_items.append(
                {
                    "label": item.label,
                    "section": item.section,
                    "values": values,
                    "page_number": page.page_number,
                    "source_text": item.source_text,
                }
            )
    extracted["line_items"] = line_items

    overall = compute_overall_confidence(field_confidences, FINANCIAL_KEY_FIELDS)
    return extracted, overall
