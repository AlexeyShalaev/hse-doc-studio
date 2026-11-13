import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NextDeadline } from "@entities/session";
import { submissionApi } from "@entities/submission";
import { i18n } from "@shared/lib";
import {
  CheckpointDeadlineLine,
  type CheckpointDeadlineProfile,
} from "./CheckpointDeadlineLine";
import { NextDeadlineChip } from "./NextDeadlineChip";
import { RoutePointDeadline } from "./RoutePointDeadline";

// Сроки контрольных точек (signing-route.md, 16.2): строка на точке, пометка в списке и строка
// срока точки в редакторе маршрута.

const NOW = Date.parse("2026-11-12T10:00:00+03:00");
const PROJECT = "p_demo";
const HINT = {
  ru: "Обычно в середине ноября, точную дату объявляют в SmartLMS",
  en: "Usually mid-November; the exact date is announced in SmartLMS",
};

const profile = (
  overrides: Partial<CheckpointDeadlineProfile> = {},
): CheckpointDeadlineProfile => ({
  id: "topic-approval",
  deadline: null,
  deadline_state: "none",
  deadline_hint: HINT,
  packaged_at: null,
  ...overrides,
});

const wrap = (node: ReactNode) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { mutations: { retry: false } } })
      }
    >
      <I18nextProvider i18n={i18n}>{node}</I18nextProvider>
    </QueryClientProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("срок на точке", () => {
  it("без срока: мягкая строка с подсказкой пака и полем, время по умолчанию 23:59", () => {
    wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile()}
        canEdit
        now={NOW}
      />,
    );
    expect(screen.getByText("Срок сдачи не указан")).toBeInTheDocument();
    expect(screen.getByTestId("deadline-hint")).toHaveTextContent(HINT.ru);
    expect(screen.getByTestId("deadline-time")).toHaveValue("23:59");
    expect(screen.getByTestId("deadline-dismiss")).toHaveTextContent(
      "Не сейчас",
    );
  });

  it("«Указать срок» отправляет момент по Москве", async () => {
    const put = vi.spyOn(submissionApi, "setDeadline").mockResolvedValue({
      profile_id: "topic-approval",
      deadline: "2026-11-15T23:59:00+03:00",
      state: "soon",
      packaged_at: null,
    });
    const user = userEvent.setup();
    wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile()}
        canEdit
        now={NOW}
      />,
    );
    fireEvent.change(screen.getByTestId("deadline-date"), {
      target: { value: "2026-11-15" },
    });
    await user.click(screen.getByTestId("deadline-submit"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledWith(
        PROJECT,
        "topic-approval",
        "2026-11-15T23:59:00+03:00",
      );
    });
  });

  it("пустая дата не уходит на сервер", async () => {
    const put = vi.spyOn(submissionApi, "setDeadline");
    const user = userEvent.setup();
    wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile()}
        canEdit
        now={NOW}
      />,
    );
    await user.click(screen.getByTestId("deadline-submit"));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Укажите дату и время срока",
    );
    expect(put).not.toHaveBeenCalled();
  });

  it("«Не сейчас» прячет строку для точки в этом браузере, «Указать срок» остаётся", async () => {
    const user = userEvent.setup();
    wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile()}
        canEdit
        now={NOW}
      />,
    );
    await user.click(screen.getByTestId("deadline-dismiss"));
    expect(screen.queryByText("Срок сдачи не указан")).toBeNull();
    expect(screen.getByTestId("deadline-open")).toHaveTextContent(
      "Указать срок",
    );
    cleanup();
    wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile()}
        canEdit
        now={NOW}
      />,
    );
    expect(screen.getByTestId("deadline-open")).toBeInTheDocument();
    await user.click(screen.getByTestId("deadline-open"));
    expect(screen.getByTestId("deadline-form")).toBeInTheDocument();
  });

  it("читатель без срока ничего не видит", () => {
    const { container } = wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile()}
        canEdit={false}
        now={NOW}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    ["upcoming", "2026-11-20T23:59:00+03:00", null, "Срок: 20.11, 23:59"],
    [
      "soon",
      "2026-11-15T23:59:00+03:00",
      null,
      "Срок: 15.11, 23:59 (через 3 дня)",
    ],
    ["today", "2026-11-12T18:00:00+03:00", null, "Сегодня до 18:00"],
    [
      "packaged",
      "2026-11-11T23:59:00+03:00",
      "2026-11-10T18:05:00+03:00",
      "Срок прошёл 11.11: пакет собран 10.11",
    ],
    [
      "overdue",
      "2026-11-11T23:59:00+03:00",
      null,
      "Просрочено: пакет не собран",
    ],
  ] as const)("состояние %s", (state, deadline, packaged, text) => {
    wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile({
          deadline,
          deadline_state: state,
          packaged_at: packaged,
        })}
        canEdit={false}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("deadline-state")).toHaveTextContent(text);
    expect(screen.queryByTestId("deadline-edit")).toBeNull();
  });

  it("«Убрать срок» снимает срок, карандаш открывает поле со сроком", async () => {
    const put = vi.spyOn(submissionApi, "setDeadline").mockResolvedValue({
      profile_id: "topic-approval",
      deadline: null,
      state: "none",
      packaged_at: null,
    });
    const user = userEvent.setup();
    wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile({
          deadline: "2026-11-15T20:00:00+03:00",
          deadline_state: "soon",
        })}
        canEdit
        now={NOW}
      />,
    );
    await user.click(screen.getByTestId("deadline-edit"));
    expect(screen.getByTestId("deadline-date")).toHaveValue("2026-11-15");
    expect(screen.getByTestId("deadline-time")).toHaveValue("20:00");
    await user.click(screen.getByTestId("deadline-dismiss"));
    await user.click(screen.getByTestId("deadline-clear"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledWith(PROJECT, "topic-approval", null);
    });
  });

  it("английский текст", async () => {
    await i18n.changeLanguage("en");
    wrap(
      <CheckpointDeadlineLine
        projectId={PROJECT}
        profile={profile({
          deadline: "2026-11-15T23:59:00+03:00",
          deadline_state: "soon",
        })}
        canEdit={false}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("deadline-state")).toHaveTextContent(
      "Due: 15.11, 23:59 (in 3 days)",
    );
  });
});

