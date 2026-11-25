"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  AgentEvent,
  AgentEventList,
  AgentRun,
  AgentRunStart,
  AgentRunStatus,
  Approval,
} from "../lib/types";
import { AgentApprovalControls } from "./AgentApprovalControls";
import { AgentEventTimeline } from "./AgentEventTimeline";

const STATUS_LABELS: Record<AgentRunStatus, string> = {
  pending: "Pendiente",
  running: "En curso",
  waiting_approval: "Esperando aprobación",
  completed: "Completada",
  failed: "Fallida",
  cancelled: "Cancelada",
  timed_out: "Agotado por tiempo",
};

function describeError(cause: unknown): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return "No se pudo completar la solicitud.";
}

export function AgentRunPanel() {
  const [applicationId, setApplicationId] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadRun(runId: string) {
    const [detail, eventList, approvalList] = await Promise.all([
      apiFetch<AgentRun>(`/api/v1/agents/runs/${encodeURIComponent(runId)}`),
      apiFetch<AgentEventList>(`/api/v1/agents/runs/${encodeURIComponent(runId)}/events`),
      apiFetch<Approval[]>(`/api/v1/agents/runs/${encodeURIComponent(runId)}/approvals`),
    ]);
    setRun(detail);
    setEvents(eventList.items ?? []);
    setApprovals(Array.isArray(approvalList) ? approvalList : []);
  }

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const application = applicationId.trim();
    const key = idempotencyKey.trim();
    if (!application || !key) return;

    setSubmitting(true);
    setError(null);
    setNotice(null);
    setRun(null);
    setEvents([]);
    setApprovals([]);
    try {
      const body: AgentRunStart = { application_id: application, idempotency_key: key };
      const created = await apiFetch<AgentRun>("/api/v1/agents/runs", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setNotice("Ejecución cargada.");
      setLoadingDetail(true);
      await loadRun(created.id);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setLoadingDetail(false);
      setSubmitting(false);
    }
  }

  const reviewRequired =
    run?.status === "waiting_approval" ||
    approvals.some((item) => item.status === "pending") ||
    events.some(
      (item) =>
        item.event_type === "run.waiting_approval" ||
        item.event_type === "approval.requested",
    );

  return (
    <section aria-labelledby="agent-run-heading" aria-busy={submitting || loadingDetail} className="space-y-5">
      <div className="space-y-1">
        <h2 id="agent-run-heading" className="text-lg font-semibold">
          Ejecutar agente
        </h2>
        <p className="text-sm text-text-muted">
          Trazas verificables y aprobación humana explícita. Sin puntajes ni decisiones automáticas.
        </p>
      </div>

      <form onSubmit={(event) => void start(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1 space-y-1">
          <label htmlFor="agent-application-id" className="block text-sm font-semibold">
            ID de postulación
          </label>
          <input
            id="agent-application-id"
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
            className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
          />
        </div>
        <div className="min-w-48 flex-1 space-y-1">
          <label htmlFor="agent-idempotency-key" className="block text-sm font-semibold">
            Clave de idempotencia
          </label>
          <input
            id="agent-idempotency-key"
            value={idempotencyKey}
            onChange={(event) => setIdempotencyKey(event.target.value)}
            required
            maxLength={100}
            className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {submitting ? "Iniciando…" : "Iniciar ejecución"}
        </button>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {submitting
          ? "Iniciando ejecución…"
          : loadingDetail
            ? "Cargando detalle, eventos y aprobaciones…"
            : notice}
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
            Reintentar con otra ejecución
          </button>
        </section>
      ) : null}

      {!run && !error && !submitting && !loadingDetail ? (
        <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
          Ingresa una postulación y una clave de idempotencia para inspeccionar una ejecución.
        </p>
      ) : null}

      {run ? (
        <div className="space-y-5">
          <section aria-labelledby="agent-run-detail-heading" className="space-y-2">
            <h3 id="agent-run-detail-heading" className="text-base font-semibold">
              Detalle de la ejecución
            </h3>
            <dl className="flex flex-wrap gap-x-6 gap-y-2 rounded-sm border border-border p-3 text-sm">
              <div>
                <dt className="text-xs font-semibold text-text-muted">Workflow: </dt>
                <dd className="inline">{run.workflow}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Versión: </dt>
                <dd className="inline">{run.version}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Estado: </dt>
                <dd className="inline">{STATUS_LABELS[run.status]}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Correlation ID: </dt>
                <dd className="inline">{run.correlation_id}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Duración: </dt>
                <dd className="inline">{run.duration_ms ?? 0} ms</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Proveedor: </dt>
                <dd className="inline">{run.configured_provider ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Modelo: </dt>
                <dd className="inline">{run.configured_model ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Vacante: </dt>
                <dd className="inline">{run.job_id ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Candidato: </dt>
                <dd className="inline">{run.candidate_id ?? "—"}</dd>
              </div>
              {run.output_ref ? (
                <div>
                  <dt className="text-xs font-semibold text-text-muted">Output ref: </dt>
                  <dd className="inline">{run.output_ref}</dd>
                </div>
              ) : null}
            </dl>
            {reviewRequired ? (
              <p role="status" className="rounded-sm border border-border px-3 py-2 text-sm">
                review_required: revisión humana requerida antes de continuar.
              </p>
            ) : null}
          </section>

          <AgentApprovalControls
            runId={run.id}
            approvals={approvals}
            onRunChange={setRun}
            onRefresh={() => loadRun(run.id)}
          />
          <AgentEventTimeline events={events} loading={loadingDetail} />
        </div>
      ) : null}
    </section>
  );
}
