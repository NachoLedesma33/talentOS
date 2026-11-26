import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "../src/app/dashboard/page";
import { MembersPanel } from "../src/components/MembersPanel";
import { OrganizationSelector } from "../src/components/OrganizationSelector";
import { ACTIVE_ORG_STORAGE_KEY } from "../src/lib/api";

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

const meBase = {
  id: "user-1",
  email: "user-a@example.test",
  name: "Usuario A",
  status: "active" as const,
};

const organizations = [
  {
    id: "org-1",
    name: "Organización Uno",
    slug: "organizacion-uno",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "org-2",
    name: "Organización Dos",
    slug: "organizacion-dos",
    created_at: "2026-01-02T00:00:00Z",
  },
];

function mockFetch(payload: unknown, status = 200) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      void input;
      void init;
      return jsonResponse(payload, status);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const members = [
  {
    user_id: "user-1",
    email: "user-a@example.test",
    name: "Usuario A",
    role: "admin",
  },
  {
    user_id: "user-2",
    email: "user-b@example.test",
    name: "Usuario B",
    role: "viewer",
  },
];

describe("identidad y organizaciones", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("lista dos organizaciones y persiste el cambio de activa", async () => {
    const fetchMock = mockFetch(organizations);
    const onChange = vi.fn();

    render(<OrganizationSelector onActiveOrganizationChange={onChange} />);

    const select = (await screen.findByRole("combobox", {
      name: "Organización activa",
    })) as HTMLSelectElement;
    expect(select.options).toHaveLength(2);
    expect(select.value).toBe("org-1");
    expect(window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY)).toBe("org-1");
    expect(onChange).toHaveBeenCalledWith("org-1");

    fireEvent.change(select, { target: { value: "org-2" } });
    expect(window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY)).toBe("org-2");
    expect(onChange).toHaveBeenCalledWith("org-2");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost:8000/api/v1/organizations");
    expect(init?.credentials).toBe("include");
  });

  it("muestra sesión requerida cuando /me responde 401", async () => {
    const envelope = {
      error: {
        code: "unauthorized",
        message: "Autenticación requerida.",
        request_id: "req-me-401",
      },
    };
    const fetchMock = mockFetch(envelope, 401);

    render(<DashboardPage />);

    expect(await screen.findByRole("heading", { name: "Sesión requerida" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ir a iniciar sesión" }).getAttribute("href")).toBe(
      "/login",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("muestra no encontrado cuando /me responde 404", async () => {
    const envelope = {
      error: {
        code: "not_found",
        message: "Recurso no encontrado.",
        request_id: "req-me-404",
      },
    };
    const fetchMock = mockFetch(envelope, 404);

    render(<DashboardPage />);

    expect(await screen.findByRole("heading", { name: "No encontrado." })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("No encontrado.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("muestra error del servidor cuando /me responde 500", async () => {
    const envelope = {
      error: {
        code: "internal_error",
        message: "Fallo interno del servidor.",
        request_id: "req-me-500",
      },
    };
    const fetchMock = mockFetch(envelope, 500);

    render(<DashboardPage />);

    expect(await screen.findByRole("heading", { name: "Error del servidor." })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Error del servidor.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("carga miembros con la organización activa del localStorage", async () => {
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, "org-1");
    const fetchMock = mockFetch(members);

    render(<MembersPanel organizationId="org-1" />);

    expect(await screen.findByText("Usuario A")).toBeTruthy();
    expect(screen.getByText("user-b@example.test")).toBeTruthy();

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost:8000/api/v1/organizations/org-1/members");
    expect(new Headers(init?.headers).get("X-Organization-ID")).toBe("org-1");
  });

  it("muestra permisos insuficientes si invitar responde 403", async () => {
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, "org-1");
    const envelope = {
      error: {
        code: "forbidden",
        message: "Rol insuficiente.",
        request_id: "req-invite-403",
      },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      if (init?.method === "POST") {
        return jsonResponse(envelope, 403);
      }
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MembersPanel organizationId="org-1" />);
    expect(await screen.findByText("Sin miembros en esta organización.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: "user-b@example.test" },
    });
    fireEvent.change(screen.getByLabelText("Rol"), { target: { value: "admin" } });
    fireEvent.click(screen.getByRole("button", { name: "Invitar miembro" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Permisos insuficientes.");

    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(postCall?.[0]).toBe("http://localhost:8000/api/v1/organizations/org-1/members");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      email: "user-b@example.test",
      role: "admin",
    });
  });

  it("expone la navegación principal como landmark accesible", async () => {
    const me = {
      id: "user-1",
      email: "user-a@example.test",
      name: "Usuario A",
      status: "active" as const,
      organizations: [{ id: "org-1", name: "Organización Uno" }],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) return jsonResponse(me);
      if (url.endsWith("/api/v1/organizations")) return jsonResponse(organizations);
      if (url.includes("/members")) return jsonResponse(members);
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardPage />);

    expect(
      await screen.findByRole("navigation", { name: /Recruitment Core|Núcleo de selección/ }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Analítica" }).getAttribute("href")).toBe(
      "/analytics",
    );
  });

  it("expone usuario y organización activa en el shell del panel", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = String(input);
        if (url.endsWith("/api/v1/auth/me")) {
          return jsonResponse({ ...meBase, onboarding: { step: "complete" } });
        }
        if (url.endsWith("/api/v1/organizations")) return jsonResponse(organizations);
        if (url.includes("/members")) return jsonResponse(members);
        if (url.endsWith("/api/v1/auth/logout") && init?.method === "POST") {
          return jsonResponse({ message: "Sesión cerrada." });
        }
        return jsonResponse({});
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Organización activa en la barra" }),
    );
    const orgSelect = (await screen.findByRole("combobox", {
      name: "Organización activa en la barra",
    })) as HTMLSelectElement;
    expect(orgSelect.value).toBe("org-1");
    expect(window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY)).toBe("org-1");

    fireEvent.change(orgSelect, { target: { value: "org-2" } });
    expect(window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY)).toBe("org-2");

    const userButton = await screen.findByRole("button", { name: "Cuenta" });
    fireEvent.click(userButton);
    expect((await screen.findAllByText("user-a@example.test")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));
    expect(await screen.findByText("Sesión cerrada.")).toBeTruthy();
    expect(window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY)).toBeNull();
    const logoutCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith("/api/v1/auth/logout") && init?.method === "POST",
    );
    expect(logoutCall).toBeDefined();
  });

  it("ofrece crear organización y vuelve al panel tras crearla", async () => {
    let meCalls = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = String(input);
        if (url.endsWith("/api/v1/auth/me")) {
          meCalls += 1;
          return jsonResponse({
            ...meBase,
            organizations: [],
            onboarding: {
              step: meCalls === 1 ? "create_organization" : "complete",
            },
          });
        }
        if (url === "http://localhost:8000/api/v1/organizations" && init?.method === "POST") {
          return jsonResponse(
            {
              id: "org-1",
              name: "Nueva Org",
              slug: "nueva-org",
              created_at: "2026-01-01T00:00:00Z",
            },
            201,
          );
        }
        if (url.endsWith("/api/v1/organizations")) return jsonResponse(organizations);
        if (url.includes("/members")) return jsonResponse(members);
        return jsonResponse({});
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardPage />);
    expect(await screen.findByRole("heading", { name: "Creá tu organización" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: /Recruitment Core|Núcleo de selección/ })).toBeNull();

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Nueva Org" } });
    fireEvent.change(screen.getByLabelText("Identificador"), { target: { value: "nueva-org" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear organización" }));

    expect(await screen.findByRole("navigation", { name: /Recruitment Core|Núcleo de selección/ })).toBeTruthy();
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      name: "Nueva Org",
      slug: "nueva-org",
    });
  });

  it("muestra checklist de primeros pasos con enlaces reales", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL): Promise<Response> => {
        const url = String(input);
        if (url.endsWith("/api/v1/auth/me")) {
          return jsonResponse({
            ...meBase,
            organizations: [],
            onboarding: { step: "complete" },
          });
        }
        if (url.endsWith("/api/v1/organizations")) return jsonResponse(organizations);
        if (url.includes("/members")) return jsonResponse(members);
        return jsonResponse({});
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardPage />);
    expect(await screen.findByRole("list", { name: "Primeros pasos" })).toBeTruthy();
    expect(screen.getByText("Crear tu organización").textContent).not.toContain("completado");
    expect(screen.getByRole("link", { name: "Invitar a tu equipo" }).getAttribute("href")).toBe(
      "#members-heading",
    );
    expect(screen.getByRole("link", { name: "Publicar una vacante" }).getAttribute("href")).toBe(
      "/jobs",
    );
    expect(screen.getByRole("link", { name: "Añadir candidatos" }).getAttribute("href")).toBe(
      "/candidates",
    );
  });

  it("pide aceptar invitación pendiente y permite reconsultar el estado", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL): Promise<Response> => {
        if (String(input).endsWith("/api/v1/auth/me")) {
          return jsonResponse({
            ...meBase,
            organizations: [],
            onboarding: { step: "accept_invitation" },
          });
        }
        return jsonResponse({});
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardPage />);
    expect(await screen.findByRole("heading", { name: "Invitación pendiente" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: /Recruitment Core|Núcleo de selección/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Ya la acepté, revisar de nuevo" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });
});
