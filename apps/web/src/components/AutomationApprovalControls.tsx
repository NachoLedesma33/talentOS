"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  AutomationApproval,
  AutomationApprovalDecisionResult,
  AutomationApprovalStatus,
  AutomationDecisionRequest,
  AutomationRunDetail,
} from "../lib/types";

type Decision = Exclude<AutomationApprovalStatus, "pending">;

const STATUS_LABELS: Record<AutomationApprovalStatus, string> = {
  pending: "Pendiente",
  approved: "Aprobada",
  rejected: "Rechazada",
};

function describeError(cause: unknown): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return "No se pudo completar la acción.";
}

function formatUtc(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

export function AutomationApprovalControls({
  runId,
  approvals,
  onDecision,
  onRunChange,
  onRefresh,
}: {
  runId: string | null;
  approvals: AutomationApproval[];
  onDecision?: (result: AutomationApprovalDecisionResult) => void;
  onRunChange?: (run: AutomationRunDetail) => void;
  onRefresh?: () => Promise<void> | void;
}) {
  const [selections, setSelections] = useState<Record<string, Decision | "">>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState<Record<string, Decision>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const isBusy = busy !== null;

  async function decide(event: FormEvent<HTMLFormElement>, approval: AutomationApproval) {
    event.preventDefault();
    const decision = selections[approval.id];
    if (!runId || isBusy || approval.status !== "pending" || confirmed[approval.id] || !decision) {
      return;
    }

    const body: AutomationDecisionRequest = {
      decision,
      note: notes[approval.id]?.trim() || null,
    };
    setBusy(`decide:${approval.id}`);
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<AutomationApprovalDecisionResult>(
        `/api/v1/automations/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approval.id)}/decide`,
        { method: "POST", body: JSON.stringify(body) },
      );
      setConfirmed((current) => ({ ...current, [approval.id]: decision }));
      setNotice(`Decisión registrada: ${result.status === "approved" ? "aprobada" : "rechazada"}.`);
      onDecision?.(result);
      await onRefresh?.();
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(null);
    }
  }

  async function cancel() {
    if (!runId || isBusy) return;
    if (!window.confirm("¿Cancelar la ejecución? Esta acción no se puede deshacer.")) return;

    setBusy("cancel");
    setError(null);
    setNotice(null);
    try {
      const updated = await apiFetch<AutomationRunDetail>(
        `/api/v1/automations/runs/${encodeURIComponent(runId)}/cancel`,
        { method: "POST" },
      );
      onRunChange?.(updated);
      setNotice("Ejecución cancelada.");
      await onRefresh?.();
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="automation-approvals-heading" aria-busy={isBusy} className="space-y-3">
      <div className="space-y-1">
        <h3 id="automation-approvals-heading" className="text-base font-semibold">
          Aprobaciones humanas
        </h3>
        <p className="text-sm text-text-muted">
          La decisión la valida y persiste el servidor. No se aprueba ni se reanuda nada
          automáticamente.
        </p>
      </div>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {notice ?? "Sin decisiones registradas en esta vista."}
      </p>
      {error ? (
        <p role="alert" className="rounded-sm border border-border p-3 text-sm">
          {error}
        </p>
      ) : null}

      {approvals.length === 0 ? (
        <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
          No hay aprobaciones para esta ejecución.
        </p>
      ) : (
        <ul className="space-y-3">
          {approvals.map((approval) => {
            const current = confirmed[approval.id] ?? approval.status;
            const decided = approval.status !== "pending" || Boolean(confirmed[approval.id]);
            return (
              <li key={approval.id} className="space-y-2 rounded-sm border border-border p-3">
                <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-text-muted">
                  <div>
                    <dt className="inline font-semibold">Acción: </dt>
                    <dd className="inline">{approval.action_type}</dd>
                  </div>
                  <div>
                    <dt className="inline font-semibold">Creada UTC: </dt>
                    <dd className="inline">{formatUtc(approval.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="inline font-semibold">Estado: </dt>
                    <dd className="inline">{STATUS_LABELS[current]}</dd>
                  </div>
                </dl>

                {decided ? (
                  <p role="status" className="text-sm text-text-muted">
                    Decisión registrada: {STATUS_LABELS[current]}. No se puede repetir.
                  </p>
                ) : (
                  <form
                    onSubmit={(event) => void decide(event, approval)}
                    className="flex flex-wrap items-end gap-3"
                  >
                    <div className="space-y-1">
                      <label
                        htmlFor={`automation-decision-${approval.id}`}
                        className="block text-sm font-semibold"
                      >
                        Decisión para {approval.action_type}
                      </label>
                      <select
                        id={`automation-decision-${approval.id}`}
                        value={selections[approval.id] ?? ""}
                        onChange={(event) =>
                          setSelections((currentState) => ({
                            ...currentState,
                            [approval.id]: event.target.value as Decision | "",
                          }))
                        }
                        disabled={isBusy}
                        required
                        className="rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                      >
                        <option value="">Selecciona decisión</option>
                        <option value="approved">Aprobar acción</option>
                        <option value="rejected">Rechazar y devolver a revisión</option>
                      </select>
                    </div>
                    <div className="min-w-48 flex-1 space-y-1">
                      <label
                        htmlFor={`automation-note-${approval.id}`}
                        className="block text-sm font-semibold"
                      >
                        Nota opcional para {approval.action_type}
                      </label>
                      <input
                        id={`automation-note-${approval.id}`}
                        value={notes[approval.id] ?? ""}
                        onChange={(event) =>
                          setNotes((currentState) => ({
                            ...currentState,
                            [approval.id]: event.target.value,
                          }))
                        }
                        maxLength={500}
                        disabled={isBusy}
                        className="w-full rounded-sm border border-border bg-surface px-2 py-2 text-sm"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={isBusy || !selections[approval.id]}
                      aria-label={`Registrar decisión para ${approval.action_type}`}
                      className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-on-accent disabled:opacity-60"
                    >
                      {busy === `decide:${approval.id}` ? "Registrando…" : "Registrar decisión"}
                    </button>
                  </form>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void cancel()}
          disabled={isBusy || !runId}
          className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:opacity-60"
        >
          {busy === "cancel" ? "Cancelando…" : "Cancelar ejecución"}
        </button>
      </div>
    </section>
  );
}
