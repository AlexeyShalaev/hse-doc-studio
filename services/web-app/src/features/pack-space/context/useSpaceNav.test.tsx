import { cleanup, fireEvent, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { useSituation } from "./useSituation";
import { useSpace } from "./SpaceContext";
import { useSpaceNav } from "./useSpaceNav";

const Panel = () => {
  const nav = useSpaceNav();
  const { tab, selection, released, version } = useSpace();
  const situation = useSituation();
  return (
    <div>
      <output data-testid="state">
        {JSON.stringify({
          tab,
          selection,
          released,
          status: version?.status,
          ...situation,
          setInput: undefined,
          setInputs: undefined,
          setCase: undefined,
          reset: undefined,
        })}
      </output>
      <a href={nav.href({ tab: "content", doc: "ts" })} data-testid="href">
        link
      </a>
      <button
        onClick={() => {
          nav.go({ sel: "documents:ts" });
        }}
      >
        select
      </button>
      <button
        onClick={() => {
          nav.go({ tab: "check", part: "map" });
        }}
      >
        check
      </button>
      <button
        onClick={() => {
          situation.setInput("kind", "research");
        }}
      >
        kind
      </button>
      <button
        onClick={() => {
          situation.setInput("kind", null);
        }}
      >
        unkind
      </button>
      <button
        onClick={() => {
          situation.setInputs({ a: "1" }, "c1");
        }}
      >
        set
      </button>
      <button
        onClick={() => {
          situation.reset();
        }}
      >
        reset
      </button>
    </div>
  );
};

const location = () => screen.getByTestId("location").textContent;
const state = () =>
  JSON.parse(screen.getByTestId("state").textContent ?? "{}") as Record<
    string,
    unknown
  >;

describe("useSpace, useSpaceNav, useSituation", () => {
  afterEach(cleanup);

  it("место: вкладка, версия и состояние берутся из дерева и адреса", () => {
    renderSpace(
      <Panel />,
      `${SPACE_BASE}/2026.1.3/result?sel=documents%3Ats&i.kind=research`,
    );
    expect(state()).toMatchObject({
      tab: "result",
      selection: "documents:ts",
      released: false,
      status: "beta",
      inputs: { kind: "research" },
    });
  });

  it("выпущенная версия видна как released", () => {
    renderSpace(<Panel />, `${SPACE_BASE}/2026.1.2/content`);
    expect(state()).toMatchObject({
      tab: "content",
      released: true,
      status: "stable",
    });
  });

  it("href строит адрес без перехода", () => {
    renderSpace(<Panel />);
    expect(screen.getByTestId("href").getAttribute("href")).toBe(
      `${SPACE_BASE}/2026.1.3/content?doc=ts`,
    );
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result`);
  });

  it("go меняет адрес: выбор остаётся на вкладке, переход на другую вкладку сбрасывает выбор", () => {
    renderSpace(<Panel />);
    fireEvent.click(screen.getByText("select"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result?sel=documents%3Ats`);
    fireEvent.click(screen.getByText("check"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/check?part=map`);
    expect(state().selection).toBeNull();
  });

  it("условия: задать, снять, заменить вместе со случаем, сбросить", () => {
    renderSpace(<Panel />);
    fireEvent.click(screen.getByText("kind"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result?i.kind=research`);
    fireEvent.click(screen.getByText("unkind"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result`);
    fireEvent.click(screen.getByText("set"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result?i.a=1&case=c1`);
    expect(state()).toMatchObject({ inputs: { a: "1" }, caseId: "c1" });
    fireEvent.click(screen.getByText("reset"));
    expect(location()).toBe(`${SPACE_BASE}/2026.1.3/result`);
  });

  it("условия переживают переход между вкладками", () => {
    renderSpace(
      <Panel />,
      `${SPACE_BASE}/2026.1.3/result?i.kind=research&sel=documents%3Ats`,
    );
    fireEvent.click(screen.getByText("check"));
    expect(location()).toBe(
      `${SPACE_BASE}/2026.1.3/check?i.kind=research&part=map`,
    );
  });

  it("вне SpaceProvider useSpace бросает понятную ошибку", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => renderHook(() => useSpace())).toThrow(/SpaceProvider/);
    spy.mockRestore();
  });
});
