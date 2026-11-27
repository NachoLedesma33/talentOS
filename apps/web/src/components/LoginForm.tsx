"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n } from "../lib/i18n";
import type { AuthResponse, LoginRequest } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";

type SubmitStatus = "idle" | "loading" | "success" | "error";

export function LoginForm() {
  const { t } = useI18n();
  const router = useRouter();
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload: LoginRequest = {
      email: String(data.get("email") ?? "").trim(),
      password: String(data.get("password") ?? ""),
    };

    setStatus("loading");
    setMessage(null);
    try {
      await apiFetch<AuthResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setStatus("success");
      setMessage(t("login.success"));
      router.push("/dashboard");
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof ApiError ? error.message : t("login.error"));
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={status === "loading"} className="space-y-5">
      <div className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <Button
            type="button"
            variant="outline"
            disabled
            aria-describedby="login-social-note"
            className="gap-2"
          >
            <span aria-hidden="true" className="font-semibold">G</span>
            {t("auth.socialGoogle")}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled
            aria-describedby="login-social-note"
            className="gap-2"
          >
            <span aria-hidden="true" className="font-semibold">⊞</span>
            {t("auth.socialMicrosoft")}
          </Button>
        </div>
        <p id="login-social-note" className="text-xs text-text-muted">
          {t("auth.socialUnavailable")}
        </p>
        <div className="flex items-center gap-3 text-xs text-text-muted">
          <span aria-hidden="true" className="h-px flex-1 bg-border-subtle" />
          {t("auth.socialDivider")}
          <span aria-hidden="true" className="h-px flex-1 bg-border-subtle" />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="login-email" className="block">
          {t("login.email")}
        </Label>
        <Input
          id="login-email"
          name="email"
          type="email"
          autoComplete="email"
          required
        />
      </div>

      <div className="space-y-1">
        <Label htmlFor="login-password" className="block">
          {t("login.password")}
        </Label>
        <Input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
      </div>

      <Button type="submit" disabled={status === "loading"} className="w-full">
        {status === "loading" ? t("login.submitting") : t("login.submit")}
      </Button>

      <p
        aria-live={status === "error" ? "assertive" : "polite"}
        role={status === "error" ? "alert" : undefined}
        className="min-h-5 text-sm text-text-muted"
      >
        {status === "error" ? `${t("login.errorPrefix")} ${message}` : message}
      </p>
    </form>
  );
}
