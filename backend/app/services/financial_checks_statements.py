"""Profit & loss and cash flow checks -- split out from financial_checks.py (which
keeps invoice and balance sheet) to keep each file focused and under ~300 lines.
"""

from backend.app.services.financial_validation_service import LABEL_SYNONYMS, evaluate_check, find_line_item_value


def build_profit_and_loss_checks(extracted_data: dict, abs_tol: float, rel_tol: float) -> list[dict]:
    checks = []
    line_items = extracted_data.get("line_items", [])
    for period in extracted_data.get("periods", []):

        def find(key):
            return find_line_item_value(line_items, period, LABEL_SYNONYMS[key])[0]

        total_income = find("total_income")
        checks.append(
            evaluate_check(
                name=f"profit_and_loss_income_check[{period}]",
                formula="interest_earned + other_income",
                operands={"interest_earned": find("interest_earned"), "other_income": find("other_income")},
                calc_fn=lambda o: o["interest_earned"] + o["other_income"],
                reported_value=total_income,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )

        total_expenditure = find("total_expenditure")
        checks.append(
            evaluate_check(
                name=f"profit_and_loss_expenditure_check[{period}]",
                formula="interest_expended + operating_expenses + provisions_and_contingencies",
                operands={
                    "interest_expended": find("interest_expended"),
                    "operating_expenses": find("operating_expenses"),
                    "provisions_and_contingencies": find("provisions_and_contingencies"),
                },
                calc_fn=lambda o: o["interest_expended"] + o["operating_expenses"] + o["provisions_and_contingencies"],
                reported_value=total_expenditure,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )

        net_profit_before_minority = find("net_profit_before_minority_interest")
        checks.append(
            evaluate_check(
                name=f"profit_and_loss_net_profit_check[{period}]",
                formula="total_income - total_expenditure",
                operands={"total_income": total_income, "total_expenditure": total_expenditure},
                calc_fn=lambda o: o["total_income"] - o["total_expenditure"],
                reported_value=net_profit_before_minority,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )

        checks.append(
            evaluate_check(
                name=f"profit_and_loss_minority_interest_check[{period}]",
                formula="net_profit_before_minority_interest - minority_interest",
                operands={
                    "net_profit_before_minority_interest": net_profit_before_minority,
                    "minority_interest": find("minority_interest"),
                },
                calc_fn=lambda o: o["net_profit_before_minority_interest"] - o["minority_interest"],
                reported_value=find("net_profit_attributable_to_group"),
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )

        checks.append(
            evaluate_check(
                name=f"profit_and_loss_appropriation_check[{period}]",
                formula="current_profit + brought_forward_profit",
                operands={"current_profit": find("current_profit"), "brought_forward_profit": find("brought_forward_profit")},
                calc_fn=lambda o: o["current_profit"] + o["brought_forward_profit"],
                reported_value=find("total_available_for_appropriation"),
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )
    return checks


def build_cash_flow_checks(extracted_data: dict, abs_tol: float, rel_tol: float) -> list[dict]:
    checks = []
    line_items = extracted_data.get("line_items", [])
    for period in extracted_data.get("periods", []):

        def find(key):
            return find_line_item_value(line_items, period, LABEL_SYNONYMS[key])[0]

        operating = find("operating_activities")
        investing = find("investing_activities")
        financing = find("financing_activities")
        # A missing FX line means no FX adjustment was reported that year, not an
        # unknown value -- same reasoning as invoice discount in financial_checks.py.
        fx = find("fx_adjustment")
        fx = fx if fx is not None else 0.0
        net_increase = find("net_increase_in_cash")

        checks.append(
            evaluate_check(
                name=f"cash_flow_net_increase_check[{period}]",
                formula="operating_activities + investing_activities + financing_activities + fx_adjustment",
                operands={
                    "operating_activities": operating,
                    "investing_activities": investing,
                    "financing_activities": financing,
                    "fx_adjustment": fx,
                },
                calc_fn=lambda o: o["operating_activities"]
                + o["investing_activities"]
                + o["financing_activities"]
                + o["fx_adjustment"],
                reported_value=net_increase,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )

        opening_cash = find("opening_cash")
        cash_acquired = find("cash_acquired_on_amalgamation")
        cash_acquired = cash_acquired if cash_acquired is not None else 0.0
        checks.append(
            evaluate_check(
                name=f"cash_flow_closing_balance_check[{period}]",
                formula="opening_cash + net_increase_in_cash + cash_acquired_on_amalgamation",
                operands={
                    "opening_cash": opening_cash,
                    "net_increase_in_cash": net_increase,
                    "cash_acquired_on_amalgamation": cash_acquired,
                },
                calc_fn=lambda o: o["opening_cash"] + o["net_increase_in_cash"] + o["cash_acquired_on_amalgamation"],
                reported_value=find("closing_cash"),
                abs_tol=abs_tol,
                rel_tol=rel_tol,
            )
        )
    return checks
