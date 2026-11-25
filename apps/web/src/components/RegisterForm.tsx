"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { AuthResponse, RegisterRequest } from "../lib/types";

type SubmitStatus = "idle" | "loading" | "success" | "error";

export function RegisterForm() {
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload: RegisterRequest = {
      name: String(data.get("name") ?? "").trim(),
      email: String(data.get("email") ?? "").trim(),
      password: String(data.get("password") ?? ""),
    };

    setStatus("loading");
    setMessage(null);
    try {
      await apiFetch<AuthResponse>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setStatus("success");
      setMessage("Cuenta creada. Ahora puedes iniciar sesión.");
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof ApiError ? error.message : "No se pudo crear la cuenta.");
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={status === "loading"} className="space-y-4">
      <div className="space-y-1">
        <label htmlFor="register-name" className="block text-sm font-semibold">
          Nombre
        </label>
        <input
          id="register-name"
          name="name"
          type="text"
          autoComplete="name"
          required
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>

      <div className="space-y-1">
        <label htmlFor="register-email" className="block text-sm font-semibold">
          Correo electrónico
        </label>
        <input
          id="register-email"
          name="email"
          type="email"
          autoComplete="email"
          required
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>

      <div className="space-y-1">
        <label htmlFor="register-password" className="block text-sm font-semibold">
          Contraseña
        </label>
        <input
          id="register-password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
        <p className="text-xs text-text-muted">Mínimo 8 caracteres.</p>
      </div>

      <button
        type="submit"
        disabled={status === "loading"}
        className="rounded-sm bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
      >
        {status === "loading" ? "Creando cuenta…" : "Crear cuenta"}
      </button>

      <p
        aria-live={status === "error" ? "assertive" : "polite"}
        role={status === "error" ? "alert" : undefined}
        className="min-h-5 text-sm text-text-muted"
      >
        {status === "error" ? `Error: ${message}` : message}
      </p>

      {status === "success" ? (
        <p className="text-sm">
          <a href="/login">Ir a iniciar sesión</a>
        </p>
      ) : null}
    </form>
  );
}
