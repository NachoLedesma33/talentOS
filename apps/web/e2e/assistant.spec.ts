import { expect, test, type Page } from "@playwright/test";

test.use({ launchOptions: { args: ["--disable-web-security"] } });

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

const ORG_ID = "org-e2e-asistente";
const DOCUMENT_ID = "doc-e2e-asistente";
const RUN_ID = "run-e2e-asistente";
const ACTION_ID = "action-e2e-asistente";
const QUOTE = "Evidencia sintética verificada";
const ANSWER = "Respuesta sintética verificada";

const sessionUser = {
  id: "user-e2e-asistente",
  email: "asistente@example.test",
  name: "Usuario E2E Asistente",
  status: "active",
  organizations: [{ id: ORG_ID, name: "Organización E2E" }],
  onboarding: { step: "complete" },
};

const organizations = [
  {
    id: ORG_ID,
    name: "Organización E2E",
    slug: "organizacion-e2e",
    created_at: "2026-01-01T00:00:00Z",
  },
];

type MockReply = { status?: number; body: unknown };
type MockHandler = (
  pathname: string,
  method: string,
  headers: Record<string, string>,
  body: Record<string, unknown>,
) => MockReply | null;

async function mockApi(page: Page, handler: MockHandler) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    const raw = request.postData();
    const body = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    const reply = handler(
      new URL(request.url()).pathname,
      request.method(),
      request.headers(),
      body,
    );
    if (!reply) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        headers: corsHeaders,
        body: JSON.stringify({
          error: { code: "not_found", message: "No encontrado", request_id: "e2e" },
        }),
      });
      return;
    }
    await route.fulfill({
      status: reply.status ?? 200,
      contentType: "application/json",
      headers: corsHeaders,
      body: JSON.stringify(reply.body),
    });
  });
}

function workspaceApi(): MockHandler {
  return (pathname, method) => {
    if (method === "GET" && pathname === "/api/v1/auth/me") {
      return { body: sessionUser };
    }
    if (method === "GET" && pathname === "/api/v1/organizations") {
      return { body: organizations };
    }
    if (method === "GET" && pathname.endsWith("/members")) {
      return { body: [] };
    }
    return null;
  };
}

function makeResponse(overrides: Record<string, unknown> = {}) {
  return {
    run_id: RUN_ID,
    answer: ANSWER,
    status: "completed",
    citations: [
      {
        quote: QUOTE,
        organization_id: ORG_ID,
        document_id: DOCUMENT_ID,
        page: 2,
      },
    ],
    proposed_actions: [],
    limitations: [],
    unsupported_reason: null,
    ...overrides,
  };
}

function makeAction() {
  return {
    action_id: ACTION_ID,
    type: "navigate",
    form_id: null,
    route: "/jobs",
    patch: {},
    field_origins: {},
    requires_confirmation: true,
  };
}

function assistantPanel(page: Page) {
  return page.getByRole("region", { name: "Asistente del workspace" });
}

test("asistente muestra evidencia y confirma la acción aprobada", async ({ page }) => {
  let messageBody: Record<string, unknown> = {};
  let ackBody: Record<string, unknown> = {};
  let messageOrgHeader: string | null = null;

  await mockApi(page, (pathname, method, headers, body) => {
    if (method === "POST" && pathname === "/api/v1/agents/assistant/messages") {
      messageBody = body;
      messageOrgHeader = headers["x-organization-id"] ?? null;
      return {
        status: 201,
        body: makeResponse({
          status: "waiting_approval",
          proposed_actions: [makeAction()],
        }),
      };
    }
    if (
      method === "POST" &&
      pathname === `/api/v1/agents/assistant/actions/${ACTION_ID}/ack`
    ) {
      ackBody = body;
      return { body: makeResponse({ citations: [] }) };
    }
    return workspaceApi()(pathname, method, headers, body);
  });

  await page.goto("/dashboard");
  const panel = assistantPanel(page);
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/Todavía no hay respuesta/)).toBeVisible();

  await panel.getByLabel("Pregunta para el asistente").fill("¿Qué evidencia confirma el perfil?");
  await panel.getByRole("button", { name: "Consultar" }).click();

  await expect(panel.getByText(ANSWER)).toBeVisible();
  await expect(panel.getByText(QUOTE)).toBeVisible();
  await expect(panel.getByText(new RegExp(`Documento: ${DOCUMENT_ID}`))).toBeVisible();
  await expect(panel.getByText("/jobs")).toBeVisible();
  expect(messageOrgHeader).toBe(ORG_ID);
  expect(messageBody).toMatchObject({
    schema_version: "1.0",
    message: "¿Qué evidencia confirma el perfil?",
    surface: "dashboard",
    resource_ref: null,
  });
  expect(typeof messageBody?.idempotency_key).toBe("string");

  await panel.getByRole("button", { name: "Aplicar" }).click();
  await expect(panel.getByText("Decisión aplicada. La API confirmó el resultado.")).toBeVisible();
  expect(ackBody).toMatchObject({
    schema_version: "1.0",
    action_id: ACTION_ID,
    decision: "applied",
    idempotency_key: messageBody?.idempotency_key,
  });
});

test("asistente exige confirmación explícita antes de descartar", async ({ page }) => {
  let ackCount = 0;

  await mockApi(page, (pathname, method, headers, body) => {
    if (method === "POST" && pathname === "/api/v1/agents/assistant/messages") {
      return {
        status: 201,
        body: makeResponse({
          status: "waiting_approval",
          proposed_actions: [makeAction()],
        }),
      };
    }
    if (method === "POST" && pathname.endsWith("/ack")) {
      ackCount += 1;
      return { body: makeResponse({ citations: [], proposed_actions: [] }) };
    }
    return workspaceApi()(pathname, method, headers, body);
  });

  await page.goto("/dashboard");
  const panel = assistantPanel(page);
  await panel.getByLabel("Pregunta para el asistente").fill("¿Descarto la navegación?");
  await panel.getByRole("button", { name: "Consultar" }).click();

  await panel.getByRole("button", { name: "Descartar" }).click();
  await expect(panel.getByText("¿Descartar esta acción propuesta?")).toBeVisible();
  expect(ackCount).toBe(0);

  await panel.getByRole("button", { name: "Cancelar" }).click();
  await expect(panel.getByText("¿Descartar esta acción propuesta?")).toBeHidden();
  expect(ackCount).toBe(0);

  await panel.getByRole("button", { name: "Descartar" }).click();
  await panel.getByRole("button", { name: "Confirmar descarte" }).click();
  await expect(panel.getByText("Acción descartada. La API confirmó el resultado.")).toBeVisible();
  expect(ackCount).toBe(1);
});

test("asistente muestra error de la API sin simular respuesta", async ({ page }) => {
  await mockApi(page, (pathname, method, headers, body) => {
    if (method === "POST" && pathname === "/api/v1/agents/assistant/messages") {
      return {
        status: 403,
        body: {
          error: {
            code: "forbidden",
            message: "Rol insuficiente.",
            request_id: "e2e",
          },
        },
      };
    }
    return workspaceApi()(pathname, method, headers, body);
  });

  await page.goto("/dashboard");
  const panel = assistantPanel(page);
  await panel.getByLabel("Pregunta para el asistente").fill("¿Puedo ver datos privados?");
  await panel.getByRole("button", { name: "Consultar" }).click();

  await expect(panel.getByRole("alert")).toContainText("403: Rol insuficiente.");
  await expect(panel.getByText(ANSWER)).toHaveCount(0);
});
