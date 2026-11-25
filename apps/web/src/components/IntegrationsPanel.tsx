"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "../lib/api";
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

const PAGE_SIZE = 20;

const PROVIDER_LABELS: Record<IntegrationProvider, string> = {
  email_sandbox: "Correo sandbox",
  webhook_outbound: "Webhook saliente",
  webhook_inbound: "Webhook entrante",
};

const INTEGRATION_STATUS_LABELS: Record<IntegrationStatus, string> = {
  active: "Activa",
  disabled: "Desactivada",
};

const DELIVERY_STATUS_LABELS: Record<WebhookDeliveryStatus, string> = {
  pending: "Pendiente",
  sending: "Enviando",
  delivered: "Entregada",
  failed: "Fallida",
  dead_letter: "Dead letter",
};

const EMAIL_TEMPLATE_LABELS: Record<EmailTemplate, string> = {
  initial_contact: "Contacto inicial",
  interview_invite: "Invitación a entrevista",
  follow_up: "Seguimiento",
};

const APPROVAL_LABELS: Record<EmailApprovalStatus, string> = {
  pending: "Pendiente",
  approved: "Aprobado",
  rejected: "Rechazado",
};

const DELIVERY_LABELS: Record<EmailDeliveryStatus, string> = {
  not_sent: "Sin enviar",
  sent: "Enviado",
  failed: "Fallido",
};

type DraftAction = "approve" | "reject" | "send";

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    return `${cause.status}: ${cause.message}`;
  }
  return fallback;
}

