"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  Assessment,
  AssessmentStatus,
  RequirementEvaluation,
  RunAssessmentRequest,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { RequirementEvaluationCard } from "./RequirementEvaluationCard";

const STATUS_KEYS: Record<AssessmentStatus, MessageKey> = {
  pending: "assessment.status.pending",
  completed: "assessment.status.completed",
  failed: "assessment.status.failed",
  needs_review: "assessment.status.needs_review",
};

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

function List({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold text-text-muted">{title}</h4>
      {items.length > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-text-muted">{empty}</p>
      )}
    </div>
  );
}

export function AssessmentPanel() {
  const { t } = useI18n();
  const [applicationId, setApplicationId] = useState("");
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = applicationId.trim();
    if (!id || loading) return;

    setLoading(true);
    setError(null);
    setNotice(null);
    setAssessment(null);
    try {
      const payload: RunAssessmentRequest = { application_id: id };
      const result = await apiFetch<Assessment>("/api/v1/assessment/run", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const detail = await apiFetch<Assessment>(
        `/api/v1/assessment/${encodeURIComponent(result.id)}`,
      );
      setAssessment(detail);
      setNotice(
        assessment?.id === result.id
          ? t("assessment.recovered")
          : t("assessment.created"),
      );
    } catch (cause) {
      setError(describeError(cause, t("assessment.error")));
    } finally {
      setLoading(false);
    }
  }

  function applyReview(updated: RequirementEvaluation) {
    setAssessment((current) =>
      current
        ? {
            ...current,
            evaluations: current.evaluations.map((item) =>
              item.id === updated.id ? updated : item,
            ),
          }
        : current,
    );
  }

  return (
    <section aria-labelledby="assessment-panel-heading" aria-busy={loading} className="space-y-4">
      <div className="space-y-1">
        <h2 id="assessment-panel-heading" className="text-lg font-semibold">
          {t("assessment.title")}
        </h2>
        <p className="text-sm text-text-muted">{t("assessment.note")}</p>
      </div>

      <form onSubmit={(event) => void run(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1 space-y-1">
          <Label htmlFor="assessment-application-id" className="block">
            {t("assessment.applicationId")}
          </Label>
          <Input
            id="assessment-application-id"
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
          />
        </div>
        <Button type="submit" disabled={loading}>
          {loading ? t("assessment.running") : t("assessment.run")}
        </Button>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {loading ? t("assessment.processing") : notice}
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
            {t("assessment.retry")}
          </Button>
        </Card>
      ) : null}
      {!assessment && !error && !loading ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          {t("assessment.empty")}
        </Card>
      ) : null}

      {assessment ? (
        <div className="space-y-4">
          <section aria-labelledby="assessment-summary-heading" className="space-y-3">
            <h3 id="assessment-summary-heading" className="text-base font-semibold">
              {t("assessment.summary")}
            </h3>
            <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-text-muted">
              <div>
                <dt className="inline font-semibold">{t("assessment.statusLabel")} </dt>
                <dd className="inline">{t(STATUS_KEYS[assessment.status])}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">{t("assessment.model")} </dt>
                <dd className="inline">{assessment.model_version}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">{t("assessment.prompt")} </dt>
                <dd className="inline">{assessment.prompt_version}</dd>
              </div>
            </dl>
            {assessment.review_required ? (
              <Card role="status" className="px-3 py-2 text-sm">
                {t("assessment.reviewRequired")}
              </Card>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2">
              <Card className="space-y-3 p-3">
                <List
                  title={t("assessment.strengths")}
                  items={assessment.summary.strengths}
                  empty={t("assessment.strengthsEmpty")}
                />
                <List
                  title={t("assessment.gaps")}
                  items={assessment.summary.gaps}
                  empty={t("assessment.gapsEmpty")}
                />
              </Card>
              <Card className="space-y-3 p-3">
                <List
                  title={t("assessment.questions")}
                  items={assessment.summary.questions}
                  empty={t("assessment.questionsEmpty")}
                />
                <List
                  title={t("assessment.limitations")}
                  items={assessment.limitations}
                  empty={t("assessment.limitationsEmpty")}
                />
              </Card>
            </div>
          </section>

          <section aria-labelledby="assessment-requirements-heading" className="space-y-2">
            <h3 id="assessment-requirements-heading" className="text-base font-semibold">
              {t("assessment.requirements")}
            </h3>
            {assessment.evaluations.length > 0 ? (
              <ul className="space-y-3">
                {assessment.evaluations.map((evaluation) => (
                  <li
                    key={`${evaluation.id}-${evaluation.status}-${evaluation.reviewed_at ?? "sin-revision"}`}
                  >
                    <RequirementEvaluationCard
                      assessmentId={assessment.id}
                      evaluation={evaluation}
                      onReviewed={applyReview}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-text-muted">
                {t("assessment.noCriteria")}
              </p>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}
