"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { Job, JobCreate } from "../lib/types";

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function JobForm({ onCreated }: { onCreated?: (job: Job) => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const payload: JobCreate = {
      title: value("title"),
      description: value("description"),
      modality: value("modality") || null,
      location: value("location") || null,
      seniority: value("seniority") || null,
      owner_id: value("owner_id"),
    };

    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const job = await apiFetch<Job>("/api/v1/jobs", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      form.reset();
      setMessage(`Vacante creada: ${job.title}.`);
      onCreated?.(job);
    } catch (cause) {
      setError(describeError(cause, "No se pudo crear la vacante."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={submitting} className="space-y-3">
      <h3 className="text-sm font-semibold">Nueva vacante</h3>
      <div className="space-y-1">
        <label htmlFor="job-title" className="block text-sm font-semibold">
          Título
        </label>
        <input
          id="job-title"
          name="title"
          type="text"
          required
          maxLength={200}
          disabled={submitting}
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="job-description" className="block text-sm font-semibold">
          Descripción
        </label>
        <textarea
          id="job-description"
          name="description"
          rows={3}
          disabled={submitting}
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <label htmlFor="job-modality" className="block text-sm font-semibold">
            Modalidad
          </label>
          <input
            id="job-modality"
            name="modality"
            type="text"
            disabled={submitting}
            className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="job-location" className="block text-sm font-semibold">
            Ubicación
          </label>
          <input
            id="job-location"
            name="location"
            type="text"
            disabled={submitting}
            className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="job-seniority" className="block text-sm font-semibold">
            Seniority
          </label>
          <input
            id="job-seniority"
            name="seniority"
            type="text"
            disabled={submitting}
            className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
          />
        </div>
      </div>
      <div className="space-y-1">
        <label htmlFor="job-owner" className="block text-sm font-semibold">
          ID del responsable (UUID)
        </label>
        <input
          id="job-owner"
          name="owner_id"
          type="text"
          required
          disabled={submitting}
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={submitting}
        className="rounded-sm bg-accent px-4 py-2 text-sm font-semibold text-on-accent disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? "Creando vacante…" : "Crear vacante"}
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
