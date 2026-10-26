import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import * as sharedLib from "@shared/lib";
import { gitSyncApi, useSyncUiStore } from "@entities/git-sync";
import {
  MERGED,
  PROJECT_ID,
  operation,
  renderExchange,
  resetExchangeEnvironment,
} from "../testing/renderExchange";
import { BundleImportDialog } from "./BundleImportDialog";

const bundle = (name = "coursework.bundle") =>
  new File(["bundle"], name, { type: "application/octet-stream" });

const mount = (
  props: Partial<React.ComponentProps<typeof BundleImportDialog>> = {},
) => {
  const onClose = vi.fn();
  const view = renderExchange(
    <BundleImportDialog
      isOpen
      projectId={PROJECT_ID}
      onClose={onClose}
      {...props}
    />,
  );
  return { onClose, ...view };
};

const choose = async (file: File) => {
  const user = userEvent.setup({ applyAccept: false });
  await user.upload(screen.getByTestId("import-input"), file);
  return user;
};

const submit = () => screen.getByRole("button", { name: "Загрузить" });

describe("окно загрузки файла проекта", () => {
  beforeEach(async () => {
    await resetExchangeEnvironment();
    vi.spyOn(sharedLib, "flushPendingSaves").mockResolvedValue({
      total: 0,
      failed: 0,
    });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useSyncUiStore.setState({ profileDialogOpen: false });
  });

  describe("выбор файла", () => {
    it("объясняет, что произойдёт, и не даёт начать без файла", () => {
      mount();
      expect(
        screen.getByRole("dialog", { name: "Загрузить файл проекта" }),
      ).toBeInTheDocument();
      expect(screen.getByTestId("import-dropzone")).toBeInTheDocument();
      expect(screen.getByText(/объединит с проектом/)).toBeInTheDocument();
      expect(submit()).toBeDisabled();
    });

    it("принимает файл .bundle и показывает его имя и размер", async () => {
      mount();
      await choose(bundle());
      const card = await screen.findByTestId("import-file");
      expect(card).toHaveTextContent("coursework.bundle");
      expect(screen.queryByTestId("import-dropzone")).toBeNull();
      expect(submit()).toBeEnabled();
    });

    it("отказывает файлу с чужим расширением", () => {
      mount();
      fireEvent.change(screen.getByTestId("import-input"), {
        target: { files: [new File(["x"], "notes.txt")] },
      });
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Нужен файл .bundle или .hseenc.",
      );
      expect(submit()).toBeDisabled();
    });

    it("принимает файл, брошенный на область", () => {
      mount();
      const file = bundle("dropped.bundle");
      fireEvent.drop(screen.getByTestId("import-dropzone"), {
        dataTransfer: { files: [file] },
      });
      expect(screen.getByTestId("import-file")).toHaveTextContent(
        "dropped.bundle",
      );
    });

    it("для зашифрованного файла просит пароль и ждёт его", async () => {
      mount();
      const user = await choose(bundle("coursework.bundle.hseenc"));
      const password = await screen.findByTestId("import-password");
      expect(screen.getByTestId("import-file")).toHaveTextContent(
        "защищён паролем",
      );
      expect(submit()).toBeDisabled();
      await user.type(password, "secret");
      expect(submit()).toBeEnabled();
    });

    it("позволяет убрать файл и выбрать заново", async () => {
      mount();
      const user = await choose(bundle());
      await user.click(
        await screen.findByRole("button", { name: "Убрать файл" }),
      );
      expect(screen.getByTestId("import-dropzone")).toBeInTheDocument();
      expect(submit()).toBeDisabled();
    });

    it("в проекте только для чтения объясняет причину и не даёт загрузить", () => {
      mount({ disabledReason: "Проект открыт только для чтения." });
      expect(screen.getByRole("status")).toHaveTextContent(
        "Проект открыт только для чтения.",
      );
      expect(submit()).toBeDisabled();
    });
  });

  describe("загрузка и слияние", () => {
    it("показывает процент отправки и даёт её отменить", async () => {
      const importer = vi
        .spyOn(gitSyncApi, "importBundle")
        .mockImplementation((_project, _file, _password, options) => {
          options?.onProgress?.(42);
          return new Promise((_resolve, reject) => {
            options?.signal?.addEventListener("abort", () => {
              const error = new Error("canceled");
              error.name = "CanceledError";
              reject(error);
            });
          });
        });
      mount();
      const user = await choose(bundle());
      await user.click(submit());

      const bar = await screen.findByRole("progressbar");
      expect(bar).toHaveAttribute("aria-valuenow", "42");
      expect(screen.getByTestId("import-upload")).toHaveTextContent("42%");
      expect(importer).toHaveBeenCalledTimes(1);

      await user.click(
        screen.getByRole("button", { name: "Отменить загрузку" }),
      );
      // Вернулись к выбору файла, файл остался выбранным.
      await screen.findByTestId("import-file");
      expect(screen.queryByRole("progressbar")).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("не закрывается, пока файл отправляется", async () => {
      vi.spyOn(gitSyncApi, "importBundle").mockReturnValue(
        new Promise(() => undefined),
      );
      const { onClose } = mount();
      const user = await choose(bundle());
      await user.click(submit());
      await screen.findByRole("progressbar");
      await user.keyboard("{Escape}");
      expect(onClose).not.toHaveBeenCalled();
    });

    it("после отправки следит за операцией и показывает шаги, пока она идёт", async () => {
      vi.spyOn(gitSyncApi, "importBundle").mockResolvedValue({
        operation_id: "op-1",
      });
      vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
        operation({ phase: "merge" }),
      );
      const cancel = vi
        .spyOn(gitSyncApi, "cancelOperation")
        .mockResolvedValue(operation({ status: "cancelled" }));
      mount();
      const user = await choose(bundle());
      await user.click(submit());

      const phases = await screen.findByTestId("import-phases");
      expect(phases).toHaveTextContent("Объединяем с проектом");
      expect(phases.querySelector('[aria-current="step"]')).toHaveTextContent(
        "Объединяем с проектом",
      );
      await user.click(screen.getByRole("button", { name: "Отменить" }));
      expect(cancel).toHaveBeenCalledWith("op-1");
    });

    it("отмена операции возвращает к выбору файла с пояснением", async () => {
      vi.spyOn(gitSyncApi, "importBundle").mockResolvedValue({
        operation_id: "op-1",
      });
      vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
        operation({ status: "cancelled" }),
      );
      mount();
      const user = await choose(bundle());
      await user.click(submit());
      expect(await screen.findByText(/Загрузка отменена/)).toBeInTheDocument();
      expect(screen.getByTestId("import-file")).toBeInTheDocument();
    });

    it("не поднимает загрузку, если правки в редакторе не сохранились", async () => {
      vi.spyOn(sharedLib, "flushPendingSaves").mockResolvedValue({
        total: 1,
        failed: 1,
      });
      const importer = vi.spyOn(gitSyncApi, "importBundle");
      mount();
      const user = await choose(bundle());
      await user.click(submit());
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Не удалось сохранить правки в открытых файлах.",
      );
      expect(importer).not.toHaveBeenCalled();
    });
  });

  describe("итог", () => {
    const succeed = (result: typeof MERGED) => {
      vi.spyOn(gitSyncApi, "importBundle").mockResolvedValue({
        operation_id: "op-1",
      });
      vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
        operation({
          status: "succeeded",
          phase: "merge",
          finished_at: "2026-10-26T10:01:00Z",
          result,
        }),
      );
    };

    it("после слияния называет, что пришло, и закрывается кнопкой", async () => {
      succeed(MERGED);
      const { onClose } = mount();
      const user = await choose(bundle());
      await user.click(submit());
      const done = await screen.findByTestId("import-result-merged");
      expect(done).toHaveTextContent("Файл объединён с проектом");
      expect(done).toHaveTextContent("Новых версий");
      expect(done).toHaveTextContent("3");
      expect(done).toHaveTextContent("Объединено автоматически");
      await user.click(screen.getByRole("button", { name: "Готово" }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("когда в файле нет нового, говорит об этом спокойно", async () => {
      succeed({
        ...MERGED,
        outcome: "up_to_date",
        pulled_commits: 0,
        auto: [],
      });
      mount();
      const user = await choose(bundle());
      await user.click(submit());
      expect(
        await screen.findByTestId("import-result-up_to_date"),
      ).toHaveTextContent("В файле нет ничего нового");
    });

    it("передаёт предупреждения слияния", async () => {
      succeed({
        ...MERGED,
        warnings: [{ code: "signatures_stale", paths: ["a.pdf"] }],
      });
      mount();
      const user = await choose(bundle());
      await user.click(submit());
      expect(
        await screen.findByText("Подписи могли устареть"),
      ).toBeInTheDocument();
    });

    it("при конфликтах ведёт на экран конфликтов", async () => {
      succeed({
        ...MERGED,
        outcome: "conflicts",
        conflicts: { files_total: 2, files_open: 2 },
      });
      const onNavigate = vi.fn();
      const { onClose } = mount({ onNavigate });
      const user = await choose(bundle());
      await user.click(submit());
      const result = await screen.findByTestId("import-result-conflicts");
      expect(result).toHaveTextContent("Файлов с конфликтами: 2");
      await user.click(
        screen.getByRole("button", { name: "Открыть конфликты" }),
      );
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(onNavigate).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("location")).toHaveTextContent(
        `/projects/${PROJECT_ID}/sync/conflicts`,
      );
    });

    it("после слияния обновляет данные проекта один раз", async () => {
      succeed(MERGED);
      const { client } = mount();
      const invalidate = vi.spyOn(client, "invalidateQueries");
      const user = await choose(bundle());
      await user.click(submit());
      await screen.findByTestId("import-result-merged");
      await waitFor(() => {
        expect(invalidate).toHaveBeenCalled();
      });
      const calls = invalidate.mock.calls.length;
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(invalidate.mock.calls.length).toBe(calls);
    });
  });

  describe("отказы", () => {
    const reject = (
      code: string,
      status: number,
      detail: string,
      data = {},
    ) => {
      vi.spyOn(gitSyncApi, "importBundle").mockRejectedValue(
        new ApiError(detail, code, status, data),
      );
    };

    it.each([
      [
        "bundle_invalid",
        400,
        "Файл не похож на файл проекта Студии.",
        "Попроси выгрузить его ещё раз.",
      ],
      [
        "bundle_prerequisites_missing",
        400,
        "Нужен более ранний файл или полная выгрузка.",
        "Попроси коллегу выгрузить проект целиком.",
      ],
      [
        "unrelated_histories",
        409,
        "Файл относится к другому проекту.",
        "Проверь, тот ли файл ты выбрал.",
      ],
      [
        "not_a_studio_project",
        409,
        "В файле нет проекта Студии.",
        "Выгрузить bundle",
      ],
    ])(
      "файл с кодом %s объясняется под файлом",
      async (code, status, text, hint) => {
        reject(code, status, "server text");
        mount();
        const user = await choose(bundle());
        await user.click(submit());
        const alert = await screen.findByRole("alert");
        expect(alert).toHaveTextContent(text);
        expect(alert).toHaveTextContent(hint);
        // Файл остаётся выбранным: можно заменить и повторить.
        expect(screen.getByTestId("import-file")).toBeInTheDocument();
        expect(submit()).toBeEnabled();
      },
    );

    it("bundle_password_required просит пароль у файла без «.hseenc» в имени", async () => {
      reject("bundle_password_required", 400, "Нужен пароль");
      mount();
      const user = await choose(bundle("renamed.bundle"));
      expect(screen.queryByTestId("import-password")).toBeNull();
      await user.click(submit());
      const field = await screen.findByTestId("import-password");
      expect(field).toHaveAttribute("aria-invalid", "true");
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Архив зашифрован, нужен пароль.",
      );
      expect(submit()).toBeDisabled();
    });

    it("пароль для файла без «.hseenc» остаётся в поле и уходит на сервер", async () => {
      const importer = vi
        .spyOn(gitSyncApi, "importBundle")
        .mockRejectedValueOnce(
          new ApiError("Нужен пароль", "bundle_password_required", 400, {}),
        )
        .mockReturnValue(new Promise(() => undefined));
      mount();
      const user = await choose(bundle("renamed.bundle"));
      await user.click(submit());
      await user.type(await screen.findByTestId("import-password"), "secret");
      // Ввод снимает текст ошибки, но поле не исчезает.
      expect(screen.getByTestId("import-password")).toHaveValue("secret");
      expect(screen.queryByRole("alert")).toBeNull();
      expect(submit()).toBeEnabled();
      await user.click(submit());
      await waitFor(() => {
        expect(importer).toHaveBeenCalledTimes(2);
      });
      expect(importer.mock.calls[1]?.[2]).toBe("secret");
    });

    it("bundle_password_wrong отмечает поле пароля и снимается при вводе", async () => {
      reject("bundle_password_wrong", 400, "Пароль не подошёл.");
      mount();
      const user = await choose(bundle("a.bundle.hseenc"));
      await user.type(await screen.findByTestId("import-password"), "wrong");
      await user.click(submit());
      await waitFor(() => {
        expect(screen.getByTestId("import-password")).toHaveAttribute(
          "aria-invalid",
          "true",
        );
      });
      expect(screen.getByRole("alert")).toHaveTextContent("Пароль не подошёл.");
      await user.type(screen.getByTestId("import-password"), "x");
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("profile_required открывает окно «Представься» и закрывает внешнее окно", async () => {
      reject("profile_required", 409, "Нужен профиль");
      const onNavigate = vi.fn();
      const { onClose } = mount({ onNavigate });
      const user = await choose(bundle());
      await user.click(submit());
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Сначала укажи имя и e-mail автора",
      );
      await user.click(screen.getByRole("button", { name: "Указать автора" }));
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(onNavigate).toHaveBeenCalledTimes(1);
      expect(useSyncUiStore.getState().profileDialogOpen).toBe(true);
      expect(screen.getByTestId("location")).not.toHaveTextContent(
        "/settings/profile",
      );
    });

    it.each([
      ["sync_busy", 409, "Синхронизация уже идёт."],
      ["off_branch", 409, "Проект открыт не на рабочей ветке."],
      ["store_untrusted", 409, "Настройки истории проекта выглядят чужими."],
    ])(
      "состояние проекта %s показывается сообщением",
      async (code, status, text) => {
        reject(code, status, "server text");
        mount();
        const user = await choose(bundle());
        await user.click(submit());
        expect(await screen.findByRole("alert")).toHaveTextContent(text);
      },
    );

    it("неизвестный код показывает текст сервера", async () => {
      reject("brand_new_code", 502, "Сервер объяснил по-своему.");
      mount();
      const user = await choose(bundle());
      await user.click(submit());
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Сервер объяснил по-своему.",
      );
    });

    it("обрыв связи объясняется запасным текстом", async () => {
      vi.spyOn(gitSyncApi, "importBundle").mockRejectedValue(
        new Error("Network Error"),
      );
      mount();
      const user = await choose(bundle());
      await user.click(submit());
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Не получилось выполнить запрос.",
      );
    });

    it("отказ внутри операции возвращает к файлу с тем же объяснением", async () => {
      vi.spyOn(gitSyncApi, "importBundle").mockResolvedValue({
        operation_id: "op-1",
      });
      vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue(
        operation({
          status: "failed",
          error: {
            code: "bundle_prerequisites_missing",
            detail: "no base",
          },
        }),
      );
      mount();
      const user = await choose(bundle());
      await user.click(submit());
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Нужен более ранний файл или полная выгрузка.",
      );
      expect(screen.getByTestId("import-file")).toBeInTheDocument();
      // Повторная попытка начинается с чистого листа.
      vi.mocked(gitSyncApi.importBundle).mockClear();
      await user.click(submit());
      await waitFor(() => {
        expect(gitSyncApi.importBundle).toHaveBeenCalledTimes(1);
      });
    });

    it("смена файла снимает прежний отказ", async () => {
      reject("bundle_invalid", 400, "bad");
      mount();
      const user = await choose(bundle());
      await user.click(submit());
      await screen.findByRole("alert");
      await user.click(screen.getByRole("button", { name: "Убрать файл" }));
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });

  it("закрывается кнопкой «Отмена» и забывает выбранный файл", async () => {
    const { onClose } = mount();
    const user = await choose(bundle());
    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("import-dropzone")).toBeInTheDocument();
  });
});
