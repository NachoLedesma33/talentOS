"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
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
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";

const PAGE_SIZE = 20;

const AUTOMATION_STATUS_LABEL_KEYS: Record<AutomationStatus, MessageKey> = {
  draft: "automations.status.draft",
  active: "automations.status.active",
  inactive: "automations.status.inactive",
  archived: "automations.status.archived",
};

const RUN_STATUS_LABEL_KEYS: Record<AutomationRunStatus, MessageKey> = {
  pending: "runTimeline.status.pending",
  running: "runTimeline.status.running",
  waiting_approval: "runTimeline.status.waiting_approval",
  completed: "runTimeline.status.completed",
  failed: "runTimeline.status.failed",
  cancelled: "runTimeline.status.cancelled",
  timed_out: "runTimeline.status.timed_out",
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

function describeError(
  cause: unknown,
  fallback: string,
  t: (key: MessageKey) => string,
): string {
  if (cause instanceof ApiError) {
    if (cause.code === "broker_unavailable" || cause.status === 503) {
      return t("approval.brokerError");
    }
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
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
function snapshotText(detail: AutomationDetail, noVersion: string): string {
  const version = detail.active_version;
  if (!version) return noVersion;
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
  const { t } = useI18n();
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
      setError(describeError(cause, t("automations.errorList"), t));
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
      setError(describeError(cause, t("automations.errorTrace"), t));
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
      setError(describeError(cause, t("automations.errorLoad"), t));
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
        if (active) setError(describeError(cause, t("automations.errorList"), t));
      },
    ).finally(() => {
      if (active) setListLoading(false);
    });
    return () => {
      active = false;
    };
  }, [t]);

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
      setNotice(t("automations.created"));
      await loadList();
      await openAutomation(created.id);
    } catch (cause) {
      setError(describeError(cause, t("automations.errorCreate"), t));
    } finally {
      setBusy(null);
    }
  }

  async function saveVersion(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!detail || working) return;
    if (actions.length === 0) {
      setError(t("automations.requireAction"));
      return;
    }
    if (
      actions.some(
        (action) => action.type === "propose_stage_change" && !action.payload.target_stage,
      )
    ) {
      setError(t("automations.requireStage"));
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
      setNotice(t("automations.versionCreated"));
      await loadList();
      await openAutomation(detail.id);
    } catch (cause) {
      setError(describeError(cause, t("automations.errorVersion"), t));
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
      setNotice(`${t("automations.statusUpdated")}${t(AUTOMATION_STATUS_LABEL_KEYS[status])}.`);
      await loadList();
      await openAutomation(detail.id);
    } catch (cause) {
      setError(describeError(cause, t("automations.errorStatus"), t));
    } finally {
      setBusy(null);
    }
  }

  async function execute(mode: AutomationRunMode): Promise<void> {
    if (!detail || working) return;
    const application = applicationId.trim();
    const key = idempotencyKey.trim();
    if (!application || !key) {
      setError(t("automations.requireExecution"));
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
        setNotice(t("automations.testRecorded"));
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
          result.queued ? t("automations.runQueued") : t("automations.runDuplicate"),
        );
        await loadRuns(detail.id);
        await loadRunTrace(result.id);
      }
    } catch (cause) {
      setError(describeError(cause, t("automations.errorExecute"), t));
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
          {t("automations.title")}
        </h2>
        <p className="text-sm text-text-muted">{t("automations.intro")}</p>
      </div>

      <form onSubmit={(event) => void createAutomation(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1 space-y-1">
          <Label htmlFor="automation-name" className="block">
            {t("automations.nameLabel")}
          </Label>
          <Input
            id="automation-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={200}
            placeholder={t("automations.namePlaceholder")}
            className="w-full"
          />
        </div>
        <Button
          type="submit"
          disabled={working}
          variant="default"
        >
          {busy === "create" ? t("automations.creatingButton") : t("automations.create")}
        </Button>
      </form>

      <div className="space-y-2">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="automation-status-filter" className="block">
              {t("automations.filterStatus")}
            </Label>
            <Select
              id="automation-status-filter"
              value={statusFilter}
              onChange={(event) => {
                const next = event.target.value as AutomationStatus | "all";
                setStatusFilter(next);
                setOffset(0);
                void loadList(next, 0);
              }}
              disabled={working}
              className="w-full"
            >
              <option value="all">{t("integrations.filterAll")}</option>
              {ALL_STATUSES.filter((item) => item !== "all").map((item) => (
                <option key={item} value={item}>
                  {t(AUTOMATION_STATUS_LABEL_KEYS[item])}
                </option>
              ))}
            </Select>
          </div>
          <Button
            type="button"
            onClick={() => void loadList()}
            disabled={working}
            variant="outline"
          >
            {t("automations.refresh")}
          </Button>
        </div>

        <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
          {busy === "create"
            ? t("automations.creating")
            : busy === "version"
              ? t("automations.savingVersion")
              : busy?.startsWith("status")
                ? t("automations.updatingStatus")
                : busy === "execution:test"
                  ? t("automations.testing")
                  : busy === "execution:live"
                    ? t("automations.queuing")
                    : listLoading
                      ? t("automations.loading")
                      : detailLoading
                        ? t("automations.loadingDetail")
                        : notice}
        </p>
        {error ? (
          <Card role="alert" className="space-y-2 p-3">
            <p className="text-sm">{error}</p>
            <Button
              type="button"
              onClick={() => {
                setError(null);
                setNotice(null);
              }}
              variant="outline"
              size="sm"
            >
              {t("automations.reviewRetry")}
            </Button>
          </Card>
        ) : null}

        {list && list.items.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {list.items.map((item) => (
              <li key={item.id}>
                <Button
                  type="button"
                  disabled={working}
                  onClick={() => void openAutomation(item.id)}
                  aria-current={item.id === detail?.id ? "true" : undefined}
                  aria-label={`${t("automations.openAria")}${item.name}${t("automations.openVersionAria")}${item.current_version}`}
                  variant="outline"
                  size="sm"
                  className={item.id === detail?.id ? "bg-secondary" : undefined}
                >
                  {item.name} · v{item.current_version} · {t(AUTOMATION_STATUS_LABEL_KEYS[item.status])}
                </Button>
              </li>
            ))}
          </ul>
        ) : list && !listLoading && !error ? (
          <Card className="bg-secondary p-3 text-sm text-text-muted">
            {t("automations.empty")}
          </Card>
        ) : null}

        {list ? (
          <div className="flex flex-wrap items-center gap-3 text-sm text-text-muted">
            <span>
              {`${t("integrations.page")}${currentPage}${t("integrations.of")}${totalPages} · ${list.total}${t("integrations.records")}`}
            </span>
            <Button
              type="button"
              disabled={working || offset === 0}
              onClick={() => {
                const next = Math.max(0, offset - PAGE_SIZE);
                setOffset(next);
                void loadList(statusFilter, next);
              }}
              variant="outline"
              size="sm"
            >
              {t("integrations.prevPage")}
            </Button>
            <Button
              type="button"
              disabled={working || offset + PAGE_SIZE >= list.total}
              onClick={() => {
                const next = offset + PAGE_SIZE;
                setOffset(next);
                void loadList(statusFilter, next);
              }}
              variant="outline"
              size="sm"
            >
              {t("integrations.nextPage")}
            </Button>
          </div>
        ) : null}
      </div>

      {detail ? (
        <div className="space-y-6">
          <section aria-labelledby="automation-detail-heading" className="space-y-3">
            <h3 id="automation-detail-heading" className="text-base font-semibold">
              {detail.name}
            </h3>
            <Card className="p-3 text-sm">
            <dl className="flex flex-wrap gap-x-6 gap-y-1">
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("automations.detail.status")}</dt>
                <dd className="inline">{t(AUTOMATION_STATUS_LABEL_KEYS[detail.status])}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("automations.detail.version")}</dt>
                <dd className="inline">{detail.current_version}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("automations.detail.created")}</dt>
                <dd className="inline">{detail.created_at}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("automations.detail.updated")}</dt>
                <dd className="inline">{detail.updated_at}</dd>
              </div>
            </dl>
            </Card>
            <div className="space-y-1">
              <h4 className="text-sm font-semibold">{t("automations.activeVersionTitle")}</h4>
              <code className="block break-all bg-secondary p-3 text-xs">
                {snapshotText(detail, t("automations.noActiveVersion"))}
              </code>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button
                type="button"
                disabled={working || detail.status === "active"}
                onClick={() => void patchStatus("active")}
                variant="outline"
              >
                {t("automations.activate")}
              </Button>
              <Button
                type="button"
                disabled={working || detail.status === "inactive"}
                onClick={() => void patchStatus("inactive")}
                variant="outline"
              >
                {t("automations.deactivate")}
              </Button>
              <Button
                type="button"
                disabled={working || detail.status === "archived"}
                onClick={() => void patchStatus("archived")}
                variant="outline"
              >
                {t("automations.archive")}
              </Button>
              {detail.status === "archived" ? (
                <p className="text-sm text-text-muted">{t("automations.archivedTerminal")}</p>
              ) : null}
            </div>
          </section>

          <div role="group" aria-label={t("automations.editorModeAria")} className="flex flex-wrap gap-2">
            <Button
              type="button"
              aria-pressed={editorMode === "form"}
              onClick={() => setEditorMode("form")}
              variant={editorMode === "form" ? "secondary" : "outline"}
              size="sm"
            >
              {t("automations.form")}
            </Button>
            <Button
              type="button"
              aria-pressed={editorMode === "visual"}
              onClick={() => setEditorMode("visual")}
              variant={editorMode === "visual" ? "secondary" : "outline"}
              size="sm"
            >
              {t("automations.visualEditor")}
            </Button>
          </div>

          <form onSubmit={(event) => void saveVersion(event)} className="space-y-3">
            <div className="space-y-1">
              <h3 className="text-base font-semibold">{t("automations.newVersion")}</h3>
              <p className="text-sm text-text-muted">{t("automations.newVersionIntro")}</p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="automation-trigger" className="block">
                {t("automations.trigger")}
              </Label>
              <Select
                id="automation-trigger"
                value="application.stage_changed"
                onChange={() => undefined}
                className="w-full max-w-md bg-secondary"
              >
                <option value="application.stage_changed">{t("automations.triggerOption")}</option>
              </Select>
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
            <Card className="p-3">
            <fieldset disabled={working} className="space-y-2">
              <legend className="px-1 text-sm font-semibold">{t("automations.conditions")}</legend>
              <ol className="space-y-3">
                {conditions.map((condition, index) => {
                  const choices = automationConditionValues(condition.field);
                  const isList = condition.operator === "in";
                  const valueKey = isList
                    ? t("automations.values")
                    : t("automations.value");
                  return (
                    <li key={index} className="flex flex-wrap items-end gap-3">
                      <div className="space-y-1">
                        <Label
                          htmlFor={`automation-condition-field-${index}`}
                          className="block"
                        >
                          {`${t("automations.field")}${index + 1}`}
                        </Label>
                        <Select
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
                          className="w-full"
                        >
                          {CONDITION_FIELDS.map((field) => (
                            <option key={field} value={field}>{field}</option>
                          ))}
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label
                          htmlFor={`automation-condition-operator-${index}`}
                          className="block"
                        >
                          {`${t("automations.operator")}${index + 1}`}
                        </Label>
                        <Select
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
                          className="w-full"
                        >
                          {CONDITION_OPERATORS.map((operator) => (
                            <option key={operator} value={operator}>{operator}</option>
                          ))}
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label
                          htmlFor={`automation-condition-value-${index}`}
                          className="block"
                        >
                          {`${valueKey} ${index + 1}`}
                        </Label>
                        <Select
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
                          className="min-w-40"
                        >
                          {choices.map((choice) => (
                            <option key={choice} value={choice}>{choice}</option>
                          ))}
                        </Select>
                      </div>
                      <Button
                        type="button"
                        onClick={() => setConditions((current) => current.filter((_, i) => i !== index))}
                        disabled={working}
                        variant="outline"
                        size="sm"
                      >
                        {`${t("automations.removeCondition")}${index + 1}`}
                      </Button>
                    </li>
                  );
                })}
              </ol>
              <Button
                type="button"
                onClick={() => setConditions((current) => [...current, createAutomationCondition()])}
                disabled={working || conditions.length >= MAX_CONDITIONS}
                variant="outline"
            size="sm"
              >
                {t("automations.addCondition")}
              </Button>
            </fieldset>
            </Card>

            <Card className="p-3">
            <fieldset disabled={working} className="space-y-2">
              <legend className="px-1 text-sm font-semibold">{t("automations.actions")}</legend>
              <ol className="space-y-3">
                {actions.map((action, index) => (
                  <li key={index} className="flex flex-wrap items-end gap-3">
                    <div className="space-y-1">
                      <Label
                        htmlFor={`automation-action-type-${index}`}
                        className="block"
                      >
                        {`${t("automations.actionType")}${index + 1}`}
                      </Label>
                      <Select
                        id={`automation-action-type-${index}`}
                        value={action.type}
                        onChange={(event) => {
                          const type = event.target.value as AutomationActionType;
                          updateAction(index, {
                            type,
                            payload: { ...AUTOMATION_EMPTY_ACTION_PAYLOAD },
                          });
                        }}
                        className="w-full"
                      >
                        {ACTION_TYPES.map((type) => (
                          <option key={type} value={type}>{type}</option>
                        ))}
                      </Select>
                    </div>
                    {action.type === "propose_stage_change" ? (
                      <div className="space-y-1">
                        <Label
                          htmlFor={`automation-action-stage-${index}`}
                          className="block"
                        >
                          {`${t("automations.proposedStage")}${index + 1}`}
                        </Label>
                        <Select
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
                          className="w-full"
                        >
                          <option value="">{t("automations.selectStage")}</option>
                          {STAGE_VALUES.map((stage) => (
                            <option key={stage} value={stage}>{stage}</option>
                          ))}
                        </Select>
                      </div>
                    ) : null}
                    <Button
                      type="button"
                      onClick={() => setActions((current) => current.filter((_, i) => i !== index))}
                      disabled={working}
                      variant="outline"
                        size="sm"
                    >
                      {`${t("automations.removeAction")}${index + 1}`}
                    </Button>
                  </li>
                ))}
              </ol>
              <Button
                type="button"
                onClick={() => setActions((current) => [...current, createAutomationAction()])}
                disabled={working || actions.length >= MAX_ACTIONS}
                variant="outline"
            size="sm"
              >
                {t("automations.addAction")}
              </Button>
            </fieldset>
            </Card>
              </div>
            )}

            <Button
              type="submit"
              disabled={working}
              variant="default"
            >
              {busy === "version"
                ? t("automations.savingVersion")
                : t("automations.saveVersion")}
            </Button>
          </form>

          <section aria-labelledby="automation-execution-heading" className="space-y-3">
            <h3 id="automation-execution-heading" className="text-base font-semibold">
              {t("automations.executeTitle")}
            </h3>
            <p className="text-sm text-text-muted">{t("automations.executeIntro")}</p>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-64 flex-1 space-y-1">
                <Label htmlFor="automation-execution-application" className="block">
                  {t("agentRun.applicationId")}
                </Label>
                <Input
                  id="automation-execution-application"
                  value={applicationId}
                  onChange={(event) => setApplicationId(event.target.value)}
                  placeholder="00000000-0000-4000-8000-000000000000"
                  className="w-full"
                />
              </div>
              <div className="min-w-48 flex-1 space-y-1">
                <Label htmlFor="automation-execution-key" className="block">
                  {t("agentRun.idempotencyKey")}
                </Label>
                <Input
                  id="automation-execution-key"
                  value={idempotencyKey}
                  onChange={(event) => setIdempotencyKey(event.target.value)}
                  maxLength={100}
                  className="w-full"
                />
              </div>
              <Button
                type="button"
                disabled={working}
                onClick={() => void execute("test")}
                variant="outline"
              >
                {busy === "execution:test"
                  ? t("automations.testingButton")
                  : t("automations.testButton")}
              </Button>
              <Button
                type="button"
                disabled={working}
                onClick={() => void execute("live")}
                variant="default"
              >
                {busy === "execution:live"
                  ? t("automations.queuingButton")
                  : t("automations.runButton")}
              </Button>
            </div>

            {execution ? (
              <Card className="p-3 text-sm">
            <dl className="flex flex-wrap gap-x-6 gap-y-1">
                <div>
                  <dt className="text-xs font-semibold text-text-muted">{t("automations.execution.mode")}</dt>
                  <dd className="inline">
                    {t(execution.kind === "test" ? "runTimeline.mode.test" : "runTimeline.mode.live")}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">{t("automations.execution.status")}</dt>
                  <dd className="inline">{t(RUN_STATUS_LABEL_KEYS[execution.status])}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">{t("automations.execution.version")}</dt>
                  <dd className="inline">{detail.current_version}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">{t("automations.execution.correlation")}</dt>
                  <dd className="inline">{execution.correlationId}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">{t("automations.execution.queued")}</dt>
                  <dd className="inline">
                    {execution.queued === null
                      ? t("automations.execution.na")
                      : execution.queued
                        ? t("automations.yes")
                        : t("automations.no")}
                  </dd>
                </div>
              </dl>
            </Card>
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
