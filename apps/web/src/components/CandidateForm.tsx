"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n } from "../lib/i18n";
import type { Candidate, CandidateCreate } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function CandidateForm({ onCreated }: { onCreated?: (candidate: Candidate) => void }) {
  const { t } = useI18n();
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const payload: CandidateCreate = {
      name: value("name"),
      email: value("email"),
      location: value("location") || null,
    };

    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const candidate = await apiFetch<Candidate>("/api/v1/candidates", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      form.reset();
      setMessage(`${t("candidates.form.created")} ${candidate.name}.`);
      onCreated?.(candidate);
    } catch (cause) {
      setError(describeError(cause, t("candidates.form.error")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={submitting} className="space-y-3">
      <h3 className="text-sm font-semibold">{t("candidates.form.new")}</h3>
      <div className="space-y-1">
        <Label htmlFor="candidate-name" className="block">
          {t("candidates.form.name")}
        </Label>
        <Input
          id="candidate-name"
          name="name"
          type="text"
          required
          maxLength={200}
          disabled={submitting}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="candidate-email" className="block">
          {t("candidates.form.email")}
        </Label>
        <Input
          id="candidate-email"
          name="email"
          type="email"
          required
          disabled={submitting}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="candidate-location" className="block">
          {t("candidates.form.location")}
        </Label>
        <Input
          id="candidate-location"
          name="location"
          type="text"
          disabled={submitting}
        />
      </div>
      <Button type="submit" disabled={submitting}>
        {submitting ? t("candidates.form.creating") : t("candidates.form.create")}
      </Button>
      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {error ? (
          <span role="alert" className="text-text">
            {error}
          </span>
        ) : (
          message
        )}
      </p>
    </form>
  );
}
