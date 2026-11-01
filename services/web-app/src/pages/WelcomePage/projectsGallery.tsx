import type { z } from "zod";
import { CloneWizard } from "@features/git-remote";
import { ProjectCreateWizard } from "@features/project-create";
import type { ProjectResponseSchema } from "@entities/project";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import { EmptyState } from "./EmptyState";
import { LoadError } from "./LoadError";
import { ProjectCard } from "./ProjectCard";
import { WelcomePage } from "./WelcomePage";

type Item = z.infer<typeof ProjectResponseSchema>;

const noop = () => undefined;

const item = (overrides: Partial<Item>): Item => ({
  id: "p_gallery",
  name: "Bertie: курсовой проект",
  folder: "",
  lock: { pack_id: "", template_id: "", version: "", engine: "xelatex" },
  kind: "project",
  staffing: "team",
  lang: "ru",
  updated_at: "2026-10-26T18:20:00Z",
  pinned: false,
  archived: false,
  shared_enabled: true,
  ...overrides,
});

const card = (id: string, title: string, note: string, project: Item) => ({
  id,
  title,
  note,
  frame: "plain" as const,
  width: 420,
  render: () => (
    <ProjectCard
      project={project}
      onOpen={noop}
      onTogglePin={noop}
      onToggleArchive={noop}
    />
  ),
});

const ANNA = {
  kind: "user" as const,
  id: "u_anna",
  name: "Анна Петрова",
  slug: null,
};
const ORG = {
  kind: "org" as const,
  id: "org_msp",
  name: "МСПИН 2025",
  slug: "msp-2025",
};

/** Проекты без папок и состояния доступа для галереи серверных экранов. */
export const getProjectsGallery = (): GalleryGroup[] => [
  {
    id: "project-cards",
    title: "Карточки проектов",
    description: "Папки нет: вместо неё владелец и роль человека.",
    entries: [
      card(
        "card_own",
        "Личный проект",
        "Роль владельца не показывается: это и так очевидно.",
        item({ owner: ANNA, my_role: "owner", pinned: true }),
      ),
      card(
        "card_org_reviewer",
        "Проект организации, рецензент",
        "Значок организации и роль в подвале карточки.",
        item({
          name: "Industry adoption of CI",
          kind: "research",
          lang: "en",
          owner: ORG,
          my_role: "reviewer",
        }),
      ),
      card(
        "card_shared_reader",
        "Чужой проект, читатель",
        "Владелец назван по имени.",
        item({
          name: "Анализ нагрузки на очередь задач",
          staffing: "solo",
          owner: { ...ANNA, id: "u_pavel", name: "Павел Орлов" },
          my_role: "reader",
        }),
      ),
      card(
        "card_archived",
        "Архивный проект",
        "Приглушён, как в локальном режиме.",
        item({
          name: "Практика 2025: отчёт",
          staffing: "solo",
          archived: true,
          owner: ANNA,
          my_role: "owner",
        }),
      ),
    ],
  },
  {
    id: "project-list-states",
    title: "Список: пустые и ошибочные состояния",
    entries: [
      {
        id: "list_empty_server",
        title: "Проектов пока нет",
        note: "Без «Подключить папку»: можно создать проект или ждать приглашения.",
        frame: "window" as const,
        width: 720,
        render: () => (
          <EmptyState variant="server" onCreate={noop} onClone={noop} />
        ),
      },
      {
        id: "list_empty_scope",
        title: "Пусто в выбранном разделе",
        note: "Выбрано «Организации», а проектов организаций нет.",
        frame: "window" as const,
        width: 720,
        render: () => (
          <EmptyState
            variant="server"
            scopeFiltered
            onResetScope={noop}
            onCreate={noop}
          />
        ),
      },
      {
        id: "list_load_error",
        title: "Список не загрузился",
        frame: "window" as const,
        width: 720,
        render: () => <LoadError onRetry={noop} />,
      },
      {
        id: "list_load_error_retrying",
        title: "Повторная загрузка",
        frame: "window" as const,
        width: 720,
        render: () => <LoadError onRetry={noop} retrying />,
      },
    ],
  },
  {
    id: "project-live",
    title: "Живые экраны на демо-сервере",
    description:
      "Работают на данных вкладки. Чужой проект открывается по адресу /projects/p_01hxa9foreign.",
    entries: [
      {
        id: "live_welcome_student",
        title: "Список: студент с организацией",
        note: "Три проекта и архив, фильтр «Мои / Организации», закрепление и архив (архив только у владельца: иначе тост с ролью).",
        frame: "screen" as const,
        scenario: "student_ready",
        render: () => <WelcomePage />,
      },
      {
        id: "live_welcome_newcomer",
        title: "Список: новичок",
        note: "Пустое состояние сервера.",
        frame: "screen" as const,
        scenario: "newcomer",
        render: () => <WelcomePage />,
      },
      {
        id: "live_create_wizard",
        title: "Создание проекта без папки",
        note: "Шаг «Название» с выбором владельца вместо шага «Папка». У студента владельцем может быть только он сам: организацию можно выбрать у администратора.",
        frame: "screen" as const,
        scenario: "admin_ready",
        render: () => <ProjectCreateWizard />,
      },
      {
        id: "live_clone_wizard",
        title: "Клонирование без папки",
        note: "Шаг «Название» вместо шага «Папка».",
        frame: "screen" as const,
        scenario: "student_ready",
        render: () => (
          <CloneWizard folderless onExit={noop} onOpenProject={noop} />
        ),
      },
    ],
  },
];
