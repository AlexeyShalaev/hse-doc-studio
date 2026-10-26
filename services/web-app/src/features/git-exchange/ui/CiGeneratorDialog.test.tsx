import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { documentApi } from "@entities/document";
import { gitRemoteApi } from "@entities/git-remote";
import { gitSyncApi, type CiPreview } from "@entities/git-sync";
import {
  CONTENTS,
  PROJECT_ID,
  renderExchange,
  resetExchangeEnvironment,
} from "../testing/renderExchange";
import { CiGeneratorDialog } from "./CiGeneratorDialog";

// Настоящий редактор тянет CodeMirror: для проверки хватит его содержимого.
vi.mock("@shared/ui/CodeEditor", () => ({
  CodeEditor: ({
    value,
    ariaLabel,
    readOnly,
    language,
  }: {
    value: string;
    ariaLabel?: string;
    readOnly?: boolean;
    language?: string;
  }) => (
    <pre
      aria-label={ariaLabel}
      data-readonly={String(readOnly)}
      data-language={language}
    >
      {value}
    </pre>
  ),
}));

const GITHUB_PATH = ".github/workflows/hse-studio-build.yml";

const preview = (overrides: Partial<CiPreview["files"][number]> = {}) =>
  ({
    files: [
      {
        path: GITHUB_PATH,
        content: "name: Сборка документов\non:\n  push:\n",
        exists: false,
        same: false,
        ...overrides,
      },
    ],
    command: "hse-doc-studio build --all",
    notes: ["PDF сохраняются как артефакты сборки."],
  }) satisfies CiPreview;

const DOCS = [
  { id: "thesis", def_id: "thesis", name: { ru: "Диплом", en: "Thesis" } },
  {
    id: "annotation",
    def_id: "annotation",
    name: { ru: "Аннотация", en: "Annotation" },
  },
];

const mount = () => {
  const onClose = vi.fn();
  renderExchange(
    <CiGeneratorDialog isOpen projectId={PROJECT_ID} onClose={onClose} />,
  );
  return { onClose };
};

const writeButton = () =>
  screen.getByRole("button", { name: "Записать в проект" });

