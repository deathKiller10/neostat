from backend.app.schemas.extraction import (
    FinancialLineItem,
    FinancialStatementExtraction,
    InvoiceExtraction,
    NumField,
    PeriodValue,
    StrField,
)
from backend.app.services.extraction_service import PreparedPage, extract


class MockLLM:
    def __init__(self, response):
        self.response = response

    def generate_structured(self, prompt, image, schema):
        return self.response


def _page(text: str, text_source: str = "native_text") -> PreparedPage:
    return PreparedPage(
        page_number=1,
        image=None,
        text=text,
        text_source=text_source,
        ocr_mean_confidence=0.9 if text_source == "rendered_ocr" else None,
        ocr_words=[],
    )


def test_invoice_schema_accepts_nulls_for_missing_fields():
    extraction = InvoiceExtraction()
    assert extraction.invoice_number.value is None
    assert extraction.line_items == []


def test_financial_schema_preserves_comparative_periods():
    extraction = FinancialStatementExtraction(
        periods=["March 31, 2024", "March 31, 2023"],
        line_items=[
            FinancialLineItem(
                label="Total Assets",
                values=[
                    PeriodValue(period="March 31, 2024", value=100.0),
                    PeriodValue(period="March 31, 2023", value=90.0),
                ],
            )
        ],
    )
    values_by_period = {pv.period: pv.value for pv in extraction.line_items[0].values}
    assert values_by_period["March 31, 2024"] == 100.0
    assert values_by_period["March 31, 2023"] == 90.0


def test_grounded_value_gets_high_confidence_and_grounded_true():
    page = _page("Total Amount Due: USD 13,125.00", text_source="native_text")
    response = InvoiceExtraction(total_amount=NumField(value=13125.00, source_text="Total Amount Due: USD 13,125.00"))
    extracted, _ = extract([page], "invoice", MockLLM(response))
    assert extracted["total_amount"]["grounded"] is True
    assert extracted["total_amount"]["confidence"] > 0.9


def test_ungrounded_value_is_flagged_and_confidence_drops():
    page = _page("Total Amount Due: USD 13,125.00", text_source="native_text")
    response = InvoiceExtraction(total_amount=NumField(value=99999.99, source_text="hallucinated"))
    extracted, _ = extract([page], "invoice", MockLLM(response))
    assert extracted["total_amount"]["grounded"] is False
    assert extracted["total_amount"]["confidence"] < 0.5


def test_missing_value_has_null_and_zero_confidence():
    page = _page("Some unrelated text", text_source="native_text")
    response = InvoiceExtraction()
    extracted, _ = extract([page], "invoice", MockLLM(response))
    assert extracted["total_amount"]["value"] is None
    assert extracted["total_amount"]["confidence"] == 0.0


def test_financial_line_item_period_grounding():
    page = _page("Deposits 3 11,462,071,336 9,225,026,779", text_source="native_text")
    response = FinancialStatementExtraction(
        statement_title=StrField(value="Consolidated Balance Sheet"),
        periods=["March 31, 2020", "March 31, 2019"],
        line_items=[
            FinancialLineItem(
                label="Deposits",
                section="CAPITAL AND LIABILITIES",
                values=[
                    PeriodValue(period="March 31, 2020", value=11462071336.0),
                    PeriodValue(period="March 31, 2019", value=9225026779.0),
                ],
                source_text="Deposits 3 11,462,071,336 9,225,026,779",
            )
        ],
    )
    extracted, _ = extract([page], "balance_sheet", MockLLM(response))
    values = extracted["line_items"][0]["values"]
    assert values["March 31, 2020"]["grounded"] is True
    assert values["March 31, 2019"]["grounded"] is True
