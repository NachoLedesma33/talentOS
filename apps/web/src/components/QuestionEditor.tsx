"use client";

import { useState, type FormEvent } from "react";
import { ACTIVE_ORG_STORAGE_KEY, ApiError, apiFetch } from "../lib/api";
import type {
  InterviewQuestion,
  InterviewQuestionCategory,
  InterviewQuestionCreateRequest,
  InterviewQuestionStatus,
  InterviewQuestionUpdateRequest,
  PolicyErrorEnvelope,
} from "../lib/types";
import { FeedbackForm } from "./FeedbackForm";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";
import { Textarea } from "./ui/shadcn/textarea";

const CATEGORY_LABELS: Record<InterviewQuestionCategory, string> = {
  technical: "Técnica",
  deep_dive: "Profundización",
};

const STATUS_LABELS: Record<InterviewQuestionStatus, string> = {
  draft: "Borrador",
  approved: "Aprobada",
  rejected: "Rechazada",
  archived: "Archivada",
};

const EDITABLE_STATUSES: InterviewQuestionStatus[] = ["draft", "approved", "rejected"];
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

class QuestionRequestError extends Error {
  readonly status: number;
  readonly reasonCode?: string;

  constructor(status: number, message: string, reasonCode?: string) {
    super(message);
    this.name = "QuestionRequestError";
    this.status = status;
    this.reasonCode = reasonCode;
  }
}

function parseErrorEnvelope(value: unknown): PolicyErrorEnvelope | null {
  if (typeof value !== "object" || value === null) return null;
  const rawError = (value as { error?: unknown }).error;
  if (typeof rawError !== "object" || rawError === null) return null;
  const error = rawError as {
    code?: unknown;
    message?: unknown;
    request_id?: unknown;
    reason_code?: unknown;
  };
  if (typeof error.code !== "string" || typeof error.message !== "string") return null;
  return {
    error: {
      code: error.code,
      message: error.message,
      request_id: typeof error.request_id === "string" ? error.request_id : "unknown",
      reason_code: typeof error.reason_code === "string" ? error.reason_code : undefined,
    },
  };
}

/**
 * `apiFetch` no expone `reason_code`; en este único punto se lee el envelope
 * completo para mostrar el motivo de la política anti-discriminación.
 */
async function requestQuestion<T>(
  path: string,
  method: "POST" | "PATCH",
  body: InterviewQuestionCreateRequest | InterviewQuestionUpdateRequest,
): Promise<T> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const activeOrganizationId =
    typeof window === "undefined" ? null : window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY);
  if (activeOrganizationId) {
    headers.set("X-Organization-ID", activeOrganizationId);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!response.ok) {
    let envelope: PolicyErrorEnvelope | null = null;
    try {
      envelope = parseErrorEnvelope(await response.json());
    } catch {
      envelope = null;
    }
    throw new QuestionRequestError(
      response.status,
      envelope?.error.message ?? "No se pudo guardar la pregunta.",
      envelope?.error.reason_code,
    );
  }
  return (await response.json()) as T;
}

function describeError(error: unknown): { text: string; reasonCode?: string } {
  if (error instanceof QuestionRequestError) {
    return {
      text: `${error.status}: ${error.message}`,
      reasonCode: error.reasonCode,
    };
  }
  if (error instanceof ApiError) {
    return { text: `${error.status}: ${error.message}` };
  }
  return { text: "No se pudo guardar la pregunta." };
}

function ErrorNotice({ error }: { error: { text: string; reasonCode?: string } }) {
  return (
    <Card role="alert" className="space-y-1 p-2">
      <p className="text-sm">{error.text}</p>
      {error.reasonCode ? (
        <p className="text-sm">Motivo de política: {error.reasonCode}</p>
      ) : null}
    </Card>
  );
}

interface QuestionRowProps {
  question: InterviewQuestion;
  onChanged?: (question: InterviewQuestion) => void;
}

