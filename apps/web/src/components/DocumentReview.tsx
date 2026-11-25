"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { Extraction, ExtractionField, ReviewResult, ReviewSummary } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";

const FIELD_LABELS: Record<ExtractionField["field_name"], string> = {
  name: "Nombre",
  email: "Correo",
  location: "Ubicación",
  experience: "Experiencia",
  education: "Formación",
  skills: "Habilidades",
  projects: "Proyectos",
  languages: "Idiomas",
};

const STATUS_LABELS: Record<ExtractionField["status"], string> = {
  extracted: "Extraído",
  needs_review: "Requiere revisión",
  missing: "Ausente",
  confirmed: "Confirmado",
  corrected: "Corregido",
};

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return "No se pudo completar la revisión.";
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
        setError(describeError(cause));
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [requestExtraction]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setExtraction(await requestExtraction());
    } catch (cause) {
      setError(describeError(cause));
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
      setMessage(`${FIELD_LABELS[result.field_name]}: ${STATUS_LABELS[result.status]}.`);
      await load();
    } catch (cause) {
      setError(describeError(cause));
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
        `Confirmados ${result.confirmed}; pendientes de revisión ${result.needs_review}.`,
      );
      await load();
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setConfirmingAll(false);
    }
  }

  if (loading && extraction === null) {
    return <p aria-live="polite">Cargando extracción…</p>;
  }

  if (!extraction) {
    return (
      <section role="alert" className="space-y-2">
        <p>{error ?? "No se pudo cargar la extracción."}</p>
        <Button type="button" variant="outline" onClick={() => void load()}>
          Reintentar
        </Button>
      </section>
    );
  }

  return (
    <section aria-labelledby="review-heading" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="review-heading" className="text-lg font-semibold">
          Revisión de extracción
        </h2>
        <Button
          type="button"
          variant="outline"
          onClick={() => void confirmAll()}
          disabled={confirmingAll}
        >
          {confirmingAll ? "Confirmando…" : "Confirmar campos con evidencia"}
        </Button>
      </div>

      {extraction.injection_detected ? (
        <Card role="alert" className="px-3 py-2 text-sm">
          Se detectó una posible inyección de prompt en el documento. Revisa cada campo
          individualmente antes de confirmar.
        </Card>
      ) : null}
      {extraction.review_required ? (
        <p role="status" className="text-sm text-text-muted">
          Este documento requiere revisión humana.
        </p>
      ) : null}

      <ul className="space-y-3">
        {extraction.fields.map((field) => {
          const label = FIELD_LABELS[field.field_name];
          return (
            <li key={field.id}>
              <Card className="space-y-2 p-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">{label}</h3>
                  <span className="text-xs text-text-muted">
                    {STATUS_LABELS[field.status]}
                  </span>
                </div>
                <p className="break-words text-sm">{displayValue(field.value)}</p>
                {field.evidence.length > 0 ? (
                  <ul className="space-y-1">
                    {field.evidence.map((evidence, index) => (
                      <li key={`${evidence.document_id}-${evidence.page}-${index}`}>
                        <blockquote className="border-l-2 border-border pl-2 text-xs text-text-muted">
                          Página {evidence.page}: {evidence.quote.slice(0, 120)}
                        </blockquote>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-text-muted">Sin evidencia verificable.</p>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <Label htmlFor={`correction-${field.id}`} className="sr-only">
                    Corregir {label}
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
                    placeholder="Corrección opcional"
                    className="min-w-40 flex-1"
                  />
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void confirmField(field)}
                    disabled={busyField === field.id}
                  >
                    {busyField === field.id ? "Confirmando…" : "Confirmar"}
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
