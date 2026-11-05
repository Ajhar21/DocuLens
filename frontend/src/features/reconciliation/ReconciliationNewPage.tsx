import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  FileSpreadsheet,
  FileText,
  GitCompare,
  HelpCircle,
  Loader2,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  fetchDocumentDetail,
  fetchDocuments,
} from "@/features/documents/api";
import { ApiError } from "@/lib/api/errors";
import type { DocumentItem } from "@/lib/api/types";
import {
  fetchExcelSheets,
  reconcilePdfExcel,
  reconcilePdfPdf,
} from "./api";
import {
  autoSuggestColumnMapping,
  INVOICE_FIELDS,
} from "./auto-suggest";

export function ReconciliationNewPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<"pdf-pdf" | "pdf-excel">("pdf-pdf");

  // PDF-to-PDF State
  const [sourceDocId, setSourceDocId] = useState<string>("");
  const [targetDocId, setTargetDocId] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  // PDF-to-Excel State
  const [pdfSourceId, setPdfSourceId] = useState<string>("");
  const [excelTargetId, setExcelTargetId] = useState<string>("");
  const [selectedSheet, setSelectedSheet] = useState<string>("");
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [excelNotes, setExcelNotes] = useState<string>("");

  // Fetch parsed candidate documents for reconciliation
  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ["documents", "candidates-reconciliation"],
    queryFn: () => fetchDocuments({ limit: 100, status: "parsed" }),
  });

  const allParsedDocs = useMemo(() => docsData?.items ?? [], [docsData]);

  // Candidate PDF documents only (exclude spreadsheets)
  const candidatePdfDocs = useMemo(
    () =>
      allParsedDocs.filter((d: DocumentItem) => {
        const ext = (d.file_ext || "").toLowerCase();
        return ext === ".pdf" || d.content_type.includes("pdf");
      }),
    [allParsedDocs],
  );

  // Candidate Target PDF documents (excludes currently selected source)
  const candidateTargetPdfDocs = useMemo(
    () => candidatePdfDocs.filter((d: DocumentItem) => d.id !== sourceDocId),
    [candidatePdfDocs, sourceDocId],
  );

  // Candidate Excel / Spreadsheet documents only
  const candidateExcelDocs = useMemo(
    () =>
      allParsedDocs.filter((d: DocumentItem) => {
        const ext = (d.file_ext || "").toLowerCase();
        return (
          ext === ".xlsx" ||
          ext === ".xls" ||
          ext === ".csv" ||
          d.content_type.includes("spreadsheet") ||
          d.content_type.includes("excel")
        );
      }),
    [allParsedDocs],
  );

  // PDF-to-PDF Mutation
  const pdfPdfMutation = useMutation({
    mutationFn: () => {
      if (!sourceDocId || !targetDocId) {
        throw new Error("Both source and target documents must be selected.");
      }
      return reconcilePdfPdf({
        document_id_a: sourceDocId,
        document_id_b: targetDocId,
        notes: notes.trim() || undefined,
      });
    },
    onSuccess: (result) => {
      toast.success(
        `Reconciliation completed with status: ${result.overall_status}`,
      );
      void queryClient.invalidateQueries({ queryKey: ["reconciliations"] });
      navigate(`/reconciliation/${result.id}`);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        toast.error(`Reconciliation failed: ${err.message}`);
        return;
      }
      toast.error(
        err instanceof Error ? err.message : "Failed to run reconciliation.",
      );
    },
  });

  // Query sheets for selected Excel document
  const { data: sheetsData, isLoading: sheetsLoading } = useQuery({
    queryKey: ["reconciliation", "sheets", excelTargetId],
    queryFn: () => fetchExcelSheets(excelTargetId),
    enabled: Boolean(excelTargetId),
  });

  // Query full parse details for selected Excel document (contains tables and columns)
  const { data: excelDetailData, isLoading: excelDetailLoading } = useQuery({
    queryKey: ["documents", "excel-detail", excelTargetId],
    queryFn: () => fetchDocumentDetail(excelTargetId),
    enabled: Boolean(excelTargetId),
  });

  // Available sheets from backend
  const availableSheets: string[] = useMemo(() => {
    if (sheetsData?.sheet_names && sheetsData.sheet_names.length > 0) {
      return sheetsData.sheet_names;
    }
    const parseTables = excelDetailData?.parse_summary?.tables;
    if (parseTables && parseTables.length > 0) {
      return parseTables
        .map((t) => (t as { name?: string }).name)
        .filter((n): n is string => Boolean(n));
    }
    return [];
  }, [sheetsData, excelDetailData]);

  // Automatically select first sheet when sheets load
  useEffect(() => {
    if (availableSheets.length > 0) {
      if (!selectedSheet || !availableSheets.includes(selectedSheet)) {
        setSelectedSheet(availableSheets[0] ?? "");
      }
    } else {
      setSelectedSheet("");
    }
  }, [availableSheets, selectedSheet]);

  // Detected column headers in the currently selected sheet
  const currentSheetColumns: string[] = useMemo(() => {
    if (!excelDetailData?.parse_summary?.tables) return [];
    const tables = excelDetailData.parse_summary.tables as {
      name?: string;
      columns?: string[];
    }[];
    const targetTable =
      tables.find((t) => t.name === selectedSheet) || tables[0];
    return targetTable?.columns || [];
  }, [excelDetailData, selectedSheet]);

  // Auto-suggest column mapping when sheet columns change
  useEffect(() => {
    if (currentSheetColumns.length > 0) {
      const suggested = autoSuggestColumnMapping(currentSheetColumns);
      setColumnMapping(suggested);
    } else {
      setColumnMapping({});
    }
  }, [currentSheetColumns]);

  const handleResetMapping = () => {
    if (currentSheetColumns.length > 0) {
      setColumnMapping(autoSuggestColumnMapping(currentSheetColumns));
      toast.info("Column mappings reset to auto-detected suggestions.");
    }
  };

  const handleFieldMappingChange = (fieldKey: string, sheetHeader: string) => {
    setColumnMapping((prev) => {
      const next = { ...prev };
      if (sheetHeader) {
        next[fieldKey] = sheetHeader;
      } else {
        delete next[fieldKey];
      }
      return next;
    });
  };

  // PDF-to-Excel Mutation
  const pdfExcelMutation = useMutation({
    mutationFn: () => {
      if (!pdfSourceId || !excelTargetId) {
        throw new Error(
          "Please select both a PDF invoice and an Excel workbook.",
        );
      }
      if (!selectedSheet) {
        throw new Error("Please select a target worksheet.");
      }
      if (!columnMapping.invoice_number?.trim()) {
        throw new Error(
          "Column mapping must map 'Invoice Number' to a sheet header.",
        );
      }

      // Filter out empty mappings
      const cleanMapping: Record<string, string> = {};
      for (const [k, v] of Object.entries(columnMapping)) {
        if (v && v.trim()) {
          cleanMapping[k] = v.trim();
        }
      }

      return reconcilePdfExcel({
        document_id_a: pdfSourceId,
        document_id_b: excelTargetId,
        excel_sheet_name: selectedSheet,
        column_mapping: cleanMapping,
        notes: excelNotes.trim() || undefined,
      });
    },
    onSuccess: (result) => {
      toast.success(
        `PDF-to-Excel reconciliation completed with status: ${result.overall_status}`,
      );
      void queryClient.invalidateQueries({ queryKey: ["reconciliations"] });
      navigate(`/reconciliation/${result.id}`);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        toast.error(`Reconciliation failed: ${err.message}`);
        return;
      }
      toast.error(
        err instanceof Error ? err.message : "Failed to run reconciliation.",
      );
    },
  });

  const handlePdfPdfSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceDocId || !targetDocId) {
      toast.error("Please select both a source and target document.");
      return;
    }
    pdfPdfMutation.mutate();
  };

  const handlePdfExcelSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pdfSourceId || !excelTargetId) {
      toast.error("Please select both a PDF invoice and an Excel workbook.");
      return;
    }
    if (!selectedSheet) {
      toast.error("Please select a target sheet.");
      return;
    }
    if (!columnMapping.invoice_number) {
      toast.error(
        "Invoice Number must be mapped to identify the corresponding spreadsheet record.",
      );
      return;
    }
    pdfExcelMutation.mutate();
  };

  const isInvoiceNumberMapped = Boolean(columnMapping.invoice_number?.trim());

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button asChild variant="outline" size="sm" className="h-8 gap-1.5">
          <Link to="/reconciliation">
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Reconciliations</span>
          </Link>
        </Button>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">
            Initiate Document Reconciliation
          </h1>
          <p className="text-xs text-muted-foreground">
            Execute deterministic comparison with configured tolerances across
            invoice records.
          </p>
        </div>
      </div>

      {/* Mode Tabs */}
      <div className="flex items-center border-b">
        <button
          type="button"
          onClick={() => setActiveTab("pdf-pdf")}
          className={`flex items-center gap-2 border-b-2 px-5 py-2.5 text-sm font-medium transition-colors ${
            activeTab === "pdf-pdf"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <FileText className="h-4 w-4" />
          <span>PDF to PDF Invoice</span>
          <Badge
            variant="outline"
            className="text-[10px] h-4 px-1 text-emerald-700 bg-emerald-50 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-300"
          >
            Active
          </Badge>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("pdf-excel")}
          className={`flex items-center gap-2 border-b-2 px-5 py-2.5 text-sm font-medium transition-colors ${
            activeTab === "pdf-excel"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <FileSpreadsheet className="h-4 w-4" />
          <span>PDF to Excel Worksheet</span>
          <Badge
            variant="outline"
            className="text-[10px] h-4 px-1 text-emerald-700 bg-emerald-50 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-300"
          >
            Active
          </Badge>
        </button>
      </div>

      {/* Tab 1: PDF to PDF Reconciliation */}
      {activeTab === "pdf-pdf" && (
        <Card className="border shadow-sm">
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <GitCompare className="h-4 w-4 text-primary" />
              <span>Cross-PDF Invoice Comparison</span>
            </CardTitle>
            <CardDescription className="text-xs">
              Select two parsed PDF invoices. The comparator will align invoice
              numbers, dates, supplier/customer names, amounts (with ±$0.05 /
              0.1% tolerance), and structured line items.
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handlePdfPdfSubmit} className="space-y-6">
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                {/* Source Document A */}
                <div className="space-y-2 rounded-lg border p-4 bg-muted/10">
                  <Label
                    htmlFor="source-doc-select"
                    className="text-xs font-semibold flex items-center justify-between"
                  >
                    <span>Source Document (A)</span>
                    <span className="text-[10px] text-muted-foreground font-normal">
                      Primary Invoice
                    </span>
                  </Label>
                  <select
                    id="source-doc-select"
                    value={sourceDocId}
                    onChange={(e) => {
                      setSourceDocId(e.target.value);
                      if (targetDocId === e.target.value) {
                        setTargetDocId("");
                      }
                    }}
                    disabled={docsLoading || pdfPdfMutation.isPending}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="">Select parsed PDF invoice…</option>
                    {candidatePdfDocs.map((doc: DocumentItem) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.original_filename} ({doc.id.slice(0, 8)})
                      </option>
                    ))}
                  </select>
                  {candidatePdfDocs.length === 0 && !docsLoading && (
                    <p className="text-[11px] text-amber-600 dark:text-amber-400">
                      No parsed PDF invoices available. Upload and process
                      documents first.
                    </p>
                  )}
                </div>

                {/* Target Document B */}
                <div className="space-y-2 rounded-lg border p-4 bg-muted/10">
                  <Label
                    htmlFor="target-doc-select"
                    className="text-xs font-semibold flex items-center justify-between"
                  >
                    <span>Target Document (B)</span>
                    <span className="text-[10px] text-muted-foreground font-normal">
                      Comparison Invoice
                    </span>
                  </Label>
                  <select
                    id="target-doc-select"
                    value={targetDocId}
                    onChange={(e) => setTargetDocId(e.target.value)}
                    disabled={
                      docsLoading || !sourceDocId || pdfPdfMutation.isPending
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
                  >
                    <option value="">
                      {!sourceDocId
                        ? "Select Source Document A first…"
                        : "Select comparison PDF invoice…"}
                    </option>
                    {candidateTargetPdfDocs.map((doc: DocumentItem) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.original_filename} ({doc.id.slice(0, 8)})
                      </option>
                    ))}
                  </select>
                  {sourceDocId && candidateTargetPdfDocs.length === 0 && (
                    <p className="text-[11px] text-muted-foreground">
                      No additional parsed PDFs available to compare against.
                    </p>
                  )}
                </div>
              </div>

              {/* Notes */}
              <div className="space-y-1.5">
                <Label htmlFor="recon-notes" className="text-xs font-medium">
                  Run Notes (Optional)
                </Label>
                <textarea
                  id="recon-notes"
                  rows={2}
                  placeholder="e.g. Monthly vendor statement vs supplier invoice reconciliation..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  disabled={pdfPdfMutation.isPending}
                  className="flex w-full rounded-md border border-input bg-background p-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-3 border-t">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => navigate("/reconciliation")}
                  disabled={pdfPdfMutation.isPending}
                  className="text-xs"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={
                    !sourceDocId || !targetDocId || pdfPdfMutation.isPending
                  }
                  className="gap-1.5 text-xs"
                >
                  {pdfPdfMutation.isPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Reconciling Invoices…</span>
                    </>
                  ) : (
                    <>
                      <GitCompare className="h-3.5 w-3.5" />
                      <span>Execute PDF Reconciliation</span>
                    </>
                  )}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Tab 2: PDF to Excel Reconciliation with Interactive Column Mapping */}
      {activeTab === "pdf-excel" && (
        <Card className="border shadow-sm">
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4 text-primary" />
              <span>PDF-to-Excel Worksheet Reconciliation</span>
            </CardTitle>
            <CardDescription className="text-xs">
              Reconcile a processed PDF invoice against a spreadsheet ledger.
              Select the target worksheet and map invoice fields to spreadsheet
              column headers. The comparator automatically identifies the matching
              record row using the mapped invoice number.
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handlePdfExcelSubmit} className="space-y-6">
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                {/* PDF Source Document */}
                <div className="space-y-2 rounded-lg border p-4 bg-muted/10">
                  <Label
                    htmlFor="pdf-source-select"
                    className="text-xs font-semibold flex items-center justify-between"
                  >
                    <span>PDF Invoice (Document A)</span>
                    <span className="text-[10px] text-muted-foreground font-normal">
                      Source
                    </span>
                  </Label>
                  <select
                    id="pdf-source-select"
                    value={pdfSourceId}
                    onChange={(e) => setPdfSourceId(e.target.value)}
                    disabled={docsLoading || pdfExcelMutation.isPending}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="">Select parsed PDF invoice…</option>
                    {candidatePdfDocs.map((doc: DocumentItem) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.original_filename} ({doc.id.slice(0, 8)})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Excel Target Document */}
                <div className="space-y-2 rounded-lg border p-4 bg-muted/10">
                  <Label
                    htmlFor="excel-target-select"
                    className="text-xs font-semibold flex items-center justify-between"
                  >
                    <span>Spreadsheet Ledger (Document B)</span>
                    <span className="text-[10px] text-muted-foreground font-normal">
                      Target (.xlsx, .csv)
                    </span>
                  </Label>
                  <select
                    id="excel-target-select"
                    value={excelTargetId}
                    onChange={(e) => {
                      setExcelTargetId(e.target.value);
                      setSelectedSheet("");
                      setColumnMapping({});
                    }}
                    disabled={docsLoading || pdfExcelMutation.isPending}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="">Select parsed spreadsheet…</option>
                    {candidateExcelDocs.map((doc: DocumentItem) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.original_filename} ({doc.id.slice(0, 8)})
                      </option>
                    ))}
                  </select>
                  {candidateExcelDocs.length === 0 && !docsLoading && (
                    <p className="text-[11px] text-amber-600 dark:text-amber-400">
                      No parsed spreadsheets available (.xlsx or .csv).
                    </p>
                  )}
                </div>
              </div>

              {/* Sheet Selector & Column Header Preview */}
              {excelTargetId && (
                <div className="space-y-3 rounded-lg border p-4 bg-muted/10">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="space-y-1">
                      <Label
                        htmlFor="sheet-selector"
                        className="text-xs font-semibold flex items-center gap-1.5"
                      >
                        <span>Target Worksheet</span>
                        {sheetsLoading && (
                          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                        )}
                      </Label>
                      <p className="text-[11px] text-muted-foreground">
                        Select the sheet containing transaction records.
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <select
                        id="sheet-selector"
                        value={selectedSheet}
                        onChange={(e) => setSelectedSheet(e.target.value)}
                        disabled={
                          sheetsLoading ||
                          excelDetailLoading ||
                          pdfExcelMutation.isPending
                        }
                        className="flex h-8 rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      >
                        {availableSheets.map((name) => (
                          <option key={name} value={name}>
                            {name}
                          </option>
                        ))}
                      </select>

                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleResetMapping}
                        disabled={
                          currentSheetColumns.length === 0 ||
                          pdfExcelMutation.isPending
                        }
                        className="h-8 gap-1 text-[11px]"
                        title="Re-run auto-detection for sheet columns"
                      >
                        <Sparkles className="h-3.5 w-3.5 text-primary" />
                        <span>Auto-Suggest</span>
                      </Button>
                    </div>
                  </div>

                  {/* Detected sheet headers preview */}
                  {currentSheetColumns.length > 0 && (
                    <div className="pt-2 border-t space-y-1.5">
                      <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        Available Sheet Columns ({currentSheetColumns.length})
                      </span>
                      <div className="flex flex-wrap gap-1.5 max-h-20 overflow-y-auto">
                        {currentSheetColumns.map((col) => (
                          <span
                            key={col}
                            className="inline-flex items-center rounded-md bg-secondary px-2 py-0.5 text-[10px] font-mono font-medium text-secondary-foreground"
                          >
                            {col}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Column Mapping Table */}
              {excelTargetId && selectedSheet && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                        <span>Invoice Field Mapping</span>
                        <span title="Map each invoice attribute to the corresponding spreadsheet column">
                          <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                        </span>
                      </h3>
                      <p className="text-[11px] text-muted-foreground">
                        Match each financial invoice field with its corresponding
                        column in the sheet.
                      </p>
                    </div>

                    {!isInvoiceNumberMapped && (
                      <Badge
                        variant="destructive"
                        className="text-[10px] h-5"
                      >
                        Invoice Number mapping required
                      </Badge>
                    )}
                  </div>

                  <div className="rounded-md border overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-muted/50 border-b text-muted-foreground font-medium">
                        <tr>
                          <th className="py-2.5 px-4 text-left font-medium w-1/2">
                            Invoice Field
                          </th>
                          <th className="py-2.5 px-4 text-left font-medium w-1/2">
                            Spreadsheet Column Header
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {INVOICE_FIELDS.map((field) => {
                          const currentMapped = columnMapping[field.key] || "";
                          const isRequired = field.key === "invoice_number";
                          return (
                            <tr
                              key={field.key}
                              className={
                                isRequired && !currentMapped
                                  ? "bg-destructive/5"
                                  : undefined
                              }
                            >
                              <td className="py-2.5 px-4">
                                <div className="flex items-center gap-2">
                                  <span className="font-medium text-foreground">
                                    {field.label}
                                  </span>
                                  {isRequired && (
                                    <Badge
                                      variant="outline"
                                      className="text-[9px] h-4 px-1 text-destructive border-destructive/40"
                                    >
                                      Required
                                    </Badge>
                                  )}
                                </div>
                                <span className="text-[10px] text-muted-foreground font-mono">
                                  {field.key}
                                </span>
                              </td>
                              <td className="py-2.5 px-4">
                                <select
                                  value={currentMapped}
                                  onChange={(e) =>
                                    handleFieldMappingChange(
                                      field.key,
                                      e.target.value,
                                    )
                                  }
                                  disabled={pdfExcelMutation.isPending}
                                  className={`flex h-8 w-full rounded-md border px-2 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                                    isRequired && !currentMapped
                                      ? "border-destructive/60 bg-destructive/5"
                                      : "border-input bg-background"
                                  }`}
                                >
                                  <option value="">-- Not Mapped --</option>
                                  {currentSheetColumns.map((col) => (
                                    <option key={col} value={col}>
                                      {col}
                                    </option>
                                  ))}
                                </select>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Notes */}
              <div className="space-y-1.5">
                <Label htmlFor="excel-recon-notes" className="text-xs font-medium">
                  Run Notes (Optional)
                </Label>
                <textarea
                  id="excel-recon-notes"
                  rows={2}
                  placeholder="e.g. Q1 Bank ledger vs PDF vendor invoice..."
                  value={excelNotes}
                  onChange={(e) => setExcelNotes(e.target.value)}
                  disabled={pdfExcelMutation.isPending}
                  className="flex w-full rounded-md border border-input bg-background p-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-3 border-t">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleResetMapping}
                  disabled={
                    !excelTargetId ||
                    currentSheetColumns.length === 0 ||
                    pdfExcelMutation.isPending
                  }
                  className="gap-1.5 text-xs"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  <span>Reset Mappings</span>
                </Button>

                <div className="flex items-center gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => navigate("/reconciliation")}
                    disabled={pdfExcelMutation.isPending}
                    className="text-xs"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    size="sm"
                    disabled={
                      !pdfSourceId ||
                      !excelTargetId ||
                      !selectedSheet ||
                      !isInvoiceNumberMapped ||
                      pdfExcelMutation.isPending
                    }
                    className="gap-1.5 text-xs"
                  >
                    {pdfExcelMutation.isPending ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Reconciling Worksheet…</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span>Execute PDF-to-Excel Reconciliation</span>
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
