import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { toast, useToastStore } from "@shared/lib";
import { Toaster } from "./Toaster";

// jsdom не считает :has() и положение, поэтому место уведомлений проверяем по таблице стилей.
const css = readFileSync(
  join(import.meta.dirname, "../../../index.css"),
  "utf8",
);

describe("Toaster", () => {
  afterEach(() => {
    cleanup();
    useToastStore.setState({ toasts: [] });
  });

  it("место задаёт класс .toaster, а не встроенные стили", () => {
    render(<Toaster />);
    act(() => {
      toast.success("Запрос #412 открыт");
    });
    const box = screen.getByTestId("toaster");
    expect(box).toHaveClass("toaster");
    expect(box.getAttribute("style")).toBeNull();
    expect(box).toHaveTextContent("Запрос #412 открыт");
  });

  it("по умолчанию внизу справа", () => {
    expect(css).toMatch(
      /\.toaster \{[^}]*position: fixed;[^}]*bottom: 2\.5rem;[^}]*right: 1rem;/,
    );
  });

  it("при открытом окне, шторке или боковой панели уходит наверх и не закрывает их кнопки", () => {
    const rule =
      /body:has\(\[role="dialog"\]\[data-state="open"\], \[data-form="sheet"\], \.sp-side\)\s*\.toaster \{([^}]*)\}/.exec(
        css,
      );
    expect(rule).not.toBeNull();
    const body = rule?.[1] ?? "";
    expect(body).toMatch(/top: calc\(var\(--safe-top\) \+ 0\.75rem\);/);
    expect(body).toMatch(/bottom: auto;/);
    expect(body).toMatch(/left: 50%;/);
  });
});
