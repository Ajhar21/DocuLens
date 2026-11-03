import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "./use-auth";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div
        className="flex min-h-screen bg-background"
        aria-busy="true"
        aria-label="Restoring session"
      >
        <aside className="hidden w-60 border-r bg-sidebar p-5 lg:block">
          <Skeleton className="mb-8 h-7 w-32" />
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
          </div>
        </aside>
        <div className="flex flex-1 flex-col">
          <header className="flex h-14 items-center justify-between border-b px-6">
            <Skeleton className="h-5 w-28" />
            <Skeleton className="h-8 w-36 rounded-full" />
          </header>
          <main className="mx-auto w-full max-w-6xl space-y-6 p-6">
            <Skeleton className="h-28 w-full rounded-lg" />
            <Skeleton className="h-64 w-full rounded-lg" />
          </main>
        </div>
      </div>
    );
  }

  if (status === "anonymous") {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  return <>{children}</>;
}

