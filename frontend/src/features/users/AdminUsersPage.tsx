import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  History,
  KeyRound,
  Loader2,
  MailPlus,
  RefreshCw,
  Shield,
  UserCheck,
  UserMinus,
  Users,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ROLE_LABELS } from "@/features/auth/roles";
import { useAuth } from "@/features/auth/use-auth";
import { ApiError } from "@/lib/api/errors";
import type { RoleName, User } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import {
  deactivateAdminUser,
  inviteAdminUser,
  listAdminUsers,
  listUserAuditLogs,
  reactivateAdminUser,
  requestAdminUserPasswordReset,
  resendAdminUserInvite,
  revokeAdminUserInvite,
  updateAdminUserRole,
} from "./api";

const ADMIN_USERS_QUERY_KEY = ["admin", "users"] as const;
const USER_AUDIT_QUERY_KEY = ["admin", "user-audit-logs"] as const;

const ALL_ROLES: readonly RoleName[] = [
  "FINANCE_EXECUTIVE",
  "FINANCE_MANAGER",
  "ACCOUNTS_AUDIT",
  "SYSTEM_ADMIN",
];

const inviteUserSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  full_name: z.string().max(255).optional(),
  role: z.enum([
    "FINANCE_EXECUTIVE",
    "FINANCE_MANAGER",
    "ACCOUNTS_AUDIT",
    "SYSTEM_ADMIN",
  ]),
});

type InviteUserFormValues = z.infer<typeof inviteUserSchema>;

interface GeneratedLinkInfo {
  title: string;
  description: string;
  email: string;
  url: string;
  token: string;
  expiresAt: string;
}

function getUserStatus(user: User): "active" | "invited" | "deactivated" {
  if (
    user.status === "active" ||
    user.status === "invited" ||
    user.status === "deactivated"
  ) {
    return user.status;
  }
  return user.is_active ? "active" : "deactivated";
}

