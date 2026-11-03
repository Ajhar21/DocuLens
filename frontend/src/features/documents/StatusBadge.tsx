import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { DocumentStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { DOCUMENT_STATUS_META } from "./status";

interface StatusBadgeProps {
  status: DocumentStatus;
  error?: string | null;
}

export function StatusBadge({ status, error }: StatusBadgeProps) {
  const meta = DOCUMENT_STATUS_META[status];
  const Icon = meta.icon;

  const badge = (
    <Badge
      variant="outline"
      className={cn("font-medium", meta.badgeClassName)}
      data-testid={`status-badge-${status}`}
    >
      <Icon
        className={cn("h-3.5 w-3.5 shrink-0", meta.spin && "animate-spin")}
        aria-hidden="true"
      />
      <span>{meta.label}</span>
    </Badge>
  );

  if (status === "failed" && error) {
    return (
      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex cursor-help">{badge}</span>
          </TooltipTrigger>
          <TooltipContent>
            <p className="font-medium">Parse error</p>
            <p className="mt-0.5 text-primary-foreground/90">{error}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return badge;
}

