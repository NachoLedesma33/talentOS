"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n } from "../lib/i18n";
import type {
  Job,
  RequirementCategory,
  RequirementCreate,
  RequirementImportance,
  JobRequirement,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";
import { Textarea } from "./ui/shadcn/textarea";

const CATEGORIES: readonly RequirementCategory[] = [
  "skill",
  "experience",
  "education",
  "language",
  "certification",
  "other",
];

const IMPORTANCES: readonly RequirementImportance[] = ["required", "desirable"];

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function RequirementsEditor({ job }: { job: Job | null }) {
  const { t } = useI18n();
  const [submitting, setSubmitting] = useState(false);
  const [requirements, setRequirements] = useState<JobRequirement[]>([]);
  const [loadedJobId, setLoadedJobId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!job) {
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const payload: RequirementCreate = {
      category: value("category") as RequirementCategory,
      description: value("description"),
      importance: value("importance") as RequirementImportance,
      weight: Number(value("weight")),
      weight_justification: value("weight_justification"),
    };

    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const created = await apiFetch<JobRequirement>(
        `/api/v1/jobs/${job.id}/requirements`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      setRequirements((current) =>
        loadedJobId === job.id ? [...current, created] : [created],
      );
      setLoadedJobId(job.id);
      form.reset();
      setMessage(t("requirements.added"));
    } catch (cause) {
      setError(describeError(cause, t("requirements.error")));
    } finally {
      setSubmitting(false);
    }
  }

  const visibleRequirements = loadedJobId === job?.id ? requirements : [];

  return (
    <section aria-labelledby="requirements-heading" className="space-y-3">
      <h3 id="requirements-heading" className="text-sm font-semibold">
        {t("requirements.title")}
      </h3>
      {job ? (
        <p className="text-sm text-text-muted">
          {t("requirements.selected")} {job.title}
        </p>
      ) : (
        <p className="text-sm text-text-muted">{t("requirements.selectJob")}</p>
      )}

      <form onSubmit={handleSubmit} aria-busy={submitting}>
        <Card className="space-y-3 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="requirement-category" className="block">
                {t("requirements.category")}
              </Label>
              <Select
                id="requirement-category"
                name="category"
                defaultValue="skill"
                disabled={submitting || !job}
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="requirement-importance" className="block">
                {t("requirements.importance")}
              </Label>
              <Select
                id="requirement-importance"
                name="importance"
                defaultValue="required"
                disabled={submitting || !job}
              >
                {IMPORTANCES.map((importance) => (
                  <option key={importance} value={importance}>
                    {importance}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="requirement-description" className="block">
              {t("requirements.description")}
            </Label>
            <Textarea
              id="requirement-description"
              name="description"
              rows={2}
              required
              disabled={submitting || !job}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="requirement-weight" className="block">
                {t("requirements.weight")}
              </Label>
              <Input
                id="requirement-weight"
                name="weight"
                type="number"
                min={0}
                max={1}
                step={0.01}
                defaultValue="0"
                disabled={submitting || !job}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="requirement-justification" className="block">
                {t("requirements.justification")}
              </Label>
              <Input
                id="requirement-justification"
                name="weight_justification"
                type="text"
                disabled={submitting || !job}
              />
            </div>
          </div>
          <Button type="submit" disabled={submitting || !job}>
            {submitting ? t("requirements.adding") : t("requirements.add")}
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
        </Card>
      </form>

      {visibleRequirements.length > 0 ? (
        <ul className="space-y-1">
          {visibleRequirements.map((requirement) => (
            <li key={requirement.id}>
              <Card className="p-3 text-sm text-text-muted">
                <span className="font-semibold text-text">{requirement.category}</span>:{" "}
                {requirement.description} ({requirement.importance},{" "}
                {t("requirements.weightShort")} {requirement.weight})
              </Card>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
