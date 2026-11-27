"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  GenerateGuideRequest,
  GuideGeneration,
  InterviewGuideDetail,
  InterviewGuideList,
  InterviewGuideStatus,
  InterviewGuideSummary,
  InterviewQuestion,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { GuideHistory } from "./GuideHistory";
import { QuestionEditor } from "./QuestionEditor";

const GUIDE_STATUS_KEYS: Record<InterviewGuideStatus, MessageKey> = {
  draft: "guide.status.draft",
  published: "guide.status.published",
  archived: "guide.status.archived",
};

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function InterviewGuidePanel() {
  const { t } = useI18n();
  const [applicationId, setApplicationId] = useState("");
  const [guides, setGuides] = useState<InterviewGuideSummary[] | null>(null);
  const [guide, setGuide] = useState<InterviewGuideDetail | null>(null);
  const [generating, setGenerating] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const busy = generating || detailLoading || publishing;

  async function loadGuides(id: string): Promise<void> {
    const list = await apiFetch<InterviewGuideList>(
      `/api/v1/interviews/guides?application_id=${encodeURIComponent(id)}`,
    );
    setGuides(list.items);
  }

  async function openGuide(id: string, successNotice?: string): Promise<void> {
    setDetailLoading(true);
    try {
      const detail = await apiFetch<InterviewGuideDetail>(
        `/api/v1/interviews/guides/${encodeURIComponent(id)}`,
      );
      setGuide(detail);
      setNotice(successNotice ?? t("guide.loaded"));
    } catch (cause) {
      setGuide(null);
      setError(describeError(cause, t("guide.error.load")));
    } finally {
      setDetailLoading(false);
    }
  }

  async function generate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const id = applicationId.trim();
    if (!id || busy) return;

    setGenerating(true);
    setError(null);
    setNotice(null);
    setGuide(null);
    setGuides(null);
    try {
      const payload: GenerateGuideRequest = { application_id: id };
      const result = await apiFetch<GuideGeneration>("/api/v1/interviews/guides/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await loadGuides(id);
      await openGuide(
        result.guide_id,
        result.created ? t("guide.created") : t("guide.reused"),
      );
    } catch (cause) {
      setError(describeError(cause, t("guide.error.generate")));
    } finally {
      setGenerating(false);
    }
  }

  async function publish(): Promise<void> {
    if (!guide || publishing) return;

    setPublishing(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiFetch<InterviewGuideDetail>(
        `/api/v1/interviews/guides/${encodeURIComponent(guide.id)}`,
        { method: "PATCH", body: JSON.stringify({ status: "published" }) },
      );
      setGuide(updated);
      setGuides((current) =>
        current
          ? current.map((item) =>
              item.id === updated.id
                ? { ...item, status: updated.status, version: updated.version }
                : item,
            )
          : current,
      );
      setNotice(t("guide.published"));
    } catch (cause) {
      setError(describeError(cause, t("guide.error.publish")));
    } finally {
      setPublishing(false);
    }
  }

  function applyQuestionChange(question: InterviewQuestion): void {
    setGuide((current) => {
      if (!current) return current;
      const known = current.questions.some((item) => item.id === question.id);
      const questions = known
        ? current.questions.map((item) => (item.id === question.id ? question : item))
        : [...current.questions, question].sort((left, right) => left.position - right.position);
      return { ...current, questions };
    });
  }

  return (
    <section aria-labelledby="interview-panel-heading" aria-busy={busy} className="space-y-4">
      <div className="space-y-1">
        <h2 id="interview-panel-heading" className="text-lg font-semibold">
          {t("guide.title")}
        </h2>
        <p className="text-sm text-text-muted">{t("guide.note")}</p>
      </div>

      <form onSubmit={(event) => void generate(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1 space-y-1">
          <Label htmlFor="interview-application-id" className="block">
            {t("guide.applicationId")}
          </Label>
          <Input
            id="interview-application-id"
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
          />
        </div>
        <Button type="submit" disabled={busy}>
          {generating ? t("guide.generating") : t("guide.generate")}
        </Button>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {generating
          ? t("guide.generatingLong")
          : detailLoading
            ? t("guide.loadingDetail")
            : publishing
              ? t("guide.publishing")
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
            {t("guide.retry")}
          </Button>
        </Card>
      ) : null}

      {guides ? (
        <section aria-labelledby="interview-guides-heading" className="space-y-2">
          <h3 id="interview-guides-heading" className="text-base font-semibold">
            {t("guide.listTitle")}
          </h3>
          {guides.length > 0 ? (
            <ul className="flex flex-wrap gap-2">
              {guides.map((item) => (
                <li key={item.id}>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => void openGuide(item.id)}
                  >
                    {item.title} · v{item.version}
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <Card className="bg-secondary p-3 text-sm text-text-muted">
              {t("guide.empty")}
            </Card>
          )}
        </section>
      ) : null}

      {!guide && !error && !busy ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          {t("guide.prompt")}
        </Card>
      ) : null}

      {guide ? (
        <div className="space-y-4">
          <section aria-labelledby="interview-guide-heading" className="space-y-3">
            <h3 id="interview-guide-heading" className="text-base font-semibold">
              {guide.title}
            </h3>
            <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-text-muted">
              <div>
                <dt className="inline font-semibold">{t("guide.statusLabel")}</dt>
                <dd className="inline">{t(GUIDE_STATUS_KEYS[guide.status])}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">{t("guide.versionLabel")}</dt>
                <dd className="inline">v{guide.version}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">{t("guide.modelLabel")}</dt>
                <dd className="inline">{guide.model_version ?? "—"}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">{t("guide.promptVersionLabel")}</dt>
                <dd className="inline">{guide.prompt_version ?? "—"}</dd>
              </div>
            </dl>
            <p className="text-sm">
              {t("guide.reviewRequired")}
              {guide.review_required ? t("guide.yes") : t("guide.no")}
            </p>
            {guide.needs_review ? (
              <Card role="status" className="px-3 py-2 text-sm">
                {t("guide.needsReview")}
              </Card>
            ) : null}
            <Button
              type="button"
              disabled={publishing || guide.status !== "draft"}
              onClick={() => void publish()}
            >
              {guide.status === "published"
                ? t("guide.publishedButton")
                : publishing
                  ? t("guide.publishing")
                  : t("guide.publish")}
            </Button>
          </section>

          <QuestionEditor
            guideId={guide.id}
            questions={guide.questions}
            modelVersion={guide.model_version}
            promptVersion={guide.prompt_version}
            onChanged={applyQuestionChange}
          />
          <GuideHistory guideId={guide.id} />
        </div>
      ) : null}
    </section>
  );
}
