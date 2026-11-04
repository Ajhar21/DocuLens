from __future__ import annotations

from datetime import date
from decimal import Decimal
import pytest

from app.extraction.normalizer import (
    normalize_currency,
    normalize_date,
    normalize_decimal,
    normalize_invoice_number_key,
    normalize_supplier_key,
)


def test_normalize_decimal_standard_and_Accounting_negatives() -> None:
    assert normalize_decimal("1,234.56") == Decimal("1234.5600")
    assert normalize_decimal("$ 12,345,678.90") == Decimal("12345678.9000")
    assert normalize_decimal("USD 99.5") == Decimal("99.5000")
    assert normalize_decimal("(1,250.75)") == Decimal("-1250.7500")
    assert normalize_decimal("$(45.00)") == Decimal("-45.0000")
    assert normalize_decimal("-300.25") == Decimal("-300.2500")
    assert normalize_decimal("300.25-") == Decimal("-300.2500")
    assert normalize_decimal("1,000") == Decimal("1000.0000")
    assert normalize_decimal("4", scale=6) == Decimal("4.000000")


def test_normalize_decimal_european_comma_decimal() -> None:
    # Unambiguous European thousand-dots + comma-decimal
    assert normalize_decimal("1.234,56") == Decimal("1234.5600")
    assert normalize_decimal("€ 12.345.678,90") == Decimal("12345678.9000")
    # Unambiguous single comma with 1 or 2 decimals
    assert normalize_decimal("123,45") == Decimal("123.4500")
    assert normalize_decimal("0,5") == Decimal("0.5000")


def test_normalize_decimal_rejects_float_and_invalid_strings() -> None:
    with pytest.raises(TypeError):
        normalize_decimal(12.34)  # type: ignore[arg-type]

    assert normalize_decimal(None) is None
    assert normalize_decimal("") is None
    assert normalize_decimal("N/A") is None
    assert normalize_decimal("12,34,56.78") is None
    assert normalize_decimal("1.23.45") is None


def test_normalize_date_unambiguous_and_ambiguous() -> None:
    # ISO date
    res_iso = normalize_date("2025-04-03")
    assert res_iso.value == date(2025, 4, 3)
    assert res_iso.is_ambiguous is False

    # Named month formats
    res_named = normalize_date("15 Jan 2026")
    assert res_named.value == date(2026, 1, 15)
    assert res_named.is_ambiguous is False

    res_named_2 = normalize_date("March 4th, 2025")
    assert res_named_2.value == date(2025, 3, 4)
    assert res_named_2.is_ambiguous is False

    # Unambiguous DD/MM/YYYY (first > 12)
    res_dmy = normalize_date("25/04/2025")
    assert res_dmy.value == date(2025, 4, 25)
    assert res_dmy.is_ambiguous is False

    # Unambiguous MM/DD/YYYY (second > 12)
    res_mdy = normalize_date("04/25/2025")
    assert res_mdy.value == date(2025, 4, 25)
    assert res_mdy.is_ambiguous is False

    # Equal day and month (05/05/2025) is unambiguous
    res_same = normalize_date("05/05/2025")
    assert res_same.value == date(2025, 5, 5)
    assert res_same.is_ambiguous is False

    # Ambiguous numeric date (both <= 12 and unequal): must leave date None and flag is_ambiguous
    res_ambig = normalize_date("03/04/2025")
    assert res_ambig.value is None
    assert res_ambig.is_ambiguous is True
    assert res_ambig.raw_value == "03/04/2025"

    # Two-digit year is also treated as ambiguous
    res_short = normalize_date("15/04/25")
    assert res_short.value is None
    assert res_short.is_ambiguous is True


def test_normalize_currency_explicit_iso_unambiguous_symbols_and_bare_dollar() -> None:
    assert normalize_currency("USD").value == "USD"
    assert normalize_currency("eur").value == "EUR"
    assert normalize_currency("€").value == "EUR"
    assert normalize_currency("£").value == "GBP"
    assert normalize_currency("৳").value == "BDT"
    assert normalize_currency("US$").value == "USD"
    assert normalize_currency("CA$").value == "CAD"

    # Bare '$' is ambiguous => value is None, is_ambiguous is True (never defaults to USD)
    bare_dollar = normalize_currency("$")
    assert bare_dollar.value is None
    assert bare_dollar.is_ambiguous is True

    # Fallback to amount strings when currency is null
    fallback_eur = normalize_currency(None, fallback_amount_strings=["€ 1,200.00"])
    assert fallback_eur.value == "EUR"

    fallback_bare_dollar = normalize_currency(None, fallback_amount_strings=["$1,200.00"])
    assert fallback_bare_dollar.value is None
    assert fallback_bare_dollar.is_ambiguous is True


def test_duplicate_key_normalization_helpers() -> None:
    assert normalize_supplier_key("  Acme, Inc. - Global   Supplies!! ") == "acme inc global supplies"
    assert normalize_supplier_key(None) is None
    assert normalize_invoice_number_key(" inv-2026 / 0042#a ") == "INV20260042A"
    assert normalize_invoice_number_key("   --- ") is None

