import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, FileText, Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { acceptInviteRequest, resetPasswordWithTokenRequest } from "./api";

const acceptInviteSchema = z
  .object({
    token: z.string().min(10, "A valid token is required"),
    full_name: z.string().max(255).optional(),
    password: z
      .string()
      .min(12, "Password must be at least 12 characters long")
      .max(255),
    confirm_password: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

type AcceptInviteFormValues = z.infer<typeof acceptInviteSchema>;

export function AcceptInvitePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialToken = searchParams.get("token") ?? "";
  const mode = searchParams.get("mode") === "reset" ? "reset" : "invite";
  const [formError, setFormError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AcceptInviteFormValues>({
    resolver: zodResolver(acceptInviteSchema),
    defaultValues: {
      token: initialToken,
      full_name: "",
      password: "",
      confirm_password: "",
    },
  });

  const onSubmit = async (values: AcceptInviteFormValues) => {
    setFormError(null);
    try {
      if (mode === "reset") {
        await resetPasswordWithTokenRequest({
          token: values.token.trim(),
          password: values.password,
        });
        toast.success("Password reset complete. Please sign in.");
        setCompleted(true);
        setTimeout(() => navigate("/login", { replace: true }), 1200);
      } else {
        await acceptInviteRequest({
          token: values.token.trim(),
          password: values.password,
          full_name: values.full_name?.trim() || undefined,
        });
        toast.success("Invitation accepted! You can now sign in.");
        setCompleted(true);
        setTimeout(() => navigate("/login", { replace: true }), 1200);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Failed to process token. It may have expired or been used.");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md shadow-md">
        <CardHeader className="space-y-2">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <FileText className="h-4 w-4" />
            </div>
            <span className="text-base font-semibold">DocuLens</span>
          </div>
          <CardTitle className="text-xl">
            {mode === "reset" ? "Reset Your Password" : "Accept Your Invitation"}
          </CardTitle>
          <CardDescription>
            {mode === "reset"
              ? "Enter a new password of at least 12 characters using your single-use reset token."
              : "Set your password (minimum 12 characters) to activate your DocuLens account."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {completed ? (
            <div className="space-y-4 py-4 text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-600" />
              <p className="text-sm font-medium">
                {mode === "reset"
                  ? "Your password has been reset."
                  : "Your account is now active."}
              </p>
              <Button asChild className="w-full">
                <Link to="/login">Continue to Sign In</Link>
              </Button>
            </div>
          ) : (
            <>
              {formError && (
                <Alert variant="destructive" className="mb-4">
                  <AlertDescription>{formError}</AlertDescription>
                </Alert>
              )}

              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
                <div className="space-y-1.5">
                  <Label htmlFor="token">
                    {mode === "reset" ? "Reset token" : "Invite token"}
                  </Label>
                  <Input
                    id="token"
                    type="text"
                    placeholder="Paste your single-use token"
                    {...register("token")}
                  />
                  {errors.token && (
                    <p className="text-xs text-destructive">
                      {errors.token.message}
                    </p>
                  )}
                </div>

                {mode === "invite" && (
                  <div className="space-y-1.5">
                    <Label htmlFor="full_name">Full name (optional)</Label>
                    <Input
                      id="full_name"
                      type="text"
                      placeholder="Jane Doe"
                      {...register("full_name")}
                    />
                    {errors.full_name && (
                      <p className="text-xs text-destructive">
                        {errors.full_name.message}
                      </p>
                    )}
                  </div>
                )}

                <div className="space-y-1.5">
                  <Label htmlFor="password">New password (min 12 characters)</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="new-password"
                    {...register("password")}
                  />
                  {errors.password && (
                    <p className="text-xs text-destructive">
                      {errors.password.message}
                    </p>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="confirm_password">Confirm password</Label>
                  <Input
                    id="confirm_password"
                    type="password"
                    autoComplete="new-password"
                    {...register("confirm_password")}
                  />
                  {errors.confirm_password && (
                    <p className="text-xs text-destructive">
                      {errors.confirm_password.message}
                    </p>
                  )}
                </div>

                <Button type="submit" className="w-full" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Activating...
                    </>
                  ) : mode === "reset" ? (
                    "Reset password"
                  ) : (
                    "Accept invite & activate account"
                  )}
                </Button>

                <div className="text-center text-xs text-muted-foreground">
                  Already have an active account?{" "}
                  <Link to="/login" className="font-medium text-primary hover:underline">
                    Sign in
                  </Link>
                </div>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
