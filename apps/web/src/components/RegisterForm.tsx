"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { AuthResponse, RegisterRequest } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";

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
        <Label htmlFor="register-name" className="block">
          Nombre
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
          Correo electrónico
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
          Contraseña
        </Label>
        <Input
          id="register-password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
        />
        <p className="text-xs text-text-muted">Mínimo 8 caracteres.</p>
      </div>

      <Button type="submit" disabled={status === "loading"}>
        {status === "loading" ? "Creando cuenta…" : "Crear cuenta"}
      </Button>

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
