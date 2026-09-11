import pytest

from backend.app.utils.numbers import (
    extract_numbers_from_text,
    parse_number,
    value_grounded_in_text,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,546.40", 1546.40),
        ("(1,546.40)", -1546.40),
        ("(1546.40)", -1546.40),
        ("₹1,000", 1000.0),
        ("`5,000.50", 5000.50),
        ("RM 9.00", 9.00),
        ("Rs. 250", 250.0),
        ("-", 0.0),
        ("–", 0.0),
        ("—", 0.0),
        ("", None),
        (None, None),
        ("N/A", None),
        ("abc", None),
        (1234.5, 1234.5),
        (100, 100.0),
        ("42,928,057,065", 42928057065.0),
        ("-1546.40", -1546.40),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


def test_extract_numbers_from_text():
    text = "Total 42,928,057,065 ASSETS Cash (1,546.40) Deposits ` 5,000"
    numbers = extract_numbers_from_text(text)
    assert 42928057065.0 in numbers
    assert -1546.40 in numbers
    assert 5000.0 in numbers


def test_value_grounded_in_text():
    text = "Consolidated profit before income tax 50,775.24 42,772.58"
    assert value_grounded_in_text(50775.24, text)
    assert not value_grounded_in_text(99999.99, text)
