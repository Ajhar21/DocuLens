import { useEffect, useMemo, useState } from "react";
import { AlertCircle, AlertTriangle, History, Lock, Save } from "lucide-react";
import { useForm } from "react-hook-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  CorrectionItem,
  ExtractedInvoiceRead,
  ValidationResultRead,
} from "@/lib/api/types";
import {
  EDITABLE_HEADER_FIELDS,
  buildDirtyCorrections,
  type EditableHeaderField,
  type FieldReasons,
  type HeaderFormValues,
} from "./corrections-builder";

interface HeaderCorrectionFormProps {
  extractedInvoice: ExtractedInvoiceRead | null | undefined;
  originalLlmOutput: Record<string, unknown> | null | undefined;
  validationResults: ValidationResultRead[];
  isApproved: boolean;
  canEdit: boolean;
  isSubmitting: boolean;
  onSubmitCorrections: (corrections: CorrectionItem[]) => Promise<void>;
}

const FIELD_LABELS: Record<EditableHeaderField, string> = {
  invoice_number: "Invoice Number",
  invoice_date: "Invoice Date (YYYY-MM-DD)",
  supplier_name: "Supplier Name",
  customer_name: "Customer Name",
  subtotal: "Subtotal Amount",
  tax: "Tax Amount",
  total: "Total Amount",
  currency: "Currency (e.g. USD, EUR)",
};

