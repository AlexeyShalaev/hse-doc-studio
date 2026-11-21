import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from "vitest";
import {
  PackStaleFileError,
  packStudioApi,
  packStudioKeys,
  resetPackFilesRevision,
  type PackLint,
} from "@entities/pack-studio";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { GALLERY_WORKSPACE } from "../../galleryKit";
import { renderSpace, SPACE_BASE } from "../../spaceTestKit";
import ContentMain from "../ContentMain";
import {
  CONTENT_TEXT,
  CONTENT_TEXT_PATH,
  CONTENT_VERSION_DIR,
  RELEASED_MODEL,
  seedContentModel,
  seedContentText,
} from "../fixtures";
import { AUTOSAVE_DELAY_MS } from "./autosave";

// CodeMirror в jsdom не поднимается: редактор подменён полем.
vi.mock("@shared/ui/CodeEditor", async () => {
  const { createElement } = await import("react");
  return {
    CodeEditor: ({
      value,
      onChange,
      readOnly,
      diagnostics,
      ariaLabel,
      reveal,
    }: {
      value: string;
      onChange?: (value: string) => void;
      readOnly?: boolean;
      diagnostics?: { line: number; message: string }[];
      ariaLabel?: string;
      reveal?: { line: number };
    }) =>
      createElement("textarea", {
        "aria-label": ariaLabel,
        "data-testid": "code",
        "data-reveal": reveal ? String(reveal.line) : undefined,
        "data-diagnostics": (diagnostics ?? []).length,
        value,
        readOnly,
        onChange: (event: { target: { value: string } }) => {
          onChange?.(event.target.value);
        },
      }),
  };
});

const SEARCH = "doc=technical_specification&seg=text";
const WS = GALLERY_WORKSPACE.id;
const code = () => screen.getByTestId<HTMLTextAreaElement>("code");
const type = (value: string) => {
  fireEvent.change(code(), { target: { value } });
};
const wait = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

const lintWith = (findings: PackLint["findings"]): PackLint => ({
  scope: "version",
  target: CONTENT_VERSION_DIR,
  released: false,
  errors: 0,
  warnings: findings.length,
  findings,
});