function QuestionRow({ question, onChanged }: QuestionRowProps) {
  const [editing, setEditing] = useState(false);
  const [questionText, setQuestionText] = useState(question.question);
  const [evidenceFocus, setEvidenceFocus] = useState(question.evidence_focus);
  const [competency, setCompetency] = useState(question.competency);
  const [position, setPosition] = useState(String(question.position));
  const [status, setStatus] = useState<InterviewQuestionStatus>(question.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; reasonCode?: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  async function save(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError(null);
    setNotice(null);
    const payload: InterviewQuestionUpdateRequest = {
      question: questionText.trim(),
      evidence_focus: evidenceFocus.trim(),
      competency: competency.trim(),
      position: Number(position),
      status,
    };
    try {
      const updated = await requestQuestion<InterviewQuestion>(
        `/api/v1/interviews/questions/${encodeURIComponent(question.id)}`,
        "PATCH",
        payload,
      );
      setEditing(false);
      setNotice("Pregunta actualizada.");
      onChanged?.(updated);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function archive(): Promise<void> {
    if (busy) return;
    if (
      !window.confirm(
        "¿Archivar esta pregunta? Dejará de estar disponible en la guía activa.",
      )
    ) {
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiFetch<InterviewQuestion>(
        `/api/v1/interviews/questions/${encodeURIComponent(question.id)}`,
        { method: "DELETE" },
      );
      setNotice("Pregunta archivada.");
      onChanged?.(updated);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      role="article"
      aria-labelledby={`interview-question-${question.id}`}
      className="space-y-3 p-3"
    >
      <div className="space-y-1">
        <h4 id={`interview-question-${question.id}`} className="text-sm font-semibold">
          Posición {question.position} · {CATEGORY_LABELS[question.category]}
        </h4>
        <p className="break-words text-sm">{question.question}</p>
      </div>

      <dl className="grid gap-x-6 gap-y-1 text-xs text-text-muted md:grid-cols-2">
        <div>
          <dt className="inline font-semibold">Requisito: </dt>
          <dd className="inline">{question.requirement_id}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">Estado: </dt>
          <dd className="inline">{STATUS_LABELS[question.status]}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">Foco de evidencia: </dt>
          <dd className="inline">{question.evidence_focus}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">Competencia: </dt>
          <dd className="inline">{question.competency}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">Posición: </dt>
          <dd className="inline">{question.position}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">Revisión requerida: </dt>
          <dd className="inline">{question.review_required ? "sí" : "no"}</dd>
        </div>
      </dl>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => {
            setEditing((current) => !current);
            setError(null);
            setNotice(null);
          }}
        >
          {editing ? "Cerrar edición" : "Editar pregunta"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy || question.status === "archived"}
          onClick={() => void archive()}
        >
          Archivar pregunta
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setFeedbackOpen((current) => !current)}
        >
          {feedbackOpen ? "Cerrar feedback" : "Registrar feedback"}
        </Button>
      </div>

      {editing ? (
        <form onSubmit={(event) => void save(event)} className="space-y-2">
          <Label htmlFor={`question-text-${question.id}`} className="block text-xs">
            Pregunta {question.id}
          </Label>
          <Textarea
            id={`question-text-${question.id}`}
            value={questionText}
            onChange={(event) => setQuestionText(event.target.value)}
            required
            rows={2}
          />
          <Label
            htmlFor={`question-focus-${question.id}`}
            className="block text-xs"
          >
            Foco de evidencia {question.id}
          </Label>
          <Input
            id={`question-focus-${question.id}`}
            value={evidenceFocus}
            onChange={(event) => setEvidenceFocus(event.target.value)}
            required
          />
          <Label
            htmlFor={`question-competency-${question.id}`}
            className="block text-xs"
          >
            Competencia {question.id}
          </Label>
          <Input
            id={`question-competency-${question.id}`}
            value={competency}
            onChange={(event) => setCompetency(event.target.value)}
            required
          />
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label
                htmlFor={`question-position-${question.id}`}
                className="block text-xs"
              >
                Posición {question.id}
              </Label>
              <Input
                id={`question-position-${question.id}`}
                type="number"
                min={1}
                value={position}
                onChange={(event) => setPosition(event.target.value)}
                required
                className="w-24"
              />
            </div>
            <div className="space-y-1">
              <Label
                htmlFor={`question-status-${question.id}`}
                className="block text-xs"
              >
                Estado {question.id}
              </Label>
              <Select
                id={`question-status-${question.id}`}
                value={status}
                onChange={(event) => setStatus(event.target.value as InterviewQuestionStatus)}
                className="w-auto"
              >
                {EDITABLE_STATUSES.map((option) => (
                  <option key={option} value={option}>
                    {STATUS_LABELS[option]}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? "Guardando…" : "Guardar pregunta"}
          </Button>
        </form>
      ) : null}

      {feedbackOpen ? (
        <FeedbackForm questionId={question.id} requirementId={question.requirement_id} />
      ) : null}

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {notice}
      </p>
      {error ? <ErrorNotice error={error} /> : null}
    </Card>
  );
}

interface QuestionEditorProps {
  guideId: string;
  questions: InterviewQuestion[];
  modelVersion: string | null;
  promptVersion: string | null;
  onChanged?: (question: InterviewQuestion) => void;
}

export function QuestionEditor({
  guideId,
  questions,
  modelVersion,
  promptVersion,
  onChanged,
}: QuestionEditorProps) {
  const [requirementId, setRequirementId] = useState("");
  const [position, setPosition] = useState(String(questions.length + 1));
  const [category, setCategory] = useState<InterviewQuestionCategory>("technical");
  const [question, setQuestion] = useState("");
  const [evidenceFocus, setEvidenceFocus] = useState("");
  const [competency, setCompetency] = useState("");
  const [reviewRequired, setReviewRequired] = useState(false);
  const [newModelVersion, setNewModelVersion] = useState(modelVersion ?? "");
  const [newPromptVersion, setNewPromptVersion] = useState(promptVersion ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; reasonCode?: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function create(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError(null);
    setNotice(null);
    const payload: InterviewQuestionCreateRequest = {
      requirement_id: requirementId.trim(),
      position: Number(position),
      category,
      question: question.trim(),
      evidence_focus: evidenceFocus.trim(),
      competency: competency.trim(),
      review_required: reviewRequired,
      model_version: newModelVersion.trim(),
      prompt_version: newPromptVersion.trim(),
    };
    try {
      const created = await requestQuestion<InterviewQuestion>(
        `/api/v1/interviews/guides/${encodeURIComponent(guideId)}/questions`,
        "POST",
        payload,
      );
      setNotice("Pregunta agregada.");
      setQuestion("");
      setEvidenceFocus("");
      setCompetency("");
      setPosition(String(created.position + 1));
      onChanged?.(created);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="question-editor-heading" className="space-y-3">
      <div className="space-y-1">
        <h3 id="question-editor-heading" className="text-base font-semibold">
          Preguntas
        </h3>
        <p className="text-xs text-text-muted">
          Cada pregunta queda vinculada a un requisito; la política se valida en el servidor.
        </p>
      </div>

      {questions.length > 0 ? (
        <ul className="space-y-3">
          {questions.map((item) => (
            <li key={item.id}>
              <QuestionRow question={item} onChanged={onChanged} />
            </li>
          ))}
        </ul>
      ) : (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          La guía todavía no tiene preguntas registradas.
        </Card>
      )}

      <form onSubmit={(event) => void create(event)} className="space-y-2">
        <Card className="space-y-2 p-3">
          <h4 className="text-sm font-semibold">Agregar pregunta</h4>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="new-question-requirement" className="block text-xs">
                ID de requisito
              </Label>
              <Input
                id="new-question-requirement"
                value={requirementId}
                onChange={(event) => setRequirementId(event.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-question-position" className="block text-xs">
                Posición
              </Label>
              <Input
                id="new-question-position"
                type="number"
                min={1}
                value={position}
                onChange={(event) => setPosition(event.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-question-category" className="block text-xs">
                Categoría
              </Label>
              <Select
                id="new-question-category"
                value={category}
                onChange={(event) => setCategory(event.target.value as InterviewQuestionCategory)}
              >
                {(Object.keys(CATEGORY_LABELS) as InterviewQuestionCategory[]).map((option) => (
                  <option key={option} value={option}>
                    {CATEGORY_LABELS[option]}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-question-competency" className="block text-xs">
                Competencia
              </Label>
              <Input
                id="new-question-competency"
                value={competency}
                onChange={(event) => setCompetency(event.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-question-model" className="block text-xs">
                Versión del modelo
              </Label>
              <Input
                id="new-question-model"
                value={newModelVersion}
                onChange={(event) => setNewModelVersion(event.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-question-prompt" className="block text-xs">
                Versión del prompt
              </Label>
              <Input
                id="new-question-prompt"
                value={newPromptVersion}
                onChange={(event) => setNewPromptVersion(event.target.value)}
                required
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="new-question-text" className="block text-xs">
              Pregunta
            </Label>
            <Textarea
              id="new-question-text"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              required
              rows={2}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="new-question-focus" className="block text-xs">
              Foco de evidencia
            </Label>
            <Input
              id="new-question-focus"
              value={evidenceFocus}
              onChange={(event) => setEvidenceFocus(event.target.value)}
              required
            />
          </div>
          <Label htmlFor="new-question-review" className="flex items-center gap-2 text-sm">
            <input
              id="new-question-review"
              type="checkbox"
              checked={reviewRequired}
              onChange={(event) => setReviewRequired(event.target.checked)}
              className="h-4 w-4"
            />
            Requiere revisión humana
          </Label>
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? "Guardando…" : "Agregar pregunta"}
          </Button>
        </Card>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {notice}
      </p>
      {error ? <ErrorNotice error={error} /> : null}
    </section>
  );
}
