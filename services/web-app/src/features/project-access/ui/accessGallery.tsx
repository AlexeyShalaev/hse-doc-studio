import type {
  ProjectAccessCandidate,
  ProjectAccessEntry,
} from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { AccessView } from "./AccessView";

const W = 620;
const noop = () => undefined;

const ENTRIES: ProjectAccessEntry[] = [
  {
    subject_kind: "user",
    subject_id: "u_01hx7k2m9c",
    name: "Анна Петрова",
    detail: "anna.petrova@example.org",
    role: "owner",
    locked: true,
  },
  {
    subject_kind: "group",
    subject_id: "g_01hx7m4c2d",
    name: "Команда Bertie",
    detail: "МСПИН 2025",
    role: "editor",
    locked: false,
  },
  {
    subject_kind: "user",
    subject_id: "u_01hx7k1a0b",
    name: "Иван Сидоров",
    detail: "ivan.sidorov@example.org",
    role: "reviewer",
    locked: false,
  },
];

const ORG_ROW: ProjectAccessEntry = {
  subject_kind: "org",
  subject_id: "org_01hx5a",
  name: "МСПИН 2025",
  detail: null,
  role: "reader",
  locked: true,
};

const CANDIDATES: ProjectAccessCandidate[] = [
  {
    subject_kind: "group",
    subject_id: "g_01hx7m5d3e",
    name: "Наставники",
    detail: "МСПИН 2025",
  },
  {
    subject_kind: "user",
    subject_id: "u_01hx7k3e5f",
    name: "Елена Миронова",
    detail: "elena.mironova@example.org",
  },
];

const entry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({ id, title, frame: "window", width: W, render, ...extra });

const view = (extra: Partial<Parameters<typeof AccessView>[0]> = {}) => (
  <AccessView
    status="ready"
    entries={ENTRIES}
    myRole="owner"
    query=""
    onQuery={noop}
    onAdd={noop}
    onChangeRole={noop}
    onRemove={noop}
    {...extra}
  />
);

/** Панель «Доступ» проекта: состояния. */
export const getProjectAccessGallery = (): GalleryGroup[] => [
  {
    id: "project-access",
    title: "Проект: доступ",
    entries: [
      entry("access_owner", "Владелец: список и добавление", () => view()),
      entry("access_search", "Поиск, найдены группа и человек", () =>
        view({ query: "на", candidates: CANDIDATES }),
      ),
      entry("access_none", "Поиск ничего не нашёл", () =>
        view({ query: "zzz" }),
      ),
      entry("access_searching", "Идёт поиск", () =>
        view({ query: "ел", candidatesLoading: true }),
      ),
      entry("access_org", "Проект организации", () =>
        view({ entries: [ORG_ROW, ...ENTRIES.slice(1)] }),
      ),
      entry("access_editor", "Редактор: только чтение", () =>
        view({ myRole: "editor", selfId: "u_01hx7k1a0b" }),
      ),
      entry("access_busy", "Идёт смена роли", () =>
        view({ busyKey: "group:g_01hx7m4c2d" }),
      ),
      entry("access_failed", "Сервер отказал", () =>
        view({ failure: { code: "member_not_found" } }),
      ),
      entry("access_loading", "Загрузка", () =>
        view({ status: "loading", entries: [] }),
      ),
      entry("access_error", "Не загрузился", () =>
        view({ status: "error", entries: [], onRetry: noop }),
      ),
    ],
  },
];
