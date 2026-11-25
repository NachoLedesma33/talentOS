"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { GuideRevision, GuideRevisionList } from "../lib/types";

function describeError(cause: unknown): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return "No se pudo cargar el historial.";
}

/** Sólo agregados: nunca se renderiza el snapshot crudo, CV ni secretos. */
function summarizeSnapshot(snapshot: Record<string, unknown>): string {
  const questions = Array.isArray(snapshot.questions) ? snapshot.questions.length : 0;
  const rejected = Array.isArray(snapshot.rejected_questions)
    ? snapshot.rejected_questions.length
    : 0;
  const limitations = Array.isArray(snapshot.limitations) ? snapshot.limitations.length : 0;
  const review = snapshot.review_required === true ? "requerida" : "no requerida";
  return `${questions} preguntas · ${rejected} rechazadas · ${limitations} limitaciones · revisión ${review}`;
}

export function GuideHistory({ guideId }: { guideId: string }) {
  const [revisions, setRevisions] = useState<GuideRevision[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestRevisions = useCallback(
    () =>
      apiFetch<GuideRevisionList>(
        `/api/v1/interviews/guides/${encodeURIComponent(guideId)}/revisions`,
      ),
    [guideId],
  );

  async function load(): Promise<void> {
    setRefreshing(true);
    setError(null);
    try {
      const result = await requestRevisions();
      setRevisions(result.items);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    requestRevisions().then(
      (result) => {
        if (!active) return;
        setRevisions(result.items);
        setLoading(false);
      },
      (cause: unknown) => {
        if (!active) return;
        setError(describeError(cause));
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [requestRevisions]);

  return (
    <section aria-labelledby={`guide-history-heading-${guideId}`} className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`guide-history-heading-${guideId}`} className="text-base font-semibold">
          Historial de cambios
        </h3>
        <button
          type="button"
          disabled={refreshing}
          onClick={() => void load()}
          className="rounded-sm border border-border px-3 py-1 text-sm font-semibold disabled:opacity-60"
        >
          {refreshing ? "Actualizando…" : "Actualizar historial"}
        </button>
      </div>
      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {loading ? "Cargando historial de la guía…" : null}
      </p>
      {error ? (
        <section role="alert" className="rounded-sm border border-border p-2 text-sm">
          {error}
        </section>
      ) : null}

      {!loading && revisions.length === 0 && !error ? (
        <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
          Todavía no hay revisiones registradas para esta guía.
        </p>
      ) : revisions.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <caption className="sr-only">Revisiones de la guía</caption>
            <thead>
              <tr className="border-b border-border">
                <th scope="col" className="py-1 pr-3 font-semibold">
                  Versión
                </th>
                <th scope="col" className="py-1 pr-3 font-semibold">
                  Creado por
                </th>
                <th scope="col" className="py-1 pr-3 font-semibold">
                  Fecha
                </th>
                <th scope="col" className="py-1 font-semibold">
                  Resumen del snapshot saneado
                </th>
              </tr>
            </thead>
            <tbody>
              {revisions.map((item) => (
                <tr key={item.id} className="border-b border-border align-top">
                  <td className="py-1 pr-3">v{item.version}</td>
                  <td className="py-1 pr-3">{item.created_by}</td>
                  <td className="py-1 pr-3">{item.created_at}</td>
                  <td className="py-1">{summarizeSnapshot(item.snapshot)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
