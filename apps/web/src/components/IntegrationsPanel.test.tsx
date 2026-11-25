import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "../lib/api";
import type {
  EmailApprovalStatus,
  EmailDeliveryStatus,
  EmailDraft,
  EmailDraftList,
  IntegrationList,
  IntegrationSummary,
  WebhookDelivery,
  WebhookDeliveryList,
} from "../lib/types";
import { IntegrationsPanel } from "./IntegrationsPanel";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, apiFetch: vi.fn() };
});

type ApiHandler = (path: string, init?: RequestInit) => Promise<unknown>;

const OUTBOUND_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const EMAIL_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const INBOUND_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const DELIVERY_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const DRAFT_PENDING_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const DRAFT_APPROVED_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff";
const DRAFT_SENT_ID = "11111111-1111-4111-8111-111111111111";
const DRAFT_REJECTED_ID = "22222222-2222-4222-8222-222222222222";
const CREATED_AT = "2026-03-01T10:00:00Z";
const SECRET_MARKER = "SECRETO-SINTETICO-NO-DEBE-APARECER";

function mockApi(handler: ApiHandler): void {
  vi.mocked(apiFetch).mockImplementation(
    ((path: string, init?: RequestInit) => handler(path, init)) as unknown as typeof apiFetch,
  );
}

function pathOnly(path: string): string {
  return path.split("?")[0] ?? path;
}

function callsTo(path: string, method = "GET"): number {
  return vi
    .mocked(apiFetch)
    .mock.calls.filter(
      ([callPath, init]) =>
        pathOnly(callPath) === pathOnly(path) && (init?.method ?? "GET") === method,
    ).length;
}

function makeIntegration(overrides: Partial<IntegrationSummary> = {}): IntegrationSummary {
  return {
    id: INBOUND_ID,
    provider: "webhook_inbound",
    status: "active",
    config_version: 1,
    key_id: "clave-sintetica-01",
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    ...overrides,
  };
}

function makeList(items: IntegrationSummary[] = [makeIntegration()]): IntegrationList {
  return { items, total: items.length, limit: 20, offset: 0 };
}

function makeDelivery(overrides: Partial<WebhookDelivery> = {}): WebhookDelivery {
  return {
    id: DELIVERY_ID,
    event_id: "33333333-3333-4333-8333-333333333333",
    event_type: "application.stage_changed",
    status: "failed",
    attempts: 2,
    last_error_code: "provider_timeout",
    last_status_code: 504,
    created_at: CREATED_AT,
    delivered_at: null,
    ...overrides,
  };
}

function makeDeliveryList(items: WebhookDelivery[] = [makeDelivery()]): WebhookDeliveryList {
  return { items, total: items.length, limit: 20, offset: 0 };
}

function makeDraft(overrides: Partial<EmailDraft> = {}): EmailDraft {
  return {
    id: DRAFT_PENDING_ID,
    candidate_id: "44444444-4444-4444-8444-444444444444",
    template: "initial_contact",
    approval_status: "pending",
    delivery_status: "not_sent",
    attempts: 0,
    created_at: CREATED_AT,
    ...overrides,
  };
}

function makeDraftList(items: EmailDraft[]): EmailDraftList {
  return { items, total: items.length, limit: 20, offset: 0 };
}

