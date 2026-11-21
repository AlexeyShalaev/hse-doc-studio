import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { CONTENT_BASE, renderContent } from "./contentTestKit";
import { ContentNavView } from "./ContentNav";
import ContentNav from "./ContentNav";
import { setContentDirty } from "./contentGuard";
import { modelWithDocuments } from "./fixtures";

const location = () => screen.getByTestId("location").textContent;

describe("навигация «Что редактируем»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    setContentDirty("test", false);
    vi.restoreAllMocks();
    cleanup();
  });

  it("документы списком с числами, разделы версии и «Все файлы» внизу", () => {
    renderContent(<ContentNav />);
    const nav = screen.getByTestId("ct-nav");
    expect(within(nav).getByText("Документы")).toBeInTheDocument();
    expect(within(nav).getByText("8")).toBeInTheDocument();
    expect(
      within(nav).getByTestId("ct-doc-technical_specification"),
    ).toHaveTextContent("Техническое задание");
    for (const [part, label, count] of [
      ["fields", "Данные проекта", "18"],
      ["forms", "Анкеты", "2"],
      ["deadlines", "Сроки и сдача", "3"],
      ["signatures", "Подписи и места", "6"],
      ["languages", "Языки", null],
      ["rules", "Правила проверки", null],
      ["files", "Все файлы", null],
    ] as const) {
      const item = within(nav).getByTestId(`ct-part-${part}`);
      expect(item).toHaveTextContent(label);
      if (count) expect(item).toHaveTextContent(count);
    }
    expect(within(nav).getByTestId("ct-part-files")).toHaveTextContent(
      "для опытных",
    );
  });

  it("пустой адрес: активен последний документ из памяти, иначе первый", () => {
    window.localStorage.setItem(
      "ps.space.gallery-ws",
      JSON.stringify({ ui: { "content.doc": "nda" } }),
    );
    const { unmount } = renderContent(<ContentNav />);
    expect(screen.getByTestId("ct-doc-nda")).toHaveAttribute(
      "aria-current",
      "page",
    );
    unmount();
    window.localStorage.clear();
    renderContent(<ContentNav />);
    expect(
      screen.getByTestId("ct-doc-technical_specification"),
    ).toHaveAttribute("aria-current", "page");
  });

  it("клик по документу меняет адрес заменой записи и сбрасывает сегмент", () => {
    renderContent(<ContentNav />, "doc=nda&seg=terms&file=nda%2Fnda.tex");
    fireEvent.click(screen.getByTestId("ct-doc-operator_manual"));
    expect(location()).toBe(`${CONTENT_BASE}?doc=operator_manual`);
    expect(screen.getByTestId("ct-doc-operator_manual")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("раздел и «Все файлы» открывают part, активен ровно один пункт", () => {
    renderContent(<ContentNav />, "doc=nda");
    fireEvent.click(screen.getByTestId("ct-part-forms"));
    expect(location()).toBe(`${CONTENT_BASE}?part=forms`);
    expect(screen.getByTestId("ct-part-forms")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByTestId("ct-doc-nda")).not.toHaveAttribute(
      "aria-current",
    );
    fireEvent.click(screen.getByTestId("ct-part-files"));
    expect(location()).toBe(`${CONTENT_BASE}?part=files`);
    expect(
      document.querySelectorAll('[data-testid="ct-nav"] [aria-current="page"]'),
    ).toHaveLength(1);
  });

  it("заголовок «Документы» ведёт в состав документов версии", () => {
    renderContent(<ContentNav />, "doc=nda");
    fireEvent.click(screen.getByTestId("ct-part-documents"));
    expect(location()).toBe(`${CONTENT_BASE}?part=documents`);
    expect(screen.getByTestId("ct-part-documents")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      document.querySelectorAll('[data-testid="ct-nav"] [aria-current="page"]'),
    ).toHaveLength(1);
  });

  it("поиск есть, только когда документов больше десяти", () => {
    const { unmount } = renderContent(<ContentNav />);
    expect(screen.queryByTestId("ct-search")).toBeNull();
    unmount();
    renderContent(<ContentNav />, "", { model: modelWithDocuments(16) });
    const search = screen.getByTestId("ct-search");
    fireEvent.change(search, {
      target: { value: "дополнительный" },
    });
    expect(screen.getAllByTestId(/^ct-doc-extra_document_/)).toHaveLength(8);
    expect(screen.queryByTestId("ct-doc-nda")).toBeNull();
    fireEvent.change(search, { target: { value: "нет такого" } });
    expect(screen.getByText("Такого документа нет")).toBeInTheDocument();
  });

  it("несохранённая правка: уход спрашивает, отказ оставляет на месте", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderContent(<ContentNav />, "doc=technical_specification");
    setContentDirty("test", true);
    fireEvent.click(screen.getByTestId("ct-doc-nda"));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(location()).toBe(`${CONTENT_BASE}?doc=technical_specification`);
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByTestId("ct-doc-nda"));
    expect(location()).toBe(`${CONTENT_BASE}?doc=nda`);
    // Согласие снимает охрану: следующий переход не спрашивает.
    confirm.mockClear();
    fireEvent.click(screen.getByTestId("ct-doc-operator_manual"));
    expect(confirm).not.toHaveBeenCalled();
  });

  it("версия без документов: подсказка вместо списка", () => {
    const model = { ...modelWithDocuments(0), documents: [] };
    renderContent(<ContentNav />, "", { model });
    expect(
      screen.getByText("В версии пока нет документов."),
    ).toBeInTheDocument();
  });

  it("ContentNavView отдельно от слота: префикс testid", () => {
    renderContent(
      <ContentNavView
        testId="x"
        data={{
          workspaceId: "gallery-ws",
          versionDir: "d",
          readOnly: false,
          status: "ready",
          error: null,
          refetch: () => undefined,
          docs: [],
          counts: {},
        }}
        route={{ kind: "none" }}
      />,
    );
    expect(screen.getByTestId("x-nav")).toBeInTheDocument();
  });
});
