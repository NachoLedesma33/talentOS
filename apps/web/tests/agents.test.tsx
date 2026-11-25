import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentApprovalControls } from "../src/components/AgentApprovalControls";
import { AgentRunPanel } from "../src/components/AgentRunPanel";
import type {
  AgentEventList,
  AgentRun,
  Approval,
} from "../src/lib/types";

type FetchHandler = (url: URL, init?: RequestInit) => Response | Promise<Response>;

const APPLICATION_ID = "11111111-1111-4111-8111-111111111111";
const RUN_ID = "22222222-2222-4222-8222-222222222222";
const APPROVAL_ID = "33333333-3333-4333-8333-333333333333";
const CORRELATION_ID = "44444444-4444-4444-8444-444444444444";
const JOB_ID = "55555555-5555-4555-8555-555555555555";
const CANDIDATE_ID = "66666666-6666-4666-8666-666666666666";
const CREATED_AT = "2026-01-01T00:00:00Z";
const IDEMPOTENCY_KEY = "clave-sintetica-unica";
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

function makeRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: RUN_ID,
    workflow: "matching_review",
    version: "1.0.0",
    status: "waiting_approval",
    correlation_id: CORRELATION_ID,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    output_ref: "draft:sintetico",
    job_id: JOB_ID,
    candidate_id: CANDIDATE_ID,
    event_summary: [{ event_type: "run.created", count: 1 }],
    event_count: 3,
    ...overrides,
  };
}

function makeEvents(): AgentEventList {
  return {
    items: [
      {
        event_type: "run.waiting_approval",
        created_at: CREATED_AT,
        correlation_id: CORRELATION_ID,
        payload: {
          node: "matching_review_node",
          duration_ms: 41,
          attempts: 3,
          error_type: "timeout_error",
          correlation_id: CORRELATION_ID,
        },
      },
      {
        event_type: "tool.invoked",
        created_at: CREATED_AT,
        correlation_id: CORRELATION_ID,
        payload: {
          cv_text: CV_MARKER,
          secret: SECRET_MARKER,
          storage_path: STORAGE_MARKER,
          decision: "approved",
          tool: "create_assessment_draft",
          statuses_summary: [{ status: "supported", count: 1 }],
          template: "initial_contact",
          char_count: 91,
        },
      },
    ],
    total: 2,
    limit: 50,
    offset: 0,
  };
}

function makeApprovals(status: Approval["status"] = "pending"): Approval[] {
  return [
    {
      id: APPROVAL_ID,
      action_type: "create_assessment",
      status,
      created_at: CREATED_AT,
      decided_at: status === "pending" ? null : CREATED_AT,
    },
  ];
}

function fillAgentForm() {
  fireEvent.change(screen.getByLabelText("ID de postulación"), {
    target: { value: APPLICATION_ID },
  });
  fireEvent.change(screen.getByLabelText("Clave de idempotencia"), {
    target: { value: IDEMPOTENCY_KEY },
  });
}

function submitForm(buttonName: string) {
  fireEvent.submit(screen.getByRole("button", { name: buttonName }).closest("form")!);
}

