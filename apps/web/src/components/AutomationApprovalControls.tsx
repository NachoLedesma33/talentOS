"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  AutomationApproval,
  AutomationApprovalDecisionResult,
  AutomationApprovalStatus,
  AutomationDecisionRequest,
  AutomationRunDetail,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";

type Decision = Exclude<AutomationApprovalStatus, "pending">;

const STATUS_KEYS: Record<AutomationApprovalStatus, MessageKey> = {
  pending: "approval.status.pending",
  approved: "approval.status.approved",
  rejected: "approval.status.rejected",
};

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
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
  const { t } = useI18n();
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
      setNotice(
        `${t("approval.decisionRecorded")}${result.status === "approved" ? t("approval.decision.approved") : t("approval.decision.rejected")}.`,
      );
      onDecision?.(result);
      await onRefresh?.();
    } catch (cause) {
      setError(describeError(cause, t("approval.error")));
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
      const updated = await apiFetch<AutomationRunDetail>(
        `/api/v1/automations/runs/${encodeURIComponent(runId)}/cancel`,
        { method: "POST" },
      );
      onRunChange?.(updated);
      setNotice(t("approval.cancelled"));
      await onRefresh?.();
    } catch (cause) {
      setError(describeError(cause, t("approval.error")));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="automation-approvals-heading" aria-busy={isBusy} className="space-y-3">
      <div className="space-y-1">
        <h3 id="automation-approvals-heading" className="text-base font-semibold">
          {t("approval.title")}
        </h3>
        <p className="text-sm text-text-muted">{t("approval.noteAutomation")}</p>
      </div>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {notice ?? t("approval.noDecisionsView")}
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
            const current = confirmed[approval.id] ?? approval.status;
            const decided = approval.status !== "pending" || Boolean(confirmed[approval.id]);
            return (
              <li key={approval.id}>
                <Card className="space-y-2 p-3">
                  <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-text-muted">
                    <div>
                      <dt className="inline font-semibold">{t("approval.actionLabel")}</dt>
                      <dd className="inline">{approval.action_type}</dd>
                    </div>
                    <div>
                      <dt className="inline font-semibold">{t("approval.createdUtcLabel")}</dt>
                      <dd className="inline">{formatUtc(approval.created_at)}</dd>
                    </div>
                    <div>
                      <dt className="inline font-semibold">{t("approval.statusLabel")}</dt>
                      <dd className="inline">{t(STATUS_KEYS[current])}</dd>
                    </div>
                  </dl>

                  {decided ? (
                    <p role="status" className="text-sm text-text-muted">
                      {t("approval.decisionRecorded")}
                      {t(STATUS_KEYS[current])}
                      {t("approval.cannotRepeat")}
                    </p>
                  ) : (
                    <form
                      onSubmit={(event) => void decide(event, approval)}
                      className="flex flex-wrap items-end gap-3"
                    >
                      <div className="space-y-1">
                        <Label htmlFor={`automation-decision-${approval.id}`} className="block">
                          {t("approval.decisionFor")}
                          {approval.action_type}
                        </Label>
                        <Select
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
                        >
                          <option value="">{t("approval.selectDecision")}</option>
                          <option value="approved">{t("approval.approveAction")}</option>
                          <option value="rejected">{t("approval.rejectReview")}</option>
                        </Select>
                      </div>
                      <div className="min-w-48 flex-1 space-y-1">
                        <Label htmlFor={`automation-note-${approval.id}`} className="block">
                          {t("approval.noteFor")}
                          {approval.action_type}
                        </Label>
                        <Input
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
                        />
                      </div>
                      <Button
                        type="submit"
                        disabled={isBusy || !selections[approval.id]}
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
          onClick={() => void cancel()}
          disabled={isBusy || !runId}
        >
          {busy === "cancel" ? t("approval.cancelling") : t("approval.cancel")}
        </Button>
      </div>
    </section>
  );
}
