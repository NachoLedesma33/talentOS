"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../../lib/api";
import type {
  PasswordResetRequest,
  PasswordResetRequestResponse,
} from "../../lib/types";
import { Button } from "../../components/ui/shadcn/button";
import { Card } from "../../components/ui/shadcn/card";
import { Input } from "../../components/ui/shadcn/input";
import { Label } from "../../components/ui/shadcn/label";

type SubmitStatus = "idle" | "loading" | "success" | "error";

export default function ForgotPasswordPage() {
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload: PasswordResetRequest = {
      email: String(data.get("email") ?? "").trim(),
    };

    setStatus("loading");
    setMessage(null);
    setDevToken(null);
    try {
      const response = await apiFetch<PasswordResetRequestResponse>(
        "/api/v1/auth/forgot-password",
        { method: "POST", body: JSON.stringify(payload) },
      );
      setStatus("success");
      setMessage(response.message);
      setDevToken(response.dev_token);
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof ApiError ? error.message : "No se pudo solicitar el restablecimiento.",
      );
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-4">
        <div className="space-y-1">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            TalentOS
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">Recuperar contraseña</h1>
          <p className="text-sm text-text-muted">
            Ingresá tu correo. Si existe una cuenta, te daremos el siguiente paso.
          </p>
        </div>
        <Card className="p-5">
          <form onSubmit={handleSubmit} aria-busy={status === "loading"} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="forgot-email" className="block">
                Correo electrónico
              </Label>
              <Input
                id="forgot-email"
                name="email"
                type="email"
                autoComplete="email"
                required
              />
            </div>

            <Button type="submit" disabled={status === "loading"}>
              {status === "loading" ? "Enviando…" : "Enviar instrucciones"}
            </Button>

            <p
              aria-live={status === "error" ? "assertive" : "polite"}
              role={status === "error" ? "alert" : undefined}
              className="min-h-5 text-sm text-text-muted"
            >
              {status === "error" ? `Error: ${message}` : message}
            </p>

            {status === "success" && devToken ? (
              <div className="space-y-2 rounded-md border border-border bg-surface-muted p-3 text-sm">
                <p className="font-medium">Modo demo: no se envió ningún correo.</p>
                <p className="text-text-muted">Usá este token para continuar:</p>
                <code className="block break-all text-xs">{devToken}</code>
                <Link
                  href={`/reset-password?token=${encodeURIComponent(devToken)}`}
                  className="font-medium text-accent hover:opacity-80"
                >
                  Continuar con el restablecimiento
                </Link>
              </div>
            ) : null}
          </form>
        </Card>
        <p className="text-sm text-text-muted">
          <Link href="/login" className="font-medium text-accent hover:opacity-80">
            Volver a iniciar sesión
          </Link>
        </p>
      </div>
    </main>
  );
}
