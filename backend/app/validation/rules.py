from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Optional, Sequence
import uuid

from app.core.config import Settings, settings as default_settings
from app.models.validation import ValidationSeverity, ValidationStatus

VALID_ISO_CURRENCIES: set[str] = {
    "USD", "EUR", "GBP", "BDT", "CAD", "AUD", "JPY", "CHF", "CNY", "INR",
    "SGD", "HKD", "NZD", "SEK", "NOK", "DKK", "AED", "SAR", "MYR", "THB",
    "ZAR", "BRL", "MXN", "KRW", "PKR", "LKR", "NPR", "PLN", "CZK", "HUF",
    "TRY", "ILS", "PHP", "IDR", "VND", "EGP", "NGN", "KES", "QAR", "KWD",
    "BHD", "OMR",
}


@dataclass(frozen=True)
class ValidationItem:
    validation_code: str
    field_name: Optional[str]
    severity: str
    message: str
    expected_value: Optional[str]
    actual_value: Optional[str]
    status: str


def normalize_supplier_key(supplier_name: Optional[str]) -> Optional[str]:
    """Normalize supplier name for duplicate key: lowercase, strip punctuation, collapse whitespace."""
    if not supplier_name:
        return None
    lowered = str(supplier_name).lower()
    no_punct = re.sub(r"[^\w\s]|_", " ", lowered, flags=re.UNICODE)
    collapsed = re.sub(r"\s+", " ", no_punct).strip()
    return collapsed or None


def normalize_invoice_number_key(invoice_number: Optional[str]) -> Optional[str]:
    """Normalize invoice number for duplicate key: uppercase, ASCII alphanumerics only."""
    if not invoice_number:
        return None
    upper = str(invoice_number).upper()
    alnum = re.sub(r"[^A-Z0-9]", "", upper)
    return alnum or None


def build_duplicate_key(
    supplier_name: Optional[str],
    invoice_number: Optional[str],
    invoice_date: Optional[date],
    total: Optional[Decimal],
) -> Optional[tuple[str, str, date, Decimal]]:
    norm_supplier = normalize_supplier_key(supplier_name)
    norm_inv_num = normalize_invoice_number_key(invoice_number)
    if norm_supplier is None or norm_inv_num is None or invoice_date is None or total is None:
        return None
    quant_total = Decimal(total).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return (norm_supplier, norm_inv_num, invoice_date, quant_total)


def _to_decimal_safe(val: Any) -> Optional[Decimal]:
    if val is None or isinstance(val, float):
        return None
    if isinstance(val, Decimal):
        return val
    try:
        text = str(val).strip()
        if not text:
            return None
        return Decimal(text)
    except InvalidOperation:
        return None


