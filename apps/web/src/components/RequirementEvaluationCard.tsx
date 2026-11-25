"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  AssessmentEvidenceRef,
  RequirementEvaluation,
  RequirementEvaluationStatus,
  ReviewDecision,
} from "../lib/types";

const STATUS_LABELS: Record<RequirementEvaluationStatus, string> = {
  supported: "Respaldado",
  partial: "Parcial",
  not_found: "No encontrado",
  needs_review: "Requiere revisión",
};

const STATUS_MARKS: Record<RequirementEvaluationStatus, string> = {
  supported: "✓",
  partial: "◐",
  not_found: "∅",
  needs_review: "!",
};

const STATUS_OPTIONS: RequirementEvaluationStatus[] = [
  "supported",
  "partial",
  "not_found",
  "needs_review",
];

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return "No se pudo guardar la revisión.";
}

function truncateQuote(quote: string, limit = 160): string {
  return quote.length > limit ? `${quote.slice(0, limit)}…` : quote;
}

function Evidence({ item }: { item: AssessmentEvidenceRef }) {
  return (
    <li className="rounded-sm border border-border bg-surface-muted p-2">
      <p className="text-xs text-text-muted">
        Documento {item.document_id} · Campo {item.field_name} · Página {item.page}
      </p>
      <blockquote
        title={item.quote}
        className="mt-1 border-l-2 border-border pl-2 text-sm text-text"
      >
        «{truncateQuote(item.quote)}»
      </blockquote>
    </li>
  );
}

interface RequirementEvaluationCardProps {
  assessmentId: string;
  evaluation: RequirementEvaluation;
  onReviewed?: (updated: RequirementEvaluation) => void;
}

export function RequirementEvaluationCard({
  assessmentId,
  evaluation,
  onReviewed,
}: RequirementEvaluationCardProps) {
  const [status, setStatus] = useState<RequirementEvaluationStatus>(evaluation.status);
  const [explanation, setExplanation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saved, setSaved] = useState<RequirementEvaluation | null>(null);

  const current = saved ?? evaluation;
  const statusId = `review-status-${evaluation.id}`;
  const explanationId = `review-explanation-${evaluation.id}`;
  const evidenceId = `review-evidence-${evaluation.id}`;

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError(null);
    setMessage(null);
    const payload: ReviewDecision = {
      status,
      explanation: explanation.trim() || null,
    };

    try {
      const updated = await apiFetch<RequirementEvaluation>(
        `/api/v1/assessment/${encodeURIComponent(assessmentId)}/evaluations/${encodeURIComponent(evaluation.id)}/review`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      setSaved(updated);
      setMessage(`Revisión registrada: ${STATUS_LABELS[updated.status]}.`);
      onReviewed?.(updated);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article
      aria-labelledby={`evaluation-${evaluation.id}`}
      className="space-y-3 rounded-md border border-border p-3"
    >
      <div className="space-y-1">
        <h4 id={`evaluation-${evaluation.id}`} className="text-sm font-semibold">
          Estado:{" "}
          <span
            data-status={current.status}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5"
          >
            <span aria-hidden="true">{STATUS_MARKS[current.status]}</span>
            {STATUS_LABELS[current.status]}
          </span>
        </h4>
        <p className="break-words text-xs text-text-muted">
          Requisito {current.requirement_id}
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <p className="text-sm">{current.explanation}</p>
          {current.limitations.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-text-muted">
              {current.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          ) : null}
          {current.review_required ? (
            <p className="text-xs text-text">Requiere revisión humana.</p>
          ) : null}
          {current.reviewed_by || current.reviewed_at ? (
            <p className="text-xs text-text-muted">
              Revisado por {current.reviewed_by ?? "—"}
              {current.reviewed_at ? ` el ${current.reviewed_at}` : ""}
            </p>
          ) : (
            <p className="text-xs text-text-muted">Sin revisión humana registrada.</p>
          )}
        </div>

        <div className="space-y-2">
          <h5 id={evidenceId} className="text-xs font-semibold text-text-muted">
            Evidencia verificable
          </h5>
          {current.evidence.length > 0 ? (
            <ul aria-labelledby={evidenceId} className="space-y-2">
              {current.evidence.map((item, index) => (
                <Evidence
                  key={`${item.document_id}-${item.page}-${item.field_name}-${index}`}
                  item={item}
                />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-text-muted">
              Sin evidencia verificable para este requisito.
            </p>
          )}
        </div>
      </div>

      <form onSubmit={(event) => void submitReview(event)} className="space-y-2">
        <label htmlFor={statusId} className="block text-xs font-semibold">
          Estado corregido
        </label>
        <select
          id={statusId}
          value={status}
          onChange={(event) =>
            setStatus(event.target.value as RequirementEvaluationStatus)
          }
          className="w-full rounded-sm border border-border bg-surface px-2 py-1 text-sm"
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {STATUS_LABELS[option]}
            </option>
          ))}
        </select>
        <label htmlFor={explanationId} className="block text-xs font-semibold">
          Explicación (opcional)
        </label>
        <textarea
          id={explanationId}
          value={explanation}
          onChange={(event) => setExplanation(event.target.value)}
          rows={2}
          className="w-full rounded-sm border border-border bg-surface px-2 py-1 text-sm"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-sm bg-accent px-3 py-1 text-sm font-semibold text-white disabled:opacity-60"
        >
          {busy ? "Guardando revisión…" : "Corregir revisión"}
        </button>
      </form>

      <p aria-live="polite" className="min-h-5 text-xs text-text-muted">
        {error ? (
          <span role="alert" className="text-text">
            {error}
          </span>
        ) : (
          message
        )}
      </p>
    </article>
  );
}
