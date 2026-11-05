import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Eye,
  GitCompare,
  Plus,
  XCircle,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { EmptyState } from "@/components/shared/EmptyState";
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
import { formatDateTime } from "@/lib/format";
import { usePermissions } from "@/lib/permissions";
import { fetchReconciliations } from "./api";

const PAGE_SIZE = 20;

export function ReconciliationListPage() {
  const navigate = useNavigate();
  const { can } = usePermissions();
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const canRun = can("reconciliation:run");

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["reconciliations", { page, page_size: PAGE_SIZE }],
    queryFn: () => fetchReconciliations({ page, page_size: PAGE_SIZE }),
  });

  const pagination = data?.pagination;
  const rawItems = data?.items ?? [];

  // Client-side filtering across current page records for UI convenience
  const items = rawItems.filter((item) => {
    if (typeFilter !== "all" && item.reconciliation_type !== typeFilter) {
      return false;
    }
    if (statusFilter !== "all" && item.overall_status !== statusFilter) {
      return false;
    }
    return true;
  });

  const totalPages = pagination?.total_pages ?? 1;
  const total = pagination?.total ?? rawItems.length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Document Reconciliation
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Compare financial fields between invoices (PDF-to-PDF) and worksheets (PDF-to-Excel) with tolerance verification.
          </p>
        </div>

        {canRun && (
          <Button asChild size="sm" className="h-9 gap-1.5 self-start sm:self-auto">
            <Link to="/reconciliation/new">
              <Plus className="h-4 w-4" />
              <span>New Reconciliation</span>
            </Link>
          </Button>
        )}
      </div>

      {/* Filter Toolbar */}
      <Card className="border shadow-sm">
        <CardHeader className="border-b py-3 px-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              {isLoading
                ? "Loading reconciliation jobs…"
                : `Showing ${items.length} of ${total} reconciliation runs`}
            </CardTitle>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <label htmlFor="filter-type" className="text-xs text-muted-foreground">
                  Type:
                </label>
                <select
                  id="filter-type"
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="all">All Types</option>
                  <option value="PDF_PDF">PDF to PDF</option>
                  <option value="PDF_EXCEL">PDF to Excel</option>
                </select>
              </div>

              <div className="flex items-center gap-1.5">
                <label htmlFor="filter-status" className="text-xs text-muted-foreground">
                  Status:
                </label>
                <select
                  id="filter-status"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="all">All Statuses</option>
                  <option value="MATCHED">Matched</option>
                  <option value="MISMATCHED">Mismatched</option>
                  <option value="ERROR">Error</option>
                </select>
              </div>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {isLoading && <LoadingState message="Loading reconciliation runs…" className="m-6" />}

          {isError && (
            <div className="p-6">
              <ErrorState
                title="Failed to Load Reconciliations"
                message={error instanceof Error ? error.message : "Unable to load reconciliation history."}
                onRetry={() => void refetch()}
              />
            </div>
          )}

          {!isLoading && !isError && items.length === 0 && (
            <div className="p-6">
              <EmptyState
                icon={GitCompare}
                title="No Reconciliation Runs Found"
                description={
                  typeFilter !== "all" || statusFilter !== "all"
                    ? "No reconciliation records match your selected filter criteria."
                    : "You haven't run any reconciliations yet. Initiate a new run to compare invoice records."
                }
                action={
                  canRun ? (
                    <Button asChild size="sm" variant="outline" className="gap-1.5">
                      <Link to="/reconciliation/new">
                        <Plus className="h-4 w-4" />
                        <span>Start First Reconciliation</span>
                      </Link>
                    </Button>
                  ) : undefined
                }
              />
            </div>
          )}

          {!isLoading && !isError && items.length > 0 && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40 hover:bg-muted/40">
                    <TableHead className="w-[120px]">Run ID</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Source Doc (A)</TableHead>
                    <TableHead>Target Doc (B)</TableHead>
                    <TableHead>Overall Status</TableHead>
                    <TableHead className="text-center">Discrepancies</TableHead>
                    <TableHead>Initiated At</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((job) => {
                    const isMatched = job.overall_status === "MATCHED";
                    const isMismatched = job.overall_status === "MISMATCHED";

                    return (
                      <TableRow
                        key={job.id}
                        className="cursor-pointer transition-colors hover:bg-muted/30"
                        onClick={() => navigate(`/reconciliation/${job.id}`)}
                      >
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {job.id.slice(0, 8)}…
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-mono text-[10px]">
                            {job.reconciliation_type === "PDF_PDF" ? "PDF ↔ PDF" : "PDF ↔ Excel"}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {job.document_id_a.slice(0, 8)}…
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {job.document_id_b.slice(0, 8)}…
                        </TableCell>
                        <TableCell>
                          {isMatched && (
                            <Badge className="gap-1 border-emerald-500/40 bg-emerald-50 text-emerald-800 text-[11px] dark:bg-emerald-950/40 dark:text-emerald-300">
                              <CheckCircle2 className="h-3 w-3" />
                              <span>MATCHED</span>
                            </Badge>
                          )}
                          {isMismatched && (
                            <Badge variant="destructive" className="gap-1 text-[11px]">
                              <XCircle className="h-3 w-3" />
                              <span>MISMATCHED</span>
                            </Badge>
                          )}
                          {!isMatched && !isMismatched && (
                            <Badge variant="outline" className="gap-1 text-[11px]">
                              <AlertCircle className="h-3 w-3" />
                              <span>{job.overall_status}</span>
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-center font-semibold">
                          {job.discrepancy_count > 0 ? (
                            <span className="text-destructive font-mono">
                              {job.discrepancy_count}
                            </span>
                          ) : (
                            <span className="text-emerald-600 dark:text-emerald-400 font-mono">
                              0
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {formatDateTime(job.initiated_at)}
                        </TableCell>
                        <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                          <Button
                            asChild
                            variant="ghost"
                            size="sm"
                            className="h-8 gap-1.5 text-xs text-primary"
                          >
                            <Link to={`/reconciliation/${job.id}`}>
                              <Eye className="h-3.5 w-3.5" />
                              <span>View Result</span>
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t px-6 py-3">
            <p className="text-xs text-muted-foreground">
              Page {page} of {totalPages}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-8 w-8 p-0"
              >
                <ChevronLeft className="h-4 w-4" />
                <span className="sr-only">Previous page</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="h-8 w-8 p-0"
              >
                <ChevronRight className="h-4 w-4" />
                <span className="sr-only">Next page</span>
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

