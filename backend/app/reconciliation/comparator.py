from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Optional, Sequence

LEGAL_SUFFIXES_REGEX = re.compile(
    r"\b(ltd|llc|inc|corp|co|limited|corporation|incorporated)\b\.?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FieldComparison:
    entity_type: str
    field_name: str
    source_a_value: Optional[str]
    source_b_value: Optional[str]
    match_status: str
    absolute_difference: Optional[Decimal] = None
    percentage_difference: Optional[Decimal] = None


@dataclass(frozen=True)
class ComparisonResult:
    overall_status: str
    discrepancy_count: int
    results: list[FieldComparison]


def to_decimal(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    try:
        clean = str(val).strip().replace(",", "")
        if not clean:
            return None
        return Decimal(clean)
    except (InvalidOperation, ValueError):
        return None


def to_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        clean = val.strip()
        if not clean:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(clean, fmt).date()
            except ValueError:
                continue
    return None


def normalize_supplier_name(val: Optional[str]) -> str:
    """Normalize supplier name: lowercase, strip legal suffixes, punctuation, collapse whitespace."""
    if not val:
        return ""
    text = str(val).lower()
    text = LEGAL_SUFFIXES_REGEX.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_string(val: Optional[str]) -> str:
    if not val:
        return ""
    return re.sub(r"\s+", " ", str(val).strip().lower())


def compare_amount(
    field_name: str,
    val_a: Optional[Decimal],
    val_b: Optional[Decimal],
    tol_abs: Decimal,
    tol_pct: Decimal,
    *,
    entity_type: str = "HEADER",
    allow_null_not_comparable: bool = False,
) -> FieldComparison:
    str_a = str(val_a.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)) if val_a is not None else None
    str_b = str(val_b.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)) if val_b is not None else None

    # Subtotal and tax null in either document -> NOT_COMPARABLE
    if allow_null_not_comparable and (val_a is None or val_b is None):
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=str_a,
            source_b_value=str_b,
            match_status="NOT_COMPARABLE",
        )

    if val_a is None and val_b is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=None,
            source_b_value=None,
            match_status="EXACT_MATCH",
        )
    if val_a is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=None,
            source_b_value=str_b,
            match_status="MISSING_IN_A",
        )
    if val_b is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=str_a,
            source_b_value=None,
            match_status="MISSING_IN_B",
        )

    diff_abs = abs(val_a - val_b).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if val_a != 0:
        diff_pct = (diff_abs / abs(val_a)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    else:
        diff_pct = Decimal("0.0000") if val_b == 0 else Decimal("1.0000")

    if diff_abs == Decimal("0.0000"):
        status = "EXACT_MATCH"
    elif diff_abs <= tol_abs or diff_pct <= tol_pct:
        status = "TOLERANCE_MATCH"
    else:
        status = "MISMATCH"

    return FieldComparison(
        entity_type=entity_type,
        field_name=field_name,
        source_a_value=str_a,
        source_b_value=str_b,
        match_status=status,
        absolute_difference=diff_abs,
        percentage_difference=diff_pct,
    )


def compare_date(
    field_name: str,
    val_a: Optional[date],
    val_b: Optional[date],
    tolerance_days: int = 0,
    *,
    entity_type: str = "HEADER",
) -> FieldComparison:
    str_a = val_a.isoformat() if val_a is not None else None
    str_b = val_b.isoformat() if val_b is not None else None

    if val_a is None and val_b is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=None,
            source_b_value=None,
            match_status="EXACT_MATCH",
        )
    if val_a is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=None,
            source_b_value=str_b,
            match_status="MISSING_IN_A",
        )
    if val_b is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=str_a,
            source_b_value=None,
            match_status="MISSING_IN_B",
        )

    diff_days = abs((val_a - val_b).days)
    if diff_days == 0:
        status = "EXACT_MATCH"
    elif diff_days <= tolerance_days:
        status = "TOLERANCE_MATCH"
    else:
        status = "MISMATCH"

    return FieldComparison(
        entity_type=entity_type,
        field_name=field_name,
        source_a_value=str_a,
        source_b_value=str_b,
        match_status=status,
        absolute_difference=Decimal(str(diff_days)),
    )