function busyText(busy: string | null): string | null {
  if (!busy) return null;
  if (busy.startsWith("delivery:")) return "Reintentando entrega…";
  if (busy.startsWith("draft:approve:")) return "Aprobando borrador…";
  if (busy.startsWith("draft:reject:")) return "Rechazando borrador…";
  if (busy.startsWith("draft:send:")) return "Solicitando envío…";
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
      setError(describeError(cause, "No se pudo cargar el listado de integraciones."));
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
          setError(describeError(cause, "No se pudo cargar el listado de integraciones."));
        }
      },
    ).finally(() => {
      if (active) setListLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);

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
      setNotice("Este proveedor no expone entregas salientes ni borradores de correo.");
      return;
    }

    setDetailLoading(true);
    if (wantsDeliveries) {
      try {
        setDeliveries((await requestDeliveries(integration.id)).items);
      } catch (cause) {
        setDeliveriesError(describeError(cause, "No se pudo cargar las entregas salientes."));
      }
    }
    if (wantsDrafts) {
      try {
        setDrafts((await requestDrafts(integration.id)).items);
      } catch (cause) {
        setDraftsError(describeError(cause, "No se pudo cargar los borradores de correo."));
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
      setNotice("Reintento encolado. El estado final lo confirma el servidor.");
    } catch (cause) {
      setActionError(describeError(cause, "No se pudo solicitar el reintento."));
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
          ? "Borrador aprobado. No se envió."
          : action === "reject"
            ? "Borrador rechazado. Sin envío."
            : updated.delivery_status === "sent"
              ? "Borrador enviado."
              : "Solicitud de envío registrada; revisa el estado devuelto.",
      );
    } catch (cause) {
      setActionError(describeError(cause, "No se pudo completar la acción sobre el borrador."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="integrations-panel-heading" aria-busy={working} className="space-y-6">
      <div className="space-y-1">
        <h2 id="integrations-panel-heading" className="text-lg font-semibold">
          Estado de integraciones
        </h2>
        <p className="text-sm text-text-muted">
          Metadatos y diagnóstico operativo. Las credenciales se cifran en el servidor y nunca se
          muestran aquí; el alta y la rotación se hacen desde la API.
        </p>
      </div>

      <p role="status" aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {listLoading
          ? "Cargando integraciones…"
          : detailLoading
            ? "Cargando diagnóstico…"
            : busyText(busy) ?? notice ?? ""}
      </p>

      {error ? (
        <section role="alert" className="space-y-2 rounded-sm border border-border p-3">
          <p className="text-sm">{error}</p>
          <button
            type="button"
            onClick={() => void loadList()}
            className="rounded-sm border border-border px-3 py-1 text-sm font-semibold"
          >
            Reintentar
          </button>
        </section>
      ) : null}

      {actionError ? (
        <section role="alert" className="rounded-sm border border-border p-3 text-sm">
          {actionError}
        </section>
      ) : null}

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label htmlFor="integration-status-filter" className="block text-sm font-semibold">
            Filtrar por estado
          </label>
          <select
            id="integration-status-filter"
            value={statusFilter}
            onChange={(event) => {
              const next = event.target.value as IntegrationStatus | "all";
              setStatusFilter(next);
              void loadList(next, 0);
            }}
            disabled={working}
            className="rounded-sm border border-border bg-surface px-2 py-2 text-sm"
          >
            <option value="all">Todos</option>
            <option value="active">Activa</option>
            <option value="disabled">Desactivada</option>
          </select>
        </div>
        <button
          type="button"
          onClick={() => void loadList()}
          disabled={working}
          className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:opacity-60"
        >
          Actualizar listado
        </button>
      </div>

      {list && list.items.length > 0 ? (
        <div className="space-y-2">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Integraciones de la organización activa</caption>
            <thead>
              <tr className="border-b border-border text-left">
                <th scope="col" className="px-2 py-2 font-semibold">Proveedor</th>
                <th scope="col" className="px-2 py-2 font-semibold">Estado</th>
                <th scope="col" className="px-2 py-2 font-semibold">Versión de config.</th>
                <th scope="col" className="px-2 py-2 font-semibold">ID de clave</th>
                <th scope="col" className="px-2 py-2 font-semibold">Creada (UTC)</th>
                <th scope="col" className="px-2 py-2 font-semibold">Actualizada (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {list.items.map((item) => (
                <tr key={item.id} className="border-b border-border">
                  <td className="px-2 py-2">
                    <button
                      type="button"
                      disabled={working}
                      onClick={() => void selectIntegration(item)}
                      aria-current={item.id === selected?.id ? "true" : undefined}
                      aria-label={`Seleccionar integración ${item.provider}`}
                      className="rounded-sm border border-border bg-surface px-2 py-1 text-left font-semibold disabled:opacity-60"
                    >
                      {PROVIDER_LABELS[item.provider]} · <code>{item.provider}</code>
                    </button>
                  </td>
                  <td className="px-2 py-2">{INTEGRATION_STATUS_LABELS[item.status]}</td>
                  <td className="px-2 py-2">{item.config_version}</td>
                  <td className="px-2 py-2"><code>{item.key_id}</code></td>
                  <td className="px-2 py-2">{item.created_at}</td>
                  <td className="px-2 py-2">{item.updated_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex flex-wrap items-center gap-3 text-sm text-text-muted">
            <span>{`Página ${currentPage} de ${totalPages} · ${list.total} registros`}</span>
            <button
              type="button"
              disabled={working || offset === 0}
              onClick={() => {
                const next = Math.max(0, offset - PAGE_SIZE);
                setOffset(next);
                void loadList(statusFilter, next);
              }}
              className="rounded-sm border border-border px-3 py-1 font-semibold disabled:opacity-60"
            >
              Página anterior
            </button>
            <button
              type="button"
              disabled={working || offset + PAGE_SIZE >= list.total}
              onClick={() => {
                const next = offset + PAGE_SIZE;
                setOffset(next);
                void loadList(statusFilter, next);
              }}
              className="rounded-sm border border-border px-3 py-1 font-semibold disabled:opacity-60"
            >
              Página siguiente
            </button>
          </div>
        </div>
      ) : list && !listLoading && !error ? (
        <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
          No hay integraciones registradas. Configúralas desde la API; esta pantalla no pide ni
          muestra credenciales.
        </p>
      ) : null}

      {selected ? (
        <div className="space-y-6">
          <section aria-labelledby="integration-detail-heading" className="space-y-3">
            <h3 id="integration-detail-heading" className="text-base font-semibold">
              {PROVIDER_LABELS[selected.provider]} · <code>{selected.provider}</code>
            </h3>
            <dl className="flex flex-wrap gap-x-6 gap-y-1 rounded-sm border border-border p-3 text-sm">
              <div>
                <dt className="text-xs font-semibold text-text-muted">Estado: </dt>
                <dd className="inline">{INTEGRATION_STATUS_LABELS[selected.status]}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">Versión de config.: </dt>
                <dd className="inline">{selected.config_version}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold text-text-muted">ID de clave: </dt>
                <dd className="inline"><code>{selected.key_id}</code></dd>
              </div>
            </dl>
          </section>

          {selected.provider === "webhook_outbound" ? (
            <section aria-labelledby="deliveries-heading" className="space-y-2">
              <h3 id="deliveries-heading" className="text-base font-semibold">
                Entregas salientes
              </h3>
              {deliveriesError ? (
                <p role="alert" className="rounded-sm border border-border p-3 text-sm">
                  {deliveriesError}
                </p>
              ) : null}
              {deliveries && deliveries.length > 0 ? (
                <table className="w-full border-collapse text-sm">
                  <caption className="sr-only">Entregas salientes registradas</caption>
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th scope="col" className="px-2 py-2 font-semibold">Evento</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Estado</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Intentos</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Error</th>
                      <th scope="col" className="px-2 py-2 font-semibold">HTTP</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Creada (UTC)</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.map((delivery) => (
                      <tr key={delivery.id} className="border-b border-border">
                        <td className="px-2 py-2"><code>{delivery.event_type}</code></td>
                        <td className="px-2 py-2">{DELIVERY_STATUS_LABELS[delivery.status]}</td>
                        <td className="px-2 py-2">{delivery.attempts}</td>
                        <td className="px-2 py-2">{delivery.last_error_code ?? "—"}</td>
                        <td className="px-2 py-2">{delivery.last_status_code ?? "—"}</td>
                        <td className="px-2 py-2">{delivery.created_at}</td>
                        <td className="px-2 py-2">
                          {delivery.status === "failed" || delivery.status === "dead_letter" ? (
                            <button
                              type="button"
                              disabled={working}
                              onClick={() => void retryDelivery(delivery)}
                              aria-label={`Reintentar entrega ${delivery.id}`}
                              className="rounded-sm border border-border px-2 py-1 text-sm font-semibold disabled:opacity-60"
                            >
                              Reintentar
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : detailLoading ? null : (
                <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
                  No hay entregas salientes registradas.
                </p>
              )}
            </section>
          ) : null}

          {selected.provider === "email_sandbox" ? (
            <section aria-labelledby="drafts-heading" className="space-y-2">
              <h3 id="drafts-heading" className="text-base font-semibold">
                Borradores de correo
              </h3>
              {draftsError ? (
                <p role="alert" className="rounded-sm border border-border p-3 text-sm">
                  {draftsError}
                </p>
              ) : null}
              {drafts && drafts.length > 0 ? (
                <table className="w-full border-collapse text-sm">
                  <caption className="sr-only">Borradores de correo sandbox</caption>
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th scope="col" className="px-2 py-2 font-semibold">Plantilla</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Aprobación</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Entrega</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Intentos</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Creado (UTC)</th>
                      <th scope="col" className="px-2 py-2 font-semibold">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drafts.map((draft) => (
                      <tr key={draft.id} className="border-b border-border">
                        <td className="px-2 py-2">{EMAIL_TEMPLATE_LABELS[draft.template]}</td>
                        <td className="px-2 py-2">{APPROVAL_LABELS[draft.approval_status]}</td>
                        <td className="px-2 py-2">{DELIVERY_LABELS[draft.delivery_status]}</td>
                        <td className="px-2 py-2">{draft.attempts}</td>
                        <td className="px-2 py-2">{draft.created_at}</td>
                        <td className="px-2 py-2">
                          <div className="flex flex-wrap gap-2">
                            {draft.approval_status === "pending" ? (
                              <>
                                <button
                                  type="button"
                                  disabled={working}
                                  onClick={() => void decideDraft(draft, "approve")}
                                  aria-label={`Aprobar borrador ${draft.id}`}
                                  className="rounded-sm border border-border px-2 py-1 text-sm font-semibold disabled:opacity-60"
                                >
                                  Aprobar
                                </button>
                                <button
                                  type="button"
                                  disabled={working}
                                  onClick={() => void decideDraft(draft, "reject")}
                                  aria-label={`Rechazar borrador ${draft.id}`}
                                  className="rounded-sm border border-border px-2 py-1 text-sm font-semibold disabled:opacity-60"
                                >
                                  Rechazar
                                </button>
                              </>
                            ) : null}
                            {draft.approval_status === "approved" && draft.delivery_status !== "sent" ? (
                              <button
                                type="button"
                                disabled={working}
                                onClick={() => void decideDraft(draft, "send")}
                                aria-label={`Enviar borrador ${draft.id}`}
                                className="rounded-sm bg-accent px-2 py-1 text-sm font-semibold text-white disabled:opacity-60"
                              >
                                Enviar
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : detailLoading ? null : (
                <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
                  No hay borradores de correo registrados.
                </p>
              )}
            </section>
          ) : null}

          {selected.provider === "webhook_inbound" ? (
            <p className="rounded-sm border border-border bg-surface-muted p-3 text-sm text-text-muted">
              Este proveedor sólo recibe eventos; no hay entregas salientes ni borradores que revisar.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