async function selectProvider(provider: string): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: `Seleccionar integración ${provider}` }));
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("IntegrationsPanel", () => {
  it("muestra carga, luego el listado sin exponer secretos", async () => {
    const list = {
      ...makeList([
        makeIntegration({
          id: OUTBOUND_ID,
          provider: "webhook_outbound",
          key_id: "clave-sintetica-02",
        }),
      ]),
      items: [
        {
          ...makeIntegration({
            id: OUTBOUND_ID,
            provider: "webhook_outbound",
            key_id: "clave-sintetica-02",
          }),
          secret: SECRET_MARKER,
        },
      ],
    } as unknown as IntegrationList;
    mockApi(async (path) => {
      if (pathOnly(path) === "/api/v1/integrations") return list;
      return makeDeliveryList();
    });

    render(<IntegrationsPanel />);
    expect(screen.getByRole("status").textContent).toContain("Cargando integraciones…");

    const table = await screen.findByRole("table", {
      name: "Integraciones de la organización activa",
    });
    expect(table.parentElement?.className).toContain("overflow-x-auto");
    expect(screen.getByText("clave-sintetica-02")).toBeTruthy();
    expect(screen.getByText("webhook_outbound")).toBeTruthy();
    expect(document.body.textContent).not.toContain(SECRET_MARKER);
    expect(document.querySelector("input")).toBeNull();
  });

  it("muestra error 403 del backend y permite reintentar el listado", async () => {
    let fail = true;
    mockApi(async (path) => {
      if (pathOnly(path) !== "/api/v1/integrations") return makeList();
      if (fail) {
        throw new ApiError(403, "permission_denied", "Rol insuficiente.", "req-403");
      }
      return makeList();
    });

    render(<IntegrationsPanel />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("403: Rol insuficiente.");

    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("table")).toBeTruthy();
  });

  it("muestra estado vacío con acción cuando no hay integraciones", async () => {
    mockApi(async () => makeList([]));

    render(<IntegrationsPanel />);
    const empty = await screen.findByText(/No hay integraciones registradas/);
    expect(empty.textContent).toContain("API");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("carga entregas de webhook_outbound y reintenta una entrega fallida", async () => {
    const retryPath = `/api/v1/integrations/${OUTBOUND_ID}/deliveries/${DELIVERY_ID}/retry`;
    mockApi(async (path, init) => {
      if (pathOnly(path) === "/api/v1/integrations") {
        return makeList([makeIntegration({ id: OUTBOUND_ID, provider: "webhook_outbound" })]);
      }
      if (pathOnly(path) === `/api/v1/integrations/${OUTBOUND_ID}/deliveries`) {
        return makeDeliveryList();
      }
      if (path === retryPath && init?.method === "POST") {
        return makeDelivery({ status: "pending", attempts: 3, last_error_code: null });
      }
      return makeList([]);
    });

    render(<IntegrationsPanel />);
    await screen.findByRole("table");
    await selectProvider("webhook_outbound");

    expect(await screen.findByRole("heading", { name: "Entregas salientes" })).toBeTruthy();
    const deliveriesTable = await screen.findByRole("table", {
      name: "Entregas salientes registradas",
    });
    expect(deliveriesTable.parentElement?.className).toContain("overflow-x-auto");
    const retry = await screen.findByRole("button", { name: `Reintentar entrega ${DELIVERY_ID}` });
    fireEvent.click(retry);

    expect(await screen.findByText(/Reintento encolado/)).toBeTruthy();
    expect(callsTo(retryPath, "POST")).toBe(1);
  });

  it("carga borradores de email_sandbox y muestra botones según estado", async () => {
    mockApi(async (path) => {
      if (pathOnly(path) === "/api/v1/integrations") {
        return makeList([makeIntegration({ id: EMAIL_ID, provider: "email_sandbox" })]);
      }
      if (pathOnly(path) === `/api/v1/integrations/${EMAIL_ID}/email-drafts`) {
        return makeDraftList([
          makeDraft({ id: DRAFT_PENDING_ID }),
          makeDraft({
            id: DRAFT_APPROVED_ID,
            approval_status: "approved",
            delivery_status: "not_sent",
          }),
          makeDraft({
            id: DRAFT_SENT_ID,
            approval_status: "approved",
            delivery_status: "sent",
          }),
          makeDraft({
            id: DRAFT_REJECTED_ID,
            approval_status: "rejected",
            delivery_status: "not_sent",
          }),
        ]);
      }
      return makeList([]);
    });

    render(<IntegrationsPanel />);
    await screen.findByRole("table");
    await selectProvider("email_sandbox");

    expect(await screen.findByRole("heading", { name: "Borradores de correo" })).toBeTruthy();
    const draftsTable = await screen.findByRole("table", {
      name: "Borradores de correo sandbox",
    });
    expect(draftsTable.parentElement?.className).toContain("overflow-x-auto");
    expect(
      screen.getByRole("button", { name: `Aprobar borrador ${DRAFT_PENDING_ID}` }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: `Rechazar borrador ${DRAFT_PENDING_ID}` }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: `Enviar borrador ${DRAFT_PENDING_ID}` }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: `Enviar borrador ${DRAFT_APPROVED_ID}` }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: `Aprobar borrador ${DRAFT_APPROVED_ID}` }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: `Enviar borrador ${DRAFT_SENT_ID}` })).toBeNull();
    expect(
      screen.queryByRole("button", { name: `Aprobar borrador ${DRAFT_REJECTED_ID}` }),
    ).toBeNull();
  });

  it("aprobar no envía; enviar tras aprobación llama al endpoint de envío", async () => {
    let approval: EmailApprovalStatus = "pending";
    let delivery: EmailDeliveryStatus = "not_sent";
    const base = `/api/v1/integrations/${EMAIL_ID}/email-drafts/${DRAFT_PENDING_ID}`;
    mockApi(async (path, init) => {
      if (pathOnly(path) === "/api/v1/integrations") {
        return makeList([makeIntegration({ id: EMAIL_ID, provider: "email_sandbox" })]);
      }
      if (pathOnly(path) === `/api/v1/integrations/${EMAIL_ID}/email-drafts`) {
        return makeDraftList([makeDraft({ approval_status: approval, delivery_status: delivery })]);
      }
      if (path === `${base}/approve` && init?.method === "POST") {
        approval = "approved";
        return makeDraft({ approval_status: approval, delivery_status: delivery });
      }
      if (path === `${base}/send` && init?.method === "POST") {
        delivery = "sent";
        return makeDraft({ approval_status: approval, delivery_status: delivery });
      }
      return makeList([]);
    });

    render(<IntegrationsPanel />);
    await screen.findByRole("table");
    await selectProvider("email_sandbox");
    await screen.findByRole("button", { name: `Aprobar borrador ${DRAFT_PENDING_ID}` });

    fireEvent.click(screen.getByRole("button", { name: `Aprobar borrador ${DRAFT_PENDING_ID}` }));
    expect(await screen.findByText("Borrador aprobado. No se envió.")).toBeTruthy();
    expect(callsTo(`${base}/approve`, "POST")).toBe(1);
    expect(callsTo(`${base}/send`, "POST")).toBe(0);

    fireEvent.click(await screen.findByRole("button", { name: `Enviar borrador ${DRAFT_PENDING_ID}` }));
    expect(await screen.findByText("Borrador enviado.")).toBeTruthy();
    expect(callsTo(`${base}/send`, "POST")).toBe(1);
  });

  it("muestra el error de una acción sin mutar el borrador local", async () => {
    const approvePath = `/api/v1/integrations/${EMAIL_ID}/email-drafts/${DRAFT_PENDING_ID}/approve`;
    const sendPath = `/api/v1/integrations/${EMAIL_ID}/email-drafts/${DRAFT_PENDING_ID}/send`;
    mockApi(async (path) => {
      if (pathOnly(path) === "/api/v1/integrations") {
        return makeList([makeIntegration({ id: EMAIL_ID, provider: "email_sandbox" })]);
      }
      if (pathOnly(path) === `/api/v1/integrations/${EMAIL_ID}/email-drafts`) {
        return makeDraftList([makeDraft()]);
      }
      if (path === approvePath) {
        throw new ApiError(403, "permission_denied", "Rol insuficiente.", "req-403");
      }
      return makeDraft();
    });

    render(<IntegrationsPanel />);
    await screen.findByRole("table");
    await selectProvider("email_sandbox");
    await screen.findByRole("button", { name: `Aprobar borrador ${DRAFT_PENDING_ID}` });

    fireEvent.click(screen.getByRole("button", { name: `Aprobar borrador ${DRAFT_PENDING_ID}` }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("403: Rol insuficiente.");
    expect(
      screen.getByRole("button", { name: `Aprobar borrador ${DRAFT_PENDING_ID}` }),
    ).toBeTruthy();
    expect(screen.getByText("Pendiente")).toBeTruthy();
    expect(callsTo(sendPath, "POST")).toBe(0);
  });

  it("no pide entregas para email_sandbox ni borradores para webhook_outbound", async () => {
    mockApi(async (path) => {
      if (pathOnly(path) === "/api/v1/integrations") {
        return makeList([
          makeIntegration({ id: OUTBOUND_ID, provider: "webhook_outbound" }),
          makeIntegration({ id: EMAIL_ID, provider: "email_sandbox" }),
        ]);
      }
      if (pathOnly(path) === `/api/v1/integrations/${OUTBOUND_ID}/deliveries`) {
        return makeDeliveryList([]);
      }
      if (pathOnly(path) === `/api/v1/integrations/${EMAIL_ID}/email-drafts`) {
        return makeDraftList([]);
      }
      return makeList([]);
    });

    render(<IntegrationsPanel />);
    await screen.findByRole("table");
    await selectProvider("webhook_outbound");
    expect(await screen.findByRole("heading", { name: "Entregas salientes" })).toBeTruthy();
    expect(callsTo(`/api/v1/integrations/${OUTBOUND_ID}/deliveries`, "GET")).toBe(1);
    expect(callsTo(`/api/v1/integrations/${OUTBOUND_ID}/email-drafts`, "GET")).toBe(0);

    await selectProvider("email_sandbox");
    expect(await screen.findByRole("heading", { name: "Borradores de correo" })).toBeTruthy();
    expect(callsTo(`/api/v1/integrations/${EMAIL_ID}/email-drafts`, "GET")).toBe(1);
    expect(callsTo(`/api/v1/integrations/${EMAIL_ID}/deliveries`, "GET")).toBe(0);
  });
});
