"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  GenerateGuideRequest,
  GuideGeneration,
  InterviewGuideDetail,
  InterviewGuideList,
  InterviewGuideStatus,
  InterviewGuideSummary,
  InterviewQuestion,
} from "../lib/types";
import { GuideHistory } from "./GuideHistory";
import { QuestionEditor } from "./QuestionEditor";

const GUIDE_STATUS_LABELS: Record<InterviewGuideStatus, string> = {
  draft: "Borrador",
  published: "Publicada",
  archived: "Archivada",
};

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function InterviewGuidePanel() {
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

  async function openGuide(id: string, successNotice = "Guía cargada."): Promise<void> {
    setDetailLoading(true);
    try {
      const detail = await apiFetch<InterviewGuideDetail>(
        `/api/v1/interviews/guides/${encodeURIComponent(id)}`,
      );
      setGuide(detail);
      setNotice(successNotice);
    } catch (cause) {
      setGuide(null);
      setError(describeError(cause, "No se pudo cargar la guía."));
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
        result.created ? "Guía creada." : "Guía existente recuperada.",
      );
    } catch (cause) {
      setError(describeError(cause, "No se pudo generar la guía."));
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
      setNotice("Guía publicada.");
    } catch (cause) {
      setError(describeError(cause, "No se pudo publicar la guía."));
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
          Guías de entrevista
        </h2>
        <p className="text-sm text-text-muted">
          Preguntas vinculadas a requisitos, revisión humana y evidencia observada. Sin puntuación
          ni decisión automática. Los permisos los valida el servidor.
        </p>
      </div>

      <form onSubmit={(event) => void generate(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1 space-y-1">
          <label htmlFor="interview-application-id" className="block text-sm font-semibold">
            ID de postulación
          </label>
          <input
            id="interview-application-id"
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
            className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-on-accent disabled:opacity-60"
        >
          {generating ? "Generando…" : "Generar guía"}
        </button>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {generating
          ? "Generando guía y validando políticas…"
          : detailLoading
            ? "Cargando detalle de la guía…"
            : publishing
              ? "Publicando guía…"
              : notice}
      </p>
      {error ? (
        <section role="alert" className="space-y-2 rounded-sm border border-border p-3">
          <p className="text-sm">{error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setNotice(null);
            }}
            className="rounded-sm border border-border px-3 py-1 text-sm font-semibold"
          >
            Revisar y reintentar
          </button>
        </section>
      ) : null}

      {guides ? (
        <section aria-labelledby="interview-guides-heading" className="space-y-2">
          <h3 id="interview-guides-heading" className="text-base font-semibold">
            Guías de la postulación
          </h3>
          {guides.length > 0 ? (
            <ul className="flex flex-wrap gap-2">
              {guides.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void openGuide(item.id)}
                    className="rounded-sm border border-border bg-surface px-3 py-1 text-sm font-semibold disabled:opacity-60"
                  >
                    {item.title} · v{item.version}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
              No hay guías registradas para esta postulación.
            </p>
          )}
        </section>
      ) : null}

      {!guide && !error && !busy ? (
        <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
          Ingresa el ID de una postulación para generar o recuperar su guía de entrevista.
        </p>
      ) : null}

      {guide ? (
        <div className="space-y-4">
          <section aria-labelledby="interview-guide-heading" className="space-y-3">
            <h3 id="interview-guide-heading" className="text-base font-semibold">
              {guide.title}
            </h3>
            <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-text-muted">
              <div>
                <dt className="inline font-semibold">Estado: </dt>
                <dd className="inline">{GUIDE_STATUS_LABELS[guide.status]}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">Versión: </dt>
                <dd className="inline">v{guide.version}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">Modelo: </dt>
                <dd className="inline">{guide.model_version ?? "—"}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">Prompt: </dt>
                <dd className="inline">{guide.prompt_version ?? "—"}</dd>
              </div>
            </dl>
            <p className="text-sm">{`Revisión requerida: ${guide.review_required ? "sí" : "no"}`}</p>
            {guide.needs_review ? (
              <p role="status" className="rounded-sm border border-border px-3 py-2 text-sm">
                La guía conserva observaciones pendientes de revisión humana.
              </p>
            ) : null}
            <button
              type="button"
              disabled={publishing || guide.status !== "draft"}
              onClick={() => void publish()}
              className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-on-accent disabled:opacity-60"
            >
              {guide.status === "published"
                ? "Guía ya publicada"
                : publishing
                  ? "Publicando…"
                  : "Publicar guía"}
            </button>
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
