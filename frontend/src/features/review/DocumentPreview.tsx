import { useEffect, useState } from "react";
import { Download, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchDocumentFileBlob } from "./api";

interface DocumentPreviewProps {
  documentId: string;
  filename: string;
}

export function DocumentPreview({ documentId, filename }: DocumentPreviewProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const lowerFilename = filename.toLowerCase();
  const isPdf = lowerFilename.endsWith(".pdf") || mimeType.includes("pdf");
  const isImage =
    lowerFilename.endsWith(".png") ||
    lowerFilename.endsWith(".jpg") ||
    lowerFilename.endsWith(".jpeg") ||
    lowerFilename.endsWith(".tiff") ||
    lowerFilename.endsWith(".tif") ||
    mimeType.startsWith("image/");
  const isSpreadsheet =
    lowerFilename.endsWith(".xlsx") ||
    lowerFilename.endsWith(".xls") ||
    lowerFilename.endsWith(".csv");

  useEffect(() => {
    let active = true;
    let url: string | null = null;

    async function loadBlob() {
      setIsLoading(true);
      setError(null);
      try {
        const blob = await fetchDocumentFileBlob(documentId);
        if (!active) return;
        setMimeType(blob.type);
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      } catch (err) {
        if (!active) return;
        setError(
          err instanceof Error
            ? err.message
            : "Failed to download document file.",
        );
      } finally {
        if (active) setIsLoading(false);
      }
    }

    void loadBlob();

    return () => {
      active = false;
      if (url) {
        URL.revokeObjectURL(url);
      }
    };
  }, [documentId]);

  return (
    <Card className="flex h-full flex-col border shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2 truncate">
          <FileText className="h-4 w-4 shrink-0 text-primary" />
          <CardTitle className="truncate text-sm font-semibold" title={filename}>
            {filename}
          </CardTitle>
        </div>
        {blobUrl && (
          <Button asChild variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
            <a href={blobUrl} download={filename}>
              <Download className="h-3 w-3" />
              <span>Download</span>
            </a>
          </Button>
        )}
      </CardHeader>

      <CardContent className="relative flex flex-1 items-center justify-center p-2 bg-muted/20 min-h-[500px]">
        {isLoading && (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <Loader2 className="h-7 w-7 animate-spin text-primary" />
            <p className="text-xs">Loading document preview…</p>
          </div>
        )}

        {error && (
          <div className="p-6 text-center">
            <p className="text-sm font-medium text-destructive">{error}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Unable to stream document preview from server.
            </p>
          </div>
        )}

        {!isLoading && !error && blobUrl && (
          <>
            {isPdf && (
              <iframe
                src={blobUrl}
                title={`Preview of ${filename}`}
                className="h-full w-full rounded border bg-white shadow-inner"
              />
            )}

            {isImage && (
              <div className="flex h-full w-full items-center justify-center overflow-auto p-4">
                <img
                  src={blobUrl}
                  alt={`Preview of ${filename}`}
                  className="max-h-full max-w-full rounded border bg-white object-contain shadow-sm"
                />
              </div>
            )}

            {isSpreadsheet && (
              <div className="flex flex-col items-center justify-center p-8 text-center">
                <div className="rounded-full bg-emerald-100 p-4 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                  <FileSpreadsheet className="h-8 w-8" />
                </div>
                <h4 className="mt-3 text-sm font-semibold">Spreadsheet File</h4>
                <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                  In-browser preview is unavailable for spreadsheet workbooks. Download the file to view.
                </p>
                <Button asChild size="sm" className="mt-4 gap-1.5 text-xs">
                  <a href={blobUrl} download={filename}>
                    <Download className="h-3.5 w-3.5" />
                    <span>Download {filename}</span>
                  </a>
                </Button>
              </div>
            )}

            {!isPdf && !isImage && !isSpreadsheet && (
              <div className="flex flex-col items-center justify-center p-8 text-center">
                <FileText className="h-8 w-8 text-muted-foreground" />
                <p className="mt-2 text-xs text-muted-foreground">
                  Unsupported preview format ({mimeType || "unknown"}).
                </p>
                <Button asChild size="sm" variant="outline" className="mt-4 gap-1.5 text-xs">
                  <a href={blobUrl} download={filename}>
                    <Download className="h-3.5 w-3.5" />
                    <span>Download File</span>
                  </a>
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

