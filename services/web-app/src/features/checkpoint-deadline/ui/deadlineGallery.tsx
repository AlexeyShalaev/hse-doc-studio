import type { GalleryGroup } from "@shared/lib/stateGallery";
import {
  CheckpointDeadlineLine,
  type CheckpointDeadlineProfile,
} from "./CheckpointDeadlineLine";
import { NextDeadlineChip } from "./NextDeadlineChip";
import { RoutePointDeadline } from "./RoutePointDeadline";

// Галерея сроков контрольных точек (docs/design/signing-route.md, 16.2): строка на точке во всех
// состояниях, пометка в списке и строка срока точки в редакторе маршрута. «Сейчас» зафиксировано,
// чтобы «через 3 дня» не плыло. «Не сейчас» в галерее запоминается в браузере, как в приложении.

const NOW = Date.parse("2026-11-12T10:00:00+03:00");
const POINT = "2026-11-15T23:59:00+03:00";
const PROJECT = "p_gallery_deadline";
const HINT = {
  ru: "Обычно в середине ноября, точную дату объявляют в SmartLMS",
  en: "Usually mid-November; the exact date is announced in SmartLMS",
};

const profile = (
  id: string,
  overrides: Partial<CheckpointDeadlineProfile> = {},
): CheckpointDeadlineProfile => ({
  id,
  deadline: null,
  deadline_state: "none",
  deadline_hint: HINT,
  packaged_at: null,
  ...overrides,
});

const noop = () => undefined;

const line = (
  id: string,
  title: string,
  note: string,
  point: CheckpointDeadlineProfile,
  canEdit = true,
) => ({
  id,
  title,
  note,
  frame: "plain" as const,
  width: 560,
  render: () => (
    <CheckpointDeadlineLine
      projectId={PROJECT}
      profile={point}
      canEdit={canEdit}
      now={NOW}
    />
  ),
});

const route = (
  id: string,
  title: string,
  note: string,
  props: {
    point: CheckpointDeadlineProfile;
    routeDeadline: string | null;
    atDraft: string | null;
  },
) => ({
  id,
  title,
  note,
  frame: "plain" as const,
  width: 380,
  render: () => (
    <RoutePointDeadline
      projectId={PROJECT}
      profile={props.point}
      routeDeadline={props.routeDeadline}
      pointDeadlineAtDraft={props.atDraft}
      canEdit
      onApply={noop}
      now={NOW}
    />
  ),
});

const chip = (
  id: string,
  title: string,
  state: "upcoming" | "soon" | "today" | "overdue",
  deadline: string,
) => ({
  id,
  title,
  frame: "plain" as const,
  width: 320,
  render: () => (
    <NextDeadlineChip
      projectId={id}
      now={NOW}
      next={{
        profile_id: "topic-approval",
        name: { ru: "Заявка на тему", en: "Topic application" },
        deadline,
        state,
      }}
    />
  ),
});

