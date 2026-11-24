import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutomationApprovalControls } from "../src/components/AutomationApprovalControls";
import { AutomationRulePanel } from "../src/components/AutomationRulePanel";
import { AutomationRunTimeline } from "../src/components/AutomationRunTimeline";
import type {
  AutomationApproval,
  AutomationApprovalStatus,
  AutomationDetail,
  AutomationList,
  AutomationRunDetail,
  AutomationRunEvent,
  AutomationRunEventList,
  AutomationRunList,
  AutomationRunSummary,
  AutomationStatus,
  AutomationSummary,
  AutomationTestResult,
} from "../src/lib/types";

type FetchHandler = (url: URL, init?: RequestInit) => Response | Promise<Response>;

const AUTOMATION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const VERSION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const RUN_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const APPROVAL_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const CORRELATION_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const APPLICATION_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff";
const IDEMPOTENCY_KEY = "clave-sintetica-unica";
const CREATED_AT = "2026-03-01T10:00:00Z";
const LATER_AT = "2026-03-01T10:00:01Z";
const CV_MARKER = "CV-SINTETICO-NO-DEBE-APARECER";
const SECRET_MARKER = "sk-sintetico-no-debe-aparecer";
const STORAGE_MARKER = "/private/storage/no-debe-aparecer.pdf";

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