def compare_text(
    field_name: str,
    val_a: Optional[str],
    val_b: Optional[str],
    *,
    entity_type: str = "HEADER",
    is_supplier: bool = False,
    allow_null_not_comparable: bool = False,
) -> FieldComparison:
    str_a = str(val_a).strip() if val_a is not None else None
    str_b = str(val_b).strip() if val_b is not None else None

    if allow_null_not_comparable and (str_a is None or str_b is None):
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=str_a,
            source_b_value=str_b,
            match_status="NOT_COMPARABLE",
        )

    if str_a is None and str_b is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=None,
            source_b_value=None,
            match_status="EXACT_MATCH",
        )
    if str_a is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=None,
            source_b_value=str_b,
            match_status="MISSING_IN_A",
        )
    if str_b is None:
        return FieldComparison(
            entity_type=entity_type,
            field_name=field_name,
            source_a_value=str_a,
            source_b_value=None,
            match_status="MISSING_IN_B",
        )

    if is_supplier:
        norm_a = normalize_supplier_name(str_a)
        norm_b = normalize_supplier_name(str_b)
    else:
        norm_a = normalize_string(str_a)
        norm_b = normalize_string(str_b)

    status = "EXACT_MATCH" if norm_a == norm_b else "MISMATCH"

    return FieldComparison(
        entity_type=entity_type,
        field_name=field_name,
        source_a_value=str_a,
        source_b_value=str_b,
        match_status=status,
    )


