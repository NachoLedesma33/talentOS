"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  Job,
  RequirementCategory,
  RequirementCreate,
  RequirementImportance,
  JobRequirement,
} from "../lib/types";

const CATEGORIES: readonly RequirementCategory[] = [
  "skill",
  "experience",
  "education",
  "language",
  "certification",
  "other",
];

const IMPORTANCES: readonly RequirementImportance[] = ["required", "desirable"];

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function RequirementsEditor({ job }: { job: Job | null }) {
  const [submitting, setSubmitting] = useState(false);
  const [requirements, setRequirements] = useState<JobRequirement[]>([]);
  const [loadedJobId, setLoadedJobId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!job) {
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const payload: RequirementCreate = {
      category: value("category") as RequirementCategory,
      description: value("description"),
      importance: value("importance") as RequirementImportance,
      weight: Number(value("weight")),
      weight_justification: value("weight_justification"),
    };

    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const created = await apiFetch<JobRequirement>(
        `/api/v1/jobs/${job.id}/requirements`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      setRequirements((current) =>
        loadedJobId === job.id ? [...current, created] : [created],
      );
      setLoadedJobId(job.id);
      form.reset();
      setMessage("Requisito añadido.");
    } catch (cause) {
      setError(describeError(cause, "No se pudo añadir el requisito."));
    } finally {
      setSubmitting(false);
    }
  }

  const visibleRequirements = loadedJobId === job?.id ? requirements : [];

  return (
    <section aria-labelledby="requirements-heading" className="space-y-3">
      <h3 id="requirements-heading" className="text-sm font-semibold">
        Requisitos
      </h3>
      {job ? (
        <p className="text-sm text-text-muted">Vacante seleccionada: {job.title}</p>
      ) : (
        <p className="text-sm text-text-muted">
          Selecciona una vacante para añadir requisitos.
        </p>
      )}

      <form onSubmit={handleSubmit} aria-busy={submitting} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor="requirement-category" className="block text-sm font-semibold">
              Categoría
            </label>
            <select
              id="requirement-category"
              name="category"
              defaultValue="skill"
              disabled={submitting || !job}
              className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
            >
              {CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="requirement-importance" className="block text-sm font-semibold">
              Importancia
            </label>
            <select
              id="requirement-importance"
              name="importance"
              defaultValue="required"
              disabled={submitting || !job}
              className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
            >
              {IMPORTANCES.map((importance) => (
                <option key={importance} value={importance}>
                  {importance}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="space-y-1">
          <label htmlFor="requirement-description" className="block text-sm font-semibold">
            Descripción del requisito
          </label>
          <textarea
            id="requirement-description"
            name="description"
            rows={2}
            required
            disabled={submitting || !job}
            className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor="requirement-weight" className="block text-sm font-semibold">
              Peso (0 a 1)
            </label>
            <input
              id="requirement-weight"
              name="weight"
              type="number"
              min={0}
              max={1}
              step={0.01}
              defaultValue="0"
              disabled={submitting || !job}
              className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="requirement-justification" className="block text-sm font-semibold">
              Justificación del peso
            </label>
            <input
              id="requirement-justification"
              name="weight_justification"
              type="text"
              disabled={submitting || !job}
              className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={submitting || !job}
          className="rounded-sm bg-accent px-4 py-2 text-sm font-semibold text-on-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Añadiendo requisito…" : "Añadir requisito"}
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

      {visibleRequirements.length > 0 ? (
        <ul className="space-y-1">
          {visibleRequirements.map((requirement) => (
            <li key={requirement.id} className="text-sm text-text-muted">
              <span className="font-semibold text-text">{requirement.category}</span>:{" "}
              {requirement.description} ({requirement.importance}, peso {requirement.weight})
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
