const rawBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;

export const config = {
  apiBaseUrl: (rawBaseUrl?.trim() || "/api").replace(/\/+$/, ""),
} as const;

