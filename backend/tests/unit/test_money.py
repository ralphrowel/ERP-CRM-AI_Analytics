from decimal import Decimal

import pytest

from app.core.money import calculate_line, round_money, round_qty, round_rate, round_unit_price


def test_round_money_half_up():
    assert round_money(Decimal("10.004")) == Decimal("10.00")
    assert round_money(Decimal("10.005")) == Decimal("10.01")
    assert round_money("1234.567") == Decimal("1234.57")
    assert round_money(100) == Decimal("100.00")


def test_round_qty():
    assert round_qty("5.1234") == Decimal("5.123")
    assert round_qty("5.1235") == Decimal("5.124")


def test_round_unit_price():
    assert round_unit_price("150.12344") == Decimal("150.1234")
    assert round_unit_price("150.12345") == Decimal("150.1235")


def test_round_rate():
    assert round_rate("0.12001") == Decimal("0.1200")
    assert round_rate("0.12005") == Decimal("0.1201")


def test_calculate_line_standard():
    # 10 units at 150.00 PHP with standard 12% VAT
    res = calculate_line(
        quantity=Decimal("10.000"),
        unit_price=Decimal("150.0000"),
        discount_amount=Decimal("0.00"),
        tax_rate=Decimal("0.1200"),
    )
    assert res["line_gross"] == Decimal("1500.00")
    assert res["line_net"] == Decimal("1500.00")
    assert res["line_tax"] == Decimal("180.00")  # 1500 * 0.12 = 180.00
    assert res["line_total"] == Decimal("1680.00")


def test_calculate_line_with_discount():
    res = calculate_line(
        quantity=Decimal("2.000"),
        unit_price=Decimal("100.0000"),
        discount_amount=Decimal("20.00"),
        tax_rate=Decimal("0.1200"),
    )
    assert res["line_gross"] == Decimal("200.00")
    assert res["line_net"] == Decimal("180.00")
    assert res["line_tax"] == Decimal("21.60")  # 180 * 0.12 = 21.60
    assert res["line_total"] == Decimal("201.60")


def test_calculate_line_invalid_discount():
    with pytest.raises(ValueError, match="cannot exceed"):
        calculate_line(
            quantity=Decimal("1.000"),
            unit_price=Decimal("50.0000"),
            discount_amount=Decimal("60.00"),
        )

    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_line(
            quantity=Decimal("1.000"),
            unit_price=Decimal("50.0000"),
            discount_amount=Decimal("-5.00"),
        )
