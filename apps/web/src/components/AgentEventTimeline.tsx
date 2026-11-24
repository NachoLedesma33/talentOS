"use client";

import type { AgentEvent } from "../lib/types";

/** Espejo de la lista pública del backend; el filtro local es defensa en profundidad. */
const PUBLIC_PAYLOAD_KEYS = new Set([
  "action_type",
  "agent_run_id",
  "approval_id",
  "correlation_id",
  "decided_by",
  "decision",
  "draft_id",
  "duration_ms",
  "error_type",
  "node",
  "resumed",
  "status",
  "version",
  "workflow",
]);

const DETAIL_KEYS = ["node", "duration_ms", "error_type"] as const;

function formatUtc(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function compact(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value) ?? "";
  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

function safePayload(payload: Record<string, unknown>): Record<string, string> {
  const result: Record<string, string> = {};
  for (const key of PUBLIC_PAYLOAD_KEYS) {
    if (
      Object.prototype.hasOwnProperty.call(payload, key) &&
      payload[key] !== null &&
      payload[key] !== undefined
    ) {
      result[key] = compact(payload[key]);
    }
  }
  return result;
}

export function AgentEventTimeline({
  events,
  loading = false,
}: {
  events: AgentEvent[];
  loading?: boolean;
}) {
  return (
    <section aria-labelledby="agent-events-heading" aria-busy={loading} className="space-y-2">
      <div className="space-y-1">
        <h3 id="agent-events-heading" className="text-base font-semibold">
          Traza de la ejecución
        </h3>
        <p aria-live="polite" className="text-sm text-text-muted">
          {loading
            ? "Cargando eventos…"
            : `${events.length} evento${events.length === 1 ? "" : "s"} registrado${events.length === 1 ? "" : "s"}.`}
        </p>
      </div>

      {!loading && events.length === 0 ? (
        <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
          Todavía no hay eventos para esta ejecución.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-sm border border-border">
          <table className="w-full border-collapse text-left text-sm">
            <caption className="sr-only">Eventos de la ejecución con metadatos saneados</caption>
            <thead className="bg-surface-muted text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-semibold">Tipo</th>
                <th scope="col" className="px-3 py-2 font-semibold">Fecha UTC</th>
                <th scope="col" className="px-3 py-2 font-semibold">Correlación</th>
                <th scope="col" className="px-3 py-2 font-semibold">Detalle saneado</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, index) => {
                const payload = safePayload(event.payload ?? {});
                const extra = Object.entries(payload).filter(
                  ([key]) => !DETAIL_KEYS.includes(key as (typeof DETAIL_KEYS)[number]),
                );
                return (
                  <tr key={`${event.event_type}-${event.created_at}-${index}`} className="border-t border-border align-top">
                    <td className="px-3 py-2 font-medium">{event.event_type}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-text-muted">{formatUtc(event.created_at)}</td>
                    <td className="px-3 py-2 text-text-muted">{event.correlation_id}</td>
                    <td className="px-3 py-2">
                      <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                        {DETAIL_KEYS.filter((key) => payload[key] !== undefined).map((key) => (
                          <div key={key}>
                            <dt className="inline font-semibold">{key}: </dt>
                            <dd className="inline">{payload[key]}</dd>
                          </div>
                        ))}
                      </dl>
                      {extra.length > 0 ? (
                        <code className="mt-1 block break-all text-xs text-text-muted">
                          {JSON.stringify(Object.fromEntries(extra))}
                        </code>
                      ) : null}
                      {extra.length === 0 && DETAIL_KEYS.every((key) => payload[key] === undefined) ? (
                        <span className="text-xs text-text-muted">Sin metadatos adicionales.</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
