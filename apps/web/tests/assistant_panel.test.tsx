import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantPanel } from "../src/components/AssistantPanel";
import { ACTIVE_ORG_STORAGE_KEY } from "../src/lib/api";

type FetchHandler = (url: URL, init?: RequestInit) => Response | Promise<Response>;

const ORGANIZATION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const DOCUMENT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const RUN_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const ACTION_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const IDEMPOTENCY_KEY = "clave-sintetica-asistente";
const QUOTE = "Evidencia sintética verificada";

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

function errorResponse(status: number, message: string, code = "http_error"): Response {
  return jsonResponse(
    { error: { code, message, request_id: `req-${status}` } },
    status,
  );
}

function mockFetch(handler: FetchHandler) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    return handler(url, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body)) as Record<string, unknown>;
}

function makeResponse(overrides: Record<string, unknown> = {}) {
  return {
    run_id: RUN_ID,
    answer: "Respuesta sintética verificada",
    status: "completed",
    citations: [
      {
        quote: QUOTE,
        organization_id: ORGANIZATION_ID,
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

function openChat() {
  if (!screen.queryByLabelText(/Pregunta para el asistente/i)) {
    fireEvent.click(screen.getByRole("button", { name: "Expandir chat" }));
  }
}

function ask(question = "¿Qué evidencia confirma el perfil?") {
  openChat();
  fireEvent.change(screen.getByLabelText(/Pregunta para el asistente/i), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole("button", { name: "Consultar" }));
}

beforeEach(() => {
  window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, ORGANIZATION_ID);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("AssistantPanel", () => {
  it("muestra vacío, envía mensaje autenticado y renderiza cita verificable", async () => {
    const fetchMock = mockFetch((url, init) => {
      expect(url.pathname).toBe("/api/v1/agents/assistant/messages");
      expect(init?.method).toBe("POST");
      expect(init?.credentials).toBe("include");
      expect(new Headers(init?.headers).get("X-Organization-ID")).toBe(ORGANIZATION_ID);
      expect(parseBody(init)).toMatchObject({
        schema_version: "1.0",
        message: "¿Qué evidencia confirma el perfil?",
        surface: "dashboard",
        resource_ref: DOCUMENT_ID,
        idempotency_key: IDEMPOTENCY_KEY,
      });
      return jsonResponse(makeResponse(), 201);
    });

    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} resourceRef={DOCUMENT_ID} />);
    openChat();
    expect(screen.getByText(/Todavía no hay respuesta/i)).toBeTruthy();

    ask();

    expect(await screen.findByText("Respuesta sintética verificada")).toBeTruthy();
    expect(screen.getByText(QUOTE)).toBeTruthy();
    expect(screen.getByText(new RegExp(DOCUMENT_ID))).toBeTruthy();
    expect(screen.getByText(/Página: 2/)).toBeTruthy();
    expect(screen.getByText(/No hay acciones propuestas/i)).toBeTruthy();
    expect(screen.getByText(/Las acciones solo se pueden decidir/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Aplicar" })).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("aplica acción solo con confirmación y reenvía la misma clave de idempotencia", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (url.pathname.endsWith("/messages")) {
        return jsonResponse(
          makeResponse({ status: "waiting_approval", proposed_actions: [makeAction()] }),
          201,
        );
      }
      expect(url.pathname).toBe(
        `/api/v1/agents/assistant/actions/${ACTION_ID}/ack`,
      );
      expect(parseBody(init)).toEqual({
        schema_version: "1.0",
        action_id: ACTION_ID,
        decision: "applied",
        idempotency_key: IDEMPOTENCY_KEY,
      });
      return jsonResponse(makeResponse({ citations: [] }));
    });

    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);
    ask("¿Puedo ver las vacantes?");

    expect(await screen.findByText("/jobs")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(await screen.findByText(/Decisión aplicada/i)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("descarta acción solo tras confirmación explícita", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (url.pathname.endsWith("/messages")) {
        return jsonResponse(
          makeResponse({ status: "waiting_approval", proposed_actions: [makeAction()] }),
          201,
        );
      }
      expect(parseBody(init)).toMatchObject({
        action_id: ACTION_ID,
        decision: "discarded",
        idempotency_key: IDEMPOTENCY_KEY,
      });
      return jsonResponse(makeResponse({ citations: [], proposed_actions: [] }));
    });

    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);
    ask("¿Descarto la navegación?");

    const discard = await screen.findByRole("button", { name: "Descartar" });
    fireEvent.click(discard);
    expect(screen.getByText("¿Descartar esta acción propuesta?")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByText("¿Descartar esta acción propuesta?")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar descarte" }));

    expect(await screen.findByText(/Acción descartada/i)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("muestra error accionable sin simular respuesta cuando la API responde 403", async () => {
    mockFetch(() => errorResponse(403, "Rol insuficiente.", "forbidden"));

    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);
    ask();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("403: Rol insuficiente.")).toBeTruthy();
    expect(screen.queryByText("Respuesta sintética verificada")).toBeNull();
  });

  it("muestra limitaciones y motivo de no disponibilidad devueltos por la API", async () => {
    mockFetch(() =>
      jsonResponse(
        makeResponse({
          status: "needs_review",
          citations: [],
          limitations: ["Fuente sin confirmar"],
          unsupported_reason: "not_available",
        }),
      ),
    );

    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);
    ask("¿Qué pasa con este recurso?");

    expect(await screen.findByText("Fuente sin confirmar")).toBeTruthy();
    expect(screen.getByText(/not_available/)).toBeTruthy();
    expect(screen.getByText(/Sin evidencia verificable/i)).toBeTruthy();
  });

  it("muestra aviso de demo limitada sin exponer el código técnico", async () => {
    mockFetch(() =>
      jsonResponse(
        makeResponse({ limitations: ["demo_mock", "Fuente sin confirmar"] }),
      ),
    );

    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);
    ask("¿Qué pasa con este recurso?");

    expect(await screen.findByText(/Demo limitada:/)).toBeTruthy();
    expect(screen.getByText("Fuente sin confirmar")).toBeTruthy();
    expect(screen.queryByText("demo_mock")).toBeNull();
  });

  it("empieza colapsado y la flecha expande y colapsa el cuerpo", () => {
    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);

    const region = screen.getByRole("region", { name: "Asistente del workspace" });
    expect(region.className).toContain("fixed");
    expect(region.className).toContain("bottom-0");
    expect(region.className).toContain("right-4");
    expect(screen.queryByRole("log", { name: "Conversación" })).toBeNull();

    const expand = screen.getByRole("button", { name: "Expandir chat" });
    expect(expand.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(expand);

    expect(screen.getByRole("log", { name: "Conversación" })).toBeTruthy();
    const collapse = screen.getByRole("button", { name: "Colapsar chat" });
    expect(collapse.getAttribute("aria-expanded")).toBe("true");
    expect(collapse.querySelector("span")?.className).toContain("rotate-180");

    fireEvent.click(collapse);
    expect(screen.queryByRole("log", { name: "Conversación" })).toBeNull();
  });

  it("muestra opciones sin consultar la API", () => {
    const fetchMock = mockFetch(() => jsonResponse(makeResponse(), 201));
    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);

    fireEvent.click(screen.getByRole("button", { name: "Más opciones" }));
    expect(screen.getByText(/Pregunta sobre datos del workspace/i)).toBeTruthy();
    expect(screen.getByText(/la decisión final es humana/i)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("nuevo mensaje reinicia la conversación local", async () => {
    mockFetch(() => jsonResponse(makeResponse(), 201));
    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);
    ask();

    expect(await screen.findByText("Respuesta sintética verificada")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Nuevo mensaje" }));

    expect(screen.getByText(/Todavía no hay respuesta/i)).toBeTruthy();
    expect(screen.getByText(/Nueva conversación iniciada/i)).toBeTruthy();
    expect(screen.queryByText("Respuesta sintética verificada")).toBeNull();
  });

  it("redimensiona el cuerpo con teclado y arrastre", () => {
    render(<AssistantPanel idempotencyKey={IDEMPOTENCY_KEY} />);
    const handle = screen.getByRole("separator", { name: "Redimensionar chat" });
    expect(handle.getAttribute("tabindex")).toBe("-1");

    openChat();
    const body = screen.getByRole("log", { name: "Conversación" }).parentElement;
    if (!body) throw new Error("Cuerpo del chat no disponible");
    expect(body.style.height).toBe("360px");

    fireEvent.keyDown(handle, { key: "ArrowUp" });
    expect(body.style.height).toBe("384px");
    fireEvent.keyDown(handle, { key: "ArrowDown" });
    expect(body.style.height).toBe("360px");

    fireEvent.pointerDown(handle, { pointerId: 1, clientY: 400 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 320 });
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 320 });
    expect(body.style.height).toBe("440px");
  });
});
