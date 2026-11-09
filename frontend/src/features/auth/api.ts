import { apiRequest } from "@/lib/api/client";
import type {
  AcceptInviteRequest,
  ChangePasswordRequest,
  ResetPasswordRequest,
  TokenResponse,
  User,
} from "@/lib/api/types";

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

export async function changePasswordRequest(
  payload: ChangePasswordRequest,
): Promise<User> {
  return apiRequest<User>("/auth/change-password", {
    method: "POST",
    json: payload,
  });
}

export async function acceptInviteRequest(
  payload: AcceptInviteRequest,
): Promise<TokenResponse & { user: User }> {
  return apiRequest<TokenResponse & { user: User }>("/auth/accept-invite", {
    method: "POST",
    json: payload,
    auth: false,
  });
}

export async function resetPasswordWithTokenRequest(
  payload: ResetPasswordRequest,
): Promise<User> {
  return apiRequest<User>("/auth/reset-password", {
    method: "POST",
    json: payload,
    auth: false,
  });
}

