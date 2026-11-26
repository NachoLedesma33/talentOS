"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  AgentApprovalDecision,
  AgentResumeResponse,
  AgentRun,
  Approval,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";

type Decision = AgentApprovalDecision["decision"];

function describeError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === "broker_unavailable") {
      return "broker no disponible, sin cambios.";
    }
    return `${cause.status}: ${cause.message}`;
  }
  return "No se pudo completar la acción.";
}

function decisionLabel(decision: Decision | Approval["status"]): string {
  if (decision === "approved") return "aprobada";
  if (decision === "rejected") return "rechazada";
  return "pendiente";
}

export function AgentApprovalControls({
  runId,
  approvals,
  onRunChange,
  onRefresh,
}: {
  runId: string | null;
  approvals: Approval[];
  onRunChange?: (run: AgentRun) => void;
  onRefresh?: () => Promise<void> | void;
}) {
  const [selections, setSelections] = useState<Record<string, Decision>>({});
  const [confirmed, setConfirmed] = useState<Record<string, Decision>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const isBusy = busy !== null;
  const confirmedIds = Object.keys(confirmed);
  const hasPersistedDecision =
    confirmedIds.length > 0 || approvals.some((item) => item.status !== "pending");

  async function decide(event: FormEvent<HTMLFormElement>, approval: Approval) {
    event.preventDefault();
    if (!runId || isBusy) return;

    const decision = selections[approval.id] ?? "approved";
    const noteValue = notes[approval.id]?.trim() ?? "";
    const body: AgentApprovalDecision = {
      decision,
      note: noteValue ? noteValue : null,
    };
    setBusy(`decide:${approval.id}`);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiFetch<AgentRun>(
        `/api/v1/agents/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approval.id)}/decide`,
        { method: "POST", body: JSON.stringify(body) },
      );
      setConfirmed((current) => ({ ...current, [approval.id]: decision }));
      onRunChange?.(updated);
      setNotice(`Decisión registrada: ${decisionLabel(decision)}.`);
      await onRefresh?.();
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(null);
    }
  }

  async function resume() {
    if (!runId || isBusy || !hasPersistedDecision) return;
    setBusy("resume");
    setError(null);
    setNotice(null);
    try {
      const result = await apiFetch<AgentResumeResponse>(
        `/api/v1/agents/runs/${encodeURIComponent(runId)}/resume`,
        { method: "POST" },
      );
      setNotice(
        result.queued
          ? "Reanudación encolada (queued). El estado final lo confirma el servidor."
          : "Reanudación solicitada; sin confirmación de encolado.",
      );
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
      const updated = await apiFetch<AgentRun>(
        `/api/v1/agents/runs/${encodeURIComponent(runId)}/cancel`,
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
    <section aria-labelledby="agent-approvals-heading" aria-busy={isBusy} className="space-y-3">
      <div className="space-y-1">
        <h3 id="agent-approvals-heading" className="text-base font-semibold">
          Aprobaciones humanas
        </h3>
        <p className="text-sm text-text-muted">
          Las decisiones se registran en el servidor; la reanudación requiere una decisión previa.
        </p>
      </div>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {notice ?? (hasPersistedDecision ? "Decisión persistida disponible." : "Sin decisiones registradas.")}
      </p>
      {error ? (
        <Card role="alert" className="p-3 text-sm">
          {error}
        </Card>
      ) : null}

      {approvals.length === 0 ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          No hay aprobaciones para esta ejecución.
        </Card>
      ) : (
        <ul className="space-y-3">
          {approvals.map((approval) => {
            const decided = approval.status !== "pending" || Boolean(confirmed[approval.id]);
            const current = confirmed[approval.id] ?? approval.status;
            return (
              <li key={approval.id}>
                <Card className="space-y-2 p-3">
                  <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-text-muted">
                    <div>
                      <dt className="inline font-semibold">Acción: </dt>
                      <dd className="inline">{approval.action_type}</dd>
                    </div>
                    <div>
                      <dt className="inline font-semibold">Creada: </dt>
                      <dd className="inline">{approval.created_at}</dd>
                    </div>
                    <div>
                      <dt className="inline font-semibold">Estado: </dt>
                      <dd className="inline">{decisionLabel(current)}</dd>
                    </div>
                  </dl>

                  {decided ? (
                    <p role="status" className="text-sm text-text-muted">
                      Decisión registrada: {decisionLabel(current)}. No se puede repetir.
                    </p>
                  ) : (
                    <form
                      onSubmit={(event) => void decide(event, approval)}
                      className="flex flex-wrap items-end gap-3"
                    >
                      <div className="space-y-1">
                        <Label htmlFor={`approval-decision-${approval.id}`} className="block">
                          Decisión para {approval.action_type}
                        </Label>
                        <Select
                          id={`approval-decision-${approval.id}`}
                          value={selections[approval.id] ?? "approved"}
                          onChange={(event) =>
                            setSelections((current) => ({
                              ...current,
                              [approval.id]: event.target.value as Decision,
                            }))
                          }
                          disabled={isBusy}
                        >
                          <option value="approved">Aprobar envío</option>
                          <option value="rejected">Rechazar y devolver a revisión</option>
                        </Select>
                      </div>
                      <div className="min-w-48 flex-1 space-y-1">
                        <Label htmlFor={`approval-note-${approval.id}`} className="block">
                          Nota opcional para {approval.action_type}
                        </Label>
                        <Input
                          id={`approval-note-${approval.id}`}
                          value={notes[approval.id] ?? ""}
                          onChange={(event) =>
                            setNotes((current) => ({
                              ...current,
                              [approval.id]: event.target.value,
                            }))
                          }
                          maxLength={500}
                          disabled={isBusy}
                        />
                      </div>
                      <Button
                        type="submit"
                        disabled={isBusy}
                        aria-label={`Registrar decisión para ${approval.action_type}`}
                      >
                        {busy === `decide:${approval.id}` ? "Registrando…" : "Registrar decisión"}
                      </Button>
                    </form>
                  )}
                </Card>
              </li>
            );
          })}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={() => void resume()}
          disabled={isBusy || !hasPersistedDecision || !runId}
        >
          {busy === "resume" ? "Encolando…" : "Reanudar ejecución"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void cancel()}
          disabled={isBusy || !runId}
        >
          {busy === "cancel" ? "Cancelando…" : "Cancelar ejecución"}
        </Button>
        {!hasPersistedDecision ? (
          <p className="text-sm text-text-muted">Registra una decisión antes de reanudar.</p>
        ) : null}
      </div>
    </section>
  );
}
