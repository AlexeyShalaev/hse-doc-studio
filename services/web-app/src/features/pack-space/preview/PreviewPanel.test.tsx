import type { QueryClient } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  packOutcomeKeys,
  packStudioApi,
  packStudioKeys,
  resetPackFilesRevision,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { GALLERY_WORKSPACE } from "../galleryKit";
import { useSituation } from "../context/useSituation";
import {
  PV_BUILD_ID,
  PV_DOC,
  PV_OFF_DOC,
  PV_REF,
  PV_VARIANT_DOC,
  outcomeRequestOf,
  previewBuild,
  previewOutcome,
} from "./fixtures";
import PreviewPanel from "./PreviewPanel";
import { renderPreview } from "./previewTestKit";

// Страница PDF в jsdom не рисуется: просмотрщик подменён меткой с адресом.
vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({ url }: { url: string }) => (
    <div data-testid="pdf-viewer" data-url={url} />
  ),
}));

const WS = GALLERY_WORKSPACE.id;
const location = () => screen.getByTestId("location").textContent;

/** Кнопка, которая меняет условие студента в адресе, как это делает полоса «Результата». */
const Driver = ({ id, value }: { id: string; value: string }) => {
  const situation = useSituation();
  return (
    <button
      type="button"
      data-testid="drive"
      onClick={() => {
        situation.setInput(id, value);
      }}
    >
      drive
    </button>
  );
};

const panel = (doc = PV_DOC, name = "Техническое задание") => (
  <PreviewPanel key={doc} docId={doc} docName={name} />
);

