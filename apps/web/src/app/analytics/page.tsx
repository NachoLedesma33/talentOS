"use client";

import { useCallback, useState } from "react";
import { ApiError, apiFetch } from "../../lib/api";

type ApplicationStage =
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "hired"
  | "rejected";

export interface MetricDefinition {
  key: string;
  name: string;
  description: string;
  unit: string;
  is_estimate: boolean;
}

interface Metric {
  key: string;
  value: number;
  unit: string;
  is_estimate: boolean;
}

interface StageMetric {
  stage: ApplicationStage;
  applications: number;
  arrivals: number;
  exits: number;
  avg_days_in_stage: number | null;
  total_days_in_stage: number;
}

interface PipelineReport {
  generated_at: string;
  jobs_open: number;
  jobs_closed: number;
  stages: StageMetric[];
  conversions: Metric[];
  avg_process_days: number | null;
  definitions: MetricDefinition[];
}

interface OperationalReport {
  generated_at: string;
  assessments_pending_review: number;
  agent_runs_completed: number;
  agent_runs_failed: number;
  automation_runs_executed: number;
  estimated_minutes_saved: number;
  estimates_basis: string;
  definitions: MetricDefinition[];
}

export interface AnalyticsOverview {
  generated_at: string;
  pipeline: PipelineReport;
  operational: OperationalReport;
}

type LoadStatus = "idle" | "loading" | "ready" | "error";

const STAGE_LABELS: Record<ApplicationStage, string> = {
  applied: "Postuladas",
  screening: "Cribado",
  interview: "Entrevista",
  offer: "Oferta",
  hired: "Contratadas",
  rejected: "Rechazadas",
};

const CARD_KEYS = [
  "jobs_open",
  "jobs_closed",
  "assessments_pending_review",
  "agent_runs_completed",
  "agent_runs_failed",
  "automation_runs_executed",
  "estimated_minutes_saved",
] as const;

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

function formatValue(value: number, unit: string): string {
  if (unit === "ratio") return value.toFixed(2);
  if (unit === "days") return value.toFixed(2);
  return String(value);
}

function definitionFor(definitions: MetricDefinition[], key: string): MetricDefinition | null {
  return definitions.find((definition) => definition.key === key) ?? null;
}

function cardValue(key: (typeof CARD_KEYS)[number], report: AnalyticsOverview): number {
  switch (key) {
    case "jobs_open":
      return report.pipeline.jobs_open;
    case "jobs_closed":
      return report.pipeline.jobs_closed;
    case "assessments_pending_review":
      return report.operational.assessments_pending_review;
    case "agent_runs_completed":
      return report.operational.agent_runs_completed;
    case "agent_runs_failed":
      return report.operational.agent_runs_failed;
    case "automation_runs_executed":
      return report.operational.automation_runs_executed;
    case "estimated_minutes_saved":
      return report.operational.estimated_minutes_saved;
  }
}

function cardUnit(key: (typeof CARD_KEYS)[number]): string {
  return key === "estimated_minutes_saved" ? "minutes" : "count";
}

function hasData(report: AnalyticsOverview): boolean {
  const pipeline = report.pipeline;
  const operational = report.operational;
  return (
    pipeline.jobs_open > 0 ||
    pipeline.jobs_closed > 0 ||
    pipeline.stages.some(
      (stage) => stage.applications > 0 || stage.arrivals > 0 || stage.exits > 0,
    ) ||
    operational.assessments_pending_review > 0 ||
    operational.agent_runs_completed > 0 ||
    operational.agent_runs_failed > 0 ||
    operational.automation_runs_executed > 0
  );
}