describe("окно автосборки (CI)", () => {
  beforeEach(async () => {
    await resetExchangeEnvironment();
    vi.spyOn(gitSyncApi, "getContents").mockResolvedValue(CONTENTS);
    vi.spyOn(documentApi, "list").mockResolvedValue(
      DOCS as unknown as Awaited<ReturnType<typeof documentApi.list>>,
    );
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("сразу показывает файл только для чтения и команду для сборки у себя", async () => {
    const previewCi = vi
      .spyOn(gitRemoteApi, "previewCi")
      .mockResolvedValue(preview());
    mount();
    const view = await screen.findByLabelText(
      `Содержимое файла ${GITHUB_PATH}`,
    );
    expect(view).toHaveAttribute("data-readonly", "true");
    expect(view).toHaveAttribute("data-language", "yaml");
    expect(view).toHaveTextContent("name: Сборка документов");
    expect(screen.getByTestId("ci-path")).toHaveTextContent(GITHUB_PATH);
    expect(screen.getByTestId("ci-state-new")).toHaveTextContent("новый файл");
    expect(
      screen.getByDisplayValue("hse-doc-studio build --all"),
    ).toBeInTheDocument();
    expect(screen.getByText("Собрать то же самое у себя")).toBeInTheDocument();
    expect(previewCi).toHaveBeenCalledWith(PROJECT_ID, {
      provider: "github",
      docs: "all",
      publish: "artifacts",
      triggers: ["push"],
    });
    expect(writeButton()).toBeEnabled();
  });

  it("копирует файл целиком и сообщает об этом", async () => {
    const user = userEvent.setup();
    vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(preview());
    const writeText = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockResolvedValue(undefined);
    mount();
    await screen.findByTestId("ci-yaml");
    await user.click(screen.getByRole("button", { name: "Копировать файл" }));
    expect(writeText).toHaveBeenCalledWith(
      "name: Сборка документов\non:\n  push:\n",
    );
    expect(await screen.findByText("Скопировано")).toBeInTheDocument();
  });

  it("пересчитывает файл, когда меняют сервис, результат и запуски", async () => {
    const user = userEvent.setup();
    const previewCi = vi
      .spyOn(gitRemoteApi, "previewCi")
      .mockResolvedValue(preview());
    mount();
    await screen.findByTestId("ci-yaml");

    await user.click(screen.getByRole("radio", { name: "GitLab CI" }));
    await user.click(screen.getByRole("radio", { name: "Релиз" }));
    await user.click(screen.getByTestId("ci-trigger-tag"));
    await waitFor(() => {
      expect(previewCi).toHaveBeenLastCalledWith(PROJECT_ID, {
        provider: "gitlab",
        docs: "all",
        publish: "release",
        triggers: ["push", "tag"],
      });
    });
    expect(screen.getByText(/ставишь тег вида v1.0/)).toBeInTheDocument();
  });

  it("дает выбрать документы и не пускает дальше с пустым выбором", async () => {
    const user = userEvent.setup();
    const previewCi = vi
      .spyOn(gitRemoteApi, "previewCi")
      .mockResolvedValue(preview());
    mount();
    await screen.findByTestId("ci-yaml");

    await user.click(screen.getByRole("radio", { name: "Выбрать" }));
    expect(
      screen.getByText("Выбери хотя бы один документ."),
    ).toBeInTheDocument();
    expect(writeButton()).toBeDisabled();

    const list = await screen.findByTestId("ci-docs");
    await user.click(await within(list).findByLabelText("Диплом"));
    await waitFor(() => {
      expect(previewCi).toHaveBeenLastCalledWith(
        PROJECT_ID,
        expect.objectContaining({ docs: ["thesis"] }),
      );
    });
    expect(screen.queryByText("Выбери хотя бы один документ.")).toBeNull();
  });

  it("без единого запуска объясняет, что выбрать, и ждёт исправления", async () => {
    const user = userEvent.setup();
    vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(preview());
    mount();
    await screen.findByTestId("ci-yaml");
    await user.click(screen.getByTestId("ci-trigger-push"));
    expect(
      screen.getByText("Выбери хотя бы один способ запуска."),
    ).toBeInTheDocument();
    expect(writeButton()).toBeDisabled();
  });

  it("пишет файл в проект и сообщает, куда он попадёт", async () => {
    const user = userEvent.setup();
    vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(preview());
    const writeCi = vi
      .spyOn(gitRemoteApi, "writeCi")
      .mockResolvedValue({ written: [GITHUB_PATH] });
    const { onClose } = mount();
    await screen.findByTestId("ci-yaml");
    await user.click(writeButton());

    const done = await screen.findByTestId("ci-done");
    expect(writeCi).toHaveBeenCalledWith(PROJECT_ID, {
      provider: "github",
      docs: "all",
      publish: "artifacts",
      triggers: ["push"],
      overwrite: false,
    });
    expect(done).toHaveTextContent("при следующей синхронизации");
    expect(done).toHaveTextContent(GITHUB_PATH);
    await user.click(screen.getByRole("button", { name: "Готово" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  describe("файл уже есть в проекте", () => {
    it("отличающийся файл заменяется только после подтверждения", async () => {
      const user = userEvent.setup();
      vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(
        preview({ exists: true, same: false }),
      );
      const writeCi = vi
        .spyOn(gitRemoteApi, "writeCi")
        .mockResolvedValue({ written: [GITHUB_PATH] });
      mount();
      expect(await screen.findByTestId("ci-state-differs")).toHaveTextContent(
        "отличается",
      );
      expect(
        screen.getByText(/уже есть файл с этим именем/),
      ).toBeInTheDocument();
      expect(writeButton()).toBeDisabled();

      await user.click(screen.getByTestId("ci-overwrite"));
      expect(writeButton()).toBeEnabled();
      await user.click(writeButton());
      await screen.findByTestId("ci-done");
      expect(writeCi).toHaveBeenCalledWith(
        PROJECT_ID,
        expect.objectContaining({ overwrite: true }),
      );
    });

    it("смена настроек снимает подтверждение замены", async () => {
      const user = userEvent.setup();
      vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(
        preview({ exists: true, same: false }),
      );
      mount();
      await screen.findByTestId("ci-state-differs");
      await user.click(screen.getByTestId("ci-overwrite"));
      expect(writeButton()).toBeEnabled();
      await user.click(screen.getByTestId("ci-trigger-manual"));
      await waitFor(() => {
        expect(screen.getByTestId("ci-overwrite")).not.toBeChecked();
      });
      expect(writeButton()).toBeDisabled();
    });

    it("совпадающий файл не нужно писать заново", async () => {
      vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(
        preview({ exists: true, same: true }),
      );
      mount();
      expect(await screen.findByTestId("ci-state-same")).toHaveTextContent(
        "уже записан",
      );
      expect(screen.getByText(/Менять ничего не нужно/)).toBeInTheDocument();
      expect(writeButton()).toBeDisabled();
    });
  });

  describe("файлы под NDA", () => {
    it("требуют подтверждения, прежде чем записать файл", async () => {
      const user = userEvent.setup();
      vi.spyOn(gitSyncApi, "getContents").mockResolvedValue({
        ...CONTENTS,
        nda_files: 3,
      });
      vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(preview());
      vi.spyOn(gitRemoteApi, "writeCi").mockResolvedValue({
        written: [GITHUB_PATH],
      });
      mount();
      expect(
        await screen.findByText(/отправит содержимое проекта третьим лицам/),
      ).toBeInTheDocument();
      expect(writeButton()).toBeDisabled();
      await user.click(screen.getByTestId("ci-nda"));
      expect(writeButton()).toBeEnabled();
    });

    it("без таких файлов предупреждения нет", async () => {
      vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(preview());
      mount();
      await screen.findByTestId("ci-yaml");
      expect(screen.queryByTestId("ci-nda")).toBeNull();
    });
  });

  describe("сбои", () => {
    it("ошибку предпросмотра показывает с кнопкой повтора", async () => {
      const user = userEvent.setup();
      const previewCi = vi
        .spyOn(gitRemoteApi, "previewCi")
        .mockRejectedValueOnce(
          new ApiError("Сервер недоступен.", "timeout", 502),
        )
        .mockResolvedValue(preview());
      mount();
      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(writeButton()).toBeDisabled();
      await user.click(screen.getByRole("button", { name: "Повторить" }));
      await screen.findByTestId("ci-yaml");
      expect(previewCi).toHaveBeenCalledTimes(2);
    });

    it("ошибку записи показывает под файлом и оставляет настройки", async () => {
      const user = userEvent.setup();
      vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(preview());
      vi.spyOn(gitRemoteApi, "writeCi").mockRejectedValue(
        new ApiError("Проект открыт только для чтения.", "read_only", 423),
      );
      mount();
      await screen.findByTestId("ci-yaml");
      await user.click(writeButton());
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Проект открыт только для чтения.",
      );
      expect(screen.getByTestId("ci-yaml")).toBeInTheDocument();
      expect(writeButton()).toBeEnabled();
    });

    it("если список документов не загрузился, говорит об этом", async () => {
      const user = userEvent.setup();
      vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(preview());
      vi.spyOn(documentApi, "list").mockRejectedValue(new Error("down"));
      mount();
      await screen.findByTestId("ci-yaml");
      await user.click(screen.getByRole("radio", { name: "Выбрать" }));
      expect(
        await screen.findByText("Не удалось загрузить список документов."),
      ).toBeInTheDocument();
    });
  });

  it("закрывается кнопкой «Отмена»", async () => {
    const user = userEvent.setup();
    vi.spyOn(gitRemoteApi, "previewCi").mockResolvedValue(preview());
    const { onClose } = mount();
    await screen.findByTestId("ci-yaml");
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
