"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  AssessmentComparison as AssessmentComparisonDto,
  AssessmentEvidenceRef,
  AssessmentStatus,
  RequirementEvaluationStatus,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/shadcn/table";

const STATUS_KEYS: Record<RequirementEvaluationStatus, MessageKey> = {
  supported: "evaluation.status.supported",
  partial: "evaluation.status.partial",
  not_found: "evaluation.status.not_found",
  needs_review: "evaluation.status.needs_review",
};

const ASSESSMENT_STATUS_KEYS: Record<AssessmentStatus, MessageKey> = {
  pending: "assessment.status.pending",
  completed: "assessment.status.completed",
  failed: "assessment.status.failed",
  needs_review: "assessment.status.needs_review",
};

type Translate = (key: MessageKey) => string;

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

function statusLabel(status: RequirementEvaluationStatus | null, t: Translate): string {
  return status ? t(STATUS_KEYS[status]) : "—";
}

function optionalText(value: string | null): string {
  return value && value.length > 0 ? value : "—";
}

function truncate(text: string, limit = 120): string {
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function evidenceText(refs: AssessmentEvidenceRef[], t: Translate): string {
  if (refs.length === 0) return t("evaluation.noEvidence");
  return refs
    .map((item) =>
      `${item.document_id} · ${item.field_name} · p.${item.page} · «${truncate(item.quote, 80)}»`,
    )
    .join("; ");
}

export function AssessmentComparison() {
  const { t } = useI18n();
  const [baseId, setBaseId] = useState("");
  const [otherId, setOtherId] = useState("");
  const [comparison, setComparison] = useState<AssessmentComparisonDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const base = baseId.trim();
    const other = otherId.trim();
    if (!base || !other || loading) return;

    setLoading(true);
    setError(null);
    setComparison(null);
    try {
      const result = await apiFetch<AssessmentComparisonDto>(
        `/api/v1/assessment/${encodeURIComponent(base)}/compare?other_id=${encodeURIComponent(other)}`,
      );
      setComparison(result);
    } catch (cause) {
      setError(describeError(cause, t("comparison.error")));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="comparison-heading" aria-busy={loading} className="space-y-3">
      <div className="space-y-1">
        <h2 id="comparison-heading" className="text-lg font-semibold">
          {t("comparison.title")}
        </h2>
        <p className="text-sm text-text-muted">{t("comparison.note")}</p>
      </div>

      <form onSubmit={(event) => void compare(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-1">
          <Label htmlFor="comparison-base-id" className="block">
            {t("comparison.base")}
          </Label>
          <Input
            id="comparison-base-id"
            value={baseId}
            onChange={(event) => setBaseId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
          />
        </div>
        <div className="min-w-56 flex-1 space-y-1">
          <Label htmlFor="comparison-other-id" className="block">
            {t("comparison.other")}
          </Label>
          <Input
            id="comparison-other-id"
            value={otherId}
            onChange={(event) => setOtherId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
          />
        </div>
        <Button type="submit" disabled={loading}>
          {loading ? t("comparison.comparing") : t("comparison.title")}
        </Button>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {loading ? t("comparison.comparingLong") : null}
      </p>
      {error ? (
        <Card role="alert" className="p-3 text-sm">
          {error}
        </Card>
      ) : null}
      {!comparison && !error && !loading ? (
        <p className="text-sm text-text-muted">
          {t("comparison.empty")}
        </p>
      ) : null}

      {comparison ? (
        <div className="space-y-3">
          <dl className="grid gap-2 text-xs text-text-muted md:grid-cols-2">
            <Card className="p-2">
              <dt className="font-semibold text-text">{t("comparison.base")}</dt>
              <dd>
                {comparison.base.assessment_id} · {t(ASSESSMENT_STATUS_KEYS[comparison.base.status])}
              </dd>
              <dd>{t("comparison.model")} {comparison.base.model_version}</dd>
              <dd>{t("comparison.prompt")} {comparison.base.prompt_version}</dd>
            </Card>
            <Card className="p-2">
              <dt className="font-semibold text-text">{t("comparison.compared")}</dt>
              <dd>
                {comparison.target.assessment_id} · {t(ASSESSMENT_STATUS_KEYS[comparison.target.status])}
              </dd>
              <dd>{t("comparison.model")} {comparison.target.model_version}</dd>
              <dd>{t("comparison.prompt")} {comparison.target.prompt_version}</dd>
            </Card>
          </dl>

          <Table>
            <TableCaption className="pb-2 text-left text-xs text-text-muted">
              {t("comparison.caption")}
            </TableCaption>
            <TableHeader>
              <TableRow className="border-y border-border text-xs uppercase text-text-muted">
                <TableHead scope="col" className="px-2 py-2">{t("comparison.col.requirement")}</TableHead>
                <TableHead scope="col" className="px-2 py-2">{t("comparison.col.status")}</TableHead>
                <TableHead scope="col" className="px-2 py-2">{t("comparison.col.explanation")}</TableHead>
                <TableHead scope="col" className="px-2 py-2">{t("comparison.col.evidence")}</TableHead>
                <TableHead scope="col" className="px-2 py-2">{t("comparison.col.review")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {comparison.changes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="px-2 py-3 text-sm text-text-muted">
                    {t("comparison.noChanges")}
                  </TableCell>
                </TableRow>
              ) : (
                comparison.changes.map((change) => (
                  <TableRow key={change.requirement_id} className="border-b border-border align-top">
                    <TableHead scope="row" className="px-2 py-2 text-xs font-semibold">
                      {change.requirement_id}
                    </TableHead>
                    <TableCell className="px-2 py-2">
                      <p>{t("comparison.before")} {statusLabel(change.status.before, t)}</p>
                      <p>{t("comparison.after")} {statusLabel(change.status.after, t)}</p>
                      <p className="text-xs text-text-muted">
                        {change.status.changed
                          ? t("comparison.statusChanged")
                          : t("comparison.unchanged")}
                      </p>
                    </TableCell>
                    <TableCell className="px-2 py-2">
                      <p>{t("comparison.before")} {optionalText(change.explanation.before)}</p>
                      <p>{t("comparison.after")} {optionalText(change.explanation.after)}</p>
                      <p className="text-xs text-text-muted">
                        {change.explanation.changed
                          ? t("comparison.explanationChanged")
                          : t("comparison.unchanged")}
                      </p>
                    </TableCell>
                    <TableCell className="px-2 py-2">
                      <p>{t("comparison.before")} {evidenceText(change.evidence_refs.before, t)}</p>
                      <p>{t("comparison.after")} {evidenceText(change.evidence_refs.after, t)}</p>
                      <p className="text-xs text-text-muted">
                        {change.evidence_refs.changed
                          ? t("comparison.evidenceChanged")
                          : t("comparison.unchanged")}
                      </p>
                    </TableCell>
                    <TableCell className="px-2 py-2 text-xs">
                      {t("comparison.before")}{" "}
                      {change.review_required.before ? t("comparison.yes") : t("comparison.no")}
                      <br />
                      {t("comparison.after")}{" "}
                      {change.review_required.after ? t("comparison.yes") : t("comparison.no")}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </section>
  );
}