export default function AnalyticsPage() {
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [report, setReport] = useState<AnalyticsOverview | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (status === "loading") return;
    setStatus("loading");
    setMessage(null);
    try {
      const overview = await apiFetch<AnalyticsOverview>("/api/v1/analytics/overview");
      setReport(overview);
      setStatus("ready");
    } catch (cause) {
      setReport(null);
      setMessage(describeError(cause));
      setStatus("error");
    }
  }, [status]);

  const definitions = report
    ? [...report.pipeline.definitions, ...report.operational.definitions]
    : [];
  const empty = status === "ready" && report !== null && !hasData(report);

  function renderCard(key: (typeof CARD_KEYS)[number], value: number, unit: string) {
    const definition = definitionFor(definitions, key);
    if (!definition) return null;
    return (
      <div key={key} className="space-y-1 rounded-sm border border-border p-3">
        <p className="text-xs font-semibold text-text-muted">{definition.name}</p>
        <p className="text-xl font-semibold tracking-tight">{formatValue(value, unit)}</p>
        <p className="text-xs text-text-muted">
          {definition.is_estimate ? "Estimado" : "Dato real"}
        </p>
      </div>
    );
  }

  return (
    <section aria-labelledby="analytics-heading" aria-busy={status === "loading"} className="space-y-6">
      <div className="space-y-1">
        <h1 id="analytics-heading" className="text-2xl font-semibold tracking-tight">
          Analítica
        </h1>
        <p className="text-sm text-text-muted">
          Métricas del proceso de la organización activa. La organización se toma de la sesión;
          los estimados se marcan explícitamente y no representan coste monetario.
        </p>
      </div>

      <button
        type="button"
        onClick={() => void load()}
        disabled={status === "loading"}
        className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:opacity-60"
      >
        {status === "ready" ? "Actualizar métricas" : "Consultar métricas"}
      </button>

      {status === "loading" ? (
        <p role="status" aria-live="polite" className="text-sm text-text-muted">
          Cargando métricas…
        </p>
      ) : null}

      {status === "error" ? (
        <div role="alert" className="space-y-2">
          <p className="text-sm">{message}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-sm border border-border px-3 py-1 text-sm font-semibold"
          >
            Reintentar
          </button>
        </div>
      ) : null}

      {status === "ready" && report !== null && empty ? (
        <p aria-live="polite" className="text-sm text-text-muted">
          Sin datos para la organización activa en este momento.
        </p>
      ) : null}

      {status === "ready" && report !== null && !empty ? (
        <>
          <div aria-live="polite" className="text-xs text-text-muted">
            Generado: {formatUtc(report.generated_at)}
          </div>

          <section aria-labelledby="analytics-cards-heading" className="space-y-2">
            <h2 id="analytics-cards-heading" className="text-lg font-semibold">
              Indicadores
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {CARD_KEYS.map((key) =>
                renderCard(key, cardValue(key, report), cardUnit(key)),
              )}
            </div>
          </section>

          <section aria-labelledby="analytics-stages-heading" className="space-y-2">
            <h2 id="analytics-stages-heading" className="text-lg font-semibold">
              Etapas del pipeline
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <caption className="sr-only">Postulaciones por etapa de la organización activa</caption>
                <thead>
                  <tr className="border-b border-border">
                    <th scope="col" className="py-2 pr-3 font-semibold">Etapa</th>
                    <th scope="col" className="py-2 pr-3 font-semibold">Postulaciones</th>
                    <th scope="col" className="py-2 pr-3 font-semibold">Llegadas</th>
                    <th scope="col" className="py-2 pr-3 font-semibold">Salidas</th>
                    <th scope="col" className="py-2 pr-3 font-semibold">Días medios (estimado)</th>
                    <th scope="col" className="py-2 pr-3 font-semibold">Días totales (estimado)</th>
                  </tr>
                </thead>
                <tbody>
                  {report.pipeline.stages.map((stage) => (
                    <tr key={stage.stage} className="border-b border-border">
                      <th scope="row" className="py-2 pr-3 font-normal">
                        {STAGE_LABELS[stage.stage]}
                      </th>
                      <td className="py-2 pr-3">{stage.applications}</td>
                      <td className="py-2 pr-3">{stage.arrivals}</td>
                      <td className="py-2 pr-3">{stage.exits}</td>
                      <td className="py-2 pr-3">
                        {stage.avg_days_in_stage === null
                          ? "Sin datos"
                          : formatValue(stage.avg_days_in_stage, "days")}
                      </td>
                      <td className="py-2 pr-3">
                        {formatValue(stage.total_days_in_stage, "days")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="analytics-conversions-heading" className="space-y-2">
            <h2 id="analytics-conversions-heading" className="text-lg font-semibold">
              Conversiones
            </h2>
            <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {report.pipeline.conversions.map((metric) => (
                <li key={metric.key}>
                  <span className="text-text-muted">{metric.key}: </span>
                  <span>{formatValue(metric.value, metric.unit)}</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-text-muted">
              Tiempo total de proceso:{" "}
              {report.pipeline.avg_process_days === null
                ? "Sin datos"
                : formatValue(report.pipeline.avg_process_days, "days")}
              . {report.operational.estimates_basis}.
            </p>
          </section>

          <section aria-labelledby="analytics-definitions-heading" className="space-y-2">
            <h2 id="analytics-definitions-heading" className="text-lg font-semibold">
              Definiciones
            </h2>
            <dl className="grid gap-3 sm:grid-cols-2">
              {definitions.map((definition) => (
                <div key={definition.key} className="space-y-1 rounded-sm border border-border p-3">
                  <dt className="text-sm font-semibold">
                    {definition.name}
                    {definition.is_estimate ? (
                      <span className="ml-2 text-xs font-normal text-text-muted">Estimado</span>
                    ) : null}
                  </dt>
                  <dd className="text-xs text-text-muted">{definition.description}</dd>
                </div>
              ))}
            </dl>
          </section>
        </>
      ) : null}
    </section>
  );
}