function errorResponse(status: number, message: string, code = "http_error"): Response {
  return jsonResponse({ error: { code, message, request_id: `req-${status}` } }, status);
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

function makeAutomation(overrides: Partial<AutomationSummary> = {}): AutomationSummary {
  return {
    id: AUTOMATION_ID,
    name: "Regla sintética",
    status: "draft",
    current_version: 1,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    ...overrides,
  };
}

function makeList(items: AutomationSummary[] = [makeAutomation()], total = items.length): AutomationList {
  return { items, total, limit: 20, offset: 0 };
}

function makeDetail(overrides: Partial<AutomationDetail> = {}): AutomationDetail {
  return {
    ...makeAutomation(),
    active_version: {
      trigger: { event_type: "application.stage_changed" },
      conditions: [{ field: "to_stage", operator: "eq", value: "interview" }],
      actions: [
        {
          type: "create_task",
          payload: { template_id: null, note: null, target_stage: null },
        },
      ],
      created_at: CREATED_AT,
    },
    ...overrides,
  };
}

function makeRunSummary(overrides: Partial<AutomationRunSummary> = {}): AutomationRunSummary {
  return {
    id: RUN_ID,
    automation_id: AUTOMATION_ID,
    version: 1,
    mode: "test",
    status: "completed",
    correlation_id: CORRELATION_ID,
    trigger_event_type: "application.stage_changed",
    error_code: null,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    ...overrides,
  };
}

function makeRun(overrides: Partial<AutomationRunDetail> = {}): AutomationRunDetail {
  return {
    ...makeRunSummary(),
    started_at: CREATED_AT,
    finished_at: CREATED_AT,
    draft_ids: [],
    approval_ids: [APPROVAL_ID],
    ...overrides,
  };
}

function makeRunList(items: AutomationRunSummary[] = [makeRunSummary()]): AutomationRunList {
  return { items, total: items.length, limit: 20, offset: 0 };
}

function makeEvents(events?: AutomationRunEvent[]): AutomationRunEventList {
  return {
    items: events ?? [
      {
        event_type: "dry_run",
        created_at: CREATED_AT,
        correlation_id: CORRELATION_ID,
        payload: {
          to_stage: "interview",
          action_type: "create_task",
          correlation_id: CORRELATION_ID,
        },
      },
      {
        event_type: "action_planned",
        created_at: LATER_AT,
        correlation_id: CORRELATION_ID,
        payload: {
          cv_text: CV_MARKER,
          secret: SECRET_MARKER,
          storage_path: STORAGE_MARKER,
          template_id: SECRET_MARKER,
          decision: "approved",
        },
      },
    ],
    total: events?.length ?? 2,
    limit: 20,
    offset: 0,
  };
}

function makeApprovals(status: AutomationApprovalStatus = "pending"): AutomationApproval[] {
  return [
    {
      id: APPROVAL_ID,
      action_type: "create_message_draft",
      status,
      created_at: CREATED_AT,
      decided_at: status === "pending" ? null : LATER_AT,
    },
  ];
}

function makeTestResult(): AutomationTestResult {
  return {
    id: RUN_ID,
    automation_id: AUTOMATION_ID,
    status: "completed",
    mode: "test",
    correlation_id: CORRELATION_ID,
    event_summary: [{ event_type: "dry_run", count: 1 }],
  };
}

interface PanelOptions {
  list?: AutomationList;
  detail?: AutomationDetail;
  runs?: AutomationRunSummary[];
  run?: AutomationRunDetail;
  events?: AutomationRunEvent[];
  approvals?: AutomationApproval[];
}

function panelHandler(options: PanelOptions = {}): FetchHandler {
  const detail = options.detail ?? makeDetail();
  const run = options.run ?? makeRun();
  const detailPath = `/api/v1/automations/${AUTOMATION_ID}`;
  return (url, init) => {
    const path = url.pathname;
    if (path === "/api/v1/automations" && !init?.method) {
      return jsonResponse(options.list ?? makeList());
    }
    if (path === "/api/v1/automations" && init?.method === "POST") {
      return jsonResponse(detail, 201);
    }
    if (path === detailPath && !init?.method) return jsonResponse(detail);
    if (path === detailPath && init?.method === "PATCH") return jsonResponse(detail);
    if (path === `${detailPath}/versions` && init?.method === "POST") {
      return jsonResponse(
        { id: VERSION_ID, automation_id: AUTOMATION_ID, version: 2, created_at: CREATED_AT },
        201,
      );
    }
    if (path === `${detailPath}/test` && init?.method === "POST") {
      return jsonResponse(makeTestResult(), 201);
    }
    if (path === `${detailPath}/run` && init?.method === "POST") {
      return jsonResponse(
        { id: RUN_ID, status: "pending", queued: true, correlation_id: CORRELATION_ID },
        202,
      );
    }
    if (path === "/api/v1/automations/runs" && !init?.method) {
      return jsonResponse(makeRunList(options.runs ?? [makeRunSummary()]));
    }
    if (path === `/api/v1/automations/runs/${RUN_ID}` && !init?.method) {
      return jsonResponse(run);
    }
    if (path === `/api/v1/automations/runs/${RUN_ID}/events`) {
      return jsonResponse(makeEvents(options.events));
    }
    if (path === `/api/v1/automations/runs/${RUN_ID}/approvals`) {
      return jsonResponse(options.approvals ?? []);
    }
    return errorResponse(404, "no encontrado");
  };
}

async function openFirstAutomation(): Promise<void> {
  fireEvent.click(await screen.findByRole("button", { name: /Abrir Regla sintética/ }));
  expect(await screen.findByText("Configuración de la versión activa")).toBeTruthy();
}

function fillExecution(): void {
  fireEvent.change(screen.getByLabelText("ID de postulación"), {
    target: { value: APPLICATION_ID },
  });
  fireEvent.change(screen.getByLabelText("Clave de idempotencia"), {
    target: { value: IDEMPOTENCY_KEY },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AutomationRulePanel", () => {
  it("crea y versiona con 201, lista el detalle y no muestra PII", async () => {
    const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
    const dirtyDetail = {
      ...makeDetail(),
      cv_text: CV_MARKER,
      secret: SECRET_MARKER,
      storage_path: STORAGE_MARKER,
    } as unknown as AutomationDetail;
    const base = panelHandler({ detail: dirtyDetail });
    mockFetch((url, init) => {
      if (init?.method === "POST" && url.pathname === "/api/v1/automations") {
        posts.push({ path: url.pathname, body: parseBody(init) });
      }
      if (init?.method === "POST" && url.pathname.endsWith("/versions")) {
        posts.push({ path: url.pathname, body: parseBody(init) });
      }
      return base(url, init);
    });

    render(<AutomationRulePanel />);
    await openFirstAutomation();
    expect(screen.getAllByText("Borrador").length).toBeGreaterThan(0);
    expect(document.body.textContent ?? "").toContain("application.stage_changed");

    fireEvent.change(screen.getByLabelText("Nombre de la automatización"), {
      target: { value: "Regla sintética nueva" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear automatización" }));
    expect(await screen.findByText("Automatización creada.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Campo 1"), { target: { value: "job_status" } });
    fireEvent.change(screen.getByLabelText("Operador 1"), { target: { value: "in" } });
    const values = screen.getByLabelText("Valores 1") as HTMLSelectElement;
    for (const option of Array.from(values.options)) {
      option.selected = ["open", "paused"].includes(option.value);
    }
    fireEvent.change(values);
    fireEvent.change(screen.getByLabelText("Tipo de acción 1"), {
      target: { value: "propose_stage_change" },
    });
    fireEvent.change(screen.getByLabelText("Etapa propuesta 1"), {
      target: { value: "interview" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar versión" }));

    expect(await screen.findByText("Versión creada.")).toBeTruthy();
    expect(posts).toEqual([
      { path: "/api/v1/automations", body: { name: "Regla sintética nueva" } },
      {
        path: `/api/v1/automations/${AUTOMATION_ID}/versions`,
        body: {
          trigger: { event_type: "application.stage_changed" },
          conditions: [{ field: "job_status", operator: "in", value: ["open", "paused"] }],
          actions: [
            {
              type: "propose_stage_change",
              payload: { template_id: null, note: null, target_stage: "interview" },
            },
          ],
        },
      },
    ]);
    const text = document.body.textContent ?? "";
    for (const marker of [CV_MARKER, SECRET_MARKER, STORAGE_MARKER]) {
      expect(text).not.toContain(marker);
    }
    expect(text).not.toMatch(/score|ranking|puntuación total/i);
  });

  it("filtra por estado, pagina y distingue vacío de error 403", async () => {
    const requests: string[] = [];
    mockFetch((url) => {
      if (url.pathname === "/api/v1/automations") {
        requests.push(url.search);
        if (url.searchParams.get("status") === "active") {
          const offset = Number(url.searchParams.get("offset") ?? 0);
          return jsonResponse({
            items: [makeAutomation({ status: "active" })],
            total: 30,
            limit: 20,
            offset,
          });
        }
        return jsonResponse(makeList([], 0));
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AutomationRulePanel />);
    expect(await screen.findByText("No hay automatizaciones registradas.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Filtrar por estado"), {
      target: { value: "active" },
    });
    expect(await screen.findByRole("button", { name: /Abrir Regla sintética/ })).toBeTruthy();
    expect(screen.getByText("Página 1 de 2 · 30 registros")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Página siguiente" }));
    expect(await screen.findByText("Página 2 de 2 · 30 registros")).toBeTruthy();
    expect(requests.some((query) => query.includes("status=active"))).toBe(true);
    expect(requests.some((query) => query.includes("offset=20"))).toBe(true);

    cleanup();
    mockFetch(() => errorResponse(403, "Rol insuficiente."));
    render(<AutomationRulePanel />);
    expect((await screen.findByRole("alert")).textContent).toContain("403: Rol insuficiente.");
    expect(screen.queryByText("No hay automatizaciones registradas.")).toBeNull();
  });

  it("registra prueba 201/200 sin efectos y run 202 con queued", async () => {
    const testBodies: Array<Record<string, unknown>> = [];
    const runBodies: Array<Record<string, unknown>> = [];
    const base = panelHandler();
    const testResponses = [201, 200];
    mockFetch((url, init) => {
      if (init?.method === "POST" && url.pathname.endsWith("/test")) {
        testBodies.push(parseBody(init));
        return jsonResponse(makeTestResult(), testResponses.shift() ?? 200);
      }
      if (init?.method === "POST" && url.pathname.endsWith("/run")) {
        runBodies.push(parseBody(init));
        return jsonResponse(
          { id: RUN_ID, status: "pending", queued: true, correlation_id: CORRELATION_ID },
          202,
        );
      }
      return base(url, init);
    });

    render(<AutomationRulePanel />);
    await openFirstAutomation();
    fillExecution();

    fireEvent.click(screen.getByRole("button", { name: "Test (dry-run)" }));
    expect(await screen.findByText("Prueba registrada sin efectos externos.")).toBeTruthy();
    expect(screen.getByText("no aplica (dry-run)")).toBeTruthy();
    expect(testBodies).toEqual([
      { application_id: APPLICATION_ID, idempotency_key: IDEMPOTENCY_KEY },
    ]);

    fireEvent.change(screen.getByLabelText("Clave de idempotencia"), {
      target: { value: "clave-sintetica-repetida" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test (dry-run)" }));
    await waitFor(() => expect(testBodies).toHaveLength(2));
    expect(testBodies[1]).toEqual({
      application_id: APPLICATION_ID,
      idempotency_key: "clave-sintetica-repetida",
    });

    fireEvent.click(screen.getByRole("button", { name: "Run (live)" }));
    expect(
      await screen.findByText("Ejecución encolada (queued). El estado final lo confirma el servidor."),
    ).toBeTruthy();
    expect(screen.getByText("Queued:")).toBeTruthy();
    expect(runBodies).toEqual([
      { application_id: APPLICATION_ID, idempotency_key: "clave-sintetica-repetida" },
    ]);
  });

  it("explica el 503 del broker sin optimizar la ejecución", async () => {
    const base = panelHandler();
    mockFetch((url, init) => {
      if (init?.method === "POST" && url.pathname.endsWith("/run")) {
        return errorResponse(
          503,
          "Cola no disponible; la ejecución no se creó.",
          "broker_unavailable",
        );
      }
      return base(url, init);
    });

    render(<AutomationRulePanel />);
    await openFirstAutomation();
    fillExecution();
    fireEvent.click(screen.getByRole("button", { name: "Run (live)" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "broker no disponible, sin cambios.",
    );
    expect(screen.queryByText("Queued:")).toBeNull();
    expect(screen.queryByText(/Ejecución encolada/)).toBeNull();
  });

  it("envía PATCH de estado y respeta el 403 del servidor", async () => {
    const patches: Array<Record<string, unknown>> = [];
    let currentDetail = makeDetail();
    const base = panelHandler({ detail: currentDetail });
    mockFetch((url, init) => {
      const detailPath = `/api/v1/automations/${AUTOMATION_ID}`;
      if (url.pathname === detailPath && init?.method === "PATCH") {
        patches.push(parseBody(init));
        currentDetail = { ...currentDetail, status: parseBody(init).status as AutomationStatus };
        return jsonResponse(currentDetail);
      }
      if (url.pathname === detailPath && !init?.method) return jsonResponse(currentDetail);
      return base(url, init);
    });

    render(<AutomationRulePanel />);
    await openFirstAutomation();

    fireEvent.click(screen.getByRole("button", { name: "Activar" }));
    expect(await screen.findByText("Estado actualizado: Activa.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Desactivar" }));
    expect(await screen.findByText("Estado actualizado: Inactiva.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Archivar" }));
    expect(await screen.findByText("Estado actualizado: Archivada.")).toBeTruthy();
    expect(patches).toEqual([{ status: "active" }, { status: "inactive" }, { status: "archived" }]);
    expect((screen.getByRole("button", { name: "Archivar" }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    cleanup();
    mockFetch((url, init) => {
      if (url.pathname === `/api/v1/automations/${AUTOMATION_ID}` && init?.method === "PATCH") {
        return errorResponse(403, "Rol insuficiente.");
      }
      return panelHandler()(url, init);
    });
    render(<AutomationRulePanel />);
    await openFirstAutomation();
    fireEvent.click(screen.getByRole("button", { name: "Activar" }));
    expect((await screen.findByRole("alert")).textContent).toContain("403: Rol insuficiente.");
    expect(screen.getAllByText("Borrador").length).toBeGreaterThan(0);
  });

  it("deshabilita el envío durante una petición pendiente", async () => {
    let resolveCreate: (value: Response) => void = () => undefined;
    const base = panelHandler();
    mockFetch((url, init) => {
      if (url.pathname === "/api/v1/automations" && init?.method === "POST") {
        return new Promise<Response>((resolve) => {
          resolveCreate = resolve;
        });
      }
      return base(url, init);
    });

    render(<AutomationRulePanel />);
    expect(await screen.findByRole("button", { name: "Crear automatización" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Nombre de la automatización"), {
      target: { value: "Regla pendiente" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear automatización" }));

    expect(screen.getByText("Creando automatización…")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Creando…" }) as HTMLButtonElement).disabled,
    ).toBe(true);

    resolveCreate(jsonResponse(makeDetail(), 201));
    await screen.findByText("Automatización creada.");
  });
});

describe("AutomationRunTimeline", () => {
  it("muestra modo, estado, error, duración y payload saneado", () => {
    const onSelectRun = vi.fn();
    render(
      <AutomationRunTimeline
        runs={[makeRunSummary({ error_code: "stage_conflict", updated_at: LATER_AT })]}
        events={makeEvents().items}
        selectedRunId={RUN_ID}
        onSelectRun={onSelectRun}
      />,
    );

    expect(screen.getAllByRole("table")).toHaveLength(2);
    expect(screen.getByText("Prueba")).toBeTruthy();
    expect(screen.getByText("Completada")).toBeTruthy();
    expect(screen.getByText("stage_conflict")).toBeTruthy();
    expect(screen.getByText("1.0 s")).toBeTruthy();
    expect(screen.getAllByText(CORRELATION_ID).length).toBeGreaterThan(0);
    expect(screen.getByText("dry_run")).toBeTruthy();
    expect(screen.getByText("action_planned")).toBeTruthy();

    const text = document.body.textContent ?? "";
    expect(text).toContain('"to_stage":"interview"');
    expect(text).toContain('"decision":"approved"');
    expect(text).toContain("[dato omitido]");
    for (const marker of [CV_MARKER, SECRET_MARKER, STORAGE_MARKER]) {
      expect(text).not.toContain(marker);
    }

    fireEvent.click(screen.getByRole("button", { name: `Ver ejecución ${RUN_ID}` }));
    expect(onSelectRun).toHaveBeenCalledWith(RUN_ID);
  });

  it("distingue vacío de carga", () => {
    cleanup();
    render(<AutomationRunTimeline runs={[]} events={[]} />);
    expect(
      screen.getByText("No hay ejecuciones registradas para esta automatización."),
    ).toBeTruthy();
    expect(screen.getByText("Todavía no hay eventos para esta ejecución.")).toBeTruthy();

    cleanup();
    render(<AutomationRunTimeline runs={[]} events={[]} loading />);
    expect(screen.getByText("Cargando ejecuciones y eventos…")).toBeTruthy();
    expect(document.querySelector('section[aria-busy="true"]')).toBeTruthy();
  });
});

describe("AutomationApprovalControls", () => {
  it("registra aprobación con nota y deshabilita la decisión después", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    const onDecision = vi.fn();
    mockFetch((url, init) => {
      if (init?.method === "POST" && url.pathname.endsWith("/decide")) {
        bodies.push(parseBody(init));
        return jsonResponse({
          id: APPROVAL_ID,
          run_id: RUN_ID,
          action_type: "create_message_draft",
          status: "approved",
          decided_by: null,
          decided_at: LATER_AT,
          run_status: "waiting_approval",
        });
      }
      return errorResponse(404, "no encontrado");
    });

    render(
      <AutomationApprovalControls
        runId={RUN_ID}
        approvals={makeApprovals()}
        onDecision={onDecision}
      />,
    );
    const submit = screen.getByRole("button", {
      name: "Registrar decisión para create_message_draft",
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Decisión para create_message_draft"), {
      target: { value: "approved" },
    });
    fireEvent.change(screen.getByLabelText("Nota opcional para create_message_draft"), {
      target: { value: "Nota sintética" },
    });
    fireEvent.click(submit);

    expect(await screen.findByText("Decisión registrada: aprobada.")).toBeTruthy();
    expect(bodies).toEqual([{ decision: "approved", note: "Nota sintética" }]);
    expect(onDecision).toHaveBeenCalledWith(expect.objectContaining({ status: "approved" }));
    expect(
      screen.queryByRole("button", { name: "Registrar decisión para create_message_draft" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: /Reanudar/ })).toBeNull();
  });

  it("registra rechazo con nota vacía como null", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    mockFetch((url, init) => {
      if (init?.method === "POST" && url.pathname.endsWith("/decide")) {
        bodies.push(parseBody(init));
        return jsonResponse({
          id: APPROVAL_ID,
          run_id: RUN_ID,
          action_type: "create_message_draft",
          status: "rejected",
          decided_by: null,
          decided_at: LATER_AT,
          run_status: "failed",
        });
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AutomationApprovalControls runId={RUN_ID} approvals={makeApprovals()} />);
    fireEvent.change(screen.getByLabelText("Decisión para create_message_draft"), {
      target: { value: "rejected" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Registrar decisión para create_message_draft" }),
    );

    expect(await screen.findByText("Decisión registrada: rechazada.")).toBeTruthy();
    expect(bodies).toEqual([{ decision: "rejected", note: null }]);
  });

  it.each([
    [403, "Rol insuficiente."],
    [404, "Recurso de otra organización no encontrado."],
  ])("muestra el error %i del servidor sin decidir localmente", async (status, message) => {
    mockFetch((url) => {
      if (url.pathname.endsWith("/decide")) return errorResponse(status, message);
      return errorResponse(404, "no encontrado");
    });

    render(<AutomationApprovalControls runId={RUN_ID} approvals={makeApprovals()} />);
    fireEvent.change(screen.getByLabelText("Decisión para create_message_draft"), {
      target: { value: "rejected" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Registrar decisión para create_message_draft" }),
    );

    expect((await screen.findByRole("alert")).textContent).toContain(`${status}: ${message}`);
    expect(
      screen.getByRole("button", { name: "Registrar decisión para create_message_draft" }),
    ).toBeTruthy();
    expect(screen.getByText("Pendiente")).toBeTruthy();
  });

  it("cancela sólo tras confirmación explícita", async () => {
    const confirmMock = vi.fn(() => false);
    vi.stubGlobal("confirm", confirmMock);
    const posts: string[] = [];
    const onRunChange = vi.fn();
    mockFetch((url, init) => {
      if (url.pathname === `/api/v1/automations/runs/${RUN_ID}/cancel`) {
        posts.push(String(init?.method));
        return jsonResponse(makeRun({ status: "cancelled" }));
      }
      return errorResponse(404, "no encontrado");
    });

    render(
      <AutomationApprovalControls
        runId={RUN_ID}
        approvals={makeApprovals("approved")}
        onRunChange={onRunChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancelar ejecución" }));
    expect(posts).toHaveLength(0);
    expect(confirmMock).toHaveBeenCalledTimes(1);

    confirmMock.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar ejecución" }));
    expect(await screen.findByText("Ejecución cancelada.")).toBeTruthy();
    expect(posts).toEqual(["POST"]);
    expect(onRunChange).toHaveBeenCalledWith(expect.objectContaining({ status: "cancelled" }));
  });
});
