import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { WorkspaceShell } from "../src/components/WorkspaceShell";

afterEach(() => cleanup());

describe("WorkspaceShell", () => {
  it("expone sidebar, breadcrumbs y navegación móvil accesibles", () => {
    render(
      <WorkspaceShell section="Vacantes">
        <h1>Contenido sintético</h1>
      </WorkspaceShell>,
    );

    const sidebar = screen.getByRole("complementary", {
      name: "Navegación del workspace",
    });
    const sidebarNav = within(sidebar).getByRole("navigation", {
      name: "Secciones del workspace",
    });
    expect(
      within(sidebarNav).getByRole("link", { name: "Organización" }).getAttribute("href"),
    ).toBe("/dashboard#organization-selector-heading");

    const breadcrumbs = screen.getByRole("navigation", { name: "Ruta de navegación" });
    expect(within(breadcrumbs).getByText("Vacantes").getAttribute("aria-current")).toBe(
      "page",
    );

    const toggle = screen.getByRole("button", { name: "Mostrar menú" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("aria-controls")).toBe("workspace-mobile-nav");

    fireEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: "Ocultar menú" })).toBe(toggle);
    const mobileNav = screen.getByRole("navigation", {
      name: "Navegación móvil del workspace",
    });
    expect(mobileNav.id).toBe("workspace-mobile-nav");
    expect(screen.getByRole("heading", { name: "Contenido sintético" })).toBeTruthy();

    expect(screen.queryByRole("link", { name: "Analítica" })).toBeNull();
  });
});