export function HeaderCorrectionForm({
  extractedInvoice,
  originalLlmOutput,
  validationResults,
  isApproved,
  canEdit,
  isSubmitting,
  onSubmitCorrections,
}: HeaderCorrectionFormProps) {
  const [reasons, setReasons] = useState<FieldReasons>({});
  const [activeReasonField, setActiveReasonField] = useState<EditableHeaderField | null>(null);

  const initialValues = useMemo<HeaderFormValues>(
    () => ({
      invoice_number: extractedInvoice?.invoice_number || "",
      invoice_date: extractedInvoice?.invoice_date || "",
      supplier_name: extractedInvoice?.supplier_name || "",
      customer_name: extractedInvoice?.customer_name || "",
      subtotal:
        extractedInvoice?.subtotal != null ? String(extractedInvoice.subtotal) : "",
      tax: extractedInvoice?.tax != null ? String(extractedInvoice.tax) : "",
      total:
        extractedInvoice?.total != null ? String(extractedInvoice.total) : "",
      currency: extractedInvoice?.currency || "",
    }),
    [extractedInvoice],
  );

  const { register, handleSubmit, reset, watch } = useForm<HeaderFormValues>({
    defaultValues: initialValues,
  });

  useEffect(() => {
    reset(initialValues);
    setReasons({});
    setActiveReasonField(null);
  }, [initialValues, reset]);

  const currentWatchedValues = watch();
  const isFormDisabled = isApproved || !canEdit || isSubmitting;

  // Calculate dirty items live to show count on submit button
  const dirtyItems = buildDirtyCorrections(
    initialValues,
    currentWatchedValues,
    reasons,
  );
  const dirtyCount = dirtyItems.length;

  const onFormSubmit = async (values: HeaderFormValues) => {
    const items = buildDirtyCorrections(initialValues, values, reasons);
    if (items.length === 0) return;
    await onSubmitCorrections(items);
  };

  return (
    <Card className="border shadow-sm">
      <CardHeader className="border-b px-5 py-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold">
            Invoice Header Fields
          </CardTitle>
          {isApproved ? (
            <Badge variant="outline" className="gap-1 border-emerald-500/40 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
              <Lock className="h-3 w-3" />
              <span>Approved &amp; Locked</span>
            </Badge>
          ) : !canEdit ? (
            <Badge variant="outline" className="gap-1 text-muted-foreground">
              <Lock className="h-3 w-3" />
              <span>Read Only (Requires extraction:edit)</span>
            </Badge>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="p-5">
        {isApproved && (
          <Alert className="mb-5 border-emerald-500/30 bg-emerald-50/50 text-emerald-900 dark:bg-emerald-950/20 dark:text-emerald-300">
            <Lock className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            <AlertTitle className="text-xs font-semibold">Document Locked</AlertTitle>
            <AlertDescription className="text-xs text-muted-foreground">
              This invoice has been approved. Header fields are locked against further modification unless a Finance Manager rejects/reopens it.
            </AlertDescription>
          </Alert>
        )}

        <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {EDITABLE_HEADER_FIELDS.map((fieldName) => {
              const label = FIELD_LABELS[fieldName];
              const currentValue = currentWatchedValues[fieldName] || "";
              const originalValue = originalLlmOutput?.[fieldName] != null
                ? String(originalLlmOutput[fieldName])
                : null;
              const hasDiffFromLlm =
                originalValue !== null && originalValue !== currentValue;

              // Find validation errors/warnings matching this field
              const fieldIssues = validationResults.filter(
                (v) =>
                  v.field_name === fieldName &&
                  (v.status === "FAILED" || v.status === "SKIPPED"),
              );

              const isDirty = (currentWatchedValues[fieldName] || "").trim() !==
                (initialValues[fieldName] || "").trim();

              return (
                <div key={fieldName} className="space-y-1.5 rounded-lg border border-border/50 p-3 bg-card/60">
                  <div className="flex items-center justify-between">
                    <Label htmlFor={`field-${fieldName}`} className="text-xs font-semibold">
                      {label}
                    </Label>
                    {isDirty && (
                      <Badge variant="outline" className="h-4 px-1 text-[9px] border-indigo-400 text-indigo-700 bg-indigo-50 dark:bg-indigo-950/40 dark:text-indigo-300">
                        Modified
                      </Badge>
                    )}
                  </div>

                  <Input
                    id={`field-${fieldName}`}
                    disabled={isFormDisabled}
                    className="h-8 text-xs font-mono"
                    {...register(fieldName)}
                  />

                  {/* Original LLM value reference */}
                  {hasDiffFromLlm && (
                    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground pt-0.5">
                      <History className="h-3 w-3 shrink-0 text-muted-foreground" />
                      <span>Original LLM value:</span>
                      <span className="font-mono font-medium text-foreground">
                        {originalValue || "—"}
                      </span>
                    </div>
                  )}

                  {/* Validation issues attached to this field */}
                  {fieldIssues.map((issue) => {
                    const isError = issue.severity === "ERROR";
                    return (
                      <div
                        key={issue.id}
                        className={`flex items-start gap-1.5 text-[11px] font-medium pt-1 ${
                          isError ? "text-destructive" : "text-amber-700 dark:text-amber-300"
                        }`}
                      >
                        {isError ? (
                          <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        ) : (
                          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        )}
                        <span>{issue.message}</span>
                      </div>
                    );
                  })}

                  {/* Optional Reason Input when modified */}
                  {isDirty && !isFormDisabled && (
                    <div className="pt-1.5">
                      {activeReasonField === fieldName || reasons[fieldName] ? (
                        <div className="space-y-1">
                          <label
                            htmlFor={`reason-${fieldName}`}
                            className="text-[10px] font-medium text-muted-foreground"
                          >
                            Correction Reason (Optional)
                          </label>
                          <input
                            id={`reason-${fieldName}`}
                            type="text"
                            placeholder="e.g. OCR typo in tax amount"
                            value={reasons[fieldName] || ""}
                            onChange={(e) =>
                              setReasons((prev) => ({
                                ...prev,
                                [fieldName]: e.target.value,
                              }))
                            }
                            className="flex h-7 w-full rounded border border-input bg-background px-2 text-[11px] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                          />
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setActiveReasonField(fieldName)}
                          className="text-[10px] text-primary hover:underline"
                        >
                          + Add correction reason
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {!isFormDisabled && (
            <div className="flex items-center justify-end gap-3 pt-3 border-t">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  reset(initialValues);
                  setReasons({});
                }}
                disabled={dirtyCount === 0 || isSubmitting}
                className="text-xs"
              >
                Reset Changes
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={dirtyCount === 0 || isSubmitting}
                className="gap-1.5 text-xs"
              >
                <Save className="h-3.5 w-3.5" />
                <span>
                  {isSubmitting
                    ? "Saving…"
                    : `Save Corrections (${dirtyCount} dirty field${dirtyCount === 1 ? "" : "s"})`}
                </span>
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
