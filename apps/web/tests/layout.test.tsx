import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RootLayout from "../src/app/layout";

describe("RootLayout", () => {
  it("ofrece salto al contenido principal con foco inicial", () => {
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(
      <RootLayout>
        <p>Contenido sintético</p>
      </RootLayout>,
    );

    const link = container.querySelector("a");
    const main = container.querySelector("main");

    expect(link?.textContent).toBe("Saltar al contenido principal");
    expect(link?.getAttribute("href")).toBe("#main-content");
    expect(link?.className).toContain("sr-only");
    expect(link?.className).toContain("focus:not-sr-only");
    expect(main?.id).toBe("main-content");
    expect(main?.getAttribute("tabindex")).toBe("-1");
    expect(main?.textContent).toContain("Contenido sintético");
  });
});
