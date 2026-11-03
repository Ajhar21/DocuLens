import { apiRequest } from "@/lib/api/client";
import type { TokenResponse, User } from "@/lib/api/types";

export async function loginRequest(
  email: string,
  password: string,
): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/auth/login", {
    method: "POST",
    formUrlEncoded: {
      username: email.trim().toLowerCase(),
      password,
    },
    auth: false,
    rawResponse: true,
  });
}

export async function fetchCurrentUser(): Promise<User> {
  return apiRequest<User>("/auth/me", {
    method: "GET",
  });
}

