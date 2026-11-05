import { FileText, User as UserIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/features/documents/StatusBadge";
import type { DocumentDetailRead } from "@/lib/api/types";
import { formatBytes, formatDateTime } from "@/lib/format";

interface HeaderCardProps {
  document: DocumentDetailRead;
}

export function HeaderCard({ document: doc }: HeaderCardProps) {
  return (
    <Card className="border shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-lg border bg-muted/40 p-2.5 text-primary">
              <FileText className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <CardTitle className="text-xl font-bold tracking-tight">
                {doc.original_filename}
              </CardTitle>
              <p className="mt-1 font-mono text-xs text-muted-foreground">
                ID: {doc.id}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={doc.status} category="document" />
            {doc.review_status && (
              <StatusBadge status={doc.review_status} category="review" />
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 border-t pt-4 sm:grid-cols-4 lg:grid-cols-5">
          <div>
            <span className="text-xs font-medium text-muted-foreground">File Format</span>
            <p className="mt-0.5 text-sm font-semibold uppercase">{doc.file_ext || "Unknown"}</p>
          </div>
          <div>
            <span className="text-xs font-medium text-muted-foreground">File Size</span>
            <p className="mt-0.5 text-sm font-semibold">{formatBytes(doc.size_bytes)}</p>
          </div>
          <div>
            <span className="text-xs font-medium text-muted-foreground">Uploaded By</span>
            <div className="mt-0.5 flex items-center gap-1.5 text-sm font-medium">
              <UserIcon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
              <span className="truncate" title={doc.uploader?.full_name || "Unknown"}>
                {doc.uploader?.full_name || "Unknown"}
              </span>
            </div>
          </div>
          <div>
            <span className="text-xs font-medium text-muted-foreground">Uploaded At</span>
            <p className="mt-0.5 text-sm text-foreground/90">{formatDateTime(doc.created_at)}</p>
          </div>
          <div className="col-span-2 sm:col-span-1">
            <span className="text-xs font-medium text-muted-foreground">Last Updated</span>
            <p className="mt-0.5 text-sm text-foreground/90">{formatDateTime(doc.updated_at)}</p>
          </div>
        </div>

        {doc.error && (
          <Alert variant="destructive" className="mt-4">
            <AlertTitle className="text-sm font-semibold">Document Processing Error</AlertTitle>
            <AlertDescription className="mt-1 font-mono text-xs">
              {doc.error}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
