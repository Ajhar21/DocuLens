import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { setUnauthorizedHandler } from "@/lib/api/client";
import type { User } from "@/lib/api/types";
import {
  clearToken,
  decodeTokenExpiryMs,
  getToken,
  isTokenExpired,
  setToken,
} from "@/lib/auth/token-storage";
import { fetchCurrentUser, loginRequest } from "./api";
import { AuthContext, type AuthStatus } from "./auth-context";

const CURRENT_USER_QUERY_KEY = ["auth", "me"] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [token, setTokenState] = useState<string | null>(() => {
    const existing = getToken();
    if (!existing) return null;
    if (isTokenExpired(existing)) {
      clearToken();
      return null;
    }
    return existing;
  });

  const performLogout = useCallback(
    (reason: "manual" | "expired" = "manual") => {
      clearToken();
      setTokenState(null);
      queryClient.clear();
      if (reason === "expired") {
        toast.error("Your session expired. Please sign in again.");
        navigate("/login?reason=expired", { replace: true });
      } else {
        navigate("/login", { replace: true });
      }
    },
    [navigate, queryClient],
  );

  // Register global 401 handler so any authenticated API request that returns 401
  // immediately clears the session and redirects to /login.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      performLogout("expired");
    });
    return () => {
      setUnauthorizedHandler(null);
    };
  }, [performLogout]);

  // Proactively expire session when the JWT `exp` timestamp is reached.
  useEffect(() => {
    if (!token) return;
    const expMs = decodeTokenExpiryMs(token);
    if (expMs === null) return;
    const remainingMs = expMs - Date.now();
    if (remainingMs <= 0) {
      performLogout("expired");
      return;
    }
    const timer = window.setTimeout(() => {
      performLogout("expired");
    }, remainingMs);
    return () => window.clearTimeout(timer);
  }, [token, performLogout]);

  const meQuery = useQuery({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: fetchCurrentUser,
    enabled: Boolean(token),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const login = useCallback(
    async (email: string, password: string): Promise<User> => {
      const tokenResp = await loginRequest(email, password);
      setToken(tokenResp.access_token);
      setTokenState(tokenResp.access_token);
      try {
        const user = await queryClient.fetchQuery({
          queryKey: CURRENT_USER_QUERY_KEY,
          queryFn: fetchCurrentUser,
          staleTime: 5 * 60 * 1000,
        });
        return user;
      } catch (err) {
        clearToken();
        setTokenState(null);
        throw err;
      }
    },
    [queryClient],
  );

  const status: AuthStatus = useMemo(() => {
    if (!token) return "anonymous";
    if (meQuery.isPending) return "loading";
    if (meQuery.isError || !meQuery.data) return "anonymous";
    return "authenticated";
  }, [token, meQuery.isPending, meQuery.isError, meQuery.data]);

  const value = useMemo(
    () => ({
      user: meQuery.data ?? null,
      status,
      login,
      logout: performLogout,
    }),
    [meQuery.data, status, login, performLogout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

