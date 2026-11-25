import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm } from "../src/components/LoginForm";
import { RegisterForm } from "../src/components/RegisterForm";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

const authenticatedUser = {
  id: "user-1",
  email: "user-a@example.test",
  name: "Usuario A",
  status: "active",
};

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

describe("formularios de identidad", () => {
  beforeEach(() => {
    window.localStorage.clear();
    pushMock.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("envía login y redirige al panel tras éxito", async () => {
    const fetchMock = mockFetch(authenticatedUser);

    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: authenticatedUser.email },
    });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/dashboard");
    });
    expect(screen.getByText(/Sesión iniciada/)).toBeTruthy();

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost:8000/api/v1/auth/login");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
    expect(JSON.parse(String(init?.body))).toEqual({
      email: authenticatedUser.email,
      password: "password123",
    });
  });

  it("muestra el error del envelope sin redirigir", async () => {
    const envelope = {
      error: {
        code: "unauthorized",
        message: "Credenciales inválidas.",
        request_id: "req-auth-1",
      },
    };
    const fetchMock = mockFetch(envelope, 401);

    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: authenticatedUser.email },
    });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Error: Credenciales inválidas.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(pushMock).not.toHaveBeenCalled();
    expect(
      (screen.getByRole("button", { name: "Iniciar sesión" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("registra usuario y ofrece enlace a login", async () => {
    const fetchMock = mockFetch(authenticatedUser, 201);

    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Nombre"), {
      target: { value: authenticatedUser.name },
    });
    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: authenticatedUser.email },
    });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    expect(
      await screen.findByText("Cuenta creada. Ahora puedes iniciar sesión."),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ir a iniciar sesión" }).getAttribute("href")).toBe(
      "/login",
    );

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost:8000/api/v1/auth/register");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      name: authenticatedUser.name,
      email: authenticatedUser.email,
      password: "password123",
    });
  });

  it("prefija el error de registro y lo anuncia como alerta", async () => {
    mockFetch(
      {
        error: {
          code: "conflict",
          message: "Correo ya registrado.",
          request_id: "req-reg-1",
        },
      },
      409,
    );

    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Nombre"), {
      target: { value: authenticatedUser.name },
    });
    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: authenticatedUser.email },
    });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Error: Correo ya registrado.");
    expect(alert.getAttribute("aria-live")).toBe("assertive");
  });
});
