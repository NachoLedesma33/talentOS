import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ACTIVE_ORG_STORAGE_KEY } from "../src/lib/api";
import AnalyticsPage, { type AnalyticsOverview, type MetricDefinition } from "../src/app/analytics/page";

type FetchHandler = (url: URL, init?: RequestInit) => Response | Promise<Response>;

const ORG_ID = "org-analitica";
const GENERATED_AT = "2026-01-02T03:04:05Z";

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

function errorResponse(status: number, message: string): Response {
  return jsonResponse(
    { error: { code: "forbidden", message, request_id: "req-analytics" } },
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

function makeDefinition(
  key: string,
  name: string,
  isEstimate = false,
  unit = "count",
): MetricDefinition {
  return {
    key,
    name,
    description: `Definición sintética de ${key}.`,
    unit,
    is_estimate: isEstimate,
  };
}

const PIPELINE_DEFINITIONS: MetricDefinition[] = [
  makeDefinition("jobs_open", "Vacantes abiertas"),
  makeDefinition("jobs_closed", "Vacantes cerradas"),
  makeDefinition("candidates_by_stage", "Candidatos por etapa"),
  makeDefinition("time_in_stage", "Tiempo por etapa", true, "days"),
  makeDefinition("conversion", "Conversión entre etapas", false, "ratio"),
  makeDefinition("total_process_days", "Tiempo total de proceso", true, "days"),
];

const OPERATIONAL_DEFINITIONS: MetricDefinition[] = [
  makeDefinition("assessments_pending_review", "Evaluaciones pendientes de revisión"),
  makeDefinition("agent_runs_completed", "Ejecuciones de agentes exitosas"),
  makeDefinition("agent_runs_failed", "Ejecuciones de agentes fallidas"),
  makeDefinition("automation_runs_executed", "Automatizaciones ejecutadas"),
  makeDefinition("estimated_minutes_saved", "Tiempo estimado ahorrado", true, "minutes"),
];

function makeOverview(empty = false): AnalyticsOverview {
  const count = empty ? 0 : 2;
  return {
    generated_at: GENERATED_AT,
    pipeline: {
      generated_at: GENERATED_AT,
      jobs_open: count,
      jobs_closed: empty ? 0 : 1,
      stages: [
        {
          stage: "applied",
          applications: count,
          arrivals: count,
          exits: empty ? 0 : 1,
          avg_days_in_stage: empty ? null : 1.5,
          total_days_in_stage: empty ? 0 : 3,
        },
        {
          stage: "screening",
          applications: empty ? 0 : 1,
          arrivals: empty ? 0 : 1,
          exits: 0,
          avg_days_in_stage: null,
          total_days_in_stage: 0,
        },
        {
          stage: "interview",
          applications: 0,
          arrivals: 0,
          exits: 0,
          avg_days_in_stage: null,
          total_days_in_stage: 0,
        },
        {
          stage: "offer",
          applications: 0,
          arrivals: 0,
          exits: 0,
          avg_days_in_stage: null,
          total_days_in_stage: 0,
        },
        {
          stage: "hired",
          applications: 0,
          arrivals: 0,
          exits: 0,
          avg_days_in_stage: null,
          total_days_in_stage: 0,
        },
        {
          stage: "rejected",
          applications: 0,
          arrivals: 0,
          exits: 0,
          avg_days_in_stage: null,
          total_days_in_stage: 0,
        },
      ],
      conversions: [
        { key: "conversion.applied.screening", value: 0.5, unit: "ratio", is_estimate: false },
      ],
      avg_process_days: empty ? null : 2.25,
      definitions: PIPELINE_DEFINITIONS,
    },
    operational: {
      generated_at: GENERATED_AT,
      assessments_pending_review: count,
      agent_runs_completed: count,
      agent_runs_failed: empty ? 0 : 1,
      automation_runs_executed: count,
      estimated_minutes_saved: empty ? 0 : 10,
      estimates_basis: "5 min por ejecución live completada; supuesto no medido, sin coste monetario",
      definitions: OPERATIONAL_DEFINITIONS,
    },
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("AnalyticsPage", () => {
  it("consulta bajo demanda, envía la organización activa y marca estimados", async () => {
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, ORG_ID);
    const headers: Array<string | null> = [];
    const fetchMock = mockFetch((url, init) => {
      expect(url.pathname).toBe("/api/v1/analytics/overview");
      headers.push(new Headers(init?.headers).get("X-Organization-ID"));
      return jsonResponse(makeOverview());
    });

    render(<AnalyticsPage />);
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Consultar métricas" }));

    expect((await screen.findAllByText("Vacantes abiertas")).length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(headers).toEqual([ORG_ID]);
    expect(screen.getAllByText("2", { selector: "p.text-xl" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Estimado").length).toBeGreaterThan(0);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("Postuladas")).toBeTruthy();
    expect(screen.getByText("1.50")).toBeTruthy();
    expect(screen.getByText("0.50")).toBeTruthy();
    expect(screen.getByText(/Generado:/).textContent).toContain("2026-01-02T03:04:05.000Z");
  });

  it("muestra estado vacío cuando el tenant no tiene datos", async () => {
    mockFetch(() => jsonResponse(makeOverview(true)));

    render(<AnalyticsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Consultar métricas" }));

    expect(
      await screen.findByText("Sin datos para la organización activa en este momento."),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("button", { name: "Actualizar métricas" })).toBeTruthy();
  });

  it("muestra error y permite reintentar", async () => {
    let attempts = 0;
    const fetchMock = mockFetch(() => {
      attempts += 1;
      return attempts === 1
        ? errorResponse(403, "Sin acceso al tenant")
        : jsonResponse(makeOverview());
    });

    render(<AnalyticsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Consultar métricas" }));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("403: Sin acceso al tenant")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect((await screen.findAllByText("Vacantes abiertas")).length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
