import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CandidatesPanel } from "../src/components/CandidatesPanel";
import type { Candidate } from "../src/lib/types";

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

function makeCandidate(id: string, name: string): Candidate {
  return {
    id,
    name,
    email: "user-a@example.test",
    location: "Sintético",
    profile_status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("CandidatesPanel", () => {
  it("busca candidatos por q y pagina resultados", async () => {
    const fetchMock = mockFetch((url) => {
      if (url.pathname !== "/api/v1/candidates") {
        return jsonResponse([]);
      }
      return jsonResponse({
        items: [makeCandidate("cand-1", "Candidato Uno")],
        total: 30,
        limit: 20,
        offset: Number(url.searchParams.get("offset") ?? 0),
      });
    });

    const listCalls = () =>
      fetchMock.mock.calls.filter(
        ([input]) => new URL(String(input)).pathname === "/api/v1/candidates",
      );

    render(<CandidatesPanel />);
    expect((await screen.findAllByText("Candidato Uno")).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Búsqueda (nombre o correo)"), {
      target: { value: "user-a" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => {
      expect(listCalls()).toHaveLength(2);
    });
    const searchUrl = new URL(String(listCalls()[1]?.[0]));
    expect(searchUrl.searchParams.get("q")).toBe("user-a");
    expect(searchUrl.searchParams.get("offset")).toBe("0");

    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    await waitFor(() => {
      expect(listCalls()).toHaveLength(3);
    });
    expect(new URL(String(listCalls()[2]?.[0])).searchParams.get("offset")).toBe("20");
  });

  it("crea candidato sin campos de atributos protegidos", async () => {
    const created = makeCandidate("cand-new", "Candidato Nuevo");
    const fetchMock = mockFetch((url, init) => {
      if (init?.method === "POST") {
        return jsonResponse(created, 201);
      }
      if (url.pathname.endsWith("/notes") || url.pathname.endsWith("/activity")) {
        return jsonResponse([]);
      }
      return jsonResponse({ items: [], total: 0, limit: 20, offset: 0 });
    });

    render(<CandidatesPanel />);
    expect(await screen.findByText("No hay candidatos para esta búsqueda.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Nombre"), {
      target: { value: "Candidato Nuevo" },
    });
    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: "user-a@example.test" },
    });
    fireEvent.change(screen.getByLabelText("Ubicación"), {
      target: { value: "Córdoba" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear candidato" }));

    expect(await screen.findByText("Candidato creado: Candidato Nuevo.")).toBeTruthy();
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(postCall?.[0]).toBe("http://localhost:8000/api/v1/candidates");
    const body = JSON.parse(String(postCall?.[1]?.body)) as Record<string, unknown>;
    expect(Object.keys(body)).toEqual(["name", "email", "location"]);
    expect(body).toEqual({
      name: "Candidato Nuevo",
      email: "user-a@example.test",
      location: "Córdoba",
    });
  });

  it("muestra notas y actividad del candidato seleccionado", async () => {
    mockFetch((url) => {
      if (url.pathname.endsWith("/notes")) {
        return jsonResponse([
          {
            id: "note-1",
            candidate_id: "cand-1",
            author_id: "user-1",
            body: "Nota sintética interna.",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ]);
      }
      if (url.pathname.endsWith("/activity")) {
        return jsonResponse([
          {
            id: "activity-1",
            action: "candidate.created",
            actor_id: "user-1",
            resource_type: "candidate",
            resource_id: "cand-1",
            timestamp: "2026-01-01T00:00:00Z",
          },
        ]);
      }
      return jsonResponse({
        items: [makeCandidate("cand-1", "Candidato Uno")],
        total: 1,
        limit: 20,
        offset: 0,
      });
    });

    render(<CandidatesPanel />);

    expect(await screen.findByText("Nota sintética interna.")).toBeTruthy();
    expect(await screen.findByText(/candidate.created/)).toBeTruthy();
  });

  it("muestra error accesible si las notas responden 403", async () => {
    mockFetch((url) => {
      if (url.pathname.endsWith("/notes")) {
        return errorResponse(403, "Rol insuficiente.");
      }
      if (url.pathname.endsWith("/activity")) {
        return jsonResponse([]);
      }
      return jsonResponse({
        items: [makeCandidate("cand-1", "Candidato Uno")],
        total: 1,
        limit: 20,
        offset: 0,
      });
    });

    render(<CandidatesPanel />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("403: Rol insuficiente.");
  });
});
