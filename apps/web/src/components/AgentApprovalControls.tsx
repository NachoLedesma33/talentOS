"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n } from "../lib/i18n";
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

function describeError(cause: unknown, t: (key: "approval.error" | "approval.brokerError") => string): string {
  if (cause instanceof ApiError) {
    if (cause.code === "broker_unavailable") {
      return t("approval.brokerError");
    }
    return `${cause.status}: ${cause.message}`;
  }
  return t("approval.error");
}

function decisionLabel(
  decision: Decision | Approval["status"],
  t: (key: "approval.decision.pending" | "approval.decision.approved" | "approval.decision.rejected") => string,
): string {
  if (decision === "approved") return t("approval.decision.approved");
  if (decision === "rejected") return t("approval.decision.rejected");
  return t("approval.decision.pending");
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
  const { t } = useI18n();
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
      setNotice(`${t("approval.decisionRecorded")}${decisionLabel(decision, t)}.`);
      await onRefresh?.();
    } catch (cause) {
      setError(describeError(cause, t));
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
        result.queued ? t("approval.resumeQueued") : t("approval.resumeRequested"),
      );
      await onRefresh?.();
    } catch (cause) {
      setError(describeError(cause, t));
    } finally {
      setBusy(null);
    }
  }

  async function cancel() {
    if (!runId || isBusy) return;
    if (!window.confirm(t("approval.cancelConfirm"))) return;

    setBusy("cancel");
    setError(null);
    setNotice(null);
    try {
      const updated = await apiFetch<AgentRun>(
        `/api/v1/agents/runs/${encodeURIComponent(runId)}/cancel`,
        { method: "POST" },
      );
      onRunChange?.(updated);
      setNotice(t("approval.cancelled"));
      await onRefresh?.();
    } catch (cause) {
      setError(describeError(cause, t));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="agent-approvals-heading" aria-busy={isBusy} className="space-y-3">
      <div className="space-y-1">
        <h3 id="agent-approvals-heading" className="text-base font-semibold">
          {t("approval.title")}
        </h3>
        <p className="text-sm text-text-muted">{t("approval.noteAgent")}</p>
      </div>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {notice ?? (hasPersistedDecision ? t("approval.persisted") : t("approval.noDecisions"))}
      </p>
      {error ? (
        <Card role="alert" className="p-3 text-sm">
          {error}
        </Card>
      ) : null}

      {approvals.length === 0 ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          {t("approval.empty")}
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
                      <dt className="inline font-semibold">{t("approval.actionLabel")}</dt>
                      <dd className="inline">{approval.action_type}</dd>
                    </div>
                    <div>
                      <dt className="inline font-semibold">{t("approval.createdLabel")}</dt>
                      <dd className="inline">{approval.created_at}</dd>
                    </div>
                    <div>
                      <dt className="inline font-semibold">{t("approval.statusLabel")}</dt>
                      <dd className="inline">{decisionLabel(current, t)}</dd>
                    </div>
                  </dl>

                  {decided ? (
                    <p role="status" className="text-sm text-text-muted">
                      {t("approval.decisionRecorded")}
                      {decisionLabel(current, t)}
                      {t("approval.cannotRepeat")}
                    </p>
                  ) : (
                    <form
                      onSubmit={(event) => void decide(event, approval)}
                      className="flex flex-wrap items-end gap-3"
                    >
                      <div className="space-y-1">
                        <Label htmlFor={`approval-decision-${approval.id}`} className="block">
                          {t("approval.decisionFor")}
                          {approval.action_type}
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
                          <option value="approved">{t("approval.approveSend")}</option>
                          <option value="rejected">{t("approval.rejectReview")}</option>
                        </Select>
                      </div>
                      <div className="min-w-48 flex-1 space-y-1">
                        <Label htmlFor={`approval-note-${approval.id}`} className="block">
                          {t("approval.noteFor")}
                          {approval.action_type}
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
                        aria-label={`${t("approval.registerFor")}${approval.action_type}`}
                      >
                        {busy === `decide:${approval.id}`
                          ? t("approval.registering")
                          : t("approval.register")}
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
          {busy === "resume" ? t("approval.resuming") : t("approval.resume")}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void cancel()}
          disabled={isBusy || !runId}
        >
          {busy === "cancel" ? t("approval.cancelling") : t("approval.cancel")}
        </Button>
        {!hasPersistedDecision ? (
          <p className="text-sm text-text-muted">{t("approval.resumeHint")}</p>
        ) : null}
      </div>
    </section>
  );
}
