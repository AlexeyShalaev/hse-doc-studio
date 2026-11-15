import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  PackStaleFileError,
  packStudioApi,
  type PackFile,
  type PackLint,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { PackFileEditor } from "./PackFileEditor";

// CodeMirror в jsdom не поднимается: редактор подменён полем, находки видны атрибутом.
vi.mock("@shared/ui/CodeEditor", async () => {
  const { createElement } = await import("react");
  return {
    CodeEditor: ({
      value,
      onChange,
      readOnly,
      diagnostics,
      ariaLabel,
    }: {
      value: string;
      onChange?: (value: string) => void;
      readOnly?: boolean;
      diagnostics?: { line: number; message: string }[];
      ariaLabel?: string;
    }) =>
      createElement("textarea", {
        "aria-label": ariaLabel,
        "data-testid": "code",
        "data-diagnostics": (diagnostics ?? [])
          .map((d) => `${String(d.line)}:${d.message}`)
          .join("|"),
        value,
        readOnly,
        onChange: (event: { target: { value: string } }) => {
          onChange?.(event.target.value);
        },
      }),
  };
});

const V = "demo/templates/report/versions/2026.1.1";
const MANIFEST = `${V}/version.yaml`;

const file = (patch: Partial<PackFile> = {}): PackFile => ({
  path: MANIFEST,
  content: 'id: "2026.1.1"\n',
  etag: '"e1"',
  readOnly: null,
  ...patch,
});

const LINT: PackLint = {
  scope: "version",
  target: V,
  released: false,
  errors: 2,
  warnings: 1,
  findings: [
    {
      severity: "error",
      check: "schema",
      message: "/status: 'nope' is not one of ['stable', 'beta', 'deprecated']",
      path: MANIFEST,
      line: 3,
      pointer: "/status",
    },
    {
      severity: "error",
      check: "lint",
      message: "report/main.tex:3: Jinja TemplateSyntaxError",
      path: `${V}/files/report/main.tex`,
      line: 3,
      pointer: null,
    },
    {
      severity: "warning",
      check: "lint",
      message: "v1-раскладка",
      path: null,
      line: null,
      pointer: null,
    },
  ],
};

const mount = (props: Partial<Parameters<typeof PackFileEditor>[0]> = {}) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onOpenFile = vi.fn();
  const onSaved = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PackFileEditor
          workspaceId="ws1"
          path={MANIFEST}
          lintEpoch={0}
          onSaved={onSaved}
          onOpenFile={onOpenFile}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onOpenFile, onSaved };
};

describe("редактор файла пака", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const stub = (opened: PackFile = file()) => {
    vi.spyOn(packStudioApi, "readFile").mockResolvedValue(opened);
    vi.spyOn(packStudioApi, "lint").mockResolvedValue(LINT);
    vi.spyOn(packStudioApi, "hints").mockResolvedValue({
      version: V,
      meta_fields: [],
      macros: [],
    });
  };

  it("находки открытого файла в строке, остальные в «Проблемах» с переходом к файлу", async () => {
    stub();
    const { onOpenFile } = mount();
    const code = await screen.findByTestId("code");
    await waitFor(() => {
      expect(code.getAttribute("data-diagnostics")).toContain("3:/status");
    });
    expect(code.getAttribute("data-diagnostics")).not.toContain("Jinja");
    expect(packStudioApi.lint).toHaveBeenCalledWith("ws1", V);

    const panel = screen.getByTestId("problems-panel");
    expect(within(panel).getByText("2 ошибки")).toBeInTheDocument();
    expect(within(panel).getByText("Версия целиком")).toBeInTheDocument();
    await userEvent.click(
      within(panel).getByText("report/main.tex:3: Jinja TemplateSyntaxError"),
    );
    expect(onOpenFile).toHaveBeenCalledWith(`${V}/files/report/main.tex`, 3);
    // У YAML-манифеста вкладка «Исходник», форма впереди.
    expect(screen.getByRole("tab", { name: "Исходник" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Форма" })).toBeDisabled();
  });

  it("сохранение с If-Match по версии открытого файла и перепроверка", async () => {
    stub();
    const write = vi
      .spyOn(packStudioApi, "writeFile")
      .mockResolvedValue({ path: MANIFEST, etag: '"e2"', size: 20 });
    const { onSaved } = mount();
    const code = await screen.findByTestId("code");
    const save = screen.getByTestId("editor-save");
    expect(save).toBeDisabled();
    await userEvent.type(code, "status: beta");
    expect(screen.getByTestId("editor-status")).toHaveTextContent(
      "Есть несохранённые правки",
    );
    await userEvent.click(save);
    await waitFor(() => {
      expect(write).toHaveBeenCalledWith(
        "ws1",
        MANIFEST,
        'id: "2026.1.1"\nstatus: beta',
        '"e1"',
      );
    });
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalled();
    });
    expect(screen.getByTestId("editor-status")).toHaveTextContent("Сохранено");
  });

  it("чужая правка: баннер, «Оставить мою» пишет поверх их версии", async () => {
    stub();
    const write = vi
      .spyOn(packStudioApi, "writeFile")
      .mockRejectedValueOnce(new PackStaleFileError("id: theirs\n", '"e9"'))
      .mockResolvedValueOnce({ path: MANIFEST, etag: '"e10"', size: 9 });
    mount();
    const code = await screen.findByTestId("code");
    await userEvent.type(code, "x");
    await userEvent.click(screen.getByTestId("editor-save"));
    expect(await screen.findByTestId("stale-banner")).toHaveTextContent(
      "Файл изменился",
    );
    await userEvent.click(screen.getByTestId("stale-keep-mine"));
    await waitFor(() => {
      expect(write).toHaveBeenLastCalledWith(
        "ws1",
        MANIFEST,
        'id: "2026.1.1"\nx',
        '"e9"',
      );
    });
    await waitFor(() => {
      expect(screen.queryByTestId("stale-banner")).not.toBeInTheDocument();
    });
  });

  it("файл выпущенной версии только для чтения, кнопки записи нет", async () => {
    stub(file({ readOnly: "version_released" }));
    mount();
    const code = await screen.findByTestId("code");
    expect(code).toHaveAttribute("readonly");
    expect(screen.queryByTestId("editor-save")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Версия выпущена: её файлы только для чтения/),
    ).toBeInTheDocument();
  });

  it("файл вне версий и манифестов не проверяется; предпросмотр ждёт своего среза", async () => {
    stub(file({ path: "README.md", content: "# Паки\n" }));
    mount({ path: "README.md" });
    await screen.findByTestId("code");
    expect(screen.getByTestId("problems-none")).toBeInTheDocument();
    expect(packStudioApi.lint).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("side-tab-preview"));
    expect(screen.getByTestId("preview-placeholder")).toBeInTheDocument();
  });
});
