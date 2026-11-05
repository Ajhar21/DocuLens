import { ArrowRight, History, User as UserIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DocumentCorrectionRead } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

interface CorrectionHistoryPanelProps {
  corrections: DocumentCorrectionRead[] | undefined;
}

export function CorrectionHistoryPanel({
  corrections = [],
}: CorrectionHistoryPanelProps) {
  if (corrections.length === 0) {
    return (
      <Card className="border shadow-sm">
        <CardHeader className="border-b px-5 py-3">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            <span>Correction History</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-5 text-center text-xs text-muted-foreground">
          No manual corrections have been applied to this document.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border shadow-sm">
      <CardHeader className="border-b px-5 py-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            <span>Correction History</span>
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {corrections.length} correction{corrections.length === 1 ? "" : "s"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="divide-y divide-border/60">
          {corrections.map((corr) => (
            <div key={corr.id} className="p-4 space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-foreground font-mono">
                  {corr.field_name}
                </span>
                <span className="text-muted-foreground text-[11px]">
                  {formatDateTime(corr.created_at)}
                </span>
              </div>

              <div className="flex items-center gap-2 font-mono text-[11px] bg-muted/40 p-2 rounded">
                <span className="text-destructive line-through">
                  {corr.original_value || "—"}
                </span>
                <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className="text-emerald-700 dark:text-emerald-300 font-semibold">
                  {corr.corrected_value || "—"}
                </span>
              </div>

              {corr.correction_reason && (
                <p className="text-[11px] text-muted-foreground italic">
                  Reason: &ldquo;{corr.correction_reason}&rdquo;
                </p>
              )}

              <div className="flex items-center gap-1 text-[10px] text-muted-foreground pt-0.5">
                <UserIcon className="h-3 w-3" />
                <span>By user ID: {corr.corrected_by}</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

