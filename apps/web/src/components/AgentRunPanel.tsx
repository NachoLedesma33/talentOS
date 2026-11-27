"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
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

const STATUS_KEYS: Record<AgentRunStatus, MessageKey> = {
  pending: "runTimeline.status.pending",
  running: "runTimeline.status.running",
  waiting_approval: "runTimeline.status.waiting_approval",
  completed: "runTimeline.status.completed",
  failed: "runTimeline.status.failed",
  cancelled: "runTimeline.status.cancelled",
  timed_out: "runTimeline.status.timed_out",
};

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
}

function formatUtc(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

export function AgentRunPanel() {
  const { t } = useI18n();
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
      setError(describeError(cause, t("agentRun.error")));
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
      setError(describeError(cause, t("agentRun.error")));
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
      setNotice(t("agentRun.loaded"));
      setLoadingDetail(true);
      await loadRun(created.id);
    } catch (cause) {
      setError(describeError(cause, t("agentRun.error")));
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
          {t("agentRun.title")}
        </h2>
        <p className="text-sm text-text-muted">{t("agentRun.note")}</p>
      </div>

      <form onSubmit={(event) => void start(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1 space-y-1">
          <Label htmlFor="agent-application-id" className="block">
            {t("agentRun.applicationId")}
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
            {t("agentRun.idempotencyKey")}
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
          {submitting ? t("agentRun.starting") : t("agentRun.start")}
        </Button>
      </form>

      <form onSubmit={(event) => void listRuns(event)} className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <Label htmlFor="agent-list-status" className="block">
            {t("agentRun.statusFilter")}
          </Label>
          <Select
            id="agent-list-status"
            value={listStatus}
            onChange={(event) => setListStatus(event.target.value as AgentRunStatus | "")}
          >
            <option value="">{t("agentRun.all")}</option>
            {Object.entries(STATUS_KEYS).map(([value, key]) => (
              <option key={value} value={value}>
                {t(key)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="agent-list-agent" className="block">
            {t("agentRun.agentFilter")}
          </Label>
          <Input
            id="agent-list-agent"
            value={listAgent}
            onChange={(event) => setListAgent(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="agent-list-date-from" className="block">
            {t("agentRun.from")}
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
            {t("agentRun.to")}
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
            {t("agentRun.jobFilter")}
          </Label>
          <Input
            id="agent-list-job"
            value={listJobId}
            onChange={(event) => setListJobId(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="agent-list-candidate" className="block">
            {t("agentRun.candidateFilter")}
          </Label>
          <Input
            id="agent-list-candidate"
            value={listCandidateId}
            onChange={(event) => setListCandidateId(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={listing} className="self-end">
          {listing ? t("agentRun.searching") : t("agentRun.search")}
        </Button>
      </form>

      {runs.length > 0 ? (
        <div className="overflow-x-auto">
          <Table className="text-left">
            <TableCaption className="sr-only">{t("agentRun.runsCaption")}</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">{t("agentRun.column.run")}</TableHead>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">{t("agentRun.column.agent")}</TableHead>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">{t("agentRun.column.status")}</TableHead>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">{t("agentRun.column.job")}</TableHead>
                <TableHead scope="col" className="py-2 pr-3 font-semibold">{t("agentRun.column.candidate")}</TableHead>
                <TableHead scope="col" className="py-2 font-semibold">{t("agentRun.column.created")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="py-2 pr-3">
                    <Button
                      type="button"
                      variant="link"
                      className="h-auto p-0 text-accent hover:opacity-80"
                      onClick={() => void selectRun(item.id)}
                    >
                      {item.id}
                    </Button>
                  </TableCell>
                  <TableCell className="py-2 pr-3">{item.workflow}</TableCell>
                  <TableCell className="py-2 pr-3">{t(STATUS_KEYS[item.status])}</TableCell>
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
          ? t("agentRun.startingLong")
          : loadingDetail
            ? t("agentRun.loadingDetail")
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
            {t("agentRun.retry")}
          </Button>
        </Card>
      ) : null}

      {!run && !error && !submitting && !loadingDetail ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          {t("agentRun.prompt")}
        </Card>
      ) : null}

      {run ? (
        <div className="space-y-5">
          <section aria-labelledby="agent-run-detail-heading" className="space-y-2">
            <h3 id="agent-run-detail-heading" className="text-base font-semibold">
              {t("agentRun.detailTitle")}
            </h3>
            <Card className="p-3 text-sm">
              <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.workflowLabel")}</dt>
                <dd className="inline">{run.workflow}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.versionLabel")}</dt>
                <dd className="inline">{run.version}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.statusLabel")}</dt>
                <dd className="inline">{t(STATUS_KEYS[run.status])}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.correlationLabel")}</dt>
                <dd className="inline">{run.correlation_id}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.durationLabel")}</dt>
                <dd className="inline">{run.duration_ms ?? 0} ms</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.providerLabel")}</dt>
                <dd className="inline">{run.configured_provider ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.modelLabel")}</dt>
                <dd className="inline">{run.configured_model ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.jobLabel")}</dt>
                <dd className="inline">{run.job_id ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("agentRun.candidateLabel")}</dt>
                <dd className="inline">{run.candidate_id ?? "—"}</dd>
              </div>
              {run.output_ref ? (
                <div>
                  <dt className="text-xs font-semibold text-text-muted">{t("agentRun.outputRefLabel")}</dt>
                  <dd className="inline">{run.output_ref}</dd>
                </div>
              ) : null}
              </dl>
            </Card>
            {reviewRequired ? (
              <Card role="status" className="px-3 py-2 text-sm">
                {t("agentRun.reviewRequired")}
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
