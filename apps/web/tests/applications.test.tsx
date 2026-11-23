import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PipelineBoard } from "../src/components/PipelineBoard";
import type { Application } from "../src/lib/types";

type FetchHandler = (url: URL, init?: RequestInit) => Response;

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

function errorResponse(status: number, message: string): Response {
  return jsonResponse(
    { error: { code: "http_error", message, request_id: `req-${status}` } },
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

function makeApplication(id: string, stage: Application["stage"]): Application {
  return {
    id,
    job_id: "job-1",
    candidate_id: "cand-1",
    stage,
    source: "manual",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("PipelineBoard", () => {
  it("carga columnas por etapa, filtra y pagina", async () => {
    const fetchMock = mockFetch((url) => {
      expect(url.pathname).toBe("/api/v1/applications");
      return jsonResponse({
        items: [
          makeApplication("app-1", "applied"),
          makeApplication("app-2", "screening"),
        ],
        total: 25,
        limit: 20,
        offset: Number(url.searchParams.get("offset") ?? 0),
      });
    });

    render(<PipelineBoard />);

    expect(await screen.findByText("Postulación app-1")).toBeTruthy();
    expect(screen.getByText("Postulación app-2")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Etapa applied" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Etapa rejected" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("ID de vacante (UUID)"), {
      target: { value: "job-1" },
    });
    fireEvent.change(screen.getByLabelText("Etapa"), { target: { value: "screening" } });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    const filteredUrl = new URL(String(fetchMock.mock.calls[1]?.[0]));
    expect(filteredUrl.searchParams.get("job_id")).toBe("job-1");
    expect(filteredUrl.searchParams.get("stage")).toBe("screening");

    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });
    expect(new URL(String(fetchMock.mock.calls[2]?.[0])).searchParams.get("offset")).toBe("20");
  });

  it("muestra conflicto 409 del backend sin mover la postulación", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (init?.method === "POST") {
        return errorResponse(409, "Conflicto con el estado actual.");
      }
      return jsonResponse({
        items: [makeApplication("app-1", "applied")],
        total: 1,
        limit: 20,
        offset: 0,
      });
    });

    render(<PipelineBoard />);
    expect(await screen.findByText("Postulación app-1")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Etapa destino para app-1"), {
      target: { value: "offer" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Avanzar etapa de postulación app-1" }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("(409):");
    expect(alert.textContent).toContain("Conflicto con el estado actual.");
    const appliedColumn = screen.getByRole("region", { name: "Etapa applied" });
    expect(within(appliedColumn).getByText("Postulación app-1")).toBeTruthy();

    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(postCall?.[0]).toBe("http://localhost:8000/api/v1/applications/app-1/stage");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({ to_stage: "offer" });
  });

  it("muestra permisos insuficientes 403 del backend", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (init?.method === "POST") {
        return errorResponse(403, "Rol insuficiente.");
      }
      return jsonResponse({
        items: [makeApplication("app-1", "applied")],
        total: 1,
        limit: 20,
        offset: 0,
      });
    });

    render(<PipelineBoard />);
    expect(await screen.findByText("Postulación app-1")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Etapa destino para app-1"), {
      target: { value: "screening" },
    });
    fireEvent.change(screen.getByLabelText("Nota para app-1"), {
      target: { value: "Nota sintética." },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Avanzar etapa de postulación app-1" }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("(403):");
    expect(alert.textContent).toContain("Rol insuficiente.");
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      to_stage: "screening",
      note: "Nota sintética.",
    });
  });
});
