"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
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

const MIN_PANEL_HEIGHT = 240;
const DEFAULT_PANEL_HEIGHT = 360;
const MAX_PANEL_HEIGHT = 720;
const RESIZE_STEP = 24;

const COPY = {
  es: {
    title: "Mensajes",
    regionTitle: "Asistente del workspace",
    avatar: "Asistente en línea",
    moreOptions: "Más opciones",
    newMessage: "Nuevo mensaje",
    expand: "Expandir chat",
    collapse: "Colapsar chat",
    resize: "Redimensionar chat",
    conversation: "Conversación",
    you: "Tú",
    assistantLabel: "Asistente",
    newConversation: "Nueva conversación iniciada.",
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
    title: "Messages",
    regionTitle: "Workspace assistant",
    avatar: "Assistant online",
    moreOptions: "More options",
    newMessage: "New message",
    expand: "Expand chat",
    collapse: "Collapse chat",
    resize: "Resize chat",
    conversation: "Conversation",
    you: "You",
    assistantLabel: "Assistant",
    newConversation: "New conversation started.",
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

function BotIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="size-5">
      <rect x="5" y="8" width="14" height="11" rx="3" />
      <path d="M12 8V5M9 5h6" strokeLinecap="round" />
      <circle cx="9" cy="13" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="13" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

function DotsIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="currentColor" className="size-4">
      <circle cx="5" cy="12" r="1.6" />
      <circle cx="12" cy="12" r="1.6" />
      <circle cx="19" cy="12" r="1.6" />
    </svg>
  );
}

function ComposeIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className="size-4">
      <path d="M4 20h4l10-10-4-4L4 16v4Z" />
      <path d="m13.5 6.5 4 4" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="size-4">
      <path d="m6 15 6-6 6 6" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className="size-4">
      <path d="M4 12 20 4l-4 16-4-6-8-2Z" />
      <path d="m12 14 8-10" />
    </svg>
  );
}

function GripIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 16 16" fill="currentColor" className="size-4">
      <circle cx="6" cy="4" r="1" />
      <circle cx="10" cy="4" r="1" />
      <circle cx="6" cy="8" r="1" />
      <circle cx="10" cy="8" r="1" />
      <circle cx="6" cy="12" r="1" />
      <circle cx="10" cy="12" r="1" />
    </svg>
  );
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
  const { locale, t } = useI18n();
  const copy = COPY[locale];
  const [expanded, setExpanded] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
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
  const [panelHeight, setPanelHeight] = useState(DEFAULT_PANEL_HEIGHT);
  const [maxPanelHeight, setMaxPanelHeight] = useState(MAX_PANEL_HEIGHT);
  const resizeRef = useRef<{ pointerId: number; startY: number; startHeight: number } | null>(null);

  useEffect(() => {
    const updateLimit = () => {
      setMaxPanelHeight(
        Math.max(MIN_PANEL_HEIGHT, Math.min(MAX_PANEL_HEIGHT, window.innerHeight - 160)),
      );
    };
    updateLimit();
    window.addEventListener("resize", updateLimit);
    return () => window.removeEventListener("resize", updateLimit);
  }, []);

  const effectiveHeight = Math.min(panelHeight, maxPanelHeight);

  function clampHeight(value: number): number {
    return Math.round(Math.min(Math.max(value, MIN_PANEL_HEIGHT), maxPanelHeight));
  }

  function startResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (!expanded) return;
    event.preventDefault();
    event.currentTarget.focus();
    resizeRef.current = {
      pointerId: event.pointerId,
      startY: event.clientY,
      startHeight: effectiveHeight,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function moveResize(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = resizeRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setPanelHeight(clampHeight(drag.startHeight + (drag.startY - event.clientY)));
  }

  function stopResize(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = resizeRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    resizeRef.current = null;
  }

  function resizeWithKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (!expanded) return;
    let next: number | null = null;
    if (event.key === "ArrowUp") next = effectiveHeight + RESIZE_STEP;
    if (event.key === "ArrowDown") next = effectiveHeight - RESIZE_STEP;
    if (event.key === "Home") next = MIN_PANEL_HEIGHT;
    if (event.key === "End") next = maxPanelHeight;
    if (next === null) return;
    event.preventDefault();
    setPanelHeight(clampHeight(next));
  }

  function startNewConversation() {
    setMessage("");
    setHistory([]);
    setResponse(null);
    setError(null);
    setNotice(copy.newConversation);
    setConfirmDiscard(null);
    setOptionsOpen(false);
    keyRef.current = "";
    attemptRef.current = 0;
  }

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
      aria-label={copy.regionTitle}
      aria-busy={submitting || ackPending !== null}
      className={`fixed bottom-0 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col border border-border bg-surface shadow-lg sm:right-6 ${
        expanded ? "rounded-t-xl" : "rounded-xl"
      }`}
    >
      <div className="flex shrink-0 items-center gap-2 rounded-t-xl border-b border-border-subtle bg-surface px-3 py-2">
        <div
          role="separator"
          aria-label={copy.resize}
          aria-orientation="horizontal"
          aria-valuemin={MIN_PANEL_HEIGHT}
          aria-valuemax={maxPanelHeight}
          aria-valuenow={effectiveHeight}
          aria-controls={expanded ? "assistant-panel-body" : undefined}
          tabIndex={expanded ? 0 : -1}
          onPointerDown={startResize}
          onPointerMove={moveResize}
          onPointerUp={stopResize}
          onPointerCancel={stopResize}
          onKeyDown={resizeWithKeyboard}
          className={`flex size-8 shrink-0 touch-none items-center justify-center rounded text-text-muted outline-none focus-visible:ring-2 focus-visible:ring-accent ${
            expanded ? "cursor-ns-resize" : "cursor-default opacity-50"
          }`}
        >
          <GripIcon />
        </div>
        <span
          role="img"
          aria-label={copy.avatar}
          className="relative flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent"
        >
          <BotIcon />
          <span
            aria-hidden="true"
            className="absolute bottom-0 right-0 size-2.5 rounded-full bg-success ring-2 ring-surface"
          />
        </span>
        <h3 id="assistant-panel-heading" className="text-sm font-semibold">
          {copy.title}
        </h3>
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={copy.moreOptions}
            aria-expanded={optionsOpen}
            aria-controls={optionsOpen ? "assistant-panel-options" : undefined}
            onClick={() => setOptionsOpen((open) => !open)}
            className="size-8"
          >
            <DotsIcon />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={copy.newMessage}
            disabled={submitting || ackPending !== null}
            onClick={startNewConversation}
            className="size-8"
          >
            <ComposeIcon />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={expanded ? copy.collapse : copy.expand}
            aria-expanded={expanded}
            aria-controls={expanded ? "assistant-panel-body" : undefined}
            onClick={() => setExpanded((open) => !open)}
            className="size-8"
          >
            <span className={`transition-transform motion-reduce:transition-none ${expanded ? "rotate-180" : ""}`}>
              <ChevronIcon />
            </span>
          </Button>
        </div>
      </div>

      {optionsOpen && (
        <div id="assistant-panel-options" className="space-y-1 border-b border-border-subtle bg-surface-muted px-3 py-2 text-xs text-text-muted">
          <p>{copy.description}</p>
          <p>{t("assistant.note")}</p>
        </div>
      )}

      {expanded && (
        <div
          id="assistant-panel-body"
          className="flex flex-col"
          style={{ height: `${effectiveHeight}px`, maxHeight: `${maxPanelHeight}px` }}
        >
          <div
            role="log"
            aria-label={copy.conversation}
            className="min-h-24 flex-1 space-y-3 overflow-y-auto px-3 py-3"
          >
            <p aria-live="polite" className="text-xs text-text-muted">
              {notice}
            </p>

            {error !== null && (
              <Card role="alert" className="border-destructive p-3 text-sm">
                {error}
              </Card>
            )}

            {history.length === 0 ? (
              <Card className="bg-secondary p-3 text-sm text-text-muted">{copy.empty}</Card>
            ) : (
              history.map((entry, index) => (
                <div
                  key={`${entry.role}-${index}`}
                  className={`rounded-lg px-3 py-2 text-sm ${
                    entry.role === "user"
                      ? "ml-6 bg-accent text-on-accent"
                      : "mr-6 bg-secondary text-text"
                  }`}
                >
                  <p className="text-xs font-semibold opacity-80">
                    {entry.role === "user" ? copy.you : copy.assistantLabel}
                  </p>
                  <p className="whitespace-pre-wrap break-words">{entry.content}</p>
                </div>
              ))
            )}

            {response !== null && (
              <div className="space-y-3 border-t border-border-subtle pt-3">
                <p className="text-xs font-semibold text-text-muted">{copy.answer}</p>
                <p className="text-xs text-text-muted">{response.status}</p>

                <div className="space-y-2">
                  <h4 className="text-xs font-semibold">{copy.citations}</h4>
                  {response.citations.length === 0 ? (
                    <p className="text-xs text-text-muted">{copy.noCitations}</p>
                  ) : (
                    <ul className="space-y-2">
                      {response.citations.map((citation, index) => {
                        const source = citation.document_id ?? citation.candidate_id;
                        return (
                          <li key={`${source ?? "unverified"}-${index}`} className="rounded-md border border-border p-2 text-xs">
                            <blockquote className="border-l-2 border-border pl-2">{citation.quote}</blockquote>
                            <p className="mt-1 text-text-muted">
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
                  <Card className="space-y-1 bg-secondary p-3 text-xs">
                    <h4 className="font-semibold">{copy.limitations}</h4>
                    <ul className="list-disc pl-5">
                      {response.limitations.map((limitation, index) => (
                        <li key={`${limitation}-${index}`}>{limitation}</li>
                      ))}
                    </ul>
                  </Card>
                )}

                {response.unsupported_reason !== null && (
                  <Card role="status" className="p-3 text-xs">
                    {copy.unsupported}: {response.unsupported_reason}
                  </Card>
                )}

                <div className="space-y-2">
                  <h4 className="text-xs font-semibold">{copy.actions}</h4>
                  {!canDecide && <p className="text-xs text-text-muted">{copy.locked}</p>}
                  {actions.length === 0 ? (
                    <p className="text-xs text-text-muted">{copy.noActions}</p>
                  ) : (
                    <ul className="space-y-2">
                      {actions.map((action) => (
                        <li key={action.action_id} className="space-y-2 rounded-md border border-border p-3 text-xs">
                          <p className="font-medium">{action.type}</p>
                          {action.route !== null && action.route !== undefined && (
                            <p className="text-text-muted">{action.route}</p>
                          )}
                          {action.form_id !== null && action.form_id !== undefined && (
                            <p className="text-text-muted">{action.form_id}</p>
                          )}
                          {confirmDiscard === action.action_id ? (
                            <Card className="space-y-2 p-2">
                              <p>{copy.confirmQuestion}</p>
                              <div className="flex flex-wrap gap-2">
                                <Button
                                  type="button"
                                  variant="destructive"
                                  size="sm"
                                  disabled={ackPending !== null}
                                  onClick={() => void ack(action.action_id, "discarded")}
                                >
                                  {copy.confirmDiscard}
                                </Button>
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
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
                                size="sm"
                                disabled={!canDecide || !action.requires_confirmation || ackPending !== null}
                                onClick={() => void ack(action.action_id, "applied")}
                              >
                                {copy.apply}
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
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
          </div>

          <form onSubmit={send} className="shrink-0 border-t border-border-subtle p-3">
            <Label htmlFor="assistant-panel-message" className="sr-only">
              {copy.label}
            </Label>
            <div className="flex items-end gap-2">
              <Textarea
                id="assistant-panel-message"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder={copy.placeholder}
                disabled={submitting}
                maxLength={2000}
                rows={1}
                className="min-h-10 max-h-28 resize-none"
              />
              <Button
                type="submit"
                size="icon"
                aria-label={submitting ? copy.sending : copy.send}
                disabled={submitting || message.trim().length === 0}
              >
                <SendIcon />
              </Button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
