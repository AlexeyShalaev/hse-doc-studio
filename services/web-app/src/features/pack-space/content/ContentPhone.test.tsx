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
import { SpacePhoneContext } from "../shell/phoneContext";
import { CONTENT_BASE, renderContent } from "./contentTestKit";
import ContentMain from "./ContentMain";

// «Содержимое» на телефоне (S11, 5.8): список «Что редактируем» страница первого уровня, правка
// следующая страница с кнопкой «назад», у документа кнопка «Предпросмотр PDF».

vi.mock("./registry", () => {
  const probe = (name: string) => () => (
    <output data-testid={`probe-${name}`}>{name}</output>
  );
  return {
    SEGMENT_COMPONENTS: {
      terms: probe("terms"),
      text: probe("text"),
      signatures: probe("signatures"),
    },
    PART_COMPONENTS: Object.fromEntries(
      [
        "documents",
        "fields",
        "forms",
        "deadlines",
        "signatures",
        "languages",
        "rules",
        "files",
      ].map((name) => [name, probe(name)]),
    ),
  };
});

const location = () => screen.getByTestId("location").textContent;
const phone = (search = "") =>
  renderContent(
    <SpacePhoneContext.Provider value>
      <ContentMain />
    </SpacePhoneContext.Provider>,
    search,
  );

describe("«Содержимое» на телефоне", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("пустой адрес: список разделов страницей, документ сам не открывается", async () => {
    phone();
    expect(await screen.findByTestId("ct-list")).toHaveTextContent(
      "Что редактируем",
    );
    expect(
      screen.getByTestId("ct-list-doc-technical_specification"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("ct-list-part-files")).toBeInTheDocument();
    expect(screen.queryByTestId("ct-doc")).toBeNull();
    expect(screen.queryByTestId("ct-back")).toBeNull();
    expect(location()).toBe(CONTENT_BASE);
  });

  it("строка списка открывает документ новой записью истории, «назад» браузера вернёт в список", async () => {
    phone();
    fireEvent.click(
      await screen.findByTestId("ct-list-doc-technical_specification"),
    );
    expect(location()).toContain("doc=technical_specification");
  });

  it("открыт документ: «назад» ведёт к списку и убирает doc, seg и file", async () => {
    phone("doc=technical_specification&seg=terms&file=x.tex");
    expect(await screen.findByTestId("ct-doc")).toBeInTheDocument();
    expect(screen.queryByTestId("ct-list")).toBeNull();
    const back = screen.getByTestId("ct-back");
    expect(back).toHaveTextContent("Что редактируем");
    fireEvent.click(back);
    expect(location()).toBe(CONTENT_BASE);
  });

  it("открыт раздел: тоже «назад» к списку", async () => {
    phone("part=languages");
    expect(await screen.findByTestId("ct-part")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("ct-back"));
    expect(location()).toBe(CONTENT_BASE);
  });

  it("«Все файлы» с открытым файлом: «назад» ведёт к дереву, а не в начало", async () => {
    phone("part=files&file=hse-cs-sse%2Fa.tex");
    const back = await screen.findByTestId("ct-back");
    expect(back).toHaveTextContent("Все файлы");
    fireEvent.click(back);
    expect(location()).toContain("part=files");
    expect(location()).not.toContain("file=");
  });

  it("у документа кнопка «Предпросмотр PDF» ставит preview=1", async () => {
    phone("doc=technical_specification");
    fireEvent.click(await screen.findByTestId("ct-preview-open"));
    expect(location()).toContain("preview=1");
    expect(location()).toContain("doc=technical_specification");
  });

  it("на широком экране пустой адрес по-прежнему открывает документ", async () => {
    renderContent(<ContentMain />);
    expect(await screen.findByTestId("ct-doc")).toBeInTheDocument();
    expect(screen.queryByTestId("ct-list")).toBeNull();
    expect(screen.queryByTestId("ct-back")).toBeNull();
  });
});