describe("сегмент «Текст»", () => {
  let write: MockInstance<typeof packStudioApi.writeFile>;
  beforeAll(async () => {
    await loadPackSpaceNamespace();
    await loadPackStudioNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
    // Проверки версии лежат под ключом «сколько записей было»: каждый тест начинает с нуля.
    resetPackFilesRevision();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    write = vi
      .spyOn(packStudioApi, "writeFile")
      .mockImplementation((_id, path, content) =>
        Promise.resolve({
          path,
          etag: `etag:${String(content.length)}`,
          size: 0,
        }),
      );
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const open = async (
    setup: (client: QueryClient) => void = seedContentText,
    version = "2026.1.3",
  ) => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    setup(client);
    renderSpace(
      <QueryClientProvider client={client}>
        <ContentMain />
      </QueryClientProvider>,
      `${SPACE_BASE}/${version}/content?${SEARCH}`,
    );
    await screen.findByTestId("ct-text");
  };

  it("правка записывается сама через 1,5 секунды, рядом «записано»", async () => {
    await open();
    expect(screen.queryByTestId("ct-text-state")).toBeNull();
    type("новый текст");
    await wait(AUTOSAVE_DELAY_MS - 100);
    expect(write).not.toHaveBeenCalled();
    await wait(200);
    expect(write).toHaveBeenCalledExactlyOnceWith(
      WS,
      CONTENT_TEXT_PATH,
      "новый текст",
      "etag-text",
    );
    expect(await screen.findByText("записано")).toBeInTheDocument();
    expect(screen.queryByText("Сохранить")).toBeNull();
  });

  it("смена сегмента сразу дописывает набранное, текст не теряется", async () => {
    await open();
    type("не успел дождаться паузы");
    fireEvent.click(screen.getByTestId("ct-seg-signatures"));
    // Не ждём паузы автосохранения: следующий сегмент подгружается лениво, затем текст дописывается.
    await waitFor(() => {
      expect(write).toHaveBeenCalledExactlyOnceWith(
        WS,
        CONTENT_TEXT_PATH,
        "не успел дождаться паузы",
        "etag-text",
      );
    });
  });

  it("конфликт: плашка с выбором, «Оставить мою» пишет поверх чужой версии", async () => {
    write.mockRejectedValueOnce(
      new PackStaleFileError("чужой текст", "etag-x"),
    );
    await open();
    type("моя правка");
    await wait(AUTOSAVE_DELAY_MS);
    expect(await screen.findByTestId("stale-banner")).toBeInTheDocument();
    expect(code().value).toBe("моя правка");
    fireEvent.click(screen.getByTestId("stale-keep-mine"));
    await wait(0);
    expect(write).toHaveBeenLastCalledWith(
      WS,
      CONTENT_TEXT_PATH,
      "моя правка",
      "etag-x",
    );
    await waitFor(() => {
      expect(screen.queryByTestId("stale-banner")).toBeNull();
    });
  });

  it("сбой записи: правка остаётся, есть «Повторить»", async () => {
    write.mockRejectedValueOnce(new Error("offline"));
    await open();
    type("правка");
    await wait(AUTOSAVE_DELAY_MS);
    expect(await screen.findByTestId("ct-text-failed")).toBeInTheDocument();
    expect(code().value).toBe("правка");
    fireEvent.click(screen.getByText("Повторить"));
    await wait(0);
    expect(write).toHaveBeenCalledTimes(2);
    await waitFor(() => {
      expect(screen.queryByTestId("ct-text-failed")).toBeNull();
    });
  });

  it("«Вернуть как было» возвращает текст, каким его открыли, и записывает", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await open();
    expect(screen.queryByTestId("ct-text-revert")).toBeNull();
    type("испорченный текст");
    await wait(AUTOSAVE_DELAY_MS);
    expect(write).toHaveBeenCalledTimes(1);
    fireEvent.click(await screen.findByTestId("ct-text-revert"));
    await wait(0);
    expect(code().value).toBe(CONTENT_TEXT.content);
    expect(write).toHaveBeenLastCalledWith(
      WS,
      CONTENT_TEXT_PATH,
      CONTENT_TEXT.content,
      "etag:17",
    );
  });

  it("ближайшее замечание с кнопкой «Исправить» чинит опечатку в поле", async () => {
    await open((client) => {
      seedContentText(client);
      client.setQueryData(packStudioKeys.file(WS, CONTENT_TEXT_PATH), {
        ...CONTENT_TEXT,
        content: "Краткое: {{ meta.name_shrt }}\n",
      });
      client.setQueryData(
        packStudioKeys.lint(WS, CONTENT_VERSION_DIR, "0"),
        lintWith([
          {
            severity: "warning",
            check: "outcome",
            message:
              "Шаблон читает project.meta.name_shrt, а такого поля нет в meta_fields версии.",
            path: CONTENT_TEXT_PATH,
            line: null,
            pointer: null,
          },
        ]),
      );
      client.setQueryData(packStudioKeys.hints(WS, CONTENT_VERSION_DIR), {
        version: CONTENT_VERSION_DIR,
        meta_fields: [
          { key: "name_short", type: "string", label: null, group: null },
        ],
        macros: [],
      });
    });
    const banner = await screen.findByTestId("ct-text-finding");
    expect(banner).toHaveTextContent("Строка 1");
    expect(banner).toHaveTextContent("Возможно, вы хотели «name_short»");
    fireEvent.click(screen.getByTestId("ct-text-fix"));
    expect(code().value).toBe("Краткое: {{ meta.name_short }}\n");
    await wait(AUTOSAVE_DELAY_MS);
    expect(write).toHaveBeenCalledWith(
      WS,
      CONTENT_TEXT_PATH,
      "Краткое: {{ meta.name_short }}\n",
      "etag-text",
    );
  });

  it("замечание без автоисправления показано без кнопки", async () => {
    await open((client) => {
      seedContentText(client);
      client.setQueryData(
        packStudioKeys.lint(WS, CONTENT_VERSION_DIR, "0"),
        lintWith([
          {
            severity: "error",
            check: "lint",
            message: "Jinja: незакрытая скобка",
            path: CONTENT_TEXT_PATH,
            line: 5,
            pointer: null,
          },
        ]),
      );
    });
    expect(await screen.findByTestId("ct-text-finding")).toHaveTextContent(
      "Строка 5: Jinja: незакрытая скобка",
    );
    expect(screen.queryByTestId("ct-text-fix")).toBeNull();
    fireEvent.click(screen.getByText("Строка 5:"));
    expect(code()).toHaveAttribute("data-reveal", "5");
  });

  it("выпущенная версия: только чтение и «Править копию» по контракту каркаса", async () => {
    const path = CONTENT_TEXT_PATH.replace("2026.1.3", "2026.1.2");
    await open((client) => {
      seedContentModel(client, RELEASED_MODEL);
      client.setQueryData(packStudioKeys.file(WS, path), {
        ...CONTENT_TEXT,
        path,
        readOnly: "version_released",
      });
    }, "2026.1.2");
    expect(code().readOnly).toBe(true);
    expect(screen.getByTestId("ct-text-lock")).toBeInTheDocument();
    expect(screen.queryByTestId("ct-text-revert")).toBeNull();
    fireEvent.click(screen.getByTestId("ct-text-copy"));
    expect(screen.getByTestId("location").textContent).toContain("copy=1");
    expect(write).not.toHaveBeenCalled();
  });
});