function isDisabled(name: string): boolean {
  return (screen.getByRole("button", { name }) as HTMLButtonElement).disabled;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentRunPanel", () => {
  it("crea con 201, carga detalle y eventos saneados, y marca revisión requerida", async () => {
    const posts: Array<Record<string, unknown>> = [];
    mockFetch((url, init) => {
      if (url.pathname === "/api/v1/agents/runs" && init?.method === "POST") {
        posts.push(parseBody(init));
        return jsonResponse(makeRun(), 201);
      }
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}`) return jsonResponse(makeRun());
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/events`) return jsonResponse(makeEvents());
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/approvals`) {
        return jsonResponse(makeApprovals());
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AgentRunPanel />);
    expect(
      screen.getByText(
        "Ingresa una postulación y una clave de idempotencia para inspeccionar una ejecución.",
      ),
    ).toBeTruthy();

    fillAgentForm();
    submitForm("Iniciar ejecución");

    expect(await screen.findByText("Ejecución cargada.")).toBeTruthy();
    expect(posts).toEqual([
      { application_id: APPLICATION_ID, idempotency_key: IDEMPOTENCY_KEY },
    ]);
    expect(screen.getByText("matching_review")).toBeTruthy();
    expect(screen.getByText("1.0.0")).toBeTruthy();
    expect(screen.getAllByText("Esperando aprobación").length).toBeGreaterThan(0);
    expect(screen.getAllByText(CORRELATION_ID).length).toBeGreaterThan(0);
    expect(screen.getAllByText("draft:sintetico").length).toBeGreaterThan(0);
    expect(screen.getByText(/review_required: revisión humana requerida/)).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("run.waiting_approval")).toBeTruthy();
    expect(screen.getByText("tool.invoked")).toBeTruthy();
    expect(screen.getByText("matching_review_node")).toBeTruthy();
    expect(screen.getByText("41")).toBeTruthy();
    expect(screen.getByText("timeout_error")).toBeTruthy();
    const text = document.body.textContent ?? "";
    expect(text).toContain("attempts: 3");
    expect(text).toContain('"decision":"approved"');
    expect(text).toContain('"tool":"create_assessment_draft"');
    expect(text).toContain('"statuses_summary":"[{\\"status\\":\\"supported\\",\\"count\\":1}]"');
    expect(text).toContain('"template":"initial_contact"');
    expect(text).toContain('"char_count":"91"');
    for (const marker of [CV_MARKER, SECRET_MARKER, STORAGE_MARKER]) {
      expect(text).not.toContain(marker);
    }
    expect(text).not.toMatch(/score|ranking|puntuación total/i);
  });

  it("lista ejecuciones con filtros y carga la selección", async () => {
    const queries: string[] = [];
    mockFetch((url) => {
      if (url.pathname === "/api/v1/agents/runs") {
        queries.push(url.search);
        return jsonResponse({ items: [makeRun()], total: 1, limit: 50, offset: 0 });
      }
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}`) return jsonResponse(makeRun());
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/events`) {
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
      }
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/approvals`) return jsonResponse([]);
      return errorResponse(404, "no encontrado");
    });

    render(<AgentRunPanel />);
    fireEvent.change(screen.getByLabelText("Estado (filtro)"), {
      target: { value: "waiting_approval" },
    });
    fireEvent.change(screen.getByLabelText("Agente (filtro)"), {
      target: { value: "matching_review" },
    });
    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("Hasta"), { target: { value: "2026-01-02" } });
    fireEvent.change(screen.getByLabelText("Vacante (ID)"), {
      target: { value: "55555555-5555-4555-8555-555555555555" },
    });
    fireEvent.change(screen.getByLabelText("Candidato (ID)"), {
      target: { value: "66666666-6666-4666-8666-666666666666" },
    });
    submitForm("Buscar ejecuciones");

    expect(await screen.findByRole("button", { name: RUN_ID })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Vacante" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Candidato" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: JOB_ID })).toBeTruthy();
    expect(screen.getByRole("cell", { name: CANDIDATE_ID })).toBeTruthy();
    const params = new URLSearchParams(queries[0]);
    expect(params.get("status")).toBe("waiting_approval");
    expect(params.get("agent")).toBe("matching_review");
    expect(params.get("date_from")).toBe("2026-01-01");
    expect(params.get("date_to")).toBe("2026-01-02");
    expect(params.get("job_id")).toBe("55555555-5555-4555-8555-555555555555");
    expect(params.get("candidate_id")).toBe("66666666-6666-4666-8666-666666666666");

    fireEvent.click(screen.getByRole("button", { name: RUN_ID }));
    expect(await screen.findByText("Detalle de la ejecución")).toBeTruthy();
  });

  it("acepta una ejecución repetida con 200 sin marcar revisión", async () => {
    mockFetch((url) => {
      if (url.pathname === "/api/v1/agents/runs") {
        return jsonResponse(makeRun({ status: "completed", output_ref: null }), 200);
      }
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}`) {
        return jsonResponse(makeRun({ status: "completed", output_ref: null }));
      }
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/events`) {
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
      }
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/approvals`) return jsonResponse([]);
      return errorResponse(404, "no encontrado");
    });

    render(<AgentRunPanel />);
    fillAgentForm();
    submitForm("Iniciar ejecución");

    expect(await screen.findByText("Ejecución cargada.")).toBeTruthy();
    expect(screen.getAllByText("Completada").length).toBeGreaterThan(0);
    expect(screen.queryByText(/review_required:/)).toBeNull();
    expect(screen.queryByText("Output ref:")).toBeNull();
    expect(screen.getByText("Todavía no hay eventos para esta ejecución.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each([
    [403, "Rol insuficiente."],
    [404, "Ejecución no encontrada."],
  ])("anuncia el error %i devuelto por el servidor", async (status, message) => {
    mockFetch(() => errorResponse(status, message));

    render(<AgentRunPanel />);
    fillAgentForm();
    submitForm("Iniciar ejecución");

    expect((await screen.findByRole("alert")).textContent).toContain(`${status}: ${message}`);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("deshabilita el envío mientras la petición está pendiente", async () => {
    let resolveStart: (value: Response) => void = () => undefined;
    mockFetch((url) => {
      if (url.pathname === "/api/v1/agents/runs") {
        return new Promise<Response>((resolve) => {
          resolveStart = resolve;
        });
      }
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}`) return jsonResponse(makeRun());
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/events`) return jsonResponse(makeEvents());
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/approvals`) {
        return jsonResponse(makeApprovals());
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AgentRunPanel />);
    fillAgentForm();
    submitForm("Iniciar ejecución");

    expect(isDisabled("Iniciando…")).toBe(true);
    expect(screen.getByText("Iniciando ejecución…")).toBeTruthy();

    resolveStart(jsonResponse(makeRun(), 201));
    await waitFor(() => expect(isDisabled("Iniciar ejecución")).toBe(false));
  });
});

