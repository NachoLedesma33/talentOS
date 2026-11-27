"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type { GuideRevision, GuideRevisionList } from "../lib/types";
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

type Translate = (key: MessageKey) => string;

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
}

/** Sólo agregados: nunca se renderiza el snapshot crudo, CV ni secretos. */
function summarizeSnapshot(snapshot: Record<string, unknown>, t: Translate): string {
  const questions = Array.isArray(snapshot.questions) ? snapshot.questions.length : 0;
  const rejected = Array.isArray(snapshot.rejected_questions)
    ? snapshot.rejected_questions.length
    : 0;
  const limitations = Array.isArray(snapshot.limitations) ? snapshot.limitations.length : 0;
  const review =
    snapshot.review_required === true
      ? t("history.required")
      : t("history.notRequired");
  return `${questions} ${t("history.questions")} · ${rejected} ${t("history.rejected")} · ${limitations} ${t("history.limitations")} · ${t("history.review")} ${review}`;
}

export function GuideHistory({ guideId }: { guideId: string }) {
  const { t } = useI18n();
  const [revisions, setRevisions] = useState<GuideRevision[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestRevisions = useCallback(
    () =>
      apiFetch<GuideRevisionList>(
        `/api/v1/interviews/guides/${encodeURIComponent(guideId)}/revisions`,
      ),
    [guideId],
  );

  async function load(): Promise<void> {
    setRefreshing(true);
    setError(null);
    try {
      const result = await requestRevisions();
      setRevisions(result.items);
    } catch (cause) {
      setError(describeError(cause, t("history.error")));
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    requestRevisions().then(
      (result) => {
        if (!active) return;
        setRevisions(result.items);
        setLoading(false);
      },
      (cause: unknown) => {
        if (!active) return;
        setError(describeError(cause, t("history.error")));
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [requestRevisions, t]);

  return (
    <section aria-labelledby={`guide-history-heading-${guideId}`} className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`guide-history-heading-${guideId}`} className="text-base font-semibold">
          {t("history.title")}
        </h3>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={refreshing}
          onClick={() => void load()}
        >
          {refreshing ? t("history.refreshing") : t("history.refresh")}
        </Button>
      </div>
      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {loading ? t("history.loading") : null}
      </p>
      {error ? (
        <Card role="alert" className="p-2 text-sm">
          {error}
        </Card>
      ) : null}

      {!loading && revisions.length === 0 && !error ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          {t("history.empty")}
        </Card>
      ) : revisions.length > 0 ? (
        <Table className="text-left text-xs">
          <TableCaption className="sr-only">{t("history.caption")}</TableCaption>
          <TableHeader>
            <TableRow className="border-b border-border">
              <TableHead scope="col" className="py-1 pr-3 font-semibold">
                {t("history.col.version")}
              </TableHead>
              <TableHead scope="col" className="py-1 pr-3 font-semibold">
                {t("history.col.createdBy")}
              </TableHead>
              <TableHead scope="col" className="py-1 pr-3 font-semibold">
                {t("history.col.date")}
              </TableHead>
              <TableHead scope="col" className="py-1 font-semibold">
                {t("history.col.summary")}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {revisions.map((item) => (
              <TableRow key={item.id} className="border-b border-border align-top">
                <TableCell className="py-1 pr-3">v{item.version}</TableCell>
                <TableCell className="py-1 pr-3">{item.created_by}</TableCell>
                <TableCell className="py-1 pr-3">{item.created_at}</TableCell>
                <TableCell className="py-1">{summarizeSnapshot(item.snapshot, t)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </section>
  );
}
