"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../../lib/api";
import type { MessageResponse, PasswordResetConfirm } from "../../lib/types";
import { Button } from "../../components/ui/shadcn/button";
import { Card } from "../../components/ui/shadcn/card";
import { Checkbox } from "../../components/ui/shadcn/checkbox";
import { Input } from "../../components/ui/shadcn/input";
import { Label } from "../../components/ui/shadcn/label";

type SubmitStatus = "idle" | "loading" | "success" | "error";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const tokenFromLink = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload: PasswordResetConfirm = {
      token: String(data.get("token") ?? "").trim(),
      password: String(data.get("password") ?? ""),
      accept_privacy: data.get("accept_privacy") === "true",
    };

    setStatus("loading");
    setMessage(null);
    try {
      const response = await apiFetch<MessageResponse>("/api/v1/auth/reset-password", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setStatus("success");
      setMessage(response.message);
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof ApiError ? error.message : "No se pudo actualizar la contraseña.",
      );
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-4">
        <div className="space-y-1">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            TalentOS
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">Nueva contraseña</h1>
          <p className="text-sm text-text-muted">
            Ingresá el token recibido y elegí una contraseña nueva.
          </p>
        </div>
        <Card className="p-5">
          <form onSubmit={handleSubmit} aria-busy={status === "loading"} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="reset-token" className="block">
                Token de recuperación
              </Label>
              <Input
                id="reset-token"
                name="token"
                type="text"
                defaultValue={tokenFromLink}
                autoComplete="off"
                required
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="reset-password" className="block">
                Contraseña nueva
              </Label>
              <Input
                id="reset-password"
                name="password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
              />
              <p className="text-xs text-text-muted">Mínimo 8 caracteres.</p>
            </div>

            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <Checkbox
                  id="reset-consent"
                  name="accept_privacy"
                  value="true"
                  aria-describedby="reset-consent-help"
                  required
                />
                <Label htmlFor="reset-consent" className="text-sm font-normal">
                  Acepto la política de privacidad y los términos de servicio.
                </Label>
              </div>
              <p id="reset-consent-help" className="text-xs text-text-muted">
                Revisá la{" "}
                <a
                  href="https://github.com/NachoLedesma33/talentOS/blob/main/docs/privacy-policy.md"
                  className="font-medium text-accent hover:opacity-80"
                >
                  política de privacidad
                </a>{" "}
                y los{" "}
                <a
                  href="https://github.com/NachoLedesma33/talentOS/blob/main/docs/terms-of-service.md"
                  className="font-medium text-accent hover:opacity-80"
                >
                  términos de servicio
                </a>
                .
              </p>
            </div>

            <Button type="submit" disabled={status === "loading"}>
              {status === "loading" ? "Actualizando…" : "Actualizar contraseña"}
            </Button>

            <p
              aria-live={status === "error" ? "assertive" : "polite"}
              role={status === "error" ? "alert" : undefined}
              className="min-h-5 text-sm text-text-muted"
            >
              {status === "error" ? `Error: ${message}` : message}
            </p>

            {status === "success" ? (
              <Link href="/login" className="font-medium text-accent hover:opacity-80">
                Ir a iniciar sesión
              </Link>
            ) : null}
          </form>
        </Card>
        <p className="text-sm text-text-muted">
          <Link href="/forgot-password" className="font-medium text-accent hover:opacity-80">
            Solicitar otro token
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<p className="p-10 text-sm text-text-muted">Cargando…</p>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
