"""Schemas the LLM fills in directly, one per page. Confidence and page_number are
computed by our own code afterwards (see extraction_service.py), never by the model --
each field only carries a value and the verbatim source line it was read from, which
both grounds the value and gives the model somewhere concrete to point instead of
guessing.
"""

from pydantic import BaseModel, Field


class StrField(BaseModel):
    value: str | None = None
    source_text: str | None = None


class NumField(BaseModel):
    value: float | None = None
    source_text: str | None = None


class BoolField(BaseModel):
    value: bool | None = None
    source_text: str | None = None


class InvoiceLineItem(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    source_text: str | None = None


class InvoiceExtraction(BaseModel):
    shop_name: StrField = Field(default_factory=StrField)
    registration_number: StrField = Field(default_factory=StrField)
    gst_id: StrField = Field(default_factory=StrField)
    invoice_number: StrField = Field(default_factory=StrField)
    invoice_date: StrField = Field(default_factory=StrField)
    currency: StrField = Field(default_factory=StrField)
    is_tax_inclusive: BoolField = Field(default_factory=BoolField)
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    subtotal: NumField = Field(default_factory=NumField)
    tax_amount: NumField = Field(default_factory=NumField)
    discount: NumField = Field(default_factory=NumField)
    gst_taxable_amount: NumField = Field(default_factory=NumField)
    gst_amount: NumField = Field(default_factory=NumField)
    total_amount: NumField = Field(default_factory=NumField)
    cash_paid: NumField = Field(default_factory=NumField)
    change_given: NumField = Field(default_factory=NumField)


class PeriodValue(BaseModel):
    period: str
    value: float | None = None


class FinancialLineItem(BaseModel):
    """`values` is a list of (period, value) pairs rather than a dict keyed by period
    -- Gemini's structured-output mode on the free Developer API doesn't support
    open-ended object maps (`additionalProperties`), only fixed-shape objects, so a
    dict-of-periods schema is rejected at request time. `extraction_merge.py`
    converts this list into the period-keyed shape the API actually returns.
    """

    label: str
    section: str | None = None
    values: list[PeriodValue] = Field(default_factory=list)
    source_text: str | None = None


class FinancialStatementExtraction(BaseModel):
    statement_title: StrField = Field(default_factory=StrField)
    entity_name: StrField = Field(default_factory=StrField)
    period_end: StrField = Field(default_factory=StrField)
    currency: StrField = Field(default_factory=StrField)
    units: StrField = Field(default_factory=StrField)
    periods: list[str] = Field(default_factory=list)
    line_items: list[FinancialLineItem] = Field(default_factory=list)


EXTRACTION_SCHEMAS = {
    "invoice": InvoiceExtraction,
    "balance_sheet": FinancialStatementExtraction,
    "profit_and_loss": FinancialStatementExtraction,
    "cash_flow_statement": FinancialStatementExtraction,
}
