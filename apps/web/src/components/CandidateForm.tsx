"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { Candidate, CandidateCreate } from "../lib/types";

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function CandidateForm({ onCreated }: { onCreated?: (candidate: Candidate) => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const payload: CandidateCreate = {
      name: value("name"),
      email: value("email"),
      location: value("location") || null,
    };

    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const candidate = await apiFetch<Candidate>("/api/v1/candidates", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      form.reset();
      setMessage(`Candidato creado: ${candidate.name}.`);
      onCreated?.(candidate);
    } catch (cause) {
      setError(describeError(cause, "No se pudo crear el candidato."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={submitting} className="space-y-3">
      <h3 className="text-sm font-semibold">Nuevo candidato</h3>
      <div className="space-y-1">
        <label htmlFor="candidate-name" className="block text-sm font-semibold">
          Nombre
        </label>
        <input
          id="candidate-name"
          name="name"
          type="text"
          required
          maxLength={200}
          disabled={submitting}
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="candidate-email" className="block text-sm font-semibold">
          Correo electrónico
        </label>
        <input
          id="candidate-email"
          name="email"
          type="email"
          required
          disabled={submitting}
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="candidate-location" className="block text-sm font-semibold">
          Ubicación
        </label>
        <input
          id="candidate-location"
          name="location"
          type="text"
          disabled={submitting}
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={submitting}
        className="rounded-sm bg-accent px-4 py-2 text-sm font-semibold text-on-accent disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? "Creando candidato…" : "Crear candidato"}
      </button>
      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {error ? (
          <span role="alert" className="text-text">
            {error}
          </span>
        ) : (
          message
        )}
      </p>
    </form>
  );
}