export const getCheckpointDeadlineGallery = (): GalleryGroup[] => [
  {
    id: "deadline-point",
    title: "Срок на точке сдачи",
    description:
      "Под названием точки. Сейчас 12.11, 10:00 по Москве; срок вводится и показывается по Москве.",
    entries: [
      line(
        "deadline_none",
        "Срок не указан",
        "Подсказка пака серым, дата и время (23:59 по умолчанию), «Указать срок» и «Не сейчас». На телефоне поля в столбик.",
        profile("gallery-none"),
      ),
      line(
        "deadline_none_no_hint",
        "Срок не указан, у пака нет подсказки",
        "Строка без серого текста (hse-cs-se до своей версии с подсказками).",
        profile("gallery-none-nohint", { deadline_hint: null }),
      ),
      line(
        "deadline_upcoming",
        "Срок впереди",
        "Больше трёх дней: только дата и время.",
        profile("gallery-upcoming", {
          deadline: "2026-11-20T23:59:00+03:00",
          deadline_state: "upcoming",
        }),
      ),
      line(
        "deadline_soon",
        "Срок скоро",
        "1–3 дня: «через N дней», цвет предупреждения.",
        profile("gallery-soon", { deadline: POINT, deadline_state: "soon" }),
      ),
      line(
        "deadline_today",
        "Срок сегодня",
        "«Сегодня до 23:59».",
        profile("gallery-today", {
          deadline: "2026-11-12T23:59:00+03:00",
          deadline_state: "today",
        }),
      ),
      line(
        "deadline_packaged",
        "Срок прошёл, пакет собран",
        "Пакет точки собран к сроку.",
        profile("gallery-packaged", {
          deadline: "2026-11-11T23:59:00+03:00",
          deadline_state: "packaged",
          packaged_at: "2026-11-10T18:05:00+03:00",
        }),
      ),
      line(
        "deadline_overdue",
        "Просрочено",
        "Срок прошёл, а пакета к сроку нет. Сдачу в ЛМС Студия не видит.",
        profile("gallery-overdue", {
          deadline: "2026-11-11T23:59:00+03:00",
          deadline_state: "overdue",
        }),
      ),
      line(
        "deadline_reader",
        "Читатель",
        "Срок виден, карандаша и «Убрать срок» нет.",
        profile("gallery-reader", { deadline: POINT, deadline_state: "soon" }),
        false,
      ),
    ],
  },
  {
    id: "deadline-list",
    title: "Пометка в списке проектов",
    description:
      "Ближайший срок проекта: у своих проектов и у проектов студентов, где человек руководитель.",
    entries: [
      chip(
        "chip_upcoming",
        "Через 11 дней",
        "upcoming",
        "2026-11-23T23:59:00+03:00",
      ),
      chip("chip_soon", "Через 3 дня", "soon", POINT),
      chip("chip_today", "Сегодня", "today", "2026-11-12T23:59:00+03:00"),
      chip(
        "chip_overdue",
        "Просрочено",
        "overdue",
        "2026-11-10T23:59:00+03:00",
      ),
    ],
  },
  {
    id: "deadline-route",
    title: "Срок точки в «Отправить на подписание»",
    description:
      "Под полем срока маршрута. Срок черновика из срока точки ставит сервер (R29); редактор показывает, откуда он.",
    entries: [
      route(
        "route_derived",
        "Срок маршрута из срока точки",
        "На день раньше срока точки.",
        {
          point: profile("route-derived", {
            deadline: POINT,
            deadline_state: "soon",
          }),
          routeDeadline: "2026-11-14T23:59:00+03:00",
          atDraft: POINT,
        },
      ),
      route(
        "route_suggest",
        "Срока маршрута нет",
        "Черновик создан до срока точки или до R29: «Поставить».",
        {
          point: profile("route-suggest", {
            deadline: POINT,
            deadline_state: "soon",
          }),
          routeDeadline: null,
          atDraft: null,
        },
      ),
      route(
        "route_changed",
        "Срок точки изменился",
        "После черновика срок точки перенесли на 20.11.",
        {
          point: profile("route-changed", {
            deadline: "2026-11-20T23:59:00+03:00",
            deadline_state: "upcoming",
          }),
          routeDeadline: "2026-11-14T23:59:00+03:00",
          atDraft: POINT,
        },
      ),
      route(
        "route_later",
        "Срок маршрута позже срока сдачи",
        "Допустимо, но редактор предупреждает.",
        {
          point: profile("route-later", {
            deadline: POINT,
            deadline_state: "soon",
          }),
          routeDeadline: "2026-11-17T23:59:00+03:00",
          atDraft: null,
        },
      ),
      route(
        "route_no_point",
        "Срока точки нет",
        "Та же мягкая строка, что на точке.",
        {
          point: profile("route-none"),
          routeDeadline: null,
          atDraft: null,
        },
      ),
    ],
  },
];