describe("пометка в списке проектов", () => {
  const next = (
    state: NextDeadline["state"],
    deadline: string,
  ): NextDeadline => ({
    profile_id: "topic-approval",
    name: { ru: "Заявка на тему", en: "Topic application" },
    deadline,
    state,
  });

  it.each([
    ["soon", "2026-11-15T23:59:00+03:00", "Заявка на тему: через 3 дня"],
    ["upcoming", "2026-11-23T23:59:00+03:00", "Заявка на тему: через 11 дней"],
    ["today", "2026-11-12T23:59:00+03:00", "Заявка на тему: сегодня"],
    ["overdue", "2026-11-10T23:59:00+03:00", "Заявка на тему: просрочено"],
  ] as const)("%s", (state, deadline, text) => {
    wrap(
      <NextDeadlineChip
        next={next(state, deadline)}
        projectId={PROJECT}
        now={NOW}
      />,
    );
    expect(screen.getByTestId(`project-deadline-${PROJECT}`)).toHaveTextContent(
      text,
    );
  });

  it("собранный к сроку и пустой срок пометки не дают", () => {
    const { container } = wrap(
      <>
        <NextDeadlineChip
          next={next("packaged", "2026-11-10T23:59:00+03:00")}
          projectId={PROJECT}
          now={NOW}
          containerStyle={{ margin: 0 }}
        />
        <NextDeadlineChip next={null} projectId={PROJECT} now={NOW} />
      </>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("срок точки в редакторе маршрута", () => {
  const POINT = "2026-11-15T23:59:00+03:00";
  const ROUTE = "2026-11-14T23:59:00+03:00";
  const withPoint = profile({ deadline: POINT, deadline_state: "soon" });

  it("срок маршрута из срока точки: откуда он взят", () => {
    wrap(
      <RoutePointDeadline
        projectId={PROJECT}
        profile={withPoint}
        routeDeadline={ROUTE}
        pointDeadlineAtDraft={POINT}
        canEdit
        onApply={vi.fn()}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("route-point-deadline")).toHaveTextContent(
      "Срок маршрута: 14.11, 23:59. На день раньше срока точки (15.11), чтобы осталось время собрать пакет",
    );
    expect(screen.queryByTestId("route-point-apply")).toBeNull();
  });

  it("срока маршрута нет: «Поставить» на день раньше", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    wrap(
      <RoutePointDeadline
        projectId={PROJECT}
        profile={withPoint}
        routeDeadline={null}
        pointDeadlineAtDraft={undefined}
        canEdit
        onApply={onApply}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("route-point-offer")).toHaveTextContent(
      "Срок точки: 15.11. Поставить срок маршрута 14.11?",
    );
    await user.click(screen.getByTestId("route-point-apply"));
    expect(onApply).toHaveBeenCalledWith(ROUTE);
  });

  it("срок точки изменился после черновика", () => {
    wrap(
      <RoutePointDeadline
        projectId={PROJECT}
        profile={profile({
          deadline: "2026-11-20T23:59:00+03:00",
          deadline_state: "upcoming",
        })}
        routeDeadline={ROUTE}
        pointDeadlineAtDraft={POINT}
        canEdit
        onApply={vi.fn()}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("route-point-offer")).toHaveTextContent(
      "Срок точки изменился: 20.11. Поставить срок маршрута 19.11?",
    );
  });

  it("срок маршрута позже срока сдачи: предупреждение", () => {
    wrap(
      <RoutePointDeadline
        projectId={PROJECT}
        profile={withPoint}
        routeDeadline="2026-11-17T23:59:00+03:00"
        pointDeadlineAtDraft={undefined}
        canEdit
        onApply={vi.fn()}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("route-point-later")).toHaveTextContent(
      "Срок маршрута позже срока сдачи",
    );
  });

  it("до срока точки меньше двух суток: срок маршрута равен ему", () => {
    const point = "2026-11-13T18:00:00+03:00";
    wrap(
      <RoutePointDeadline
        projectId={PROJECT}
        profile={profile({ deadline: point, deadline_state: "soon" })}
        routeDeadline={point}
        pointDeadlineAtDraft={point}
        canEdit
        onApply={vi.fn()}
        now={NOW}
      />,
    );
    expect(screen.getByTestId("route-point-deadline")).toHaveTextContent(
      "Срок маршрута равен сроку точки (13.11, 18:00): до него меньше двух суток",
    );
  });

  it("срока точки нет: та же мягкая строка, что на точке", () => {
    wrap(
      <RoutePointDeadline
        projectId={PROJECT}
        profile={profile()}
        routeDeadline={null}
        pointDeadlineAtDraft={null}
        canEdit
        onApply={vi.fn()}
        now={NOW}
      />,
    );
    expect(screen.getByText("Срок сдачи не указан")).toBeInTheDocument();
    expect(screen.getByTestId("deadline-submit")).toHaveTextContent(
      "Указать срок",
    );
  });
});
