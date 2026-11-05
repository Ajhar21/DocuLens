from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.reconciliation.comparator import (
    compare_amount,
    compare_date,
    compare_invoices,
    compare_text,
    normalize_supplier_name,
)


def test_normalize_supplier_name_legal_suffixes() -> None:
    assert normalize_supplier_name("Acme Corp.") == "acme"
    assert normalize_supplier_name("Acme Corporation") == "acme"
    assert normalize_supplier_name("Acme Inc.") == "acme"
    assert normalize_supplier_name("Acme Incorporated") == "acme"
    assert normalize_supplier_name("Acme LLC") == "acme"
    assert normalize_supplier_name("Acme Ltd.") == "acme"
    assert normalize_supplier_name("Acme Limited") == "acme"
    assert normalize_supplier_name("Acme Co.") == "acme"
    assert normalize_supplier_name("  Global   Logistics  LLC  ") == "global logistics"


def test_compare_text_supplier_suffix_stripping() -> None:
    res = compare_text("supplier_name", "Stark Industries Corp.", "Stark Industries LLC", is_supplier=True)
    assert res.match_status == "EXACT_MATCH"

    res_diff = compare_text("supplier_name", "Wayne Enterprises Ltd", "LexCorp Inc", is_supplier=True)
    assert res_diff.match_status == "MISMATCH"


def test_compare_amount_tolerances_and_boundaries() -> None:
    tol_abs = Decimal("0.05")
    tol_pct = Decimal("0.001")  # 0.1%

    # Exact match
    res_exact = compare_amount("total", Decimal("100.00"), Decimal("100.00"), tol_abs, tol_pct)
    assert res_exact.match_status == "EXACT_MATCH"
    assert res_exact.absolute_difference == Decimal("0.0000")

    # Within absolute tolerance (diff = 0.04 <= 0.05)
    res_tol_abs = compare_amount("total", Decimal("100.00"), Decimal("100.04"), tol_abs, tol_pct)
    assert res_tol_abs.match_status == "TOLERANCE_MATCH"

    # Beyond absolute tolerance on small amount (diff = 0.06 > 0.05, 0.06% < 0.1%? 0.06/100 = 0.0006 <= 0.001 -> pct match!)
    # On small amounts, let's test where both fail:
    # 10.00 vs 10.10: diff = 0.10 (> 0.05 abs), pct = 0.01 = 1% (> 0.1% pct) -> MISMATCH
    res_mismatch = compare_amount("total", Decimal("10.00"), Decimal("10.10"), tol_abs, tol_pct)
    assert res_mismatch.match_status == "MISMATCH"
    assert res_mismatch.absolute_difference == Decimal("0.1000")

    # Large amount within percentage tolerance (10,000.00 vs 10,005.00: diff 5.00 > 0.05, but 5/10000 = 0.0005 <= 0.001)
    res_tol_pct = compare_amount("total", Decimal("10000.00"), Decimal("10005.00"), tol_abs, tol_pct)
    assert res_tol_pct.match_status == "TOLERANCE_MATCH"

    # Large amount outside percentage tolerance (10,000.00 vs 10,020.00: diff 20.00, 20/10000 = 0.002 > 0.001)
    res_pct_mismatch = compare_amount("total", Decimal("10000.00"), Decimal("10020.00"), tol_abs, tol_pct)
    assert res_pct_mismatch.match_status == "MISMATCH"


def test_compare_subtotal_and_tax_null_is_not_comparable() -> None:
    tol_abs = Decimal("0.05")
    tol_pct = Decimal("0.001")

    # Tax missing in B
    res_tax = compare_amount("tax", Decimal("15.00"), None, tol_abs, tol_pct, allow_null_not_comparable=True)
    assert res_tax.match_status == "NOT_COMPARABLE"

    # Subtotal missing in A
    res_subtotal = compare_amount("subtotal", None, Decimal("100.00"), tol_abs, tol_pct, allow_null_not_comparable=True)
    assert res_subtotal.match_status == "NOT_COMPARABLE"

    # Total missing in A (allow_null_not_comparable=False) -> MISSING_IN_A
    res_total = compare_amount("total", None, Decimal("115.00"), tol_abs, tol_pct, allow_null_not_comparable=False)
    assert res_total.match_status == "MISSING_IN_A"


def test_compare_invoices_matched_pair() -> None:
    inv_a = {
        "invoice_number": "INV-2026-001",
        "supplier_name": "Wayne Enterprises Corp.",
        "customer_name": "Gotham City",
        "invoice_date": date(2026, 3, 15),
        "subtotal": Decimal("1000.00"),
        "tax": None,  # Null in A
        "total": Decimal("1000.03"),  # Within absolute tolerance
        "currency": "USD",
        "line_items": [
            {"description": "Tactical Helmet", "quantity": Decimal("2"), "unit_price": Decimal("250.00"), "amount": Decimal("500.00")},
            {"description": "Grappling Hook", "quantity": Decimal("1"), "unit_price": Decimal("500.00"), "amount": Decimal("500.00")},
        ],
    }
    inv_b = {
        "invoice_number": "inv-2026-001",
        "supplier_name": "Wayne Enterprises LLC",
        "customer_name": "Gotham City",
        "invoice_date": "2026-03-15",
        "subtotal": Decimal("1000.00"),
        "tax": Decimal("0.00"),
        "total": Decimal("1000.00"),
        "currency": "USD",
        "line_items": [
            {"item_description": "Tactical Helmet", "quantity": Decimal("2"), "unit_price": Decimal("250.00"), "amount": Decimal("500.00")},
            {"item_description": "Grappling Hook", "quantity": Decimal("1"), "unit_price": Decimal("500.00"), "amount": Decimal("500.00")},
        ],
    }

    result = compare_invoices(inv_a, inv_b)
    assert result.overall_status == "MATCHED"
    assert result.discrepancy_count == 0


def test_compare_invoices_mismatched_pair() -> None:
    inv_a = {
        "invoice_number": "INV-A",
        "supplier_name": "Acme Supplies Ltd",
        "total": Decimal("500.00"),
        "line_items": [
            {"description": "Item 1", "amount": Decimal("500.00")},
        ],
    }
    inv_b = {
        "invoice_number": "INV-B",  # Mismatch
        "supplier_name": "Acme Supplies Inc",
        "total": Decimal("550.00"),  # Mismatch
        "line_items": [
            {"description": "Item 2", "amount": Decimal("550.00")},  # Item 1 missing in B, Item 2 missing in A
        ],
    }

    result = compare_invoices(inv_a, inv_b)
    assert result.overall_status == "MISMATCHED"
    assert result.discrepancy_count >= 2
    match_statuses = {r.match_status for r in result.results}
    assert "MISMATCH" in match_statuses

