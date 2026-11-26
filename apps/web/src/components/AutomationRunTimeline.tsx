"use client";

import type {
  AutomationRunEvent,
  AutomationRunMode,
  AutomationRunStatus,
  AutomationRunSummary,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/shadcn/table";

/** Espejo de las claves públicas del backend; defensa en profundidad en la UI. */
const PUBLIC_PAYLOAD_KEYS = new Set([
  "action_id",
  "action_index",
  "action_type",
  "approval_id",
  "attempt",
  "condition_count",
  "correlation_id",
  "decision",
  "draft_id",
  "from_stage",
  "kind",
  "matched",
  "reason_code",
  "resource_id",
  "run_id",
  "status",
  "target_stage",
  "template_id",
  "to_stage",
]);

const RUN_STATUS_LABELS: Record<AutomationRunStatus, string> = {
  pending: "Pendiente",
  running: "En curso",
  waiting_approval: "Esperando aprobación",
  completed: "Completada",
  failed: "Fallida",
  cancelled: "Cancelada",
  timed_out: "Agotado por tiempo",
};

const RUN_MODE_LABELS: Record<AutomationRunMode, string> = {
  test: "Prueba",
  live: "Real",
};

const SENSITIVE_VALUE = /@|https?:\/\/|www\.|\/private\/|sk-/i;

function formatUtc(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function formatDuration(run: AutomationRunSummary): string | null {
  const start = Date.parse(run.created_at);
  const end = Date.parse(run.updated_at);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  const milliseconds = end - start;
  return milliseconds < 1000
    ? `${milliseconds} ms`
    : `${(milliseconds / 1000).toFixed(1)} s`;
}

function compact(value: unknown): string {
  const text = typeof value === "string" ? value : (JSON.stringify(value) ?? "");
  if (SENSITIVE_VALUE.test(text)) return "[dato omitido]";
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

export function AutomationRunTimeline({
  runs,
  events,
  selectedRunId = null,
  loading = false,
  error = null,
  onSelectRun,
}: {
  runs: AutomationRunSummary[];
  events: AutomationRunEvent[];
  selectedRunId?: string | null;
  loading?: boolean;
  error?: string | null;
  onSelectRun?: (runId: string) => void;
}) {
  return (
    <section aria-labelledby="automation-timeline-heading" aria-busy={loading} className="space-y-4">
      <div className="space-y-1">
        <h3 id="automation-timeline-heading" className="text-base font-semibold">
          Ejecuciones y traza
        </h3>
        <p aria-live="polite" className="text-sm text-text-muted">
          {loading
            ? "Cargando ejecuciones y eventos…"
            : `${runs.length} ejecución${runs.length === 1 ? "" : "es"} · ${events.length} evento${events.length === 1 ? "" : "s"} registrado${events.length === 1 ? "" : "s"}.`}
        </p>
      </div>

      {error ? (
        <Card role="alert" className="p-3 text-sm">
          {error}
        </Card>
      ) : null}

      <div className="space-y-2">
        <h4 className="text-sm font-semibold">Ejecuciones</h4>
        {!loading && runs.length === 0 && !error ? (
          <Card className="bg-secondary p-3 text-sm text-text-muted">
            No hay ejecuciones registradas para esta automatización.
          </Card>
        ) : (
          <Table className="border border-border text-left">
            <TableCaption className="sr-only">Ejecuciones de la automatización</TableCaption>
            <TableHeader className="bg-surface-muted text-xs uppercase tracking-wide text-text-muted">
              <TableRow>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Ejecución</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Modo</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Estado</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Error</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Creada UTC</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Duración</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Correlación</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run) => {
                const duration = formatDuration(run);
                return (
                  <TableRow
                    key={run.id}
                    className="border-t border-border align-top"
                    aria-current={run.id === selectedRunId ? "true" : undefined}
                  >
                    <TableCell className="px-3 py-2">
                      {onSelectRun ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => onSelectRun(run.id)}
                          aria-label={`Ver ejecución ${run.id}`}
                        >
                          {run.id} · v{run.version}
                        </Button>
                      ) : (
                        <span>{run.id} · v{run.version}</span>
                      )}
                    </TableCell>
                    <TableCell className="px-3 py-2">{RUN_MODE_LABELS[run.mode]}</TableCell>
                    <TableCell className="px-3 py-2">{RUN_STATUS_LABELS[run.status]}</TableCell>
                    <TableCell className="px-3 py-2 text-text-muted">{run.error_code ?? "—"}</TableCell>
                    <TableCell className="whitespace-nowrap px-3 py-2 text-text-muted">
                      {formatUtc(run.created_at)}
                    </TableCell>
                    <TableCell className="px-3 py-2 text-text-muted">{duration ?? "—"}</TableCell>
                    <TableCell className="px-3 py-2 text-text-muted">{run.correlation_id}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>

      <div className="space-y-2">
        <h4 className="text-sm font-semibold">Eventos de la ejecución seleccionada</h4>
        {!loading && events.length === 0 && !error ? (
          <Card className="bg-secondary p-3 text-sm text-text-muted">
            Todavía no hay eventos para esta ejecución.
          </Card>
        ) : (
          <Table className="border border-border text-left">
            <TableCaption className="sr-only">Eventos con payload saneado</TableCaption>
            <TableHeader className="bg-surface-muted text-xs uppercase tracking-wide text-text-muted">
              <TableRow>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Tipo</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Fecha UTC</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Correlación</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">Payload saneado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((event, index) => {
                const payload = safePayload(event.payload ?? {});
                const keys = Object.keys(payload);
                return (
                  <TableRow
                    key={`${event.event_type}-${event.created_at}-${index}`}
                    className="border-t border-border align-top"
                  >
                    <TableCell className="px-3 py-2 font-medium">{event.event_type}</TableCell>
                    <TableCell className="whitespace-nowrap px-3 py-2 text-text-muted">
                      {formatUtc(event.created_at)}
                    </TableCell>
                    <TableCell className="px-3 py-2 text-text-muted">{event.correlation_id}</TableCell>
                    <TableCell className="px-3 py-2">
                      {keys.length === 0 ? (
                        <span className="text-xs text-text-muted">Sin metadatos adicionales.</span>
                      ) : (
                        <code className="block break-all text-xs text-text-muted">
                          {JSON.stringify(payload)}
                        </code>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </section>
  );
}
