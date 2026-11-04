import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { CompileFailureNotice } from "./index";

const mount = (props: Parameters<typeof CompileFailureNotice>[0]) =>
  render(
    <I18nextProvider i18n={i18n}>
      <CompileFailureNotice {...props} />
    </I18nextProvider>,
  );

describe("CompileFailureNotice", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("shows the code, the message and the raw detail", () => {
    mount({
      error: {
        code: "image_missing",
        detail: "Docker image not installed: texlive/texlive:latest",
        message: "Не установлен образ TeX Live. Установите его.",
      },
      status: "failure",
      hasOutput: true,
    });

    expect(screen.getByTestId("compile-failure").dataset.code).toBe(
      "image_missing",
    );
    expect(screen.getByTestId("compile-failure-code").textContent).toBe(
      "image_missing",
    );
    expect(screen.getByTestId("compile-failure-message").textContent).toContain(
      "Установите",
    );
    expect(screen.getByTestId("compile-failure-detail").textContent).toContain(
      "texlive/texlive:latest",
    );
    expect(screen.queryByTestId("compile-failure-no-output")).toBeNull();
  });

  it("says plainly that the build did not start when there is no output and the code is a refusal", () => {
    mount({
      error: { code: "docker_unavailable", message: "Docker недоступен." },
      status: "failure",
      hasOutput: false,
    });

    expect(
      screen.getByTestId("compile-failure-no-output").textContent,
    ).toContain("LaTeX не запускался");
  });

  it("says the runner sent nothing when there is no output and the code is not a refusal", () => {
    mount({
      error: { code: "executor_crashed", message: "Раннер упал." },
      status: "failure",
      hasOutput: false,
    });

    expect(
      screen.getByTestId("compile-failure-no-output").textContent,
    ).toContain("не прислал ни одной строки");
  });

  it("explains that an old record has no recorded reason", () => {
    mount({ error: null, status: "failure", hasOutput: true });

    expect(screen.getByTestId("compile-failure").dataset.code).toBe("unknown");
    expect(screen.getByTestId("compile-failure-message").textContent).toContain(
      "Причина не записана",
    );
  });

  it("uses the cancelled title and lets the user retry", () => {
    const retry = vi.fn();
    mount({
      error: { code: "cancelled", message: "Сборку отменили." },
      status: "cancelled",
      hasOutput: true,
      onRetry: retry,
    });

    expect(screen.getByText("Сборка отменена")).toBeTruthy();
    screen.getByRole("button").click();
    expect(retry).toHaveBeenCalledOnce();
  });

  it("renders English text", async () => {
    await i18n.changeLanguage("en");
    mount({
      error: { code: "timed_out", message: "The build timed out." },
      status: "failure",
      hasOutput: true,
    });

    expect(screen.getByText("Build failed")).toBeTruthy();
  });
});
