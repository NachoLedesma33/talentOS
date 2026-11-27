"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  InterviewFeedback,
  InterviewFeedbackList,
  InterviewFeedbackStatus,
  InterviewFeedbackSubmitRequest,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Checkbox } from "./ui/shadcn/checkbox";
import { Label } from "./ui/shadcn/label";
import { Textarea } from "./ui/shadcn/textarea";

const MAX_LINES = 20;
const MAX_LINE_LENGTH = 500;
const MAX_NOTES = 1000;

type Translate = (key: MessageKey) => string;

const STATUS_KEYS: Record<InterviewFeedbackStatus, MessageKey> = {
  pending: "feedback.status.pending",
  submitted: "feedback.status.submitted",
  needs_review: "feedback.status.needs_review",
};

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
}

function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function validateLines(lines: string[], t: Translate): string | null {
  if (lines.length > MAX_LINES) {
    return `${t("feedback.maxItemsPrefix")}${MAX_LINES}${t("feedback.maxItemsSuffix")}`;
  }
  if (lines.some((line) => line.length > MAX_LINE_LENGTH)) {
    return `${t("feedback.maxCharsPrefix")}${MAX_LINE_LENGTH}${t("feedback.maxCharsSuffix")}`;
  }
  return null;
}

interface FeedbackFormProps {
  questionId: string;
  requirementId: string;
}

