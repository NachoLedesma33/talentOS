"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  AssessmentComparison as AssessmentComparisonDto,
  AssessmentEvidenceRef,
  AssessmentStatus,
  RequirementEvaluationStatus,
} from "../lib/types";

const STATUS_LABELS: Record<RequirementEvaluationStatus, string> = {
  supported: "Respaldado",
  partial: "Parcial",
  not_found: "No encontrado",
  needs_review: "Requiere revisión",
};

const ASSESSMENT_STATUS_LABELS: Record<AssessmentStatus, string> = {
  pending: "Pendiente",
  completed: "Completada",
  failed: "Fallida",
  needs_review: "Requiere revisión",
};

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return "No se pudo completar la comparación.";
}

function statusLabel(status: RequirementEvaluationStatus | null): string {
  return status ? STATUS_LABELS[status] : "—";
}

function optionalText(value: string | null): string {
  return value && value.length > 0 ? value : "—";
}

function truncate(text: string, limit = 120): string {
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function evidenceText(refs: AssessmentEvidenceRef[]): string {
  if (refs.length === 0) return "Sin evidencia verificable";
  return refs
    .map((item) =>
      `${item.document_id} · ${item.field_name} · p.${item.page} · «${truncate(item.quote, 80)}»`,
    )
    .join("; ");
}

export function AssessmentComparison() {
  const [baseId, setBaseId] = useState("");
  const [otherId, setOtherId] = useState("");
  const [comparison, setComparison] = useState<AssessmentComparisonDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const base = baseId.trim();
    const other = otherId.trim();
    if (!base || !other || loading) return;

    setLoading(true);
    setError(null);
    setComparison(null);
    try {
      const result = await apiFetch<AssessmentComparisonDto>(
        `/api/v1/assessment/${encodeURIComponent(base)}/compare?other_id=${encodeURIComponent(other)}`,
      );
      setComparison(result);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="comparison-heading" aria-busy={loading} className="space-y-3">
      <div className="space-y-1">
        <h2 id="comparison-heading" className="text-lg font-semibold">
          Comparar evaluaciones
        </h2>
        <p className="text-sm text-text-muted">
          Cambios por requisito entre versiones, con modelo y prompt de cada evaluación.
        </p>
      </div>

      <form onSubmit={(event) => void compare(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-1">
          <label htmlFor="comparison-base-id" className="block text-sm font-semibold">
            Evaluación base
          </label>
          <input
            id="comparison-base-id"
            value={baseId}
            onChange={(event) => setBaseId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
            className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
          />
        </div>
        <div className="min-w-56 flex-1 space-y-1">
          <label htmlFor="comparison-other-id" className="block text-sm font-semibold">
            Otra evaluación
          </label>
          <input
            id="comparison-other-id"
            value={otherId}
            onChange={(event) => setOtherId(event.target.value)}
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
          {loading ? "Comparando…" : "Comparar evaluaciones"}
        </button>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {loading ? "Comparando evaluaciones…" : null}
      </p>
      {error ? (
        <p role="alert" className="rounded-sm border border-border p-3 text-sm">
          {error}
        </p>
      ) : null}
      {!comparison && !error && !loading ? (
        <p className="text-sm text-text-muted">
          Ingresa dos IDs de evaluación de la misma postulación para ver los cambios.
        </p>
      ) : null}

      {comparison ? (
        <div className="space-y-3">
          <dl className="grid gap-2 text-xs text-text-muted md:grid-cols-2">
            <div className="rounded-sm border border-border p-2">
              <dt className="font-semibold text-text">Evaluación base</dt>
              <dd>
                {comparison.base.assessment_id} · {ASSESSMENT_STATUS_LABELS[comparison.base.status]}
              </dd>
              <dd>Modelo: {comparison.base.model_version}</dd>
              <dd>Prompt: {comparison.base.prompt_version}</dd>
            </div>
            <div className="rounded-sm border border-border p-2">
              <dt className="font-semibold text-text">Evaluación comparada</dt>
              <dd>
                {comparison.target.assessment_id} · {ASSESSMENT_STATUS_LABELS[comparison.target.status]}
              </dd>
              <dd>Modelo: {comparison.target.model_version}</dd>
              <dd>Prompt: {comparison.target.prompt_version}</dd>
            </div>
          </dl>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <caption className="pb-2 text-left text-xs text-text-muted">
                Cambios trazables por requisito, sin puntuación agregada.
              </caption>
              <thead>
                <tr className="border-y border-border text-xs uppercase text-text-muted">
                  <th scope="col" className="px-2 py-2">Requisito</th>
                  <th scope="col" className="px-2 py-2">Estado</th>
                  <th scope="col" className="px-2 py-2">Explicación</th>
                  <th scope="col" className="px-2 py-2">Evidencia</th>
                  <th scope="col" className="px-2 py-2">Revisión</th>
                </tr>
              </thead>
              <tbody>
                {comparison.changes.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-2 py-3 text-sm text-text-muted">
                      No hay cambios registrados entre estas versiones.
                    </td>
                  </tr>
                ) : (
                  comparison.changes.map((change) => (
                    <tr key={change.requirement_id} className="border-b border-border align-top">
                      <th scope="row" className="px-2 py-2 text-xs font-semibold">
                        {change.requirement_id}
                      </th>
                      <td className="px-2 py-2">
                        <p>Antes: {statusLabel(change.status.before)}</p>
                        <p>Después: {statusLabel(change.status.after)}</p>
                        <p className="text-xs text-text-muted">
                          {change.status.changed ? "Estado modificado" : "Sin cambios"}
                        </p>
                      </td>
                      <td className="px-2 py-2">
                        <p>Antes: {optionalText(change.explanation.before)}</p>
                        <p>Después: {optionalText(change.explanation.after)}</p>
                        <p className="text-xs text-text-muted">
                          {change.explanation.changed ? "Explicación modificada" : "Sin cambios"}
                        </p>
                      </td>
                      <td className="px-2 py-2">
                        <p>Antes: {evidenceText(change.evidence_refs.before)}</p>
                        <p>Después: {evidenceText(change.evidence_refs.after)}</p>
                        <p className="text-xs text-text-muted">
                          {change.evidence_refs.changed ? "Evidencia modificada" : "Sin cambios"}
                        </p>
                      </td>
                      <td className="px-2 py-2 text-xs">
                        Antes: {change.review_required.before ? "Sí" : "No"}
                        <br />
                        Después: {change.review_required.after ? "Sí" : "No"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