describe("AgentApprovalControls", () => {
  it("registra la decisión en el servidor y habilita reanudar solo después", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    mockFetch((url, init) => {
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/approvals/${APPROVAL_ID}/decide`) {
        expect(init?.method).toBe("POST");
        bodies.push(parseBody(init));
        return jsonResponse(makeRun({ status: "completed" }));
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AgentApprovalControls runId={RUN_ID} approvals={makeApprovals()} />);
    expect(isDisabled("Reanudar ejecución")).toBe(true);
    expect(screen.getByText("Registra una decisión antes de reanudar.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Decisión para create_assessment"), {
      target: { value: "rejected" },
    });
    fireEvent.change(screen.getByLabelText("Nota opcional para create_assessment"), {
      target: { value: "Nota sintética" },
    });
    submitForm("Registrar decisión para create_assessment");

    expect(await screen.findByText("Decisión registrada: rechazada.")).toBeTruthy();
    expect(bodies).toEqual([{ decision: "rejected", note: "Nota sintética" }]);
    expect(isDisabled("Reanudar ejecución")).toBe(false);
    expect(screen.queryByRole("button", { name: /Registrar decisión/ })).toBeNull();
  });

  it("muestra queued quando el servidor responde 202 al reanudar", async () => {
    const calls = vi.fn();
    mockFetch((url, init) => {
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/resume`) {
        calls(init?.method, init?.body);
        return jsonResponse(
          {
            agent_run_id: RUN_ID,
            status: "running",
            queued: true,
            correlation_id: CORRELATION_ID,
          },
          202,
        );
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AgentApprovalControls runId={RUN_ID} approvals={makeApprovals("approved")} />);
    fireEvent.click(screen.getByRole("button", { name: "Reanudar ejecución" }));

    expect(await screen.findByText(/Reanudación encolada \(queued\)/)).toBeTruthy();
    expect(calls).toHaveBeenCalledWith("POST", undefined);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("explica el 503 del broker sin optimizar el estado", async () => {
    mockFetch((url) => {
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/resume`) {
        return errorResponse(
          503,
          "Cola no disponible; la ejecución no cambió de estado.",
          "broker_unavailable",
        );
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AgentApprovalControls runId={RUN_ID} approvals={makeApprovals("approved")} />);
    fireEvent.click(screen.getByRole("button", { name: "Reanudar ejecución" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "broker no disponible, sin cambios.",
    );
    expect(screen.queryByText(/Reanudación encolada/)).toBeNull();
    expect(isDisabled("Reanudar ejecución")).toBe(false);
  });

  it("muestra el 403 del servidor sin registrar la decisión localmente", async () => {
    mockFetch((url) => {
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/approvals/${APPROVAL_ID}/decide`) {
        return errorResponse(403, "Rol insuficiente.");
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AgentApprovalControls runId={RUN_ID} approvals={makeApprovals()} />);
    submitForm("Registrar decisión para create_assessment");

    expect((await screen.findByRole("alert")).textContent).toContain("403: Rol insuficiente.");
    expect(screen.getByRole("button", { name: /Registrar decisión/ })).toBeTruthy();
    expect(isDisabled("Reanudar ejecución")).toBe(true);
  });

  it("muestra el 404 cross-tenant al cancelar", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    mockFetch((url) => {
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/cancel`) {
        return errorResponse(404, "Ejecución o aprobación no encontrada.");
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AgentApprovalControls runId={RUN_ID} approvals={makeApprovals("approved")} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar ejecución" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "404: Ejecución o aprobación no encontrada.",
    );
  });

  it("cancela solo después de confirmación explícita", async () => {
    const confirmMock = vi.fn(() => false);
    vi.stubGlobal("confirm", confirmMock);
    const posts: string[] = [];
    mockFetch((url, init) => {
      if (url.pathname === `/api/v1/agents/runs/${RUN_ID}/cancel`) {
        posts.push(String(init?.method));
        return jsonResponse(makeRun({ status: "cancelled" }));
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AgentApprovalControls runId={RUN_ID} approvals={makeApprovals("approved")} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar ejecución" }));
    expect(posts).toHaveLength(0);
    expect(confirmMock).toHaveBeenCalledTimes(1);

    confirmMock.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar ejecución" }));

    expect(await screen.findByText("Ejecución cancelada.")).toBeTruthy();
    expect(posts).toEqual(["POST"]);
    expect(confirmMock).toHaveBeenCalledTimes(2);
  });
});
