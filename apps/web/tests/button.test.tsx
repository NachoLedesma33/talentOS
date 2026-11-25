import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "../src/components/ui/Button";

describe("Button", () => {
  afterEach(() => {
    cleanup();
  });

  it("renderiza primary por defecto", () => {
    render(<Button>Acción</Button>);

    const button = screen.getByRole("button", { name: "Acción" });
    expect(button.className).toContain("bg-accent");
  });

  it("renderiza secondary con borde", () => {
    render(<Button variant="secondary">Acción</Button>);

    const button = screen.getByRole("button", { name: "Acción" });
    expect(button.className).toContain("border-border");
  });

  it("preserva type button", () => {
    render(<Button type="button">Acción</Button>);

    expect(screen.getByRole("button", { name: "Acción" }).getAttribute("type")).toBe("button");
  });

  it("respeta disabled", () => {
    render(<Button disabled>Acción</Button>);

    expect((screen.getByRole("button", { name: "Acción" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("preserva aria-label", () => {
    render(<Button aria-label="Cerrar">x</Button>);

    expect(screen.getByRole("button", { name: "Cerrar" }).getAttribute("aria-label")).toBe(
      "Cerrar",
    );
  });

  it("dispara onClick", () => {
    const onClick = vi.fn();

    render(<Button onClick={onClick}>Acción</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Acción" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
