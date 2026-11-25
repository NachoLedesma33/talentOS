"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  ApplicationStage,
  AutomationAction,
  AutomationActionType,
  AutomationApproval,
  AutomationCondition,
  AutomationConditionField,
  AutomationConditionOperator,
  AutomationDetail,
  AutomationExecutionRequest,
  AutomationList,
  AutomationRunDetail,
  AutomationRunEvent,
  AutomationRunEventList,
  AutomationRunList,
  AutomationRunMode,
  AutomationRunQueueResult,
  AutomationRunStatus,
  AutomationRunSummary,
  AutomationStatus,
  AutomationSummary,
  AutomationTestResult,
  AutomationVersionCreate,
  AutomationVersionResult,
} from "../lib/types";
import { AutomationApprovalControls } from "./AutomationApprovalControls";
import {
  AUTOMATION_ACTION_TYPES,
  AUTOMATION_CONDITION_FIELDS,
  AUTOMATION_CONDITION_OPERATORS,
  AUTOMATION_EMPTY_ACTION_PAYLOAD,
  AUTOMATION_STAGE_VALUES,
  AutomationNodeEditor,
  MAX_ACTIONS,
  MAX_CONDITIONS,
  automationConditionValues,
  buildAutomationVersionPayload,
  createAutomationAction,
  createAutomationCondition,
} from "./AutomationNodeEditor";
import { AutomationRunTimeline } from "./AutomationRunTimeline";

const PAGE_SIZE = 20;

const AUTOMATION_STATUS_LABELS: Record<AutomationStatus, string> = {
  draft: "Borrador",
  active: "Activa",
  inactive: "Inactiva",
  archived: "Archivada",
};

const RUN_STATUS_LABELS: Record<AutomationRunStatus, string> = {
  pending: "Pendiente",
  running: "En curso",
  waiting_approval: "Esperando aprobación",
  completed: "Completada",
  failed: "Fallida",
  cancelled: "Cancelada",
  timed_out: "Agotado por tiempo",
};

const CONDITION_FIELDS = AUTOMATION_CONDITION_FIELDS;
const CONDITION_OPERATORS = AUTOMATION_CONDITION_OPERATORS;
const ACTION_TYPES = AUTOMATION_ACTION_TYPES;
const STAGE_VALUES = AUTOMATION_STAGE_VALUES;
const ALL_STATUSES: Array<AutomationStatus | "all"> = [
  "all",
  "draft",
  "active",
  "inactive",
  "archived",
];

interface ExecutionState {
  kind: AutomationRunMode;
  status: AutomationRunStatus;
  correlationId: string;
  queued: boolean | null;
}

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    if (cause.code === "broker_unavailable" || cause.status === 503) {
      return "broker no disponible, sin cambios.";
    }
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
}

function editorModeButtonClass(active: boolean): string {
  return `rounded-sm border px-3 py-1 text-sm font-semibold ${
    active ? "border-accent bg-surface-muted text-accent" : "border-border bg-surface text-text"
  }`;
}

function requestAutomationList(status: AutomationStatus | "all", pageOffset: number): Promise<AutomationList> {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(pageOffset),
  });
  if (status !== "all") params.set("status", status);
  return apiFetch<AutomationList>(`/api/v1/automations?${params.toString()}`);
}

/** Muestra sólo metadatos de la versión; nunca notas libres ni campos extra. */
function snapshotText(detail: AutomationDetail): string {
  const version = detail.active_version;
  if (!version) return "Sin versión activa.";
  const sanitized = {
    trigger: version.trigger.event_type ?? null,
    conditions: version.conditions.map((item) => ({
      field: item.field ?? null,
      operator: item.operator ?? null,
      value: item.value ?? null,
    })),
    actions: version.actions.map((item) => ({
      type: item.type ?? null,
      target_stage:
        typeof item.payload === "object" && item.payload !== null
          ? (item.payload as Record<string, unknown>).target_stage ?? null
          : null,
    })),
  };
  return JSON.stringify(sanitized);
}

