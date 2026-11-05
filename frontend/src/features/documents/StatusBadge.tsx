import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  getStatusPresentation,
  type StatusCategory,
} from "./status";

export interface StatusBadgeProps {
  status: string | null | undefined;
  category?: StatusCategory;
  error?: string | null;
  showIcon?: boolean;
  className?: string;
}

/**
 * Universal StatusBadge component driven by the real backend values.
 * - Conveys status via icon + text + color (never color alone).
 * - Tooltip error on hover when error is provided.
 * - Unknown values render the raw string neutrally without crashing.
 */
export function StatusBadge({
  status,
  category,
  error,
  showIcon = true,
  className,
}: StatusBadgeProps) {
  const meta = getStatusPresentation(status, category);
  const Icon = meta.icon;

  const badge = (
    <Badge
      variant="outline"
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium tracking-tight",
        meta.badgeClassName,
        className,
      )}
      data-testid={`status-badge-${status || "unknown"}`}
    >
      {showIcon && (
        <Icon
          className={cn("h-3.5 w-3.5 shrink-0", meta.spin && "animate-spin")}
          aria-hidden="true"
        />
      )}
      <span>{meta.label}</span>
    </Badge>
  );

  if (error) {
    return (
      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex cursor-help">{badge}</span>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs text-xs">
            <p className="font-semibold text-rose-300">Failure reason</p>
            <p className="mt-0.5 break-words text-primary-foreground/90">{error}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return badge;
}
