import { expect, test } from "@playwright/test";

test("portada pública", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("navigation", { name: "Navegación de la portada" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /Decisiones de contratación con evidencia/ }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/register");
  await expect(page.getByRole("link", { name: "Ir al panel" })).toHaveAttribute("href", "/dashboard");
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
