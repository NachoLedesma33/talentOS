import { expect, test } from "@playwright/test";

test("ruta de navegación principal", async ({ page }, testInfo) => {
  await page.goto("/");

  await expect(page.getByRole("navigation", { name: "Ruta de navegación" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Ir al panel" })).toHaveAttribute("href", "/dashboard");

  if (testInfo.project.name === "desktop") {
    await expect(page.getByRole("complementary", { name: "Navegación del workspace" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Mostrar menú" })).toBeHidden();
  }
});

test("menú móvil del workspace", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "solo móvil");

  await page.goto("/");

  await expect(page.getByRole("button", { name: "Mostrar menú" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navegación móvil del workspace" })).toBeHidden();
  await page.getByRole("button", { name: "Mostrar menú" }).click();
  await expect(page.getByRole("button", { name: "Ocultar menú" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ocultar menú" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("navigation", { name: "Navegación móvil del workspace" })).toBeVisible();
});
