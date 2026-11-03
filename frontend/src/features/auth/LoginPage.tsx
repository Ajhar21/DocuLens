import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, FileText, Loader2, ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { loginSchema, type LoginFormValues } from "./login-schema";
import { useAuth } from "./use-auth";

interface LocationState {
  from?: string;
}

interface LoginBanner {
  title: string;
  description: string;
}

function mapLoginError(err: unknown): LoginBanner {
  if (err instanceof ApiError) {
    if (
      err.code === "account_inactive" ||
      err.message.toLowerCase().includes("inactive")
    ) {
      return {
        title: "Account inactive",
        description:
          "Your account has been deactivated. Contact an administrator to restore access.",
      };
    }
    if (err.kind === "unauthorized" || err.code === "invalid_credentials") {
      return {
        title: "Invalid credentials",
        description:
          "The email or password you entered is incorrect. Please check and try again.",
      };
    }
    if (err.kind === "network") {
      return {
        title: "Connection failed",
        description:
          "Unable to reach the DocuLens server. Verify your network connection and try again.",
      };
    }
    return {
      title: "Sign-in failed",
      description: err.message,
    };
  }
  return {
    title: "Sign-in failed",
    description: "An unexpected error occurred. Please try again.",
  };
}

export function LoginPage() {
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [bannerError, setBannerError] = useState<LoginBanner | null>(null);

  const expiredSession = searchParams.get("reason") === "expired";
  const fromPath = (location.state as LocationState | null)?.from || "/documents";

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  if (status === "authenticated") {
    return <Navigate to={fromPath} replace />;
  }

  const onSubmit = async (values: LoginFormValues) => {
    setBannerError(null);
    try {
      await login(values.email, values.password);
      navigate(fromPath, { replace: true });
    } catch (err) {
      setBannerError(mapLoginError(err));
    }
  };

  return (
    <div className="grid min-h-screen bg-gradient-to-br from-zinc-50 via-white to-indigo-50/40 lg:grid-cols-12">
      {/* Left column: restrained product positioning */}
      <div className="hidden flex-col justify-between border-r bg-zinc-950 p-10 text-zinc-100 lg:col-span-5 lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <FileText className="h-4 w-4" />
          </div>
          <span className="text-base font-semibold tracking-tight">DocuLens</span>
        </div>

        <div className="space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1 text-xs font-medium text-zinc-300">
            <ShieldCheck className="h-3.5 w-3.5 text-indigo-400" />
            Financial Document Intelligence
          </div>
          <h1 className="text-2xl font-semibold leading-snug tracking-tight text-white">
            Ingest, verify, and parse financial documents with deterministic auditability.
          </h1>
          <p className="text-sm leading-relaxed text-zinc-400">
            Upload invoices, receipts, and spreadsheets in batches. Every file is
            verified against magic-byte signatures, queued for resilient background
            extraction, and tracked in real time.
          </p>
          <ul className="space-y-2.5 pt-2 text-xs text-zinc-300">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-indigo-400" />
              PDF, PNG, JPEG, XLSX, and CSV batch ingestion
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-indigo-400" />
              Per-file validation and transparent rejection diagnostics
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-indigo-400" />
              Role-based access control for Reviewers, Viewers, and Admins
            </li>
          </ul>
        </div>

        <p className="text-xs text-zinc-500">
          DocuLens Enterprise · Secure Document Workspace
        </p>
      </div>

      {/* Right column: centered login card */}
      <div className="flex flex-col items-center justify-center p-6 sm:p-10 lg:col-span-7">
        <div className="w-full max-w-md space-y-6">
          <div className="flex items-center gap-2.5 lg:hidden">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <FileText className="h-4 w-4" />
            </div>
            <span className="text-base font-semibold tracking-tight">DocuLens</span>
          </div>

          <Card className="border-border/80 shadow-sm">
            <CardHeader className="space-y-1.5">
              <CardTitle className="text-xl font-semibold tracking-tight">
                Sign in to your account
              </CardTitle>
              <CardDescription>
                Enter your work email and password to access the document workspace.
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
              {expiredSession && !bannerError && (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle>Session expired</AlertTitle>
                  <AlertDescription>
                    Your session has expired or was invalidated. Please sign in again.
                  </AlertDescription>
                </Alert>
              )}

              {bannerError && (
                <Alert variant="destructive" data-testid="login-error-alert">
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle>{bannerError.title}</AlertTitle>
                  <AlertDescription>{bannerError.description}</AlertDescription>
                </Alert>
              )}

              <form
                onSubmit={handleSubmit(onSubmit)}
                noValidate
                className="space-y-4"
              >
                <div className="space-y-1.5">
                  <Label htmlFor="email">Email address</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    placeholder="name@company.com"
                    aria-invalid={Boolean(errors.email)}
                    aria-describedby={errors.email ? "email-error" : undefined}
                    disabled={isSubmitting}
                    {...register("email")}
                  />
                  {errors.email && (
                    <p
                      id="email-error"
                      role="alert"
                      className="text-xs font-medium text-destructive"
                    >
                      {errors.email.message}
                    </p>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    placeholder="••••••••"
                    aria-invalid={Boolean(errors.password)}
                    aria-describedby={
                      errors.password ? "password-error" : undefined
                    }
                    disabled={isSubmitting}
                    {...register("password")}
                  />
                  {errors.password && (
                    <p
                      id="password-error"
                      role="alert"
                      className="text-xs font-medium text-destructive"
                    >
                      {errors.password.message}
                    </p>
                  )}
                </div>

                <Button
                  type="submit"
                  className="w-full"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Signing in…
                    </>
                  ) : (
                    "Sign in"
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

