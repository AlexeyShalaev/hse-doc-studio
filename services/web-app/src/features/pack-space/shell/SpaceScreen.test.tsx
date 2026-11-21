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
import { readPlace } from "../context/memory";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { SpaceScreen } from "./SpaceScreen";
import { defineSpaceSlots } from "./spaceSlots";

const text = (name: string) => () => <div>{name}</div>;
const location = () => screen.getByTestId("location").textContent;

const SLOTS = defineSpaceSlots({
  header: text("S header"),
  changesButton: text("S changesButton"),
  nextStep: text("S nextStep"),
  changes: text("S changes"),
  nav: { result: text("S nav.result"), content: text("S nav.content") },
  mainTop: { result: text("S mainTop.result") },
  main: { result: text("S main.result"), content: text("S main.content") },
  details: { result: text("S details.result") },
});

describe("SpaceScreen", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("без областей: название пространства, три вкладки и заглушка", () => {
    renderSpace(<SpaceScreen slots={{}} phone={false} />);
    expect(screen.getByTestId("sp-ws-name")).toHaveTextContent(
      "AlexeyShalaev/hse-doc-studio",
    );
    const tabs = ["result", "content", "check"].map((tab) =>
      screen.getByTestId(`sp-tab-${tab}`),
    );
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      "Результат",
      "Содержимое",
      "Проверка",
    ]);
    expect(tabs[0]).toHaveAttribute("aria-current", "page");
    expect(tabs[1]).not.toHaveAttribute("aria-current");
    expect(screen.getByTestId("sp-soon")).toHaveTextContent("Скоро");
  });

  it("переключение вкладок меняет адрес и сбрасывает выбор", () => {
    renderSpace(
      <SpaceScreen slots={{}} phone={false} />,
      `${SPACE_BASE}/2026.1.3/result?sel=documents%3Ats&i.kind=research`,
    );
    fireEvent.click(screen.getByTestId("sp-tab-content"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/content?i.kind=research`);
    expect(screen.getByTestId("sp-tab-content")).toHaveAttribute(
      "aria-current",
      "page",
    );
    fireEvent.click(screen.getByTestId("sp-tab-check"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/check?i.kind=research`);
  });

  it("телефон: нижние вкладки с «Изменениями», вкладок во второй полосе нет", () => {
    renderSpace(<SpaceScreen slots={{}} phone />);
    expect(screen.getByTestId("sp-bottom")).toBeInTheDocument();
    expect(screen.queryByTestId("sp-tab-result")).toBeNull();
    for (const id of ["result", "content", "check", "changes"]) {
      expect(screen.getByTestId(`sp-bottom-${id}`)).toBeInTheDocument();
    }
    fireEvent.click(screen.getByTestId("sp-bottom-changes"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result?changes=1`);
    expect(screen.getByTestId("sp-bottom-changes")).toHaveAttribute(
      "aria-current",
      "page",
    );
    fireEvent.click(screen.getByTestId("sp-bottom-content"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/content`);
  });

  it("слоты областей встают на места и подбираются по вкладке", () => {
    renderSpace(<SpaceScreen slots={SLOTS} phone={false} />);
    expect(screen.getByTestId("sp-bar")).toHaveTextContent("S header");
    expect(screen.getByTestId("sp-bar")).toHaveTextContent("S changesButton");
    expect(screen.getByTestId("sp-bar")).toHaveTextContent("S nextStep");
    expect(screen.getByTestId("sp-nav")).toHaveTextContent("S nav.result");
    expect(screen.getByTestId("sp-main-top")).toHaveTextContent(
      "S mainTop.result",
    );
    expect(screen.getByTestId("sp-main")).toHaveTextContent("S main.result");
    expect(screen.getByTestId("sp-side")).toHaveTextContent("S details.result");
    // Слот header заменил запасный, вкладки каркаса остались.
    expect(screen.queryByTestId("sp-ws-name")).toBeNull();
    expect(screen.getByTestId("sp-tab-result")).toBeInTheDocument();
  });

  it("на другой вкладке чужих слотов нет: нет mainTop и details, есть свои nav и main", () => {
    renderSpace(
      <SpaceScreen slots={SLOTS} phone={false} />,
      `${SPACE_BASE}/2026.1.3/content`,
    );
    expect(screen.getByTestId("sp-nav")).toHaveTextContent("S nav.content");
    expect(screen.getByTestId("sp-main")).toHaveTextContent("S main.content");
    expect(screen.queryByTestId("sp-main-top")).toBeNull();
    expect(screen.queryByTestId("sp-side")).toBeNull();
    renderSpace(
      <SpaceScreen slots={SLOTS} phone={false} />,
      `${SPACE_BASE}/2026.1.3/check`,
    );
    expect(screen.getAllByTestId("sp-soon").length).toBeGreaterThan(0);
  });

  it("выбор элемента открывает подробности, Esc снимает выбор", () => {
    renderSpace(
      <SpaceScreen slots={SLOTS} phone={false} />,
      `${SPACE_BASE}/2026.1.3/result?sel=documents%3Ats`,
    );
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "true");
    fireEvent.keyDown(screen.getByText("S details.result"), { key: "Escape" });
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result`);
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "false");
  });

  it("changes=1 показывает панель вместо подробностей, Esc закрывает её", () => {
    renderSpace(
      <SpaceScreen slots={SLOTS} phone={false} />,
      `${SPACE_BASE}/2026.1.3/result?changes=1&sel=documents%3Ats`,
    );
    expect(screen.getByTestId("sp-side")).toHaveTextContent("S changes");
    expect(screen.queryByText("S details.result")).toBeNull();
    fireEvent.keyDown(screen.getByText("S changes"), { key: "Escape" });
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result?sel=documents%3Ats`);
    expect(screen.getByTestId("sp-side")).toHaveTextContent("S details.result");
  });

  it("сбой одного слота не роняет остальные", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const Broken = () => {
      throw new Error("boom");
    };
    renderSpace(
      <SpaceScreen
        slots={{ ...SLOTS, main: { result: Broken } }}
        phone={false}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("не загрузилась");
    expect(screen.getByTestId("sp-nav")).toHaveTextContent("S nav.result");
    expect(screen.getByTestId("sp-bar")).toHaveTextContent("S nextStep");
    spy.mockRestore();
  });

  it("запоминает последнее место", () => {
    renderSpace(
      <SpaceScreen slots={{}} phone={false} />,
      `${SPACE_BASE}/2026.1.3/check?i.kind=research`,
    );
    expect(readPlace("gallery-ws")).toEqual({
      ref: { pack: "hse-cs-sse", template: "coursework", version: "2026.1.3" },
      tab: "check",
      inputs: { kind: "research" },
    });
  });
});
