"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  Assessment,
  AssessmentStatus,
  RequirementEvaluation,
  RunAssessmentRequest,
} from "../lib/types";
import { RequirementEvaluationCard } from "./RequirementEvaluationCard";

const STATUS_LABELS: Record<AssessmentStatus, string> = {
  pending: "Pendiente",
  completed: "Completada",
  failed: "Fallida",
  needs_review: "Requiere revisión",
};

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return "No se pudo completar la evaluación.";
}

function List({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold text-text-muted">{title}</h4>
      {items.length > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-text-muted">{empty}</p>
      )}
    </div>
  );
}

export function AssessmentPanel() {
  const [applicationId, setApplicationId] = useState("");
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = applicationId.trim();
    if (!id || loading) return;

    setLoading(true);
    setError(null);
    setNotice(null);
    setAssessment(null);
    try {
      const payload: RunAssessmentRequest = { application_id: id };
      const result = await apiFetch<Assessment>("/api/v1/assessment/run", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const detail = await apiFetch<Assessment>(
        `/api/v1/assessment/${encodeURIComponent(result.id)}`,
      );
      setAssessment(detail);
      setNotice(
        assessment?.id === result.id
          ? "Evaluación existente recuperada."
          : "Evaluación creada.",
      );
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setLoading(false);
    }
  }

  function applyReview(updated: RequirementEvaluation) {
    setAssessment((current) =>
      current
        ? {
            ...current,
            evaluations: current.evaluations.map((item) =>
              item.id === updated.id ? updated : item,
            ),
          }
        : current,
    );
  }

  return (
    <section aria-labelledby="assessment-panel-heading" aria-busy={loading} className="space-y-4">
      <div className="space-y-1">
        <h2 id="assessment-panel-heading" className="text-lg font-semibold">
          Evaluar postulación
        </h2>
        <p className="text-sm text-text-muted">
          Resultados explicables por requisito. Sin puntuación ni decisión automática.
        </p>
      </div>

      <form onSubmit={(event) => void run(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1 space-y-1">
          <label htmlFor="assessment-application-id" className="block text-sm font-semibold">
            ID de postulación
          </label>
          <input
            id="assessment-application-id"
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
            className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {loading ? "Evaluando…" : "Evaluar postulación"}
        </button>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {loading ? "Evaluando evidencia confirmada…" : notice}
      </p>
      {error ? (
        <section role="alert" className="space-y-2 rounded-sm border border-border p-3">
          <p className="text-sm">{error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setNotice(null);
            }}
            className="rounded-sm border border-border px-3 py-1 text-sm font-semibold"
          >
            Reintentar con otra postulación
          </button>
        </section>
      ) : null}
      {!assessment && !error && !loading ? (
        <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
          Ingresa el ID de una postulación para ver sus criterios, evidencias y limitaciones.
        </p>
      ) : null}

      {assessment ? (
        <div className="space-y-4">
          <section aria-labelledby="assessment-summary-heading" className="space-y-3">
            <h3 id="assessment-summary-heading" className="text-base font-semibold">
              Resumen de la evaluación
            </h3>
            <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-text-muted">
              <div>
                <dt className="inline font-semibold">Estado: </dt>
                <dd className="inline">{STATUS_LABELS[assessment.status]}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">Modelo: </dt>
                <dd className="inline">{assessment.model_version}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">Prompt: </dt>
                <dd className="inline">{assessment.prompt_version}</dd>
              </div>
            </dl>
            {assessment.review_required ? (
              <p role="status" className="rounded-sm border border-border px-3 py-2 text-sm">
                Esta evaluación requiere revisión humana antes de considerarse cerrada.
              </p>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-3 rounded-md border border-border p-3">
                <List
                  title="Fortalezas"
                  items={assessment.summary.strengths}
                  empty="Sin fortalezas registradas."
                />
                <List
                  title="Brechas"
                  items={assessment.summary.gaps}
                  empty="Sin brechas registradas."
                />
              </div>
              <div className="space-y-3 rounded-md border border-border p-3">
                <List
                  title="Preguntas sugeridas"
                  items={assessment.summary.questions}
                  empty="Sin preguntas registradas."
                />
                <List
                  title="Limitaciones"
                  items={assessment.limitations}
                  empty="Sin limitaciones registradas."
                />
              </div>
            </div>
          </section>

          <section aria-labelledby="assessment-requirements-heading" className="space-y-2">
            <h3 id="assessment-requirements-heading" className="text-base font-semibold">
              Requisitos evaluados
            </h3>
            {assessment.evaluations.length > 0 ? (
              <ul className="space-y-3">
                {assessment.evaluations.map((evaluation) => (
                  <li
                    key={`${evaluation.id}-${evaluation.status}-${evaluation.reviewed_at ?? "sin-revision"}`}
                  >
                    <RequirementEvaluationCard
                      assessmentId={assessment.id}
                      evaluation={evaluation}
                      onReviewed={applyReview}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-text-muted">
                La evaluación no contiene criterios por requisito.
              </p>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}
