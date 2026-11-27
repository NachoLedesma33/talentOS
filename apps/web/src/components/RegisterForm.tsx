"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n } from "../lib/i18n";
import type { AuthResponse, RegisterRequest } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Checkbox } from "./ui/shadcn/checkbox";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";

type SubmitStatus = "idle" | "loading" | "success" | "error";

export function RegisterForm() {
  const { t } = useI18n();
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload: RegisterRequest = {
      name: String(data.get("name") ?? "").trim(),
      email: String(data.get("email") ?? "").trim(),
      password: String(data.get("password") ?? ""),
      accept_privacy: data.get("accept_privacy") === "true",
    };

    setStatus("loading");
    setMessage(null);
    try {
      await apiFetch<AuthResponse>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setStatus("success");
      setMessage(t("register.success"));
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof ApiError ? error.message : t("register.error"));
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={status === "loading"} className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="register-name" className="block">
          {t("register.name")}
        </Label>
        <Input
          id="register-name"
          name="name"
          type="text"
          autoComplete="name"
          required
        />
      </div>

      <div className="space-y-1">
        <Label htmlFor="register-email" className="block">
          {t("register.email")}
        </Label>
        <Input
          id="register-email"
          name="email"
          type="email"
          autoComplete="email"
          required
        />
      </div>

      <div className="space-y-1">
        <Label htmlFor="register-password" className="block">
          {t("register.password")}
        </Label>
        <Input
          id="register-password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
        />
        <p className="text-xs text-text-muted">{t("register.passwordHint")}</p>
      </div>

      <div className="space-y-2">
        <div className="flex items-start gap-2">
          <Checkbox
            id="register-consent"
            name="accept_privacy"
            value="true"
            aria-describedby="register-consent-help"
            required
          />
          <Label htmlFor="register-consent" className="text-sm font-normal">
            {t("register.consent")}
          </Label>
        </div>
        <p id="register-consent-help" className="text-xs text-text-muted">
          {t("register.consentHelpIntro")}{" "}
          <a
            href="https://github.com/NachoLedesma33/talentOS/blob/main/docs/privacy-policy.md"
            className="font-medium text-accent hover:opacity-80"
          >
            {t("register.privacyLink")}
          </a>{" "}
          {t("register.consentHelpJoin")}{" "}
          <a
            href="https://github.com/NachoLedesma33/talentOS/blob/main/docs/terms-of-service.md"
            className="font-medium text-accent hover:opacity-80"
          >
            {t("register.termsLink")}
          </a>
          .
        </p>
      </div>

      <Button type="submit" disabled={status === "loading"}>
        {status === "loading" ? t("register.submitting") : t("register.submit")}
      </Button>

      <p
        aria-live={status === "error" ? "assertive" : "polite"}
        role={status === "error" ? "alert" : undefined}
        className="min-h-5 text-sm text-text-muted"
      >
        {status === "error" ? `${t("register.errorPrefix")} ${message}` : message}
      </p>

      {status === "success" ? (
        <p className="text-sm">
          <a href="/login">{t("register.loginLink")}</a>
        </p>
      ) : null}
    </form>
  );
}
