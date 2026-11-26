"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  AgentEvent,
  AgentEventList,
  AgentRun,
  AgentRunList,
  AgentRunStart,
  AgentRunStatus,
  Approval,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/shadcn/table";
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

function formatUtc(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

export function AgentRunPanel() {
  const [applicationId, setApplicationId] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [listing, setListing] = useState(false);
  const [runs, setRuns] = useState<AgentRunList["items"]>([]);
  const [listStatus, setListStatus] = useState<AgentRunStatus | "">("");
  const [listAgent, setListAgent] = useState("");
  const [listDateFrom, setListDateFrom] = useState("");
  const [listDateTo, setListDateTo] = useState("");
  const [listJobId, setListJobId] = useState("");
  const [listCandidateId, setListCandidateId] = useState("");
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

  async function listRuns(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (listing) return;
    const params = new URLSearchParams();
    if (listStatus) params.set("status", listStatus);
    if (listAgent.trim()) params.set("agent", listAgent.trim());
    if (listDateFrom) params.set("date_from", listDateFrom);
    if (listDateTo) params.set("date_to", listDateTo);
    if (listJobId.trim()) params.set("job_id", listJobId.trim());
    if (listCandidateId.trim()) params.set("candidate_id", listCandidateId.trim());
    setListing(true);
    setError(null);
    try {
      const list = await apiFetch<AgentRunList>(`/api/v1/agents/runs?${params.toString()}`);
      setRuns(list.items ?? []);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setListing(false);
    }
  }

  async function selectRun(runId: string) {
    setError(null);
    setNotice(null);
    setLoadingDetail(true);
    try {
      await loadRun(runId);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setLoadingDetail(false);
    }
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
          <Label htmlFor="agent-application-id" className="block">
            ID de postulación
          </Label>
          <Input
            id="agent-application-id"
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
          />
        </div>
        <div className="min-w-48 flex-1 space-y-1">
          <Label htmlFor="agent-idempotency-key" className="block">
            Clave de idempotencia
          </Label>
          <Input
            id="agent-idempotency-key"
            value={idempotencyKey}
            onChange={(event) => setIdempotencyKey(event.target.value)}
            required
            maxLength={100}
          />
        </div>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Iniciando…" : "Iniciar ejecución"}
        </Button>
      </form>

      <form onSubmit={(event) => void listRuns(event)} className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <Label htmlFor="agent-list-status" className="block">
            Estado (filtro)
          </Label>
          <Select
            id="agent-list-status"
            value={listStatus}
            onChange={(event) => setListStatus(event.target.value as AgentRunStatus | "")}
          >
            <option value="">Todos</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="agent-list-agent" className="block">
            Agente (filtro)
          </Label>
          <Input
            id="agent-list-agent"
            value={listAgent}
            onChange={(event) => setListAgent(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="agent-list-date-from" className="block">
            Desde
          </Label>
          <Input
            id="agent-list-date-from"
            type="date"
            value={listDateFrom}
            onChange={(event) => setListDateFrom(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="agent-list-date-to" className="block">
            Hasta
          </Label>
          <Input
            id="agent-list-date-to"
            type="date"
            value={listDateTo}
            onChange={(event) => setListDateTo(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="agent-list-job" className="block">
            Vacante (ID)
          </Label>
          <Input
            id="agent-list-job"
            value={listJobId}
            onChange={(event) => setListJobId(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="agent-list-candidate" className="block">
            Candidato (ID)
          </Label>
          <Input
            id="agent-list-candidate"
            value={listCandidateId}
            onChange={(event) => setListCandidateId(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={listing} className="self-end">
          {listing ? "Buscando…" : "Buscar ejecuciones"}
        </Button>
      </form>

      {runs.length > 0 ? (
        <div className="overflow-x-auto">
          <Table className="text-left">
            <TableCaption className="sr-only">Ejecuciones de agentes</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">Ejecución</TableHead>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">Agente</TableHead>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">Estado</TableHead>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">Vacante</TableHead>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">Candidato</TableHead>
                <TableHead scope="col" className="py-2 font-semibold">Creada</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="py-2 pr-3">
                    <Button
                      type="button"
                      variant="link"
                      className="h-auto p-0 text-accent underline"
                      onClick={() => void selectRun(item.id)}
                    >
                      {item.id}
                    </Button>
                  </TableCell>
                  <TableCell className="py-2 pr-3">{item.workflow}</TableCell>
                  <TableCell className="py-2 pr-3">{STATUS_LABELS[item.status]}</TableCell>
                  <TableCell className="py-2 pr-3">{item.job_id ?? "—"}</TableCell>
                  <TableCell className="py-2 pr-3">{item.candidate_id ?? "—"}</TableCell>
                  <TableCell className="py-2">{formatUtc(item.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {submitting
          ? "Iniciando ejecución…"
          : loadingDetail
            ? "Cargando detalle, eventos y aprobaciones…"
            : notice}
      </p>
      {error ? (
        <Card role="alert" className="space-y-2 p-3">
          <p className="text-sm">{error}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setError(null);
              setNotice(null);
            }}
          >
            Reintentar con otra ejecución
          </Button>
        </Card>
      ) : null}

      {!run && !error && !submitting && !loadingDetail ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          Ingresa una postulación y una clave de idempotencia para inspeccionar una ejecución.
        </Card>
      ) : null}

      {run ? (
        <div className="space-y-5">
          <section aria-labelledby="agent-run-detail-heading" className="space-y-2">
            <h3 id="agent-run-detail-heading" className="text-base font-semibold">
              Detalle de la ejecución
            </h3>
            <Card className="p-3 text-sm">
              <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
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
            </Card>
            {reviewRequired ? (
              <Card role="status" className="px-3 py-2 text-sm">
                review_required: revisión humana requerida antes de continuar.
              </Card>
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
