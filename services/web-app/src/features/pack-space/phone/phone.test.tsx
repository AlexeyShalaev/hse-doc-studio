import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { packStudioKeys } from "@entities/pack-studio";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { GALLERY_WORKSPACE } from "../galleryKit";
import { EDITED, gitStatus } from "../nav/fixtures";
import { SpaceScreen } from "../shell/SpaceScreen";
import { defineSpaceSlots, mergeSpaceSlots } from "../shell/spaceSlots";
import { spaceSlots } from "../shell/registry";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { slots as phoneSlots } from "./slots";

// Телефон нового интерфейса (S11): нижние вкладки с числом на «Изменениях», шторка подробностей
// с затемнением и крестиком, предпросмотр PDF из «Содержимого» на узком экране.

const location = () => screen.getByTestId("location").textContent;
const at = (tab: string, search = "") =>
  `${SPACE_BASE}/2026.1.3/${tab}${search}`;

const text = (name: string) => () => <div>{name}</div>;
const SLOTS = mergeSpaceSlots([
  ["phone", phoneSlots],
  [
    "test",
    defineSpaceSlots({
      changes: text("changes"),
      main: { result: text("main"), content: text("main.content") },
      details: { result: text("details"), content: text("preview") },
    }),
  ],
]);

const mount = (url: string, changed: string[] = EDITED) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(
    packStudioKeys.git(GALLERY_WORKSPACE.id),
    gitStatus(changed),
  );
  return renderSpace(
    <QueryClientProvider client={client}>
      <SpaceScreen slots={SLOTS} phone />
    </QueryClientProvider>,
    url,
  );
};

describe("телефон: нижние вкладки", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("слот bottomTabs занят областью «Телефон», запасные вкладки каркаса не нужны", () => {
    expect(spaceSlots.bottomTabs).toBe(phoneSlots.bottomTabs);
  });

  it("четыре вкладки, текущая отмечена, число изменённых файлов на «Изменениях»", () => {
    mount(at("content"));
    const tabs = screen.getByTestId("sp-phone-tabs");
    expect(tabs).toBeInTheDocument();
    expect(
      ["result", "content", "check", "changes"].map(
        (id) => screen.getByTestId(`sp-bottom-${id}`).textContent,
      ),
    ).toEqual(["Результат", "Содержимое", "Проверка", "3Изменения"]);
    expect(screen.getByTestId("sp-bottom-content")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByTestId("sp-bottom-result")).not.toHaveAttribute(
      "aria-current",
    );
    expect(screen.getByTestId("sp-bottom-count")).toHaveTextContent("3");
    expect(screen.getByTestId("sp-bottom-changes")).toHaveAccessibleName(
      "Изменения: 3 файла",
    );
  });

  it("нет изменений: значка с числом нет", () => {
    mount(at("result"), []);
    expect(screen.queryByTestId("sp-bottom-count")).toBeNull();
    expect(screen.getByTestId("sp-bottom-changes")).toHaveAccessibleName(
      "Изменения",
    );
  });

  it("«Изменения» открывают страницу и закрывают её же, вкладка снимает changes", () => {
    mount(at("result"));
    fireEvent.click(screen.getByTestId("sp-bottom-changes"));
    expect(location()).toBe(at("result", "?changes=1"));
    expect(screen.getByTestId("sp-changes-page")).toBeInTheDocument();
    expect(screen.getByTestId("sp-bottom-changes")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByTestId("sp-bottom-result")).not.toHaveAttribute(
      "aria-current",
    );
    fireEvent.click(screen.getByTestId("sp-bottom-changes"));
    expect(location()).toBe(at("result"));
    fireEvent.click(screen.getByTestId("sp-bottom-changes"));
    fireEvent.click(screen.getByTestId("sp-bottom-check"));
    expect(location()).toBe(at("check"));
  });

  it("при переходе условия студента остаются, выбор и параметры вкладки сбрасываются", () => {
    mount(at("result", "?sel=documents%3Ats&i.kind=research"));
    fireEvent.click(screen.getByTestId("sp-bottom-content"));
    expect(location()).toBe(at("content", "?i.kind=research"));
  });
});

describe("телефон: шторка подробностей", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("выбор элемента открывает шторку с ручкой, крестиком и затемнением", () => {
    mount(at("result", "?sel=documents%3Ats"));
    const side = screen.getByTestId("sp-side");
    expect(side).toHaveAttribute("data-open", "true");
    expect(side).toHaveTextContent("details");
    expect(side.querySelector(".sp-side-handle")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Закрыть" })).toBeInTheDocument();
    expect(screen.getByTestId("sp-scrim")).toBeInTheDocument();
  });

  it("касание затемнения и крестик закрывают шторку", () => {
    mount(at("result", "?sel=documents%3Ats"));
    fireEvent.click(screen.getByTestId("sp-scrim"));
    expect(location()).toBe(at("result"));
    expect(screen.queryByTestId("sp-scrim")).toBeNull();
    cleanup();
    mount(at("result", "?sel=documents%3Ats"));
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(location()).toBe(at("result"));
  });

  it("без выбора шторки и затемнения нет", () => {
    mount(at("result"));
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "false");
    expect(screen.queryByTestId("sp-scrim")).toBeNull();
  });

  it("страница «Изменений» не шторка: затемнения нет, нижние вкладки на месте", () => {
    mount(at("result", "?changes=1&sel=documents%3Ats"));
    expect(screen.queryByTestId("sp-scrim")).toBeNull();
    expect(screen.getByTestId("sp-phone-tabs")).toBeInTheDocument();
  });
});

describe("предпросмотр PDF из «Содержимого» на узком экране", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("без preview=1 колонка закрыта; preview=1 открывает её шторкой", () => {
    mount(at("content", "?doc=technical_specification"));
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "false");
    cleanup();
    mount(at("content", "?doc=technical_specification&preview=1"));
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "true");
    expect(screen.getByTestId("sp-side")).toHaveTextContent("preview");
    expect(screen.getByTestId("sp-scrim")).toBeInTheDocument();
  });

  it("закрытие шторки снимает preview, документ остаётся", () => {
    mount(at("content", "?doc=technical_specification&preview=1"));
    fireEvent.click(screen.getByTestId("sp-scrim"));
    expect(location()).toBe(at("content", "?doc=technical_specification"));
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "false");
  });

  it("Esc внутри шторки тоже закрывает её", () => {
    mount(at("content", "?doc=technical_specification&preview=1"));
    fireEvent.keyDown(screen.getByText("preview"), { key: "Escape" });
    expect(location()).toBe(at("content", "?doc=technical_specification"));
  });
});