describe("предпросмотр PDF по условиям студента", () => {
  let start: MockInstance<typeof packStudioApi.startPreview>;
  beforeAll(async () => {
    // Radix Select ловит указатель; в jsdom этих методов нет.
    const proto = Element.prototype as Partial<Element> & {
      hasPointerCapture?: (id: number) => boolean;
      releasePointerCapture?: (id: number) => void;
      scrollIntoView?: () => void;
    };
    proto.hasPointerCapture ??= () => false;
    proto.releasePointerCapture ??= () => undefined;
    proto.scrollIntoView ??= () => undefined;
    await loadPackSpaceNamespace();
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    resetPackFilesRevision();
    start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([previewBuild("succeeded")]);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("собирает сам при открытии: по условиям из адреса и примеру по умолчанию, без единого выбора", async () => {
    renderPreview(panel(), "i.kind=research");

    expect(await screen.findByTestId("sp-pv-page")).toBeInTheDocument();
    expect(start).toHaveBeenCalledTimes(1);
    const [ws, ref, body] = start.mock.calls[0] ?? [];
    expect(ws).toBe(WS);
    expect(ref).toEqual(PV_REF);
    expect(body).toMatchObject({
      documents: [PV_DOC],
      example: "auto:normal",
      combination: { kind: "research" },
    });
    expect(screen.getByTestId("sp-pv-page")).toHaveTextContent("3 страницы");
  });

  it("сводка условий: главные условия словами и «Изменить условия»", async () => {
    renderPreview(panel(), "i.kind=research");
    await screen.findByTestId("sp-pv-page");

    const chips = screen.getByTestId("sp-pv-conditions");
    expect(chips).toHaveTextContent("Для какого студента");
    expect(chips.querySelectorAll(".sp-pv-chip").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByTestId("sp-pv-change"));
    expect(await screen.findByTestId("sp-sit-more")).toBeInTheDocument();
  });

  it("смена условий не пересобирает сама, а помечает страницу устаревшей; кнопка собирает заново", async () => {
    renderPreview(
      <>
        {panel()}
        <Driver id="kind" value="research" />
      </>,
      "",
      {
        before: (client) => {
          const request = outcomeRequestOf("i.kind=research");
          client.setQueryData(packOutcomeKeys.result(WS, PV_REF, request), {
            ...previewOutcome(),
            inputs: { ...previewOutcome().inputs, kind: "research" },
          });
        },
      },
    );
    await screen.findByTestId("sp-pv-page");
    expect(start).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("drive"));

    expect(await screen.findByTestId("sp-pv-stale")).toHaveTextContent(
      "Условия изменились после сборки. Соберите заново",
    );
    expect(start).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("sp-pv-build"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledTimes(2);
    });
    expect(start.mock.calls[1]?.[2]).toMatchObject({
      combination: { kind: "research" },
    });
    await waitFor(() => {
      expect(screen.queryByTestId("sp-pv-stale")).toBeNull();
    });
  });

  it("запись файла после сборки тоже устаревает страницу, словами про файлы", async () => {
    renderPreview(panel());
    await screen.findByTestId("sp-pv-page");

    const { notifyPackFilesSaved } = await import("@entities/pack-studio");
    act(() => {
      notifyPackFilesSaved(WS);
    });

    expect(await screen.findByTestId("sp-pv-stale")).toHaveTextContent(
      "Файлы изменились после сборки",
    );
  });

  it("документа нет в комплекте при этих условиях: объяснение и «Сбросить условия», сборки нет", async () => {
    renderPreview(panel(PV_OFF_DOC, "Соглашение"), "i.kind=research");

    expect(await screen.findByTestId("sp-pv-notinkit")).toHaveTextContent(
      "При этих условиях документа нет в комплекте",
    );
    expect(start).not.toHaveBeenCalled();
    expect(screen.queryByTestId("sp-pv-build")).toBeNull();
    fireEvent.click(screen.getByTestId("sp-pv-reset"));
    expect(location()).not.toContain("i.kind");
  });

  it("документ, который сервер в PDF не собирает: пояснение, сборки нет", async () => {
    renderPreview(panel("presentation", "Презентация"));

    expect(await screen.findByTestId("sp-pv-nopdf")).toHaveTextContent(
      "PDF для этого документа не собирается",
    );
    expect(start).not.toHaveBeenCalled();
  });

  it("сборка не удалась: причина словами, «Собрать ещё раз» и журнал; слов про Jinja и LaTeX нет", async () => {
    start.mockResolvedValue([
      previewBuild("failed", {
        finished_at: "2026-11-14T09:30:09Z",
        pages: null,
        error: { code: "build_failed", detail: null },
      }),
    ]);
    renderPreview(panel());

    const failed = await screen.findByTestId("sp-pv-failed");
    expect(failed).toHaveTextContent("PDF не собрался");
    expect(failed).toHaveTextContent(
      "Документ не собрался: в тексте есть ошибка.",
    );
    expect(failed.textContent).not.toMatch(/jinja|latex|раннер|контейнер/i);
    expect(screen.getByTestId("sp-pv-open-log")).toBeInTheDocument();

    start.mockResolvedValue([previewBuild("succeeded")]);
    fireEvent.click(screen.getByTestId("sp-pv-build"));
    expect(await screen.findByTestId("sp-pv-page")).toBeInTheDocument();
    expect(start).toHaveBeenCalledTimes(2);
  });

  it("сбой запуска: понятный заголовок, сообщение сервера в подробностях и повтор по кнопке", async () => {
    start.mockRejectedValueOnce(
      new ApiError("Сервер сборки недоступен.", "internal_error", 503),
    );
    renderPreview(panel());

    const failed = await screen.findByTestId("sp-pv-failed");
    expect(failed).toHaveTextContent("PDF не собрался");
    // Текст сервера остаётся в технических подробностях, а не в заголовке.
    expect(
      within(failed).getByText("Сервер сборки недоступен.").closest("details"),
    ).not.toBeNull();
    fireEvent.click(screen.getByTestId("sp-pv-build"));
    expect(await screen.findByTestId("sp-pv-page")).toBeInTheDocument();
  });

  it("квота сборок сказана словами с числом", async () => {
    start.mockRejectedValueOnce(
      new ApiError("Слишком много.", "preview_quota", 429, { limit: 2 }),
    );
    renderPreview(panel());

    expect(await screen.findByTestId("sp-pv-quota")).toHaveTextContent(
      "Сейчас идёт предельное число сборок (2)",
    );
  });

  it("идущая сборка: ожидание с «Отменить»", async () => {
    start.mockResolvedValue([previewBuild("running")]);
    const cancel = vi
      .spyOn(packStudioApi, "cancelPreview")
      .mockResolvedValue(previewBuild("cancelled"));
    renderPreview(panel());

    const wait = await screen.findByTestId("sp-pv-building");
    expect(wait).toHaveTextContent("Собираю PDF");
    fireEvent.click(within(wait).getByTestId("sp-pv-cancel"));
    await waitFor(() => {
      expect(cancel).toHaveBeenCalledWith(WS, PV_BUILD_ID);
    });
    expect(await screen.findByTestId("sp-pv-cancelled")).toBeInTheDocument();
  });

  it("пример данных: выбор пишется в адрес, сломанный пример не собирается и объяснён", async () => {
    renderPreview(panel());
    await screen.findByTestId("sp-pv-page");

    const select = screen.getByRole("combobox", { name: "Пример данных" });
    expect(select).toBeInTheDocument();
    await userEvent.click(select);
    await userEvent.click(
      await screen.findByRole("option", { name: "Длинные ФИО" }),
    );
    expect(location()).toContain("example=long_names");
  });

  it("сломанный пример из адреса: пояснение, автосборки нет", async () => {
    renderPreview(panel(), "example=broken");

    expect(await screen.findByTestId("sp-pv-broken")).toHaveTextContent(
      "Этот пример данных не читается: строка 3: ожидался ключ.",
    );
    expect(start).not.toHaveBeenCalled();
  });

  it("варианты документа выбираются тут же; вариант без PDF предупреждён", async () => {
    renderPreview(panel(PV_VARIANT_DOC, "Программа"));
    await screen.findByTestId("sp-pv-page");
    expect(start.mock.calls[0]?.[2]).toMatchObject({ variant: "main" });

    await userEvent.click(
      screen.getByRole("combobox", { name: "Вариант документа" }),
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "Слайды" }),
    );

    expect(await screen.findByTestId("sp-pv-variant-nopdf")).toHaveTextContent(
      "Из этого варианта PDF не собирается.",
    );
  });

  it("параметры сборки не пришли: объяснение и повтор", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockRejectedValue(
      new ApiError("Нет связи.", "internal_error", 500),
    );
    renderPreview(panel(), "", {
      before: (client: QueryClient) => {
        client
          .getQueryCache()
          .build(client, {
            queryKey: packStudioKeys.previewOptions(WS, PV_REF),
          })
          .setState({
            status: "error",
            fetchStatus: "idle",
            data: undefined,
            error: new ApiError("Нет связи.", "internal_error", 500),
            errorUpdateCount: 1,
          });
      },
    });

    expect(await screen.findByTestId("sp-pv-unavailable")).toHaveTextContent(
      "Не удалось подготовить предпросмотр.",
    );
    expect(start).not.toHaveBeenCalled();
  });

  it("закрытие панели отменяет идущую сборку", async () => {
    start.mockResolvedValue([previewBuild("running")]);
    const cancel = vi
      .spyOn(packStudioApi, "cancelPreview")
      .mockResolvedValue(previewBuild("cancelled"));
    const view = renderPreview(panel());
    await screen.findByTestId("sp-pv-building");

    view.unmount();

    await waitFor(() => {
      expect(cancel).toHaveBeenCalledWith(WS, PV_BUILD_ID);
    });
  });

  it("на экране нет слов из словаря «жаргон»", async () => {
    renderPreview(panel());
    await screen.findByTestId("sp-pv-page");
    expect(screen.getByTestId("sp-preview").textContent).not.toMatch(
      /комбинаци|набор данных|раннер|вводн|сценари/i,
    );
  });
});
