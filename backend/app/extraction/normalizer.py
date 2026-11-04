from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Optional

ISO_CURRENCIES: set[str] = {
    "USD", "EUR", "GBP", "BDT", "CAD", "AUD", "JPY", "CHF", "CNY", "INR",
    "SGD", "HKD", "NZD", "SEK", "NOK", "DKK", "AED", "SAR", "MYR", "THB",
    "ZAR", "BRL", "MXN", "KRW", "PKR", "LKR", "NPR", "PLN", "CZK", "HUF",
    "TRY", "ILS", "PHP", "IDR", "VND", "EGP", "NGN", "KES", "QAR", "KWD",
    "BHD", "OMR",
}

UNAMBIGUOUS_CURRENCY_MAP: dict[str, str] = {
    "€": "EUR",
    "EUR": "EUR",
    "EURO": "EUR",
    "EUROS": "EUR",
    "£": "GBP",
    "GBP": "GBP",
    "৳": "BDT",
    "BDT": "BDT",
    "TK": "BDT",
    "TK.": "BDT",
    "TAKA": "BDT",
    "US$": "USD",
    "USD$": "USD",
    "U.S.$": "USD",
    "CA$": "CAD",
    "CAD$": "CAD",
    "C$": "CAD",
    "A$": "AUD",
    "AU$": "AUD",
    "AUD$": "AUD",
    "NZ$": "NZD",
    "NZD$": "NZD",
    "S$": "SGD",
    "SGD$": "SGD",
    "HK$": "HKD",
    "HKD$": "HKD",
    "₹": "INR",
    "RS.": "INR",
}

AMBIGUOUS_CURRENCY_SYMBOLS: set[str] = {"$", "¥"}

_CURRENCY_STRIP_RE = re.compile(
    r"(?:US\$|USD\$|U\.S\.\$|CA\$|CAD\$|AU\$|AUD\$|NZ\$|NZD\$|HK\$|HKD\$|SGD\$|C\$|A\$|S\$|"
    r"TK\.?|TAKA|[€£৳$¥₹])",
    flags=re.IGNORECASE,
)

_ISO_CODE_WORD_RE = re.compile(
    r"\b(" + "|".join(sorted(ISO_CURRENCIES)) + r")\b",
    flags=re.IGNORECASE,
)

_NAMED_DATE_FORMATS: tuple[str, ...] = (
    "%d %b %Y",
    "%d %B %Y",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%b %d %Y",
    "%B %d %Y",
    "%d %b, %Y",
    "%d %B, %Y",
    "%Y %b %d",
    "%Y %B %d",
)


@dataclass(frozen=True)
class DateNormalizationResult:
    value: Optional[date]
    is_ambiguous: bool = False
    raw_value: Optional[str] = None
    parse_failed: bool = False


@dataclass(frozen=True)
class CurrencyNormalizationResult:
    value: Optional[str]
    is_ambiguous: bool = False
    raw_value: Optional[str] = None


