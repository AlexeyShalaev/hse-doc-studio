import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  configure,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { packOutcomeApi, type PackScenarioEntry } from "@entities/pack-studio";
import {
  COURSEWORK_MATRIX,
  COURSEWORK_SCENARIOS,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { SpaceScreen } from "../shell/SpaceScreen";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { seedCases, seedMap, seedVersion } from "./seeds";
import { slots } from "./slots";

// Возвращённые функции «Типовых случаев» и «Что на что влияет» (карта паритета 7.4): окно случая,
// «Принять текущий результат как ожидаемый», удаление с подтверждением, «Так увидит студент»,
// стрелки по таблице, выпущенная версия, «По результатам», порядок, фильтры, «сейчас на экране».

const DRAFT = `${SPACE_BASE}/2026.1.3/check`;
const RELEASED = `${SPACE_BASE}/2026.1.2/check`;
const [FIRST, SECOND] = COURSEWORK_SCENARIOS.scenarios;
const COMPANY = "Научрук из компании, есть консультант";
const UNIVERSITY = "Магистрант один, научрук из ВШЭ";

const open = (
  seed: (client: QueryClient) => void,
  url = `${DRAFT}?part=cases`,
) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  seed(client);
  return renderSpace(
    <QueryClientProvider client={client}>
      <SpaceScreen slots={slots} phone={false} />
    </QueryClientProvider>,
    url,
  );
};
const openCases = () =>
  open((client) => {
    seedCases(client, "ready");
  });

const saved = (entry: PackScenarioEntry): PackScenarioEntry => ({
  ...structuredClone(entry),
  etag: '"sha256-saved"',
});

const openRow = async (name: string) => {
  fireEvent.click(
    await screen.findByRole("button", { name: `Открыть случай: ${name}` }),
  );
  return within(await screen.findByTestId("case-dialog"));
};

