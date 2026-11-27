"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  EmailApprovalStatus,
  EmailDeliveryStatus,
  EmailDraft,
  EmailDraftDetail,
  EmailDraftList,
  EmailTemplate,
  IntegrationList,
  IntegrationProvider,
  IntegrationStatus,
  IntegrationSummary,
  WebhookDelivery,
  WebhookDeliveryList,
  WebhookDeliveryStatus,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/shadcn/table";

const PAGE_SIZE = 20;

const PROVIDER_LABEL_KEYS: Record<IntegrationProvider, MessageKey> = {
  email_sandbox: "integrations.provider.emailSandbox",
  webhook_outbound: "integrations.provider.webhookOutbound",
  webhook_inbound: "integrations.provider.webhookInbound",
};

const INTEGRATION_STATUS_LABEL_KEYS: Record<IntegrationStatus, MessageKey> = {
  active: "integrations.status.active",
  disabled: "integrations.status.disabled",
};

const DELIVERY_STATUS_LABEL_KEYS: Record<WebhookDeliveryStatus, MessageKey> = {
  pending: "integrations.delivery.pending",
  sending: "integrations.delivery.sending",
  delivered: "integrations.delivery.delivered",
  failed: "integrations.delivery.failed",
  dead_letter: "integrations.delivery.deadLetter",
};

const EMAIL_TEMPLATE_LABEL_KEYS: Record<EmailTemplate, MessageKey> = {
  initial_contact: "integrations.template.initialContact",
  interview_invite: "integrations.template.interviewInvite",
  follow_up: "integrations.template.followUp",
};

const APPROVAL_LABEL_KEYS: Record<EmailApprovalStatus, MessageKey> = {
  pending: "integrations.approval.pending",
  approved: "integrations.approval.approved",
  rejected: "integrations.approval.rejected",
};

const DELIVERY_LABEL_KEYS: Record<EmailDeliveryStatus, MessageKey> = {
  not_sent: "integrations.emailDelivery.notSent",
  sent: "integrations.emailDelivery.sent",
  failed: "integrations.emailDelivery.failed",
};

type DraftAction = "approve" | "reject" | "send";

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
}

function busyText(busy: string | null, t: (key: MessageKey) => string): string | null {
  if (!busy) return null;
  if (busy.startsWith("delivery:")) return t("integrations.busyRetryDelivery");
  if (busy.startsWith("draft:approve:")) return t("integrations.busyApproveDraft");
  if (busy.startsWith("draft:reject:")) return t("integrations.busyRejectDraft");
  if (busy.startsWith("draft:send:")) return t("integrations.busySendDraft");
  return null;
}

function requestIntegrationList(
  status: IntegrationStatus | "all",
  offset: number,
): Promise<IntegrationList> {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (status !== "all") params.set("status", status);
  return apiFetch<IntegrationList>(`/api/v1/integrations?${params.toString()}`);
}

function requestDeliveries(integrationId: string): Promise<WebhookDeliveryList> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: "0" });
  return apiFetch<WebhookDeliveryList>(
    `/api/v1/integrations/${encodeURIComponent(integrationId)}/deliveries?${params.toString()}`,
  );
}

function requestDrafts(integrationId: string): Promise<EmailDraftList> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: "0" });
  return apiFetch<EmailDraftList>(
    `/api/v1/integrations/${encodeURIComponent(integrationId)}/email-drafts?${params.toString()}`,
  );
}

