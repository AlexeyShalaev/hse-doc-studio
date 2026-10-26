import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { gitSyncApi } from "@entities/git-sync";
import {
  CONTENTS,
  PROJECT_ID,
  readOnlyStatus,
  renderExchange,
  resetExchangeEnvironment,
} from "../testing/renderExchange";
import { CiCard } from "./CiCard";
import { ExchangeCard } from "./ExchangeCard";

describe("карточки «Обмен файлом» и «Автосборка»", () => {
  beforeEach(async () => {
    await resetExchangeEnvironment();
    vi.spyOn(gitSyncApi, "getContents").mockResolvedValue(CONTENTS);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("обмен файлом предлагает выгрузить и загрузить и открывает нужное окно", async () => {
    const user = userEvent.setup();
    renderExchange(<ExchangeCard projectId={PROJECT_ID} />);
    expect(screen.getByText("Выгрузить bundle")).toBeInTheDocument();
    expect(screen.getByText("Загрузить bundle")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Выгрузить…" }));
    expect(
      await screen.findByRole("dialog", { name: "Выгрузить проект в файл" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Выбрать файл…" }));
    expect(
      await screen.findByRole("dialog", { name: "Загрузить файл проекта" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Загрузить" })).toBeDisabled();
  });

  it("в проекте только для чтения принять файл нельзя, а выгрузить можно", async () => {
    const user = userEvent.setup();
    renderExchange(<ExchangeCard projectId={PROJECT_ID} />, {
      status: readOnlyStatus(),
    });
    await user.click(screen.getByRole("button", { name: "Выбрать файл…" }));
    expect(
      await screen.findByText(/открыт только для чтения, поэтому принять файл/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("import-dropzone")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    await user.click(screen.getByRole("button", { name: "Выгрузить…" }));
    expect(
      await screen.findByRole("button", { name: "Выгрузить" }),
    ).toBeEnabled();
  });

  it("автосборка рассказывает, что это, и открывает окно настройки", async () => {
    const user = userEvent.setup();
    vi.spyOn(gitSyncApi, "getContents").mockResolvedValue(CONTENTS);
    renderExchange(<CiCard projectId={PROJECT_ID} />);
    expect(
      screen.getByText(/GitHub или GitLab сами соберут/),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Настроить автосборку…" }),
    );
    expect(
      await screen.findByRole("dialog", { name: "Автосборка (CI)" }),
    ).toBeInTheDocument();
  });
});
