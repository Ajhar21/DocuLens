import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ExternalLink,
  FileText,
  Filter,
  Layers,
  Search as SearchIcon,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/features/documents/StatusBadge";
import { ApiError } from "@/lib/api/errors";
import type { SearchHit } from "@/lib/api/types";
import { formatCurrency, formatDateTime } from "@/lib/format";
import { searchDocuments, type SearchMode } from "./api";
import { renderSnippet } from "./snippet";

const PAGE_SIZE = 20;

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Read URL state
  const rawQ = searchParams.get("q") ?? "";
  const rawMode = (searchParams.get("mode") as SearchMode) || "hybrid";
  const rawSupplier = searchParams.get("supplier_name") ?? "";
  const rawDateFrom = searchParams.get("date_from") ?? "";
  const rawDateTo = searchParams.get("date_to") ?? "";
  const rawAmountMin = searchParams.get("amount_min") ?? "";
  const rawAmountMax = searchParams.get("amount_max") ?? "";
  const rawReviewStatus = searchParams.get("review_status") ?? "";
  const rawPage = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);

  // Local debounced input state for typing feel
  const [localQ, setLocalQ] = useState(rawQ);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [expandedRankingDocId, setExpandedRankingDocId] = useState<string | null>(null);

  // Sync local input if URL changes externally (e.g. back button)
  useEffect(() => {
    setLocalQ(rawQ);
  }, [rawQ]);

  // Debounce query param updates to URL (350ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localQ !== rawQ) {
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          if (localQ.trim()) {
            next.set("q", localQ.trim());
          } else {
            next.delete("q");
          }
          next.set("page", "1");
          return next;
        });
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [localQ, rawQ, setSearchParams]);

  // Update specific URL search param
  const updateParam = (key: string, value: string | undefined) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value && value.trim()) {
        next.set(key, value.trim());
      } else {
        next.delete(key);
      }
      next.set("page", "1");
      return next;
    });
  };

  const offset = (rawPage - 1) * PAGE_SIZE;
  const isQueryActive = Boolean(rawQ.trim());

  // Execute query with TanStack Query
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: [
      "search",
      {
        q: rawQ.trim(),
        mode: rawMode,
        supplier_name: rawSupplier,
        date_from: rawDateFrom,
        date_to: rawDateTo,
        amount_min: rawAmountMin,
        amount_max: rawAmountMax,
        review_status: rawReviewStatus,
        limit: PAGE_SIZE,
        offset,
      },
    ],
    queryFn: () => {
      return searchDocuments({
        q: rawQ.trim(),
        mode: rawMode,
        supplier_name: rawSupplier || undefined,
        date_from: rawDateFrom || undefined,
        date_to: rawDateTo || undefined,
        amount_min: rawAmountMin || undefined,
        amount_max: rawAmountMax || undefined,
        review_status: rawReviewStatus || undefined,
        limit: PAGE_SIZE,
        offset,
      });
    },
    enabled: isQueryActive,
    staleTime: 30_000,
  });

  const totalHits = data?.total_hits ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalHits / PAGE_SIZE));
  const hits: SearchHit[] = data?.hits ?? [];

  const activeFiltersCount = useMemo(() => {
    let count = 0;
    if (rawSupplier) count++;
    if (rawDateFrom || rawDateTo) count++;
    if (rawAmountMin || rawAmountMax) count++;
    if (rawReviewStatus) count++;
    return count;
  }, [rawSupplier, rawDateFrom, rawDateTo, rawAmountMin, rawAmountMax, rawReviewStatus]);

  const clearAllFilters = () => {
    setSearchParams(() => {
      const next = new URLSearchParams();
      if (rawQ.trim()) next.set("q", rawQ.trim());
      if (rawMode !== "hybrid") next.set("mode", rawMode);
      next.set("page", "1");
      return next;
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Document Search
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Find financial documents using keyword matching, semantic embeddings, or hybrid rank fusion.
        </p>
      </div>

      {/* Search Bar + Controls */}
      <Card className="border shadow-sm">
        <CardContent className="p-4 space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            {/* Search Input Box */}
            <div className="relative flex-1">
              <SearchIcon className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                type="search"
                placeholder="Search across invoice numbers, suppliers, content text..."
                value={localQ}
                onChange={(e) => setLocalQ(e.target.value)}
                className="pl-9 pr-4 h-10 text-sm"
              />
            </div>

            {/* Mode Selector Pill */}
            <div className="flex items-center rounded-lg border bg-muted/40 p-1">
              {(["hybrid", "keyword", "semantic"] as const).map((modeOption) => {
                const isSelected = rawMode === modeOption;
                return (
                  <button
                    key={modeOption}
                    type="button"
                    onClick={() => updateParam("mode", modeOption)}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                      isSelected
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {modeOption === "hybrid" && <Sparkles className="h-3 w-3 text-indigo-500" />}
                    {modeOption === "keyword" && <SearchIcon className="h-3 w-3 text-amber-500" />}
                    {modeOption === "semantic" && <Layers className="h-3 w-3 text-emerald-500" />}
                    <span>{modeOption}</span>
                  </button>
                );
              })}
            </div>

            {/* Filter Toggle Button */}
            <Button
              type="button"
              variant={activeFiltersCount > 0 ? "default" : "outline"}
              size="sm"
              onClick={() => setFiltersOpen((o) => !o)}
              className="h-10 gap-1.5 text-xs shrink-0"
            >
              <SlidersHorizontal className="h-3.5 w-3.5" />
              <span>Filters</span>
              {activeFiltersCount > 0 && (
                <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
                  {activeFiltersCount}
                </Badge>
              )}
            </Button>
          </div>

          {/* Collapsible Backend-Supported Filters */}
          {filtersOpen && (
            <div className="rounded-lg border bg-muted/20 p-4 space-y-4">
              <div className="flex items-center justify-between border-b pb-2">
                <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Filter className="h-3.5 w-3.5 text-muted-foreground" />
                  <span>Metadata Pre-Filters</span>
                </span>
                {activeFiltersCount > 0 && (
                  <button
                    type="button"
                    onClick={clearAllFilters}
                    className="text-[11px] text-primary hover:underline font-medium"
                  >
                    Clear All Filters
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {/* Supplier Name */}
                <div className="space-y-1">
                  <Label htmlFor="filter-supplier" className="text-xs">
                    Supplier Name
                  </Label>
                  <Input
                    id="filter-supplier"
                    placeholder="e.g. Acme, Dell..."
                    value={rawSupplier}
                    onChange={(e) => updateParam("supplier_name", e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>

                {/* Review Status */}
                <div className="space-y-1">
                  <Label htmlFor="filter-review-status" className="text-xs">
                    Review Status
                  </Label>
                  <select
                    id="filter-review-status"
                    value={rawReviewStatus}
                    onChange={(e) => updateParam("review_status", e.target.value)}
                    className="flex h-8 w-full rounded-md border border-input bg-background px-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="">All Review Statuses</option>
                    <option value="needs_review">Needs Review</option>
                    <option value="pending">Pending</option>
                    <option value="in_review">In Review</option>
                    <option value="corrected">Corrected</option>
                    <option value="approved">Approved</option>
                    <option value="rejected">Rejected</option>
                  </select>
                </div>

                {/* Invoice Date Range */}
                <div className="space-y-1">
                  <Label className="text-xs">Invoice Date Range</Label>
                  <div className="grid grid-cols-2 gap-1.5">
                    <Input
                      type="date"
                      value={rawDateFrom}
                      onChange={(e) => updateParam("date_from", e.target.value)}
                      className="h-8 text-xs px-2"
                      title="Date from"
                    />
                    <Input
                      type="date"
                      value={rawDateTo}
                      onChange={(e) => updateParam("date_to", e.target.value)}
                      className="h-8 text-xs px-2"
                      title="Date to"
                    />
                  </div>
                </div>

                {/* Amount Range */}
                <div className="space-y-1">
                  <Label className="text-xs">Total Amount Range</Label>
                  <div className="grid grid-cols-2 gap-1.5">
                    <Input
                      type="number"
                      placeholder="Min"
                      value={rawAmountMin}
                      onChange={(e) => updateParam("amount_min", e.target.value)}
                      className="h-8 text-xs"
                    />
                    <Input
                      type="number"
                      placeholder="Max"
                      value={rawAmountMax}
                      onChange={(e) => updateParam("amount_max", e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Empty State: No Query Entered */}
      {!isQueryActive && (
        <EmptyState
          icon={SearchIcon}
          title="Enter a query to search"
          description="Search by keyword, semantic similarity, or hybrid rank fusion across invoices and document text."
          action={
            <div className="flex flex-col sm:flex-row items-center gap-3">
              <Button asChild variant="outline" size="sm">
                <Link to="/documents">Browse Document List</Link>
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link to="/review">Open Review Queue</Link>
              </Button>
            </div>
          }
        />
      )}

      {/* Loading State */}
      {isQueryActive && isLoading && (
        <LoadingState message={`Searching documents in ${rawMode} mode…`} lines={5} />
      )}

      {/* Error State */}
      {isQueryActive && isError && (
        <ErrorState
          title="Search Failed"
          message={
            error instanceof ApiError && error.message.toLowerCase().includes("embedding")
              ? `Embedding model error in ${rawMode} search: ${error.message}`
              : error instanceof Error
                ? error.message
                : "Unable to complete search request."
          }
          onRetry={() => void refetch()}
        />
      )}

      {/* Results Section */}
      {isQueryActive && !isLoading && !isError && (
        <>
          {/* Summary Bar */}
          <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
            <span>
              Found <strong>{totalHits}</strong> matching document{totalHits === 1 ? "" : "s"} for &ldquo;{rawQ}&rdquo; in {rawMode} mode
            </span>
          </div>

          {/* Empty State: Query returned zero results */}
          {hits.length === 0 ? (
            <EmptyState
              icon={SearchIcon}
              title="No Results Found"
              description={`We couldn't find any documents matching '${rawQ}'. Try adjusting your search query, switching to Hybrid mode, or loosening filters.`}
              action={
                activeFiltersCount > 0 ? (
                  <Button variant="outline" size="sm" onClick={clearAllFilters}>
                    Clear Active Filters
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="space-y-4">
              {hits.map((hit) => {
                const doc = hit.document;
                const inv = hit.invoice;
                const isRankingExpanded = expandedRankingDocId === doc.id;

                const matchTypeVariant =
                  hit.match_type === "BOTH"
                    ? "border-indigo-500/40 bg-indigo-50 text-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-300"
                    : hit.match_type === "SEMANTIC"
                      ? "border-emerald-500/40 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                      : "border-amber-500/40 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300";

                return (
                  <Card
                    key={doc.id}
                    className="border shadow-sm transition-all hover:border-border/80"
                  >
                    <CardHeader className="p-4 pb-2">
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                        <div className="flex items-start gap-2.5">
                          <FileText className="h-5 w-5 shrink-0 text-primary mt-0.5" />
                          <div>
                            <Link
                              to={`/documents/${doc.id}`}
                              className="text-sm font-semibold text-foreground hover:underline flex items-center gap-1.5"
                            >
                              <span>{doc.original_filename}</span>
                              <ExternalLink className="h-3 w-3 text-muted-foreground" />
                            </Link>
                            <p className="text-[11px] text-muted-foreground">
                              Created {formatDateTime(doc.created_at)}
                            </p>
                          </div>
                        </div>

                        {/* Badges */}
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge
                            variant="outline"
                            className={`text-[10px] font-semibold tracking-tight ${matchTypeVariant}`}
                          >
                            {hit.match_type} MATCH
                          </Badge>
                          <StatusBadge status={doc.status} category="document" />
                          {doc.review_status && (
                            <StatusBadge status={doc.review_status} category="review" />
                          )}
                        </div>
                      </div>
                    </CardHeader>

                    <CardContent className="p-4 pt-2 space-y-3">
                      {/* Structured Invoice Summary Bar */}
                      {inv && (
                        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 rounded-md bg-muted/30 p-2.5 text-xs">
                          <div>
                            <span className="text-[10px] text-muted-foreground uppercase block font-medium">
                              Invoice No
                            </span>
                            <span className="font-mono font-semibold">
                              {inv.invoice_number || "—"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[10px] text-muted-foreground uppercase block font-medium">
                              Supplier
                            </span>
                            <span className="truncate block font-medium" title={inv.supplier_name || ""}>
                              {inv.supplier_name || "—"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[10px] text-muted-foreground uppercase block font-medium">
                              Invoice Date
                            </span>
                            <span>{inv.invoice_date || "—"}</span>
                          </div>
                          <div>
                            <span className="text-[10px] text-muted-foreground uppercase block font-medium">
                              Total Amount
                            </span>
                            <span className="font-semibold text-foreground">
                              {inv.total != null
                                ? formatCurrency(inv.total, inv.currency)
                                : "—"}
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Snippet with Safe Highlighting */}
                      {hit.snippet && (
                        <div className="rounded border border-border/40 bg-card p-3 text-xs leading-relaxed font-sans text-muted-foreground">
                          {renderSnippet(hit.snippet)}
                        </div>
                      )}

                      {/* Ranking Details Collapsible */}
                      <div className="border-t pt-2">
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedRankingDocId((prev) =>
                              prev === doc.id ? null : doc.id,
                            )
                          }
                          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground font-medium"
                        >
                          {isRankingExpanded ? (
                            <ChevronUp className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5" />
                          )}
                          <span>Ranking Score: {hit.score.toFixed(4)}</span>
                        </button>

                        {isRankingExpanded && (
                          <div className="mt-2 rounded bg-muted/40 p-2.5 text-[11px] font-mono text-muted-foreground space-y-1">
                            <div>Combined Fusion Score: {hit.score.toFixed(6)}</div>
                            <div>Matched via: {hit.match_type} algorithm</div>
                            <div>Document ID: {doc.id}</div>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}

              {/* Pagination Controls */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between border-t pt-4">
                  <p className="text-xs text-muted-foreground">
                    Page {rawPage} of {totalPages}
                  </p>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => updateParam("page", String(Math.max(1, rawPage - 1)))}
                      disabled={rawPage <= 1}
                      className="h-8 w-8 p-0"
                    >
                      <ChevronLeft className="h-4 w-4" />
                      <span className="sr-only">Previous page</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        updateParam("page", String(Math.min(totalPages, rawPage + 1)))
                      }
                      disabled={rawPage >= totalPages}
                      className="h-8 w-8 p-0"
                    >
                      <ChevronRight className="h-4 w-4" />
                      <span className="sr-only">Next page</span>
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
