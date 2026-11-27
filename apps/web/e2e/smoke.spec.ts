import { expect, test, type Page } from "@playwright/test";

test.use({ launchOptions: { args: ["--disable-web-security"] } });

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

const activeOrgKey = "talentos:active-org";

const sessionUser = {
  id: "user-e2e",
  email: "invitado@example.test",
  name: "Usuario E2E",
  status: "active",
  organizations: [{ id: "org-1", name: "Organización Uno" }],
  onboarding: { step: "complete" },
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

type MockReply = { status?: number; body: unknown };

async function mockApi(
  page: Page,
  handler: (pathname: string, method: string) => MockReply | null,
) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    const reply = handler(new URL(request.url()).pathname, request.method());
    if (!reply) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        headers: corsHeaders,
        body: JSON.stringify({
          error: { code: "not_found", message: "No encontrado", request_id: "e2e" },
        }),
      });
      return;
    }
    await route.fulfill({
      status: reply.status ?? 200,
      contentType: "application/json",
      headers: corsHeaders,
      body: JSON.stringify(reply.body),
    });
  });
}

function workspaceApi(): (pathname: string, method: string) => MockReply | null {
  return (pathname, method) => {
    if (method === "GET" && pathname === "/api/v1/auth/me") return { body: sessionUser };
    if (method === "GET" && pathname === "/api/v1/organizations") return { body: organizations };
    if (method === "GET" && pathname.endsWith("/members")) return { body: [] };
    return null;
  };
}