def compare_invoices(
    invoice_a: dict[str, Any],
    invoice_b: dict[str, Any],
    *,
    amount_tolerance_abs: Decimal = Decimal("0.05"),
    amount_tolerance_pct: Decimal = Decimal("0.001"),
    date_tolerance_days: int = 0,
) -> ComparisonResult:
    """Pure comparator for two invoices (PDF-PDF or PDF-Excel).

    Isolates comparison rules into a pure function with zero DB/network calls.
    Uses strictly Decimal arithmetic and returns an overall status and field results.
    """
    results: list[FieldComparison] = []

    # 1. Invoice Number
    results.append(
        compare_text(
            "invoice_number",
            invoice_a.get("invoice_number"),
            invoice_b.get("invoice_number"),
        )
    )

    # 2. Supplier Name (with legal suffix stripping)
    results.append(
        compare_text(
            "supplier_name",
            invoice_a.get("supplier_name"),
            invoice_b.get("supplier_name"),
            is_supplier=True,
        )
    )

    # 3. Customer Name
    results.append(
        compare_text(
            "customer_name",
            invoice_a.get("customer_name"),
            invoice_b.get("customer_name"),
            allow_null_not_comparable=True,
        )
    )

    # 4. Invoice Date
    results.append(
        compare_date(
            "invoice_date",
            to_date(invoice_a.get("invoice_date")),
            to_date(invoice_b.get("invoice_date")),
            tolerance_days=date_tolerance_days,
        )
    )

    # 5. Subtotal (null in either -> NOT_COMPARABLE)
    results.append(
        compare_amount(
            "subtotal",
            to_decimal(invoice_a.get("subtotal")),
            to_decimal(invoice_b.get("subtotal")),
            amount_tolerance_abs,
            amount_tolerance_pct,
            allow_null_not_comparable=True,
        )
    )

    # 6. Tax (null in either -> NOT_COMPARABLE)
    results.append(
        compare_amount(
            "tax",
            to_decimal(invoice_a.get("tax")),
            to_decimal(invoice_b.get("tax")),
            amount_tolerance_abs,
            amount_tolerance_pct,
            allow_null_not_comparable=True,
        )
    )

    # 7. Total
    results.append(
        compare_amount(
            "total",
            to_decimal(invoice_a.get("total")),
            to_decimal(invoice_b.get("total")),
            amount_tolerance_abs,
            amount_tolerance_pct,
            allow_null_not_comparable=False,
        )
    )

    # 8. Currency
    results.append(
        compare_text(
            "currency",
            invoice_a.get("currency"),
            invoice_b.get("currency"),
            allow_null_not_comparable=True,
        )
    )

    # 9. Line Items comparison
    lines_a = list(invoice_a.get("line_items") or [])
    lines_b = list(invoice_b.get("line_items") or [])

    # Index lines_b by normalized description and line_no
    unmatched_b = list(enumerate(lines_b))

    for idx_a, item_a in enumerate(lines_a, start=1):
        desc_a = normalize_string(item_a.get("description") or item_a.get("item_description"))
        line_no_a = item_a.get("line_no")

        # Find best match in unmatched_b
        best_match_idx: Optional[int] = None
        for b_pos, (orig_idx_b, item_b) in enumerate(unmatched_b):
            desc_b = normalize_string(item_b.get("description") or item_b.get("item_description"))
            line_no_b = item_b.get("line_no")
            if desc_a and desc_b and desc_a == desc_b:
                best_match_idx = b_pos
                break
            if line_no_a is not None and line_no_b is not None and line_no_a == line_no_b:
                best_match_idx = b_pos
                break

        line_prefix = f"line_items[{idx_a}]"
        if best_match_idx is not None:
            _, item_b = unmatched_b.pop(best_match_idx)
            # Compare description
            results.append(
                compare_text(
                    f"{line_prefix}.description",
                    item_a.get("description") or item_a.get("item_description"),
                    item_b.get("description") or item_b.get("item_description"),
                    entity_type="LINE_ITEM",
                )
            )
            # Compare quantity
            results.append(
                compare_amount(
                    f"{line_prefix}.quantity",
                    to_decimal(item_a.get("quantity")),
                    to_decimal(item_b.get("quantity")),
                    amount_tolerance_abs,
                    amount_tolerance_pct,
                    entity_type="LINE_ITEM",
                    allow_null_not_comparable=True,
                )
            )
            # Compare unit_price
            results.append(
                compare_amount(
                    f"{line_prefix}.unit_price",
                    to_decimal(item_a.get("unit_price")),
                    to_decimal(item_b.get("unit_price")),
                    amount_tolerance_abs,
                    amount_tolerance_pct,
                    entity_type="LINE_ITEM",
                    allow_null_not_comparable=True,
                )
            )
            # Compare amount
            results.append(
                compare_amount(
                    f"{line_prefix}.amount",
                    to_decimal(item_a.get("amount")),
                    to_decimal(item_b.get("amount")),
                    amount_tolerance_abs,
                    amount_tolerance_pct,
                    entity_type="LINE_ITEM",
                )
            )
        else:
            # Missing in B
            results.append(
                FieldComparison(
                    entity_type="LINE_ITEM",
                    field_name=f"{line_prefix}",
                    source_a_value=str(item_a.get("description") or item_a.get("amount")),
                    source_b_value=None,
                    match_status="MISSING_IN_B",
                )
            )

    # Remaining items in B that were not matched in A
    for orig_idx_b, item_b in unmatched_b:
        results.append(
            FieldComparison(
                entity_type="LINE_ITEM",
                field_name=f"line_items[b_{orig_idx_b + 1}]",
                source_a_value=None,
                source_b_value=str(item_b.get("description") or item_b.get("amount")),
                match_status="MISSING_IN_A",
            )
        )

    # Calculate discrepancies: MISMATCH, MISSING_IN_A, MISSING_IN_B
    discrepancy_count = sum(
        1 for r in results if r.match_status in ("MISMATCH", "MISSING_IN_A", "MISSING_IN_B")
    )
    overall_status = "MATCHED" if discrepancy_count == 0 else "MISMATCHED"

    return ComparisonResult(
        overall_status=overall_status,
        discrepancy_count=discrepancy_count,
        results=results,
    )