def normalize_decimal(raw: Optional[str | int | Decimal], scale: int = 4) -> Optional[Decimal]:
    """Normalize a printed monetary or quantity string to Decimal.

    Rules:
    - Never accepts float.
    - Strips currency symbols, ISO codes, and whitespace.
    - Accounting parentheses '(1,234.56)' or trailing/leading '-' => negative.
    - Standard thousand separators '1,234,567.89' and unambiguous European comma-decimal
      '1.234,56' or '123,45' are supported.
    - Returns None when input is null, empty, or ambiguous/unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, float):
        raise TypeError("Floats are forbidden for monetary/quantity values; pass str or Decimal")
    if isinstance(raw, Decimal):
        quant = Decimal("10") ** (-scale)
        return raw.quantize(quant, rounding=ROUND_HALF_UP)
    if isinstance(raw, int):
        quant = Decimal("10") ** (-scale)
        return Decimal(raw).quantize(quant, rounding=ROUND_HALF_UP)

    text = str(raw).strip()
    if not text:
        return None

    is_negative = False
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1].strip()

    # Strip known currency symbols and ISO currency codes
    text = _CURRENCY_STRIP_RE.sub("", text)
    text = _ISO_CODE_WORD_RE.sub("", text)
    text = text.strip()

    # Check again for parentheses if currency symbol was outside: e.g. $(1,234.56)
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1].strip()

    if text.startswith("-"):
        is_negative = not is_negative
        text = text[1:].strip()
    elif text.endswith("-"):
        is_negative = not is_negative
        text = text[:-1].strip()
    elif text.startswith("+"):
        text = text[1:].strip()

    # Remove spaces / non-breaking spaces used as thousand separators
    text = text.replace("\u00a0", "").replace(" ", "")
    if not text:
        return None

    # Validate allowed characters (digits, comma, dot)
    if not re.fullmatch(r"[0-9.,]+", text):
        return None

    has_comma = "," in text
    has_dot = "." in text

    if has_comma and has_dot:
        last_comma = text.rfind(",")
        last_dot = text.rfind(".")
        if last_dot > last_comma:
            # Standard format: 1,234,567.89 (commas in integer part, single dot as decimal)
            if text.count(".") > 1:
                return None
            int_part, frac_part = text.split(".")
            groups = int_part.split(",")
            if not groups[0].isdigit() or len(groups[0]) > 3:
                return None
            if any(len(g) != 3 or not g.isdigit() for g in groups[1:]):
                return None
            canonical = "".join(groups) + "." + frac_part
        else:
            # European format: 1.234.567,89 (dots in integer part, single comma as decimal)
            if text.count(",") > 1:
                return None
            int_part, frac_part = text.split(",")
            groups = int_part.split(".")
            if not groups[0].isdigit() or len(groups[0]) > 3:
                return None
            if any(len(g) != 3 or not g.isdigit() for g in groups[1:]):
                return None
            canonical = "".join(groups) + "." + frac_part
    elif has_comma and not has_dot:
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            # Unambiguous comma-decimal: e.g. 123,45 or 0,5
            if not parts[0].isdigit() or not parts[1].isdigit():
                return None
            canonical = f"{parts[0]}.{parts[1]}"
        else:
            # Thousand-separated integer: e.g. 1,000 or 1,234,567
            if not parts[0].isdigit() or len(parts[0]) == 0 or len(parts[0]) > 3:
                return None
            if any(len(g) != 3 or not g.isdigit() for g in parts[1:]):
                return None
            canonical = "".join(parts)
    elif has_dot and not has_comma:
        if text.count(".") == 1:
            int_part, frac_part = text.split(".")
            if int_part == "" and frac_part == "":
                return None
            canonical = f"{int_part or '0'}.{frac_part}"
        else:
            # Multiple dots with no comma: only valid if strict 3-digit thousand groups
            parts = text.split(".")
            if not parts[0].isdigit() or len(parts[0]) == 0 or len(parts[0]) > 3:
                return None
            if any(len(g) != 3 or not g.isdigit() for g in parts[1:]):
                return None
            canonical = "".join(parts)
    else:
        canonical = text

    try:
        dec = Decimal(canonical)
    except InvalidOperation:
        return None

    if is_negative and dec != Decimal("0"):
        dec = -dec

    quant = Decimal("10") ** (-scale)
    return dec.quantize(quant, rounding=ROUND_HALF_UP)


def normalize_date(raw: Optional[str | date]) -> DateNormalizationResult:
    """Parse an invoice date string into an ISO date without guessing ambiguous dates.

    Ambiguous numeric dates where both day and month components are <= 12 and unequal
    (e.g. '03/04/2025') return value=None and is_ambiguous=True.
    """
    if raw is None:
        return DateNormalizationResult(value=None, is_ambiguous=False, raw_value=None)
    if isinstance(raw, datetime):
        return DateNormalizationResult(value=raw.date(), is_ambiguous=False, raw_value=raw.date().isoformat())
    if isinstance(raw, date):
        return DateNormalizationResult(value=raw, is_ambiguous=False, raw_value=raw.isoformat())

    text = str(raw).strip()
    if not text:
        return DateNormalizationResult(value=None, is_ambiguous=False, raw_value=None)

    # Strip optional time suffix on ISO strings (e.g. 2025-04-03T00:00:00Z)
    iso_match = re.fullmatch(
        r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?",
        text,
    )
    if iso_match:
        year, month, day = (int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        try:
            return DateNormalizationResult(
                value=date(year, month, day),
                is_ambiguous=False,
                raw_value=text,
            )
        except ValueError:
            return DateNormalizationResult(
                value=None,
                is_ambiguous=False,
                raw_value=text,
                parse_failed=True,
            )

    # Named month formats (e.g. '15 Jan 2025', 'March 4, 2025', '04-Apr-2025')
    # Normalize ordinal suffixes ('15th March 2025' -> '15 March 2025') and collapse whitespace
    cleaned_named = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    cleaned_named = re.sub(r"\s+", " ", cleaned_named).strip()
    for fmt in _NAMED_DATE_FORMATS:
        try:
            parsed_dt = datetime.strptime(cleaned_named, fmt)
            return DateNormalizationResult(
                value=parsed_dt.date(),
                is_ambiguous=False,
                raw_value=text,
            )
        except ValueError:
            continue

    # Numeric dates with 4-digit year at end: A/B/YYYY, A-B-YYYY, A.B.YYYY
    num_match = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text)
    if num_match:
        first, second, year = (
            int(num_match.group(1)),
            int(num_match.group(2)),
            int(num_match.group(3)),
        )
        if first > 12 and 1 <= second <= 12:
            # Unambiguously DD/MM/YYYY
            try:
                return DateNormalizationResult(
                    value=date(year, second, first),
                    is_ambiguous=False,
                    raw_value=text,
                )
            except ValueError:
                return DateNormalizationResult(
                    value=None,
                    is_ambiguous=False,
                    raw_value=text,
                    parse_failed=True,
                )
        if second > 12 and 1 <= first <= 12:
            # Unambiguously MM/DD/YYYY
            try:
                return DateNormalizationResult(
                    value=date(year, first, second),
                    is_ambiguous=False,
                    raw_value=text,
                )
            except ValueError:
                return DateNormalizationResult(
                    value=None,
                    is_ambiguous=False,
                    raw_value=text,
                    parse_failed=True,
                )
        if 1 <= first <= 12 and 1 <= second <= 12:
            if first == second:
                # Same day and month (e.g. 05/05/2025) => unambiguous calendar date
                try:
                    return DateNormalizationResult(
                        value=date(year, first, second),
                        is_ambiguous=False,
                        raw_value=text,
                    )
                except ValueError:
                    return DateNormalizationResult(
                        value=None,
                        is_ambiguous=False,
                        raw_value=text,
                        parse_failed=True,
                    )
            # Both <= 12 and unequal (e.g. 03/04/2025) => ambiguous!
            return DateNormalizationResult(
                value=None,
                is_ambiguous=True,
                raw_value=text,
            )
        return DateNormalizationResult(
            value=None,
            is_ambiguous=False,
            raw_value=text,
            parse_failed=True,
        )

    # Numeric dates with 2-digit year (e.g. 03/04/25 or 15/04/25) -> ambiguous year/order
    short_year_match = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})", text)
    if short_year_match:
        return DateNormalizationResult(
            value=None,
            is_ambiguous=True,
            raw_value=text,
        )

    return DateNormalizationResult(
        value=None,
        is_ambiguous=False,
        raw_value=text,
        parse_failed=True,
    )


def _match_single_currency_token(token: str) -> CurrencyNormalizationResult:
    cleaned = token.strip()
    if not cleaned:
        return CurrencyNormalizationResult(value=None, is_ambiguous=False, raw_value=None)

    upper = cleaned.upper()
    if upper in ISO_CURRENCIES:
        return CurrencyNormalizationResult(value=upper, is_ambiguous=False, raw_value=cleaned)

    if upper in UNAMBIGUOUS_CURRENCY_MAP:
        return CurrencyNormalizationResult(
            value=UNAMBIGUOUS_CURRENCY_MAP[upper],
            is_ambiguous=False,
            raw_value=cleaned,
        )

    if cleaned in UNAMBIGUOUS_CURRENCY_MAP:
        return CurrencyNormalizationResult(
            value=UNAMBIGUOUS_CURRENCY_MAP[cleaned],
            is_ambiguous=False,
            raw_value=cleaned,
        )

    if cleaned in AMBIGUOUS_CURRENCY_SYMBOLS:
        return CurrencyNormalizationResult(
            value=None,
            is_ambiguous=True,
            raw_value=cleaned,
        )

    # Check if string contains an explicit ISO code word (e.g. "USD ($)" or "Amount in EUR")
    iso_match = _ISO_CODE_WORD_RE.search(upper)
    if iso_match:
        return CurrencyNormalizationResult(
            value=iso_match.group(1).upper(),
            is_ambiguous=False,
            raw_value=cleaned,
        )

    # Check unambiguous prefixes/symbols inside string
    for sym, iso_code in UNAMBIGUOUS_CURRENCY_MAP.items():
        if len(sym) == 1 and sym in cleaned:
            return CurrencyNormalizationResult(
                value=iso_code,
                is_ambiguous=False,
                raw_value=cleaned,
            )
        if len(sym) > 1 and sym in upper:
            return CurrencyNormalizationResult(
                value=iso_code,
                is_ambiguous=False,
                raw_value=cleaned,
            )

    if any(sym in cleaned for sym in AMBIGUOUS_CURRENCY_SYMBOLS):
        return CurrencyNormalizationResult(
            value=None,
            is_ambiguous=True,
            raw_value=cleaned,
        )

    return CurrencyNormalizationResult(value=None, is_ambiguous=False, raw_value=cleaned)


def normalize_currency(
    raw: Optional[str],
    fallback_amount_strings: Optional[list[Optional[str]]] = None,
) -> CurrencyNormalizationResult:
    """Normalize currency to a 3-letter ISO code when unambiguous.

    Explicit ISO codes and unambiguous symbols (€, £, ৳, US$, CA$, A$, ₹) map to ISO codes.
    A bare '$' (without explicit ISO code) returns value=None, is_ambiguous=True.
    """
    if raw is not None and str(raw).strip():
        res = _match_single_currency_token(str(raw))
        if res.value is not None or res.is_ambiguous:
            return res

    if fallback_amount_strings:
        saw_ambiguous: Optional[str] = None
        for amt_str in fallback_amount_strings:
            if not amt_str:
                continue
            res = _match_single_currency_token(str(amt_str))
            if res.value is not None:
                return res
            if res.is_ambiguous and saw_ambiguous is None:
                saw_ambiguous = res.raw_value
        if saw_ambiguous is not None:
            return CurrencyNormalizationResult(
                value=None,
                is_ambiguous=True,
                raw_value=saw_ambiguous,
            )

    raw_clean = str(raw).strip() if raw is not None and str(raw).strip() else None
    return CurrencyNormalizationResult(value=None, is_ambiguous=False, raw_value=raw_clean)


def normalize_supplier_key(supplier_name: Optional[str]) -> Optional[str]:
    """Normalize supplier name for exact duplicate detection: lowercase, strip punctuation, collapse whitespace."""
    if not supplier_name:
        return None
    lowered = supplier_name.lower()
    # Replace punctuation/non-alphanumeric characters (preserving Unicode letters/digits) with spaces
    no_punct = re.sub(r"[^\w\s]|_", " ", lowered, flags=re.UNICODE)
    collapsed = re.sub(r"\s+", " ", no_punct).strip()
    return collapsed or None


def normalize_invoice_number_key(invoice_number: Optional[str]) -> Optional[str]:
    """Normalize invoice number for exact duplicate detection: uppercase, alphanumerics only."""
    if not invoice_number:
        return None
    upper = invoice_number.upper()
    alnum = re.sub(r"[^A-Z0-9]", "", upper)
    return alnum or None