describe("Типовые случаи: окно случая и действия", { timeout: 30_000 }, () => {
  beforeAll(async () => {
    configure({ asyncUtilTimeout: 8000 });
    await loadPackSpaceNamespace();
    await i18n.changeLanguage("ru");
    await Promise.all([import("./CheckMain"), import("./CheckNav")]);
  }, 60_000);
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    seedVersion();
  });

  it("«Открыть случай» из строки: окно с названием, итогом и ожиданиями словами", async () => {
    openCases();
    const dialog = await openRow(COMPANY);
    expect(screen.getByRole("heading", { name: COMPANY })).toBeInTheDocument();
    expect(
      dialog.getByText("Результат совпадает с ожидаемым"),
    ).toBeInTheDocument();
    const items = dialog.getAllByTestId("case-expect-item");
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      expect(item.textContent).not.toMatch(/[a-z]+_[a-z]+|утвержд|сценари/i);
    }
  });

  it("«Открыть случай» из клетки: выбрать клетку и открыть из карточки", async () => {
    openCases();
    const [cell] = await screen.findAllByRole("button", {
      name: new RegExp(`^${COMPANY}, Документы`),
    });
    fireEvent.click(cell!);
    fireEvent.click(await screen.findByTestId("case-open-detail"));
    const dialog = await screen.findByTestId("case-dialog");
    expect(within(dialog).getByText("Что получилось")).toBeInTheDocument();
  });

  it("случай не сошёлся: что не так словами, сырое сравнение в технических подробностях", async () => {
    openCases();
    const dialog = await openRow(UNIVERSITY);
    expect(
      dialog.getByText("Результат отличается от ожидаемого"),
    ).toBeInTheDocument();
    expect(dialog.getByTestId("case-diff")).toBeInTheDocument();
    expect(dialog.getAllByText(/^Ожидали: /).length).toBeGreaterThan(0);
    const diff = dialog.getByTestId("case-diff");
    const clone = diff.cloneNode(true) as HTMLElement;
    for (const details of clone.querySelectorAll("details")) details.remove();
    expect(clone.textContent).not.toMatch(/[a-z]+_[a-z]+|участник [a-z]/);
  });

  it("«Принять текущий результат как ожидаемый» пишет снимок в файл случая", async () => {
    const put = vi
      .spyOn(packOutcomeApi, "putScenario")
      .mockResolvedValue(saved(SECOND!));
    openCases();
    const dialog = await openRow(UNIVERSITY);
    fireEvent.click(
      dialog.getByRole("button", {
        name: "Принять текущий результат как ожидаемый",
      }),
    );
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const call = put.mock.calls[0];
    expect(call?.[3]).toBe(SECOND!.id);
    expect(call?.[4]).toMatchObject({ record_snapshot: "work_tree" });
    expect(call?.[5]).toBe(SECOND!.etag);
  });

  it("удаление просит подтверждение: «Не удалять» ничего не делает, «Да, удалить» удаляет", async () => {
    const del = vi.spyOn(packOutcomeApi, "deleteScenario").mockResolvedValue();
    openCases();
    const dialog = await openRow(COMPANY);
    fireEvent.click(dialog.getByRole("button", { name: "Удалить случай" }));
    const confirm = await screen.findByTestId("case-delete-confirm");
    expect(confirm).toHaveTextContent(`Удалить случай «${COMPANY}»?`);
    fireEvent.click(
      within(confirm).getByRole("button", { name: "Не удалять" }),
    );
    expect(del).not.toHaveBeenCalled();
    expect(screen.queryByTestId("case-delete-confirm")).toBeNull();
    fireEvent.click(dialog.getByRole("button", { name: "Удалить случай" }));
    fireEvent.click(
      within(await screen.findByTestId("case-delete-confirm")).getByRole(
        "button",
        { name: "Да, удалить" },
      ),
    );
    await waitFor(() => {
      expect(del).toHaveBeenCalledTimes(1);
    });
    expect(del.mock.calls[0]?.[3]).toBe(FIRST!.id);
    expect(del.mock.calls[0]?.[4]).toBe(FIRST!.etag);
    await waitFor(() => {
      expect(screen.queryByTestId("case-dialog")).toBeNull();
    });
  });

  it("редактор ожиданий: убрать, добавить из предложенного, сохранить", async () => {
    const put = vi
      .spyOn(packOutcomeApi, "putScenario")
      .mockResolvedValue(saved(FIRST!));
    openCases();
    const dialog = await openRow(COMPANY);
    const before = dialog.getAllByTestId("case-expect-item").length;
    fireEvent.click(dialog.getAllByRole("button", { name: /^Убрать: / })[0]!);
    expect(dialog.getAllByTestId("case-expect-item")).toHaveLength(before - 1);

    const select = dialog.getByLabelText("Добавить ожидание");
    const option = [...select.querySelectorAll("option")].find(
      (item) => item.value !== "",
    );
    expect(option).toBeDefined();
    fireEvent.change(select, { target: { value: option?.value ?? "" } });
    fireEvent.click(dialog.getByRole("button", { name: "Добавить" }));
    expect(dialog.getAllByTestId("case-expect-item")).toHaveLength(before);

    fireEvent.click(dialog.getByTestId("case-save"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const body = put.mock.calls[0]?.[4];
    expect(body?.scenario.assertions).toHaveLength(before);
    expect(put.mock.calls[0]?.[5]).toBe(FIRST!.etag);
  });

  it("«Убрать все» и «Добавить всё, что есть сейчас» работают без ввода текста", async () => {
    openCases();
    const dialog = await openRow(COMPANY);
    fireEvent.click(dialog.getByRole("button", { name: "Убрать все" }));
    expect(dialog.queryAllByTestId("case-expect-item")).toHaveLength(0);
    expect(dialog.getByTestId("case-expect-empty")).toBeInTheDocument();
    fireEvent.click(
      dialog.getByRole("button", { name: /^Добавить всё, что есть сейчас/ }),
    );
    expect(dialog.getAllByTestId("case-expect-item").length).toBeGreaterThan(3);
  });

  it("«Так увидит студент» открывает вид студента по словарю нового интерфейса", async () => {
    openCases();
    const dialog = await openRow(COMPANY);
    fireEvent.click(dialog.getByTestId("case-student-open"));
    const student = await screen.findByTestId("case-student");
    expect(
      screen.getByRole("heading", { name: "Так увидит студент" }),
    ).toBeInTheDocument();
    expect(student).toHaveTextContent("В комплекте 4 документа");
    expect(student).toHaveTextContent("Кто подписывает");
    expect(student.textContent).not.toMatch(
      /Студент получит|комбинаци|вводн|маршрут/i,
    );
  });

  it("«Так увидит студент» есть и в карточке клетки таблицы", async () => {
    openCases();
    const [cell] = await screen.findAllByRole("button", {
      name: new RegExp(`^${COMPANY}, Участники`),
    });
    fireEvent.click(cell!);
    fireEvent.click(await screen.findByTestId("case-student-detail"));
    expect(await screen.findByTestId("case-student")).toBeInTheDocument();
  });

  it("выпущенная версия: окно только для чтения, «Править копию» вместо правки", async () => {
    seedVersion("2026.1.2");
    open((client) => {
      seedCases(client, "ready");
    }, `${RELEASED}?part=cases`);
    const dialog = await openRow(COMPANY);
    expect(
      dialog.getByText(
        /Версия выпущена и не меняется: случай можно только смотреть/,
      ),
    ).toBeInTheDocument();
    expect(dialog.getByTestId("case-copy")).toBeInTheDocument();
    expect(dialog.queryByTestId("case-accept")).toBeNull();
    expect(dialog.queryByTestId("case-delete")).toBeNull();
    expect(dialog.queryByTestId("case-save")).toBeNull();
    expect(dialog.queryByRole("button", { name: /^Убрать: / })).toBeNull();
    // Так увидит студент остаётся доступным.
    expect(dialog.getByTestId("case-student-open")).toBeInTheDocument();
  });

  it("«Проверить заново» запрашивает таблицу ещё раз", async () => {
    const matrix = vi.spyOn(packOutcomeApi, "matrix").mockResolvedValue({
      data: COURSEWORK_MATRIX,
      etag: null,
    });
    openCases();
    const button = await screen.findByRole("button", {
      name: "Проверить заново",
    });
    fireEvent.click(button);
    await waitFor(() => {
      expect(matrix).toHaveBeenCalledTimes(1);
    });
  });

  describe("стрелки по таблице", () => {
    const cells = async () =>
      (await screen.findAllByRole("button")).filter((item) =>
        item.hasAttribute("data-r"),
      );

    it("в Tab-порядке одна клетка; стрелки, Home, End и Ctrl переходят между клетками", async () => {
      openCases();
      const all = await cells();
      expect(all.filter((item) => item.tabIndex === 0)).toHaveLength(1);
      const at = (r: number, c: number) =>
        all.find(
          (item) =>
            item.getAttribute("data-r") === String(r) &&
            item.getAttribute("data-c") === String(c),
        )!;
      const grid = screen.getByRole("grid");
      at(0, 0).focus();
      fireEvent.keyDown(at(0, 0), { key: "ArrowRight" });
      expect(document.activeElement).toBe(at(0, 1));
      fireEvent.keyDown(at(0, 1), { key: "ArrowDown" });
      expect(document.activeElement).toBe(at(1, 1));
      fireEvent.keyDown(at(1, 1), { key: "ArrowLeft" });
      expect(document.activeElement).toBe(at(1, 0));
      fireEvent.keyDown(at(1, 0), { key: "ArrowUp" });
      expect(document.activeElement).toBe(at(0, 0));
      fireEvent.keyDown(at(0, 0), { key: "ArrowUp" });
      expect(document.activeElement).toBe(at(0, 0));
      fireEvent.keyDown(at(0, 0), { key: "End" });
      const lastC = Math.max(...all.map((item) => Number(item.dataset.c)));
      expect(document.activeElement).toBe(at(0, lastC));
      fireEvent.keyDown(at(0, lastC), { key: "Home" });
      expect(document.activeElement).toBe(at(0, 0));
      const lastR = Math.max(...all.map((item) => Number(item.dataset.r)));
      fireEvent.keyDown(at(0, 0), { key: "End", ctrlKey: true });
      expect(document.activeElement).toBe(at(lastR, lastC));
      fireEvent.keyDown(at(lastR, lastC), { key: "Home", ctrlKey: true });
      expect(document.activeElement).toBe(at(0, 0));
      // Один Tab-остановочный элемент и после перехода.
      expect(all.filter((item) => item.tabIndex === 0)).toHaveLength(1);
      expect(grid).toHaveAttribute("aria-rowcount");
    });
  });
});

