import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderInline } from "./inlineMarkdown";

describe("разметка шагов справки", () => {
  it("жирный, курсив, код и ссылка становятся узлами, а не HTML", () => {
    const { container } = render(
      <p>
        {renderInline(
          "Нажмите **Создать**, *потом* `make` и [статья](/help/ru/x/) <b>x</b>",
        )}
      </p>,
    );
    expect(container.querySelector("strong")?.textContent).toBe("Создать");
    expect(container.querySelector("em")?.textContent).toBe("потом");
    expect(container.querySelector("code")?.textContent).toBe("make");
    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/help/ru/x/");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>x</b>");
  });

  it("javascript: ссылка остаётся текстом", () => {
    const { container } = render(
      <p>{renderInline("[жми](javascript:alert(1))")}</p>,
    );
    expect(container.querySelector("a")).toBeNull();
  });
});
