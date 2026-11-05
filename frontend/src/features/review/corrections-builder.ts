import type { CorrectionItem } from "@/lib/api/types";

export const EDITABLE_HEADER_FIELDS = [
  "invoice_number",
  "invoice_date",
  "supplier_name",
  "customer_name",
  "subtotal",
  "tax",
  "total",
  "currency",
] as const;

export type EditableHeaderField = (typeof EDITABLE_HEADER_FIELDS)[number];

export interface HeaderFormValues {
  invoice_number: string;
  invoice_date: string;
  supplier_name: string;
  customer_name: string;
  subtotal: string;
  tax: string;
  total: string;
  currency: string;
}

export type FieldReasons = Partial<Record<EditableHeaderField, string>>;

/**
 * Normalizes amount string input safely WITHOUT converting to float or Number.
 * Preserves user digits and decimals while trimming leading/trailing whitespace.
 */
export function normalizeMoneyString(val: string | null | undefined): string {
  if (val === null || val === undefined) return "";
  return String(val).trim();
}

/**
 * Normalizes a field value for dirty comparison.
 */
function normalizeFieldValue(
  field: EditableHeaderField,
  val: string | null | undefined,
): string {
  if (val === null || val === undefined) return "";
  const trimmed = String(val).trim();
  if (field === "subtotal" || field === "tax" || field === "total") {
    return normalizeMoneyString(trimmed);
  }
  return trimmed;
}

/**
 * Builds the correction payload containing ONLY dirty/modified fields.
 *
 * Requirements:
 * - Money values handled as strings end-to-end (never parseFloat/Number).
 * - Only dirty fields submitted.
 * - Optional reason per field included when provided.
 */
export function buildDirtyCorrections(
  initial: Partial<HeaderFormValues>,
  current: HeaderFormValues,
  reasons: FieldReasons = {},
): CorrectionItem[] {
  const dirtyItems: CorrectionItem[] = [];

  for (const field of EDITABLE_HEADER_FIELDS) {
    const initNorm = normalizeFieldValue(field, initial[field]);
    const currNorm = normalizeFieldValue(field, current[field]);

    if (initNorm !== currNorm) {
      const reasonText = reasons[field]?.trim() || undefined;
      dirtyItems.push({
        field_name: field,
        // Send string or null if empty
        corrected_value: currNorm === "" ? null : currNorm,
        reason: reasonText,
      });
    }
  }

  return dirtyItems;
}

