import { apiRequest } from "@/lib/api/client";
import type {
  AuditLogPage,
  PasswordResetLinkResponse,
  RoleName,
  User,
  UserInviteRequest,
  UserInviteResponse,
} from "@/lib/api/types";

export async function listAdminUsers(params?: {
  role?: RoleName;
  is_active?: boolean;
}): Promise<User[]> {
  return apiRequest<User[]>("/admin/users", {
    method: "GET",
    query: params,
  });
}

export async function inviteAdminUser(
  payload: UserInviteRequest,
): Promise<UserInviteResponse> {
  return apiRequest<UserInviteResponse>("/admin/users/invite", {
    method: "POST",
    json: payload,
  });
}

export async function resendAdminUserInvite(
  userId: string,
): Promise<UserInviteResponse> {
  return apiRequest<UserInviteResponse>(
    `/admin/users/${userId}/resend-invite`,
    {
      method: "POST",
    },
  );
}

export async function revokeAdminUserInvite(userId: string): Promise<User> {
  return apiRequest<User>(`/admin/users/${userId}/revoke-invite`, {
    method: "POST",
  });
}

export async function updateAdminUserRole(
  userId: string,
  role: RoleName,
): Promise<User> {
  return apiRequest<User>(`/admin/users/${userId}/role`, {
    method: "PATCH",
    json: { role },
  });
}

export async function deactivateAdminUser(userId: string): Promise<User> {
  return apiRequest<User>(`/admin/users/${userId}/deactivate`, {
    method: "POST",
  });
}

export async function reactivateAdminUser(userId: string): Promise<User> {
  return apiRequest<User>(`/admin/users/${userId}/reactivate`, {
    method: "POST",
  });
}

export async function requestAdminUserPasswordReset(
  userId: string,
): Promise<PasswordResetLinkResponse> {
  return apiRequest<PasswordResetLinkResponse>(
    `/admin/users/${userId}/reset-password`,
    {
      method: "POST",
    },
  );
}

export async function listUserAuditLogs(params?: {
  limit?: number;
  offset?: number;
  action?: string;
}): Promise<AuditLogPage> {
  return apiRequest<AuditLogPage>("/audit-logs", {
    method: "GET",
    query: {
      entity_type: "USER",
      limit: params?.limit ?? 25,
      offset: params?.offset ?? 0,
      action: params?.action,
    },
  });
}