export function FeedbackForm({ questionId, requirementId }: FeedbackFormProps) {
  const { t } = useI18n();
  const [observedText, setObservedText] = useState("");
  const [gapsText, setGapsText] = useState("");
  const [followUpNeeded, setFollowUpNeeded] = useState(false);
  const [notes, setNotes] = useState("");
  const [history, setHistory] = useState<InterviewFeedback[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [latest, setLatest] = useState<InterviewFeedback | null>(null);

  const requestHistory = useCallback(
    () =>
      apiFetch<InterviewFeedbackList>(
        `/api/v1/interviews/questions/${encodeURIComponent(questionId)}/feedback`,
      ),
    [questionId],
  );

  async function load(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const result = await requestHistory();
      setHistory(result.items);
    } catch (cause) {
      setError(describeError(cause, t("feedback.error")));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    requestHistory().then(
      (result) => {
        if (!active) return;
        setHistory(result.items);
        setLoading(false);
      },
      (cause: unknown) => {
        if (!active) return;
        setError(describeError(cause, t("feedback.error")));
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [requestHistory, t]);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting) return;

    const observedEvidence = parseLines(observedText);
    const gaps = parseLines(gapsText);
    const invalid = validateLines(observedEvidence, t) ?? validateLines(gaps, t);
    if (invalid) {
      setError(invalid);
      return;
    }

    setSubmitting(true);
    setError(null);
    setNotice(null);
    const payload: InterviewFeedbackSubmitRequest = {
      observed_evidence: observedEvidence,
      gaps,
      follow_up_needed: followUpNeeded,
      notes: notes.trim() || null,
    };
    try {
      const created = await apiFetch<InterviewFeedback>(
        `/api/v1/interviews/questions/${encodeURIComponent(questionId)}/feedback`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      setLatest(created);
      setNotice(t("feedback.saved"));
      setObservedText("");
      setGapsText("");
      setFollowUpNeeded(false);
      setNotes("");
      await load();
    } catch (cause) {
      setError(describeError(cause, t("feedback.error")));
    } finally {
      setSubmitting(false);
    }
  }

  const recorded = latest ?? history[0] ?? null;

  return (
    <section aria-labelledby={`feedback-heading-${questionId}`} className="space-y-3 border-t border-border pt-3">
      <div className="space-y-1">
        <h5 id={`feedback-heading-${questionId}`} className="text-sm font-semibold">
          {t("feedback.title")}
        </h5>
        <p className="text-xs text-text-muted">{t("feedback.note")}</p>
        <p className="text-xs text-text-muted">
          {t("feedback.requirement")}
          {requirementId}
        </p>
      </div>

      <form onSubmit={(event) => void submit(event)} aria-busy={submitting}>
        <Card className="space-y-2 p-3">
          <div className="space-y-1">
            <Label
              htmlFor={`feedback-evidence-${questionId}`}
              className="block text-xs"
            >
              {t("feedback.evidenceLabelPrefix")}
              {MAX_LINES}
              {t("feedback.evidenceLabelSuffix")}
            </Label>
            <Textarea
              id={`feedback-evidence-${questionId}`}
              value={observedText}
              onChange={(event) => setObservedText(event.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`feedback-gaps-${questionId}`} className="block text-xs">
              {t("feedback.gapsLabelPrefix")}
              {MAX_LINES}
              {t("feedback.gapsLabelSuffix")}
            </Label>
            <Textarea
              id={`feedback-gaps-${questionId}`}
              value={gapsText}
              onChange={(event) => setGapsText(event.target.value)}
              rows={3}
            />
          </div>
          <Label htmlFor={`feedback-follow-up-${questionId}`} className="flex items-center gap-2 text-sm">
            <Checkbox
              id={`feedback-follow-up-${questionId}`}
              checked={followUpNeeded}
              onChange={(event) => setFollowUpNeeded(event.target.checked)}
            />
            {t("feedback.followUp")}
          </Label>
          <div className="space-y-1">
            <Label htmlFor={`feedback-notes-${questionId}`} className="block text-xs">
              {t("feedback.notes")}
            </Label>
            <Textarea
              id={`feedback-notes-${questionId}`}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              maxLength={MAX_NOTES}
              rows={2}
            />
          </div>
          <Button type="submit" size="sm" disabled={submitting}>
            {submitting ? t("feedback.submitting") : t("feedback.submit")}
          </Button>
        </Card>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {loading ? t("feedback.loading") : notice}
      </p>
      {error ? (
        <Card role="alert" className="p-2 text-sm">
          {t("feedback.errorPrefix")} {error}
        </Card>
      ) : null}

      {recorded ? (
        <dl className="grid gap-x-6 gap-y-1 text-xs text-text-muted">
          <div>
            <dt className="inline font-semibold">{t("feedback.requirementLabel")}</dt>
            <dd className="inline">{recorded.requirement_id}</dd>
          </div>
          <div>
            <dt className="inline font-semibold">{t("feedback.interviewerLabel")}</dt>
            <dd className="inline">{recorded.interviewer_id}</dd>
          </div>
          <div>
            <dt className="inline font-semibold">{t("feedback.submittedLabel")}</dt>
            <dd className="inline">{recorded.submitted_at ?? "—"}</dd>
          </div>
        </dl>
      ) : null}

      <h6 className="text-xs font-semibold text-text-muted">{t("feedback.history")}</h6>
      {!loading && history.length === 0 && !error ? (
        <p className="text-sm text-text-muted">{t("feedback.empty")}</p>
      ) : history.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <caption className="sr-only">{t("feedback.history")}</caption>
            <thead>
              <tr className="border-b border-border">
                <th scope="col" className="py-1 pr-3 font-semibold">
                  {t("feedback.col.requirement")}
                </th>
                <th scope="col" className="py-1 pr-3 font-semibold">
                  {t("feedback.col.interviewer")}
                </th>
                <th scope="col" className="py-1 pr-3 font-semibold">
                  {t("feedback.col.submitted")}
                </th>
                <th scope="col" className="py-1 pr-3 font-semibold">
                  {t("feedback.col.status")}
                </th>
                <th scope="col" className="py-1 font-semibold">
                  {t("feedback.col.evidence")}
                </th>
              </tr>
            </thead>
            <tbody>
              {history.map((item) => (
                <tr key={item.id} className="border-b border-border align-top">
                  <td className="py-1 pr-3">{item.requirement_id}</td>
                  <td className="py-1 pr-3">{item.interviewer_id}</td>
                  <td className="py-1 pr-3">{item.submitted_at ?? "—"}</td>
                  <td className="py-1 pr-3">{t(STATUS_KEYS[item.status])}</td>
                  <td className="py-1">
                    {item.observed_evidence.length} {t("feedback.evidenceCount")} ·{" "}
                    {item.gaps.length} {t("feedback.gapCount")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
