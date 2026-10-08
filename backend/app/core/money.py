from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
THREE_PLACES = Decimal("0.001")
FOUR_PLACES = Decimal("0.0001")


def round_money(value: Decimal | float | int | str) -> Decimal:
    """Rounds currency amounts to 2 decimal places using ROUND_HALF_UP."""
    dec_val = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return dec_val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def round_qty(value: Decimal | float | int | str) -> Decimal:
    """Rounds quantities to 3 decimal places using ROUND_HALF_UP."""
    dec_val = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return dec_val.quantize(THREE_PLACES, rounding=ROUND_HALF_UP)


def round_unit_price(value: Decimal | float | int | str) -> Decimal:
    """Rounds unit prices and unit costs to 4 decimal places using ROUND_HALF_UP."""
    dec_val = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return dec_val.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def round_rate(value: Decimal | float | int | str) -> Decimal:
    """Rounds tax and probability rates to 4 decimal places."""
    dec_val = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return dec_val.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def calculate_line(
    quantity: Decimal,
    unit_price: Decimal,
    discount_amount: Decimal = Decimal("0.00"),
    tax_rate: Decimal = Decimal("0.1200"),
) -> dict[str, Decimal]:
    """
    Standard line-item calculation per Roadmap §4.3:
    line_gross  = round2(quantity * unit_price)
    line_net    = line_gross - discount_amount (0 <= discount_amount <= line_gross)
    line_tax    = round2(line_net * tax_rate)
    line_total  = line_net + line_tax
    """
    gross = round_money(quantity * unit_price)
    if discount_amount < Decimal("0.00"):
        raise ValueError("discount_amount cannot be negative")
    if discount_amount > gross:
        raise ValueError("discount_amount cannot exceed line gross amount")

    net = round_money(gross - discount_amount)
    tax = round_money(net * tax_rate)
    total = round_money(net + tax)

    return {
        "line_gross": gross,
        "discount_amount": discount_amount,
        "line_net": net,
        "line_tax": tax,
        "line_total": total,
    }
