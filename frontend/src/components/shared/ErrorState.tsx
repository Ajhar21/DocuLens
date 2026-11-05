import { AlertCircle, RefreshCw, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  message?: string;
  isForbidden?: boolean;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title,
  message = "An error occurred while loading this section.",
  isForbidden = false,
  onRetry,
  className,
}: ErrorStateProps) {
  const Icon = isForbidden ? ShieldAlert : AlertCircle;
  const defaultTitle = isForbidden ? "Access Denied" : "Unable to Load Data";

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-destructive/20 bg-destructive/5 p-12 text-center",
        className,
      )}
    >
      <div className="rounded-full bg-destructive/10 p-3 text-destructive">
        <Icon className="h-6 w-6" aria-hidden="true" />
      </div>
      <h3 className="mt-4 text-base font-semibold text-foreground">
        {title || defaultTitle}
      </h3>
      <p className="mt-1.5 max-w-md text-xs text-muted-foreground leading-relaxed">
        {message}
      </p>
      {onRetry && !isForbidden && (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          className="mt-5 gap-2 border-border/80"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Try Again</span>
        </Button>
      )}
    </div>
  );
}

