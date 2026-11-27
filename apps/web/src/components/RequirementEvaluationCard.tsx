"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  AssessmentEvidenceRef,
  RequirementEvaluation,
  RequirementEvaluationStatus,
  ReviewDecision,
} from "../lib/types";
import { Button, buttonVariants } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";
import { Textarea } from "./ui/shadcn/textarea";

const STATUS_KEYS: Record<RequirementEvaluationStatus, MessageKey> = {
  supported: "evaluation.status.supported",
  partial: "evaluation.status.partial",
  not_found: "evaluation.status.not_found",
  needs_review: "evaluation.status.needs_review",
};

const STATUS_MARKS: Record<RequirementEvaluationStatus, string> = {
  supported: "✓",
  partial: "◐",
  not_found: "∅",
  needs_review: "!",
};

const STATUS_OPTIONS: RequirementEvaluationStatus[] = [
  "supported",
  "partial",
  "not_found",
  "needs_review",
];

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

function truncateQuote(quote: string, limit = 160): string {
  return quote.length > limit ? `${quote.slice(0, limit)}…` : quote;
}

function Evidence({ item }: { item: AssessmentEvidenceRef }) {
  const { t } = useI18n();
  return (
    <li>
      <Card className="bg-secondary p-2">
        <p className="text-xs text-text-muted">
          {t("evaluation.document")} {item.document_id} · {t("evaluation.field")}{" "}
          {item.field_name} · {t("evaluation.page")} {item.page}
        </p>
        <blockquote
          title={item.quote}
          className="mt-1 border-l-2 border-border pl-2 text-sm text-text"
        >
          «{truncateQuote(item.quote)}»
        </blockquote>
      </Card>
    </li>
  );
}

interface RequirementEvaluationCardProps {
  assessmentId: string;
  evaluation: RequirementEvaluation;
  onReviewed?: (updated: RequirementEvaluation) => void;
}

export function RequirementEvaluationCard({
  assessmentId,
  evaluation,
  onReviewed,
}: RequirementEvaluationCardProps) {
  const { t } = useI18n();
  const [status, setStatus] = useState<RequirementEvaluationStatus>(evaluation.status);
  const [explanation, setExplanation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saved, setSaved] = useState<RequirementEvaluation | null>(null);

  const current = saved ?? evaluation;
  const statusId = `review-status-${evaluation.id}`;
  const explanationId = `review-explanation-${evaluation.id}`;
  const evidenceId = `review-evidence-${evaluation.id}`;

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError(null);
    setMessage(null);
    const payload: ReviewDecision = {
      status,
      explanation: explanation.trim() || null,
    };

    try {
      const updated = await apiFetch<RequirementEvaluation>(
        `/api/v1/assessment/${encodeURIComponent(assessmentId)}/evaluations/${encodeURIComponent(evaluation.id)}/review`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      setSaved(updated);
      setMessage(`${t("evaluation.saved")} ${t(STATUS_KEYS[updated.status])}.`);
      onReviewed?.(updated);
    } catch (cause) {
      setError(describeError(cause, t("evaluation.error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      role="article"
      aria-labelledby={`evaluation-${evaluation.id}`}
      className="space-y-3 p-3"
    >
      <div className="space-y-1">
        <h4 id={`evaluation-${evaluation.id}`} className="text-sm font-semibold">
          {t("evaluation.statusLabel")}{" "}
          <span
            data-status={current.status}
            className={buttonVariants({
              variant: "outline",
              className: "h-auto gap-1 px-2 py-0.5 text-xs",
            })}
          >
            <span aria-hidden="true">{STATUS_MARKS[current.status]}</span>
            {t(STATUS_KEYS[current.status])}
          </span>
        </h4>
        <p className="break-words text-xs text-text-muted">
          {t("evaluation.requirement")} {current.requirement_id}
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <p className="text-sm">{current.explanation}</p>
          {current.limitations.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-text-muted">
              {current.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          ) : null}
          {current.review_required ? (
            <p className="text-xs text-text">{t("evaluation.reviewRequired")}</p>
          ) : null}
          {current.reviewed_by || current.reviewed_at ? (
            <p className="text-xs text-text-muted">
              {t("evaluation.reviewedBy")} {current.reviewed_by ?? "—"}
              {current.reviewed_at
                ? ` ${t("evaluation.reviewedAt")} ${current.reviewed_at}`
                : ""}
            </p>
          ) : (
            <p className="text-xs text-text-muted">{t("evaluation.noReview")}</p>
          )}
        </div>

        <div className="space-y-2">
          <h5 id={evidenceId} className="text-xs font-semibold text-text-muted">
            {t("evaluation.evidenceTitle")}
          </h5>
          {current.evidence.length > 0 ? (
            <ul aria-labelledby={evidenceId} className="space-y-2">
              {current.evidence.map((item, index) => (
                <Evidence
                  key={`${item.document_id}-${item.page}-${item.field_name}-${index}`}
                  item={item}
                />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-text-muted">
              {t("evaluation.noEvidence")}
            </p>
          )}
        </div>
      </div>

      <form onSubmit={(event) => void submitReview(event)} className="space-y-2">
        <Label htmlFor={statusId} className="block text-xs">
          {t("evaluation.correctedStatus")}
        </Label>
        <Select
          id={statusId}
          value={status}
          onChange={(event) =>
            setStatus(event.target.value as RequirementEvaluationStatus)
          }
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {t(STATUS_KEYS[option])}
            </option>
          ))}
        </Select>
        <Label htmlFor={explanationId} className="block text-xs">
          {t("evaluation.explanation")}
        </Label>
        <Textarea
          id={explanationId}
          value={explanation}
          onChange={(event) => setExplanation(event.target.value)}
          rows={2}
        />
        <Button type="submit" size="sm" disabled={busy}>
          {busy ? t("evaluation.saving") : t("evaluation.correct")}
        </Button>
      </form>

      <p aria-live="polite" className="min-h-5 text-xs text-text-muted">
        {error ? (
          <span role="alert" className="text-text">
            {error}
          </span>
        ) : (
          message
        )}
      </p>
    </Card>
  );
}
