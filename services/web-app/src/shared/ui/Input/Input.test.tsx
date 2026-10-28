import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Input } from "./Input";

describe("Input", () => {
  it("связывает ошибку с полем через aria-invalid и aria-describedby", () => {
    render(<Input label="Пароль" error="Слишком короткий" />);
    const input = screen.getByLabelText("Пароль");
    expect(input).toHaveAttribute("aria-invalid", "true");
    const id = input.getAttribute("aria-describedby");
    expect(id).toBeTruthy();
    expect(document.getElementById(id ?? "")).toHaveTextContent(
      "Слишком короткий",
    );
  });

  it("подсказка связана с полем, а без ошибки поле валидно", () => {
    render(<Input label="Почта" hint="Рабочий адрес" />);
    const input = screen.getByLabelText("Почта");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(
      document.getElementById(input.getAttribute("aria-describedby") ?? ""),
    ).toHaveTextContent("Рабочий адрес");
  });

  it("сохраняет переданный aria-describedby", () => {
    render(<Input label="Имя" error="Ошибка" aria-describedby="extra" />);
    expect(
      screen.getByLabelText("Имя").getAttribute("aria-describedby"),
    ).toMatch(/^extra /);
  });
});
