/**
 * Pure column mapping auto-suggestion helper.
 * Normalizes spreadsheet column headers and matches them to standard invoice fields.
 */

export interface InvoiceFieldDef {
  key: string;
  label: string;
  required?: boolean;
}

export const INVOICE_FIELDS: InvoiceFieldDef[] = [
  { key: "invoice_number", label: "Invoice Number", required: true },
  { key: "supplier_name", label: "Supplier / Vendor Name" },
  { key: "customer_name", label: "Customer / Client Name" },
  { key: "invoice_date", label: "Invoice Date" },
  { key: "subtotal", label: "Subtotal / Net Amount" },
  { key: "tax", label: "Tax / VAT / GST" },
  { key: "total", label: "Total / Gross Amount" },
  { key: "currency", label: "Currency" },
];

const ALIAS_MAP: Record<string, string[]> = {
  invoice_number: [
    "invoice_number",
    "invoice_no",
    "inv_num",
    "inv_no",
    "inv",
    "invoice",
    "doc_ref",
    "doc_number",
    "document_number",
    "bill_no",
    "bill_number",
    "reference",
    "ref_no",
  ],
  supplier_name: [
    "supplier_name",
    "supplier",
    "vendor_name",
    "vendor_title",
    "vendor",
    "seller",
    "payee",
    "creditor",
  ],
  customer_name: [
    "customer_name",
    "customer",
    "client_name",
    "client",
    "buyer",
    "bill_to",
    "debtor",
  ],
  invoice_date: [
    "invoice_date",
    "inv_date",
    "booking_date",
    "billing_date",
    "bill_date",
    "doc_date",
    "date",
    "txn_date",
  ],
  subtotal: [
    "subtotal",
    "sub_total",
    "net_amount",
    "net_total",
    "net",
    "base_amount",
  ],
  tax: ["tax", "tax_amount", "vat", "vat_amount", "gst", "hst", "sales_tax"],
  total: [
    "total",
    "total_amount",
    "gross_total",
    "gross_amount",
    "amount",
    "final_amount",
    "grand_total",
    "balance",
  ],
  currency: ["currency", "curr", "currency_code", "curr_code", "iso_curr"],
};

export function normalizeHeader(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^\w]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Returns suggested column mapping { [invoiceFieldKey]: sheetColumnHeader }.
 * Maps each invoice field to at most one sheet column based on recognized aliases.
 */
export function autoSuggestColumnMapping(
  sheetColumns: string[],
): Record<string, string> {
  const mapping: Record<string, string> = {};
  const usedColumns = new Set<string>();

  // Map normalized sheet column -> original sheet column name
  const normalizedSheetCols: { original: string; norm: string }[] = sheetColumns
    .filter((col) => typeof col === "string" && col.trim().length > 0)
    .map((original) => ({
      original,
      norm: normalizeHeader(original),
    }));

  for (const field of INVOICE_FIELDS) {
    const aliases = ALIAS_MAP[field.key] || [];

    // 1. Try exact normalized match
    let matched: string | null = null;
    for (const alias of aliases) {
      const candidate = normalizedSheetCols.find(
        (c) => c.norm === alias && !usedColumns.has(c.original),
      );
      if (candidate) {
        matched = candidate.original;
        break;
      }
    }

    // 2. If no exact match, try contains match for specific long patterns
    if (!matched) {
      for (const alias of aliases) {
        if (alias.length < 4) continue; // Skip short aliases to prevent false positives like "in"
        const candidate = normalizedSheetCols.find(
          (c) =>
            (c.norm.includes(alias) || alias.includes(c.norm)) &&
            !usedColumns.has(c.original),
        );
        if (candidate) {
          matched = candidate.original;
          break;
        }
      }
    }

    if (matched) {
      mapping[field.key] = matched;
      usedColumns.add(matched);
    }
  }

  return mapping;
}

