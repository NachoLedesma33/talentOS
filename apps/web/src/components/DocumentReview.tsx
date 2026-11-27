"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type { Extraction, ExtractionField, ReviewResult, ReviewSummary } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";

const FIELD_KEYS: Record<ExtractionField["field_name"], MessageKey> = {
  name: "review.field.name",
  email: "review.field.email",
  location: "review.field.location",
  experience: "review.field.experience",
  education: "review.field.education",
  skills: "review.field.skills",
  projects: "review.field.projects",
  languages: "review.field.languages",
};

const STATUS_KEYS: Record<ExtractionField["status"], MessageKey> = {
  extracted: "review.status.extracted",
  needs_review: "review.status.needs_review",
  missing: "review.status.missing",
  confirmed: "review.status.confirmed",
  corrected: "review.status.corrected",
};

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

function displayValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(String).join(", ") || "—";
  }
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export function DocumentReview({ documentId }: { documentId: string }) {
  const { t } = useI18n();
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [busyField, setBusyField] = useState<string | null>(null);
  const [confirmingAll, setConfirmingAll] = useState(false);

  const requestExtraction = useCallback(
    () => apiFetch<Extraction>(`/api/v1/documents/${documentId}/extraction`),
    [documentId],
  );

  useEffect(() => {
    let active = true;
    requestExtraction().then(
      (result) => {
        if (!active) return;
        setExtraction(result);
        setLoading(false);
      },
      (cause: unknown) => {
        if (!active) return;
        setError(describeError(cause, t("review.error")));
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [requestExtraction, t]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setExtraction(await requestExtraction());
    } catch (cause) {
      setError(describeError(cause, t("review.error")));
    } finally {
      setLoading(false);
    }
  }

  async function confirmField(field: ExtractionField) {
    setBusyField(field.id);
    setError(null);
    setMessage(null);
    const correction = (corrections[field.id] ?? "").trim();
    const payload = correction ? { value: { text: correction } } : {};
    try {
      const result = await apiFetch<ReviewResult>(
        `/api/v1/documents/${documentId}/extraction/fields/${field.id}/confirm`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      setMessage(
        `${t(FIELD_KEYS[result.field_name])}: ${t(STATUS_KEYS[result.status])}.`,
      );
      await load();
    } catch (cause) {
      setError(describeError(cause, t("review.error")));
    } finally {
      setBusyField(null);
    }
  }

  async function confirmAll() {
    setConfirmingAll(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<ReviewSummary>(
        `/api/v1/documents/${documentId}/extraction/confirm-all`,
        { method: "POST" },
      );
      setMessage(
        `${t("review.confirmed")} ${result.confirmed}; ${t("review.pendingReview")} ${result.needs_review}.`,
      );
      await load();
    } catch (cause) {
      setError(describeError(cause, t("review.error")));
    } finally {
      setConfirmingAll(false);
    }
  }

  if (loading && extraction === null) {
    return <p aria-live="polite">{t("review.loading")}</p>;
  }

  if (!extraction) {
    return (
      <section role="alert" className="space-y-2">
        <p>{error ?? t("review.loadError")}</p>
        <Button type="button" variant="outline" onClick={() => void load()}>
          {t("review.retry")}
        </Button>
      </section>
    );
  }

  return (
    <section aria-labelledby="review-heading" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="review-heading" className="text-lg font-semibold">
          {t("review.title")}
        </h2>
        <Button
          type="button"
          variant="outline"
          onClick={() => void confirmAll()}
          disabled={confirmingAll}
        >
          {confirmingAll ? t("review.confirmingAll") : t("review.confirmAll")}
        </Button>
      </div>

      {extraction.injection_detected ? (
        <Card role="alert" className="px-3 py-2 text-sm">
          {t("review.injection")}
        </Card>
      ) : null}
      {extraction.review_required ? (
        <p role="status" className="text-sm text-text-muted">
          {t("review.humanRequired")}
        </p>
      ) : null}

      <ul className="space-y-3">
        {extraction.fields.map((field) => {
          const label = t(FIELD_KEYS[field.field_name]);
          return (
            <li key={field.id}>
              <Card className="space-y-2 p-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">{label}</h3>
                  <span className="text-xs text-text-muted">
                    {t(STATUS_KEYS[field.status])}
                  </span>
                </div>
                <p className="break-words text-sm">{displayValue(field.value)}</p>
                {field.evidence.length > 0 ? (
                  <ul className="space-y-1">
                    {field.evidence.map((evidence, index) => (
                      <li key={`${evidence.document_id}-${evidence.page}-${index}`}>
                        <blockquote className="border-l-2 border-border pl-2 text-xs text-text-muted">
                          {t("review.page")} {evidence.page}: {evidence.quote.slice(0, 120)}
                        </blockquote>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-text-muted">{t("review.noEvidence")}</p>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <Label htmlFor={`correction-${field.id}`} className="sr-only">
                    {t("review.correct")} {label}
                  </Label>
                  <Input
                    id={`correction-${field.id}`}
                    value={corrections[field.id] ?? ""}
                    onChange={(event) =>
                      setCorrections((current) => ({
                        ...current,
                        [field.id]: event.target.value,
                      }))
                    }
                    placeholder={t("review.correction")}
                    className="min-w-40 flex-1"
                  />
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void confirmField(field)}
                    disabled={busyField === field.id}
                  >
                    {busyField === field.id ? t("review.confirming") : t("review.confirm")}
                  </Button>
                </div>
              </Card>
            </li>
          );
        })}
      </ul>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {error ? (
          <span role="alert" className="text-text">
            {error}
          </span>
        ) : (
          message
        )}
      </p>
    </section>
  );
}