test("portada pública", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("navigation", { name: "Navegación de la portada" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /Decisiones de contratación con evidencia/ }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Acceder" })).toHaveAttribute("href", "/login");
  await expect(page.getByRole("link", { name: "Empezar ahora" })).toHaveAttribute("href", "/register");
  await expect(page.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/register");
  await expect(page.getByRole("link", { name: "Ir al panel" })).toHaveAttribute("href", "/dashboard");
  const cta = page.getByRole("link", { name: "Crear cuenta" });
  expect(await cta.evaluate((element) => getComputedStyle(element).textDecorationLine)).toBe("none");
});

test("página 404 con acciones", async ({ page }) => {
  await page.goto("/ruta-inexistente");

  await expect(page.getByRole("heading", { name: "Esta página no existe." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Volver al panel" })).toHaveAttribute("href", "/dashboard");
  await expect(page.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/");
});

test("ruta de navegación principal del workspace", async ({ page }, testInfo) => {
  await page.goto("/jobs");

  await expect(page.getByRole("navigation", { name: "Ruta de navegación" })).toBeVisible();

  if (testInfo.project.name === "desktop") {
    await expect(page.getByRole("complementary", { name: "Navegación del workspace" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Mostrar menú" })).toBeHidden();
  }
});

test("menú de comandos del workspace", async ({ page }) => {
  await page.goto("/jobs");

  const trigger = page.getByRole("button", { name: "Buscar sección…" });
  await expect(trigger).toBeVisible();
  await trigger.click();

  const dialog = page.getByRole("dialog", { name: "Buscar sección" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  await page.keyboard.press("Control+k");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("searchbox", { name: "Filtrar secciones" }).fill("candidatos");
  await expect(dialog.getByRole("link", { name: /Candidatos/ })).toBeVisible();
  await expect(dialog.getByRole("link", { name: /Vacantes/ })).toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("menú móvil del workspace", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "solo móvil");

  await page.goto("/jobs");

  await expect(page.getByRole("button", { name: "Mostrar menú" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navegación móvil del workspace" })).toBeHidden();
  await page.getByRole("button", { name: "Mostrar menú" }).click();
  await expect(page.getByRole("button", { name: "Ocultar menú" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ocultar menú" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("navigation", { name: "Navegación móvil del workspace" })).toBeVisible();
});

test("tarea: recuperar contraseña y definir una nueva", async ({ page }) => {
  await mockApi(page, (pathname, method) => {
    if (method === "POST" && pathname === "/api/v1/auth/forgot-password") {
      return {
        body: {
          message: "Si la cuenta existe, continúa con el token.",
          dev_token: "demo-reset-token",
        },
      };
    }
    if (method === "POST" && pathname === "/api/v1/auth/reset-password") {
      return { body: { message: "Contraseña actualizada." } };
    }
    return null;
  });

  await page.goto("/login");
  await page.getByRole("link", { name: "Recuperar contraseña" }).click();
  await expect(page.getByRole("heading", { name: "Recuperar contraseña" })).toBeVisible();
  await page.getByLabel("Correo electrónico").fill("invitado@example.test");
  await page.getByRole("checkbox", { name: /Acepto la política de privacidad/i }).check();
  await page.getByRole("button", { name: "Enviar instrucciones" }).click();
  await expect(page.getByText("Modo demo: no se envió ningún correo.")).toBeVisible();

  await page.getByRole("link", { name: "Continuar con el restablecimiento" }).click();
  await expect(page.getByRole("heading", { name: "Nueva contraseña" })).toBeVisible();
  await expect(page.getByLabel("Token de recuperación")).toHaveValue("demo-reset-token");
  await page.getByLabel("Contraseña nueva").fill("NuevaClaveSegura123");
  await page.getByRole("button", { name: "Actualizar contraseña" }).click();
  await expect(page.getByRole("link", { name: "Ir a iniciar sesión" })).toBeVisible();
});

test("tarea: aceptar invitación desde el enlace recibido", async ({ page }) => {
  let authenticated = false;
  await mockApi(page, (pathname, method) => {
    if (method === "GET" && pathname === "/api/v1/organizations/invitations/invite-token") {
      return {
        body: {
          organization_name: "Organización Uno",
          email: "invitado@example.test",
          role: "recruiter",
          expires_at: "2026-12-31T00:00:00Z",
        },
      };
    }
    if (method === "GET" && pathname === "/api/v1/auth/me") {
      return authenticated
        ? { body: sessionUser }
        : {
            status: 401,
            body: {
              error: {
                code: "unauthorized",
                message: "Sesión requerida",
                request_id: "e2e",
              },
            },
          };
    }
    if (method === "POST" && pathname === "/api/v1/auth/login") {
      authenticated = true;
      return { body: sessionUser };
    }
    if (
      method === "POST" &&
      pathname === "/api/v1/organizations/invitations/invite-token/accept"
    ) {
      return {
        body: {
          organization_id: "org-1",
          organization_name: "Organización Uno",
          role: "recruiter",
        },
      };
    }
    return workspaceApi()(pathname, method);
  });

  await page.goto("/invite/invite-token");
  await expect(page.getByText("invitado@example.test")).toBeVisible();
  await expect(page.getByRole("button", { name: "Iniciar sesión y aceptar" })).toBeVisible();
  await page.getByLabel("Contraseña").fill("ClaveSegura123");
  await page.getByRole("button", { name: "Iniciar sesión y aceptar" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Panel" })).toBeVisible();
  expect(await page.evaluate((key) => window.localStorage.getItem(key), activeOrgKey)).toBe(
    "org-1",
  );
});

test("tarea: cambiar la organización activa desde el shell", async ({ page }) => {
  await mockApi(page, workspaceApi());

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Panel" })).toBeVisible();
  await page.getByRole("button", { name: "Organización activa en la barra" }).click();
  const selector = page.getByRole("combobox", { name: "Organización activa en la barra" });
  await expect(selector).toHaveValue("org-1");
  await selector.selectOption("org-2");
  expect(await page.evaluate((key) => window.localStorage.getItem(key), activeOrgKey)).toBe(
    "org-2",
  );
});

test("tarea: cerrar sesión desde el menú de cuenta", async ({ page }) => {
  let logoutCalled = false;
  await mockApi(page, (pathname, method) => {
    if (method === "POST" && pathname === "/api/v1/auth/logout") {
      logoutCalled = true;
      return { body: { message: "Sesión cerrada." } };
    }
    return workspaceApi()(pathname, method);
  });

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Panel" })).toBeVisible();
  await page.getByRole("button", { name: "Cuenta" }).click();
  const menu = page.locator("#workspace-user-menu");
  await expect(menu.getByText("invitado@example.test")).toBeVisible();
  await menu.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(menu.getByText("Sesión cerrada.")).toBeVisible();
  expect(logoutCalled).toBe(true);
});

