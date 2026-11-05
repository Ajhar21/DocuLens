import { describe, expect, it } from "vitest";
import {
  autoSuggestColumnMapping,
  normalizeHeader,
} from "../auto-suggest";

describe("Column Mapping Auto-Suggestion", () => {
  it("normalizes header strings into snake_case tokens", () => {
    expect(normalizeHeader("Invoice Number")).toBe("invoice_number");
    expect(normalizeHeader("Inv No.")).toBe("inv_no");
    expect(normalizeHeader("Total  Amount ($)")).toBe("total_amount");
    expect(normalizeHeader("Vendor-Name")).toBe("vendor_name");
  });

  it("auto-suggests standard invoice headers from exact matches", () => {
    const columns = [
      "invoice_number",
      "supplier_name",
      "customer_name",
      "invoice_date",
      "subtotal",
      "tax",
      "total",
      "currency",
    ];
    const mapping = autoSuggestColumnMapping(columns);

    expect(mapping.invoice_number).toBe("invoice_number");
    expect(mapping.supplier_name).toBe("supplier_name");
    expect(mapping.customer_name).toBe("customer_name");
    expect(mapping.invoice_date).toBe("invoice_date");
    expect(mapping.subtotal).toBe("subtotal");
    expect(mapping.tax).toBe("tax");
    expect(mapping.total).toBe("total");
    expect(mapping.currency).toBe("currency");
  });

  it("maps colloquial and accounting aliases correctly", () => {
    const columns = [
      "Doc Ref",
      "Vendor Title",
      "Booking Date",
      "Net Amount",
      "VAT Amount",
      "Gross Total",
      "Curr Code",
    ];
    const mapping = autoSuggestColumnMapping(columns);

    expect(mapping.invoice_number).toBe("Doc Ref");
    expect(mapping.supplier_name).toBe("Vendor Title");
    expect(mapping.invoice_date).toBe("Booking Date");
    expect(mapping.subtotal).toBe("Net Amount");
    expect(mapping.tax).toBe("VAT Amount");
    expect(mapping.total).toBe("Gross Total");
    expect(mapping.currency).toBe("Curr Code");
  });

  it("leaves unmapped fields empty when no match exists", () => {
    const columns = ["Item ID", "Qty", "Unit Price", "Inv #"];
    const mapping = autoSuggestColumnMapping(columns);

    expect(mapping.invoice_number).toBe("Inv #");
    expect(mapping.supplier_name).toBeUndefined();
    expect(mapping.total).toBeUndefined();
  });

  it("prevents duplicate column assignment", () => {
    const columns = ["Amount", "Total Amount"];
    const mapping = autoSuggestColumnMapping(columns);

    // Total should get mapped to one, subtotal won't greedily take the same column
    expect(mapping.total).toBeDefined();
    if (mapping.subtotal) {
      expect(mapping.subtotal).not.toBe(mapping.total);
    }
  });
});

