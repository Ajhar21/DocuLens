from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Optional
import uuid

from app.core.config import settings
from app.models.document import ReviewStatus
from app.validation.rules import (
    evaluate_invoice_validation,
)
from app.validation.service import determine_review_status


@dataclass
class DummyLineItem:
    line_no: int
    description: Optional[str] = "Item"
    quantity: Optional[Decimal] = Decimal("1.000000")
    unit_price: Optional[Decimal] = Decimal("100.0000")
    amount: Optional[Decimal] = Decimal("100.0000")


@dataclass
class DummyInvoice:
    invoice_number: Optional[str] = "INV-100"
    invoice_date: Optional[date] = date(2026, 1, 15)
    supplier_name: Optional[str] = "Acme Ltd"
    customer_name: Optional[str] = "Client Co"
    subtotal: Optional[Decimal] = Decimal("100.0000")
    tax: Optional[Decimal] = Decimal("10.0000")
    total: Optional[Decimal] = Decimal("110.0000")
    currency: Optional[str] = "USD"
    extraction_metadata: dict[str, Any] = field(default_factory=dict)


def _by_code(items, code: str):
    return [i for i in items if i.validation_code == code]


def test_validation_happy_path_all_pass() -> None:
    inv = DummyInvoice(
        extraction_metadata={"ocr_confidence_avg": 0.92, "ocr_confidence_min": 0.88}
    )
    lines = [DummyLineItem(line_no=1)]
    res = evaluate_invoice_validation(
        invoice=inv,
        line_items=lines,
        reference_date=date(2026, 2, 1),
    )

    assert all(r.status == "PASSED" for r in res), [r for r in res if r.status != "PASSED"]
    assert determine_review_status(res) == ReviewStatus.NOT_REQUIRED.value
    assert determine_review_status([]) == ReviewStatus.PENDING.value


def test_missing_required_fields_and_ambiguous_date() -> None:
    inv = DummyInvoice(
        invoice_number=None,
        invoice_date=None,
        supplier_name="  ",
        total=None,
        subtotal=None,
        extraction_metadata={
            "normalization": {
                "date_ambiguous": True,
                "date_raw": "03/04/2025",
            }
        },
    )
    res = evaluate_invoice_validation(invoice=inv, line_items=[])

    missing = _by_code(res, "MISSING_REQUIRED_FIELD")
    assert len(missing) == 4
    assert all(m.status == "FAILED" and m.severity == "ERROR" for m in missing)

    ambig = _by_code(res, "AMBIGUOUS_DATE")[0]
    assert ambig.status == "FAILED"
    assert ambig.severity == "WARNING"
    assert ambig.actual_value == "03/04/2025"

    no_lines = _by_code(res, "NO_LINE_ITEMS")[0]
    assert no_lines.status == "FAILED"
    assert no_lines.severity == "WARNING"

    assert determine_review_status(res) == ReviewStatus.NEEDS_REVIEW.value


def test_tolerance_boundary_and_discount_shipping_in_total() -> None:
    # Tolerance is 0.01: 0.01 diff passes, 0.02 diff fails
    inv_pass = DummyInvoice(
        subtotal=Decimal("200.0000"),
        tax=Decimal("20.0000"),
        total=Decimal("205.0100"),  # 200 + 20 + 10(shipping) - 25(discount) = 205.00 (+0.01 within tolerance)
        extraction_metadata={
            "shipping": "10.0000",
            "discount": "25.0000",
        },
    )
    lines_pass = [
        DummyLineItem(
            line_no=1,
            quantity=Decimal("2.000000"),
            unit_price=Decimal("100.0000"),
            amount=Decimal("200.0100"),  # within 0.01 tolerance of 200.00
        )
    ]
    res_pass = evaluate_invoice_validation(inv_pass, lines_pass, reference_date=date(2026, 2, 1))
    assert _by_code(res_pass, "LINE_ITEM_AMOUNT_MISMATCH")[0].status == "PASSED"
    assert _by_code(res_pass, "SUBTOTAL_MISMATCH")[0].status == "PASSED"
    assert _by_code(res_pass, "TOTAL_MISMATCH")[0].status == "PASSED"

    # Now exceed tolerance by 0.02 -> FAILED
    inv_fail = DummyInvoice(
        subtotal=Decimal("200.0000"),
        tax=Decimal("20.0000"),
        total=Decimal("205.0200"),
        extraction_metadata={
            "shipping": "10.0000",
            "discount": "25.0000",
        },
    )
    lines_fail = [
        DummyLineItem(
            line_no=1,
            quantity=Decimal("2.000000"),
            unit_price=Decimal("100.0000"),
            amount=Decimal("200.0200"),
        )
    ]
    res_fail = evaluate_invoice_validation(inv_fail, lines_fail, reference_date=date(2026, 2, 1))
    assert _by_code(res_fail, "LINE_ITEM_AMOUNT_MISMATCH")[0].status == "FAILED"
    assert _by_code(res_fail, "SUBTOTAL_MISMATCH")[0].status == "FAILED"
    assert _by_code(res_fail, "TOTAL_MISMATCH")[0].status == "FAILED"
    assert determine_review_status(res_fail) == ReviewStatus.NEEDS_REVIEW.value


def test_negative_amount_future_date_unknown_currency_low_ocr_and_duplicate() -> None:
    dup_id = uuid.uuid4()
    inv = DummyInvoice(
        invoice_date=date(2027, 5, 1),
        subtotal=Decimal("-100.0000"),
        tax=Decimal("0.0000"),
        total=Decimal("-100.0000"),
        currency=None,
        extraction_metadata={
            "ocr_confidence_avg": float(settings.OCR_LOW_CONFIDENCE_THRESHOLD) - 0.15,
            "normalization": {"currency_ambiguous": True, "currency_raw": "$"},
        },
    )
    lines = [
        DummyLineItem(
            line_no=1,
            quantity=Decimal("1.000000"),
            unit_price=Decimal("-100.0000"),
            amount=Decimal("-100.0000"),
        )
    ]
    res = evaluate_invoice_validation(
        invoice=inv,
        line_items=lines,
        duplicate_document_ids=[dup_id],
        reference_date=date(2026, 2, 1),
    )

    neg = _by_code(res, "NEGATIVE_AMOUNT")[0]
    assert neg.status == "FAILED" and neg.severity == "WARNING"

    fut = _by_code(res, "FUTURE_DATE")[0]
    assert fut.status == "FAILED" and fut.severity == "WARNING"

    curr = _by_code(res, "UNKNOWN_CURRENCY")[0]
    assert curr.status == "FAILED" and curr.severity == "INFO"
    assert curr.actual_value == "$"

    ocr = _by_code(res, "LOW_OCR_CONFIDENCE")[0]
    assert ocr.status == "FAILED" and ocr.severity == "INFO"

    dup = _by_code(res, "DUPLICATE_INVOICE")[0]
    assert dup.status == "FAILED" and dup.severity == "WARNING"
    assert dup.actual_value == str(dup_id)

    # Any failed validation (including DUPLICATE_INVOICE) flags document for review
    assert determine_review_status(res) == ReviewStatus.NEEDS_REVIEW.value

