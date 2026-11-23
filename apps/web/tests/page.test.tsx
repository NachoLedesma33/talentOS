import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import Home from "../src/app/page";

afterEach(() => {
  cleanup();
});

describe("página inicial de Fase 1", () => {
  it("muestra identidad, estado y enlaces de la API sin llamadas de red", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { level: 1, name: "TalentOS" }),
    ).toBeTruthy();
    expect(
      screen.getByText("Reclutamiento asistido, trazable y supervisado."),
    ).toBeTruthy();
    expect(
      screen.getByText("Fase 1 — Fundación del monorepo"),
    ).toBeTruthy();

    const healthLink = screen.getByRole("link", {
      name: "http://localhost:8000/health",
    });
    const readyLink = screen.getByRole("link", {
      name: "http://localhost:8000/ready",
    });

    expect(healthLink.getAttribute("href")).toBe("http://localhost:8000/health");
    expect(readyLink.getAttribute("href")).toBe("http://localhost:8000/ready");
  });
});