export function IntegrationsPanel() {
  const { t } = useI18n();
  const [statusFilter, setStatusFilter] = useState<IntegrationStatus | "all">("all");
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<IntegrationList | null>(null);
  const [selected, setSelected] = useState<IntegrationSummary | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[] | null>(null);
  const [drafts, setDrafts] = useState<EmailDraft[] | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deliveriesError, setDeliveriesError] = useState<string | null>(null);
  const [draftsError, setDraftsError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const working = busy !== null || listLoading || detailLoading;
  const totalPages = list ? Math.max(1, Math.ceil(list.total / list.limit)) : 1;
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  async function loadList(
    nextStatus: IntegrationStatus | "all" = statusFilter,
    nextOffset = offset,
  ): Promise<void> {
    setListLoading(true);
    setError(null);
    setNotice(null);
    try {
      setList(await requestIntegrationList(nextStatus, nextOffset));
      setOffset(nextOffset);
    } catch (cause) {
      setError(describeError(cause, t("integrations.errorList")));
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    requestIntegrationList("all", 0).then(
      (result) => {
        if (active) setList(result);
      },
      (cause: unknown) => {
        if (active) {
          setError(describeError(cause, t("integrations.errorList")));
        }
      },
    ).finally(() => {
      if (active) setListLoading(false);
    });
    return () => {
      active = false;
    };
  }, [t]);

  async function selectIntegration(integration: IntegrationSummary): Promise<void> {
    if (busy) return;
    setSelected(integration);
    setDeliveries(null);
    setDrafts(null);
    setDeliveriesError(null);
    setDraftsError(null);
    setActionError(null);
    setNotice(null);

    const wantsDeliveries = integration.provider === "webhook_outbound";
    const wantsDrafts = integration.provider === "email_sandbox";
    if (!wantsDeliveries && !wantsDrafts) {
      setNotice(t("integrations.errorSelect"));
      return;
    }

    setDetailLoading(true);
    if (wantsDeliveries) {
      try {
        setDeliveries((await requestDeliveries(integration.id)).items);
      } catch (cause) {
        setDeliveriesError(describeError(cause, t("integrations.errorDeliveries")));
      }
    }
    if (wantsDrafts) {
      try {
        setDrafts((await requestDrafts(integration.id)).items);
      } catch (cause) {
        setDraftsError(describeError(cause, t("integrations.errorDrafts")));
      }
    }
    setDetailLoading(false);
  }

  async function retryDelivery(delivery: WebhookDelivery): Promise<void> {
    if (!selected || busy) return;
    setBusy(`delivery:${delivery.id}`);
    setActionError(null);
    setNotice(null);
    try {
      const updated = await apiFetch<WebhookDelivery>(
        `/api/v1/integrations/${encodeURIComponent(selected.id)}/deliveries/${encodeURIComponent(delivery.id)}/retry`,
        { method: "POST" },
      );
      setDeliveries((current) =>
        current?.map((item) => (item.id === updated.id ? updated : item)) ?? null,
      );
      setNotice(t("integrations.retryQueued"));
    } catch (cause) {
      setActionError(describeError(cause, t("integrations.errorRetry")));
    } finally {
      setBusy(null);
    }
  }

  async function decideDraft(draft: EmailDraft, action: DraftAction): Promise<void> {
    if (!selected || busy) return;
    setBusy(`draft:${action}:${draft.id}`);
    setActionError(null);
    setNotice(null);
    try {
      const updated = await apiFetch<EmailDraftDetail>(
        `/api/v1/integrations/${encodeURIComponent(selected.id)}/email-drafts/${encodeURIComponent(draft.id)}/${action}`,
        { method: "POST" },
      );
      setDrafts((current) =>
        current?.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)) ?? null,
      );
      setNotice(
        action === "approve"
          ? t("integrations.draftApproved")
          : action === "reject"
            ? t("integrations.draftRejected")
            : updated.delivery_status === "sent"
              ? t("integrations.draftSent")
              : t("integrations.draftSendRequested"),
      );
    } catch (cause) {
      setActionError(describeError(cause, t("integrations.errorDraftAction")));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="integrations-panel-heading" aria-busy={working} className="space-y-6">
      <div className="space-y-1">
        <h2 id="integrations-panel-heading" className="text-lg font-semibold">
          {t("integrations.heading")}
        </h2>
        <p className="text-sm text-text-muted">{t("integrations.intro")}</p>
      </div>

      <p role="status" aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {listLoading
          ? t("integrations.loadingList")
          : detailLoading
            ? t("integrations.loadingDiagnostics")
            : busyText(busy, t) ?? notice ?? ""}
      </p>

      {error ? (
        <Card role="alert" className="space-y-2 p-3">
          <p className="text-sm">{error}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => void loadList()}>
            {t("integrations.retry")}
          </Button>
        </Card>
      ) : null}

      {actionError ? (
        <Card role="alert" className="p-3 text-sm">
          {actionError}
        </Card>
      ) : null}

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="integration-status-filter" className="block">
            {t("integrations.filterStatus")}
          </Label>
          <Select
            id="integration-status-filter"
            value={statusFilter}
            onChange={(event) => {
              const next = event.target.value as IntegrationStatus | "all";
              setStatusFilter(next);
              void loadList(next, 0);
            }}
            disabled={working}
          >
            <option value="all">{t("integrations.filterAll")}</option>
            <option value="active">{t("integrations.status.active")}</option>
            <option value="disabled">{t("integrations.status.disabled")}</option>
          </Select>
        </div>
        <Button type="button" variant="outline" onClick={() => void loadList()} disabled={working}>
          {t("integrations.refresh")}
        </Button>
      </div>

      {list && list.items.length > 0 ? (
        <div className="space-y-2">
          <Table className="text-left">
            <TableCaption className="sr-only">{t("integrations.tableCaption")}</TableCaption>
            <TableHeader>
              <TableRow className="border-b border-border text-left">
                <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colProvider")}</TableHead>
                <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colStatus")}</TableHead>
                <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colConfigVersion")}</TableHead>
                <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colKeyId")}</TableHead>
                <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colCreated")}</TableHead>
                <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colUpdated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.items.map((item) => (
                <TableRow key={item.id} className="border-b border-border">
                  <TableCell className="px-2 py-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={working}
                      onClick={() => void selectIntegration(item)}
                      aria-current={item.id === selected?.id ? "true" : undefined}
                      aria-label={`${t("integrations.selectAria")}${item.provider}`}
                    >
                      {t(PROVIDER_LABEL_KEYS[item.provider])} · <code>{item.provider}</code>
                    </Button>
                  </TableCell>
                  <TableCell className="px-2 py-2">{t(INTEGRATION_STATUS_LABEL_KEYS[item.status])}</TableCell>
                  <TableCell className="px-2 py-2">{item.config_version}</TableCell>
                  <TableCell className="px-2 py-2"><code>{item.key_id}</code></TableCell>
                  <TableCell className="px-2 py-2">{item.created_at}</TableCell>
                  <TableCell className="px-2 py-2">{item.updated_at}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex flex-wrap items-center gap-3 text-sm text-text-muted">
            <span>
              {`${t("integrations.page")}${currentPage}${t("integrations.of")}${totalPages} · ${list.total}${t("integrations.records")}`}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={working || offset === 0}
              onClick={() => {
                const next = Math.max(0, offset - PAGE_SIZE);
                setOffset(next);
                void loadList(statusFilter, next);
              }}
            >
              {t("integrations.prevPage")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={working || offset + PAGE_SIZE >= list.total}
              onClick={() => {
                const next = offset + PAGE_SIZE;
                setOffset(next);
                void loadList(statusFilter, next);
              }}
            >
              {t("integrations.nextPage")}
            </Button>
          </div>
        </div>
      ) : list && !listLoading && !error ? (
        <Card className="bg-secondary p-3 text-sm text-text-muted">
          {t("integrations.empty")}
        </Card>
      ) : null}

      {selected ? (
        <div className="space-y-6">
          <section aria-labelledby="integration-detail-heading" className="space-y-3">
            <h3 id="integration-detail-heading" className="text-base font-semibold">
              {t(PROVIDER_LABEL_KEYS[selected.provider])} · <code>{selected.provider}</code>
            </h3>
            <Card className="p-3 text-sm">
              <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("integrations.detailStatus")}</dt>
                <dd className="inline">{t(INTEGRATION_STATUS_LABEL_KEYS[selected.status])}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">{t("integrations.detailConfigVersion")}</dt>
                <dd className="inline">{selected.config_version}</dd>
              </div>
                <div>
                  <dt className="text-xs font-semibold text-text-muted">{t("integrations.detailKeyId")}</dt>
                  <dd className="inline"><code>{selected.key_id}</code></dd>
                </div>
              </dl>
            </Card>
          </section>

          {selected.provider === "webhook_outbound" ? (
            <section aria-labelledby="deliveries-heading" className="space-y-2">
              <h3 id="deliveries-heading" className="text-base font-semibold">
                {t("integrations.deliveries")}
              </h3>
              {deliveriesError ? (
                <Card role="alert" className="p-3 text-sm">
                  {deliveriesError}
                </Card>
              ) : null}
              {deliveries && deliveries.length > 0 ? (
                <Table className="text-left text-sm">
                  <TableCaption className="sr-only">{t("integrations.deliveriesCaption")}</TableCaption>
                  <TableHeader>
                    <TableRow className="border-b border-border text-left">
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colEvent")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colStatus")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colAttempts")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colError")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colHttp")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colCreated")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colAction")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {deliveries.map((delivery) => (
                      <TableRow key={delivery.id} className="border-b border-border">
                        <TableCell className="px-2 py-2"><code>{delivery.event_type}</code></TableCell>
                        <TableCell className="px-2 py-2">{t(DELIVERY_STATUS_LABEL_KEYS[delivery.status])}</TableCell>
                        <TableCell className="px-2 py-2">{delivery.attempts}</TableCell>
                        <TableCell className="px-2 py-2">{delivery.last_error_code ?? "—"}</TableCell>
                        <TableCell className="px-2 py-2">{delivery.last_status_code ?? "—"}</TableCell>
                        <TableCell className="px-2 py-2">{delivery.created_at}</TableCell>
                        <TableCell className="px-2 py-2">
                          {delivery.status === "failed" || delivery.status === "dead_letter" ? (
                            <Button
                              type="button"
                              disabled={working}
                              onClick={() => void retryDelivery(delivery)}
                              aria-label={`${t("integrations.retryDeliveryAria")}${delivery.id}`}
                              variant="outline"
                              size="sm"
                            >
                              {t("integrations.retry")}
                            </Button>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : detailLoading ? null : (
                <Card className="bg-secondary p-3 text-sm text-text-muted">
                  {t("integrations.emptyDeliveries")}
                </Card>
              )}
            </section>
          ) : null}

          {selected.provider === "email_sandbox" ? (
            <section aria-labelledby="drafts-heading" className="space-y-2">
              <h3 id="drafts-heading" className="text-base font-semibold">
                {t("integrations.drafts")}
              </h3>
              {draftsError ? (
                <Card role="alert" className="p-3 text-sm">
                  {draftsError}
                </Card>
              ) : null}
              {drafts && drafts.length > 0 ? (
                <Table className="text-left text-sm">
                  <TableCaption className="sr-only">{t("integrations.draftsCaption")}</TableCaption>
                  <TableHeader>
                    <TableRow className="border-b border-border text-left">
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colTemplate")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colApproval")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colDelivery")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colAttempts")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colCreatedDraft")}</TableHead>
                      <TableHead scope="col" className="px-2 py-2 font-semibold">{t("integrations.colActions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {drafts.map((draft) => (
                      <TableRow key={draft.id} className="border-b border-border">
                        <TableCell className="px-2 py-2">{t(EMAIL_TEMPLATE_LABEL_KEYS[draft.template])}</TableCell>
                        <TableCell className="px-2 py-2">{t(APPROVAL_LABEL_KEYS[draft.approval_status])}</TableCell>
                        <TableCell className="px-2 py-2">{t(DELIVERY_LABEL_KEYS[draft.delivery_status])}</TableCell>
                        <TableCell className="px-2 py-2">{draft.attempts}</TableCell>
                        <TableCell className="px-2 py-2">{draft.created_at}</TableCell>
                        <TableCell className="px-2 py-2">
                          <div className="flex flex-wrap gap-2">
                            {draft.approval_status === "pending" ? (
                              <>
                                <Button
                                  type="button"
                                  disabled={working}
                                  onClick={() => void decideDraft(draft, "approve")}
                                  aria-label={`${t("integrations.approveDraftAria")}${draft.id}`}
                                  variant="outline"
                                  size="sm"
                                >
                                  {t("integrations.approve")}
                                </Button>
                                <Button
                                  type="button"
                                  disabled={working}
                                  onClick={() => void decideDraft(draft, "reject")}
                                  aria-label={`${t("integrations.rejectDraftAria")}${draft.id}`}
                                  variant="outline"
                                  size="sm"
                                >
                                  {t("integrations.reject")}
                                </Button>
                              </>
                            ) : null}
                            {draft.approval_status === "approved" && draft.delivery_status !== "sent" ? (
                              <Button
                                type="button"
                                disabled={working}
                                onClick={() => void decideDraft(draft, "send")}
                                aria-label={`${t("integrations.sendDraftAria")}${draft.id}`}
                                size="sm"
                              >
                                {t("integrations.send")}
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : detailLoading ? null : (
                <Card className="bg-secondary p-3 text-sm text-text-muted">
                  {t("integrations.emptyDrafts")}
                </Card>
              )}
            </section>
          ) : null}

          {selected.provider === "webhook_inbound" ? (
            <Card className="bg-secondary p-3 text-sm text-text-muted">
              {t("integrations.inboundNotice")}
            </Card>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
