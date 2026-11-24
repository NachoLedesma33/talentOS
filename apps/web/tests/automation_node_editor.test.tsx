import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AutomationNodeEditor,
  MAX_ACTIONS,
  MAX_CONDITIONS,
  buildAutomationVersionPayload,
  createAutomationAction,
  createAutomationCondition,
  type AutomationNodeEditorValue,
} from "../src/components/AutomationNodeEditor";
import { AutomationRulePanel } from "../src/components/AutomationRulePanel";
import type {
  AutomationAction,
  AutomationCondition,
  AutomationDetail,
  AutomationVersionCreate,
} from "../src/lib/types";

type FetchHandler = (url: URL, init?: RequestInit) => Response;

const AUTOMATION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const VERSION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const CREATED_AT = "2026-03-01T10:00:00Z";

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

function errorResponse(status: number, message: string): Response {
  return jsonResponse({ error: { code: "http_error", message, request_id: "req-sintetico" } }, status);
}

function mockFetch(handler: FetchHandler) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    return handler(new URL(String(input)), init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body)) as Record<string, unknown>;
}

function makeValue(
  conditions: AutomationCondition[] = [createAutomationCondition()],
  actions: AutomationAction[] = [createAutomationAction()],
): AutomationNodeEditorValue {
  return { trigger: { event_type: "application.stage_changed" }, conditions, actions };
}

interface HarnessProps {
  initial: AutomationNodeEditorValue;
  onChange?: (value: AutomationNodeEditorValue) => void;
}

function EditorHarness({ initial, onChange }: HarnessProps) {
  const [value, setValue] = useState(initial);
  return (
    <div>
      <AutomationNodeEditor
        value={value}
        onChange={(next) => {
          setValue(next);
          onChange?.(next);
        }}
      />
      <div data-testid="version-payload">{JSON.stringify(buildAutomationVersionPayload(value))}</div>
    </div>
  );
}

function payloadFromScreen(): AutomationVersionCreate {
  return JSON.parse(screen.getByTestId("version-payload").textContent ?? "") as AutomationVersionCreate;
}

function selectValues(select: HTMLSelectElement, values: string[]): void {
  for (const option of Array.from(select.options)) {
    option.selected = values.includes(option.value);
  }
  fireEvent.change(select);
}

function makeDetail(): AutomationDetail {
  return {
    id: AUTOMATION_ID,
    name: "Regla sintética",
    status: "draft",
    current_version: 1,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    active_version: {
      trigger: { event_type: "application.stage_changed" },
      conditions: [],
      actions: [],
      created_at: CREATED_AT,
    },
  };
}

