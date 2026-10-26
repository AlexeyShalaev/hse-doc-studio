import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import * as sharedLib from "@shared/lib";
import { gitSyncApi } from "@entities/git-sync";
import {
  CONTENTS,
  PROJECT_ID,
  renderExchange,
  resetExchangeEnvironment,
} from "../testing/renderExchange";
import { BundleExportDialog } from "./BundleExportDialog";

const FILE = {
  blob: new Blob(["bundle"], { type: "application/octet-stream" }),
  filename: "coursework-20261026-1200.bundle",
};

const mount = (props: { onClose?: () => void } = {}) => {
  const onClose = props.onClose ?? vi.fn();
  renderExchange(
    <BundleExportDialog isOpen projectId={PROJECT_ID} onClose={onClose} />,
  );
  return { onClose };
};

describe("окно выгрузки проекта в файл", () => {
  beforeEach(async () => {
    await resetExchangeEnvironment();
    vi.spyOn(gitSyncApi, "getContents").mockResolvedValue(CONTENTS);
    vi.spyOn(sharedLib, "flushPendingSaves").mockResolvedValue({
      total: 0,
      failed: 0,
    });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("называет, что войдёт в файл", async () => {
    mount();
    expect(
      screen.getByRole("dialog", { name: "Выгрузить проект в файл" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("142")).toBeInTheDocument();
    expect(screen.getByText("86")).toBeInTheDocument();
  });

  it("выгружает без пароля и показывает, что файл сохранён", async () => {
    const user = userEvent.setup();
    const download = vi
      .spyOn(sharedLib, "downloadBlob")
      .mockImplementation(() => undefined);
    const exporter = vi
      .spyOn(gitSyncApi, "exportBundle")
      .mockResolvedValue(FILE);
    mount();
    await user.click(screen.getByRole("button", { name: "Выгрузить" }));
    const done = await screen.findByTestId("export-done");
    expect(exporter).toHaveBeenCalledWith(PROJECT_ID, undefined);
    expect(download).toHaveBeenCalledWith(FILE.blob, FILE.filename);
    expect(done).toHaveTextContent(FILE.filename);
    expect(done).toHaveTextContent("Без пароля");
    await user.click(screen.getByRole("button", { name: "Скачать ещё раз" }));
    expect(download).toHaveBeenCalledTimes(2);
  });

  it("с паролем просит повторить его и не пускает дальше при расхождении", async () => {
    const user = userEvent.setup();
    vi.spyOn(sharedLib, "downloadBlob").mockImplementation(() => undefined);
    const exporter = vi
      .spyOn(gitSyncApi, "exportBundle")
      .mockResolvedValue({ ...FILE, filename: `${FILE.filename}.hseenc` });
    mount();
    await user.click(screen.getByTestId("export-protect"));
    const submit = screen.getByRole("button", { name: "Выгрузить" });
    expect(submit).toBeDisabled();

    await user.type(screen.getByTestId("export-password"), "secret-1");
    await user.type(screen.getByTestId("export-repeat"), "secret-2");
    expect(screen.getByText("Пароли не совпадают.")).toBeInTheDocument();
    expect(submit).toBeDisabled();

    await user.clear(screen.getByTestId("export-repeat"));
    await user.type(screen.getByTestId("export-repeat"), "secret-1");
    expect(screen.queryByText("Пароли не совпадают.")).toBeNull();
    expect(submit).toBeEnabled();
    await user.click(submit);

    const done = await screen.findByTestId("export-done");
    expect(exporter).toHaveBeenCalledWith(PROJECT_ID, "secret-1");
    expect(done).toHaveTextContent("Пароль");
    expect(done).toHaveTextContent("отдельно от файла");
  });

  it("предупреждает про файлы под NDA и защищает их одним нажатием", async () => {
    const user = userEvent.setup();
    vi.spyOn(gitSyncApi, "getContents").mockResolvedValue({
      ...CONTENTS,
      nda_files: 2,
    });
    mount();
    expect(await screen.findByText(/файлы под NDA/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Защитить паролем" }));
    expect(screen.queryByText(/файлы под NDA/)).toBeNull();
    expect(screen.getByTestId("export-password")).toBeInTheDocument();
  });

  it("показывает отказ сервера и даёт повторить", async () => {
    const user = userEvent.setup();
    const exporter = vi
      .spyOn(gitSyncApi, "exportBundle")
      .mockRejectedValueOnce(
        new ApiError("Идёт синхронизация.", "sync_busy", 409),
      )
      .mockResolvedValueOnce(FILE);
    vi.spyOn(sharedLib, "downloadBlob").mockImplementation(() => undefined);
    mount();
    await user.click(screen.getByRole("button", { name: "Выгрузить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Синхронизация уже идёт.",
    );
    await user.click(screen.getByRole("button", { name: "Выгрузить" }));
    await screen.findByTestId("export-done");
    expect(exporter).toHaveBeenCalledTimes(2);
  });

  it("не выгружает, если правки в редакторе не сохранились", async () => {
    const user = userEvent.setup();
    vi.spyOn(sharedLib, "flushPendingSaves").mockResolvedValue({
      total: 1,
      failed: 1,
    });
    const exporter = vi.spyOn(gitSyncApi, "exportBundle");
    mount();
    await user.click(screen.getByRole("button", { name: "Выгрузить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось сохранить правки",
    );
    expect(exporter).not.toHaveBeenCalled();
  });

  it("закрывается кнопкой «Отмена» и после выгрузки кнопкой «Готово»", async () => {
    const user = userEvent.setup();
    vi.spyOn(sharedLib, "downloadBlob").mockImplementation(() => undefined);
    vi.spyOn(gitSyncApi, "exportBundle").mockResolvedValue(FILE);
    const { onClose } = mount();
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Выгрузить" }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Готово" }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Готово" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
