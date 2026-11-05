import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  GitCompare,
  HelpCircle,
  XCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import type { ReconciliationResultRead } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { fetchReconciliationDetail } from "./api";

export function ReconciliationDetailPage() {
  const { id } = useParams<{ id: string }>();

  const {
    data: detail,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["reconciliation", id],
    queryFn: () => {
      if (!id) throw new Error("Reconciliation ID required");
      return fetchReconciliationDetail(id);
    },
    enabled: Boolean(id),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link to="/reconciliation">
              <ArrowLeft className="h-4 w-4 mr-1" />
              <span>Back to Reconciliations</span>
            </Link>
          </Button>
        </div>
        <LoadingState message="Loading reconciliation results…" lines={6} />
      </div>
    );
  }

  if (isError || !detail) {
    const isForbidden = error instanceof ApiError && error.status === 403;
    return (
      <div className="space-y-6">
        <Button asChild variant="ghost" size="sm">
          <Link to="/reconciliation">
            <ArrowLeft className="h-4 w-4 mr-1" />
            <span>Back to Reconciliations</span>
          </Link>
        </Button>
        <ErrorState
          isForbidden={isForbidden}
          title={isForbidden ? "Access Denied" : "Reconciliation Run Not Found"}
          message={error instanceof Error ? error.message : "Unable to load reconciliation comparison."}
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  const isMatched = detail.overall_status === "MATCHED";
  const isMismatched = detail.overall_status === "MISMATCHED";
  const allResults = detail.results || [];

  const headerResults = allResults.filter((r) => r.entity_type === "HEADER");
  const lineItemResults = allResults.filter((r) => r.entity_type === "LINE_ITEM");

  const isPdfExcel = detail.reconciliation_type === "PDF_EXCEL";

  return (
    <div className="space-y-6">
      {/* Top Navigation & Status Bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b pb-4">
        <div className="flex items-center gap-3">
          <Button asChild variant="outline" size="sm" className="h-8 gap-1.5">
            <Link to="/reconciliation">
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Back to Reconciliations</span>
            </Link>
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-foreground">
                Reconciliation Comparison
              </h1>
              <Badge variant="outline" className="font-mono text-xs">
                {isPdfExcel ? "PDF ↔ Excel" : "PDF ↔ PDF"}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground font-mono">
              Job ID: {detail.id} · Initiated {formatDateTime(detail.initiated_at)}
            </p>
          </div>
        </div>

        {/* Overall Status Badge */}
        <div className="flex items-center gap-2">
          {isMatched && (
            <Badge className="gap-1.5 px-3 py-1 border-emerald-500/40 bg-emerald-50 text-emerald-800 text-xs font-semibold dark:bg-emerald-950/40 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4" />
              <span>MATCHED (Zero Discrepancies)</span>
            </Badge>
          )}
          {isMismatched && (
            <Badge variant="destructive" className="gap-1.5 px-3 py-1 text-xs font-semibold">
              <XCircle className="h-4 w-4" />
              <span>MISMATCHED ({detail.discrepancy_count} Discrepanc{detail.discrepancy_count === 1 ? "y" : "ies"})</span>
            </Badge>
          )}
          {!isMatched && !isMismatched && (
            <Badge variant="outline" className="gap-1.5 px-3 py-1 text-xs font-semibold">
              <AlertCircle className="h-4 w-4" />
              <span>{detail.overall_status}</span>
            </Badge>
          )}
        </div>
      </div>

      {/* Document Comparison Metadata Card */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Document A (Source) */}
        <Card className="border shadow-sm bg-card/60">
          <CardHeader className="py-3 px-4 border-b">
            <CardTitle className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <FileText className="h-4 w-4 text-primary" />
                <span>Source Document (A)</span>
              </span>
              <Badge variant="secondary" className="text-[10px]">Primary PDF</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground font-medium">Document ID:</span>
              <Link
                to={`/documents/${detail.document_id_a}`}
                className="font-mono text-primary hover:underline flex items-center gap-1 text-[11px]"
              >
                <span>{detail.document_id_a}</span>
                <ExternalLink className="h-3 w-3" />
              </Link>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground font-medium">Review Page:</span>
              <Link
                to={`/review/${detail.document_id_a}`}
                className="text-primary hover:underline text-[11px]"
              >
                Open in Review Queue →
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Document B (Target) */}
        <Card className="border shadow-sm bg-card/60">
          <CardHeader className="py-3 px-4 border-b">
            <CardTitle className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                {isPdfExcel ? (
                  <FileSpreadsheet className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <FileText className="h-4 w-4 text-primary" />
                )}
                <span>Target Document (B)</span>
              </span>
              <Badge variant="secondary" className="text-[10px]">
                {isPdfExcel ? "Target Spreadsheet" : "Comparison PDF"}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground font-medium">Document ID:</span>
              <Link
                to={`/documents/${detail.document_id_b}`}
                className="font-mono text-primary hover:underline flex items-center gap-1 text-[11px]"
              >
                <span>{detail.document_id_b}</span>
                <ExternalLink className="h-3 w-3" />
              </Link>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground font-medium">Details:</span>
              <Link
                to={`/documents/${detail.document_id_b}`}
                className="text-primary hover:underline text-[11px]"
              >
                View Document Details →
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {detail.notes && (
        <div className="rounded-lg border bg-muted/20 p-3 text-xs">
          <span className="font-semibold text-foreground">Reconciliation Notes: </span>
          <span className="text-muted-foreground">{detail.notes}</span>
        </div>
      )}

      {/* Header Fields Comparison Table */}
      <Card className="border shadow-sm">
        <CardHeader className="border-b py-3 px-6">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <GitCompare className="h-4 w-4 text-primary" />
            <span>Invoice Header Fields Comparison</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <ComparisonTable results={headerResults} />
        </CardContent>
      </Card>

      {/* Line Item Fields Comparison Table (if present) */}
      {lineItemResults.length > 0 && (
        <Card className="border shadow-sm">
          <CardHeader className="border-b py-3 px-6">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <GitCompare className="h-4 w-4 text-primary" />
              <span>Line Items Comparison ({lineItemResults.length} fields evaluated)</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ComparisonTable results={lineItemResults} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ComparisonTable({ results }: { results: ReconciliationResultRead[] }) {
  if (results.length === 0) {
    return (
      <div className="py-8 text-center text-xs text-muted-foreground">
        No comparison results recorded for this section.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="w-[180px]">Field</TableHead>
            <TableHead>Source Value (Doc A)</TableHead>
            <TableHead>Target Value (Doc B)</TableHead>
            <TableHead className="w-[160px]">Difference</TableHead>
            <TableHead className="w-[160px] text-right">Result Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((res) => {
            const isMismatch = res.match_status === "MISMATCH";
            const isExact = res.match_status === "EXACT_MATCH";
            const isTolerance = res.match_status === "TOLERANCE_MATCH";
            const isMissingA = res.match_status === "MISSING_IN_A";
            const isMissingB = res.match_status === "MISSING_IN_B";
            const isNotComparable = res.match_status === "NOT_COMPARABLE";

            return (
              <TableRow
                key={res.id}
                className={
                  isMismatch
                    ? "bg-destructive/5 hover:bg-destructive/10 font-semibold"
                    : undefined
                }
              >
                {/* Field Name */}
                <TableCell className="font-mono text-xs">
                  {res.field_name}
                </TableCell>

                {/* Source A Value */}
                <TableCell className="font-mono text-xs">
                  {res.source_a_value != null ? (
                    <span>{res.source_a_value}</span>
                  ) : (
                    <span className="text-muted-foreground italic">None / Missing</span>
                  )}
                </TableCell>

                {/* Target B Value */}
                <TableCell className="font-mono text-xs">
                  {res.source_b_value != null ? (
                    <span>{res.source_b_value}</span>
                  ) : (
                    <span className="text-muted-foreground italic">None / Missing</span>
                  )}
                </TableCell>

                {/* Difference */}
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {res.absolute_difference != null ? (
                    <div>
                      <span>Diff: ±{res.absolute_difference}</span>
                      {res.percentage_difference != null && (
                        <span className="text-[10px] block text-muted-foreground">
                          ({(Number(res.percentage_difference) * 100).toFixed(2)}%)
                        </span>
                      )}
                    </div>
                  ) : (
                    <span>—</span>
                  )}
                </TableCell>

                {/* Result Badge */}
                <TableCell className="text-right">
                  {isExact && (
                    <Badge className="border-emerald-500/40 bg-emerald-50 text-emerald-800 text-[11px] gap-1 dark:bg-emerald-950/40 dark:text-emerald-300">
                      <CheckCircle2 className="h-3 w-3" />
                      <span>EXACT MATCH</span>
                    </Badge>
                  )}

                  {isTolerance && (
                    <Badge className="border-emerald-500/40 bg-emerald-50 text-emerald-800 text-[11px] gap-1 dark:bg-emerald-950/40 dark:text-emerald-300">
                      <CheckCircle2 className="h-3 w-3" />
                      <span>TOLERANCE MATCH</span>
                    </Badge>
                  )}

                  {isMismatch && (
                    <Badge variant="destructive" className="text-[11px] gap-1 shadow-sm">
                      <XCircle className="h-3 w-3" />
                      <span>MISMATCH</span>
                    </Badge>
                  )}

                  {isMissingA && (
                    <Badge variant="outline" className="border-amber-500/50 bg-amber-50 text-amber-800 text-[10px] gap-1 dark:bg-amber-950/40 dark:text-amber-300">
                      <AlertTriangle className="h-3 w-3" />
                      <span>MISSING IN A</span>
                    </Badge>
                  )}

                  {isMissingB && (
                    <Badge variant="outline" className="border-amber-500/50 bg-amber-50 text-amber-800 text-[10px] gap-1 dark:bg-amber-950/40 dark:text-amber-300">
                      <AlertTriangle className="h-3 w-3" />
                      <span>MISSING IN B</span>
                    </Badge>
                  )}

                  {isNotComparable && (
                    <Badge variant="outline" className="border-border text-muted-foreground text-[10px] gap-1">
                      <HelpCircle className="h-3 w-3" />
                      <span>NOT COMPARABLE</span>
                    </Badge>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