function panelHandler(): FetchHandler {
  const detail = makeDetail();
  const detailPath = `/api/v1/automations/${AUTOMATION_ID}`;
  return (url, init) => {
    const path = url.pathname;
    if (path === "/api/v1/automations" && !init?.method) {
      return jsonResponse({ items: [detail], total: 1, limit: 20, offset: 0 });
    }
    if (path === detailPath && !init?.method) return jsonResponse(detail);
    if (path === `${detailPath}/versions` && init?.method === "POST") {
      return jsonResponse(
        { id: VERSION_ID, automation_id: AUTOMATION_ID, version: 2, created_at: CREATED_AT },
        201,
      );
    }
    if (path === "/api/v1/automations/runs" && !init?.method) {
      return jsonResponse({ items: [], total: 0, limit: 20, offset: 0 });
    }
    return errorResponse(404, "no encontrado");
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AutomationNodeEditor", () => {
  it("muestra nodos y conectores en orden disparador, condiciones, acciones y resultado", () => {
    const { container } = render(<EditorHarness initial={makeValue()} />);

    expect(
      Array.from(container.querySelectorAll('[role="group"]')).map((node) =>
        node.getAttribute("aria-label"),
      ),
    ).toEqual(["Disparador", "Condición 1 de 1", "Acción 1 de 1", "Resultado"]);
    expect(container.querySelectorAll('[data-testid="automation-node-connector"]')).toHaveLength(3);
    expect(screen.getByRole("region", { name: "Editor visual de nodos" })).toBeTruthy();
    expect(container.querySelector("svg")).toBeTruthy();
    expect(container.querySelector("input")).toBeNull();
  });

  it("añade, edita y elimina condiciones emitiendo el snapshot esperado", () => {
    const onChange = vi.fn();
    render(<EditorHarness initial={makeValue()} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Añadir condición" }));
    expect(screen.getByRole("group", { name: "Condición 2 de 2" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Campo 2"), { target: { value: "job_status" } });
    fireEvent.change(screen.getByLabelText("Operador 2"), { target: { value: "in" } });
    selectValues(screen.getByLabelText("Valores 2") as HTMLSelectElement, ["open", "paused"]);

    expect(payloadFromScreen().conditions).toEqual([
      { field: "to_stage", operator: "eq", value: "interview" },
      { field: "job_status", operator: "in", value: ["open", "paused"] },
    ]);
    expect(onChange).toHaveBeenCalled();
    expect(screen.getByRole("status").textContent).toContain("Condición 2 actualizada.");

    fireEvent.click(screen.getByRole("button", { name: "Eliminar condición 2" }));
    expect(screen.queryByRole("group", { name: /Condición 2 de/ })).toBeNull();
    expect(payloadFromScreen().conditions).toHaveLength(1);
    expect(screen.getByRole("status").textContent).toContain("Condición 2 eliminada.");
  });

  it("añade, reordena y elimina acciones respetando el orden del DOM", () => {
    render(<EditorHarness initial={makeValue()} />);

    fireEvent.click(screen.getByRole("button", { name: "Añadir acción" }));
    expect(screen.getByRole("group", { name: "Acción 2 de 2" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Tipo de acción 2"), {
      target: { value: "propose_stage_change" },
    });
    fireEvent.change(screen.getByLabelText("Etapa propuesta 2"), { target: { value: "offer" } });
    expect(payloadFromScreen().actions.map((action) => action.type)).toEqual([
      "create_task",
      "propose_stage_change",
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Subir acción 2" }));
    expect(payloadFromScreen().actions.map((action) => action.type)).toEqual([
      "propose_stage_change",
      "create_task",
    ]);
    expect(screen.getByRole("status").textContent).toContain("Acción 2 movida arriba.");

    fireEvent.click(screen.getByRole("button", { name: "Bajar acción 1" }));
    expect(payloadFromScreen().actions.map((action) => action.type)).toEqual([
      "create_task",
      "propose_stage_change",
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Eliminar acción 1" }));
    expect(screen.queryByRole("group", { name: /Acción 2 de/ })).toBeNull();
    expect(payloadFromScreen().actions).toEqual([
      {
        type: "propose_stage_change",
        payload: { template_id: null, note: null, target_stage: "offer" },
      },
    ]);
    expect(
      (screen.getByRole("button", { name: "Subir acción 1" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Bajar acción 1" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("deshabilita altas y movimientos al alcanzar los límites", () => {
    const conditions = Array.from({ length: MAX_CONDITIONS - 1 }, () => createAutomationCondition());
    const actions = Array.from({ length: MAX_ACTIONS - 1 }, () => createAutomationAction());
    render(<EditorHarness initial={makeValue(conditions, actions)} />);

    const addCondition = screen.getByRole("button", {
      name: "Añadir condición",
    }) as HTMLButtonElement;
    const addAction = screen.getByRole("button", { name: "Añadir acción" }) as HTMLButtonElement;
    expect(addCondition.disabled).toBe(false);
    expect(addAction.disabled).toBe(false);

    fireEvent.click(addCondition);
    fireEvent.click(addAction);

    expect(payloadFromScreen().conditions).toHaveLength(MAX_CONDITIONS);
    expect(payloadFromScreen().actions).toHaveLength(MAX_ACTIONS);
    expect(addCondition.disabled).toBe(true);
    expect(addAction.disabled).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Subir acción 1" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: `Bajar acción ${MAX_ACTIONS}` }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("serializa exactamente el payload del contrato POST /versions sin PII", () => {
    const conditions: AutomationCondition[] = [
      { field: "to_stage", operator: "eq", value: "interview" },
      { field: "job_status", operator: "in", value: ["open", "paused"] },
    ];
    const actions: AutomationAction[] = [
      createAutomationAction(),
      {
        type: "propose_stage_change",
        payload: { template_id: null, note: null, target_stage: "offer" },
      },
    ];
    const { container } = render(<EditorHarness initial={makeValue(conditions, actions)} />);

    expect(payloadFromScreen()).toEqual({
      trigger: { event_type: "application.stage_changed" },
      conditions: [
        { field: "to_stage", operator: "eq", value: "interview" },
        { field: "job_status", operator: "in", value: ["open", "paused"] },
      ],
      actions: [
        {
          type: "create_task",
          payload: { template_id: null, note: null, target_stage: null },
        },
        {
          type: "propose_stage_change",
          payload: { template_id: null, note: null, target_stage: "offer" },
        },
      ],
    });
    expect(screen.getByTestId("version-payload").textContent ?? "").not.toMatch(
      /@|https?:\/\/|www\./,
    );
    expect(container.textContent ?? "").not.toMatch(/@|https?:\/\/|www\./);
  });

  it("expone estados vacío y error accesibles sin campos libres", () => {
    const { container } = render(<EditorHarness initial={makeValue([], [])} />);

    expect(screen.getByRole("group", { name: "Disparador" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Resultado" })).toBeTruthy();
    expect(screen.getByText("Sin condiciones: el disparo se evalúa sin filtros adicionales.")).toBeTruthy();
    expect(screen.getByText("Sin acciones: añade al menos una antes de guardar.")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Añade al menos una acción");

    fireEvent.click(screen.getByRole("button", { name: "Añadir acción" }));
    fireEvent.change(screen.getByLabelText("Tipo de acción 1"), {
      target: { value: "propose_stage_change" },
    });
    expect(screen.getByRole("alert").textContent).toContain("Selecciona la etapa propuesta");

    fireEvent.change(screen.getByLabelText("Etapa propuesta 1"), { target: { value: "screening" } });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Acción 1 actualizada.");
    expect(container.querySelector("input")).toBeNull();
  });
});

describe("Integración del editor visual en AutomationRulePanel", () => {
  it("alterna entre editor y formulario con un único POST de versión", async () => {
    const versionPosts: Array<Record<string, unknown>> = [];
    const base = panelHandler();
    mockFetch((url, init) => {
      if (init?.method === "POST" && url.pathname.endsWith("/versions")) {
        versionPosts.push(parseBody(init));
      }
      return base(url, init);
    });

    render(<AutomationRulePanel />);
    fireEvent.click(await screen.findByRole("button", { name: /Abrir Regla sintética/ }));
    await screen.findByText("Configuración de la versión activa");

    const visualToggle = screen.getByRole("button", { name: "Editor visual" });
    expect(visualToggle.getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByRole("region", { name: "Editor visual de nodos" })).toBeNull();
    fireEvent.click(visualToggle);
    expect(visualToggle.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("region", { name: "Editor visual de nodos" })).toBeTruthy();
    expect(screen.queryByText("Condiciones")).toBeNull();
    expect(versionPosts).toHaveLength(0);

    fireEvent.change(screen.getByLabelText("Campo 1"), { target: { value: "job_status" } });
    fireEvent.change(screen.getByLabelText("Operador 1"), { target: { value: "in" } });
    selectValues(screen.getByLabelText("Valores 1") as HTMLSelectElement, ["open"]);
    expect(versionPosts).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Guardar versión" }));
    expect(await screen.findByText("Versión creada.")).toBeTruthy();
    expect(versionPosts).toEqual([
      {
        trigger: { event_type: "application.stage_changed" },
        conditions: [{ field: "job_status", operator: "in", value: ["open"] }],
        actions: [
          {
            type: "create_task",
            payload: { template_id: null, note: null, target_stage: null },
          },
        ],
      },
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Formulario" }));
    expect(screen.queryByRole("region", { name: "Editor visual de nodos" })).toBeNull();
    expect(screen.getByText("Condiciones")).toBeTruthy();
    expect(screen.getByLabelText("Campo 1")).toBeTruthy();
    expect(versionPosts).toHaveLength(1);
  });
});
