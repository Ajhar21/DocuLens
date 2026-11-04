import { useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Info,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { StatusBadge } from "@/features/documents/StatusBadge";
import {
  getValidationCodeLabel,
} from "@/features/documents/status";
import type {
  DocumentDetailRead,
  ValidationResultRead,
} from "@/lib/api/types";
import { extractDuplicateDocumentIds } from "@/lib/format";

interface ValidationCardProps {
  document: DocumentDetailRead;
}

const SEVERITY_ORDER: Record<string, number> = {
  ERROR: 1,
  WARNING: 2,
  INFO: 3,
};

export function ValidationCard({ document: doc }: ValidationCardProps) {
  const results = doc.validation_results || [];
  const [showPassed, setShowPassed] = useState(false);

  if (results.length === 0) {
    return (
      <Card className="border shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2.5">
            <div className="rounded-md border bg-muted/30 p-2 text-primary">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <CardTitle className="text-lg font-semibold">Validation Rules</CardTitle>
              <CardDescription className="text-xs text-muted-foreground">
                Deterministic financial verification
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-dashed py-8 text-center text-xs text-muted-foreground">
            Validation checks have not yet run for this document.
          </div>
        </CardContent>
      </Card>
    );
  }

  // Segment results
  const failedResults = results
    .filter((r) => r.status === "FAILED")
    .sort((a, b) => {
      const orderA = SEVERITY_ORDER[a.severity] ?? 99;
      const orderB = SEVERITY_ORDER[b.severity] ?? 99;
      if (orderA !== orderB) return orderA - orderB;
      return (a.field_name || a.validation_code).localeCompare(
        b.field_name || b.validation_code,
      );
    });

  const passedOrSkipped = results.filter((r) => r.status !== "FAILED");

  // Summary counts
  const errorCount = results.filter(
    (r) => r.status === "FAILED" && r.severity === "ERROR",
  ).length;
  const warningCount = results.filter(
    (r) => r.status === "FAILED" && r.severity === "WARNING",
  ).length;
  const infoCount = results.filter(
    (r) => r.severity === "INFO" && (r.status === "FAILED" || r.status === "SKIPPED"),
  ).length;
  const passedCount = results.filter((r) => r.status === "PASSED").length;

  const isAllClear = errorCount === 0 && warningCount === 0;

  return (
    <Card className="border shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <div className="rounded-md border bg-muted/30 p-2 text-primary">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <CardTitle className="text-lg font-semibold">Validation Rules</CardTitle>
              <CardDescription className="text-xs text-muted-foreground">
                Automated deterministic financial and business logic checks
              </CardDescription>
            </div>
          </div>

          {/* Summary Badges */}
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant="outline"
              className={
                errorCount > 0
                  ? "border-rose-500/40 bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300 font-semibold"
                  : "border-border bg-muted/30 text-muted-foreground"
              }
            >
              <AlertCircle className="mr-1 h-3 w-3" />
              {errorCount} {errorCount === 1 ? "Error" : "Errors"}
            </Badge>

            <Badge
              variant="outline"
              className={
                warningCount > 0
                  ? "border-amber-500/40 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 font-semibold"
                  : "border-border bg-muted/30 text-muted-foreground"
              }
            >
              <AlertTriangle className="mr-1 h-3 w-3" />
              {warningCount} {warningCount === 1 ? "Warning" : "Warnings"}
            </Badge>

            {infoCount > 0 && (
              <Badge
                variant="outline"
                className="border-sky-500/40 bg-sky-50 text-sky-800 dark:bg-sky-950/40 dark:text-sky-300"
              >
                <Info className="mr-1 h-3 w-3" />
                {infoCount} Info
              </Badge>
            )}

            <Badge
              variant="outline"
              className="border-emerald-500/40 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
            >
              <CheckCircle2 className="mr-1 h-3 w-3" />
              {passedCount} Passed
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* All-Clear Alert */}
        {isAllClear && (
          <div className="flex items-center gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-50/50 p-3 text-emerald-900 dark:bg-emerald-950/20 dark:text-emerald-300">
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <div className="text-xs">
              <span className="font-semibold">All validations clear!</span> No critical calculation errors or required field discrepancies were found.
            </div>
          </div>
        )}

        {/* Failed Validations List */}
        {failedResults.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-rose-800 dark:text-rose-400">
              Issues Requiring Attention ({failedResults.length})
            </h4>

            <div className="space-y-2.5">
              {failedResults.map((result) => (
                <ValidationResultItem key={result.id || result.validation_code} item={result} />
              ))}
            </div>
          </div>
        )}

        {/* Collapsible Passed / Skipped Checks */}
        {passedOrSkipped.length > 0 && (
          <div className="border-t pt-3">
            <Button
              variant="ghost"
              size="sm"
              className="flex w-full items-center justify-between px-2 text-xs font-medium text-muted-foreground hover:text-foreground"
              onClick={() => setShowPassed((prev) => !prev)}
            >
              <span>Passed & Skipped Checks ({passedOrSkipped.length})</span>
              {showPassed ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>

            {showPassed && (
              <div className="mt-3 space-y-2 pl-1">
                {passedOrSkipped.map((result) => (
                  <ValidationResultItem key={result.id || result.validation_code} item={result} />
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ValidationResultItem({ item }: { item: ValidationResultRead }) {
  const isDuplicateCheck = item.validation_code === "DUPLICATE_INVOICE";
  const duplicateIds = isDuplicateCheck
    ? extractDuplicateDocumentIds(item.actual_value, item.message)
    : [];

  return (
    <div className="rounded-lg border bg-card p-3.5 shadow-xs transition-colors">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={item.severity} category="validation-severity" />
          <span className="text-xs font-semibold text-foreground">
            {getValidationCodeLabel(item.validation_code)}
          </span>
          {item.field_name && (
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
              {item.field_name}
            </span>
          )}
        </div>
        <StatusBadge status={item.status} category="validation-status" />
      </div>

      <p className="mt-2 text-xs text-foreground/90 leading-relaxed">{item.message}</p>

      {/* Duplicate Document Links */}
      {isDuplicateCheck && duplicateIds.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 p-2">
          <span className="text-xs font-medium text-muted-foreground">Matching Document(s):</span>
          {duplicateIds.map((docId) => (
            <Link
              key={docId}
              to={`/documents/${docId}`}
              className="inline-flex items-center gap-1 rounded border border-primary/20 bg-background px-2 py-0.5 font-mono text-xs text-primary hover:bg-accent hover:underline"
              title={`View document ${docId}`}
            >
              <ExternalLink className="h-3 w-3" />
              <span>{docId.slice(0, 8)}...</span>
            </Link>
          ))}
        </div>
      )}

      {/* Expected vs Actual Blocks (Monospace, no parsing) */}
      {(item.expected_value !== null || item.actual_value !== null) && (
        <div className="mt-2.5 grid grid-cols-1 gap-2 rounded-md bg-muted/40 p-2.5 font-mono text-xs sm:grid-cols-2">
          <div>
            <span className="text-[10px] font-sans font-semibold uppercase tracking-wider text-muted-foreground">
              Expected
            </span>
            <p className="mt-0.5 break-all text-foreground/80">
              {item.expected_value !== null && item.expected_value !== undefined
                ? item.expected_value
                : "—"}
            </p>
          </div>
          <div>
            <span className="text-[10px] font-sans font-semibold uppercase tracking-wider text-muted-foreground">
              Actual
            </span>
            <p className="mt-0.5 break-all text-foreground/80">
              {item.actual_value !== null && item.actual_value !== undefined
                ? item.actual_value
                : "—"}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

