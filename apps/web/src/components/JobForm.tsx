"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { Job, JobCreate } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Textarea } from "./ui/shadcn/textarea";

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function JobForm({ onCreated }: { onCreated?: (job: Job) => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const payload: JobCreate = {
      title: value("title"),
      description: value("description"),
      modality: value("modality") || null,
      location: value("location") || null,
      seniority: value("seniority") || null,
      owner_id: value("owner_id"),
    };

    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const job = await apiFetch<Job>("/api/v1/jobs", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      form.reset();
      setMessage(`Vacante creada: ${job.title}.`);
      onCreated?.(job);
    } catch (cause) {
      setError(describeError(cause, "No se pudo crear la vacante."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={submitting}>
      <Card className="space-y-3 p-4">
        <h3 className="text-sm font-semibold">Nueva vacante</h3>
        <div className="space-y-1">
          <Label htmlFor="job-title" className="block">
            Título
          </Label>
          <Input
            id="job-title"
            name="title"
            type="text"
            required
            maxLength={200}
            disabled={submitting}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="job-description" className="block">
            Descripción
          </Label>
          <Textarea
            id="job-description"
            name="description"
            rows={3}
            disabled={submitting}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="job-modality" className="block">
              Modalidad
            </Label>
            <Input
              id="job-modality"
              name="modality"
              type="text"
              disabled={submitting}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="job-location" className="block">
              Ubicación
            </Label>
            <Input
              id="job-location"
              name="location"
              type="text"
              disabled={submitting}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="job-seniority" className="block">
              Seniority
            </Label>
            <Input
              id="job-seniority"
              name="seniority"
              type="text"
              disabled={submitting}
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="job-owner" className="block">
            ID del responsable (UUID)
          </Label>
          <Input
            id="job-owner"
            name="owner_id"
            type="text"
            required
            disabled={submitting}
          />
        </div>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Creando vacante…" : "Crear vacante"}
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
  );
}