function StatusBadge({ status }: { status: "active" | "invited" | "deactivated" }) {
  if (status === "active") {
    return (
      <Badge
        variant="outline"
        className="border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 capitalize"
      >
        Active
      </Badge>
    );
  }
  if (status === "invited") {
    return (
      <Badge
        variant="outline"
        className="border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300 capitalize"
      >
        Invited
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="capitalize">
      Deactivated
    </Badge>
  );
}

export function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();

  const [inviteOpen, setInviteOpen] = useState(false);
  const [generatedLink, setGeneratedLink] = useState<GeneratedLinkInfo | null>(
    null,
  );
  const [copiedField, setCopiedField] = useState<"url" | "token" | null>(null);

  const usersQuery = useQuery({
    queryKey: ADMIN_USERS_QUERY_KEY,
    queryFn: () => listAdminUsers(),
  });

  const auditQuery = useQuery({
    queryKey: USER_AUDIT_QUERY_KEY,
    queryFn: () => listUserAuditLogs({ limit: 20 }),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<InviteUserFormValues>({
    resolver: zodResolver(inviteUserSchema),
    defaultValues: {
      email: "",
      full_name: "",
      role: "FINANCE_EXECUTIVE",
    },
  });

  const refreshData = () => {
    void queryClient.invalidateQueries({ queryKey: ADMIN_USERS_QUERY_KEY });
    void queryClient.invalidateQueries({ queryKey: USER_AUDIT_QUERY_KEY });
  };

  const handleMutationError = (err: unknown, fallback: string) => {
    if (err instanceof ApiError) {
      toast.error(err.message);
      if (err.status === 409) {
        refreshData();
      }
    } else {
      toast.error(fallback);
    }
  };

  const inviteMutation = useMutation({
    mutationFn: inviteAdminUser,
    onSuccess: (res) => {
      toast.success(`Invitation created for ${res.user.email}`);
      setInviteOpen(false);
      reset();
      setGeneratedLink({
        title: "Single-Use Invitation Link",
        description:
          "Copy and share this one-time link with the invited user. Only the SHA-256 hash is stored on the server, so this link cannot be viewed again.",
        email: res.user.email,
        url: res.invite_url,
        token: res.invite_token,
        expiresAt: res.expires_at,
      });
      refreshData();
    },
    onError: (err) => handleMutationError(err, "Failed to invite user"),
  });

  const resendInviteMutation = useMutation({
    mutationFn: resendAdminUserInvite,
    onSuccess: (res) => {
      toast.success(`New invitation link generated for ${res.user.email}`);
      setGeneratedLink({
        title: "Resent Invitation Link",
        description:
          "Previous unused invite tokens for this user have been revoked. Share this new single-use link.",
        email: res.user.email,
        url: res.invite_url,
        token: res.invite_token,
        expiresAt: res.expires_at,
      });
      refreshData();
    },
    onError: (err) => handleMutationError(err, "Failed to resend invitation"),
  });

  const revokeInviteMutation = useMutation({
    mutationFn: revokeAdminUserInvite,
    onSuccess: (updated) => {
      toast.success(`Invitation revoked for ${updated.email}`);
      refreshData();
    },
    onError: (err) => handleMutationError(err, "Failed to revoke invitation"),
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: RoleName }) =>
      updateAdminUserRole(userId, role),
    onSuccess: (updated) => {
      toast.success(
        `Updated ${updated.email} role to ${ROLE_LABELS[updated.role] ?? updated.role}`,
      );
      refreshData();
    },
    onError: (err) => handleMutationError(err, "Failed to update user role"),
  });

  const deactivateMutation = useMutation({
    mutationFn: deactivateAdminUser,
    onSuccess: (updated) => {
      toast.success(`Deactivated ${updated.email}`);
      refreshData();
    },
    onError: (err) => handleMutationError(err, "Failed to deactivate user"),
  });

  const reactivateMutation = useMutation({
    mutationFn: reactivateAdminUser,
    onSuccess: (updated) => {
      toast.success(`Reactivated ${updated.email}`);
      refreshData();
    },
    onError: (err) => handleMutationError(err, "Failed to reactivate user"),
  });

  const resetPasswordMutation = useMutation({
    mutationFn: requestAdminUserPasswordReset,
    onSuccess: (res) => {
      toast.success(`Password reset link generated for ${res.user.email}`);
      setGeneratedLink({
        title: "Single-Use Password Reset Link",
        description:
          "Share this one-time password reset link with the user. It expires automatically after the configured TTL.",
        email: res.user.email,
        url: res.reset_url,
        token: res.reset_token,
        expiresAt: res.expires_at,
      });
      refreshData();
    },
    onError: (err) =>
      handleMutationError(err, "Failed to generate password reset link"),
  });

  const copyToClipboard = async (value: string, field: "url" | "token") => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(field);
      toast.success(
        field === "url" ? "Link copied to clipboard" : "Token copied to clipboard",
      );
      setTimeout(() => setCopiedField(null), 2000);
    } catch {
      toast.error("Could not copy automatically. Please copy the text manually.");
    }
  };

  const users = usersQuery.data ?? [];
  const activeSystemAdminCount = users.filter(
    (u) => u.role === "SYSTEM_ADMIN" && u.is_active,
  ).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Users &amp; Access Control
          </h1>
          <p className="text-sm text-muted-foreground">
            Manage single-tenant workspace users, role assignments, single-use invitations, and security lifecycle events.
          </p>
        </div>
        <Button onClick={() => setInviteOpen(true)}>
          <MailPlus className="mr-2 h-4 w-4" />
          Invite User
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Workspace Users</CardTitle>
              <CardDescription>
                Role changes and account deactivations immediately invalidate active sessions.
              </CardDescription>
            </div>
            <Badge variant="outline" className="gap-1.5">
              <Shield className="h-3.5 w-3.5 text-primary" />
              {activeSystemAdminCount} Active Admin
              {activeSystemAdminCount === 1 ? "" : "s"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {usersQuery.isPending ? (
            <div className="space-y-2.5">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : usersQuery.isError ? (
            <ErrorState
              title="Failed to load users"
              message="Could not retrieve the user directory."
              onRetry={() => void usersQuery.refetch()}
            />
          ) : users.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No users found"
              description="Invite your first team member to get started."
            />
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Last Login</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((u) => {
                    const userStatus = getUserStatus(u);
                    const isSelf = currentUser?.id === u.id;
                    const isLastActiveAdmin =
                      u.role === "SYSTEM_ADMIN" &&
                      u.is_active &&
                      activeSystemAdminCount <= 1;

                    return (
                      <TableRow key={u.id}>
                        <TableCell>
                          <div className="flex flex-col">
                            <span className="font-medium text-foreground">
                              {u.full_name}
                              {isSelf && (
                                <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                                  (you)
                                </span>
                              )}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {u.email}
                            </span>
                          </div>
                        </TableCell>

                        <TableCell>
                          <select
                            aria-label={`Role for ${u.email}`}
                            value={u.role}
                            disabled={
                              isSelf ||
                              isLastActiveAdmin ||
                              roleMutation.isPending
                            }
                            onChange={(e) =>
                              roleMutation.mutate({
                                userId: u.id,
                                role: e.target.value as RoleName,
                              })
                            }
                            className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {ALL_ROLES.map((r) => (
                              <option key={r} value={r}>
                                {ROLE_LABELS[r] ?? r}
                              </option>
                            ))}
                          </select>
                        </TableCell>

                        <TableCell>
                          <div className="flex items-center gap-1.5">
                            <StatusBadge status={userStatus} />
                            {u.must_change_password && (
                              <Badge variant="outline" className="text-[10px]">
                                Must rotate password
                              </Badge>
                            )}
                          </div>
                        </TableCell>

                        <TableCell className="text-xs text-muted-foreground">
                          {u.last_login_at
                            ? formatDateTime(u.last_login_at)
                            : "Never"}
                        </TableCell>

                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {userStatus === "invited" && (
                              <>
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  disabled={resendInviteMutation.isPending}
                                  onClick={() => resendInviteMutation.mutate(u.id)}
                                >
                                  <RefreshCw className="mr-1 h-3.5 w-3.5" />
                                  Resend
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  disabled={revokeInviteMutation.isPending}
                                  onClick={() => revokeInviteMutation.mutate(u.id)}
                                >
                                  <XCircle className="mr-1 h-3.5 w-3.5 text-destructive" />
                                  Revoke
                                </Button>
                              </>
                            )}

                            {userStatus !== "invited" && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={resetPasswordMutation.isPending}
                                onClick={() => resetPasswordMutation.mutate(u.id)}
                              >
                                <KeyRound className="mr-1 h-3.5 w-3.5" />
                                Reset Link
                              </Button>
                            )}

                            {u.is_active ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                disabled={
                                  isSelf ||
                                  isLastActiveAdmin ||
                                  deactivateMutation.isPending
                                }
                                title={
                                  isSelf
                                    ? "You cannot deactivate your own account"
                                    : isLastActiveAdmin
                                      ? "Cannot deactivate the last active System Admin"
                                      : "Deactivate user"
                                }
                                onClick={() => deactivateMutation.mutate(u.id)}
                              >
                                <UserMinus className="mr-1 h-3.5 w-3.5 text-destructive" />
                                Deactivate
                              </Button>
                            ) : (
                              userStatus === "deactivated" && (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  disabled={reactivateMutation.isPending}
                                  onClick={() => reactivateMutation.mutate(u.id)}
                                >
                                  <UserCheck className="mr-1 h-3.5 w-3.5 text-emerald-600" />
                                  Reactivate
                                </Button>
                              )
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* User & Role Audit Trail */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            <div>
              <CardTitle className="text-base">
                Recent User & Access Audit Log
              </CardTitle>
              <CardDescription>
                Immutable record of invitations, role changes, deactivations, and password events.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {auditQuery.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : auditQuery.isError ? (
            <p className="text-xs text-muted-foreground">
              Unable to load audit events.
            </p>
          ) : (auditQuery.data?.items.length ?? 0) === 0 ? (
            <p className="text-xs text-muted-foreground">
              No user lifecycle audit events recorded yet.
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Event</TableHead>
                    <TableHead>Actor</TableHead>
                    <TableHead>Details</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {auditQuery.data?.items.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatDateTime(entry.created_at)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="font-mono text-xs">
                          {entry.action}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">
                        {entry.user_email ?? "System"}
                      </TableCell>
                      <TableCell className="max-w-md truncate font-mono text-xs text-muted-foreground">
                        {JSON.stringify(entry.new_values ?? entry.old_values ?? {})}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Invite User Dialog */}
      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite User to DocuLens</DialogTitle>
            <DialogDescription>
              Creates the user in an invited state and generates a single-use invitation link (expires after 72 hours).
            </DialogDescription>
          </DialogHeader>

          <form
            onSubmit={handleSubmit((values) =>
              inviteMutation.mutate({
                email: values.email.trim().toLowerCase(),
                full_name: values.full_name?.trim() || undefined,
                role: values.role,
              }),
            )}
            className="space-y-4"
            noValidate
          >
            <div className="space-y-1.5">
              <Label htmlFor="invite-email">Email address</Label>
              <Input
                id="invite-email"
                type="email"
                placeholder="colleague@company.com"
                {...register("email")}
              />
              {errors.email && (
                <p className="text-xs text-destructive">{errors.email.message}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="invite-name">Full name (optional)</Label>
              <Input
                id="invite-name"
                type="text"
                placeholder="Alex Rivera"
                {...register("full_name")}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="invite-role">Assigned role</Label>
              <select
                id="invite-role"
                {...register("role")}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {ALL_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r] ?? r}
                  </option>
                ))}
              </select>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setInviteOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={inviteMutation.isPending}>
                {inviteMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating link...
                  </>
                ) : (
                  "Create Invite Link"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Copy Single-Use Link Dialog */}
      <Dialog
        open={Boolean(generatedLink)}
        onOpenChange={(open) => {
          if (!open) setGeneratedLink(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{generatedLink?.title}</DialogTitle>
            <DialogDescription>{generatedLink?.description}</DialogDescription>
          </DialogHeader>

          {generatedLink && (
            <div className="space-y-4">
              <div className="rounded-md bg-muted/50 p-3 text-xs">
                <div>
                  <span className="font-medium">Recipient:</span>{" "}
                  {generatedLink.email}
                </div>
                <div>
                  <span className="font-medium">Expires:</span>{" "}
                  {formatDateTime(generatedLink.expiresAt)}
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="generated-invite-url">One-time action URL</Label>
                <div className="flex gap-2">
                  <Input
                    id="generated-invite-url"
                    readOnly
                    value={generatedLink.url}
                    className="font-mono text-xs"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() =>
                      void copyToClipboard(generatedLink.url, "url")
                    }
                  >
                    {copiedField === "url" ? (
                      <>
                        <Check className="mr-1.5 h-4 w-4 text-emerald-600" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="mr-1.5 h-4 w-4" />
                        Copy Link
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button type="button" onClick={() => setGeneratedLink(null)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
