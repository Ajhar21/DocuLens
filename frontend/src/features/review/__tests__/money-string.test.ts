import { describe, expect, it } from "vitest";
import {
  buildDirtyCorrections,
  normalizeMoneyString,
  type HeaderFormValues,
} from "../corrections-builder";

describe("corrections builder & money-string preservation", () => {
  const baseValues: HeaderFormValues = {
    invoice_number: "INV-2026-001",
    invoice_date: "2026-11-01",
    supplier_name: "Acme Corp",
    customer_name: "Global Logistics",
    subtotal: "1000.00",
    tax: "150.00",
    total: "1150.00",
    currency: "USD",
  };

  it("normalizes money strings without converting to float or altering digits", () => {
    expect(normalizeMoneyString("  1234.5678  ")).toBe("1234.5678");
    expect(normalizeMoneyString("0.0001")).toBe("0.0001");
    expect(normalizeMoneyString("9999999999999999.99")).toBe("9999999999999999.99");
    expect(normalizeMoneyString(null)).toBe("");
    expect(normalizeMoneyString(undefined)).toBe("");
  });

  it("returns an empty array when no fields are modified", () => {
    const dirty = buildDirtyCorrections(baseValues, { ...baseValues });
    expect(dirty).toEqual([]);
  });

  it("identifies only dirty fields and retains money string representations", () => {
    const modified: HeaderFormValues = {
      ...baseValues,
      total: "1250.50", // Modified money field
      invoice_number: "INV-2026-999", // Modified text field
    };

    const dirty = buildDirtyCorrections(baseValues, modified, {
      total: "Updated total with shipping",
    });

    expect(dirty).toHaveLength(2);
    expect(dirty).toEqual([
      {
        field_name: "invoice_number",
        corrected_value: "INV-2026-999",
        reason: undefined,
      },
      {
        field_name: "total",
        corrected_value: "1250.50",
        reason: "Updated total with shipping",
      },
    ]);
  });

  it("does not falsely mark trimmed equal money values as dirty", () => {
    const modified: HeaderFormValues = {
      ...baseValues,
      subtotal: " 1000.00 ", // Only whitespace differs
    };

    const dirty = buildDirtyCorrections(baseValues, modified);
    expect(dirty).toEqual([]);
  });

  it("submits null when a field is cleared", () => {
    const modified: HeaderFormValues = {
      ...baseValues,
      customer_name: "",
    };

    const dirty = buildDirtyCorrections(baseValues, modified);
    expect(dirty).toEqual([
      {
        field_name: "customer_name",
        corrected_value: null,
        reason: undefined,
      },
    ]);
  });
});