def _fmt_money(val: Decimal) -> str:
    return str(val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def evaluate_invoice_validation(
    invoice: Any,
    line_items: Sequence[Any],
    app_settings: Optional[Settings] = None,
    duplicate_document_ids: Optional[Sequence[uuid.UUID | str]] = None,
    reference_date: Optional[date] = None,
) -> list[ValidationItem]:
    """Pure deterministic financial validation function (Decimal only, no LLM, no DB)."""
    cfg = app_settings or default_settings
    tolerance = Decimal(str(cfg.VALIDATION_TOLERANCE))
    today = reference_date or datetime.now(timezone.utc).date()

    meta: dict[str, Any] = (
        invoice.extraction_metadata
        if isinstance(getattr(invoice, "extraction_metadata", None), dict)
        else {}
    )
    norm_meta: dict[str, Any] = (
        meta.get("normalization") if isinstance(meta.get("normalization"), dict) else {}
    )

    results: list[ValidationItem] = []

    # 1. MISSING_REQUIRED_FIELD (ERROR): invoice_number, invoice_date, supplier_name, total
    required_fields = (
        ("invoice_number", getattr(invoice, "invoice_number", None)),
        ("invoice_date", getattr(invoice, "invoice_date", None)),
        ("supplier_name", getattr(invoice, "supplier_name", None)),
        ("total", getattr(invoice, "total", None)),
    )
    for field_name, val in required_fields:
        is_present = val is not None and (not isinstance(val, str) or bool(val.strip()))
        if is_present:
            actual_str = (
                val.isoformat()
                if isinstance(val, date)
                else (_fmt_money(val) if isinstance(val, Decimal) else str(val))
            )
            results.append(
                ValidationItem(
                    validation_code="MISSING_REQUIRED_FIELD",
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR.value,
                    message=f"Required field '{field_name}' is present.",
                    expected_value="non-null",
                    actual_value=actual_str,
                    status=ValidationStatus.PASSED.value,
                )
            )
        else:
            results.append(
                ValidationItem(
                    validation_code="MISSING_REQUIRED_FIELD",
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR.value,
                    message=f"Required field '{field_name}' is missing.",
                    expected_value="non-null",
                    actual_value=None,
                    status=ValidationStatus.FAILED.value,
                )
            )

    # 2. AMBIGUOUS_DATE (WARNING)
    date_ambiguous = bool(norm_meta.get("date_ambiguous"))
    date_raw = norm_meta.get("date_raw")
    inv_date: Optional[date] = getattr(invoice, "invoice_date", None)
    if date_ambiguous:
        results.append(
            ValidationItem(
                validation_code="AMBIGUOUS_DATE",
                field_name="invoice_date",
                severity=ValidationSeverity.WARNING.value,
                message=f"Invoice date '{date_raw}' is ambiguous between DD/MM and MM/DD formats and was left null.",
                expected_value="YYYY-MM-DD or unambiguous date",
                actual_value=str(date_raw) if date_raw is not None else None,
                status=ValidationStatus.FAILED.value,
            )
        )
    elif inv_date is not None:
        results.append(
            ValidationItem(
                validation_code="AMBIGUOUS_DATE",
                field_name="invoice_date",
                severity=ValidationSeverity.WARNING.value,
                message="Invoice date format is unambiguous.",
                expected_value="YYYY-MM-DD or unambiguous date",
                actual_value=inv_date.isoformat(),
                status=ValidationStatus.PASSED.value,
            )
        )
    else:
        results.append(
            ValidationItem(
                validation_code="AMBIGUOUS_DATE",
                field_name="invoice_date",
                severity=ValidationSeverity.WARNING.value,
                message="Skipped ambiguous date check because no invoice date was extracted.",
                expected_value="YYYY-MM-DD or unambiguous date",
                actual_value=str(date_raw) if date_raw is not None else None,
                status=ValidationStatus.SKIPPED.value,
            )
        )

    # 3. NO_LINE_ITEMS (WARNING)
    if not line_items:
        results.append(
            ValidationItem(
                validation_code="NO_LINE_ITEMS",
                field_name="line_items",
                severity=ValidationSeverity.WARNING.value,
                message="Invoice contains no extracted line items.",
                expected_value=">= 1",
                actual_value="0",
                status=ValidationStatus.FAILED.value,
            )
        )
    else:
        results.append(
            ValidationItem(
                validation_code="NO_LINE_ITEMS",
                field_name="line_items",
                severity=ValidationSeverity.WARNING.value,
                message=f"Invoice has {len(line_items)} line item(s).",
                expected_value=">= 1",
                actual_value=str(len(line_items)),
                status=ValidationStatus.PASSED.value,
            )
        )

    # 4. LINE_ITEM_AMOUNT_MISMATCH (WARNING, per line): quantity * unit_price vs amount
    for idx, item in enumerate(line_items, start=1):
        line_no = getattr(item, "line_no", None) or idx
        field_ref = f"line_items[{line_no}].amount"
        qty = _to_decimal_safe(getattr(item, "quantity", None))
        unit_price = _to_decimal_safe(getattr(item, "unit_price", None))
        amount = _to_decimal_safe(getattr(item, "amount", None))

        if qty is None or unit_price is None or amount is None:
            results.append(
                ValidationItem(
                    validation_code="LINE_ITEM_AMOUNT_MISMATCH",
                    field_name=field_ref,
                    severity=ValidationSeverity.WARNING.value,
                    message=f"Line {line_no}: skipped amount check due to missing quantity, unit_price, or amount.",
                    expected_value=None,
                    actual_value=_fmt_money(amount) if amount is not None else None,
                    status=ValidationStatus.SKIPPED.value,
                )
            )
            continue

        expected_amt = (qty * unit_price).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        diff = abs((qty * unit_price) - amount)
        if diff <= tolerance:
            results.append(
                ValidationItem(
                    validation_code="LINE_ITEM_AMOUNT_MISMATCH",
                    field_name=field_ref,
                    severity=ValidationSeverity.WARNING.value,
                    message=f"Line {line_no}: quantity * unit_price matches amount within tolerance.",
                    expected_value=_fmt_money(expected_amt),
                    actual_value=_fmt_money(amount),
                    status=ValidationStatus.PASSED.value,
                )
            )
        else:
            results.append(
                ValidationItem(
                    validation_code="LINE_ITEM_AMOUNT_MISMATCH",
                    field_name=field_ref,
                    severity=ValidationSeverity.WARNING.value,
                    message=(
                        f"Line {line_no}: quantity ({qty}) * unit_price ({_fmt_money(unit_price)}) "
                        f"= {_fmt_money(expected_amt)} does not match amount {_fmt_money(amount)}."
                    ),
                    expected_value=_fmt_money(expected_amt),
                    actual_value=_fmt_money(amount),
                    status=ValidationStatus.FAILED.value,
                )
            )

    # 5. SUBTOTAL_MISMATCH (ERROR): sum(line amounts) vs subtotal
    subtotal_dec = _to_decimal_safe(getattr(invoice, "subtotal", None))
    line_amounts = [_to_decimal_safe(getattr(li, "amount", None)) for li in line_items]
    if subtotal_dec is None or not line_items or any(a is None for a in line_amounts):
        results.append(
            ValidationItem(
                validation_code="SUBTOTAL_MISMATCH",
                field_name="subtotal",
                severity=ValidationSeverity.ERROR.value,
                message="Skipped subtotal check because subtotal or line item amounts are missing.",
                expected_value=None,
                actual_value=_fmt_money(subtotal_dec) if subtotal_dec is not None else None,
                status=ValidationStatus.SKIPPED.value,
            )
        )
    else:
        sum_lines = sum((a for a in line_amounts if a is not None), Decimal("0.0000"))
        if abs(sum_lines - subtotal_dec) <= tolerance:
            results.append(
                ValidationItem(
                    validation_code="SUBTOTAL_MISMATCH",
                    field_name="subtotal",
                    severity=ValidationSeverity.ERROR.value,
                    message="Sum of line item amounts matches subtotal within tolerance.",
                    expected_value=_fmt_money(sum_lines),
                    actual_value=_fmt_money(subtotal_dec),
                    status=ValidationStatus.PASSED.value,
                )
            )
        else:
            results.append(
                ValidationItem(
                    validation_code="SUBTOTAL_MISMATCH",
                    field_name="subtotal",
                    severity=ValidationSeverity.ERROR.value,
                    message=f"Sum of line items ({_fmt_money(sum_lines)}) does not match subtotal ({_fmt_money(subtotal_dec)}).",
                    expected_value=_fmt_money(sum_lines),
                    actual_value=_fmt_money(subtotal_dec),
                    status=ValidationStatus.FAILED.value,
                )
            )

    # 6. TOTAL_MISMATCH (ERROR): subtotal + tax + shipping - discount vs total
    total_dec = _to_decimal_safe(getattr(invoice, "total", None))
    tax_dec = _to_decimal_safe(getattr(invoice, "tax", None)) or Decimal("0.0000")
    shipping_dec = _to_decimal_safe(meta.get("shipping")) or Decimal("0.0000")
    discount_dec = _to_decimal_safe(meta.get("discount")) or Decimal("0.0000")

    if subtotal_dec is None or total_dec is None:
        results.append(
            ValidationItem(
                validation_code="TOTAL_MISMATCH",
                field_name="total",
                severity=ValidationSeverity.ERROR.value,
                message="Skipped total check because subtotal or total is missing.",
                expected_value=None,
                actual_value=_fmt_money(total_dec) if total_dec is not None else None,
                status=ValidationStatus.SKIPPED.value,
            )
        )
    else:
        expected_total = (subtotal_dec + tax_dec + shipping_dec - abs(discount_dec)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        if abs(expected_total - total_dec) <= tolerance:
            results.append(
                ValidationItem(
                    validation_code="TOTAL_MISMATCH",
                    field_name="total",
                    severity=ValidationSeverity.ERROR.value,
                    message="Calculated total (subtotal + tax + shipping - discount) matches invoice total within tolerance.",
                    expected_value=_fmt_money(expected_total),
                    actual_value=_fmt_money(total_dec),
                    status=ValidationStatus.PASSED.value,
                )
            )
        else:
            results.append(
                ValidationItem(
                    validation_code="TOTAL_MISMATCH",
                    field_name="total",
                    severity=ValidationSeverity.ERROR.value,
                    message=(
                        f"Expected total {_fmt_money(expected_total)} "
                        f"(subtotal {_fmt_money(subtotal_dec)} + tax {_fmt_money(tax_dec)} "
                        f"+ shipping {_fmt_money(shipping_dec)} - discount {_fmt_money(abs(discount_dec))}) "
                        f"does not match invoice total {_fmt_money(total_dec)}."
                    ),
                    expected_value=_fmt_money(expected_total),
                    actual_value=_fmt_money(total_dec),
                    status=ValidationStatus.FAILED.value,
                )
            )

    # 7. NEGATIVE_AMOUNT (WARNING)
    checked_amounts: list[tuple[str, Decimal]] = []
    for fname in ("subtotal", "tax", "total"):
        fval = _to_decimal_safe(getattr(invoice, fname, None))
        if fval is not None:
            checked_amounts.append((fname, fval))
    for idx, item in enumerate(line_items, start=1):
        line_no = getattr(item, "line_no", None) or idx
        for lfield in ("quantity", "unit_price", "amount"):
            lval = _to_decimal_safe(getattr(item, lfield, None))
            if lval is not None:
                checked_amounts.append((f"line_items[{line_no}].{lfield}", lval))

    if not checked_amounts:
        results.append(
            ValidationItem(
                validation_code="NEGATIVE_AMOUNT",
                field_name="total",
                severity=ValidationSeverity.WARNING.value,
                message="Skipped negative amount check because no monetary values were extracted.",
                expected_value=">= 0.0000",
                actual_value=None,
                status=ValidationStatus.SKIPPED.value,
            )
        )
    else:
        negatives = [(name, val) for name, val in checked_amounts if val < Decimal("0")]
        if negatives:
            neg_fields = ", ".join(name for name, _ in negatives)
            neg_vals = ", ".join(f"{name}={val}" for name, val in negatives)
            results.append(
                ValidationItem(
                    validation_code="NEGATIVE_AMOUNT",
                    field_name=negatives[0][0],
                    severity=ValidationSeverity.WARNING.value,
                    message=f"Negative amount(s) detected on {neg_fields}.",
                    expected_value=">= 0.0000",
                    actual_value=neg_vals,
                    status=ValidationStatus.FAILED.value,
                )
            )
        else:
            results.append(
                ValidationItem(
                    validation_code="NEGATIVE_AMOUNT",
                    field_name="total",
                    severity=ValidationSeverity.WARNING.value,
                    message="All extracted monetary and quantity values are non-negative.",
                    expected_value=">= 0.0000",
                    actual_value=_fmt_money(total_dec) if total_dec is not None else "non-negative",
                    status=ValidationStatus.PASSED.value,
                )
            )

    # 8. FUTURE_DATE (WARNING)
    if inv_date is None:
        results.append(
            ValidationItem(
                validation_code="FUTURE_DATE",
                field_name="invoice_date",
                severity=ValidationSeverity.WARNING.value,
                message="Skipped future date check because invoice_date is null.",
                expected_value=f"<= {today.isoformat()}",
                actual_value=None,
                status=ValidationStatus.SKIPPED.value,
            )
        )
    elif inv_date > today:
        results.append(
            ValidationItem(
                validation_code="FUTURE_DATE",
                field_name="invoice_date",
                severity=ValidationSeverity.WARNING.value,
                message=f"Invoice date {inv_date.isoformat()} is in the future (today is {today.isoformat()}).",
                expected_value=f"<= {today.isoformat()}",
                actual_value=inv_date.isoformat(),
                status=ValidationStatus.FAILED.value,
            )
        )
    else:
        results.append(
            ValidationItem(
                validation_code="FUTURE_DATE",
                field_name="invoice_date",
                severity=ValidationSeverity.WARNING.value,
                message="Invoice date is not in the future.",
                expected_value=f"<= {today.isoformat()}",
                actual_value=inv_date.isoformat(),
                status=ValidationStatus.PASSED.value,
            )
        )

    # 9. UNKNOWN_CURRENCY (INFO)
    currency_val = (getattr(invoice, "currency", None) or "").strip().upper() or None
    currency_raw = norm_meta.get("currency_raw")
    currency_ambiguous = bool(norm_meta.get("currency_ambiguous"))
    if currency_val and currency_val in VALID_ISO_CURRENCIES:
        results.append(
            ValidationItem(
                validation_code="UNKNOWN_CURRENCY",
                field_name="currency",
                severity=ValidationSeverity.INFO.value,
                message=f"Currency resolved to ISO code '{currency_val}'.",
                expected_value="ISO-4217 code",
                actual_value=currency_val,
                status=ValidationStatus.PASSED.value,
            )
        )
    else:
        reason = (
            f"Currency symbol '{currency_raw}' is ambiguous without an explicit ISO code."
            if currency_ambiguous
            else "Currency is missing or could not be mapped to an unambiguous ISO-4217 code."
        )
        results.append(
            ValidationItem(
                validation_code="UNKNOWN_CURRENCY",
                field_name="currency",
                severity=ValidationSeverity.INFO.value,
                message=reason,
                expected_value="ISO-4217 code",
                actual_value=str(currency_raw) if currency_raw is not None else None,
                status=ValidationStatus.FAILED.value,
            )
        )

    # 10. LOW_OCR_CONFIDENCE (INFO)
    ocr_avg_raw = meta.get("ocr_confidence_avg")
    ocr_avg_dec: Optional[Decimal] = None
    if ocr_avg_raw is not None:
        try:
            ocr_avg_dec = Decimal(str(ocr_avg_raw))
        except InvalidOperation:
            ocr_avg_dec = None
    ocr_threshold_dec = Decimal(str(cfg.OCR_LOW_CONFIDENCE_THRESHOLD))
    if ocr_avg_dec is None:
        results.append(
            ValidationItem(
                validation_code="LOW_OCR_CONFIDENCE",
                field_name="ocr_confidence",
                severity=ValidationSeverity.INFO.value,
                message="Skipped OCR confidence check because OCR was not used on this document.",
                expected_value=f">= {ocr_threshold_dec}",
                actual_value=None,
                status=ValidationStatus.SKIPPED.value,
            )
        )
    elif ocr_avg_dec < ocr_threshold_dec:
        results.append(
            ValidationItem(
                validation_code="LOW_OCR_CONFIDENCE",
                field_name="ocr_confidence",
                severity=ValidationSeverity.INFO.value,
                message=(
                    f"Average OCR confidence ({ocr_avg_dec}) is below threshold "
                    f"({ocr_threshold_dec})."
                ),
                expected_value=f">= {ocr_threshold_dec}",
                actual_value=str(ocr_avg_dec),
                status=ValidationStatus.FAILED.value,
            )
        )
    else:
        results.append(
            ValidationItem(
                validation_code="LOW_OCR_CONFIDENCE",
                field_name="ocr_confidence",
                severity=ValidationSeverity.INFO.value,
                message=f"Average OCR confidence ({ocr_avg_dec}) meets threshold ({ocr_threshold_dec}).",
                expected_value=f">= {ocr_threshold_dec}",
                actual_value=str(ocr_avg_dec),
                status=ValidationStatus.PASSED.value,
            )
        )

    # 11. DUPLICATE_INVOICE (WARNING, never blocks)
    dup_key = build_duplicate_key(
        supplier_name=getattr(invoice, "supplier_name", None),
        invoice_number=getattr(invoice, "invoice_number", None),
        invoice_date=inv_date,
        total=total_dec,
    )
    dup_ids = [str(d) for d in (duplicate_document_ids or [])]
    if dup_key is None:
        results.append(
            ValidationItem(
                validation_code="DUPLICATE_INVOICE",
                field_name="invoice_number",
                severity=ValidationSeverity.WARNING.value,
                message="Skipped duplicate check because one or more key fields (supplier, invoice_number, invoice_date, total) are missing.",
                expected_value="no duplicate document",
                actual_value=None,
                status=ValidationStatus.SKIPPED.value,
            )
        )
    elif dup_ids:
        joined_ids = ",".join(dup_ids)
        results.append(
            ValidationItem(
                validation_code="DUPLICATE_INVOICE",
                field_name="invoice_number",
                severity=ValidationSeverity.WARNING.value,
                message=f"Exact duplicate invoice detected matching document(s): {joined_ids}.",
                expected_value="no duplicate document",
                actual_value=joined_ids,
                status=ValidationStatus.FAILED.value,
            )
        )
    else:
        results.append(
            ValidationItem(
                validation_code="DUPLICATE_INVOICE",
                field_name="invoice_number",
                severity=ValidationSeverity.WARNING.value,
                message="No duplicate invoice found.",
                expected_value="no duplicate document",
                actual_value=None,
                status=ValidationStatus.PASSED.value,
            )
        )

    return results

