import { cleanup, fireEvent, screen } from "@testing-library/react";
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
import ContentMain from "./ContentMain";
import { CONTENT_MODEL, RELEASED_MODEL } from "./fixtures";

// Сегменты и разделы подменены пробами: их содержимое (редактор, формы) тестируют срезы, которым
// они принадлежат, а здесь проверяется рамка и что именно получает расширение.
vi.mock("./registry", () => {
  const segment = (name: string) => (props: Record<string, unknown>) => (
    <output data-testid={`probe-segment-${name}`}>
      {JSON.stringify({
        doc: (props.doc as { id: string }).id,
        file: props.file,
        readOnly: props.readOnly,
        versionDir: props.versionDir,
      })}
    </output>
  );
  const part = (name: string) => (props: Record<string, unknown>) => (
    <output data-testid={`probe-part-${name}`}>
      {JSON.stringify({
        at: props.at,
        file: props.file,
        readOnly: props.readOnly,
      })}
    </output>
  );
  return {
    SEGMENT_COMPONENTS: {
      terms: segment("terms"),
      text: segment("text"),
      signatures: segment("signatures"),
    },
    PART_COMPONENTS: Object.fromEntries(
      [
        "fields",
        "forms",
        "deadlines",
        "signatures",
        "languages",
        "rules",
        "files",
      ].map((name) => [name, part(name)]),
    ),
  };
});

const location = () => screen.getByTestId("location").textContent;
const probe = (id: string) =>
  JSON.parse(screen.getByTestId(id).textContent) as Record<string, unknown>;

describe("центр «Содержимого»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("пустой адрес: первый документ, сегмент «Текст»", async () => {
    renderContent(<ContentMain />);
    expect(await screen.findByTestId("probe-segment-text")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Техническое задание",
    );
    expect(screen.getByTestId("ct-seg-text")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("расширение получает документ, файл, каталог версии и право писать", async () => {
    renderContent(<ContentMain />, "doc=nda&seg=signatures&file=nda%2Fnda.tex");
    await screen.findByTestId("probe-segment-signatures");
    expect(probe("probe-segment-signatures")).toEqual({
      doc: "nda",
      file: "nda/nda.tex",
      readOnly: false,
      versionDir: "hse-cs-sse/templates/coursework/versions/2026.1.3",
    });
  });

  it("сегменты переключаются ссылками и пишут адрес заменой", async () => {
    renderContent(<ContentMain />, "doc=nda");
    await screen.findByTestId("probe-segment-text");
    fireEvent.click(screen.getByTestId("ct-seg-terms"));
    expect(location()).toBe(`${CONTENT_BASE}?doc=nda&seg=terms`);
    await screen.findByTestId("probe-segment-terms");
    fireEvent.click(screen.getByTestId("ct-seg-text"));
    expect(location()).toBe(`${CONTENT_BASE}?doc=nda`);
  });

  it("помнит последний документ и сегмент для пустого адреса", async () => {
    const first = renderContent(<ContentMain />, "doc=nda&seg=terms");
    await first.findByTestId("probe-segment-terms");
    first.unmount();
    renderContent(<ContentMain />);
    expect(
      await screen.findByTestId("probe-segment-terms"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Соглашение о неразглашении",
    );
  });

  it("раздел версии: заголовок и указатель в расширение", async () => {
    renderContent(<ContentMain />, "part=forms&at=%2Fforms%2F1");
    await screen.findByTestId("probe-part-forms");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Анкеты",
    );
    expect(probe("probe-part-forms")).toEqual({
      at: "/forms/1",
      file: null,
      readOnly: false,
    });
  });

  it("документа нет в версии: сказано, не пустой экран", async () => {
    renderContent(<ContentMain />, "doc=gone");
    expect(await screen.findByTestId("ct-doc-missing")).toHaveTextContent(
      "gone",
    );
  });

  it("выпущенная версия: плашка, замок и readOnly в расширение", async () => {
    renderContent(<ContentMain />, "doc=nda", {
      model: RELEASED_MODEL,
      version: "2026.1.2",
    });
    expect(await screen.findByTestId("ct-released")).toHaveTextContent(
      "Версия 2026.1.2 выпущена и не меняется. Нажмите «Править копию»",
    );
    expect(screen.getByTestId("ct-readonly")).toBeInTheDocument();
    expect(probe("probe-segment-text").readOnly).toBe(true);
  });

  it("черновик: ни плашки, ни замка", async () => {
    renderContent(<ContentMain />, "doc=nda");
    await screen.findByTestId("probe-segment-text");
    expect(screen.queryByTestId("ct-released")).toBeNull();
    expect(screen.queryByTestId("ct-readonly")).toBeNull();
  });

  it("версия без документов: подсказка", async () => {
    const model = { ...CONTENT_MODEL, documents: [] };
    renderContent(<ContentMain />, "", { model });
    expect(await screen.findByTestId("ct-no-docs")).toBeInTheDocument();
  });
});
