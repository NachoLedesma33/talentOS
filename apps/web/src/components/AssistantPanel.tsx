"use client";

import { useRef, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Label } from "./ui/shadcn/label";
import { Textarea } from "./ui/shadcn/textarea";

export type AssistantSurface =
  | "dashboard"
  | "jobs"
  | "candidates"
  | "applications"
  | "assessment"
  | "interviews"
  | "documents"
  | "automations"
  | "integrations"
  | "analytics"
  | "agents";

type AssistantStatus =
  | "pending"
  | "completed"
  | "needs_review"
  | "waiting_approval"
  | "failed";

interface AssistantSnapshot {
  role: "user" | "assistant";
  content: string;
}

interface AssistantCitation {
  quote: string;
  organization_id: string;
  document_id?: string | null;
  candidate_id?: string | null;
  page?: number | null;
}

interface AssistantAction {
  action_id: string;
  type: string;
  form_id?: string | null;
  route?: string | null;
  patch: Record<string, unknown>;
  field_origins: Record<string, string>;
  requires_confirmation: boolean;
}

interface AssistantResponse {
  run_id: string;
  answer: string;
  status: AssistantStatus;
  citations: AssistantCitation[];
  proposed_actions: AssistantAction[];
  limitations: string[];
  unsupported_reason: string | null;
}

export interface AssistantPanelProps {
  surface?: AssistantSurface;
  resourceRef?: string;
  idempotencyKey?: string;
}

const COPY = {
  es: {
    title: "Asistente del workspace",
    description: "Pregunta sobre datos del workspace. Las acciones requieren confirmación.",
    label: "Pregunta para el asistente",
    placeholder: "Por ejemplo: ¿qué evidencia confirma este perfil?",
    send: "Consultar",
    sending: "Consultando…",
    empty: "Todavía no hay respuesta. Escribe una pregunta para empezar.",
    answer: "Respuesta",
    citations: "Evidencia",
    noCitations: "Sin evidencia verificable en esta respuesta.",
    document: "Documento",
    candidate: "Candidato",
    page: "Página",
    unverified: "Cita sin origen verificable",
    limitations: "Limitaciones",
    unsupported: "Motivo de no disponibilidad",
    actions: "Acciones propuestas",
    noActions: "No hay acciones propuestas.",
    apply: "Aplicar",
    discard: "Descartar",
    confirmDiscard: "Confirmar descarte",
    cancel: "Cancelar",
    confirmQuestion: "¿Descartar esta acción propuesta?",
    locked: "Las acciones solo se pueden decidir cuando la API marca aprobación pendiente.",
    ackSending: "Registrando decisión…",
    applied: "Decisión aplicada. La API confirmó el resultado.",
    discarded: "Acción descartada. La API confirmó el resultado.",
    error: "No se pudo completar la solicitud.",
  },
  en: {
    title: "Workspace assistant",
    description: "Ask about workspace data. Actions always require confirmation.",
    label: "Question for the assistant",
    placeholder: "For example: which evidence supports this profile?",
    send: "Ask",
    sending: "Asking…",
    empty: "No answer yet. Write a question to start.",
    answer: "Answer",
    citations: "Evidence",
    noCitations: "No verifiable evidence in this answer.",
    document: "Document",
    candidate: "Candidate",
    page: "Page",
    unverified: "Citation without verifiable source",
    limitations: "Limitations",
    unsupported: "Reason not available",
    actions: "Proposed actions",
    noActions: "No proposed actions.",
    apply: "Apply",
    discard: "Discard",
    confirmDiscard: "Confirm discard",
    cancel: "Cancel",
    confirmQuestion: "Discard this proposed action?",
    locked: "Actions can only be decided when the API reports a pending approval.",
    ackSending: "Recording decision…",
    applied: "Decision applied. The API confirmed the result.",
    discarded: "Action discarded. The API confirmed the result.",
    error: "The request could not be completed.",
  },
} as const;

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
}

