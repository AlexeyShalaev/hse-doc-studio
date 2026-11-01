import {
  AlertTriangle,
  ArrowLeftRight,
  Cpu,
  CloudUpload,
  Download,
  Files,
  FolderSync,
  GitBranch,
  FileType,
  GraduationCap,
  Info,
  ListChecks,
  Lock,
  Package,
  RefreshCw,
  ShieldCheck,
  Tag,
  Timer,
  Type,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

// Секции настроек проекта. Форма реестра повторяет SECTIONS из SettingsPage
// (id + labelKey + icon), чтобы приложение говорило на одном языке: там ими
// рулится /settings/:section, здесь — будущий /project-settings/:section.
export type ProjectSettingsSectionId =
  | "general"
  | "template"
  | "confidentiality"
  | "builds"
  | "doc-set"
  | "doc-formats"
  | "shared-docs"
  | "authors"
  | "access"
  | "meta"
  | "fonts"
  | "supervisor"
  | "checks"
  | "sync-remote"
  | "sync-options"
  | "sync-shared-folder"
  | "sync-exchange"
  | "sync-ci"
  | "sync-server-clone"
  | "danger-zone";

// Всё, от чего зависит показ условных секций. Вычисляется владельцем черновика
// (ProjectSettingsView) из тех же хелперов sectionData, что рисуют содержимое —
// так навигация и сами карточки не могут разойтись.
export type ProjectSettingsSectionContext = {
  // Командный проект (project.staffing === "team").
  isTeam: boolean;
  // Есть хотя бы один документ, у которого ≥2 вариантов, доступных в языке
  // проекта (collectVariantRows(...).length > 0).
  hasDocFormats: boolean;
  // Пак увёл на страницу «Документы» хотя бы одну непустую группу мета-полей
  // (buildMetaGroupCards(..., "documents").length > 0).
  hasDocSetMeta: boolean;
  // Пак объявил хотя бы одно редактируемое meta-поле для этого вида работы,
  // оставшееся за «Метаданными» (уведённые в другие секции не считаются).
  hasMetaFields: boolean;
  // Бэкенд умеет синхронизацию с репозиторием. Пока состояние не загружено,
  // считается, что умеет: иначе ссылка на «Синхронизацию» сначала открывала бы
  // другую группу и только потом переключалась.
  syncSupported: boolean;
  // К проекту подключён репозиторий: без него настраивать нечего.
  syncConnected: boolean;
  // Папка проекта лежит в облачном диске (бэкенд определил это сам).
  hasSharedFolder: boolean;
  // Серверный проект: у него есть роль смотрящего и панель «Доступ».
  hasAccess?: boolean;
  // Сервер отдаёт проекты по git (capabilities.git_remote) и это серверный проект.
  hasGitRemote?: boolean;
};

export type ProjectSettingsSectionDef = {
  id: ProjectSettingsSectionId;
  // Ключ i18n в пространстве имён `workspace`.
  labelKey: string;
  icon: LucideIcon;
  // Отсутствует — секция есть всегда.
  isAvailable?: (ctx: ProjectSettingsSectionContext) => boolean;
};

export const PROJECT_SETTINGS_SECTIONS: readonly ProjectSettingsSectionDef[] = [
  {
    id: "general",
    labelKey: "projectSettings.sectionGeneral",
    icon: Info,
  },
  {
    id: "template",
    labelKey: "projectSettings.sectionTemplate",
    icon: RefreshCw,
  },
  {
    id: "confidentiality",
    labelKey: "projectSettings.sectionConfidentiality",
    icon: Lock,
  },
  // Где идут сборки серверного проекта: личные раннеры владельца или общие.
  // Видна всем участникам, править может только владелец.
  {
    id: "builds",
    labelKey: "projectSettings.sectionBuilds",
    icon: Cpu,
    isAvailable: (ctx) => ctx.hasAccess === true,
  },
  // Состав комплекта идёт ПЕРЕД форматами: сначала решают, какие документы
  // вообще входят в комплект, и только потом — в каком виде их собирать.
  {
    id: "doc-set",
    labelKey: "projectSettings.sectionDocSet",
    icon: Package,
    isAvailable: (ctx) => ctx.hasDocSetMeta,
  },
  {
    id: "doc-formats",
    labelKey: "projectSettings.sectionDocFormats",
    icon: FileType,
    isAvailable: (ctx) => ctx.hasDocFormats,
  },
  {
    id: "shared-docs",
    labelKey: "projectSettings.sectionSharedDocs",
    icon: Files,
    isAvailable: (ctx) => ctx.isTeam,
  },
  {
    id: "authors",
    labelKey: "projectSettings.sectionAuthors",
    icon: Users,
  },
  {
    id: "access",
    labelKey: "projectSettings.sectionAccess",
    icon: ShieldCheck,
    isAvailable: (ctx) => ctx.hasAccess === true,
  },
  {
    id: "meta",
    labelKey: "projectSettings.sectionMeta",
    icon: Tag,
    isAvailable: (ctx) => ctx.hasMetaFields,
  },
  {
    id: "fonts",
    labelKey: "projectSettings.sectionFonts",
    icon: Type,
  },
  {
    id: "supervisor",
    labelKey: "projectSettings.sectionSupervisor",
    icon: GraduationCap,
  },
  {
    id: "checks",
    labelKey: "projectChecks.title",
    icon: ListChecks,
  },
  {
    id: "sync-remote",
    labelKey: "projectSettings.sectionSyncRemote",
    icon: GitBranch,
    isAvailable: (ctx) => ctx.syncSupported,
  },
  {
    id: "sync-options",
    labelKey: "projectSettings.sectionSyncOptions",
    icon: Timer,
    isAvailable: (ctx) => ctx.syncSupported && ctx.syncConnected,
  },
  {
    id: "sync-shared-folder",
    labelKey: "projectSettings.sectionSyncSharedFolder",
    icon: FolderSync,
    isAvailable: (ctx) =>
      ctx.syncSupported && ctx.syncConnected && ctx.hasSharedFolder,
  },
  // Обмен файлом и автосборка не требуют подключённого репозитория: файл можно
  // передать без сервера, а настройки CI подготовить до подключения.
  {
    id: "sync-exchange",
    labelKey: "projectSettings.sectionSyncExchange",
    icon: ArrowLeftRight,
    isAvailable: (ctx) => ctx.syncSupported,
  },
  {
    id: "sync-ci",
    labelKey: "projectSettings.sectionSyncCi",
    icon: Workflow,
    isAvailable: (ctx) => ctx.syncSupported,
  },
  // gitremote: адрес проекта для git на сервере (раздел 10.12).
  {
    id: "sync-server-clone",
    labelKey: "projectSettings.sectionSyncServerClone",
    icon: Download,
    isAvailable: (ctx) => ctx.hasGitRemote === true,
  },
  {
    id: "danger-zone",
    labelKey: "projectSettings.sectionDangerZone",
    icon: AlertTriangle,
  },
];

export const DEFAULT_PROJECT_SETTINGS_SECTION: ProjectSettingsSectionId =
  "general";

export const visibleProjectSettingsSections = (
  ctx: ProjectSettingsSectionContext,
): ProjectSettingsSectionDef[] =>
  PROJECT_SETTINGS_SECTIONS.filter((s) => s.isAvailable?.(ctx) ?? true);

/**
 * Группы разделов — то, чем на самом деле навигируют.
 *
 * Десять отдельных страниц оказались перебором в другую сторону от простыни:
 * искать нужный пункт среди десяти не легче, чем скроллить. Группа — это одна
 * страница с одной-тремя карточками; разделы внутри неё остаются теми же
 * компонентами и рендерятся стопкой, как раньше.
 *
 * «Опасная зона» намеренно живёт внизу «Проекта», а не отдельным пунктом:
 * удаление проекта не заслуживает собственной строки в навигации, но и
 * прятать его не следует.
 */
export type ProjectSettingsGroupId =
  "project" | "people" | "documents" | "meta" | "checks" | "sync";

export type ProjectSettingsGroupDef = {
  id: ProjectSettingsGroupId;
  /** Ключ в namespace "workbench". */
  labelKey: string;
  icon: LucideIcon;
  sections: readonly ProjectSettingsSectionId[];
};

export const PROJECT_SETTINGS_GROUPS: readonly ProjectSettingsGroupDef[] = [
  {
    id: "project",
    labelKey: "projectSettingsNav.groupProject",
    icon: Info,
    sections: [
      "general",
      "template",
      "confidentiality",
      "builds",
      "danger-zone",
    ],
  },
  {
    id: "people",
    labelKey: "projectSettingsNav.groupPeople",
    icon: Users,
    sections: ["authors", "access", "supervisor"],
  },
  {
    id: "documents",
    labelKey: "projectSettingsNav.groupDocuments",
    icon: FileType,
    sections: ["doc-set", "doc-formats", "shared-docs", "fonts"],
  },
  {
    id: "meta",
    labelKey: "projectSettingsNav.groupMeta",
    icon: Tag,
    sections: ["meta"],
  },
  {
    id: "checks",
    labelKey: "projectSettingsNav.groupChecks",
    icon: ListChecks,
    sections: ["checks"],
  },
  {
    id: "sync",
    labelKey: "projectSettingsNav.groupSync",
    icon: CloudUpload,
    sections: [
      "sync-server-clone",
      "sync-remote",
      "sync-options",
      "sync-shared-folder",
      "sync-exchange",
      "sync-ci",
    ],
  },
];

export const DEFAULT_PROJECT_SETTINGS_GROUP: ProjectSettingsGroupId = "project";

// Безусловная группа: на неё откатывается разбор маршрута, поэтому она обязана
// существовать как значение, а не как результат поиска по массиву.
const PROJECT_SETTINGS_PROJECT_GROUP: ProjectSettingsGroupDef = {
  id: "project",
  labelKey: "projectSettingsNav.groupProject",
  icon: Info,
  sections: ["general", "template", "confidentiality", "builds", "danger-zone"],
};

/** Группа видна, пока хоть один её раздел доступен в этом проекте. */
export const visibleProjectSettingsGroups = (
  ctx: ProjectSettingsSectionContext,
): ProjectSettingsGroupDef[] => {
  const available = new Set(
    visibleProjectSettingsSections(ctx).map((section) => section.id),
  );
  return PROJECT_SETTINGS_GROUPS.filter((group) =>
    group.sections.some((id) => available.has(id)),
  );
};

/** Разделы группы, уже отфильтрованные по доступности и в порядке страницы. */
export const groupSections = (
  group: ProjectSettingsGroupDef,
  ctx: ProjectSettingsSectionContext,
): ProjectSettingsSectionDef[] => {
  const available = new Set(
    visibleProjectSettingsSections(ctx).map((section) => section.id),
  );
  return group.sections
    .filter((id) => available.has(id))
    .flatMap((id) => PROJECT_SETTINGS_SECTIONS.filter((s) => s.id === id));
};

/**
 * Разбор параметра маршрута. Незнакомое значение — опечатка или ссылка из
 * другой версии: открываем группу по умолчанию, а не пустой канвас.
 */
export const resolveProjectSettingsGroup = (
  param: string,
  ctx: ProjectSettingsSectionContext,
): ProjectSettingsGroupDef => {
  const visible = visibleProjectSettingsGroups(ctx);
  const byGroup = visible.find((group) => group.id === param);
  if (byGroup) return byGroup;
  // Ссылка на конкретный раздел открывает группу, в которой он живёт.
  const bySection = visible.find((group) =>
    (group.sections as readonly string[]).includes(param),
  );
  if (bySection) return bySection;
  // Ни одна группа не доступна — вырожденный проект без единой настройки.
  // «Проект» существует всегда: он содержит «Общую информацию» без условий.
  return (
    visible.find((group) => group.id === DEFAULT_PROJECT_SETTINGS_GROUP) ??
    visible[0] ??
    PROJECT_SETTINGS_PROJECT_GROUP
  );
};
