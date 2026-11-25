"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { AuthResponse, LoginRequest } from "../lib/types";

type SubmitStatus = "idle" | "loading" | "success" | "error";

export function LoginForm() {
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
      setMessage("Sesión iniciada. Redirigiendo al panel…");
      router.push("/dashboard");
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof ApiError ? error.message : "No se pudo iniciar sesión.",
      );
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={status === "loading"} className="space-y-4">
      <div className="space-y-1">
        <label htmlFor="login-email" className="block text-sm font-semibold">
          Correo electrónico
        </label>
        <input
          id="login-email"
          name="email"
          type="email"
          autoComplete="email"
          required
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>

      <div className="space-y-1">
        <label htmlFor="login-password" className="block text-sm font-semibold">
          Contraseña
        </label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>

      <button
        type="submit"
        disabled={status === "loading"}
        className="rounded-sm bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
      >
        {status === "loading" ? "Iniciando sesión…" : "Iniciar sesión"}
      </button>

      <p
        aria-live={status === "error" ? "assertive" : "polite"}
        role={status === "error" ? "alert" : undefined}
        className="min-h-5 text-sm text-text-muted"
      >
        {status === "error" ? `Error: ${message}` : message}
      </p>
    </form>
  );
}