function nextKey(seed: string | undefined, attempt: number): string {
  if (seed) {
    return (attempt === 0 ? seed : `${seed}-${attempt}`).slice(0, 100);
  }
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${attempt}`;
  return `assistant-${random}`.slice(0, 100);
}

function normalizeResponse(value: AssistantResponse): AssistantResponse {
  return {
    ...value,
    citations: Array.isArray(value.citations) ? value.citations : [],
    proposed_actions: Array.isArray(value.proposed_actions) ? value.proposed_actions : [],
    limitations: Array.isArray(value.limitations) ? value.limitations : [],
    unsupported_reason: value.unsupported_reason ?? null,
  };
}

export function AssistantPanel({
  surface = "dashboard",
  resourceRef,
  idempotencyKey,
}: AssistantPanelProps) {
  const { locale } = useI18n();
  const copy = COPY[locale];
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<AssistantSnapshot[]>([]);
  const [response, setResponse] = useState<AssistantResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [ackPending, setAckPending] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState<string | null>(null);
  const keyRef = useRef<string>("");
  const attemptRef = useRef(0);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = message.trim();
    if (!content || submitting) return;

    keyRef.current = nextKey(idempotencyKey, attemptRef.current++);
    setSubmitting(true);
    setError(null);
    setNotice(copy.sending);
    try {
      const body = {
        schema_version: "1.0",
        message: content,
        surface,
        resource_ref: resourceRef ?? null,
        recent_messages: history.slice(-8),
        idempotency_key: keyRef.current,
      };
      const result = await apiFetch<AssistantResponse>(
        "/api/v1/agents/assistant/messages",
        { method: "POST", body: JSON.stringify(body) },
      );
      const normalized = normalizeResponse(result);
      setResponse(normalized);
      setMessage("");
      const nextHistory: AssistantSnapshot[] = [
        ...history,
        { role: "user", content },
        { role: "assistant", content: normalized.answer },
      ];
      setHistory(nextHistory.slice(-8));
      setConfirmDiscard(null);
      setNotice(null);
    } catch (cause) {
      setError(describeError(cause, copy.error));
      setNotice(null);
    } finally {
      setSubmitting(false);
    }
  }

  async function ack(actionId: string, decision: "applied" | "discarded") {
    if (ackPending || !response) return;
    setAckPending(actionId);
    setError(null);
    setNotice(copy.ackSending);
    try {
      const body = {
        schema_version: "1.0",
        action_id: actionId,
        decision,
        idempotency_key: keyRef.current,
      };
      const result = await apiFetch<AssistantResponse>(
        `/api/v1/agents/assistant/actions/${encodeURIComponent(actionId)}/ack`,
        { method: "POST", body: JSON.stringify(body) },
      );
      setResponse(normalizeResponse(result));
      setConfirmDiscard(null);
      setNotice(decision === "applied" ? copy.applied : copy.discarded);
    } catch (cause) {
      setError(describeError(cause, copy.error));
      setNotice(null);
    } finally {
      setAckPending(null);
    }
  }

  const actions = response?.proposed_actions ?? [];
  const canDecide = response?.status === "waiting_approval";

  return (
    <section
      aria-labelledby="assistant-panel-heading"
      aria-busy={submitting || ackPending !== null}
      className="space-y-3"
    >
      <div className="space-y-1">
        <h3 id="assistant-panel-heading" className="text-base font-semibold">
          {copy.title}
        </h3>
        <p className="text-sm text-text-muted">{copy.description}</p>
      </div>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {notice}
      </p>

      {error !== null && (
        <Card role="alert" className="border-destructive p-3 text-sm">
          {error}
        </Card>
      )}

      <form onSubmit={send} className="space-y-2">
        <Label htmlFor="assistant-panel-message">{copy.label}</Label>
        <Textarea
          id="assistant-panel-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={copy.placeholder}
          disabled={submitting}
          maxLength={2000}
        />
        <Button type="submit" disabled={submitting || message.trim().length === 0}>
          {submitting ? copy.sending : copy.send}
        </Button>
      </form>

      {response === null ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">{copy.empty}</Card>
      ) : (
        <div className="space-y-3">
          <Card className="space-y-1 p-3">
            <h4 className="text-sm font-semibold">{copy.answer}</h4>
            <p className="text-sm">{response.answer}</p>
            <p className="text-xs text-text-muted">{response.status}</p>
          </Card>

          <div className="space-y-2">
            <h4 className="text-sm font-semibold">{copy.citations}</h4>
            {response.citations.length === 0 ? (
              <p className="text-sm text-text-muted">{copy.noCitations}</p>
            ) : (
              <ul className="space-y-2">
                {response.citations.map((citation, index) => {
                  const source = citation.document_id ?? citation.candidate_id;
                  return (
                    <li key={`${source ?? "unverified"}-${index}`} className="rounded-md border border-border p-3 text-sm">
                      <blockquote className="border-l-2 border-border pl-2">{citation.quote}</blockquote>
                      <p className="mt-1 text-xs text-text-muted">
                        {source
                          ? [
                              citation.document_id ? `${copy.document}: ${citation.document_id}` : null,
                              citation.candidate_id ? `${copy.candidate}: ${citation.candidate_id}` : null,
                              citation.page ? `${copy.page}: ${citation.page}` : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")
                          : copy.unverified}
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {response.limitations.length > 0 && (
            <Card className="space-y-1 bg-secondary p-3 text-sm">
              <h4 className="font-semibold">{copy.limitations}</h4>
              <ul className="list-disc pl-5">
                {response.limitations.map((limitation, index) => (
                  <li key={`${limitation}-${index}`}>{limitation}</li>
                ))}
              </ul>
            </Card>
          )}

          {response.unsupported_reason !== null && (
            <Card role="status" className="p-3 text-sm">
              {copy.unsupported}: {response.unsupported_reason}
            </Card>
          )}

          <div className="space-y-2">
            <h4 className="text-sm font-semibold">{copy.actions}</h4>
            {!canDecide && <p className="text-sm text-text-muted">{copy.locked}</p>}
            {actions.length === 0 ? (
              <p className="text-sm text-text-muted">{copy.noActions}</p>
            ) : (
              <ul className="space-y-2">
                {actions.map((action) => (
                  <li key={action.action_id} className="space-y-2 rounded-md border border-border p-3 text-sm">
                    <p className="font-medium">{action.type}</p>
                    {action.route !== null && action.route !== undefined && (
                      <p className="text-xs text-text-muted">{action.route}</p>
                    )}
                    {action.form_id !== null && action.form_id !== undefined && (
                      <p className="text-xs text-text-muted">{action.form_id}</p>
                    )}
                    {confirmDiscard === action.action_id ? (
                      <Card className="space-y-2 p-2">
                        <p>{copy.confirmQuestion}</p>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            type="button"
                            variant="destructive"
                            disabled={ackPending !== null}
                            onClick={() => void ack(action.action_id, "discarded")}
                          >
                            {copy.confirmDiscard}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={ackPending !== null}
                            onClick={() => setConfirmDiscard(null)}
                          >
                            {copy.cancel}
                          </Button>
                        </div>
                      </Card>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          disabled={!canDecide || !action.requires_confirmation || ackPending !== null}
                          onClick={() => void ack(action.action_id, "applied")}
                        >
                          {copy.apply}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          disabled={!canDecide || !action.requires_confirmation || ackPending !== null}
                          onClick={() => setConfirmDiscard(action.action_id)}
                        >
                          {copy.discard}
                        </Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
