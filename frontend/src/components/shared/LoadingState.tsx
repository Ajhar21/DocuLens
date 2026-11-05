import { Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface LoadingStateProps {
  message?: string;
  className?: string;
  lines?: number;
}

export function LoadingState({
  message = "Loading data…",
  className,
  lines = 4,
}: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-border/60 bg-card p-12 text-center shadow-sm",
        className,
      )}
    >
      <Loader2 className="h-8 w-8 animate-spin text-primary" aria-hidden="true" />
      <p className="mt-3 text-sm font-medium text-muted-foreground">{message}</p>
      <div className="mt-6 w-full max-w-md space-y-2">
        {Array.from({ length: lines }).map((_, idx) => (
          <Skeleton
            key={idx}
            className="h-4 w-full"
            style={{ width: `${Math.max(40, 100 - idx * 15)}%` }}
          />
        ))}
      </div>
    </div>
  );
}