export function AutomationRulePanel() {
  const [name, setName] = useState("");
  const [statusFilter, setStatusFilter] = useState<AutomationStatus | "all">("all");
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<AutomationList | null>(null);
  const [detail, setDetail] = useState<AutomationDetail | null>(null);
  const [conditions, setConditions] = useState<AutomationCondition[]>([createAutomationCondition()]);
  const [actions, setActions] = useState<AutomationAction[]>([createAutomationAction()]);
  const [editorMode, setEditorMode] = useState<"form" | "visual">("form");
  const [applicationId, setApplicationId] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [runs, setRuns] = useState<AutomationRunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<AutomationRunDetail | null>(null);
  const [events, setEvents] = useState<AutomationRunEvent[]>([]);
  const [approvals, setApprovals] = useState<AutomationApproval[]>([]);
  const [execution, setExecution] = useState<ExecutionState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [traceLoading, setTraceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const isBusy = busy !== null;
  const working = isBusy || listLoading || detailLoading || traceLoading;

  async function loadList(nextStatus = statusFilter, nextOffset = offset): Promise<void> {
    setListLoading(true);
    setError(null);
    try {
      setList(await requestAutomationList(nextStatus, nextOffset));
    } catch (cause) {
      setError(describeError(cause, "No se pudo cargar el listado de automatizaciones."));
    } finally {
      setListLoading(false);
    }
  }

  async function loadRuns(automationId: string): Promise<AutomationRunSummary[]> {
    const params = new URLSearchParams({
      automation_id: automationId,
      limit: String(PAGE_SIZE),
      offset: "0",
    });
    const result = await apiFetch<AutomationRunList>(`/api/v1/automations/runs?${params.toString()}`);
    setRuns(result.items);
    return result.items;
  }

  async function loadRunTrace(runId: string | null): Promise<void> {
    if (!runId) {
      setSelectedRun(null);
      setEvents([]);
      setApprovals([]);
      return;
    }
    setTraceLoading(true);
    try {
      const [run, eventList, approvalList] = await Promise.all([
        apiFetch<AutomationRunDetail>(`/api/v1/automations/runs/${encodeURIComponent(runId)}`),
        apiFetch<AutomationRunEventList>(
          `/api/v1/automations/runs/${encodeURIComponent(runId)}/events`,
        ),
        apiFetch<AutomationApproval[]>(
          `/api/v1/automations/runs/${encodeURIComponent(runId)}/approvals`,
        ),
      ]);
      setSelectedRun(run);
      setEvents(eventList.items);
      setApprovals(Array.isArray(approvalList) ? approvalList : []);
      setRuns((current) => current.map((item) => (item.id === run.id ? { ...item, ...run } : item)));
    } catch (cause) {
      setError(describeError(cause, "No se pudo cargar la traza de la ejecución."));
    } finally {
      setTraceLoading(false);
    }
  }

  async function openAutomation(automationId: string, successNotice?: string): Promise<void> {
    setDetailLoading(true);
    setError(null);
    try {
      const loaded = await apiFetch<AutomationDetail>(
        `/api/v1/automations/${encodeURIComponent(automationId)}`,
      );
      const runItems = await loadRuns(automationId);
      setDetail(loaded);
      setExecution(null);
      if (successNotice) setNotice(successNotice);
      await loadRunTrace(runItems[0]?.id ?? null);
    } catch (cause) {
      setDetail(null);
      setError(describeError(cause, "No se pudo cargar la automatización."));
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    requestAutomationList("all", 0).then(
      (result) => {
        if (active) setList(result);
      },
      (cause: unknown) => {
        if (active) setError(describeError(cause, "No se pudo cargar el listado de automatizaciones."));
      },
    ).finally(() => {
      if (active) setListLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);

  async function createAutomation(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const value = name.trim();
    if (!value || working) return;

    setBusy("create");
    setError(null);
    setNotice(null);
    try {
      const created = await apiFetch<AutomationSummary>("/api/v1/automations", {
        method: "POST",
        body: JSON.stringify({ name: value } satisfies { name: string }),
      });
      setName("");
      setNotice("Automatización creada.");
      await loadList();
      await openAutomation(created.id);
    } catch (cause) {
      setError(describeError(cause, "No se pudo crear la automatización."));
    } finally {
      setBusy(null);
    }
  }

  async function saveVersion(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!detail || working) return;
    if (actions.length === 0) {
      setError("Define al menos una acción.");
      return;
    }
    if (
      actions.some(
        (action) => action.type === "propose_stage_change" && !action.payload.target_stage,
      )
    ) {
      setError("Selecciona la etapa propuesta de cada acción.");
      return;
    }

    const payload: AutomationVersionCreate = buildAutomationVersionPayload({
      trigger: { event_type: "application.stage_changed" },
      conditions,
      actions,
    });
    setBusy("version");
    setError(null);
    setNotice(null);
    try {
      await apiFetch<AutomationVersionResult>(
        `/api/v1/automations/${encodeURIComponent(detail.id)}/versions`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      setNotice("Versión creada.");
      await loadList();
      await openAutomation(detail.id);
    } catch (cause) {
      setError(describeError(cause, "No se pudo crear la versión."));
    } finally {
      setBusy(null);
    }
  }

  async function patchStatus(status: AutomationStatus): Promise<void> {
    if (!detail || working) return;
    setBusy(`status:${status}`);
    setError(null);
    setNotice(null);
    try {
      await apiFetch<AutomationDetail>(
        `/api/v1/automations/${encodeURIComponent(detail.id)}`,
        { method: "PATCH", body: JSON.stringify({ status } satisfies { status: AutomationStatus }) },
      );
      setNotice(`Estado actualizado: ${AUTOMATION_STATUS_LABELS[status]}.`);
      await loadList();
      await openAutomation(detail.id);
    } catch (cause) {
      setError(describeError(cause, "No se pudo actualizar el estado."));
    } finally {
      setBusy(null);
    }
  }

  async function execute(mode: AutomationRunMode): Promise<void> {
    if (!detail || working) return;
    const application = applicationId.trim();
    const key = idempotencyKey.trim();
    if (!application || !key) {
      setError("Indica el ID de postulación y la clave de idempotencia.");
      return;
    }

    const body: AutomationExecutionRequest = {
      application_id: application,
      idempotency_key: key,
    };
    const path = `/api/v1/automations/${encodeURIComponent(detail.id)}/${mode === "test" ? "test" : "run"}`;
    setBusy(`execution:${mode}`);
    setError(null);
    setNotice(null);
    try {
      if (mode === "test") {
        const result = await apiFetch<AutomationTestResult>(path, {
          method: "POST",
          body: JSON.stringify(body),
        });
        setExecution({
          kind: "test",
          status: result.status,
          correlationId: result.correlation_id,
          queued: null,
        });
        setNotice("Prueba registrada sin efectos externos.");
        await loadRuns(detail.id);
        await loadRunTrace(result.id);
      } else {
        const result = await apiFetch<AutomationRunQueueResult>(path, {
          method: "POST",
          body: JSON.stringify(body),
        });
        setExecution({
          kind: "live",
          status: result.status,
          correlationId: result.correlation_id,
          queued: result.queued,
        });
        setNotice(
          result.queued
            ? "Ejecución encolada (queued). El estado final lo confirma el servidor."
            : "La clave ya existe; no se reencoló la ejecución.",
        );
        await loadRuns(detail.id);
        await loadRunTrace(result.id);
      }
    } catch (cause) {
      setError(describeError(cause, "No se pudo solicitar la ejecución."));
    } finally {
      setBusy(null);
    }
  }

  function updateCondition(index: number, next: AutomationCondition): void {
    setConditions((current) => current.map((item, position) => (position === index ? next : item)));
  }

  function updateAction(index: number, next: AutomationAction): void {
    setActions((current) => current.map((item, position) => (position === index ? next : item)));
  }

  const selectedRunId = selectedRun?.id ?? null;
  const totalPages = list ? Math.max(1, Math.ceil(list.total / list.limit)) : 1;
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <section aria-labelledby="automation-panel-heading" aria-busy={working} className="space-y-6">
      <div className="space-y-1">
        <h2 id="automation-panel-heading" className="text-lg font-semibold">
          Automatizaciones
        </h2>
        <p className="text-sm text-text-muted">
          Reglas deterministas, versionadas y probables sin efectos externos. Los permisos y el
          estado final los decide el servidor. Sin puntuaciones ni decisiones automáticas.
        </p>
      </div>

      <form onSubmit={(event) => void createAutomation(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1 space-y-1">
          <label htmlFor="automation-name" className="block text-sm font-semibold">
            Nombre de la automatización
          </label>
          <input
            id="automation-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={200}
            placeholder="Regla sintética de etapa"
            className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={working}
          className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-on-accent disabled:opacity-60"
        >
          {busy === "create" ? "Creando…" : "Crear automatización"}
        </button>
      </form>

      <div className="space-y-2">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label htmlFor="automation-status-filter" className="block text-sm font-semibold">
              Filtrar por estado
            </label>
            <select
              id="automation-status-filter"
              value={statusFilter}
              onChange={(event) => {
                const next = event.target.value as AutomationStatus | "all";
                setStatusFilter(next);
                setOffset(0);
                void loadList(next, 0);
              }}
              disabled={working}
              className="rounded-sm border border-border bg-surface px-2 py-2 text-sm"
            >
              <option value="all">Todos</option>
              {ALL_STATUSES.filter((item) => item !== "all").map((item) => (
                <option key={item} value={item}>
                  {AUTOMATION_STATUS_LABELS[item]}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => void loadList()}
            disabled={working}
            className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:opacity-60"
          >
            Actualizar listado
          </button>
        </div>

        <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
          {busy === "create"
            ? "Creando automatización…"
            : busy === "version"
              ? "Guardando versión…"
              : busy?.startsWith("status")
                ? "Actualizando estado…"
                : busy === "execution:test"
                  ? "Registrando prueba…"
                  : busy === "execution:live"
                    ? "Encolando ejecución…"
                    : listLoading
                      ? "Cargando automatizaciones…"
                      : detailLoading
                        ? "Cargando detalle y ejecuciones…"
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
              Revisar y reintentar
            </button>
          </section>
        ) : null}

        {list && list.items.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {list.items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  disabled={working}
                  onClick={() => void openAutomation(item.id)}
                  aria-current={item.id === detail?.id ? "true" : undefined}
                  aria-label={`Abrir ${item.name} versión ${item.current_version}`}
                  className="rounded-sm border border-border bg-surface px-3 py-1 text-sm font-semibold disabled:opacity-60"
                >
                  {item.name} · v{item.current_version} · {AUTOMATION_STATUS_LABELS[item.status]}
                </button>
              </li>
            ))}
          </ul>
        ) : list && !listLoading && !error ? (
          <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
            No hay automatizaciones registradas.
          </p>
        ) : null}

        {list ? (
          <div className="flex flex-wrap items-center gap-3 text-sm text-text-muted">
            <span>{`Página ${currentPage} de ${totalPages} · ${list.total} registros`}</span>
            <button
              type="button"
              disabled={working || offset === 0}
              onClick={() => {
                const next = Math.max(0, offset - PAGE_SIZE);
                setOffset(next);
                void loadList(statusFilter, next);
              }}
              className="rounded-sm border border-border px-3 py-1 font-semibold disabled:opacity-60"
            >
              Página anterior
            </button>
            <button
              type="button"
              disabled={working || offset + PAGE_SIZE >= list.total}
              onClick={() => {
                const next = offset + PAGE_SIZE;
                setOffset(next);
                void loadList(statusFilter, next);
              }}
              className="rounded-sm border border-border px-3 py-1 font-semibold disabled:opacity-60"
            >
              Página siguiente
            </button>
          </div>
        ) : null}
      </div>

      {detail ? (
        <div className="space-y-6">
          <section aria-labelledby="automation-detail-heading" className="space-y-3">
            <h3 id="automation-detail-heading" className="text-base font-semibold">
              {detail.name}
            </h3>
            <dl className="flex flex-wrap gap-x-6 gap-y-1 rounded-sm border border-border p-3 text-sm">
              <div>
                <dt className="text-xs font-semibold text-text-muted">Estado: </dt>
                <dd className="inline">{AUTOMATION_STATUS_LABELS[detail.status]}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Versión: </dt>
                <dd className="inline">{detail.current_version}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Creada UTC: </dt>
                <dd className="inline">{detail.created_at}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Actualizada UTC: </dt>
                <dd className="inline">{detail.updated_at}</dd>
              </div>
            </dl>
            <div className="space-y-1">
              <h4 className="text-sm font-semibold">Configuración de la versión activa</h4>
              <code className="block break-all rounded-sm bg-surface-muted p-3 text-xs">
                {snapshotText(detail)}
              </code>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                disabled={working || detail.status === "active"}
                onClick={() => void patchStatus("active")}
                className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:opacity-60"
              >
                Activar
              </button>
              <button
                type="button"
                disabled={working || detail.status === "inactive"}
                onClick={() => void patchStatus("inactive")}
                className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:opacity-60"
              >
                Desactivar
              </button>
              <button
                type="button"
                disabled={working || detail.status === "archived"}
                onClick={() => void patchStatus("archived")}
                className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:opacity-60"
              >
                Archivar
              </button>
              {detail.status === "archived" ? (
                <p className="text-sm text-text-muted">Archivada es terminal.</p>
              ) : null}
            </div>
          </section>

          <div role="group" aria-label="Modo de edición de la versión" className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-pressed={editorMode === "form"}
              onClick={() => setEditorMode("form")}
              className={editorModeButtonClass(editorMode === "form")}
            >
              Formulario
            </button>
            <button
              type="button"
              aria-pressed={editorMode === "visual"}
              onClick={() => setEditorMode("visual")}
              className={editorModeButtonClass(editorMode === "visual")}
            >
              Editor visual
            </button>
          </div>

          <form onSubmit={(event) => void saveVersion(event)} className="space-y-3">
            <div className="space-y-1">
              <h3 className="text-base font-semibold">Nueva versión</h3>
              <p className="text-sm text-text-muted">
                Disparo, condiciones y acciones cerradas. Cada versión es inmutable.
              </p>
            </div>
            <div className="space-y-1">
              <label htmlFor="automation-trigger" className="block text-sm font-semibold">
                Disparador
              </label>
              <select
                id="automation-trigger"
                value="application.stage_changed"
                onChange={() => undefined}
                className="w-full max-w-md rounded-sm border border-border bg-surface-muted px-2 py-2 text-sm"
              >
                <option value="application.stage_changed">Cambio de etapa de postulación</option>
              </select>
            </div>

            {editorMode === "visual" ? (
              <AutomationNodeEditor
                value={{ trigger: { event_type: "application.stage_changed" }, conditions, actions }}
                onChange={(next) => {
                  setConditions(next.conditions);
                  setActions(next.actions);
                }}
                disabled={working}
              />
            ) : (
              <div className="space-y-2">
            <fieldset disabled={working} className="space-y-2 rounded-sm border border-border p-3">
              <legend className="px-1 text-sm font-semibold">Condiciones</legend>
              <ol className="space-y-3">
                {conditions.map((condition, index) => {
                  const choices = automationConditionValues(condition.field);
                  const isList = condition.operator === "in";
                  const valueKey = isList ? "Valores" : "Valor";
                  return (
                    <li key={index} className="flex flex-wrap items-end gap-3">
                      <div className="space-y-1">
                        <label
                          htmlFor={`automation-condition-field-${index}`}
                          className="block text-sm font-semibold"
                        >
                          Campo {index + 1}
                        </label>
                        <select
                          id={`automation-condition-field-${index}`}
                          value={condition.field}
                          onChange={(event) => {
                            const field = event.target.value as AutomationConditionField;
                            updateCondition(index, {
                              field,
                              operator: condition.operator,
                              value: automationConditionValues(field)[0],
                            });
                          }}
                          className="rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                        >
                          {CONDITION_FIELDS.map((field) => (
                            <option key={field} value={field}>{field}</option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label
                          htmlFor={`automation-condition-operator-${index}`}
                          className="block text-sm font-semibold"
                        >
                          Operador {index + 1}
                        </label>
                        <select
                          id={`automation-condition-operator-${index}`}
                          value={condition.operator}
                          onChange={(event) => {
                            const operator = event.target.value as AutomationConditionOperator;
                            updateCondition(index, {
                              ...condition,
                              operator,
                              value: operator === "in" ? [choices[0]] : choices[0],
                            });
                          }}
                          className="rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                        >
                          {CONDITION_OPERATORS.map((operator) => (
                            <option key={operator} value={operator}>{operator}</option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label
                          htmlFor={`automation-condition-value-${index}`}
                          className="block text-sm font-semibold"
                        >
                          {valueKey} {index + 1}
                        </label>
                        <select
                          id={`automation-condition-value-${index}`}
                          multiple={isList}
                          required
                          value={isList ? (Array.isArray(condition.value) ? condition.value : []) : (
                            typeof condition.value === "string" ? condition.value : ""
                          )}
                          onChange={(event) => {
                            const selected = Array.from(event.target.selectedOptions).map(
                              (option) => option.value,
                            );
                            updateCondition(index, {
                              ...condition,
                              value: isList ? selected : (selected[0] ?? choices[0]),
                            });
                          }}
                          className="min-w-40 rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                        >
                          {choices.map((choice) => (
                            <option key={choice} value={choice}>{choice}</option>
                          ))}
                        </select>
                      </div>
                      <button
                        type="button"
                        onClick={() => setConditions((current) => current.filter((_, i) => i !== index))}
                        disabled={working}
                        className="rounded-sm border border-border px-2 py-2 text-sm font-semibold disabled:opacity-60"
                      >
                        {`Quitar condición ${index + 1}`}
                      </button>
                    </li>
                  );
                })}
              </ol>
              <button
                type="button"
                onClick={() => setConditions((current) => [...current, createAutomationCondition()])}
                disabled={working || conditions.length >= MAX_CONDITIONS}
                className="rounded-sm border border-border px-3 py-1 text-sm font-semibold disabled:opacity-60"
              >
                Agregar condición
              </button>
            </fieldset>

            <fieldset disabled={working} className="space-y-2 rounded-sm border border-border p-3">
              <legend className="px-1 text-sm font-semibold">Acciones</legend>
              <ol className="space-y-3">
                {actions.map((action, index) => (
                  <li key={index} className="flex flex-wrap items-end gap-3">
                    <div className="space-y-1">
                      <label
                        htmlFor={`automation-action-type-${index}`}
                        className="block text-sm font-semibold"
                      >
                        Tipo de acción {index + 1}
                      </label>
                      <select
                        id={`automation-action-type-${index}`}
                        value={action.type}
                        onChange={(event) => {
                          const type = event.target.value as AutomationActionType;
                          updateAction(index, {
                            type,
                            payload: { ...AUTOMATION_EMPTY_ACTION_PAYLOAD },
                          });
                        }}
                        className="rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                      >
                        {ACTION_TYPES.map((type) => (
                          <option key={type} value={type}>{type}</option>
                        ))}
                      </select>
                    </div>
                    {action.type === "propose_stage_change" ? (
                      <div className="space-y-1">
                        <label
                          htmlFor={`automation-action-stage-${index}`}
                          className="block text-sm font-semibold"
                        >
                          Etapa propuesta {index + 1}
                        </label>
                        <select
                          id={`automation-action-stage-${index}`}
                          value={action.payload.target_stage ?? ""}
                          onChange={(event) =>
                            updateAction(index, {
                              ...action,
                              payload: {
                                ...action.payload,
                                target_stage: event.target.value as ApplicationStage,
                              },
                            })
                          }
                          required
                          className="rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                        >
                          <option value="">Selecciona etapa</option>
                          {STAGE_VALUES.map((stage) => (
                            <option key={stage} value={stage}>{stage}</option>
                          ))}
                        </select>
                      </div>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setActions((current) => current.filter((_, i) => i !== index))}
                      disabled={working}
                      className="rounded-sm border border-border px-2 py-2 text-sm font-semibold disabled:opacity-60"
                    >
                      {`Quitar acción ${index + 1}`}
                    </button>
                  </li>
                ))}
              </ol>
              <button
                type="button"
                onClick={() => setActions((current) => [...current, createAutomationAction()])}
                disabled={working || actions.length >= MAX_ACTIONS}
                className="rounded-sm border border-border px-3 py-1 text-sm font-semibold disabled:opacity-60"
              >
                Agregar acción
              </button>
            </fieldset>
              </div>
            )}

            <button
              type="submit"
              disabled={working}
              className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-on-accent disabled:opacity-60"
            >
              {busy === "version" ? "Guardando versión…" : "Guardar versión"}
            </button>
          </form>

          <section aria-labelledby="automation-execution-heading" className="space-y-3">
            <h3 id="automation-execution-heading" className="text-base font-semibold">
              Probar y ejecutar
            </h3>
            <p className="text-sm text-text-muted">
              La prueba no produce efectos externos. La ejecución real se encola; un 503 implica
              que no se creó ninguna ejecución.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-64 flex-1 space-y-1">
                <label htmlFor="automation-execution-application" className="block text-sm font-semibold">
                  ID de postulación
                </label>
                <input
                  id="automation-execution-application"
                  value={applicationId}
                  onChange={(event) => setApplicationId(event.target.value)}
                  placeholder="00000000-0000-4000-8000-000000000000"
                  className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                />
              </div>
              <div className="min-w-48 flex-1 space-y-1">
                <label htmlFor="automation-execution-key" className="block text-sm font-semibold">
                  Clave de idempotencia
                </label>
                <input
                  id="automation-execution-key"
                  value={idempotencyKey}
                  onChange={(event) => setIdempotencyKey(event.target.value)}
                  maxLength={100}
                  className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                />
              </div>
              <button
                type="button"
                disabled={working}
                onClick={() => void execute("test")}
                className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:opacity-60"
              >
                {busy === "execution:test" ? "Probando…" : "Test (dry-run)"}
              </button>
              <button
                type="button"
                disabled={working}
                onClick={() => void execute("live")}
                className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-on-accent disabled:opacity-60"
              >
                {busy === "execution:live" ? "Encolando…" : "Run (live)"}
              </button>
            </div>

            {execution ? (
              <dl className="flex flex-wrap gap-x-6 gap-y-1 rounded-sm border border-border p-3 text-sm">
                <div>
                  <dt className="text-xs font-semibold text-text-muted">Modo: </dt>
                  <dd className="inline">{execution.kind === "test" ? "Prueba" : "Real"}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">Status: </dt>
                  <dd className="inline">{RUN_STATUS_LABELS[execution.status]}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">Versión: </dt>
                  <dd className="inline">{detail.current_version}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">Correlation ID: </dt>
                  <dd className="inline">{execution.correlationId}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">Queued: </dt>
                  <dd className="inline">
                    {execution.queued === null ? "no aplica (dry-run)" : execution.queued ? "sí" : "no"}
                  </dd>
                </div>
              </dl>
            ) : null}

            <AutomationRunTimeline
              runs={runs}
              events={events}
              selectedRunId={selectedRunId}
              loading={traceLoading}
              onSelectRun={(runId) => void loadRunTrace(runId)}
            />
            <AutomationApprovalControls
              runId={selectedRunId}
              approvals={approvals}
              onRunChange={(run) => {
                setSelectedRun(run);
                setRuns((current) =>
                  current.map((item) => (item.id === run.id ? { ...item, ...run } : item)),
                );
              }}
              onRefresh={() => loadRunTrace(selectedRunId)}
            />
          </section>
        </div>
      ) : null}
    </section>
  );
}
