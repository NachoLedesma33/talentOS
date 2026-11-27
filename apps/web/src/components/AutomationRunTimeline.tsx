"use client";

import { useI18n, type MessageKey } from "../lib/i18n";
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

type Translate = (key: MessageKey) => string;

const RUN_STATUS_KEYS: Record<AutomationRunStatus, MessageKey> = {
  pending: "runTimeline.status.pending",
  running: "runTimeline.status.running",
  waiting_approval: "runTimeline.status.waiting_approval",
  completed: "runTimeline.status.completed",
  failed: "runTimeline.status.failed",
  cancelled: "runTimeline.status.cancelled",
  timed_out: "runTimeline.status.timed_out",
};

const RUN_MODE_KEYS: Record<AutomationRunMode, MessageKey> = {
  test: "runTimeline.mode.test",
  live: "runTimeline.mode.live",
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

function compact(value: unknown, t: Translate): string {
  const text = typeof value === "string" ? value : (JSON.stringify(value) ?? "");
  if (SENSITIVE_VALUE.test(text)) return t("runTimeline.redacted");
  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

function safePayload(payload: Record<string, unknown>, t: Translate): Record<string, string> {
  const result: Record<string, string> = {};
  for (const key of PUBLIC_PAYLOAD_KEYS) {
    if (
      Object.prototype.hasOwnProperty.call(payload, key) &&
      payload[key] !== null &&
      payload[key] !== undefined
    ) {
      result[key] = compact(payload[key], t);
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
  const { t } = useI18n();
  return (
    <section aria-labelledby="automation-timeline-heading" aria-busy={loading} className="space-y-4">
      <div className="space-y-1">
        <h3 id="automation-timeline-heading" className="text-base font-semibold">
          {t("runTimeline.title")}
        </h3>
        <p aria-live="polite" className="text-sm text-text-muted">
          {loading
            ? t("runTimeline.loading")
            : `${runs.length} ${t(runs.length === 1 ? "runTimeline.runSingular" : "runTimeline.runPlural")} · ${events.length} ${t(events.length === 1 ? "runTimeline.eventSingular" : "runTimeline.eventPlural")} ${t(events.length === 1 ? "runTimeline.registeredSingular" : "runTimeline.registeredPlural")}.`}
        </p>
      </div>

      {error ? (
        <Card role="alert" className="p-3 text-sm">
          {error}
        </Card>
      ) : null}

      <div className="space-y-2">
        <h4 className="text-sm font-semibold">{t("runTimeline.runsTitle")}</h4>
        {!loading && runs.length === 0 && !error ? (
          <Card className="bg-secondary p-3 text-sm text-text-muted">
            {t("runTimeline.runsEmpty")}
          </Card>
        ) : (
          <Table className="border border-border text-left">
            <TableCaption className="sr-only">{t("runTimeline.runsCaption")}</TableCaption>
            <TableHeader className="bg-surface-muted text-xs uppercase tracking-wide text-text-muted">
              <TableRow>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.run")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.mode")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.status")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.error")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.createdUtc")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.duration")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.correlation")}</TableHead>
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
                          aria-label={`${t("runTimeline.viewRun")}${run.id}`}
                        >
                          {run.id} · v{run.version}
                        </Button>
                      ) : (
                        <span>{run.id} · v{run.version}</span>
                      )}
                    </TableCell>
                    <TableCell className="px-3 py-2">{t(RUN_MODE_KEYS[run.mode])}</TableCell>
                    <TableCell className="px-3 py-2">{t(RUN_STATUS_KEYS[run.status])}</TableCell>
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
        <h4 className="text-sm font-semibold">{t("runTimeline.eventsTitle")}</h4>
        {!loading && events.length === 0 && !error ? (
          <Card className="bg-secondary p-3 text-sm text-text-muted">
            {t("runTimeline.eventsEmpty")}
          </Card>
        ) : (
          <Table className="border border-border text-left">
            <TableCaption className="sr-only">{t("runTimeline.eventsCaption")}</TableCaption>
            <TableHeader className="bg-surface-muted text-xs uppercase tracking-wide text-text-muted">
              <TableRow>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.type")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.dateUtc")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.correlation")}</TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.safePayload")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((event, index) => {
                const payload = safePayload(event.payload ?? {}, t);
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
                        <span className="text-xs text-text-muted">
                          {t("runTimeline.noMetadata")}
                        </span>
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
