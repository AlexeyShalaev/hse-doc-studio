import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { COURSEWORK_COMPARE } from "@entities/pack-studio/reference";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { DeltaStrip } from "./DeltaStrip";
import { HIGHLIGHT_MS, deltaStore } from "./deltaStore";
import { SituationBar } from "./SituationBar";
import { seededClient, WithClient } from "./testKit";
import { useSituationDelta } from "./useSituationDelta";

const URL = `${SPACE_BASE}/2026.1.3/result?i.supervisor=company`;
const SCOPE = "gallery-ws/hse-cs-sse/coursework/2026.1.3";
const location = () => screen.getByTestId("location").textContent;
const COMPARE = {
  left: { state: "work_tree" as const, inputs: {} },
  right: {
    state: "work_tree" as const,
    inputs: { supervisor: "company" },
  },
};
const record = () => {
  deltaStore.record({
    scope: SCOPE,
    before: { inputs: {}, caseId: null },
    after: { inputs: { supervisor: "company" }, caseId: null },
    label: "Научный руководитель: Из компании",
  });
};
const show = (url = URL, client = seededClient({ compare: COMPARE })) =>
  renderSpace(
    <WithClient client={client}>
      <DeltaStrip />
    </WithClient>,
    url,
  );

describe("DeltaStrip", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    deltaStore.reset();
  });
  afterEach(cleanup);

  it("без изменения условий плашки нет", () => {
    show();
    expect(screen.queryByTestId("sp-delta")).not.toBeInTheDocument();
  });

  it("после смены условия: строки частей центра, а не элементы сервера", () => {
    record();
    show();
    const strip = screen.getByTestId("sp-delta");
    expect(strip).toHaveTextContent(
      "После «Научный руководитель: Из компании» результат изменился:",
    );
    expect(strip).toHaveTextContent("Участники: добавлено 1.");
    // Сервер: шаги и пары одной точки (+3, ~1, −2); на экране это одна строка подписей точки.
    expect(strip).toHaveTextContent("Подписи: изменено 1.");
    expect(strip).not.toHaveTextContent("Проверки");
  });

  it("«Показать только изменившееся» пишет delta=1 в адрес, кнопка меняется", () => {
    record();
    show();
    fireEvent.click(screen.getByTestId("sp-delta-only"));
    expect(location()).toContain("delta=1");
    expect(screen.getByTestId("sp-delta-only")).toHaveTextContent(
      "Показать всё",
    );
    fireEvent.click(screen.getByTestId("sp-delta-only"));
    expect(location()).not.toContain("delta=");
  });

  it("«Скрыть» убирает плашку и фильтр", () => {
    record();
    show(`${URL}&delta=1`);
    fireEvent.click(screen.getByTestId("sp-delta-hide"));
    expect(screen.queryByTestId("sp-delta")).not.toBeInTheDocument();
    expect(location()).not.toContain("delta=");
  });

  it("адрес ушёл от записи (Назад): плашка не показывает чужую разницу", () => {
    record();
    show(`${SPACE_BASE}/2026.1.3/result?i.supervisor=none`);
    expect(screen.queryByTestId("sp-delta")).not.toBeInTheDocument();
  });

  it("запись другой версии не показывается", () => {
    record();
    show(`${SPACE_BASE}/2026.1.2/result?i.supervisor=company`);
    expect(screen.queryByTestId("sp-delta")).not.toBeInTheDocument();
  });

  it("результат не изменился: об этом одна строка без «Показать только»", () => {
    record();
    show(
      URL,
      seededClient({
        compare: COMPARE,
        data: {
          ...COURSEWORK_COMPARE,
          identical: true,
          summary: [],
          changes: [],
        },
      }),
    );
    expect(screen.getByTestId("sp-delta")).toHaveTextContent(
      "результат не изменился.",
    );
    expect(screen.queryByTestId("sp-delta-only")).not.toBeInTheDocument();
  });
});

describe("useSituationDelta", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    deltaStore.reset();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  const Probe = () => {
    const delta = useSituationDelta();
    return (
      <output data-testid="probe">
        {JSON.stringify({
          active: delta.active,
          highlight: delta.highlight,
          only: delta.onlyChanged,
          changed: [...delta.changed.keys()].slice(0, 2),
        })}
      </output>
    );
  };
  const probe = () =>
    JSON.parse(screen.getByTestId("probe").textContent) as Record<
      string,
      unknown
    >;

  it("изменившиеся элементы подсвечены несколько секунд, фильтр из адреса", () => {
    record();
    renderSpace(
      <WithClient client={seededClient({ compare: COMPARE })}>
        <Probe />
      </WithClient>,
      `${URL}&delta=1`,
    );
    expect(probe()).toEqual({
      active: true,
      highlight: true,
      only: true,
      changed: ["participants:co_supervisor", "route:topic-approval/step/2"],
    });
    act(() => {
      vi.advanceTimersByTime(HIGHLIGHT_MS + 10);
    });
    expect(probe().highlight).toBe(false);
    expect(probe().active).toBe(true);
  });

  it("без записи ничего не подсвечено", () => {
    renderSpace(
      <WithClient client={seededClient()}>
        <Probe />
      </WithClient>,
      `${URL}&delta=1`,
    );
    expect(probe()).toEqual({
      active: false,
      highlight: false,
      only: false,
      changed: [],
    });
  });
});

describe("плашка вместе с полосой", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    deltaStore.reset();
  });
  afterEach(cleanup);

  it("смена условия на полосе запоминает прежнее состояние и просит сравнение", () => {
    const client = seededClient({ compare: COMPARE });
    renderSpace(
      <WithClient client={client}>
        <SituationBar />
        <DeltaStrip />
      </WithClient>,
      `${SPACE_BASE}/2026.1.3/result`,
    );
    expect(screen.queryByTestId("sp-delta")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("sp-sit-more-btn"));
    fireEvent.click(screen.getByTestId("sp-sit-value-supervisor-company"));
    expect(location()).toContain("i.supervisor=company");
    expect(screen.getByTestId("sp-delta")).toHaveTextContent(
      "После «Научный руководитель: Из компании»",
    );
    expect(deltaStore.get()?.before).toEqual({ inputs: {}, caseId: null });
  });
});
