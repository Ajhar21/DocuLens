import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import { usePermissions, type Permission } from "@/lib/permissions";
import { useAuth } from "./use-auth";

interface ProtectedRouteProps {
  children: ReactNode;
  requiredPermission?: Permission;
}

export function ProtectedRoute({
  children,
  requiredPermission,
}: ProtectedRouteProps) {
  const { status } = useAuth();
  const { can } = usePermissions();
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

  if (requiredPermission && !can(requiredPermission)) {
    return (
      <div className="mx-auto w-full max-w-4xl p-6">
        <ErrorState
          isForbidden
          title="Access Restricted"
          message={`Your assigned role does not have the '${requiredPermission}' permission required to access this resource.`}
        />
      </div>
    );
  }

  return <>{children}</>;
}
