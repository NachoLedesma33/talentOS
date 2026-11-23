import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobsPanel } from "../src/components/JobsPanel";
import type { Job } from "../src/lib/types";

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

function makeJob(id: string, title: string): Job {
  return {
    id,
    title,
    description: "Puesto sintético de prueba.",
    status: "draft",
    modality: "remote",
    location: "Remoto",
    seniority: "mid",
    owner_id: "owner-1",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("JobsPanel", () => {
  it("carga vacantes, aplica filtro de estado y pagina", async () => {
    const fetchMock = mockFetch((url) => {
      expect(url.pathname).toBe("/api/v1/jobs");
      return jsonResponse({
        items: [makeJob("job-1", "Vacante Uno"), makeJob("job-2", "Vacante Dos")],
        total: 25,
        limit: 20,
        offset: Number(url.searchParams.get("offset") ?? 0),
      });
    });

    render(<JobsPanel />);

    expect(await screen.findByText("Vacante Uno")).toBeTruthy();
    expect(screen.getByText("Vacante Dos")).toBeTruthy();
    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe("include");
    expect(new URL(String(fetchMock.mock.calls[0]?.[0])).searchParams.get("status")).toBeNull();

    fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "open" } });
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    const filteredUrl = new URL(String(fetchMock.mock.calls[1]?.[0]));
    expect(filteredUrl.searchParams.get("status")).toBe("open");
    expect(filteredUrl.searchParams.get("offset")).toBe("0");

    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });
    const pagedUrl = new URL(String(fetchMock.mock.calls[2]?.[0]));
    expect(pagedUrl.searchParams.get("offset")).toBe("20");
  });

  it("crea una vacante con el contrato de la API", async () => {
    const created = makeJob("job-new", "Vacante Nueva");
    const fetchMock = mockFetch((url, init) => {
      if (init?.method === "POST") {
        return jsonResponse(created, 201);
      }
      return jsonResponse({ items: [], total: 0, limit: 20, offset: 0 });
    });

    render(<JobsPanel />);
    expect(await screen.findByText("No hay vacantes para este filtro.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Vacante Nueva" } });
    fireEvent.change(screen.getByLabelText("Descripción"), {
      target: { value: "Descripción sintética." },
    });
    fireEvent.change(screen.getByLabelText("Modalidad"), { target: { value: "híbrido" } });
    fireEvent.change(screen.getByLabelText("Ubicación"), { target: { value: "Córdoba" } });
    fireEvent.change(screen.getByLabelText("Seniority"), { target: { value: "senior" } });
    fireEvent.change(screen.getByLabelText("ID del responsable (UUID)"), {
      target: { value: "owner-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear vacante" }));

    expect(await screen.findByText("Vacante creada: Vacante Nueva.")).toBeTruthy();
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(postCall?.[0]).toBe("http://localhost:8000/api/v1/jobs");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      title: "Vacante Nueva",
      description: "Descripción sintética.",
      modality: "híbrido",
      location: "Córdoba",
      seniority: "senior",
      owner_id: "owner-1",
    });
  });

  it("muestra error accesible al fallar la carga", async () => {
    mockFetch(() => errorResponse(500, "Fallo de carga."));

    render(<JobsPanel />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("500: Fallo de carga.");
  });

  it("muestra error 422 al añadir un requisito inválido", async () => {
    mockFetch((url, init) => {
      if (init?.method === "POST") {
        return errorResponse(422, "weight > 0 requiere weight_justification");
      }
      return jsonResponse({
        items: [makeJob("job-1", "Vacante Uno")],
        total: 1,
        limit: 20,
        offset: 0,
      });
    });

    render(<JobsPanel />);
    expect(await screen.findByText("Vacante Uno")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Descripción del requisito"), {
      target: { value: "Experiencia verificable." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Añadir requisito" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("422:");
    expect(alert.textContent).toContain("weight_justification");
  });
});
