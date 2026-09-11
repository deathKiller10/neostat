import pytest

from backend.app.core.exceptions import (
    CorruptedFileError,
    EmptyFileError,
    FileTooLargeError,
    PageLimitExceededError,
    UnsupportedFileTypeError,
)
from backend.app.services.document_validation_service import validate_upload
from backend.app.services.financial_checks import validate
from backend.tests.conftest import make_jpeg_bytes, make_pdf_bytes, make_png_bytes


def test_empty_file_rejected(settings):
    with pytest.raises(EmptyFileError):
        validate_upload(b"", "invoice.pdf", settings)


def test_valid_pdf_passes(settings):
    result = validate_upload(make_pdf_bytes(1), "statement.pdf", settings)
    assert result.status == "PASS"
    assert result.file_type == "application/pdf"
    assert result.page_count == 1


def test_valid_jpeg_passes(settings):
    result = validate_upload(make_jpeg_bytes(), "invoice.jpg", settings)
    assert result.status == "PASS"
    assert result.file_type == "image/jpeg"


def test_valid_png_passes(settings):
    result = validate_upload(make_png_bytes(), "invoice.png", settings)
    assert result.status == "PASS"
    assert result.file_type == "image/png"


def test_unsupported_extension_rejected(settings):
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload(make_pdf_bytes(1), "statement.txt", settings)


def test_extension_content_mismatch_rejected(settings):
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload(make_png_bytes(), "invoice.pdf", settings)


def test_corrupted_pdf_rejected(settings):
    with pytest.raises(CorruptedFileError):
        validate_upload(b"%PDF-1.4 not really a pdf", "statement.pdf", settings)


def test_corrupted_image_rejected(settings):
    with pytest.raises(CorruptedFileError):
        validate_upload(b"\xff\xd8\xff\x00garbage", "invoice.jpg", settings)


def test_page_limit_exceeded_rejected(settings):
    with pytest.raises(PageLimitExceededError):
        validate_upload(make_pdf_bytes(settings.max_page_count + 1), "statement.pdf", settings)


def test_file_too_large_rejected(settings):
    settings.max_upload_mb = 0
    with pytest.raises(FileTooLargeError):
        validate_upload(make_jpeg_bytes(200, 200), "invoice.jpg", settings)


# --- financial validation ---

ABS_TOL = 1.00
REL_TOL = 0.005


def _num(value, grounded=True):
    return {"value": value, "confidence": 0.9, "page_number": 1, "source_text": None, "grounded": grounded}


def _line_item(label, values, section=None, source_text=None):
    wrapped = {period: _num(value) for period, value in values.items()}
    return {"label": label, "section": section, "values": wrapped, "page_number": 1, "source_text": source_text}


def test_invoice_line_item_check_pass():
    extracted = {
        "line_items": [{"description": "A", "quantity": 2, "unit_price": 5.0, "amount": 10.0}],
        "subtotal": _num(10.0),
        "total_amount": _num(10.0),
    }
    result = validate(extracted, "invoice", ABS_TOL, REL_TOL)
    check = next(c for c in result["checks"] if c["name"] == "invoice_line_item_check[0]")
    assert check["status"] == "PASS"
    assert check["calculated_value"] == 10.0


def test_invoice_line_item_check_fail():
    extracted = {
        "line_items": [{"description": "A", "quantity": 2, "unit_price": 5.0, "amount": 999.0}],
        "total_amount": _num(999.0),
    }
    result = validate(extracted, "invoice", ABS_TOL, REL_TOL)
    check = next(c for c in result["checks"] if c["name"] == "invoice_line_item_check[0]")
    assert check["status"] == "FAIL"


def test_invoice_tax_exclusive_total_check():
    extracted = {
        "line_items": [],
        "subtotal": _num(12500.00),
        "tax_amount": _num(625.00),
        "total_amount": _num(13125.00),
    }
    result = validate(extracted, "invoice", ABS_TOL, REL_TOL)
    check = next(c for c in result["checks"] if c["name"] == "invoice_tax_exclusive_total_check")
    assert check["status"] == "PASS"
    assert check["operands"]["discount"] == 0.0


def test_invoice_tax_inclusive_total_check():
    extracted = {
        "line_items": [],
        "gst_taxable_amount": _num(8.49),
        "gst_amount": _num(0.51),
        "total_amount": _num(9.00),
    }
    result = validate(extracted, "invoice", ABS_TOL, REL_TOL)
    check = next(c for c in result["checks"] if c["name"] == "invoice_tax_inclusive_total_check")
    assert check["status"] == "PASS"


def test_invoice_cash_change_check():
    extracted = {"line_items": [], "cash_paid": _num(50.0), "total_amount": _num(9.0), "change_given": _num(41.0)}
    result = validate(extracted, "invoice", ABS_TOL, REL_TOL)
    check = next(c for c in result["checks"] if c["name"] == "invoice_cash_change_check")
    assert check["status"] == "PASS"


def test_invoice_check_not_applicable_when_operand_missing():
    extracted = {"line_items": [], "total_amount": _num(9.0)}
    result = validate(extracted, "invoice", ABS_TOL, REL_TOL)
    check = next(c for c in result["checks"] if c["name"] == "invoice_tax_inclusive_total_check")
    assert check["status"] == "NOT_APPLICABLE"
    assert check["calculated_value"] is None


