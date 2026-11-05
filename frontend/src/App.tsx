import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { LoginPage } from "@/features/auth/LoginPage";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { DocumentDetailPage } from "@/features/documents/detail/DocumentDetailPage";
import { DocumentsPage } from "@/features/documents/DocumentsPage";
import { ReconciliationDetailPage } from "@/features/reconciliation/ReconciliationDetailPage";
import { ReconciliationListPage } from "@/features/reconciliation/ReconciliationListPage";
import { ReconciliationNewPage } from "@/features/reconciliation/ReconciliationNewPage";
import { ReviewDetailPage } from "@/features/review/ReviewDetailPage";
import { ReviewQueuePage } from "@/features/review/ReviewQueuePage";
import { SearchPage } from "@/features/search/SearchPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/documents" replace />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/documents/:id" element={<DocumentDetailPage />} />
              <Route
                path="/review"
                element={
                  <ProtectedRoute requiredPermission="extraction:view">
                    <ReviewQueuePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/review/:documentId"
                element={
                  <ProtectedRoute requiredPermission="extraction:view">
                    <ReviewDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/reconciliation"
                element={
                  <ProtectedRoute requiredPermission="reconciliation:view">
                    <ReconciliationListPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/reconciliation/new"
                element={
                  <ProtectedRoute requiredPermission="reconciliation:run">
                    <ReconciliationNewPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/reconciliation/:id"
                element={
                  <ProtectedRoute requiredPermission="reconciliation:view">
                    <ReconciliationDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/search"
                element={
                  <ProtectedRoute requiredPermission="search:use">
                    <SearchPage />
                  </ProtectedRoute>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/documents" replace />} />
          </Routes>
          <Toaster />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