describe("Что на что влияет: вернувшиеся функции", { timeout: 30_000 }, () => {
  const MAP = `${DRAFT}?part=map`;
  const openMap = async () => {
    open((client) => {
      seedMap(client, "ready");
    }, MAP);
    fireEvent.click(
      await screen.findByRole("button", { name: "Показать все варианты" }),
    );
  };
  afterEach(cleanup);

  it("«Сейчас на экране»: вариант результата для условий экрана виден сразу", async () => {
    open((client) => {
      seedMap(client, "ready");
    }, MAP);
    const now = await screen.findByTestId("map-now");
    expect(now).toHaveTextContent("Сейчас на экране");
    expect(now).toHaveTextContent(/Вариант результата \d+/);
  });

  it("переключатель «По сочетаниям» и «По результатам»: варианты результата с числом сочетаний", async () => {
    await openMap();
    expect(screen.getByTestId("map-group-rows")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByTestId("map-group-outcomes"));
    const list = await screen.findByTestId("map-outcomes");
    const items = within(list).getAllByRole("listitem");
    expect(items.length).toBeGreaterThan(1);
    expect(items[0]).toHaveTextContent(/Вариант результата 1/);
    expect(items[0]).toHaveTextContent(/в \d+ сочетаниях условий/);
    expect(list.querySelector("[data-current]")).not.toBeNull();
  });

  it("«Показать эти сочетания» возвращает к строкам только этого варианта", async () => {
    await openMap();
    fireEvent.click(screen.getByTestId("map-group-outcomes"));
    const list = await screen.findByTestId("map-outcomes");
    fireEvent.click(
      within(list).getAllByRole("button", {
        name: "Показать эти сочетания",
      })[1]!,
    );
    expect(screen.getByTestId("map-outcome-filter")).toHaveTextContent(
      "Показаны сочетания только для варианта результата 2.",
    );
    expect(screen.getByTestId("map-group-rows")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Показать все" }));
    expect(screen.queryByTestId("map-outcome-filter")).toBeNull();
  });

  it("порядок «Сначала частые» ставит вариант с наибольшим числом сочетаний первым", async () => {
    await openMap();
    fireEvent.click(screen.getByTestId("map-group-outcomes"));
    const counts = () =>
      within(screen.getByTestId("map-outcomes"))
        .getAllByRole("listitem")
        .map((item) =>
          Number(/в (\d+) сочетаниях/.exec(item.textContent)?.[1]),
        );
    fireEvent.change(screen.getByTestId("map-sort"), {
      target: { value: "rows" },
    });
    const sorted = counts();
    expect(sorted).toEqual([...sorted].sort((a, b) => b - a));
    fireEvent.change(screen.getByTestId("map-sort"), {
      target: { value: "table" },
    });
    expect(counts()).toHaveLength(sorted.length);
  });

  it("поиск среди вариантов сужает список и возвращается к полному", async () => {
    await openMap();
    const status = () =>
      screen
        .getAllByRole("status")
        .map((item) => item.textContent ?? "")
        .find((text) => text.includes("Показано")) ?? "";
    const before = status();
    const search = screen.getByRole("searchbox");
    fireEvent.change(search, { target: { value: "zzz-такого-нет" } });
    expect(
      screen.getByText("Ничего не найдено. Очистите поиск."),
    ).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "" } });
    expect(status()).toBe(before);
  });

  it("фильтр по условию сужает список сочетаний и сбрасывается", async () => {
    await openMap();
    const status = () =>
      screen
        .getAllByRole("status")
        .map((item) => item.textContent ?? "")
        .find((text) => text.includes("Показано")) ?? "";
    const before = status();
    const filters = screen.getByTestId("map-filters");
    fireEvent.click(within(filters).getByText("Фильтры по условиям"));
    const select = filters.querySelector("select")!;
    const value = [...select.querySelectorAll("option")].find(
      (item) => item.value !== "",
    )?.value;
    fireEvent.change(select, { target: { value } });
    expect(status()).not.toBe(before);
    fireEvent.click(screen.getByRole("button", { name: "Сбросить фильтр" }));
    expect(status()).toBe(before);
  });
});
