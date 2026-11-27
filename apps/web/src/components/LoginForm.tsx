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
    <form onSubmit={handleSubmit} aria-busy={status === "loading"} className="space-y-4">
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

      <Button type="submit" disabled={status === "loading"}>
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
