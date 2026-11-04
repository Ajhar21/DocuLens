const BYTE_UNITS = ["B", "KB", "MB", "GB"] as const;

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    BYTE_UNITS.length - 1,
  );
  const value = bytes / 1024 ** exponent;
  const formatted =
    exponent === 0 || value >= 100
      ? Math.round(value).toString()
      : value >= 10
        ? value.toFixed(1)
        : value.toFixed(2);
  return `${formatted} ${BYTE_UNITS[exponent] ?? "B"}`;
}

const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return dateTimeFormatter.format(date);
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;

  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;

  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;

  const diffDays = Math.floor(diffHr / 24);
  if (diffDays < 30) return `${diffDays}d ago`;

  return formatDateTime(iso);
}

export function getInitials(fullName: string): string {
  const parts = fullName
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return "U";
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/** Standard ISO-4217 currency codes supported for Intl.NumberFormat formatting */
export const VALID_ISO_CURRENCIES: ReadonlySet<string> = new Set([
  "USD", "EUR", "GBP", "BDT", "CAD", "AUD", "JPY", "CHF", "CNY", "INR",
  "SGD", "HKD", "NZD", "SEK", "NOK", "DKK", "AED", "SAR", "MYR", "THB",
  "ZAR", "BRL", "MXN", "KRW", "PKR", "LKR", "NPR", "PLN", "CZK", "HUF",
  "TRY", "ILS", "PHP", "IDR", "VND", "EGP", "NGN", "KES", "QAR", "KWD",
  "BHD", "OMR",
]);

/**
 * Format money values strictly:
 * - No arithmetic in frontend.
 * - Uses Intl.NumberFormat only when currency is a recognized ISO code.
 * - Otherwise outputs exact string with currency text or "currency unknown".
 */
export function formatMoney(
  amount: string | number | null | undefined,
  currency: string | null | undefined,
): string {
  if (amount === null || amount === undefined || amount === "") {
    return "Not found";
  }

  const rawAmountStr = String(amount).trim();
  if (!rawAmountStr) {
    return "Not found";
  }

  const normCurrency = (currency || "").trim().toUpperCase();

  if (normCurrency && VALID_ISO_CURRENCIES.has(normCurrency)) {
    const num = Number.parseFloat(rawAmountStr);
    if (!Number.isNaN(num)) {
      try {
        return new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: normCurrency,
        }).format(num);
      } catch {
        // Fallback to exact representation
      }
    }
    return `${rawAmountStr} ${normCurrency}`;
  }

  if (normCurrency) {
    return `${rawAmountStr} ${normCurrency}`;
  }

  return `${rawAmountStr} (currency unknown)`;
}

const UUID_REGEX = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

/**
 * Pure helper to extract valid UUIDs for duplicate invoice links.
 * Checks both actual_value and message text.
 */
export function extractDuplicateDocumentIds(
  actualValue: string | null | undefined,
  message: string | null | undefined,
): string[] {
  const matches = new Set<string>();

  if (actualValue) {
    const found = actualValue.match(UUID_REGEX);
    if (found) {
      for (const id of found) {
        matches.add(id.toLowerCase());
      }
    }
  }

  if (message) {
    const found = message.match(UUID_REGEX);
    if (found) {
      for (const id of found) {
        matches.add(id.toLowerCase());
      }
    }
  }

  return Array.from(matches);
}
