import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ErrorPage from "../src/app/error";
import NotFound from "../src/app/not-found";

afterEach(() => {
  cleanup();
});

describe("estados de error de la interfaz", () => {
  it("muestra la página 404 con acciones de salida", () => {
    render(<NotFound />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Esta página no existe." }),
    ).toBeTruthy();
    expect(screen.getByText("404 · not_found")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Volver al panel" }).getAttribute("href")).toBe(
      "/dashboard",
    );
    expect(screen.getByRole("link", { name: "Ir al inicio" }).getAttribute("href")).toBe("/");
  });

  it("muestra referencia y permite reintentar sin exponer el mensaje crudo", () => {
    const reset = vi.fn();
    const error = new Error("secreto") as Error & { digest?: string };
    error.digest = "digest-e2e";
    render(<ErrorPage error={error} reset={reset} />);

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 1, name: "No se pudo cargar esta sección." }),
    ).toBeTruthy();
    expect(screen.getByText("digest-e2e")).toBeTruthy();
    expect(screen.queryByText("secreto")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Volver al panel" }).getAttribute("href")).toBe(
      "/dashboard",
    );
  });
});
