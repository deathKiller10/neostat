"""Per-document-type financial validation checks, built on the matching primitives in
financial_validation_service.py. Each check runs once per comparative period for
financial statements (HDFC pages show two years side by side); invoices have no
periods so their checks run once each.
"""

from backend.app.services.financial_checks_statements import (
    build_cash_flow_checks,
    build_profit_and_loss_checks,
)
from backend.app.services.financial_validation_service import (
    LABEL_SYNONYMS,
    evaluate_check,
    find_line_item_value,
    get_field_value,
    sum_section_components,
)


def build_invoice_checks(extracted_data: dict, abs_tol: float, rel_tol: float) -> list[dict]:
    checks = []
    line_items = extracted_data.get("line_items", [])

    for i, item in enumerate(line_items):
        operands = {"quantity": item.get("quantity"), "unit_price": item.get("unit_price")}
        checks.append(
            evaluate_check(
                name=f"invoice_line_item_check[{i}]",
                formula="quantity * unit_price",
                operands=operands,
                calc_fn=lambda o: o["quantity"] * o["unit_price"],
                reported_value=item.get("amount"),
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )

    line_total_sum = None
    if line_items and all(item.get("amount") is not None for item in line_items):
        line_total_sum = sum(item["amount"] for item in line_items)
    subtotal_value = get_field_value(extracted_data, "subtotal")
    total_value = get_field_value(extracted_data, "total_amount")
    reported_for_sum = subtotal_value if subtotal_value is not None else total_value
    checks.append(
        evaluate_check(
            name="invoice_line_items_sum_check",
            formula="sum(line_item.amount)",
            operands={"line_total_sum": line_total_sum},
            calc_fn=lambda o: o["line_total_sum"],
            reported_value=reported_for_sum,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
        )
    )

    # A missing discount line item means no discount was given, not an unknown value,
    # so it defaults to 0 here rather than making the whole check NOT_APPLICABLE.
    discount_value = get_field_value(extracted_data, "discount")
    discount_value = discount_value if discount_value is not None else 0.0
    checks.append(
        evaluate_check(
            name="invoice_tax_exclusive_total_check",
            formula="subtotal + tax_amount - discount",
            operands={
                "subtotal": subtotal_value,
                "tax_amount": get_field_value(extracted_data, "tax_amount"),
                "discount": discount_value,
            },
            calc_fn=lambda o: o["subtotal"] + o["tax_amount"] - o["discount"],
            reported_value=total_value,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
        )
    )

    checks.append(
        evaluate_check(
            name="invoice_tax_inclusive_total_check",
            formula="gst_taxable_amount + gst_amount",
            operands={
                "gst_taxable_amount": get_field_value(extracted_data, "gst_taxable_amount"),
                "gst_amount": get_field_value(extracted_data, "gst_amount"),
            },
            calc_fn=lambda o: o["gst_taxable_amount"] + o["gst_amount"],
            reported_value=total_value,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
        )
    )

    checks.append(
        evaluate_check(
            name="invoice_cash_change_check",
            formula="cash_paid - total_amount",
            operands={"cash_paid": get_field_value(extracted_data, "cash_paid"), "total_amount": total_value},
            calc_fn=lambda o: o["cash_paid"] - o["total_amount"],
            reported_value=get_field_value(extracted_data, "change_given"),
            abs_tol=abs_tol,
            rel_tol=rel_tol,
        )
    )

    return checks


def build_balance_sheet_checks(extracted_data: dict, abs_tol: float, rel_tol: float) -> list[dict]:
    checks = []
    line_items = extracted_data.get("line_items", [])
    for period in extracted_data.get("periods", []):
        total_assets, _ = find_line_item_value(line_items, period, LABEL_SYNONYMS["total_assets"], "asset")
        total_liabilities, _ = find_line_item_value(
            line_items, period, LABEL_SYNONYMS["total_capital_and_liabilities"], "liabilit"
        )
        checks.append(
            evaluate_check(
                name=f"balance_sheet_totals_check[{period}]",
                formula="total_capital_and_liabilities - total_assets",
                operands={"total_capital_and_liabilities": total_liabilities},
                calc_fn=lambda o: o["total_capital_and_liabilities"],
                reported_value=total_assets,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )

        liability_components = sum_section_components(line_items, period, "liabilit")
        checks.append(
            evaluate_check(
                name=f"balance_sheet_liabilities_components_check[{period}]",
                formula="sum(liability components)",
                operands=liability_components,
                calc_fn=lambda o: sum(o.values()),
                reported_value=total_liabilities,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )

        asset_components = sum_section_components(line_items, period, "asset")
        checks.append(
            evaluate_check(
                name=f"balance_sheet_assets_components_check[{period}]",
                formula="sum(asset components)",
                operands=asset_components,
                calc_fn=lambda o: sum(o.values()),
                reported_value=total_assets,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )
    return checks


CHECK_BUILDERS = {
    "invoice": build_invoice_checks,
    "balance_sheet": build_balance_sheet_checks,
    "profit_and_loss": build_profit_and_loss_checks,
    "cash_flow_statement": build_cash_flow_checks,
}


def collect_grounding_issues(extracted_data: dict) -> list[dict]:
    issues = []
    for key, field in extracted_data.items():
        if key == "line_items" or not isinstance(field, dict):
            continue
        if field.get("grounded") is False:
            issues.append(
                {
                    "type": "ungrounded_value",
                    "field": key,
                    "message": f"Value '{field.get('value')}' for {key} was not found in the source text.",
                }
            )
    for item in extracted_data.get("line_items", []):
        for period, field in item.get("values", {}).items():
            if isinstance(field, dict) and field.get("grounded") is False:
                issues.append(
                    {
                        "type": "ungrounded_value",
                        "field": f"{item.get('label')}[{period}]",
                        "message": (
                            f"Value '{field.get('value')}' for {item.get('label')} ({period}) "
                            "was not found in the source text."
                        ),
                    }
                )
    return issues


def validate(extracted_data: dict, document_type: str, abs_tol: float, rel_tol: float) -> dict:
    builder = CHECK_BUILDERS[document_type]
    checks = builder(extracted_data, abs_tol, rel_tol)
    issues = collect_grounding_issues(extracted_data)
    for check in checks:
        if check["status"] == "FAIL":
            issues.append(
                {
                    "type": "validation_failed",
                    "check": check["name"],
                    "message": (
                        f"{check['name']}: calculated {check['calculated_value']} but reported "
                        f"{check['reported_value']} (variance {check['variance']})."
                    ),
                }
            )
    overall_status = "FAIL" if any(c["status"] == "FAIL" for c in checks) else "PASS"
    return {"checks": checks, "overall_status": overall_status, "issues": issues}
