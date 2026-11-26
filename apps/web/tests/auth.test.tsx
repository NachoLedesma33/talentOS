import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ForgotPasswordPage from "../src/app/forgot-password/page";
import InvitationPage from "../src/app/invite/[token]/page";
import ResetPasswordPage from "../src/app/reset-password/page";
import { LoginForm } from "../src/components/LoginForm";
import { RegisterForm } from "../src/components/RegisterForm";
import { ACTIVE_ORG_STORAGE_KEY } from "../src/lib/api";

const { pushMock, searchParamsState, paramsState } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  searchParamsState: { value: "" },
  paramsState: { value: "" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(searchParamsState.value),
  useParams: () => ({ token: paramsState.value }),
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
    searchParamsState.value = "";
    paramsState.value = "";
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

  it("solicita recuperación y ofrece el token demo sin correo real", async () => {
    const fetchMock = mockFetch({
      message: "Revisá tu correo.",
      dev_token: "demo-reset-token",
    });

    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: authenticatedUser.email },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enviar instrucciones" }));

    expect(await screen.findByText("Revisá tu correo.")).toBeTruthy();
    expect(screen.getByText("Modo demo: no se envió ningún correo.")).toBeTruthy();
    expect(screen.getByText("demo-reset-token")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: "Continuar con el restablecimiento" })
        .getAttribute("href"),
    ).toBe("/reset-password?token=demo-reset-token");

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost:8000/api/v1/auth/forgot-password");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ email: authenticatedUser.email });
  });

  it("anuncia error de recuperación sin exponer token", async () => {
    mockFetch(
      {
        error: {
          code: "validation_error",
          message: "Correo inválido.",
          request_id: "req-forgot-1",
        },
      },
      422,
    );

    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Correo electrónico"), {
      target: { value: authenticatedUser.email },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enviar instrucciones" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Error: Correo inválido.");
    expect(screen.queryByText(/Modo demo/)).toBeNull();
    expect(
      (screen.getByRole("button", { name: "Enviar instrucciones" }) as HTMLButtonElement).disabled,
    ).toBe(false);
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

  it("restablece contraseña con token de la URL", async () => {
    searchParamsState.value = "?token=demo-reset-token";
    const fetchMock = mockFetch({ message: "Contraseña actualizada." });

    render(<ResetPasswordPage />);
    expect((screen.getByLabelText("Token de recuperación") as HTMLInputElement).value).toBe(
      "demo-reset-token",
    );
    fireEvent.change(screen.getByLabelText("Contraseña nueva"), {
      target: { value: "NewSyntheticPass456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Actualizar contraseña" }));

    expect(await screen.findByText("Contraseña actualizada.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ir a iniciar sesión" }).getAttribute("href")).toBe(
      "/login",
    );

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost:8000/api/v1/auth/reset-password");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      token: "demo-reset-token",
      password: "NewSyntheticPass456",
    });
  });

  it("anuncia token inválido sin cambiar la contraseña localmente", async () => {
    searchParamsState.value = "?token=expired-token";
    mockFetch(
      {
        error: {
          code: "bad_request",
          message: "El enlace de recuperación no es válido o expiró.",
          request_id: "req-reset-1",
        },
      },
      400,
    );

    render(<ResetPasswordPage />);
    fireEvent.change(screen.getByLabelText("Contraseña nueva"), {
      target: { value: "NewSyntheticPass456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Actualizar contraseña" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "Error: El enlace de recuperación no es válido o expiró.",
    );
    expect(screen.queryByRole("link", { name: "Ir a iniciar sesión" })).toBeNull();
    expect(
      (screen.getByRole("button", { name: "Actualizar contraseña" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("muestra preview público y acepta invitación con sesión activa", async () => {
    paramsState.value = "invite-token";
    const detail = {
      organization_name: "TalentOS Demo",
      email: authenticatedUser.email,
      role: "owner",
      expires_at: "2026-12-01T00:00:00Z",
    };
    const accepted = {
      organization_id: "org-1",
      organization_name: "TalentOS Demo",
      role: "owner",
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = String(input);
        if (url.endsWith("/api/v1/organizations/invitations/invite-token") && !init?.method) {
          return jsonResponse(detail);
        }
        if (url.endsWith("/api/v1/auth/me")) {
          return jsonResponse({
            ...authenticatedUser,
            organizations: [],
            onboarding: { step: "complete" },
          });
        }
        if (url.endsWith("/api/v1/organizations/invitations/invite-token/accept")) {
          return jsonResponse(accepted);
        }
        return jsonResponse(null, 404);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<InvitationPage />);
    expect(await screen.findByText("TalentOS Demo")).toBeTruthy();
    expect(screen.getByText("Propietario")).toBeTruthy();
    expect(screen.queryByLabelText("Contraseña")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Aceptar invitación" }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/dashboard");
    });
    expect(window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY)).toBe("org-1");
    const acceptCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).endsWith("/api/v1/organizations/invitations/invite-token/accept"),
    );
    expect(acceptCall?.[1]?.method).toBe("POST");
  });

  it("registra cuenta desde la invitación y la acepta", async () => {
    paramsState.value = "invite-token";
    const detail = {
      organization_name: "TalentOS Demo",
      email: "nueva@example.test",
      role: "recruiter",
      expires_at: "2026-12-01T00:00:00Z",
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = String(input);
        if (url.endsWith("/api/v1/organizations/invitations/invite-token") && !init?.method) {
          return jsonResponse(detail);
        }
        if (url.endsWith("/api/v1/auth/me")) {
          return jsonResponse(
            { error: { code: "unauthorized", message: "No logueado.", request_id: "req-1" } },
            401,
          );
        }
        if (url.endsWith("/api/v1/auth/register")) {
          return jsonResponse({ ...authenticatedUser, email: detail.email });
        }
        if (url.endsWith("/api/v1/organizations/invitations/invite-token/accept")) {
          return jsonResponse({
            organization_id: "org-2",
            organization_name: "TalentOS Demo",
            role: "recruiter",
          });
        }
        return jsonResponse(null, 404);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<InvitationPage />);
    expect(await screen.findByText("TalentOS Demo")).toBeTruthy();
    expect((screen.getByLabelText("Correo electrónico") as HTMLInputElement).value).toBe(
      detail.email,
    );

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Nueva Usuaria" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "SyntheticPass456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta y aceptar" }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/dashboard");
    });
    expect(window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY)).toBe("org-2");
    const registerCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).endsWith("/api/v1/auth/register"),
    );
    expect(JSON.parse(String(registerCall?.[1]?.body))).toEqual({
      name: "Nueva Usuaria",
      email: detail.email,
      password: "SyntheticPass456",
    });
  });

  it("anuncia invitación inexistente sin ofrecer aceptación", async () => {
    paramsState.value = "expired-token";
    mockFetch(
      {
        error: {
          code: "not_found",
          message: "Invitación no encontrada.",
          request_id: "req-invite-1",
        },
      },
      404,
    );

    render(<InvitationPage />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Error: Invitación no encontrada.");
    expect(screen.queryByRole("button", { name: "Aceptar invitación" })).toBeNull();
  });
});