def test_tolerance_boundary_pass_and_fail():
    # reported 1000.00, rel tolerance = 0.005 * 1000 = 5.00
    extracted_pass = {
        "line_items": [],
        "subtotal": _num(995.00),
        "tax_amount": _num(0.0),
        "total_amount": _num(1000.00),
    }
    result_pass = validate(extracted_pass, "invoice", ABS_TOL, REL_TOL)
    check_pass = next(c for c in result_pass["checks"] if c["name"] == "invoice_tax_exclusive_total_check")
    assert check_pass["status"] == "PASS"

    extracted_fail = {
        "line_items": [],
        "subtotal": _num(993.00),
        "tax_amount": _num(0.0),
        "total_amount": _num(1000.00),
    }
    result_fail = validate(extracted_fail, "invoice", ABS_TOL, REL_TOL)
    check_fail = next(c for c in result_fail["checks"] if c["name"] == "invoice_tax_exclusive_total_check")
    assert check_fail["status"] == "FAIL"


def test_balance_sheet_totals_check_by_period():
    extracted = {
        "periods": ["March 31, 2020", "March 31, 2019"],
        "line_items": [
            _line_item("Capital", {"March 31, 2020": 100.0, "March 31, 2019": 90.0}, "CAPITAL AND LIABILITIES"),
            _line_item("Deposits", {"March 31, 2020": 900.0, "March 31, 2019": 810.0}, "CAPITAL AND LIABILITIES"),
            _line_item("Total", {"March 31, 2020": 1000.0, "March 31, 2019": 900.0}, "CAPITAL AND LIABILITIES"),
            _line_item("Advances", {"March 31, 2020": 1000.0, "March 31, 2019": 900.0}, "ASSETS"),
            _line_item("Total", {"March 31, 2020": 1000.0, "March 31, 2019": 900.0}, "ASSETS"),
        ],
    }
    result = validate(extracted, "balance_sheet", ABS_TOL, REL_TOL)
    check_2020 = next(c for c in result["checks"] if c["name"] == "balance_sheet_totals_check[March 31, 2020]")
    assert check_2020["status"] == "PASS"
    liab_components = next(
        c for c in result["checks"] if c["name"] == "balance_sheet_liabilities_components_check[March 31, 2020]"
    )
    assert liab_components["calculated_value"] == 1000.0
    assert liab_components["status"] == "PASS"


def test_balance_sheet_totals_check_fail():
    extracted = {
        "periods": ["March 31, 2020"],
        "line_items": [
            _line_item("Total", {"March 31, 2020": 1000.0}, "CAPITAL AND LIABILITIES"),
            _line_item("Total", {"March 31, 2020": 850.0}, "ASSETS"),
        ],
    }
    result = validate(extracted, "balance_sheet", ABS_TOL, REL_TOL)
    check = next(c for c in result["checks"] if c["name"] == "balance_sheet_totals_check[March 31, 2020]")
    assert check["status"] == "FAIL"


def test_profit_and_loss_chain():
    period = "March 31, 2024"
    extracted = {
        "periods": [period],
        "line_items": [
            _line_item("Interest earned", {period: 800.0}),
            _line_item("Other income", {period: 200.0}),
            _line_item("Total income", {period: 1000.0}),
            _line_item("Interest expended", {period: 400.0}),
            _line_item("Operating expenses", {period: 300.0}),
            _line_item("Provisions and contingencies", {period: 100.0}),
            _line_item("Total expenditure", {period: 800.0}),
            _line_item("Consolidated net profit before minority interest", {period: 200.0}),
            _line_item("Minority interest", {period: 20.0}),
            _line_item("Net profit attributable to the group", {period: 180.0}),
        ],
    }
    result = validate(extracted, "profit_and_loss", ABS_TOL, REL_TOL)
    names = ["profit_and_loss_income_check", "profit_and_loss_expenditure_check", "profit_and_loss_net_profit_check", "profit_and_loss_minority_interest_check"]
    for name in names:
        check = next(c for c in result["checks"] if c["name"] == f"{name}[{period}]")
        assert check["status"] == "PASS", check


def test_cash_flow_chain():
    period = "March 31, 2024"
    extracted = {
        "periods": [period],
        "line_items": [
            _line_item("Net cash flow (used in) / from operating activities", {period: 500.0}),
            _line_item("Investing activities", {period: -200.0}),
            _line_item("Financing activities", {period: -100.0}),
            _line_item("Net increase (decrease) in cash and cash equivalents", {period: 200.0}),
            _line_item("Cash and cash equivalents at the beginning of the year", {period: 300.0}),
            _line_item("Cash and cash equivalents at the end of the year", {period: 500.0}),
        ],
    }
    result = validate(extracted, "cash_flow_statement", ABS_TOL, REL_TOL)
    net_increase = next(c for c in result["checks"] if c["name"] == f"cash_flow_net_increase_check[{period}]")
    assert net_increase["status"] == "PASS"
    closing = next(c for c in result["checks"] if c["name"] == f"cash_flow_closing_balance_check[{period}]")
    assert closing["status"] == "PASS"


def test_ungrounded_value_produces_issue():
    extracted = {"line_items": [], "total_amount": _num(9999.0, grounded=False)}
    result = validate(extracted, "invoice", ABS_TOL, REL_TOL)
    assert any(issue["type"] == "ungrounded_value" for issue in result["issues"])


def test_overall_status_fail_when_any_check_fails():
    extracted = {
        "line_items": [{"description": "A", "quantity": 2, "unit_price": 5.0, "amount": 999.0}],
        "total_amount": _num(999.0),
    }
    result = validate(extracted, "invoice", ABS_TOL, REL_TOL)
    assert result["overall_status"] == "FAIL"
