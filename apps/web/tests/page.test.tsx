import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import Home from "../src/app/page";
import { LocaleProvider } from "../src/lib/i18n";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe("portada pública", () => {
  it("muestra propuesta, CTAs jerarquizados y nota de demo sin llamadas de red", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /Decisiones de contratación con evidencia/,
      }),
    ).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Navegación de la portada" })).toBeTruthy();

    const registerLink = screen.getByRole("link", { name: "Crear cuenta" });
    const dashboardLink = screen.getByRole("link", { name: "Ir al panel" });
    expect(registerLink.getAttribute("href")).toBe("/register");
    expect(dashboardLink.getAttribute("href")).toBe("/dashboard");

    expect(
      screen.getByText(/Demostración local con datos sintéticos/),
    ).toBeTruthy();
  });

  it("cambia a inglés con el botón de idioma y persiste la preferencia", () => {
    render(
      <LocaleProvider>
        <Home />
      </LocaleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Cambiar a inglés/ }));

    expect(
      screen.getByRole("heading", { level: 1, name: /Hiring decisions backed by evidence/ }),
    ).toBeTruthy();
    expect(document.documentElement.lang).toBe("en");
    expect(window.localStorage.getItem("talentos:locale")).toBe("en");
  });
});
