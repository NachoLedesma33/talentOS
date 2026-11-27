"use client";

import { useI18n } from "../lib/i18n";
import type { AgentEvent } from "../lib/types";
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

/** Espejo de la lista pública del backend; el filtro local es defensa en profundidad. */
const PUBLIC_PAYLOAD_KEYS = new Set([
  "action_type",
  "agent_run_id",
  "attempts",
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
  "statuses_summary",
  "template",
  "char_count",
  "tool",
  "version",
  "workflow",
]);

const DETAIL_KEYS = ["node", "duration_ms", "attempts", "error_type"] as const;

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
  const { t } = useI18n();
  return (
    <section aria-labelledby="agent-events-heading" aria-busy={loading} className="space-y-2">
      <div className="space-y-1">
        <h3 id="agent-events-heading" className="text-base font-semibold">
          {t("agentEvent.title")}
        </h3>
        <p aria-live="polite" className="text-sm text-text-muted">
          {loading
            ? t("agentEvent.loading")
            : `${events.length} ${t(events.length === 1 ? "runTimeline.eventSingular" : "runTimeline.eventPlural")} ${t(events.length === 1 ? "runTimeline.registeredSingular" : "runTimeline.registeredPlural")}.`}
        </p>
      </div>

      {!loading && events.length === 0 ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          {t("runTimeline.eventsEmpty")}
        </Card>
      ) : (
        <Table className="rounded-md border border-border">
          <TableCaption className="sr-only">{t("agentEvent.caption")}</TableCaption>
          <TableHeader className="bg-surface-muted text-xs uppercase tracking-wide text-text-muted">
            <TableRow>
              <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.type")}</TableHead>
              <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.dateUtc")}</TableHead>
              <TableHead scope="col" className="px-3 py-2 font-semibold">{t("runTimeline.column.correlation")}</TableHead>
              <TableHead scope="col" className="px-3 py-2 font-semibold">{t("agentEvent.detailColumn")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.map((event, index) => {
              const payload = safePayload(event.payload ?? {});
              const extra = Object.entries(payload).filter(
                ([key]) => !DETAIL_KEYS.includes(key as (typeof DETAIL_KEYS)[number]),
              );
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
                      <span className="text-xs text-text-muted">
                        {t("runTimeline.noMetadata")}
                      </span>
                    ) : null}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
